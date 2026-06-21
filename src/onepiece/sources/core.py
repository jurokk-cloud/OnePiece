from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from onepiece._compat import install_numpy_pickle_compat
from onepiece._polars import dataframe_is_polars_safe, get_polars
from onepiece.adsorption import add_adsorption_energies, assign_surface_references
from onepiece.frame_utils import ensure_name_index
from onepiece.provenance import file_checksum
from onepiece.storage import detect_storage_format, load_dataset

SOURCE_STATE_KEY = "onepiece_studio_extra_hdf_sources"
logger = logging.getLogger(__name__)
GAS_REFERENCE_LABELS = ("CO", "CO2", "H2", "H2O", "CH3OH", "NH3")
EXPLICIT_DATASET_KINDS = {
    "auto": None,
    "mixed": None,
    "gas": "gas_reference",
    "gas_phase": "gas_reference",
    "surface": "surface",
    "bulk": "bulk",
}


def combined_active_database(
    state: dict[str, Any],
    base: pd.DataFrame,
    *,
    base_label: str = "base",
    base_path: str = "base",
    base_source_id: str = "base",
) -> pd.DataFrame:
    frames = [
        prepare_source_frame(
            base,
            label=base_label,
            path=base_path,
            source_id=base_source_id,
        )
    ]
    for _source_id, item in state.get(SOURCE_STATE_KEY, {}).items():
        if item.get("enabled", True):
            frames.append(item["dataframe"].copy())
    combined = pd.concat(frames, ignore_index=False, sort=False) if len(frames) > 1 else frames[0]
    return ensure_name_index(combined)


def store_source(
    state: dict[str, Any],
    frame: pd.DataFrame,
    *,
    label: str,
    path: str,
    hdf_key: str = "df",
    origin: str = "path",
    import_options: dict[str, Any] | None = None,
) -> str:
    sources = state.setdefault(SOURCE_STATE_KEY, {})
    source_id = _source_id(label, path, sources)
    prepared = prepare_source_frame(frame, label=label, path=path, source_id=source_id)
    profile = detect_source_profile(prepared)
    fingerprint = source_fingerprint(path)
    sources[source_id] = {
        "label": label,
        "path": path,
        "hdf_key": hdf_key,
        "origin": origin,
        "import_options": import_options or {},
        "rows": len(prepared),
        "columns": prepared.shape[1],
        "enabled": True,
        "dataframe": prepared,
        "profile": profile["profile"],
        "capabilities": profile["capabilities"],
        "fingerprint": fingerprint,
    }
    return source_id


def source_descriptors(state: dict[str, Any]) -> list[dict[str, Any]]:
    descriptors: list[dict[str, Any]] = []
    for source_id, item in state.get(SOURCE_STATE_KEY, {}).items():
        descriptors.append(
            {
                "id": source_id,
                "label": item.get("label", source_id),
                "path": item.get("path", ""),
                "hdf_key": item.get("hdf_key", "df"),
                "origin": item.get("origin", "path"),
                "import_options": item.get("import_options", {}),
                "enabled": bool(item.get("enabled", True)),
                "reloadable": bool(item.get("origin", "path") == "path"),
                "profile": item.get("profile", "generic_dataframe"),
                "capabilities": list(item.get("capabilities", [])),
                "fingerprint": item.get("fingerprint") or source_fingerprint(str(item.get("path", ""))),
            }
        )
    return descriptors


def restore_source_descriptors(state: dict[str, Any], descriptors: list[dict[str, Any]]) -> list[str]:
    messages: list[str] = []
    sources = state.setdefault(SOURCE_STATE_KEY, {})
    sources.clear()
    for descriptor in descriptors:
        if descriptor.get("origin", "path") != "path":
            messages.append(
                f"Skipped source '{descriptor.get('label', '')}' because uploaded temporary HDF files are not reloadable."
            )
            continue
        path = Path(str(descriptor.get("path", ""))).expanduser()
        key = str(descriptor.get("hdf_key", "df"))
        import_options = descriptor.get("import_options", {})
        try:
            frame = read_dataset_path(path, key=key)
        except Exception as exc:
            messages.append(f"Could not reload source '{descriptor.get('label', path.name)}': {exc}")
            continue
        frame = apply_import_options(frame, import_options)
        source_id = str(descriptor.get("id") or _source_id(path.name, str(path), sources))
        prepared = prepare_source_frame(frame, label=str(descriptor.get("label", path.name)), path=str(path), source_id=source_id)
        profile = detect_source_profile(prepared)
        fingerprint = source_fingerprint(path)
        expected_fingerprint = descriptor.get("fingerprint") or {}
        checksum_changed = bool(
            expected_fingerprint.get("checksum")
            and fingerprint.get("checksum")
            and expected_fingerprint.get("checksum") != fingerprint.get("checksum")
        )
        if checksum_changed:
            messages.append(f"Source '{descriptor.get('label', path.name)}' checksum changed since the project was saved.")
        sources[source_id] = {
            "label": str(descriptor.get("label", path.name)),
            "path": str(path),
            "hdf_key": key,
            "origin": "path",
            "import_options": import_options,
            "rows": len(prepared),
            "columns": prepared.shape[1],
            "enabled": bool(descriptor.get("enabled", True)),
            "dataframe": prepared,
            "profile": profile["profile"],
            "capabilities": profile["capabilities"],
            "fingerprint": fingerprint,
        }
    return messages


def source_fingerprint(path: str | Path) -> dict[str, Any]:
    """Return local FAIR source identity metadata for a path-backed source."""
    source = Path(str(path)).expanduser()
    if not source.exists() or str(path) in {"", "base"}:
        return {"path": str(path), "exists": False}
    stat = source.stat()
    payload: dict[str, Any] = {
        "path": str(source),
        "exists": True,
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "storage_format": detect_storage_format(source),
    }
    if source.is_file():
        payload["checksum"] = file_checksum(source)
    return payload


def prepare_source_frame(frame: pd.DataFrame, *, label: str, path: str, source_id: str) -> pd.DataFrame:
    prepared = ensure_name_index(frame)
    if "dataset" not in prepared.columns:
        prepared.insert(0, "dataset", Path(label).stem)
    if "dataset_label" not in prepared.columns:
        insert_at = 1 if "dataset" in prepared.columns else 0
        prepared.insert(insert_at, "dataset_label", Path(label).stem)
    if "source_hdf" not in prepared.columns:
        insert_at = min(2, len(prepared.columns))
        prepared.insert(insert_at, "source_hdf", path)
    if "source_row" not in prepared.columns:
        insert_at = min(3, len(prepared.columns))
        prepared.insert(insert_at, "source_row", prepared.index.astype(str))
    prepared["onepiece_studio_source_id"] = source_id
    prepared["onepiece_studio_source_label"] = label
    return ensure_name_index(prepared)


def read_dataset_path(path: Path, *, key: str = "df") -> pd.DataFrame:
    """Read a dataset from any supported on-disk layout.

    Detects the storage format (pandas HDF file, parquet dataset directory,
    or manifest file) and dispatches to the right reader. The returned frame
    always has a ``Name`` index.

    Examples
    --------
    >>> import onepiece
    >>> frame = onepiece.read_dataset_path(onepiece.bundled_catalysis_hub_dataset())
    >>> len(frame)
    133
    """
    if not path.exists():
        raise FileNotFoundError(path)
    storage_format = detect_storage_format(path)
    if storage_format == "parquet" and (path.is_dir() or path.suffix.lower() in {".parquet", ".pq", ".json"}):
        frame, _manifest = load_dataset(path)
        return ensure_name_index(frame)
    if storage_format == "hdf" or path.suffix.lower() in {".hdf", ".h5"}:
        return read_hdf_path(path, key=key)
    raise ValueError(f"Could not determine how to read dataset path '{path}'.")


def read_hdf_path(path: Path, *, key: str, numpy_pickle_compat: bool = True) -> pd.DataFrame:
    """Read a pandas HDF file into a ``Name``-indexed dataframe.

    This is the canonical HDF entry point: it owns the friendly error
    messages and the NumPy pickle-compatibility shim needed for files written
    with older NumPy versions. Parquet dataset directories are accepted too
    and routed through :func:`onepiece.load_dataset`.

    Examples
    --------
    >>> import onepiece
    >>> path = onepiece.bundled_catalysis_hub_dataset()
    >>> frame = onepiece.read_hdf_path(path, key="df")
    >>> "E" in frame.columns
    True
    >>> frame.index.name
    'Name'
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset file not found: {path}. Check the path; both pandas HDF "
            "files and parquet dataset directories are supported."
        )
    if path.is_dir() or path.name.endswith(".json") or path.suffix.lower() in {".parquet", ".pq"}:
        frame, _manifest = load_dataset(path)
        return ensure_name_index(frame)
    if numpy_pickle_compat:
        install_numpy_pickle_compat()
    try:
        return ensure_name_index(pd.read_hdf(path, key=key).copy())
    except Exception as exc:
        raise RuntimeError(_friendly_hdf_read_error(path, key=key, error=exc)) from exc


def read_uploaded_hdf(uploaded: Any, *, key: str) -> tuple[pd.DataFrame, Path]:
    suffix = Path(uploaded.name).suffix or ".hdf"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="onepiece_studio_upload_")
    path = Path(handle.name)
    try:
        handle.write(uploaded.getbuffer())
    finally:
        handle.close()
    return ensure_name_index(read_hdf_path(path, key=key)), path


def map_adsorption_columns(frame: pd.DataFrame, options: dict[str, Any]) -> pd.DataFrame:
    mapped = frame.copy()
    column_map = {
        "Name": str(options.get("name_column", "")).strip(),
        "E": str(options.get("energy_column", "")).strip(),
        "Formula": str(options.get("formula_column", "")).strip(),
        "Path": str(options.get("path_column", "")).strip(),
    }
    for target, source in column_map.items():
        if not source or source not in mapped.columns:
            continue
        mapped[target] = mapped[source]
    return mapped


def apply_import_options(frame: pd.DataFrame, options: dict[str, Any] | None) -> pd.DataFrame:
    if not options:
        return frame
    prepared = frame.copy()
    prepared = map_adsorption_columns(prepared, options)
    prepared = apply_dataset_kind(prepared, options)
    if options.get("enable_adsorption_prep"):
        gas_refs = detected_gas_reference_values(prepared)
        prepared = add_adsorption_energies(assign_surface_references(prepared), gas_refs)
    return prepared


def apply_dataset_kind(frame: pd.DataFrame, options: dict[str, Any] | None) -> pd.DataFrame:
    if not options:
        return frame
    kind_value = str(options.get("dataset_kind", "auto")).strip().lower()
    normalized_class = EXPLICIT_DATASET_KINDS.get(kind_value)
    prepared = frame.copy()
    prepared["onepiece_dataset_kind"] = kind_value if kind_value in EXPLICIT_DATASET_KINDS else "auto"
    if normalized_class is not None:
        prepared["record_class"] = normalized_class
    return prepared


def gas_reference_candidates(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {label: _find_gas_candidates(frame, label) for label in GAS_REFERENCE_LABELS}


def detected_gas_reference_values(frame: pd.DataFrame) -> dict[str, float]:
    detected: dict[str, float] = {}
    for label, candidate_frame in gas_reference_candidates(frame).items():
        if candidate_frame is not None and not candidate_frame.empty:
            value = pd.to_numeric(candidate_frame.iloc[0].get("E"), errors="coerce")
            if pd.notna(value):
                detected[label] = float(value)
    return detected


def detect_source_profile(frame: pd.DataFrame) -> dict[str, Any]:
    columns = set(frame.columns)
    capabilities: list[str] = ["filtering", "project_persistence"]
    profile = "generic_dataframe"
    explicit_kind = _explicit_dataset_kind(frame)

    has_structure = any(column in columns for column in ("struc", "CONTCAR", "structure", "atoms"))
    has_energy = "E" in columns
    has_formula = "Formula" in columns
    if has_structure:
        capabilities.append("ase_structure_view")
    if has_energy:
        capabilities.append("energetics")
    if has_formula:
        capabilities.append("composition_search")

    if {"form_G_per_Area", "hkl"}.intersection(columns):
        profile = "phase_diagram_local_hdf"
        capabilities.extend(["phase_diagram", "surface_thermodynamics"])
    elif {"reaction_id", "reaction_system_name"}.issubset(columns):
        profile = "reaction_database_local_hdf"
        capabilities.extend(["reaction_network", "adsorption_energy"])
    elif explicit_kind == "bulk" and {"Name", "Formula", "E"}.issubset(columns):
        profile = "bulk_materials_local_hdf"
        capabilities.extend(["bulk_screening", "composition_search"])
    elif explicit_kind == "gas" and {"Name", "Formula", "E"}.issubset(columns):
        profile = "gas_phase_local_hdf"
        capabilities.extend(["gas_reference_library", "thermochemistry"])
    elif explicit_kind == "surface" and {"Name", "Formula", "E"}.issubset(columns):
        profile = "surface_local_hdf"
        capabilities.extend(["surface_reference_assignment", "surface_screening"])
    elif {"Name", "Formula", "E"}.issubset(columns):
        profile = "surface_adsorption_local_hdf"
        capabilities.extend(["surface_reference_assignment", "adsorption_energy"])
        gas_refs = detected_gas_reference_values(frame)
        if {"CO", "CH3OH", "H2"}.issubset(set(gas_refs)):
            capabilities.append("adsorption_energy_ready")
        if {"CO2", "H2O", "H2"}.issubset(set(gas_refs)):
            capabilities.append("gibbs_energy_ready")

    capabilities = sorted(set(capabilities))
    return {
        "profile": profile,
        "capabilities": capabilities,
        "summary": source_profile_summary(profile, capabilities),
    }


def source_profile_summary(profile: str, capabilities: list[str]) -> str:
    if profile == "surface_adsorption_local_hdf":
        return "Surface/adsorption dataset with local energetics and reference assignment."
    if profile == "surface_local_hdf":
        return "Surface dataset with local energetics and explicit surface classification."
    if profile == "bulk_materials_local_hdf":
        return "Bulk-materials dataset with explicit bulk classification."
    if profile == "gas_phase_local_hdf":
        return "Gas-phase dataset suited for reference energies and thermochemistry."
    if profile == "reaction_database_local_hdf":
        return "Reaction-centric dataset suited for pathway and barrier analysis."
    if profile == "phase_diagram_local_hdf":
        return "Surface thermodynamics dataset suited for phase-diagram analysis."
    return f"Generic dataframe source with capabilities: {', '.join(capabilities[:5])}"


def _explicit_dataset_kind(frame: pd.DataFrame) -> str | None:
    if "onepiece_dataset_kind" not in frame.columns or frame.empty:
        return None
    values = frame["onepiece_dataset_kind"].dropna().astype(str).str.strip().str.lower()
    values = values[~values.isin({"", "auto", "mixed"})]
    if values.empty:
        return None
    unique_values = values.unique().tolist()
    return unique_values[0] if len(unique_values) == 1 else None


def _find_gas_candidates(source: pd.DataFrame, label: str) -> pd.DataFrame:
    accelerated = _find_gas_candidates_with_polars(source, label)
    if accelerated is not None:
        return accelerated
    if "E" not in source.columns:
        return pd.DataFrame(columns=["Name", "Formula", "E"])
    frame = source.copy()
    frame["E"] = pd.to_numeric(frame["E"], errors="coerce")
    frame = frame[frame["E"].notna() & (frame["E"] != 0)].copy()
    if frame.empty:
        return pd.DataFrame(columns=["Name", "Formula", "E"])

    names = frame.get("Name", pd.Series("", index=frame.index)).astype(str)
    paths = frame.get("Path", pd.Series("", index=frame.index)).astype(str)
    formulas = frame.get("Formula", pd.Series("", index=frame.index)).astype(str)

    normalized_name = names.map(_normalize_text)
    normalized_path = paths.map(_normalize_text)
    formula_signature = formulas.map(_formula_signature)

    expected_formulas = {
        "CO": {"C1O1"},
        "CO2": {"C1O2"},
        "CH3OH": {"C1H4O1"},
        "H2": {"H2"},
        "H2O": {"H2O1"},
        "NH3": {"H3N1"},
    }[label]
    expected_names = {
        "CO": {"CO", "GASPHASES-CO", "GASPHASE-CO"},
        "CO2": {"CO2", "GASPHASES-CO2", "GASPHASE-CO2"},
        "CH3OH": {"CH3OH", "METHANOL", "GASPHASES-CH3OH", "GASPHASE-CH3OH"},
        "H2": {"H2", "GASPHASES-H2", "GASPHASE-H2"},
        "H2O": {"H2O", "WATER", "GASPHASES-H2O", "GASPHASE-H2O"},
        "NH3": {"NH3", "AMMONIA", "GASPHASES-NH3", "GASPHASE-NH3"},
    }[label]

    exact_name = normalized_name.isin(expected_names)
    gas_path = normalized_path.str.contains(
        r"(?:^|[/_ -])(?:gas|gasphase|gasphases|molecule|molecules|reference|refs)(?:[/_ -]|$)",
        regex=True,
    )
    exact_formula = formula_signature.isin(expected_formulas)
    mask = exact_name | (exact_formula & gas_path)
    cols = [column for column in ["dataset_label", "dataset", "Name", "Formula", "E", "Path", "source_hdf", "source_row"] if column in frame.columns]
    return frame.loc[mask, cols].sort_values("E").head(20).copy()


def _find_gas_candidates_with_polars(source: pd.DataFrame, label: str) -> pd.DataFrame | None:
    pl = get_polars()
    required = ["Name", "Formula", "E", "Path"]
    if pl is None or any(column not in source.columns for column in required):
        return None
    if not dataframe_is_polars_safe(source, required):
        return None

    prepared = pd.DataFrame({"__rowid__": range(len(source))}, index=source.index)
    prepared["Name"] = source["Name"].astype("string")
    prepared["Formula"] = source["Formula"].astype("string")
    prepared["Path"] = source["Path"].astype("string")
    prepared["E"] = pd.to_numeric(source["E"], errors="coerce")
    optional_columns = [
        column for column in ["dataset_label", "dataset", "source_hdf", "source_row"]
        if column in source.columns
    ]
    for column in optional_columns:
        prepared[column] = source[column]

    try:
        frame = pl.from_pandas(prepared, include_index=False)
    except Exception:
        return None

    expected_formulas = {
        "CO": {"C1O1"},
        "CO2": {"C1O2"},
        "CH3OH": {"C1H4O1"},
        "H2": {"H2"},
        "H2O": {"H2O1"},
        "NH3": {"H3N1"},
    }[label]
    expected_names = {
        "CO": {"CO", "GASPHASES-CO", "GASPHASE-CO"},
        "CO2": {"CO2", "GASPHASES-CO2", "GASPHASE-CO2"},
        "CH3OH": {"CH3OH", "METHANOL", "GASPHASES-CH3OH", "GASPHASE-CH3OH"},
        "H2": {"H2", "GASPHASES-H2", "GASPHASE-H2"},
        "H2O": {"H2O", "WATER", "GASPHASES-H2O", "GASPHASE-H2O"},
        "NH3": {"NH3", "AMMONIA", "GASPHASES-NH3", "GASPHASE-NH3"},
    }[label]
    cols = [column for column in ["dataset_label", "dataset", "Name", "Formula", "E", "Path", "source_hdf", "source_row"] if column in prepared.columns]

    try:
        normalized_name = pl.col("Name").str.to_uppercase().str.replace_all(" ", "").str.replace_all("_", "-")
        normalized_path = pl.col("Path").str.to_uppercase().str.replace_all(" ", "").str.replace_all("_", "-")
        formula_signature = pl.col("Formula").map_elements(_formula_signature, return_dtype=pl.String)
        result = (
            frame
            .filter(pl.col("E").is_not_null() & (pl.col("E") != 0))
            .with_columns(
                [
                    normalized_name.alias("__normalized_name"),
                    normalized_path.alias("__normalized_path"),
                    formula_signature.alias("__formula_signature"),
                ]
            )
            .filter(
                pl.col("__normalized_name").is_in(list(expected_names))
                | (
                    pl.col("__formula_signature").is_in(list(expected_formulas))
                    & pl.col("__normalized_path").str.contains(
                        r"(?:^|[/_ -])(?:gas|gasphase|gasphases|molecule|molecules|reference|refs)(?:[/_ -]|$)"
                    )
                )
            )
            .sort("E")
            .select(cols)
            .head(20)
            .to_pandas()
        )
    except Exception:
        return None
    return result.copy()


def _formula_signature(value: Any) -> str:
    counts = _formula_counts(value)
    if not counts:
        return ""
    return "".join(f"{element}{counts[element]}" for element in sorted(counts))


def _formula_counts(value: Any) -> dict[str, int]:
    if value is None:
        return {}
    counts: dict[str, int] = {}
    for element, number in __import__("re").findall(r"([A-Z][a-z]?)(\d*)", str(value)):
        counts[element] = counts.get(element, 0) + int(number or 1)
    return counts


def _normalize_text(value: Any) -> str:
    return str(value or "").upper().replace(" ", "").replace("_", "-")


def _source_id(label: str, path: str, sources: dict[str, Any]) -> str:
    stem = Path(label).stem or "hdf"
    base = "".join(character if character.isalnum() else "_" for character in stem).strip("_")
    candidate = base or "hdf"
    counter = 2
    while candidate in sources:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _friendly_hdf_read_error(path: Path, *, key: str, error: Exception) -> str:
    message = str(error)
    text = message.lower()
    if "no module named 'sympy'" in text:
        return (
            f"Could not load HDF file '{path}' because the current Python environment is missing "
            "the optional dependency 'sympy'. Reinstall or repair the active OnePiece environment "
            "with `pip install onepiece` or `pip install onepiece-studio` and try again."
        )
    if "import pytables" in text or "no module named 'tables'" in text or "pytables" in text:
        return (
            f"Could not load HDF file '{path}' because PyTables is unavailable in the current "
            "Python environment. Install or repair the environment with "
            "`pip install onepiece`, `pip install onepiece-studio`, or `pip install tables` and try again."
        )
    if "no object named" in text:
        available = _hdf_keys(path)
        hint = f" Available keys: {', '.join(available)}." if available else ""
        return (
            f"Could not load HDF file '{path}' with key '{key}'. The file exists, but the requested "
            f"HDF key was not found.{hint} Check the stored key name, usually `df`."
        )
    if "numpy._core" in text:
        return (
            f"Could not load HDF file '{path}' with key '{key}' because it appears to contain "
            "legacy NumPy-pickled objects from an older environment. The current compatibility "
            "reader could not reconstruct them automatically."
        )
    return f"Could not load HDF file '{path}' with key '{key}': {message}"


def _hdf_keys(path: Path) -> list[str]:
    """Best-effort list of keys in a pandas HDF store, for error messages."""
    try:
        with pd.HDFStore(str(path), mode="r") as store:
            return [key.lstrip("/") for key in store.keys()]
    except Exception:
        return []
