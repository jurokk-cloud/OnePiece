from __future__ import annotations

import logging
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from ase import Atoms
from ase.data import atomic_numbers, covalent_radii
from ase.neighborlist import NeighborList, natural_cutoffs

from onepiece._compat import trapezoid
from onepiece.adsorption import assign_surface_references, primary_structure
from onepiece.frame_utils import ensure_name_index, row_name
from onepiece.vasp import (
    DoscarData,
    _as_array,
    adsorbate_atom_indices_from_structures,
    matched_surface_atom_indices_from_structures,
    read_doscar,
)

SURFACE_NORMAL = np.array([0.0, 0.0, 1.0], dtype=float)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CoordinationEnvironment:
    """Packed coordination graph for efficient repeated local-environment calculations."""

    indptr: np.ndarray
    indices: np.ndarray
    coordination: np.ndarray
    cutoff_scale: float = 1.2

    @property
    def natoms(self) -> int:
        return int(self.coordination.shape[0])

    def neighbors_of(self, atom_index: int) -> np.ndarray:
        index = int(atom_index)
        start = int(self.indptr[index])
        stop = int(self.indptr[index + 1])
        return self.indices[start:stop]

    def to_neighbor_graph(self) -> list[list[int]]:
        return [self.neighbors_of(atom_index).astype(int, copy=False).tolist() for atom_index in range(self.natoms)]

    def generalized_coordination_numbers(self, *, max_coordination: float = 12.0) -> np.ndarray:
        denominator = float(max(max_coordination, 1.0))
        gcn = np.zeros(self.natoms, dtype=float)
        if self.indices.size == 0:
            return gcn
        weights = self.coordination[self.indices].astype(float, copy=False)
        starts = self.indptr[:-1]
        nonempty = self.indptr[1:] > starts
        if np.any(nonempty):
            gcn[nonempty] = np.add.reduceat(weights, starts[nonempty]) / denominator
        return gcn


def coordination_environment(atoms: Atoms, *, cutoff_scale: float = 1.2) -> CoordinationEnvironment:
    if len(atoms) == 0:
        empty = np.zeros(0, dtype=np.int32)
        return CoordinationEnvironment(
            indptr=np.zeros(1, dtype=np.int32),
            indices=empty,
            coordination=empty,
            cutoff_scale=float(cutoff_scale),
        )

    cutoffs = natural_cutoffs(atoms, mult=cutoff_scale)
    neighbors = NeighborList(cutoffs, self_interaction=False, bothways=True)
    neighbors.update(atoms)

    flat_neighbors: list[np.ndarray] = []
    indptr = np.zeros(len(atoms) + 1, dtype=np.int32)
    coordination = np.zeros(len(atoms), dtype=np.int32)
    cursor = 0
    for atom_index in range(len(atoms)):
        indices, _ = neighbors.get_neighbors(atom_index)
        if len(indices):
            unique = np.unique(np.asarray(indices, dtype=np.int32))
            unique = unique[unique != atom_index]
        else:
            unique = np.zeros(0, dtype=np.int32)
        flat_neighbors.append(unique)
        coordination[atom_index] = np.int32(unique.size)
        cursor += int(unique.size)
        indptr[atom_index + 1] = np.int32(cursor)

    packed = np.concatenate(flat_neighbors).astype(np.int32, copy=False) if flat_neighbors else np.zeros(0, dtype=np.int32)
    return CoordinationEnvironment(
        indptr=indptr,
        indices=packed,
        coordination=coordination,
        cutoff_scale=float(cutoff_scale),
    )


def _coerce_coordination_environment(
    atoms_or_environment: Atoms | CoordinationEnvironment,
    *,
    cutoff_scale: float = 1.2,
) -> CoordinationEnvironment:
    if isinstance(atoms_or_environment, CoordinationEnvironment):
        return atoms_or_environment
    return coordination_environment(atoms_or_environment, cutoff_scale=cutoff_scale)


def infer_atomic_layers(atoms: Atoms, *, axis: int = 2, tolerance: float = 0.75) -> np.ndarray:
    positions = np.asarray(atoms.get_positions(), dtype=float)
    if positions.size == 0:
        return np.array([], dtype=int)
    order = np.argsort(positions[:, axis])
    sorted_coords = positions[order, axis]
    labels = np.zeros(len(atoms), dtype=int)
    current_layer = 0
    anchor = float(sorted_coords[0])
    labels[order[0]] = current_layer
    for atom_index, coordinate in zip(order[1:], sorted_coords[1:], strict=False):
        if float(coordinate) - anchor > float(tolerance):
            current_layer += 1
            anchor = float(coordinate)
        labels[atom_index] = current_layer
    return labels


def identify_surface_atom_indices(
    atoms: Atoms,
    *,
    axis: int = 2,
    top_layers: int = 1,
    tolerance: float = 0.75,
    bottom: bool = False,
) -> list[int]:
    if len(atoms) == 0:
        return []
    labels = infer_atomic_layers(atoms, axis=axis, tolerance=tolerance)
    unique_layers = np.unique(labels)
    if unique_layers.size == 0:
        return []
    if bottom:
        chosen = set(int(value) for value in unique_layers[: max(1, int(top_layers))])
    else:
        chosen = set(int(value) for value in unique_layers[-max(1, int(top_layers)) :])
    return [int(index) for index, label in enumerate(labels) if int(label) in chosen]


def slab_thickness(atoms: Atoms, *, axis: int = 2) -> float:
    positions = np.asarray(atoms.get_positions(), dtype=float)
    if positions.size == 0:
        return float("nan")
    return float(np.ptp(positions[:, axis]))


def vacuum_thickness(atoms: Atoms, *, axis: int = 2) -> float:
    if len(atoms) == 0:
        return float("nan")
    cell_vector = np.asarray(atoms.cell.array, dtype=float)[axis]
    cell_length = float(np.linalg.norm(cell_vector))
    if cell_length == 0.0:
        return float("nan")
    return float(max(cell_length - slab_thickness(atoms, axis=axis), 0.0))


def nearest_neighbor_distances(atoms: Atoms, *, mic: bool = True) -> np.ndarray:
    if len(atoms) <= 1:
        return np.full(len(atoms), np.nan, dtype=float)
    distances = np.asarray(atoms.get_all_distances(mic=mic), dtype=float)
    np.fill_diagonal(distances, np.inf)
    nearest = np.min(distances, axis=1)
    nearest[~np.isfinite(nearest)] = np.nan
    return nearest


def coordination_numbers(
    atoms_or_environment: Atoms | CoordinationEnvironment,
    *,
    cutoff_scale: float = 1.2,
) -> np.ndarray:
    environment = _coerce_coordination_environment(atoms_or_environment, cutoff_scale=cutoff_scale)
    return environment.coordination.astype(float, copy=True)


def generalized_coordination_numbers(
    atoms_or_environment: Atoms | CoordinationEnvironment,
    *,
    cutoff_scale: float = 1.2,
    max_coordination: float = 12.0,
) -> np.ndarray:
    environment = _coerce_coordination_environment(atoms_or_environment, cutoff_scale=cutoff_scale)
    return environment.generalized_coordination_numbers(max_coordination=max_coordination)


def plot_structure_value_3d(
    atoms: Atoms,
    values: Sequence[float],
    title: str,
    *,
    elev: float = 20.0,
    azim: float = 120.0,
    size: float = 400.0,
    colorbar_ticks: Sequence[float] | None = None,
    edgecolors: str | Sequence[str] | None = None,
    cmap: str = "nipy_spectral",
    vmin: float | None = None,
    vmax: float | None = None,
):
    """Plot per-atom ``values`` as a 3D scatter over an ASE structure.

    .. code-block:: python

        from onepiece import plot_structure_value_3d

        fig = plot_structure_value_3d(atoms, gcn_values, title="GCN")
    """
    try:
        import matplotlib.cm as cm
        import matplotlib.colors as mcolors
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("matplotlib is required for 3D structure plots.") from exc

    data = np.asarray(values, dtype=float).reshape(-1)
    if data.shape[0] != len(atoms):
        raise ValueError("values must have the same length as atoms.")

    positions = np.asarray(atoms.get_positions(), dtype=float)
    finite = np.isfinite(data)
    if not finite.any():
        raise ValueError("values does not contain any finite entries to plot.")

    lower = float(np.nanmin(data[finite])) if vmin is None else float(vmin)
    upper = float(np.nanmax(data[finite])) if vmax is None else float(vmax)
    if np.isclose(lower, upper):
        lower -= 0.5
        upper += 0.5
    normalize = mcolors.Normalize(vmin=lower, vmax=upper)
    colormap = plt.get_cmap(cmap)

    fig = plt.figure()
    ax = fig.add_subplot(projection="3d", title=title)
    ax.scatter(
        positions[finite, 0],
        positions[finite, 1],
        positions[finite, 2],
        c=colormap(normalize(data[finite])),
        s=size,
        alpha=1.0,
        edgecolors=edgecolors,
    )
    if (~finite).any():
        ax.scatter(
            positions[~finite, 0],
            positions[~finite, 1],
            positions[~finite, 2],
            c="#d9d9d9",
            s=size * 0.75,
            alpha=0.35,
            edgecolors=edgecolors,
        )

    ax.set_xlabel("a")
    ax.set_ylabel("b")
    ax.set_zlabel("c")
    ax.view_init(elev=elev, azim=azim)
    scalarmappable = cm.ScalarMappable(norm=normalize, cmap=colormap)
    scalarmappable.set_array(data[finite])
    ax.axis("off")
    ax.set_aspect("equal")
    fig.colorbar(scalarmappable, ticks=colorbar_ticks, ax=ax)
    return fig, ax


def plot_row_metric_3d(
    row: pd.Series,
    value_column: str,
    *,
    structure_column: str = "struc",
    title: str | None = None,
    elev: float = 20.0,
    azim: float = 120.0,
    size: float = 400.0,
    colorbar_ticks: Sequence[float] | None = None,
    edgecolors: str | Sequence[str] | None = None,
    cmap: str = "nipy_spectral",
    vmin: float | None = None,
    vmax: float | None = None,
):
    """Plot a per-atom metric column for a single dataframe row in 3D.

    .. code-block:: python

        from onepiece import plot_row_metric_3d

        fig = plot_row_metric_3d(frame.iloc[0], "atomic_charge_e")
    """
    atoms = row.get(structure_column)
    if atoms is None or atoms.__class__.__name__ != "Atoms":
        raise ValueError(f"Row does not contain an ASE Atoms object in column '{structure_column}'.")
    values = _as_array(row.get(value_column))
    if values is None:
        raise ValueError(f"Row does not contain numeric values in column '{value_column}'.")
    resolved_title = title or f"{row_name(row)} | {value_column}"
    return plot_structure_value_3d(
        atoms,
        values,
        resolved_title,
        elev=elev,
        azim=azim,
        size=size,
        colorbar_ticks=colorbar_ticks,
        edgecolors=edgecolors,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
    )


def save_dataframe_metric_plots_3d(
    frame: pd.DataFrame,
    metric_columns: Sequence[str],
    *,
    output_dir: Path | str,
    structure_column: str = "struc",
    elev: float = 20.0,
    azim: float = 120.0,
    size: float = 400.0,
    cmap: str = "nipy_spectral",
) -> pd.DataFrame:
    """Save a 3D metric plot per metric column and return an index frame.

    .. code-block:: python

        from onepiece import save_dataframe_metric_plots_3d

        index = save_dataframe_metric_plots_3d(
            frame, ["atomic_charge_e"], output_dir="plots"
        )
    """
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("matplotlib is required for 3D structure plots.") from exc

    df = ensure_name_index(frame)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []

    for _, row in df.iterrows():
        atoms = row.get(structure_column)
        if atoms is None or atoms.__class__.__name__ != "Atoms":
            continue
        name = row_name(row)
        for metric in metric_columns:
            values = _as_array(row.get(metric))
            if values is None or values.shape[0] != len(atoms) or not np.isfinite(values).any():
                continue
            fig, _ = plot_structure_value_3d(
                atoms,
                values,
                f"{name} | {metric}",
                elev=elev,
                azim=azim,
                size=size,
                cmap=cmap,
            )
            filename = f"{_slugify(name)}__{_slugify(metric)}.png"
            output_path = destination / filename
            fig.savefig(output_path, dpi=200, bbox_inches="tight")
            plt.close(fig)
            records.append({"Name": name, "metric": metric, "plot_path": str(output_path)})

    return pd.DataFrame(records)


def map_atoms_by_species_and_position(reference_atoms: Atoms, target_atoms: Atoms) -> list[int]:
    if len(reference_atoms) == 0:
        return []
    target_positions = np.asarray(target_atoms.get_positions(), dtype=float)
    target_symbols = list(target_atoms.get_chemical_symbols())
    unmatched = set(range(len(target_atoms)))
    matched: list[int] = []
    for symbol, position in zip(reference_atoms.get_chemical_symbols(), reference_atoms.get_positions(), strict=False):
        candidates = [idx for idx in unmatched if target_symbols[idx] == symbol]
        if not candidates:
            return []
        distances = [float(np.linalg.norm(target_positions[idx] - position)) for idx in candidates]
        best = candidates[int(np.argmin(distances))]
        matched.append(best)
        unmatched.remove(best)
    return matched


def compare_structures_rmsd(reference_atoms: Atoms, target_atoms: Atoms) -> float:
    if len(reference_atoms) != len(target_atoms):
        raise ValueError("RMSD comparison requires structures with the same atom count.")
    mapping = map_atoms_by_species_and_position(reference_atoms, target_atoms)
    if len(mapping) != len(reference_atoms):
        return float("nan")
    reference_positions = np.asarray(reference_atoms.get_positions(), dtype=float)
    target_positions = np.asarray(target_atoms.get_positions(), dtype=float)[mapping]
    deltas = target_positions - reference_positions
    return float(np.sqrt(np.mean(np.sum(deltas**2, axis=1))))


def adsorbate_surface_distance_summary(
    total_atoms: Atoms,
    surface_atoms: Atoms,
    *,
    cutoff_scale: float = 1.25,
) -> dict[str, float]:
    adsorbate_indices = adsorbate_atom_indices_from_structures(total_atoms, surface_atoms)
    surface_indices = matched_surface_atom_indices_from_structures(total_atoms, surface_atoms)
    if not adsorbate_indices or not surface_indices:
        return {
            "adsorbate_surface_bond_count": 0.0,
            "min_adsorbate_surface_distance": float("nan"),
            "mean_adsorbate_surface_distance": float("nan"),
        }
    distances = np.asarray(total_atoms.get_all_distances(mic=True), dtype=float)
    symbols = total_atoms.get_chemical_symbols()
    close_pairs = 0
    pair_distances: list[float] = []
    for ads_index in adsorbate_indices:
        for surface_index in surface_indices:
            distance = float(distances[ads_index, surface_index])
            pair_distances.append(distance)
            threshold = cutoff_scale * (
                covalent_radii[atomic_numbers[symbols[ads_index]]]
                + covalent_radii[atomic_numbers[symbols[surface_index]]]
            )
            if distance <= threshold:
                close_pairs += 1
    return {
        "adsorbate_surface_bond_count": float(close_pairs),
        "min_adsorbate_surface_distance": float(np.min(pair_distances)) if pair_distances else float("nan"),
        "mean_adsorbate_surface_distance": float(np.mean(pair_distances)) if pair_distances else float("nan"),
    }


def classify_adsorption_site(
    total_atoms: Atoms,
    surface_atoms: Atoms,
    *,
    top_layers: int = 1,
    tolerance: float = 0.75,
    site_tolerance: float = 0.35,
    desorption_distance: float = 3.2,
) -> str:
    adsorbate_indices = adsorbate_atom_indices_from_structures(total_atoms, surface_atoms)
    if not adsorbate_indices:
        return "clean_surface"
    surface_mapping = map_atoms_by_species_and_position(surface_atoms, total_atoms)
    if not surface_mapping:
        return "unknown"
    top_surface_indices = identify_surface_atom_indices(surface_atoms, top_layers=top_layers, tolerance=tolerance)
    if not top_surface_indices:
        return "unknown"
    total_top_indices = [surface_mapping[index] for index in top_surface_indices if index < len(surface_mapping)]
    if not total_top_indices:
        return "unknown"

    positions = np.asarray(total_atoms.get_positions(), dtype=float)
    anchor_index = min(adsorbate_indices, key=lambda idx: float(positions[idx, 2]))
    anchor = positions[anchor_index]
    top_positions = positions[total_top_indices]
    distances = np.linalg.norm(top_positions - anchor, axis=1)
    min_distance = float(np.min(distances))
    if min_distance > float(desorption_distance):
        return "desorbed"
    nearby = int(np.sum(distances <= min_distance + float(site_tolerance)))
    if nearby <= 0:
        return "desorbed"
    if nearby == 1:
        return "top"
    if nearby == 2:
        return "bridge"
    if nearby == 3:
        return "hollow"
    return "defect_like"


def adsorbate_orientation_angle(total_atoms: Atoms, surface_atoms: Atoms) -> float:
    adsorbate_indices = adsorbate_atom_indices_from_structures(total_atoms, surface_atoms)
    if not adsorbate_indices:
        return float("nan")
    positions = np.asarray(total_atoms.get_positions(), dtype=float)[adsorbate_indices]
    if len(positions) == 1:
        return 0.0
    centered = positions - positions.mean(axis=0)
    _, _, vectors = np.linalg.svd(centered, full_matrices=False)
    axis_vector = vectors[0]
    cosine = abs(float(np.dot(axis_vector, SURFACE_NORMAL) / np.linalg.norm(axis_vector)))
    cosine = min(max(cosine, -1.0), 1.0)
    return float(np.degrees(np.arccos(cosine)))


def detect_adsorbate_dissociation(
    total_atoms: Atoms,
    surface_atoms: Atoms,
    *,
    cutoff_scale: float = 1.15,
) -> dict[str, float | bool]:
    adsorbate_indices = adsorbate_atom_indices_from_structures(total_atoms, surface_atoms)
    if len(adsorbate_indices) <= 1:
        return {"adsorbate_fragment_count": 1.0 if adsorbate_indices else 0.0, "adsorbate_is_dissociated": False}
    adsorbate = total_atoms[adsorbate_indices]
    graph = neighbor_graph(adsorbate, cutoff_scale=cutoff_scale)
    fragments = connected_component_count(graph)
    return {
        "adsorbate_fragment_count": float(fragments),
        "adsorbate_is_dissociated": bool(fragments > 1),
    }


def surface_reconstruction_metrics(total_atoms: Atoms, surface_atoms: Atoms) -> dict[str, float]:
    matched = matched_surface_atom_indices_from_structures(total_atoms, surface_atoms)
    if len(matched) != len(surface_atoms):
        return {
            "surface_reconstruction_rmsd": float("nan"),
            "surface_reconstruction_max_displacement": float("nan"),
        }
    total_positions = np.asarray(total_atoms.get_positions(), dtype=float)[matched]
    reference_positions = np.asarray(surface_atoms.get_positions(), dtype=float)
    displacements = np.linalg.norm(total_positions - reference_positions, axis=1)
    return {
        "surface_reconstruction_rmsd": float(np.sqrt(np.mean(displacements**2))),
        "surface_reconstruction_max_displacement": float(np.max(displacements)) if displacements.size else float("nan"),
    }


def reaction_path_geometry_summary(
    images: Sequence[Atoms],
    *,
    surface_reference: Atoms | None = None,
) -> dict[str, float]:
    if not images:
        return {
            "path_image_count": 0.0,
            "path_max_rmsd_from_initial": float("nan"),
            "path_max_step_rmsd": float("nan"),
            "path_max_adsorbate_height_change": float("nan"),
        }
    initial = images[0]
    initial_rmsd = []
    step_rmsd = []
    height_changes = []
    base_height = None
    if surface_reference is not None:
        summary = adsorbate_surface_distance_summary(initial, surface_reference)
        base_height = summary["min_adsorbate_surface_distance"]
    previous = initial
    for image in images:
        initial_rmsd.append(compare_structures_rmsd(initial, image))
        step_rmsd.append(compare_structures_rmsd(previous, image))
        previous = image
        if surface_reference is not None and base_height is not None:
            current = adsorbate_surface_distance_summary(image, surface_reference)
            if np.isfinite(current["min_adsorbate_surface_distance"]):
                height_changes.append(float(current["min_adsorbate_surface_distance"] - base_height))
    return {
        "path_image_count": float(len(images)),
        "path_max_rmsd_from_initial": float(np.nanmax(initial_rmsd)),
        "path_max_step_rmsd": float(np.nanmax(step_rmsd)),
        "path_max_adsorbate_height_change": float(np.nanmax(np.abs(height_changes))) if height_changes else float("nan"),
    }


def compute_d_band_center(
    doscar: DoscarData | Path | str,
    *,
    atom_indices: Sequence[int] | None = None,
    energy_window: tuple[float, float] = (-8.0, 2.0),
    spin: str = "sum",
) -> float:
    energies, signal = projected_dos_signal(doscar, atom_indices=atom_indices, orbital_selector="d", spin=spin)
    mask = _window_mask(energies, energy_window)
    if not mask.any():
        return float("nan")
    weights = signal[mask]
    norm = float(trapezoid(weights, energies[mask]))
    if abs(norm) < 1e-12:
        return float("nan")
    return float(trapezoid(energies[mask] * weights, energies[mask]) / norm)


def compute_d_band_filling(
    doscar: DoscarData | Path | str,
    *,
    atom_indices: Sequence[int] | None = None,
    energy_window: tuple[float, float] = (-8.0, 2.0),
    spin: str = "sum",
    normalize: bool = True,
) -> float:
    energies, signal = projected_dos_signal(doscar, atom_indices=atom_indices, orbital_selector="d", spin=spin)
    total_mask = _window_mask(energies, energy_window)
    occupied_mask = _window_mask(energies, (energy_window[0], min(energy_window[1], 0.0)))
    if not occupied_mask.any():
        return 0.0
    occupied = float(trapezoid(signal[occupied_mask], energies[occupied_mask]))
    if not normalize:
        return occupied
    total = float(trapezoid(signal[total_mask], energies[total_mask])) if total_mask.any() else 0.0
    if abs(total) < 1e-12:
        return float("nan")
    return float(occupied / total)


def summarize_charge_transfer_by_layer(
    atoms: Atoms,
    atomic_charges: Sequence[float],
    *,
    tolerance: float = 0.75,
) -> dict[str, float]:
    charges = np.asarray(atomic_charges, dtype=float)
    if charges.shape[0] != len(atoms):
        raise ValueError("atomic_charges must have the same length as atoms.")
    labels = infer_atomic_layers(atoms, tolerance=tolerance)
    unique_layers = np.unique(labels)
    if unique_layers.size == 0:
        return {
            "top_layer_charge_sum_e": float("nan"),
            "bottom_layer_charge_sum_e": float("nan"),
            "layer_charge_span_e": float("nan"),
        }
    sums = {int(layer): float(charges[labels == layer].sum()) for layer in unique_layers}
    top = sums[int(unique_layers[-1])]
    bottom = sums[int(unique_layers[0])]
    return {
        "top_layer_charge_sum_e": top,
        "bottom_layer_charge_sum_e": bottom,
        "layer_charge_span_e": float(top - bottom),
    }


def detect_overlapping_atoms(atoms: Atoms, *, min_distance: float = 0.6) -> dict[str, float | bool]:
    distances = nearest_neighbor_distances(atoms)
    finite = distances[np.isfinite(distances)]
    minimum = float(np.min(finite)) if finite.size else float("nan")
    return {
        "min_interatomic_distance": minimum,
        "has_overlapping_atoms": bool(np.isfinite(minimum) and minimum < float(min_distance)),
    }


def detect_unphysical_bonds(atoms: Atoms, *, lower_scale: float = 0.55) -> dict[str, float | bool]:
    if len(atoms) <= 1:
        return {"min_bond_ratio": float("nan"), "has_unphysical_bonds": False}
    distances = np.asarray(atoms.get_all_distances(mic=True), dtype=float)
    symbols = atoms.get_chemical_symbols()
    ratios: list[float] = []
    for i in range(len(atoms)):
        for j in range(i + 1, len(atoms)):
            reference = covalent_radii[atomic_numbers[symbols[i]]] + covalent_radii[atomic_numbers[symbols[j]]]
            if reference <= 0.0:
                continue
            ratios.append(float(distances[i, j] / reference))
    minimum_ratio = float(np.min(ratios)) if ratios else float("nan")
    return {
        "min_bond_ratio": minimum_ratio,
        "has_unphysical_bonds": bool(np.isfinite(minimum_ratio) and minimum_ratio < float(lower_scale)),
    }


def detect_adsorbate_desorption(
    total_atoms: Atoms,
    surface_atoms: Atoms,
    *,
    max_distance: float = 3.2,
) -> bool:
    summary = adsorbate_surface_distance_summary(total_atoms, surface_atoms)
    minimum = summary["min_adsorbate_surface_distance"]
    return bool(np.isfinite(minimum) and minimum > float(max_distance))


def add_ase_analysis_descriptors(
    frame: pd.DataFrame,
    *,
    structure_column: str = "struc",
    include_pdos: bool = False,
    calculation_path_column: str = "Path",
    doscar_path_column: str = "doscar_path",
    dos_filename: str = "DOSCAR",
) -> pd.DataFrame:
    df = assign_surface_references(frame.copy())
    df["primary_atoms"] = df.apply(
        lambda row: primary_structure(row, structure_columns=(structure_column, "CONTCAR", "structure", "atoms")),
        axis=1,
    )
    surface_rows = df.loc[
        df["Name"].astype(str).eq(df["surface_ref_name"].astype(str)) & df["primary_atoms"].notna(),
        ["Name", "primary_atoms"],
    ].drop_duplicates("Name")
    surface_map = surface_rows.set_index("Name")["primary_atoms"].to_dict()
    df["surface_ref_atoms"] = df["surface_ref_name"].map(surface_map)

    for column in (
        "layer_count",
        "slab_thickness",
        "vacuum_thickness",
        "mean_coordination",
        "min_coordination",
        "max_coordination",
        "mean_generalized_coordination",
        "adsorbate_surface_bond_count",
        "min_adsorbate_surface_distance",
        "mean_adsorbate_surface_distance",
        "adsorbate_tilt_deg",
        "adsorbate_fragment_count",
        "surface_reconstruction_rmsd",
        "surface_reconstruction_max_displacement",
        "min_interatomic_distance",
        "min_bond_ratio",
        "metal_d_band_center_eV",
        "metal_d_band_filling",
        "top_layer_charge_sum_e",
        "bottom_layer_charge_sum_e",
        "layer_charge_span_e",
    ):
        if column not in df.columns:
            df[column] = np.nan
    for column in ("atomic_coordination_numbers", "atomic_generalized_coordination_numbers"):
        if column not in df.columns:
            df[column] = None
    for column in ("adsorption_site",):
        if column not in df.columns:
            df[column] = ""
    for column in ("adsorbate_is_dissociated", "adsorbate_desorbed", "has_overlapping_atoms", "has_unphysical_bonds"):
        if column not in df.columns:
            df[column] = False

    for index, row in df.iterrows():
        atoms = row.get("primary_atoms")
        if atoms is None or atoms.__class__.__name__ != "Atoms":
            continue
        active_atoms = atoms
        surface_atoms = row.get("surface_ref_atoms")
        if surface_atoms is None or surface_atoms.__class__.__name__ != "Atoms":
            surface_atoms = active_atoms
        layers = infer_atomic_layers(surface_atoms)
        df.at[index, "layer_count"] = float(np.unique(layers).size) if layers.size else np.nan
        df.at[index, "slab_thickness"] = slab_thickness(surface_atoms)
        df.at[index, "vacuum_thickness"] = vacuum_thickness(surface_atoms)

        environment = coordination_environment(active_atoms)
        coordination = coordination_numbers(environment)
        gcn = generalized_coordination_numbers(environment)
        df.at[index, "atomic_coordination_numbers"] = coordination.tolist() if coordination.size else None
        df.at[index, "atomic_generalized_coordination_numbers"] = gcn.tolist() if gcn.size else None
        if coordination.size:
            df.at[index, "mean_coordination"] = float(np.mean(coordination))
            df.at[index, "min_coordination"] = float(np.min(coordination))
            df.at[index, "max_coordination"] = float(np.max(coordination))
        if gcn.size:
            df.at[index, "mean_generalized_coordination"] = float(np.mean(gcn))
            symbols = np.asarray(active_atoms.get_chemical_symbols())
            for symbol in sorted(set(symbols)):
                symbol_values = gcn[symbols == symbol]
                df.at[index, f"average_{symbol}_GCN"] = float(np.mean(symbol_values))
                df.at[index, f"min_{symbol}_GCN"] = float(np.min(symbol_values))
                df.at[index, f"max_{symbol}_GCN"] = float(np.max(symbol_values))

        overlap = detect_overlapping_atoms(active_atoms)
        unphysical = detect_unphysical_bonds(active_atoms)
        df.at[index, "min_interatomic_distance"] = overlap["min_interatomic_distance"]
        df.at[index, "has_overlapping_atoms"] = overlap["has_overlapping_atoms"]
        df.at[index, "min_bond_ratio"] = unphysical["min_bond_ratio"]
        df.at[index, "has_unphysical_bonds"] = unphysical["has_unphysical_bonds"]

        adsorbate_indices = adsorbate_atom_indices_from_structures(active_atoms, surface_atoms)
        if adsorbate_indices:
            distance_summary = adsorbate_surface_distance_summary(active_atoms, surface_atoms)
            reconstruction = surface_reconstruction_metrics(active_atoms, surface_atoms)
            dissociation = detect_adsorbate_dissociation(active_atoms, surface_atoms)
            df.at[index, "adsorbate_surface_bond_count"] = distance_summary["adsorbate_surface_bond_count"]
            df.at[index, "min_adsorbate_surface_distance"] = distance_summary["min_adsorbate_surface_distance"]
            df.at[index, "mean_adsorbate_surface_distance"] = distance_summary["mean_adsorbate_surface_distance"]
            df.at[index, "adsorption_site"] = classify_adsorption_site(active_atoms, surface_atoms)
            df.at[index, "adsorbate_tilt_deg"] = adsorbate_orientation_angle(active_atoms, surface_atoms)
            df.at[index, "adsorbate_fragment_count"] = dissociation["adsorbate_fragment_count"]
            df.at[index, "adsorbate_is_dissociated"] = dissociation["adsorbate_is_dissociated"]
            df.at[index, "surface_reconstruction_rmsd"] = reconstruction["surface_reconstruction_rmsd"]
            df.at[index, "surface_reconstruction_max_displacement"] = reconstruction[
                "surface_reconstruction_max_displacement"
            ]
            df.at[index, "adsorbate_desorbed"] = detect_adsorbate_desorption(active_atoms, surface_atoms)

        charges = row.get("atomic_charges")
        if isinstance(charges, list | tuple | np.ndarray):
            charge_summary = summarize_charge_transfer_by_layer(active_atoms, charges)
            for key, value in charge_summary.items():
                df.at[index, key] = value

        if include_pdos:
            doscar_path = resolve_row_file_path(
                row,
                explicit_column=doscar_path_column,
                calculation_path_column=calculation_path_column,
                filename=dos_filename,
            )
            if doscar_path is not None and doscar_path.exists():
                try:
                    doscar = read_doscar(doscar_path)
                    surface_indices = matched_surface_atom_indices_from_structures(active_atoms, surface_atoms)
                    atom_indices = surface_indices or None
                    df.at[index, "metal_d_band_center_eV"] = compute_d_band_center(doscar, atom_indices=atom_indices)
                    df.at[index, "metal_d_band_filling"] = compute_d_band_filling(doscar, atom_indices=atom_indices)
                except Exception as exc:
                    logger.debug("Could not compute d-band descriptors for %s: %s", doscar_path, exc)

    return df


def neighbor_graph(atoms: Atoms, *, cutoff_scale: float = 1.2) -> list[list[int]]:
    return coordination_environment(atoms, cutoff_scale=cutoff_scale).to_neighbor_graph()


def connected_component_count(graph: Sequence[Sequence[int]]) -> int:
    if not graph:
        return 0
    seen: set[int] = set()
    components = 0
    for start in range(len(graph)):
        if start in seen:
            continue
        components += 1
        queue: deque[int] = deque([start])
        seen.add(start)
        while queue:
            current = queue.popleft()
            for neighbor in graph[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
    return components


def projected_dos_signal(
    doscar: DoscarData | Path | str,
    *,
    atom_indices: Sequence[int] | None = None,
    orbital_selector: str = "d",
    spin: str = "sum",
) -> tuple[np.ndarray, np.ndarray]:
    data = read_doscar(doscar) if isinstance(doscar, Path | str) else doscar
    if data.site_dos.size == 0:
        raise ValueError("DOSCAR does not contain site-projected DOS blocks.")
    indices = np.arange(data.natoms, dtype=int) if atom_indices is None else np.asarray(atom_indices, dtype=int)
    orbital_names = [
        name for name in data.orbital_columns if name.startswith(orbital_selector)
    ]
    if not orbital_names:
        raise ValueError(f"No projected orbitals starting with '{orbital_selector}' are available.")
    if spin == "up":
        orbital_names = [name for name in orbital_names if name.endswith(("-up", "+"))]
    elif spin == "down":
        orbital_names = [name for name in orbital_names if name.endswith(("-down", "-"))]
    signal = np.zeros_like(data.energies, dtype=float)
    for atom_index in indices:
        for orbital in orbital_names:
            signal += data.site_dos[atom_index, data.orbital_columns[orbital], :]
    return data.energies.copy(), signal


def resolve_row_file_path(
    row: pd.Series,
    *,
    explicit_column: str,
    calculation_path_column: str,
    filename: str,
) -> Path | None:
    explicit_value = row.get(explicit_column)
    if explicit_value is not None and not pd.isna(explicit_value):
        return resolve_vasp_file(explicit_value, filename=filename)
    calculation_value = row.get(calculation_path_column)
    if calculation_value is None or pd.isna(calculation_value):
        return None
    return resolve_vasp_file(calculation_value, filename=filename)


def _slugify(value: object) -> str:
    text = str(value).strip()
    if not text:
        return "unnamed"
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")


def resolve_vasp_file(pathlike: Path | str, *, filename: str) -> Path:
    path = Path(pathlike)
    if path.is_dir():
        return path / filename
    if path.name.upper() == filename.upper():
        return path
    return path.parent / filename


def _window_mask(energies: np.ndarray, energy_window: tuple[float, float]) -> np.ndarray:
    emin, emax = energy_window
    return (energies >= float(emin)) & (energies <= float(emax))
