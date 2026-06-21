from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from ase import Atoms
from ase.calculators.vasp.vasp_auxiliary import VaspChargeDensity, VaspDos
from ase.calculators.vasp.vasp_data import PDOS_orbital_names_and_DOSCAR_column

from onepiece._compat import trapezoid
from onepiece.adsorption import assign_surface_references, primary_structure
from onepiece.frame_utils import ensure_name_index, row_name
from onepiece.thermo import is_gas_phase_row


@dataclass(frozen=True, slots=True)
class ChgcarData:
    atoms: Atoms
    charge_density: np.ndarray
    voxel_volume: float
    source_path: str
    spin_density: np.ndarray | None = None

    @property
    def grid_shape(self) -> tuple[int, int, int]:
        return tuple(int(value) for value in self.charge_density.shape)


@dataclass(frozen=True, slots=True)
class DoscarData:
    energies: np.ndarray
    total_dos: np.ndarray
    integrated_total_dos: np.ndarray
    site_dos: np.ndarray
    efermi: float
    source_path: str
    orbital_columns: dict[str, int]

    @property
    def natoms(self) -> int:
        return int(self.site_dos.shape[0]) if self.site_dos.ndim == 3 else 0

    @property
    def spin_polarized(self) -> bool:
        return self.total_dos.shape[0] == 2


def read_acf_dat(path: Path | str, *, calculation_name: str | None = None) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    with Path(path).open(errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 7:
                continue
            if not parts[0].isdigit():
                continue
            rows.append(
                {
                    "atom_index": float(parts[0]),
                    "X": float(parts[1]),
                    "Y": float(parts[2]),
                    "Z": float(parts[3]),
                    "CHARGE": float(parts[4]),
                    "MIN DISTANCES": float(parts[5]),
                    "ATOMIC VOL": float(parts[6]),
                }
            )
    table = pd.DataFrame(
        rows,
        columns=["atom_index", "X", "Y", "Z", "CHARGE", "MIN DISTANCES", "ATOMIC VOL"],
    )
    if calculation_name:
        table.insert(0, "calculation_name", str(calculation_name))
        table["atom_index"] = table["atom_index"].astype(int)
        table = table.set_index(["calculation_name", "atom_index"], drop=False)
    return table


def read_chgcar(path: Path | str, *, image: int = -1) -> ChgcarData:
    charge = VaspChargeDensity(str(path))
    atoms = charge.atoms[image]
    density = np.array(charge.chg[image], copy=True)
    spin_density = None
    if charge.chgdiff:
        spin_density = np.array(charge.chgdiff[image], copy=True)
    voxel_volume = float(atoms.get_volume() / np.prod(density.shape))
    return ChgcarData(
        atoms=atoms,
        charge_density=density,
        voxel_volume=voxel_volume,
        source_path=str(path),
        spin_density=spin_density,
    )


def integrate_atomic_electron_populations(
    chgcar: ChgcarData | Path | str,
    *,
    atom_indices: Sequence[int] | None = None,
    chunk_size: int = 20_000,
) -> np.ndarray:
    data = read_chgcar(chgcar) if isinstance(chgcar, Path | str) else chgcar
    natoms = len(data.atoms)
    if natoms == 0:
        return np.array([], dtype=float)

    density = np.asarray(data.charge_density, dtype=float)
    grid_shape = density.shape
    flat_density = density.reshape(-1)
    scaled_positions = np.asarray(data.atoms.get_scaled_positions(wrap=False), dtype=float)
    cell = np.asarray(data.atoms.cell.array, dtype=float)
    electrons = np.zeros(natoms, dtype=float)

    for start in range(0, flat_density.size, chunk_size):
        stop = min(start + chunk_size, flat_density.size)
        flat_index = np.arange(start, stop)
        ix, iy, iz = np.unravel_index(flat_index, grid_shape)
        fractional = np.column_stack(
            (
                (ix + 0.5) / grid_shape[0],
                (iy + 0.5) / grid_shape[1],
                (iz + 0.5) / grid_shape[2],
            )
        )
        delta = fractional[:, None, :] - scaled_positions[None, :, :]
        delta -= np.rint(delta)
        cartesian = delta @ cell
        distances_sq = np.einsum("...i,...i->...", cartesian, cartesian)
        nearest = np.argmin(distances_sq, axis=1)
        weights = flat_density[start:stop] * data.voxel_volume
        electrons += np.bincount(nearest, weights=weights, minlength=natoms)

    if atom_indices is None:
        return electrons
    return electrons[np.asarray(atom_indices, dtype=int)]


def read_vasp_valence_electrons(
    source_path: Path | str,
    *,
    atoms: Atoms | None = None,
    potcar_name: str = "POTCAR",
    outcar_name: str = "OUTCAR",
) -> np.ndarray | None:
    path = Path(source_path)
    calculation_dir = path if path.is_dir() else path.parent
    atoms_obj = atoms

    potcar_path = calculation_dir / potcar_name
    if potcar_path.exists():
        species_values = _parse_species_valence_values(potcar_path)
        if species_values and atoms_obj is not None:
            return _expand_species_values(atoms_obj, species_values)

    outcar_path = calculation_dir / outcar_name
    if outcar_path.exists():
        species_values = _parse_species_valence_values(outcar_path)
        if species_values and atoms_obj is not None:
            return _expand_species_values(atoms_obj, species_values)

    return None


def compute_atomic_charges(
    chgcar: ChgcarData | Path | str | Sequence[float],
    *,
    reference_electrons: Sequence[float],
) -> np.ndarray:
    if isinstance(chgcar, np.ndarray | list | tuple):
        populations = np.asarray(chgcar, dtype=float)
    else:
        populations = integrate_atomic_electron_populations(chgcar)
    reference = np.asarray(reference_electrons, dtype=float)
    if reference.shape[0] != populations.shape[0]:
        raise ValueError("reference_electrons must match the number of atoms in the CHGCAR.")
    return reference - populations


def add_atomic_charge_descriptors(
    frame: pd.DataFrame,
    *,
    charge_source: str = "acf",
    acf_path_column: str = "acf_path",
    chgcar_path_column: str = "chgcar_path",
    calculation_path_column: str = "Path",
    structure_column: str = "struc",
    acf_filename: str = "ACF.dat",
    filename: str = "CHGCAR",
    compare_structure_coordinates: bool = True,
) -> pd.DataFrame:
    df = ensure_name_index(frame)
    if "integrated_electron_populations" not in df.columns:
        df["integrated_electron_populations"] = None
    if "atomic_charges" not in df.columns:
        df["atomic_charges"] = None
    if "total_integrated_electrons" not in df.columns:
        df["total_integrated_electrons"] = np.nan
    if "charge_source_used" not in df.columns:
        df["charge_source_used"] = None
    if "charge_coordinate_max_delta_A" not in df.columns:
        df["charge_coordinate_max_delta_A"] = np.nan
    if "charge_coordinate_match" not in df.columns:
        df["charge_coordinate_match"] = None

    for index, row in df.iterrows():
        atoms = _row_atoms(row, structure_column)
        populations, source_used, source_atoms, source_path, coordinate_delta = _resolve_atomic_populations(
            row,
            charge_source=charge_source,
            acf_path_column=acf_path_column,
            chgcar_path_column=chgcar_path_column,
            calculation_path_column=calculation_path_column,
            structure_column=structure_column,
            acf_filename=acf_filename,
            chgcar_filename=filename,
            compare_structure_coordinates=compare_structure_coordinates,
        )
        if populations is None:
            continue

        df.at[index, "integrated_electron_populations"] = populations.tolist()
        df.at[index, "total_integrated_electrons"] = float(populations.sum())
        df.at[index, "charge_source_used"] = source_used
        if coordinate_delta is not None:
            df.at[index, "charge_coordinate_max_delta_A"] = coordinate_delta
            df.at[index, "charge_coordinate_match"] = bool(coordinate_delta < 1e-3)

        if atoms is None:
            atoms = source_atoms
        if atoms is None:
            continue
        _write_per_element_statistics(
            df,
            index,
            atoms,
            populations,
            suffix="electron_population",
        )

        valence = read_vasp_valence_electrons(source_path, atoms=atoms) if source_path is not None else None
        if valence is None:
            continue
        charges = compute_atomic_charges(populations, reference_electrons=valence)
        df.at[index, "atomic_charges"] = charges.tolist()
        _write_per_element_statistics(df, index, atoms, charges, suffix="charge")

    return df


def atomic_magnetic_moments_from_atoms(atoms: Atoms | None) -> np.ndarray | None:
    if atoms is None or atoms.__class__.__name__ != "Atoms":
        return None
    arrays = getattr(atoms, "arrays", {})
    for key in ("magmoms", "initial_magmoms"):
        values = arrays.get(key)
        if values is not None:
            data = np.asarray(values, dtype=float).reshape(-1)
            if data.shape[0] == len(atoms):
                return data
    try:
        data = np.asarray(atoms.get_initial_magnetic_moments(), dtype=float).reshape(-1)
    except Exception:
        data = np.zeros(len(atoms), dtype=float)
    if data.shape[0] != len(atoms):
        data = np.zeros(len(atoms), dtype=float)
    return data


def add_atomic_magnetic_moment_descriptors(
    frame: pd.DataFrame,
    *,
    structure_column: str = "struc",
) -> pd.DataFrame:
    """Add per-atom and total magnetic-moment descriptors from structures.

    .. code-block:: python

        from onepiece import add_atomic_magnetic_moment_descriptors

        frame = add_atomic_magnetic_moment_descriptors(frame)
        frame[["atomic_magnetic_moments", "total_magnetic_moment"]]
    """
    df = ensure_name_index(frame)
    if "atomic_magnetic_moments" not in df.columns:
        df["atomic_magnetic_moments"] = None
    if "total_magnetic_moment" not in df.columns:
        df["total_magnetic_moment"] = np.nan

    for index, row in df.iterrows():
        atoms = _row_atoms(row, structure_column)
        moments = atomic_magnetic_moments_from_atoms(atoms)
        if moments is None:
            continue
        df.at[index, "atomic_magnetic_moments"] = moments.tolist()
        df.at[index, "total_magnetic_moment"] = float(moments.sum())
        _write_per_element_statistics(df, index, atoms, moments, suffix="magnetic_moment")

    return df


def add_adsorbate_charge_descriptors(
    frame: pd.DataFrame,
    *,
    charge_source: str = "acf",
    acf_path_column: str = "acf_path",
    chgcar_path_column: str = "chgcar_path",
    calculation_path_column: str = "Path",
    structure_column: str = "struc",
    acf_filename: str = "ACF.dat",
    filename: str = "CHGCAR",
) -> pd.DataFrame:
    df = assign_surface_references(ensure_name_index(frame))
    df = add_atomic_charge_descriptors(
        df,
        charge_source=charge_source,
        acf_path_column=acf_path_column,
        chgcar_path_column=chgcar_path_column,
        calculation_path_column=calculation_path_column,
        structure_column=structure_column,
        acf_filename=acf_filename,
        filename=filename,
    )
    df = add_atomic_magnetic_moment_descriptors(df, structure_column=structure_column)
    df["primary_atoms"] = df.apply(
        lambda row: primary_structure(row, structure_columns=(structure_column, "CONTCAR", "structure", "atoms")),
        axis=1,
    )
    surface_rows = df.loc[
        df["Name"].astype(str).eq(df["surface_ref_name"].astype(str)) & df["primary_atoms"].notna()
    ][["Name", "primary_atoms", "integrated_electron_populations", "atomic_charges", "atomic_magnetic_moments"]].drop_duplicates("Name")
    surface_atom_map = surface_rows.set_index("Name")["primary_atoms"].to_dict()
    surface_population_map = surface_rows.set_index("Name")["integrated_electron_populations"].to_dict()
    surface_charge_map = surface_rows.set_index("Name")["atomic_charges"].to_dict()

    gas_reference_map = _gas_phase_charge_references(df)
    gas_charge_reference_map = _gas_phase_atomic_array_references(df, "atomic_charges")
    gas_magnetic_moment_reference_map = _gas_phase_atomic_array_references(df, "atomic_magnetic_moments")
    surface_magnetic_moment_map = surface_rows.set_index("Name")["atomic_magnetic_moments"].to_dict()

    for column in (
        "adsorbate_atom_indices",
        "surface_atom_indices",
        "adsorbate_integrated_electrons",
        "surface_integrated_electrons",
        "surface_integrated_electrons_delta_vs_ref",
        "adsorbate_reference_integrated_electrons",
        "adsorbate_integrated_electrons_delta_vs_ref",
        "surface_reference_mode",
        "adsorbate_reference_mode",
    ):
        if column not in df.columns:
            df[column] = np.nan if "electrons" in column else None
    for column in (
        "adsorbate_net_charge_e",
        "surface_net_charge_e",
        "surface_net_charge_delta_vs_ref_e",
        "adsorbate_reference_charge_e",
        "adsorbate_charge_delta_vs_ref_e",
        "charge_balance_residual_e",
    ):
        if column not in df.columns:
            df[column] = np.nan
    for column in (
        "atomic_charge_delta_vs_surface_ref_e",
        "atomic_charge_delta_vs_gas_ref_e",
        "atomic_charge_delta_vs_valence_ref_e",
        "atomic_magnetic_moment_delta_vs_surface_ref",
        "atomic_magnetic_moment_delta_vs_gas_ref",
    ):
        if column not in df.columns:
            df[column] = None

    for index, row in df.iterrows():
        atoms = row.get("primary_atoms")
        surface_atoms = surface_atom_map.get(row.get("surface_ref_name"))
        populations = _as_array(row.get("integrated_electron_populations"))
        charges = _as_array(row.get("atomic_charges"))
        magnetic_moments = _as_array(row.get("atomic_magnetic_moments"))
        if atoms is None or surface_atoms is None or populations is None:
            continue
        natoms = len(atoms)

        surface_indices = matched_surface_atom_indices_from_structures(atoms, surface_atoms)
        if len(surface_indices) == len(atoms):
            continue
        adsorbate_indices = [i for i in range(len(atoms)) if i not in set(surface_indices)]

        df.at[index, "adsorbate_atom_indices"] = list(adsorbate_indices)
        df.at[index, "surface_atom_indices"] = list(surface_indices)

        adsorbate_integrated = float(populations[adsorbate_indices].sum())
        surface_integrated = float(populations[surface_indices].sum())
        df.at[index, "adsorbate_integrated_electrons"] = adsorbate_integrated
        df.at[index, "surface_integrated_electrons"] = surface_integrated

        surface_ref_populations = _as_array(surface_population_map.get(row.get("surface_ref_name")))
        if surface_ref_populations is not None:
            df.at[index, "surface_integrated_electrons_delta_vs_ref"] = (
                surface_integrated - float(surface_ref_populations.sum())
            )
            df.at[index, "surface_reference_mode"] = "surface_reference"

        if charges is not None:
            df.at[index, "atomic_charge_delta_vs_valence_ref_e"] = charges.tolist()
            adsorbate_net_charge = float(charges[adsorbate_indices].sum())
            surface_net_charge = float(charges[surface_indices].sum())
            df.at[index, "adsorbate_net_charge_e"] = adsorbate_net_charge
            df.at[index, "surface_net_charge_e"] = surface_net_charge

            surface_ref_charges = _as_array(surface_charge_map.get(row.get("surface_ref_name")))
            if surface_ref_charges is not None:
                df.at[index, "surface_net_charge_delta_vs_ref_e"] = (
                    surface_net_charge - float(surface_ref_charges.sum())
                )
                df.at[index, "atomic_charge_delta_vs_surface_ref_e"] = _aligned_reference_difference_vector(
                    charges,
                    surface_ref_charges,
                    natoms=natoms,
                    target_indices=surface_indices,
                )

        if magnetic_moments is not None:
            surface_ref_magnetic_moments = _as_array(surface_magnetic_moment_map.get(row.get("surface_ref_name")))
            if surface_ref_magnetic_moments is not None:
                df.at[index, "atomic_magnetic_moment_delta_vs_surface_ref"] = _aligned_reference_difference_vector(
                    magnetic_moments,
                    surface_ref_magnetic_moments,
                    natoms=natoms,
                    target_indices=surface_indices,
                )

        reference_mode = None
        reference_electrons = np.nan
        reference_charge = np.nan
        adsorbate_label = str(row.get("adsorbate", "")).strip()
        gas_reference = gas_reference_map.get(adsorbate_label)
        if gas_reference is not None:
            reference_mode = "gas_phase"
            reference_electrons = float(gas_reference.get("integrated_electrons", np.nan))
            reference_charge = float(gas_reference.get("net_charge", np.nan))
        else:
            charge_path = _resolve_existing_charge_path(
                row,
                charge_source=charge_source,
                acf_path_column=acf_path_column,
                explicit_column=chgcar_path_column,
                calculation_path_column=calculation_path_column,
                acf_filename=acf_filename,
                filename=filename,
            )
            if charge_path is not None and charge_path.exists():
                valence = read_vasp_valence_electrons(charge_path, atoms=atoms)
                if valence is not None:
                    reference_mode = "valence"
                    reference_electrons = float(np.asarray(valence)[adsorbate_indices].sum())
                    reference_charge = 0.0

        gas_charge_reference = _as_array(gas_charge_reference_map.get(adsorbate_label))
        if charges is not None and gas_charge_reference is not None:
            df.at[index, "atomic_charge_delta_vs_gas_ref_e"] = _aligned_reference_difference_vector(
                charges,
                gas_charge_reference,
                natoms=natoms,
                target_indices=adsorbate_indices,
            )

        gas_magnetic_reference = _as_array(gas_magnetic_moment_reference_map.get(adsorbate_label))
        if magnetic_moments is not None and gas_magnetic_reference is not None:
            df.at[index, "atomic_magnetic_moment_delta_vs_gas_ref"] = _aligned_reference_difference_vector(
                magnetic_moments,
                gas_magnetic_reference,
                natoms=natoms,
                target_indices=adsorbate_indices,
            )

        if reference_mode is not None:
            df.at[index, "adsorbate_reference_mode"] = reference_mode
            df.at[index, "adsorbate_reference_integrated_electrons"] = reference_electrons
            df.at[index, "adsorbate_integrated_electrons_delta_vs_ref"] = (
                adsorbate_integrated - reference_electrons
            )
            if pd.notna(df.at[index, "adsorbate_net_charge_e"]):
                df.at[index, "adsorbate_reference_charge_e"] = reference_charge
                df.at[index, "adsorbate_charge_delta_vs_ref_e"] = (
                    float(df.at[index, "adsorbate_net_charge_e"]) - reference_charge
                )

        if pd.notna(df.at[index, "adsorbate_net_charge_e"]) and pd.notna(
            df.at[index, "surface_net_charge_delta_vs_ref_e"]
        ):
            df.at[index, "charge_balance_residual_e"] = (
                float(df.at[index, "adsorbate_net_charge_e"])
                + float(df.at[index, "surface_net_charge_delta_vs_ref_e"])
            )

    return df


def add_atomic_reference_difference_descriptors(
    frame: pd.DataFrame,
    *,
    charge_source: str = "acf",
    acf_path_column: str = "acf_path",
    chgcar_path_column: str = "chgcar_path",
    calculation_path_column: str = "Path",
    structure_column: str = "struc",
    acf_filename: str = "ACF.dat",
    filename: str = "CHGCAR",
) -> pd.DataFrame:
    """Add per-atom charge differences versus per-element valence references.

    .. code-block:: python

        from onepiece import add_atomic_reference_difference_descriptors

        frame = add_atomic_reference_difference_descriptors(frame)
        frame["atomic_charge_delta_vs_valence_ref_e"]
    """
    return add_adsorbate_charge_descriptors(
        frame,
        charge_source=charge_source,
        acf_path_column=acf_path_column,
        chgcar_path_column=chgcar_path_column,
        calculation_path_column=calculation_path_column,
        structure_column=structure_column,
        acf_filename=acf_filename,
        filename=filename,
    )


def read_doscar(path: Path | str, *, shift_to_fermi: bool = True) -> DoscarData:
    path = Path(path)
    efermi = _read_doscar_fermi_level(path)
    raw = VaspDos(str(path), efermi=0.0)

    energies = np.array(raw.energy, copy=True)
    total_dos = np.asarray(raw.dos, dtype=float)
    total_dos = total_dos[np.newaxis, :] if total_dos.ndim == 1 else total_dos
    integrated = np.asarray(raw.integrated_dos, dtype=float)
    integrated = integrated[np.newaxis, :] if integrated.ndim == 1 else integrated

    site_dos = np.asarray(getattr(raw, "_site_dos", np.empty((0, 0, 0))), dtype=float)
    if site_dos.ndim != 3:
        site_dos = np.empty((0, 0, 0), dtype=float)

    if shift_to_fermi:
        energies = energies - efermi
        if site_dos.size:
            site_dos[:, 0, :] = site_dos[:, 0, :] - efermi

    orbital_columns = PDOS_orbital_names_and_DOSCAR_column.get(site_dos.shape[1], {}).copy()
    return DoscarData(
        energies=energies,
        total_dos=total_dos,
        integrated_total_dos=integrated,
        site_dos=site_dos,
        efermi=efermi,
        source_path=str(path),
        orbital_columns=orbital_columns,
    )


def integrate_total_dos(
    doscar: DoscarData | Path | str,
    *,
    energy_window: tuple[float, float] = (-np.inf, 0.0),
    spin: str = "sum",
) -> float:
    data = read_doscar(doscar) if isinstance(doscar, Path | str) else doscar
    values = _select_total_dos_channel(data.total_dos, spin)
    return _integrate_signal(data.energies, values, energy_window)


def integrate_projected_dos(
    doscar: DoscarData | Path | str,
    *,
    atom_indices: Sequence[int] | None = None,
    orbitals: str | Sequence[str] | None = None,
    energy_window: tuple[float, float] = (-np.inf, 0.0),
    spin: str = "sum",
) -> float:
    data = read_doscar(doscar) if isinstance(doscar, Path | str) else doscar
    if data.site_dos.size == 0:
        raise ValueError("DOSCAR does not contain site-projected DOS blocks.")

    selected_atoms = (
        np.arange(data.natoms, dtype=int)
        if atom_indices is None
        else np.asarray(atom_indices, dtype=int)
    )
    orbital_names = _resolve_orbital_names(data, orbitals=orbitals, spin=spin)
    signal = np.zeros_like(data.energies, dtype=float)
    for atom_index in selected_atoms:
        for orbital in orbital_names:
            signal += data.site_dos[atom_index, data.orbital_columns[orbital], :]
    return _integrate_signal(data.energies, signal, energy_window)


def add_projected_dos_descriptors(
    frame: pd.DataFrame,
    integrations: Sequence[dict[str, object]],
    *,
    doscar_path_column: str = "doscar_path",
    calculation_path_column: str = "Path",
    structure_column: str = "struc",
    filename: str = "DOSCAR",
) -> pd.DataFrame:
    df = ensure_name_index(frame)

    for spec in integrations:
        column = str(spec["column"])
        if column not in df.columns:
            df[column] = np.nan

    for index, row in df.iterrows():
        doscar_path = _resolve_row_file_path(
            row,
            explicit_column=doscar_path_column,
            calculation_path_column=calculation_path_column,
            filename=filename,
        )
        if doscar_path is None or not doscar_path.exists():
            continue

        doscar = read_doscar(doscar_path)
        atoms = _row_atoms(row, structure_column)

        for spec in integrations:
            atom_indices = spec.get("atom_indices")
            if atom_indices is None and spec.get("elements") is not None:
                if atoms is None:
                    raise ValueError(
                        f"Integration '{spec['column']}' selects elements but no structure is available."
                    )
                atom_indices = _atom_indices_for_elements(atoms, spec["elements"])

            energy_window = tuple(spec.get("energy_window", (-np.inf, 0.0)))
            df.at[index, str(spec["column"])] = float(
                integrate_projected_dos(
                    doscar,
                    atom_indices=atom_indices,
                    orbitals=spec.get("orbitals"),
                    energy_window=(float(energy_window[0]), float(energy_window[1])),
                    spin=str(spec.get("spin", "sum")),
                )
            )

    return df


def atomic_charge_long_table(
    frame: pd.DataFrame,
    *,
    structure_column: str = "struc",
) -> pd.DataFrame:
    """Expand atomic populations/charges into a MultiIndex table keyed by calculation name."""
    df = ensure_name_index(frame)
    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        name = row_name(row)
        atoms = _row_atoms(row, structure_column)
        populations = _as_array(row.get("integrated_electron_populations"))
        charges = _as_array(row.get("atomic_charges"))
        magnetic_moments = _as_array(row.get("atomic_magnetic_moments"))
        if atoms is None or populations is None:
            continue
        positions = np.asarray(atoms.get_positions(), dtype=float)
        symbols = atoms.get_chemical_symbols()
        for atom_index, symbol in enumerate(symbols):
            rows.append(
                {
                    "calculation_name": name,
                    "atom_index": int(atom_index),
                    "element": symbol,
                    "x": float(positions[atom_index, 0]),
                    "y": float(positions[atom_index, 1]),
                    "z": float(positions[atom_index, 2]),
                    "integrated_electron_population": float(populations[atom_index]),
                    "atomic_charge": float(charges[atom_index]) if charges is not None and atom_index < len(charges) else np.nan,
                    "atomic_magnetic_moment": float(magnetic_moments[atom_index]) if magnetic_moments is not None and atom_index < len(magnetic_moments) else np.nan,
                }
            )
    table = pd.DataFrame(rows)
    if table.empty:
        return pd.DataFrame(
            columns=[
                "calculation_name",
                "atom_index",
                "element",
                "x",
                "y",
                "z",
                "integrated_electron_population",
                "atomic_charge",
                "atomic_magnetic_moment",
            ]
        ).set_index(["calculation_name", "atom_index"], drop=False)
    return table.set_index(["calculation_name", "atom_index"], drop=False)


def doscar_projected_long_table(
    doscar: DoscarData | Path | str,
    *,
    calculation_name: str,
) -> pd.DataFrame:
    """Return site-projected DOS as a long MultiIndex table with calculation name first."""
    data = read_doscar(doscar) if isinstance(doscar, Path | str) else doscar
    if data.site_dos.size == 0 or not data.orbital_columns:
        return pd.DataFrame(
            columns=["calculation_name", "atom_index", "orbital", "energy_index", "energy_eV", "pdos"]
        ).set_index(["calculation_name", "atom_index", "orbital", "energy_index"], drop=False)
    rows: list[dict[str, object]] = []
    for atom_index in range(data.natoms):
        for orbital, orbital_column in data.orbital_columns.items():
            signal = np.asarray(data.site_dos[atom_index, orbital_column, :], dtype=float)
            for energy_index, (energy, value) in enumerate(zip(data.energies, signal, strict=False)):
                rows.append(
                    {
                        "calculation_name": calculation_name,
                        "atom_index": int(atom_index),
                        "orbital": orbital,
                        "energy_index": int(energy_index),
                        "energy_eV": float(energy),
                        "pdos": float(value),
                    }
                )
    return pd.DataFrame(rows).set_index(["calculation_name", "atom_index", "orbital", "energy_index"], drop=False)


def matched_surface_atom_indices_from_structures(total_atoms: object, surface_atoms: object) -> list[int]:
    if total_atoms.__class__.__name__ != "Atoms" or surface_atoms.__class__.__name__ != "Atoms":
        return []
    total_positions = np.asarray(total_atoms.get_positions(), dtype=float)
    total_symbols = list(total_atoms.get_chemical_symbols())
    surface_positions = np.asarray(surface_atoms.get_positions(), dtype=float)
    surface_symbols = list(surface_atoms.get_chemical_symbols())
    unmatched_total = set(range(len(total_symbols)))
    matched: list[int] = []
    for surface_symbol, surface_position in zip(surface_symbols, surface_positions, strict=False):
        candidates = [idx for idx in unmatched_total if total_symbols[idx] == surface_symbol]
        if not candidates:
            continue
        distances = [
            float(np.linalg.norm(total_positions[idx] - surface_position))
            for idx in candidates
        ]
        best = candidates[int(np.argmin(distances))]
        matched.append(best)
        unmatched_total.remove(best)
    return sorted(matched)


def adsorbate_atom_indices_from_structures(total_atoms: object, surface_atoms: object) -> list[int]:
    if total_atoms.__class__.__name__ != "Atoms" or surface_atoms.__class__.__name__ != "Atoms":
        return []
    matched = set(matched_surface_atom_indices_from_structures(total_atoms, surface_atoms))
    return [idx for idx in range(len(total_atoms)) if idx not in matched]


def _read_doscar_fermi_level(path: Path) -> float:
    with path.open() as handle:
        handle.readline()
        for _ in range(4):
            handle.readline()
        header = handle.readline().split()
    if len(header) < 4:
        raise ValueError(f"Could not parse DOSCAR header from {path}.")
    return float(header[3])


def _select_total_dos_channel(total_dos: np.ndarray, spin: str) -> np.ndarray:
    if total_dos.ndim == 1 or total_dos.shape[0] == 1:
        return total_dos.reshape(-1)
    if spin in {"sum", "total"}:
        return total_dos.sum(axis=0)
    if spin == "up":
        return total_dos[0]
    if spin == "down":
        return total_dos[1]
    raise ValueError(f"Unsupported spin selector: {spin}")


def _resolve_orbital_names(
    doscar: DoscarData,
    *,
    orbitals: str | Sequence[str] | None,
    spin: str,
) -> list[str]:
    if not doscar.orbital_columns:
        raise ValueError("No projected-orbital map is available for this DOSCAR.")

    requests = [orbitals] if isinstance(orbitals, str) else list(orbitals or doscar.orbital_columns)
    resolved: list[str] = []
    for request in requests:
        request_name = str(request).lower()
        if request_name in doscar.orbital_columns:
            resolved.append(request_name)
            continue

        if spin == "up":
            candidates = [f"{request_name}-up", f"{request_name}+"]
        elif spin == "down":
            candidates = [f"{request_name}-down", f"{request_name}-"]
        else:
            candidates = [
                request_name,
                f"{request_name}-up",
                f"{request_name}+",
                f"{request_name}-down",
                f"{request_name}-",
            ]
        matched = [candidate for candidate in candidates if candidate in doscar.orbital_columns]
        if not matched:
            raise ValueError(f"Unsupported orbital selector '{request_name}' for this DOSCAR.")
        resolved.extend(matched)
    return list(dict.fromkeys(resolved))


def _integrate_signal(
    energies: np.ndarray,
    signal: np.ndarray,
    energy_window: tuple[float, float],
) -> float:
    emin, emax = energy_window
    mask = (energies >= float(emin)) & (energies <= float(emax))
    if not mask.any():
        return 0.0
    return float(trapezoid(signal[mask], energies[mask]))


def _resolve_row_file_path(
    row: pd.Series,
    *,
    explicit_column: str,
    calculation_path_column: str,
    filename: str,
) -> Path | None:
    explicit_value = row.get(explicit_column)
    if explicit_value is not None and not pd.isna(explicit_value):
        return _resolve_vasp_file(explicit_value, filename=filename)

    calculation_value = row.get(calculation_path_column)
    if calculation_value is None or pd.isna(calculation_value):
        return None
    return _resolve_vasp_file(calculation_value, filename=filename)


def _resolve_existing_charge_path(
    row: pd.Series,
    *,
    charge_source: str,
    acf_path_column: str,
    explicit_column: str,
    calculation_path_column: str,
    acf_filename: str,
    filename: str,
) -> Path | None:
    if charge_source.lower() == "chgcar":
        path = _resolve_row_file_path(
            row,
            explicit_column=explicit_column,
            calculation_path_column=calculation_path_column,
            filename=filename,
        )
        return path if path is not None and path.exists() else None

    acf_path = _resolve_row_file_path(
        row,
        explicit_column=acf_path_column,
        calculation_path_column=calculation_path_column,
        filename=acf_filename,
    )
    if acf_path is not None and acf_path.exists():
        return acf_path
    chgcar_path = _resolve_row_file_path(
        row,
        explicit_column=explicit_column,
        calculation_path_column=calculation_path_column,
        filename=filename,
    )
    return chgcar_path if chgcar_path is not None and chgcar_path.exists() else None


def _resolve_vasp_file(pathlike: Path | str, *, filename: str) -> Path:
    path = Path(pathlike)
    if path.is_dir():
        return path / filename
    if path.name.upper() == filename.upper():
        return path
    return path.parent / filename


def _resolve_atomic_populations(
    row: pd.Series,
    *,
    charge_source: str,
    acf_path_column: str,
    chgcar_path_column: str,
    calculation_path_column: str,
    structure_column: str,
    acf_filename: str,
    chgcar_filename: str,
    compare_structure_coordinates: bool,
) -> tuple[np.ndarray | None, str | None, Atoms | None, Path | None, float | None]:
    atoms = _row_atoms(row, structure_column)

    if charge_source.lower() != "chgcar":
        acf_path = _resolve_row_file_path(
            row,
            explicit_column=acf_path_column,
            calculation_path_column=calculation_path_column,
            filename=acf_filename,
        )
        if acf_path is not None and acf_path.exists():
            table = read_acf_dat(acf_path)
            if not table.empty:
                populations = table["CHARGE"].to_numpy(dtype=float)
                coordinate_delta = None
                if compare_structure_coordinates and atoms is not None:
                    coordinate_delta = _compare_acf_coordinates(table, atoms)
                return populations, "acf", atoms, acf_path, coordinate_delta

    chgcar_path = _resolve_row_file_path(
        row,
        explicit_column=chgcar_path_column,
        calculation_path_column=calculation_path_column,
        filename=chgcar_filename,
    )
    if chgcar_path is None or not chgcar_path.exists():
        return None, None, atoms, None, None
    chgcar = read_chgcar(chgcar_path)
    populations = integrate_atomic_electron_populations(chgcar)
    active_atoms = atoms or chgcar.atoms
    return populations, "chgcar", active_atoms, chgcar_path, None


def _compare_acf_coordinates(table: pd.DataFrame, atoms: Atoms) -> float:
    if len(table) != len(atoms):
        return float("inf")
    acf_positions = table[["X", "Y", "Z"]].to_numpy(dtype=float)
    atom_positions = np.asarray(atoms.get_positions(), dtype=float)
    deltas = np.linalg.norm(acf_positions - atom_positions, axis=1)
    return float(np.max(deltas)) if len(deltas) else 0.0


def _gas_phase_charge_references(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    references: dict[str, dict[str, float]] = {}
    for _, row in frame.iterrows():
        if not is_gas_phase_row(row):
            continue
        label = str(row.get("adsorbate", "")).strip()
        if not label:
            continue
        populations = _as_array(row.get("integrated_electron_populations"))
        if populations is None:
            continue
        charges = _as_array(row.get("atomic_charges"))
        references[label] = {
            "integrated_electrons": float(populations.sum()),
            "net_charge": float(charges.sum()) if charges is not None else 0.0,
        }
    return references


def _gas_phase_atomic_array_references(frame: pd.DataFrame, value_column: str) -> dict[str, np.ndarray]:
    references: dict[str, np.ndarray] = {}
    for _, row in frame.iterrows():
        if not is_gas_phase_row(row):
            continue
        label = str(row.get("adsorbate", "")).strip()
        if not label:
            continue
        values = _as_array(row.get(value_column))
        if values is None:
            continue
        references[label] = values
    return references


def _aligned_reference_difference_vector(
    values: np.ndarray | Sequence[float],
    reference: np.ndarray | Sequence[float],
    *,
    natoms: int,
    target_indices: Sequence[int] | None = None,
) -> list[float]:
    value_array = np.asarray(values, dtype=float)
    reference_array = np.asarray(reference, dtype=float)
    result = np.full(int(natoms), np.nan, dtype=float)
    if target_indices is None:
        count = min(value_array.shape[0], reference_array.shape[0], result.shape[0])
        if count > 0:
            result[:count] = value_array[:count] - reference_array[:count]
        return result.tolist()
    indices = np.asarray(list(target_indices), dtype=int)
    if indices.size == 0:
        return result.tolist()
    count = min(indices.shape[0], reference_array.shape[0])
    if count <= 0:
        return result.tolist()
    active = indices[:count]
    valid = active[(active >= 0) & (active < value_array.shape[0]) & (active < result.shape[0])]
    count = min(valid.shape[0], reference_array.shape[0])
    if count > 0:
        result[valid[:count]] = value_array[valid[:count]] - reference_array[:count]
    return result.tolist()


def _as_array(value: object) -> np.ndarray | None:
    if isinstance(value, np.ndarray):
        return value.astype(float, copy=False)
    if isinstance(value, list | tuple):
        return np.asarray(value, dtype=float)
    if value is None or pd.isna(value):
        return None
    return None


def _row_atoms(row: pd.Series, structure_column: str) -> Atoms | None:
    value = row.get(structure_column)
    return value if value.__class__.__name__ == "Atoms" else None


def _write_per_element_statistics(
    dataframe: pd.DataFrame,
    index: Any,
    atoms: Atoms,
    values: np.ndarray,
    *,
    suffix: str,
) -> None:
    symbols = np.asarray(atoms.get_chemical_symbols())
    for symbol in sorted(set(symbols)):
        element_values = values[symbols == symbol]
        dataframe.at[index, f"average_{symbol}_{suffix}"] = float(np.mean(element_values))
        dataframe.at[index, f"min_{symbol}_{suffix}"] = float(np.min(element_values))
        dataframe.at[index, f"max_{symbol}_{suffix}"] = float(np.max(element_values))


def _parse_species_valence_values(path: Path) -> list[float]:
    values: list[float] = []
    pattern = re.compile(r"ZVAL\s*=\s*([-+]?\d+(?:\.\d+)?)")
    with path.open(errors="ignore") as handle:
        for line in handle:
            match = pattern.search(line)
            if match:
                values.append(float(match.group(1)))
    return values


def _expand_species_values(atoms: Atoms, species_values: Sequence[float]) -> np.ndarray:
    species_order = list(dict.fromkeys(atoms.get_chemical_symbols()))
    if len(species_values) == len(atoms):
        return np.asarray(species_values, dtype=float)
    if len(species_values) != len(species_order):
        raise ValueError("Number of species valence values does not match the structure.")
    mapping = {symbol: float(value) for symbol, value in zip(species_order, species_values, strict=False)}
    return np.asarray([mapping[symbol] for symbol in atoms.get_chemical_symbols()], dtype=float)


def _atom_indices_for_elements(atoms: Atoms, elements: Iterable[str]) -> list[int]:
    wanted = {str(element) for element in elements}
    return [index for index, symbol in enumerate(atoms.get_chemical_symbols()) if symbol in wanted]
