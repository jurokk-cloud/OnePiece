from __future__ import annotations

import hashlib
import json
import os
import pickle  # nosec B403
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype

from onepiece.frame_utils import ensure_name_index
from onepiece.provenance import ReferenceScheme, attach_workflow_audit_log, build_dataset_provenance

STORAGE_MANIFEST_NAME = "manifest.json"
STORAGE_SCHEMA_VERSION = 1
ROW_ID_COLUMN = "__onepiece_rowid__"


@dataclass(frozen=True, slots=True)
class StorageConfig:
    root: Path
    source_dir: Path
    workspace_dir: Path
    cache_dir: Path
    exports_dir: Path


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_id: str
    schema_version: int
    storage_format: str
    primary_key: str
    table_file: str
    object_file: str | None
    source_path: str | None
    created_at: str
    rows: int
    columns: list[str]
    object_columns: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)


def resolve_storage_config(root: str | Path | None = None) -> StorageConfig:
    configured = root or os.environ.get("ONEPIECE_HOME") or ".onepiece"
    base = Path(configured).expanduser()
    return StorageConfig(
        root=base,
        source_dir=base / "source",
        workspace_dir=base / "workspace",
        cache_dir=base / "cache",
        exports_dir=base / "exports",
    )


def ensure_storage_layout(config: StorageConfig) -> StorageConfig:
    for path in (config.root, config.source_dir, config.workspace_dir, config.cache_dir, config.exports_dir):
        path.mkdir(parents=True, exist_ok=True)
    return config


def dataset_directory(config: StorageConfig, dataset_id: str, *, area: str = "workspace") -> Path:
    base = {
        "source": config.source_dir,
        "workspace": config.workspace_dir,
        "cache": config.cache_dir,
        "exports": config.exports_dir,
    }[area]
    return base / _slugify_dataset_id(dataset_id)


def dataset_manifest_path(config: StorageConfig, dataset_id: str, *, area: str = "workspace") -> Path:
    return dataset_directory(config, dataset_id, area=area) / STORAGE_MANIFEST_NAME


def save_dataset(
    frame: pd.DataFrame,
    *,
    dataset_id: str,
    config: StorageConfig,
    storage_format: str = "parquet",
    area: str = "workspace",
    source_path: str | None = None,
    metadata: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    reference_scheme: ReferenceScheme | dict[str, Any] | None = None,
    workflow_audit_log: list[dict[str, Any]] | None = None,
) -> Path:
    """Persist a dataframe as a managed dataset and return its manifest path.

    The dataset is written under ``config``'s directory layout as parquet
    (default) or HDF, together with a ``manifest.json`` describing the schema.
    Columns holding Python objects (for example ASE ``Atoms``) go to a pickle
    sidecar so the tabular file stays portable.

    Examples
    --------
    >>> import tempfile
    >>> import pandas as pd
    >>> import onepiece
    >>> from onepiece.storage import resolve_storage_config
    >>> frame = pd.DataFrame({"Name": ["Cu211", "Cu211-CO"], "E": [-100.0, -115.2]})
    >>> config = resolve_storage_config(tempfile.mkdtemp())
    >>> manifest_path = onepiece.save_dataset(frame, dataset_id="demo", config=config)
    >>> manifest_path.name
    'manifest.json'
    """
    ensure_storage_layout(config)
    dataset_dir = dataset_directory(config, dataset_id, area=area)
    dataset_dir.mkdir(parents=True, exist_ok=True)

    normalized = ensure_name_index(frame)
    prepared = normalized.copy()
    prepared[ROW_ID_COLUMN] = range(len(prepared))
    object_columns = _object_sidecar_columns(normalized)
    manifest: DatasetManifest
    provenance_payload = provenance or build_dataset_provenance(
        dataset_id=dataset_id,
        source_path=source_path,
        operation="save_dataset",
        parameters={
            "storage_format": storage_format.lower(),
            "area": area,
            "rows": int(len(normalized)),
            "columns": [str(column) for column in normalized.columns],
            "object_columns": object_columns,
        },
        software_version=_onepiece_version(),
        reference_scheme=reference_scheme,
    ).to_dict()
    provenance_payload = attach_workflow_audit_log(provenance_payload, workflow_audit_log)

    if storage_format.lower() == "parquet":
        table_file = "table.parquet"
        object_file = "object_columns.pkl" if object_columns else None
        tabular = prepared.drop(columns=object_columns, errors="ignore")
        tabular.to_parquet(dataset_dir / table_file, index=False)
        if object_columns:
            with (dataset_dir / object_file).open("wb") as handle:
                # Trusted internal sidecar data for non-tabular columns.
                pickle.dump(  # nosec B301
                    prepared[[ROW_ID_COLUMN, "Name", *object_columns]],
                    handle,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
        manifest = DatasetManifest(
            dataset_id=dataset_id,
            schema_version=STORAGE_SCHEMA_VERSION,
            storage_format="parquet",
            primary_key="Name",
            table_file=table_file,
            object_file=object_file,
            source_path=source_path,
            created_at=_now_iso(),
            rows=int(len(normalized)),
            columns=[str(column) for column in normalized.columns],
            object_columns=object_columns,
            metadata=metadata or {},
            provenance=provenance_payload,
        )
    elif storage_format.lower() == "hdf":
        table_file = "table.hdf"
        prepared.drop(columns=[ROW_ID_COLUMN], errors="ignore").to_hdf(dataset_dir / table_file, key="df", mode="w")
        manifest = DatasetManifest(
            dataset_id=dataset_id,
            schema_version=STORAGE_SCHEMA_VERSION,
            storage_format="hdf",
            primary_key="Name",
            table_file=table_file,
            object_file=None,
            source_path=source_path,
            created_at=_now_iso(),
            rows=int(len(normalized)),
            columns=[str(column) for column in normalized.columns],
            object_columns=[],
            metadata=metadata or {},
            provenance=provenance_payload,
        )
    else:
        raise ValueError(f"Unsupported storage_format: {storage_format}")

    manifest_path = dataset_dir / STORAGE_MANIFEST_NAME
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True))
    return manifest_path


def load_dataset(path: str | Path) -> tuple[pd.DataFrame, DatasetManifest | None]:
    """Load a dataset saved by :func:`save_dataset`, or a bare data file.

    Accepts a managed dataset directory (or its ``manifest.json``), a parquet
    file, or a pandas HDF file. The manifest is ``None`` when loading a bare
    file. The returned frame always has a ``Name`` index.

    Examples
    --------
    >>> import tempfile
    >>> import pandas as pd
    >>> import onepiece
    >>> from onepiece.storage import resolve_storage_config
    >>> config = resolve_storage_config(tempfile.mkdtemp())
    >>> manifest_path = onepiece.save_dataset(
    ...     pd.DataFrame({"Name": ["Cu211", "Cu211-CO"], "E": [-100.0, -115.2]}),
    ...     dataset_id="demo",
    ...     config=config,
    ... )
    >>> frame, manifest = onepiece.load_dataset(manifest_path.parent)
    >>> list(frame.index)
    ['Cu211', 'Cu211-CO']
    >>> manifest.storage_format
    'parquet'
    """
    source = Path(path).expanduser()
    if source.is_dir():
        manifest_path = source / STORAGE_MANIFEST_NAME
        if manifest_path.exists():
            manifest = read_dataset_manifest(manifest_path)
            return _load_manifest_dataset(manifest_path.parent, manifest), manifest
        raise FileNotFoundError(f"No dataset manifest found in {source}")

    if source.name == STORAGE_MANIFEST_NAME:
        manifest = read_dataset_manifest(source)
        return _load_manifest_dataset(source.parent, manifest), manifest

    suffix = source.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return ensure_name_index(pd.read_parquet(source)), None
    if suffix in {".hdf", ".h5"}:
        return ensure_name_index(pd.read_hdf(source, key="df")), None
    raise ValueError(f"Unsupported dataset path: {source}")


def read_dataset_manifest(path: str | Path) -> DatasetManifest:
    payload = json.loads(Path(path).read_text())
    return DatasetManifest(**payload)


def detect_storage_format(path: str | Path) -> str:
    source = Path(path).expanduser()
    if source.is_dir() and (source / STORAGE_MANIFEST_NAME).exists():
        manifest = read_dataset_manifest(source / STORAGE_MANIFEST_NAME)
        return manifest.storage_format
    if source.name == STORAGE_MANIFEST_NAME:
        return read_dataset_manifest(source).storage_format
    suffix = source.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return "parquet"
    if suffix in {".hdf", ".h5"}:
        return "hdf"
    return "unknown"


def cache_key_for_paths(*paths: Path | str) -> str:
    digest = hashlib.sha256()
    for value in paths:
        path = Path(value).expanduser()
        digest.update(str(path).encode("utf-8"))
        if path.exists():
            stat = path.stat()
            digest.update(str(stat.st_size).encode("utf-8"))
            digest.update(str(stat.st_mtime_ns).encode("utf-8"))
        else:
            digest.update(b"missing")
    return digest.hexdigest()


def write_cache_payload(path: str | Path, payload: Any) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        # Trusted local cache payload written by OnePiece.
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)  # nosec B301
    return target


def read_cache_payload(path: str | Path) -> Any:
    with Path(path).expanduser().open("rb") as handle:
        # Trusted local cache payload written by OnePiece.
        return pickle.load(handle)  # nosec B301


def _load_manifest_dataset(dataset_dir: Path, manifest: DatasetManifest) -> pd.DataFrame:
    if manifest.storage_format == "parquet":
        table = pd.read_parquet(dataset_dir / manifest.table_file)
        if manifest.object_file:
            # Trusted local sidecar generated by OnePiece.
            object_frame = pd.read_pickle(  # nosec B301
                dataset_dir / manifest.object_file
            ).reset_index(drop=True)
            table = table.merge(object_frame, on=[ROW_ID_COLUMN, "Name"], how="left")
        ordered = table.drop(columns=[ROW_ID_COLUMN], errors="ignore").reindex(columns=manifest.columns)
        return ensure_name_index(ordered)
    if manifest.storage_format == "hdf":
        return ensure_name_index(pd.read_hdf(dataset_dir / manifest.table_file, key="df"))
    raise ValueError(f"Unsupported manifest storage format: {manifest.storage_format}")


def _object_sidecar_columns(frame: pd.DataFrame) -> list[str]:
    object_columns: list[str] = []
    for column in frame.columns:
        if column == "Name":
            continue
        series = frame[column]
        if is_numeric_dtype(series) or is_bool_dtype(series) or is_datetime64_any_dtype(series):
            continue
        if series.dtype != "object":
            continue
        sample = next((value for value in series if value is not None and not _is_nan_like(value)), None)
        if sample is None:
            continue
        if _is_simple_scalar(sample):
            continue
        object_columns.append(str(column))
    return object_columns


def _is_simple_scalar(value: Any) -> bool:
    if isinstance(value, str | bytes | int | float | bool):
        return True
    return value.__class__.__name__ in {"Timestamp"}


def _is_nan_like(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _slugify_dataset_id(value: str) -> str:
    text = str(value).strip()
    cleaned = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in text)
    return cleaned.strip("_") or "dataset"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _onepiece_version() -> str | None:
    try:
        from onepiece import __version__
    except Exception:
        return None
    return str(__version__)
