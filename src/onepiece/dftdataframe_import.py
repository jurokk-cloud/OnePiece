from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path
from pickle import UnpicklingError  # nosec B403
from time import ctime
from typing import Any

import numpy as np
import pandas as pd
from ase import Atoms
from ase.io import read

from onepiece._compat import trapezoid
from onepiece.adsorption import add_element_count_columns
from onepiece.frame_utils import ensure_name_index
from onepiece.storage import cache_key_for_paths, read_cache_payload, write_cache_payload
from onepiece.vasp import read_chgcar, read_doscar

DEFAULT_THERMO_FILENAME = "out.txt"
DEFAULT_STRUCTURE_FALLBACKS = ("final.traj", "CONTCAR", "OUTCAR", "POSCAR")
FREQUENCY_OUTCAR_PATTERN = re.compile(
    r"f(?P<imaginary>/i)?\s*=\s*.*?(?P<cm1>[+-]?\d+(?:\.\d+)?)\s*cm-1.*?(?P<mev>[+-]?\d+(?:\.\d+)?)\s*meV",
    flags=re.IGNORECASE,
)
KNOWN_FILE_COLUMNS = {
    "final.traj": "final_traj_path",
    "CONTCAR": "contcar_path",
    "OUTCAR": "outcar_path",
    "POSCAR": "poscar_path",
    "INCAR": "incar_path",
    "KPOINTS": "kpoints_path",
    "POTCAR": "potcar_path",
    "CHGCAR": "chgcar_path",
    "DOSCAR": "doscar_path",
    "ACF.dat": "acf_path",
    "vasprun.xml": "vasprun_path",
}


def crawl_root_to_frame(
    root: str | Path,
    *,
    calc_file: str = "final.traj",
    query: str | None = None,
    entropies_file: str | Path | None = None,
    thermo_filename: str | None = DEFAULT_THERMO_FILENAME,
    read_electronic_files: bool = True,
    electronic_workers: int | None = None,
    verbose: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
    cache_dir: str | Path | None = None,
) -> pd.DataFrame:
    """Build a OnePiece dataframe from a calculation root.

    Parameters
    ----------
    root
        Root directory that contains many calculation subfolders.
    calc_file
        Preferred structure file to read first in each folder. If it is not
        present, OnePiece falls back to ``final.traj``, ``CONTCAR``,
        ``OUTCAR``, and ``POSCAR`` in that order.
    query
        Optional ``pandas.DataFrame.query(...)`` expression applied after the
        crawl and after derived columns have been added.
    entropies_file
        Backward-compatible alias for ``thermo_filename``. If given, only the
        basename is used and OnePiece looks for that file inside every
        calculation folder.
    thermo_filename
        Per-folder thermochemistry filename, usually ``"out.txt"``.
        Use ``None`` to disable thermo parsing entirely.
    read_electronic_files
        If ``True``, run the second-stage electronic enrichment and read
        ``CHGCAR`` and ``DOSCAR`` summaries. If ``False``, only the fast base
        crawl is performed.
    electronic_workers
        Number of worker threads for the electronic enrichment stage. ``None``
        lets OnePiece choose a sensible default based on task count and CPU
        availability.
    verbose
        If ``True``, print crawl/read failures for unreadable structure or
        electronic files.
    progress_callback
        Optional callback with signature ``(completed: int, total: int,
        current_path: str)``. It is used during the base crawl.

    Returns
    -------
    pandas.DataFrame
        A dataframe with structural metadata, element counts, optional
        thermochemistry, and optional electronic summaries.

    Examples
    --------
    .. code-block:: python

        from onepiece import crawl_root_to_frame

        frame = crawl_root_to_frame(
            "path/to/calculations",
            calc_file="final.traj",
            thermo_filename="out.txt",
            read_electronic_files=True,
            electronic_workers=8,
            query="Cu > 0 and E < -10",
        )
    """
    root_path = Path(root).expanduser()
    active_thermo_filename = _active_thermo_filename(
        entropies_file=entropies_file,
        thermo_filename=thermo_filename,
    )
    calc_dirs = crawl_calculation_directories(
        root_path,
        calc_file=calc_file,
        thermo_filename=active_thermo_filename,
    )
    frame = create_calculation_frame(
        root=root_path,
        paths=calc_dirs,
        calc_file=calc_file,
        thermo_filename=active_thermo_filename,
        read_electronic_files=False,
        verbose=verbose,
        progress_callback=progress_callback,
        cache_dir=cache_dir,
    )
    if read_electronic_files:
        frame = enrich_electronic_summaries(
            frame,
            workers=electronic_workers,
            verbose=verbose,
            cache_dir=cache_dir,
        )
    frame = add_element_count_columns(frame, structure_column="struc")
    if active_thermo_filename:
        frame = merge_entropies_file(frame, active_thermo_filename)
    if query:
        frame = frame.query(query)
    return ensure_name_index(frame)


def crawl_root_to_hdf(
    root: str | Path,
    output_hdf: str | Path,
    *,
    key: str = "df",
    calc_file: str = "final.traj",
    query: str | None = None,
    entropies_file: str | Path | None = None,
    thermo_filename: str | None = DEFAULT_THERMO_FILENAME,
    read_electronic_files: bool = True,
    electronic_workers: int | None = None,
    verbose: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
    cache_dir: str | Path | None = None,
) -> Path:
    """Crawl a calculation root and persist the resulting dataframe as HDF.

    Parameters
    ----------
    root
        Root directory that contains the calculation folders.
    output_hdf
        Destination HDF path to write.
    key
        HDF dataset key, usually ``"df"``.
    calc_file
        Preferred structure filename to read first.
    query
        Optional ``DataFrame.query(...)`` expression applied before writing.
    entropies_file
        Backward-compatible alias for ``thermo_filename``.
    thermo_filename
        Per-folder thermochemistry filename, usually ``"out.txt"``.
    read_electronic_files
        Whether to run the second-stage ``CHGCAR``/``DOSCAR`` enrichment before
        writing.
    electronic_workers
        Worker count for the parallel electronic enrichment stage.
    verbose
        Print crawl/read failures when ``True``.
    progress_callback
        Optional callback with signature ``(completed, total, current_path)``.

    Returns
    -------
    pathlib.Path
        The expanded output HDF path that was written.

    Examples
    --------
    .. code-block:: python

        from onepiece.dftdataframe_import import crawl_root_to_hdf

        output = crawl_root_to_hdf(
            "path/to/calculations",
            "path/to/created_frame.hdf",
            read_electronic_files=False,
        )
    """
    frame = crawl_root_to_frame(
        root,
        calc_file=calc_file,
        query=query,
        entropies_file=entropies_file,
        thermo_filename=thermo_filename,
        read_electronic_files=read_electronic_files,
        electronic_workers=electronic_workers,
        verbose=verbose,
        progress_callback=progress_callback,
        cache_dir=cache_dir,
    )
    output_path = Path(output_hdf).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_hdf(output_path, key=key, mode="w")
    return output_path


def crawl_calculation_directories(
    root: str | Path,
    *,
    calc_file: str = "final.traj",
    thermo_filename: str | None = DEFAULT_THERMO_FILENAME,
) -> list[Path]:
    root_path = Path(root).expanduser()
    if not root_path.exists():
        raise FileNotFoundError(f"Calculation root does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Calculation root is not a directory: {root_path}")

    markers = set(DEFAULT_STRUCTURE_FALLBACKS)
    markers.add(str(calc_file))
    markers.update(KNOWN_FILE_COLUMNS)
    if thermo_filename:
        markers.add(str(thermo_filename))

    calc_dirs: list[Path] = []
    for current_root, _, files in _walk_with_followlinks(root_path):
        if markers.intersection(files):
            calc_dirs.append(current_root)
    return sorted(set(calc_dirs))


def crawl_calculation_paths(root: str | Path, *, calc_file: str = "final.traj") -> list[Path]:
    root_path = Path(root).expanduser()
    if not root_path.exists():
        raise FileNotFoundError(f"Calculation root does not exist: {root_path}")
    directories = crawl_calculation_directories(root_path, calc_file=calc_file, thermo_filename=None)
    paths: list[Path] = []
    for directory in directories:
        structure_path = _resolve_structure_file(directory, preferred_calc_file=calc_file)
        if structure_path is not None:
            paths.append(structure_path)
    return paths


def create_calculation_frame(
    *,
    root: str | Path,
    paths: Iterable[str | Path],
    calc_file: str = "final.traj",
    thermo_filename: str | None = DEFAULT_THERMO_FILENAME,
    read_electronic_files: bool = True,
    electronic_workers: int | None = None,
    verbose: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
    cache_dir: str | Path | None = None,
) -> pd.DataFrame:
    """Create a dataframe from already identified calculation paths.

    Parameters
    ----------
    root
        Common root directory of the calculations.
    paths
        Iterable of calculation directories or structure file paths.
    calc_file
        Preferred structure filename to read first.
    thermo_filename
        Optional per-folder thermo filename. Use ``None`` to skip thermo path
        bookkeeping.
    read_electronic_files
        If ``True``, run ``enrich_electronic_summaries(...)`` on the resulting
        dataframe before returning it.
    electronic_workers
        Worker count for the electronic enrichment stage.
    verbose
        Print read failures when ``True``.
    progress_callback
        Optional callback with signature ``(completed, total, current_path)``.
    """
    root_path = Path(root).expanduser()
    raw_paths = [Path(value).expanduser() for value in paths]
    directories = [_normalize_calculation_directory(path) for path in raw_paths]

    records: list[dict[str, object]] = []
    total = len(directories)
    active_cache_dir = Path(cache_dir).expanduser() if cache_dir is not None else None
    for index, calc_dir in enumerate(directories, start=1):
        if progress_callback is not None:
            progress_callback(index, total, str(calc_dir))

        inventory = _sorted_directory_files(calc_dir)
        structure_path = _resolve_structure_file(calc_dir, preferred_calc_file=calc_file, inventory=inventory)
        if structure_path is None:
            if verbose:
                print(f"[onepiece crawl] skipping folder without readable structure source: {calc_dir}")
            continue

        base_cache_path = _base_cache_path(active_cache_dir, calc_dir)
        base_cache_key = _base_cache_key(calc_dir, structure_path, thermo_filename=thermo_filename)
        cached_record = _load_cached_record(base_cache_path, expected_key=base_cache_key)
        if cached_record is not None:
            records.append(cached_record)
            continue

        atoms = _read_structure(structure_path)
        if atoms is None:
            if verbose:
                print(f"[onepiece crawl] skipping unreadable structure: {structure_path}")
            continue
        contcar_atoms = _load_optional_structure(calc_dir / "CONTCAR") or atoms.copy()

        relative_dir = calc_dir.relative_to(root_path) if calc_dir.is_relative_to(root_path) else calc_dir
        name = _make_name(relative_dir)
        timestamp = float(calc_dir.stat().st_mtime)
        record = {
            "Name": name,
            "Formula": atoms.get_chemical_formula(),
            "Path": str(calc_dir),
            "root": str(root_path),
            "relative_path": relative_dir.as_posix() if hasattr(relative_dir, "as_posix") else str(relative_dir),
            "files": inventory,
            "calc_file": calc_file,
            "structure_source": structure_path.name,
            "structure_file": str(structure_path),
            "struc": atoms.copy(),
            "CONTCAR": contcar_atoms.copy(),
            "E": _safe_energy(atoms),
            "fmax": _safe_fmax(atoms),
            "timestamp": timestamp,
            "human_time": ctime(timestamp),
            "a": _safe_cell_parameter(atoms, 0),
            "b": _safe_cell_parameter(atoms, 1),
            "c": _safe_cell_parameter(atoms, 2),
            "alpha": _safe_cell_parameter(atoms, 3),
            "beta": _safe_cell_parameter(atoms, 4),
            "gamma": _safe_cell_parameter(atoms, 5),
            "volume": _safe_volume(atoms),
            "natoms": float(len(atoms)),
            "constraints": list(getattr(atoms, "constraints", [])),
        }
        for filename, column in KNOWN_FILE_COLUMNS.items():
            candidate = calc_dir / filename
            record[column] = str(candidate) if candidate.exists() else None
            record[f"has_{column.removesuffix('_path')}"] = bool(candidate.exists())
        _update_record_with_input_summaries(
            record,
            atoms=atoms,
            structure_path=structure_path,
            calc_dir=calc_dir,
        )
        _update_record_with_frequency_summaries(record, calc_dir=calc_dir)

        entropy_path = calc_dir / str(thermo_filename) if thermo_filename else None
        record["entropy_source_file"] = str(entropy_path) if entropy_path is not None else None
        record["entropy_data_available"] = bool(entropy_path and entropy_path.exists())
        if base_cache_path is not None:
            _write_cached_record(base_cache_path, cache_key=base_cache_key, record=record)
        records.append(record)

    frame = ensure_name_index(pd.DataFrame(records))
    if read_electronic_files:
        frame = enrich_electronic_summaries(
            frame,
            workers=electronic_workers,
            verbose=verbose,
            cache_dir=cache_dir,
        )
    return ensure_name_index(frame)


def add_input_parameter_checks(
    frame: pd.DataFrame,
    *,
    encut_column: str = "input_encut",
    kpoints_grid_column: str = "input_kpoints_grid",
) -> pd.DataFrame:
    """Annotate whether ENCUT and KPOINTS match the dominant dataset settings."""
    df = frame.copy()
    encut_series = pd.to_numeric(df.get(encut_column), errors="coerce")
    kpoints_series = df.get(kpoints_grid_column, pd.Series(index=df.index, dtype=object))

    encut_reference = _series_mode_scalar(encut_series.round(6))
    kpoints_reference = _series_mode_scalar(kpoints_series.astype(str).replace({"": np.nan, "None": np.nan}))

    df["encut_reference_value"] = encut_reference
    df["kpoints_reference_grid"] = kpoints_reference if pd.notna(kpoints_reference) else None
    df["encut_matches_reference"] = encut_series.eq(encut_reference) if pd.notna(encut_reference) else pd.Series(False, index=df.index)
    df["kpoints_matches_reference"] = (
        kpoints_series.astype(str).eq(str(kpoints_reference))
        if pd.notna(kpoints_reference)
        else pd.Series(False, index=df.index)
    )
    df["input_settings_ok"] = df["encut_matches_reference"].fillna(False) & df["kpoints_matches_reference"].fillna(False)
    return df


def enrich_electronic_summaries(
    frame: pd.DataFrame,
    *,
    path_column: str = "Path",
    workers: int | None = None,
    verbose: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
    cache_dir: str | Path | None = None,
) -> pd.DataFrame:
    """Add ``CHGCAR`` and ``DOSCAR`` summary columns in a separate parallel stage.

    Parameters
    ----------
    frame
        Input dataframe that must contain a calculation-path column.
    path_column
        Column holding the calculation folder paths. The default is ``"Path"``.
    workers
        Number of worker threads. ``None`` selects a default automatically.
    verbose
        Print read failures for problematic electronic files when ``True``.
    progress_callback
        Optional callback with signature ``(completed: int, total: int,
        current_path: str)``. This callback is used during the electronic
        enrichment stage, not during the base crawl.

    Returns
    -------
    pandas.DataFrame
        Copy of the input dataframe with electronic summary columns such as
        ``chgcar_read_ok``, ``chgcar_total_integrated_electrons``,
        ``doscar_read_ok``, and ``doscar_total_dos_below_ef``.

    Examples
    --------
    .. code-block:: python

        from onepiece import crawl_root_to_frame
        from onepiece.dftdataframe_import import enrich_electronic_summaries

        base = crawl_root_to_frame(
            "path/to/calculations",
            read_electronic_files=False,
        )
        enriched = enrich_electronic_summaries(base, workers=12)
    """
    enriched = ensure_name_index(frame)
    if enriched.empty or path_column not in enriched.columns:
        return _ensure_electronic_summary_columns(enriched)

    enriched = _ensure_electronic_summary_columns(enriched)
    tasks: list[tuple[object, Path]] = []
    for index, value in enriched[path_column].items():
        if value is None or pd.isna(value):
            continue
        tasks.append((index, Path(value).expanduser()))
    if not tasks:
        return enriched
    active_cache_dir = Path(cache_dir).expanduser() if cache_dir is not None else None

    max_workers = _resolve_electronic_workers(workers, total_tasks=len(tasks))
    total = len(tasks)
    completed = 0
    if max_workers <= 1:
        for index, calc_dir in tasks:
            summary = _electronic_summary_with_cache(calc_dir, verbose=verbose, cache_dir=active_cache_dir)
            for key, value in summary.items():
                enriched.at[index, key] = value
            completed += 1
            if progress_callback is not None:
                progress_callback(completed, total, str(calc_dir))
        return enriched

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_electronic_summary_with_cache, calc_dir, verbose=verbose, cache_dir=active_cache_dir): (index, calc_dir)
            for index, calc_dir in tasks
        }
        for future in as_completed(future_map):
            index, calc_dir = future_map[future]
            summary = future.result()
            for key, value in summary.items():
                enriched.at[index, key] = value
            completed += 1
            if progress_callback is not None:
                progress_callback(completed, total, str(calc_dir))
    return ensure_name_index(enriched)


def merge_entropies_file(frame: pd.DataFrame, entropies_file: str | Path) -> pd.DataFrame:
    return _merge_per_folder_thermochemistry(frame, filename=Path(entropies_file).name)


def _merge_per_folder_thermochemistry(frame: pd.DataFrame, *, filename: str) -> pd.DataFrame:
    enriched = frame.copy()
    thermo_columns = [
        "modes_for_G",
        "Cv_at_T",
        "E_pot",
        "E_ZPE",
        "Cv_trans",
        "Cv_rot",
        "Cv_vib",
        "C_vtoC_p",
        "S_trans",
        "S_rot",
        "S_elec",
        "S_vib",
        "Sbar",
        "S",
    ]
    for column in thermo_columns:
        if column not in enriched.columns:
            enriched[column] = None if column == "modes_for_G" else np.nan
    if "entropy_source_file" not in enriched.columns:
        enriched["entropy_source_file"] = enriched.get("Path", pd.Series(index=enriched.index, dtype=object)).apply(
            lambda value: str(Path(value).expanduser() / filename) if pd.notna(value) else filename
        )
    if "entropy_data_available" not in enriched.columns:
        enriched["entropy_data_available"] = False

    for index, row in enriched.iterrows():
        path_value = row.get("Path")
        if path_value is None or pd.isna(path_value):
            continue
        thermo_path = Path(path_value).expanduser() / filename
        enriched.at[index, "entropy_source_file"] = str(thermo_path)
        if not thermo_path.exists():
            enriched.at[index, "entropy_data_available"] = False
            continue
        parsed = _parse_ase_thermo_output(thermo_path)
        if not parsed:
            enriched.at[index, "entropy_data_available"] = False
            continue
        for key, value in parsed.items():
            enriched.at[index, key] = value
        enriched.at[index, "entropy_data_available"] = True
    return enriched


def _parse_ase_thermo_output(path: Path) -> dict[str, Any]:
    text = path.read_text(errors="ignore")
    lines = text.splitlines()
    results: dict[str, Any] = {}

    mapping = {
        "cvatt": "Cv_at_T",
        "cvtat": "Cv_at_T",
        "epot": "E_pot",
        "ezpe": "E_ZPE",
        "cvtrans": "Cv_trans",
        "cvrot": "Cv_rot",
        "cvvib": "Cv_vib",
        "cvtocp": "C_vtoC_p",
        "strans": "S_trans",
        "srot": "S_rot",
        "selec": "S_elec",
        "svib": "S_vib",
        "s1bartop": "Sbar",
        "sbar": "Sbar",
    }

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if "=" in line:
            left, right = line.split("=", 1)
        elif ":" in line:
            left, right = line.split(":", 1)
        else:
            parts = line.split()
            if len(parts) < 2:
                continue
            left, right = parts[0], " ".join(parts[1:])
        normalized = _normalize_token(left)
        matched = mapping.get(normalized)
        if matched is None:
            compact_line = _normalize_token(line)
            matched = next((column for token, column in mapping.items() if token in compact_line), None)
        if matched is None:
            if line.startswith("S ") and "1 bar" not in line:
                matched = "S"
            else:
                continue
        value = _first_float(right)
        if value is not None:
            results[matched] = value

    modes = _parse_modes_for_g(lines)
    if modes:
        results["modes_for_G"] = modes

    return results


def _parse_modes_for_g(lines: list[str]) -> list[str]:
    header_index = next((idx for idx, line in enumerate(lines) if line.strip() == "#    meV     cm^-1"), None)
    if header_index is None:
        header_index = next((idx for idx, line in enumerate(lines) if "meV" in line and "cm^-1" in line), None)
    if header_index is None:
        return []

    modes: list[str] = []
    for raw_line in lines[header_index + 2 :]:
        line = raw_line.strip()
        if not line or line.startswith("-"):
            break
        parts = line.split()
        if len(parts) >= 3:
            modes.append(parts[2])
    return modes


def _active_thermo_filename(
    *,
    entropies_file: str | Path | None,
    thermo_filename: str | None,
) -> str | None:
    if entropies_file is not None:
        return Path(entropies_file).name
    if thermo_filename is None:
        return None
    text = str(thermo_filename).strip()
    return text or None


def _walk_with_followlinks(root: Path) -> Iterable[tuple[Path, list[str], list[str]]]:
    for current_root, folders, files in os.walk(root, followlinks=True):
        yield Path(current_root), folders, files


def _normalize_calculation_directory(path: Path) -> Path:
    return path if path.is_dir() else path.parent


def _resolve_structure_file(
    calc_dir: Path,
    *,
    preferred_calc_file: str,
    inventory: list[str] | None = None,
) -> Path | None:
    known_files = set(inventory or _sorted_directory_files(calc_dir))
    candidates = [str(preferred_calc_file), *DEFAULT_STRUCTURE_FALLBACKS]
    seen: set[str] = set()
    for candidate_name in candidates:
        if candidate_name in seen:
            continue
        seen.add(candidate_name)
        candidate = calc_dir / candidate_name
        if candidate_name in known_files and candidate.exists():
            return candidate
    return None


def _sorted_directory_files(path: Path) -> list[str]:
    try:
        with os.scandir(path) as entries:
            return sorted(entry.name for entry in entries if entry.is_file())
    except FileNotFoundError:
        return []


def _make_name(relative_dir: Path) -> str:
    text = relative_dir.as_posix() if hasattr(relative_dir, "as_posix") else str(relative_dir)
    text = text.strip().strip("/")
    if not text:
        return "root"
    return text.replace("/", "-")


def _read_structure(path: Path) -> Atoms | None:
    try:
        atoms = read(path, index=-1)
    except Exception:
        return None
    return atoms if atoms.__class__.__name__ == "Atoms" else None


def _load_optional_structure(path: Path) -> Atoms | None:
    if not path.exists():
        return None
    return _read_structure(path)


def _normalize_token(text: str) -> str:
    return "".join(character for character in text.lower() if character.isalnum())


def _first_float(text: str) -> float | None:
    cleaned = text.replace("D", "E").replace("d", "e")
    number_chars: list[str] = []
    started = False
    for character in cleaned:
        if character.isdigit() or character in "+-.eE":
            number_chars.append(character)
            started = True
        elif started:
            break
    number_token = "".join(number_chars)
    if not number_token:
        return None
    try:
        return float(number_token)
    except ValueError:
        return None


def _safe_energy(atoms: Atoms) -> float:
    try:
        return float(atoms.get_potential_energy())
    except Exception:
        return float("nan")


def _safe_fmax(atoms: Atoms) -> float:
    try:
        forces = np.asarray(atoms.get_forces(), dtype=float)
    except Exception:
        return float("nan")
    if forces.size == 0:
        return float("nan")
    return float(np.linalg.norm(forces, axis=1).max())


def _safe_cell_parameter(atoms: Atoms, index: int) -> float:
    try:
        return float(atoms.cell.cellpar()[index])
    except Exception:
        return float("nan")


def _safe_volume(atoms: Atoms) -> float:
    try:
        return float(atoms.get_volume())
    except Exception:
        return float("nan")


def _update_record_with_input_summaries(
    record: dict[str, object],
    *,
    atoms: Atoms,
    structure_path: Path,
    calc_dir: Path,
) -> None:
    structure_parameters = _extract_structure_input_parameters(atoms)
    incar_parameters = _parse_incar_file(calc_dir / "INCAR")
    active_parameters = structure_parameters or incar_parameters
    parameter_source = structure_path.name if structure_parameters else ("INCAR" if incar_parameters else None)
    kpoints = _parse_kpoints_file(calc_dir / "KPOINTS")

    record.update(
        {
            "input_parameter_source": parameter_source,
            "input_parameter_count": float(len(active_parameters)) if active_parameters else 0.0,
            "input_parameters_json": json.dumps(active_parameters, sort_keys=True) if active_parameters else None,
            "input_encut": _coerce_float_parameter(active_parameters.get("ENCUT")) if active_parameters else np.nan,
            "input_ismear": _coerce_float_parameter(active_parameters.get("ISMEAR")) if active_parameters else np.nan,
            "input_sigma": _coerce_float_parameter(active_parameters.get("SIGMA")) if active_parameters else np.nan,
            "input_ispin": _coerce_float_parameter(active_parameters.get("ISPIN")) if active_parameters else np.nan,
            "input_ediff": _coerce_float_parameter(active_parameters.get("EDIFF")) if active_parameters else np.nan,
            "input_prec": str(active_parameters.get("PREC")) if active_parameters and active_parameters.get("PREC") is not None else None,
            "input_gga": str(active_parameters.get("GGA")) if active_parameters and active_parameters.get("GGA") is not None else None,
            "input_kpoints_source": "KPOINTS" if kpoints else None,
            "input_kpoints_mode": kpoints.get("mode") if kpoints else None,
            "input_kpoints_grid": tuple(kpoints["grid"]) if kpoints and kpoints.get("grid") else None,
            "input_kpoints_shift": tuple(kpoints["shift"]) if kpoints and kpoints.get("shift") else None,
            "input_kpoints_present": bool(kpoints),
        }
    )


def _update_record_with_frequency_summaries(
    record: dict[str, object],
    *,
    calc_dir: Path,
) -> None:
    summary = _read_frequency_summary(calc_dir)
    record.update(summary)


def _extract_structure_input_parameters(atoms: Atoms) -> dict[str, object]:
    calc = getattr(atoms, "calc", None)
    if calc is None:
        return {}
    parameters = getattr(calc, "parameters", None)
    if isinstance(parameters, dict) and parameters:
        return {str(key).upper(): value for key, value in parameters.items()}
    if parameters is not None:
        try:
            as_dict = dict(parameters)
        except Exception:
            as_dict = {}
        if as_dict:
            return {str(key).upper(): value for key, value in as_dict.items()}
    try:
        calc_dict = calc.todict()
    except Exception:
        return {}
    candidate = calc_dict.get("parameters", calc_dict)
    if isinstance(candidate, dict):
        normalized = {str(key).upper(): value for key, value in candidate.items() if str(key).upper() != "RESULTS"}
        return normalized
    return {}


def _parse_incar_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    parameters: dict[str, object] = {}
    for raw_line in path.read_text(errors="ignore").splitlines():
        line = raw_line.split("#", 1)[0].split("!", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = str(key).strip().upper()
        parameters[normalized_key] = _parse_incar_value(value.strip())
    return parameters


def _parse_incar_value(text: str) -> object:
    stripped = text.strip()
    if not stripped:
        return ""
    parts = stripped.split()
    if len(parts) > 1:
        numeric_parts = [_coerce_float_parameter(part) for part in parts]
        if all(pd.notna(value) for value in numeric_parts):
            return [float(value) for value in numeric_parts]
        return stripped
    numeric = _coerce_float_parameter(stripped)
    if pd.notna(numeric):
        return float(numeric)
    return stripped


def _parse_kpoints_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    lines = [line.strip() for line in path.read_text(errors="ignore").splitlines() if line.strip()]
    if len(lines) < 4:
        return {}
    mode = lines[2].lower()
    grid_line = lines[3].split()
    shift_line = lines[4].split() if len(lines) > 4 else []
    grid = [int(float(value)) for value in grid_line[:3]] if len(grid_line) >= 3 else []
    shift = [float(value) for value in shift_line[:3]] if len(shift_line) >= 3 else []
    return {
        "mode": mode,
        "grid": grid,
        "shift": shift,
    }


def _coerce_float_parameter(value: object) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(numeric) if pd.notna(numeric) else float("nan")


def _series_mode_scalar(series: pd.Series) -> object:
    non_null = series.dropna()
    if non_null.empty:
        return np.nan
    mode = non_null.mode()
    if mode.empty:
        return np.nan
    return mode.iloc[0]


def _read_frequency_summary(calc_dir: Path) -> dict[str, object]:
    out_txt_path = calc_dir / DEFAULT_THERMO_FILENAME
    outcar_path = calc_dir / "OUTCAR"

    frequencies_cm1: list[float] = []
    frequencies_mev: list[float] = []
    source = None

    if out_txt_path.exists():
        parsed = _parse_ase_frequency_modes(out_txt_path)
        if parsed["frequencies_cm1"]:
            frequencies_cm1 = parsed["frequencies_cm1"]
            frequencies_mev = parsed["frequencies_mev"]
            source = str(out_txt_path)

    if not frequencies_cm1 and outcar_path.exists():
        parsed = _parse_outcar_frequencies(outcar_path)
        if parsed["frequencies_cm1"]:
            frequencies_cm1 = parsed["frequencies_cm1"]
            frequencies_mev = parsed["frequencies_mev"]
            source = str(outcar_path)

    imaginary = [value for value in frequencies_cm1 if value < 0]
    return {
        "frequency_source_file": source,
        "frequencies_cm1": frequencies_cm1 or None,
        "frequencies_mev": frequencies_mev or None,
        "frequency_count": float(len(frequencies_cm1)),
        "imaginary_frequency_count": float(len(imaginary)),
        "lowest_frequency_cm1": float(min(frequencies_cm1)) if frequencies_cm1 else np.nan,
        "highest_frequency_cm1": float(max(frequencies_cm1)) if frequencies_cm1 else np.nan,
    }


def _parse_ase_frequency_modes(path: Path) -> dict[str, list[float]]:
    lines = path.read_text(errors="ignore").splitlines()
    header_index = next((idx for idx, line in enumerate(lines) if "meV" in line and "cm^-1" in line), None)
    if header_index is None:
        return {"frequencies_cm1": [], "frequencies_mev": []}

    frequencies_cm1: list[float] = []
    frequencies_mev: list[float] = []
    for raw_line in lines[header_index + 1 :]:
        line = raw_line.strip()
        if not line or line.startswith("-"):
            continue
        parts = line.split()
        if len(parts) < 3 or not parts[0].rstrip(".").isdigit():
            continue
        mev = _first_float(parts[1])
        cm1 = _first_float(parts[2])
        if mev is None or cm1 is None:
            continue
        frequencies_mev.append(float(mev))
        frequencies_cm1.append(float(cm1))
    return {"frequencies_cm1": frequencies_cm1, "frequencies_mev": frequencies_mev}


def _parse_outcar_frequencies(path: Path) -> dict[str, list[float]]:
    frequencies_cm1: list[float] = []
    frequencies_mev: list[float] = []
    for raw_line in path.read_text(errors="ignore").splitlines():
        if " cm-1" not in raw_line or " meV" not in raw_line or " f" not in raw_line:
            continue
        match = FREQUENCY_OUTCAR_PATTERN.search(raw_line)
        if not match:
            continue
        cm1 = float(match.group("cm1"))
        mev = float(match.group("mev"))
        if match.group("imaginary"):
            cm1 = -abs(cm1)
            mev = -abs(mev)
        frequencies_cm1.append(cm1)
        frequencies_mev.append(mev)
    return {"frequencies_cm1": frequencies_cm1, "frequencies_mev": frequencies_mev}


def _update_record_with_electronic_summaries(
    record: dict[str, object],
    *,
    calc_dir: Path,
    verbose: bool,
) -> None:
    record.update(_electronic_summary_from_path(calc_dir, verbose=verbose))


def _electronic_summary_with_cache(
    calc_dir: Path,
    *,
    verbose: bool,
    cache_dir: Path | None,
) -> dict[str, object]:
    cache_path = _electronic_cache_path(cache_dir, calc_dir)
    cache_key = _electronic_cache_key(calc_dir)
    cached = _load_cached_record(cache_path, expected_key=cache_key)
    if cached is not None:
        return cached
    summary = _electronic_summary_from_path(calc_dir, verbose=verbose)
    if cache_path is not None:
        _write_cached_record(cache_path, cache_key=cache_key, record=summary)
    return summary


def _ensure_electronic_summary_columns(frame: pd.DataFrame) -> pd.DataFrame:
    ensured = frame.copy()
    defaults = _default_electronic_summary_record()
    for column, default in defaults.items():
        if column not in ensured.columns:
            ensured[column] = default
    return ensured


def _base_cache_path(cache_dir: Path | None, calc_dir: Path) -> Path | None:
    if cache_dir is None:
        return None
    digest = sha256(str(calc_dir).encode("utf-8")).hexdigest()
    return cache_dir / "base" / f"{digest}.pkl"


def _electronic_cache_path(cache_dir: Path | None, calc_dir: Path) -> Path | None:
    if cache_dir is None:
        return None
    digest = sha256(str(calc_dir).encode("utf-8")).hexdigest()
    return cache_dir / "electronic" / f"{digest}.pkl"


def _base_cache_key(calc_dir: Path, structure_path: Path, *, thermo_filename: str | None) -> str:
    parts = [
        structure_path,
        calc_dir / "CONTCAR",
        calc_dir / "INCAR",
        calc_dir / "KPOINTS",
        calc_dir / "OUTCAR",
    ]
    if thermo_filename:
        parts.append(calc_dir / thermo_filename)
    return cache_key_for_paths(*parts)


def _electronic_cache_key(calc_dir: Path) -> str:
    return cache_key_for_paths(
        calc_dir / "CHGCAR",
        calc_dir / "DOSCAR",
        calc_dir / "POTCAR",
        calc_dir / "ACF.dat",
    )


def _load_cached_record(cache_path: Path | None, *, expected_key: str) -> dict[str, object] | None:
    if cache_path is None or not cache_path.exists():
        return None
    try:
        payload = read_cache_payload(cache_path)
    except (FileNotFoundError, EOFError, UnpicklingError, AttributeError, ModuleNotFoundError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("cache_key") != expected_key:
        return None
    record = payload.get("record")
    return record.copy() if isinstance(record, dict) else None


def _write_cached_record(cache_path: Path, *, cache_key: str, record: dict[str, object]) -> None:
    write_cache_payload(cache_path, {"cache_key": cache_key, "record": record.copy()})


def _default_electronic_summary_record() -> dict[str, object]:
    return {
        "chgcar_read_ok": False,
        "chgcar_read_error": None,
        "chgcar_grid_shape": None,
        "chgcar_voxel_volume": np.nan,
        "chgcar_total_integrated_electrons": np.nan,
        "chgcar_spin_density_available": None,
        "chgcar_natoms": np.nan,
        "doscar_read_ok": False,
        "doscar_read_error": None,
        "doscar_natoms": np.nan,
        "doscar_spin_polarized": None,
        "doscar_efermi": np.nan,
        "doscar_energy_min": np.nan,
        "doscar_energy_max": np.nan,
        "doscar_points": np.nan,
        "doscar_total_dos_below_ef": np.nan,
        "doscar_integrated_states_below_ef": np.nan,
    }


def _resolve_electronic_workers(workers: int | None, *, total_tasks: int) -> int:
    if total_tasks <= 0:
        return 1
    if workers is not None:
        return max(1, min(int(workers), total_tasks))
    cpu_count = os.cpu_count() or 1
    suggested = min(32, max(4, cpu_count * 4))
    return min(suggested, total_tasks)


def _electronic_summary_from_path(calc_dir: Path, *, verbose: bool) -> dict[str, object]:
    summary = _default_electronic_summary_record()

    chgcar_path = calc_dir / "CHGCAR"
    if chgcar_path.exists():
        try:
            chgcar = read_chgcar(chgcar_path)
        except Exception as exc:
            summary["chgcar_read_error"] = f"{type(exc).__name__}: {exc}"
            if verbose:
                print(f"[onepiece crawl] CHGCAR read failed for {chgcar_path}: {exc}")
        else:
            total_electrons = float(np.asarray(chgcar.charge_density, dtype=float).sum() * chgcar.voxel_volume)
            summary["chgcar_read_ok"] = True
            summary["chgcar_grid_shape"] = tuple(int(value) for value in chgcar.grid_shape)
            summary["chgcar_voxel_volume"] = float(chgcar.voxel_volume)
            summary["chgcar_total_integrated_electrons"] = total_electrons
            summary["chgcar_spin_density_available"] = bool(chgcar.spin_density is not None)
            summary["chgcar_natoms"] = float(len(chgcar.atoms))

    doscar_path = calc_dir / "DOSCAR"
    if doscar_path.exists():
        try:
            doscar = read_doscar(doscar_path)
        except Exception as exc:
            summary["doscar_read_error"] = f"{type(exc).__name__}: {exc}"
            if verbose:
                print(f"[onepiece crawl] DOSCAR read failed for {doscar_path}: {exc}")
        else:
            energies = np.asarray(doscar.energies, dtype=float)
            total_dos = np.asarray(doscar.total_dos, dtype=float)
            below_ef_mask = energies <= 0.0
            total_signal = total_dos.sum(axis=0) if total_dos.ndim > 1 else total_dos.reshape(-1)
            if below_ef_mask.any():
                total_below_ef = float(trapezoid(total_signal[below_ef_mask], energies[below_ef_mask]))
                integrated_states_below_ef = float(doscar.integrated_total_dos[..., below_ef_mask][:, -1].sum())
            else:
                total_below_ef = 0.0
                integrated_states_below_ef = 0.0
            summary["doscar_read_ok"] = True
            summary["doscar_natoms"] = float(doscar.natoms)
            summary["doscar_spin_polarized"] = bool(doscar.spin_polarized)
            summary["doscar_efermi"] = float(doscar.efermi)
            summary["doscar_energy_min"] = float(energies.min()) if energies.size else np.nan
            summary["doscar_energy_max"] = float(energies.max()) if energies.size else np.nan
            summary["doscar_points"] = float(energies.size)
            summary["doscar_total_dos_below_ef"] = total_below_ef
            summary["doscar_integrated_states_below_ef"] = integrated_states_below_ef
    return summary
