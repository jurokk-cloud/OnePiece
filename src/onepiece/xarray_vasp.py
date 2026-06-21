from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import xarray as xr

from onepiece._compat import trapezoid
from onepiece.vasp import ChgcarData, DoscarData, read_chgcar, read_doscar

AxisName = Literal["x", "y", "z"]


def chgcar_to_xarray(chgcar: ChgcarData | Path | str) -> xr.Dataset:
    data = read_chgcar(chgcar) if isinstance(chgcar, Path | str) else chgcar
    dims = ("x", "y", "z")
    shape = data.grid_shape
    fractional_coords = {
        axis: np.linspace(0.5 / count, 1.0 - 0.5 / count, count, dtype=float)
        for axis, count in zip(dims, shape, strict=False)
    }

    dataset = xr.Dataset(
        data_vars={
            "charge_density": (dims, np.asarray(data.charge_density, dtype=float)),
        },
        coords=fractional_coords,
        attrs={
            "source_path": data.source_path,
            "voxel_volume": float(data.voxel_volume),
            "grid_shape": tuple(int(value) for value in shape),
            "cell_matrix_A": np.asarray(data.atoms.cell.array, dtype=float).tolist(),
            "chemical_symbols": list(data.atoms.get_chemical_symbols()),
            "atom_positions_A": np.asarray(data.atoms.get_positions(), dtype=float).tolist(),
            "atom_positions_frac": np.asarray(data.atoms.get_scaled_positions(wrap=False), dtype=float).tolist(),
        },
    )
    if data.spin_density is not None:
        dataset["spin_density"] = xr.DataArray(np.asarray(data.spin_density, dtype=float), dims=dims)
    return dataset


def chgcar_planar_average(
    chgcar: xr.Dataset | ChgcarData | Path | str,
    *,
    axis: AxisName = "z",
    data_var: str = "charge_density",
    statistic: Literal["mean", "sum"] = "mean",
) -> xr.DataArray:
    dataset = _ensure_chgcar_dataset(chgcar)
    _validate_chgcar_var(dataset, data_var)
    reduce_dims = tuple(dim for dim in ("x", "y", "z") if dim != axis)
    array = dataset[data_var]
    if statistic == "mean":
        result = array.mean(dim=reduce_dims)
    elif statistic == "sum":
        result = array.sum(dim=reduce_dims)
    else:
        raise ValueError(f"Unsupported planar statistic: {statistic}")
    result.name = f"{data_var}_{statistic}_{axis}"
    result.attrs["profile_axis"] = axis
    result.attrs["statistic"] = statistic
    return result


def chgcar_plane_integrated_electrons(
    chgcar: xr.Dataset | ChgcarData | Path | str,
    *,
    axis: AxisName = "z",
    data_var: str = "charge_density",
) -> xr.DataArray:
    dataset = _ensure_chgcar_dataset(chgcar)
    _validate_chgcar_var(dataset, data_var)
    reduce_dims = tuple(dim for dim in ("x", "y", "z") if dim != axis)
    plane = dataset[data_var].sum(dim=reduce_dims) * float(dataset.attrs["voxel_volume"])
    plane.name = f"{data_var}_electrons_per_{axis}_slice"
    plane.attrs["profile_axis"] = axis
    plane.attrs["quantity"] = "electrons_per_slice"
    return plane


def chgcar_cumulative_axis_profile(
    chgcar: xr.Dataset | ChgcarData | Path | str,
    *,
    axis: AxisName = "z",
    data_var: str = "charge_density",
) -> xr.DataArray:
    plane = chgcar_plane_integrated_electrons(chgcar, axis=axis, data_var=data_var)
    result = plane.cumsum(dim=axis)
    result.name = f"{data_var}_cumulative_electrons_along_{axis}"
    result.attrs["quantity"] = "cumulative_electrons"
    return result


def chgcar_line_profile(
    chgcar: xr.Dataset | ChgcarData | Path | str,
    *,
    start_frac: tuple[float, float, float],
    stop_frac: tuple[float, float, float],
    n_points: int = 200,
    data_var: str = "charge_density",
    method: str = "linear",
) -> xr.DataArray:
    dataset = _ensure_chgcar_dataset(chgcar)
    _validate_chgcar_var(dataset, data_var)
    if n_points < 2:
        raise ValueError("n_points must be at least 2.")

    sample = np.linspace(0.0, 1.0, n_points, dtype=float)
    start = np.asarray(start_frac, dtype=float)
    stop = np.asarray(stop_frac, dtype=float)
    coordinates = start[None, :] + sample[:, None] * (stop - start)[None, :]
    interpolated = dataset[data_var].interp(
        x=xr.DataArray(coordinates[:, 0], dims=("sample",)),
        y=xr.DataArray(coordinates[:, 1], dims=("sample",)),
        z=xr.DataArray(coordinates[:, 2], dims=("sample",)),
        method=method,
    )
    cell = np.asarray(dataset.attrs["cell_matrix_A"], dtype=float)
    path_vector_A = (stop - start) @ cell
    distance_A = np.linalg.norm(path_vector_A) * sample
    interpolated = interpolated.assign_coords(
        sample=("sample", sample),
        distance_A=("sample", distance_A),
        x_frac=("sample", coordinates[:, 0]),
        y_frac=("sample", coordinates[:, 1]),
        z_frac=("sample", coordinates[:, 2]),
    )
    interpolated.name = f"{data_var}_line_profile"
    interpolated.attrs["start_frac"] = tuple(float(value) for value in start)
    interpolated.attrs["stop_frac"] = tuple(float(value) for value in stop)
    interpolated.attrs["interpolation"] = method
    return interpolated


def doscar_to_xarray(doscar: DoscarData | Path | str) -> xr.Dataset:
    data = read_doscar(doscar) if isinstance(doscar, Path | str) else doscar
    spin_labels = ["up", "down"] if data.spin_polarized else ["total"]
    dataset = xr.Dataset(
        data_vars={
            "total_dos": (("spin", "energy"), np.asarray(data.total_dos, dtype=float)),
            "integrated_total_dos": (("spin", "energy"), np.asarray(data.integrated_total_dos, dtype=float)),
        },
        coords={
            "spin": spin_labels,
            "energy": np.asarray(data.energies, dtype=float),
        },
        attrs={
            "source_path": data.source_path,
            "efermi": float(data.efermi),
            "natoms": int(data.natoms),
            "spin_polarized": bool(data.spin_polarized),
        },
    )

    orbital_names = [name for name, _ in sorted(data.orbital_columns.items(), key=lambda item: item[1])]
    if data.site_dos.size and orbital_names:
        orbital_indices = [data.orbital_columns[name] for name in orbital_names]
        site_projected = np.asarray(data.site_dos[:, orbital_indices, :], dtype=float)
        dataset["site_projected_dos"] = xr.DataArray(
            site_projected,
            dims=("atom", "orbital", "energy"),
            coords={
                "atom": np.arange(data.natoms, dtype=int),
                "orbital": orbital_names,
                "energy": np.asarray(data.energies, dtype=float),
            },
        )
    return dataset


def doscar_select_energy_window(
    doscar: xr.Dataset | DoscarData | Path | str,
    *,
    energy_window: tuple[float, float],
) -> xr.Dataset:
    dataset = _ensure_doscar_dataset(doscar)
    emin, emax = float(energy_window[0]), float(energy_window[1])
    return dataset.sel(energy=slice(emin, emax))


def doscar_integrated_pdos(
    doscar: xr.Dataset | DoscarData | Path | str,
    *,
    atom_indices: list[int] | tuple[int, ...] | np.ndarray | None = None,
    orbitals: list[str] | tuple[str, ...] | str | None = None,
    energy_window: tuple[float, float] = (-np.inf, 0.0),
) -> xr.DataArray:
    dataset = _ensure_doscar_dataset(doscar)
    if "site_projected_dos" not in dataset:
        raise ValueError("DOSCAR dataset does not contain site_projected_dos.")
    signal = _select_site_projected_signal(
        dataset,
        atom_indices=atom_indices,
        orbitals=orbitals,
        energy_window=energy_window,
    )
    integrated = float(trapezoid(signal.to_numpy(), signal["energy"].to_numpy()))
    return xr.DataArray(
        integrated,
        attrs={
            "energy_window": tuple(float(value) for value in energy_window),
            "atom_indices": None if atom_indices is None else [int(value) for value in atom_indices],
            "orbitals": None if orbitals is None else _normalize_orbital_request(orbitals),
        },
        name="integrated_projected_dos",
    )


def doscar_orbital_band_center(
    doscar: xr.Dataset | DoscarData | Path | str,
    *,
    atom_indices: list[int] | tuple[int, ...] | np.ndarray | None = None,
    orbitals: list[str] | tuple[str, ...] | str | None = None,
    energy_window: tuple[float, float] = (-np.inf, 0.0),
) -> xr.DataArray:
    dataset = _ensure_doscar_dataset(doscar)
    if "site_projected_dos" not in dataset:
        raise ValueError("DOSCAR dataset does not contain site_projected_dos.")
    signal = _select_site_projected_signal(
        dataset,
        atom_indices=atom_indices,
        orbitals=orbitals,
        energy_window=energy_window,
    )
    energies = np.asarray(signal["energy"].to_numpy(), dtype=float)
    values = np.asarray(signal.to_numpy(), dtype=float)
    denominator = float(trapezoid(values, energies))
    if np.isclose(denominator, 0.0):
        band_center = np.nan
    else:
        band_center = float(trapezoid(energies * values, energies) / denominator)
    return xr.DataArray(
        band_center,
        attrs={
            "energy_window": tuple(float(value) for value in energy_window),
            "atom_indices": None if atom_indices is None else [int(value) for value in atom_indices],
            "orbitals": None if orbitals is None else _normalize_orbital_request(orbitals),
        },
        name="orbital_band_center",
    )


def _ensure_chgcar_dataset(chgcar: xr.Dataset | ChgcarData | Path | str) -> xr.Dataset:
    return chgcar if isinstance(chgcar, xr.Dataset) else chgcar_to_xarray(chgcar)


def _ensure_doscar_dataset(doscar: xr.Dataset | DoscarData | Path | str) -> xr.Dataset:
    return doscar if isinstance(doscar, xr.Dataset) else doscar_to_xarray(doscar)


def _validate_chgcar_var(dataset: xr.Dataset, data_var: str) -> None:
    if data_var not in dataset:
        raise KeyError(f"{data_var!r} not present in CHGCAR xarray dataset.")


def _select_site_projected_signal(
    dataset: xr.Dataset,
    *,
    atom_indices: list[int] | tuple[int, ...] | np.ndarray | None,
    orbitals: list[str] | tuple[str, ...] | str | None,
    energy_window: tuple[float, float],
) -> xr.DataArray:
    selected = doscar_select_energy_window(dataset, energy_window=energy_window)["site_projected_dos"]
    if atom_indices is not None:
        selected = selected.sel(atom=np.asarray(atom_indices, dtype=int))
    if orbitals is not None:
        selected = selected.sel(orbital=_normalize_orbital_request(orbitals))
    return selected.sum(dim=tuple(dim for dim in ("atom", "orbital") if dim in selected.dims))


def _normalize_orbital_request(orbitals: list[str] | tuple[str, ...] | str) -> list[str]:
    if isinstance(orbitals, str):
        return [orbitals]
    return [str(value) for value in orbitals]
