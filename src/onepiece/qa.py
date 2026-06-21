from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

import pandas as pd

from onepiece.adsorption import add_catalysis_hub_adsorption_energies
from onepiece.provenance import validate_provenance_payload
from onepiece.storage import load_dataset


@dataclass(frozen=True, slots=True)
class SelfTestResult:
    name: str
    passed: bool
    details: dict[str, Any]


def bundled_catalysis_hub_dataset() -> Path:
    """Return the path to the bundled Catalysis-Hub CO2 tutorial dataset.

    The dataset ships inside the package, so it is always available — use it
    to try the adsorption workflow before pointing OnePiece at your own data.

    Examples
    --------
    >>> import onepiece
    >>> path = onepiece.bundled_catalysis_hub_dataset()
    >>> path.name
    'catalysis_hub_co2_subset.hdf'
    >>> frame = onepiece.read_hdf_path(path, key="df")
    >>> len(frame)
    133
    """
    resource = files("onepiece.data").joinpath("catalysis_hub_co2_subset.hdf")
    with as_file(resource) as local_path:
        return Path(local_path)


def run_catalysis_hub_self_test(dataset_path: str | Path | None = None) -> SelfTestResult:
    path = Path(dataset_path) if dataset_path is not None else bundled_catalysis_hub_dataset()
    frame = pd.read_hdf(path, key="df").copy()
    analysed = add_catalysis_hub_adsorption_energies(frame)

    adsorption_rows = analysed.loc[
        analysed.get("cathub_system_kind", pd.Series(index=analysed.index, dtype=object)).astype(str).eq("adsorbate")
    ].copy()
    computed = adsorption_rows.loc[pd.to_numeric(adsorption_rows.get("adsorption_energy"), errors="coerce").notna()].copy()

    max_abs_delta = None
    if "adsorption_energy_delta_vs_reactionEnergy" in analysed.columns:
        deltas = pd.to_numeric(analysed["adsorption_energy_delta_vs_reactionEnergy"], errors="coerce").dropna()
        if not deltas.empty:
            max_abs_delta = float(deltas.abs().max())

    passed = (
        len(frame) > 0
        and len(adsorption_rows) > 0
        and len(computed) > 0
        and (max_abs_delta is not None and max_abs_delta < 1e-8)
    )

    details = {
        "dataset_path": str(path),
        "rows": int(len(frame)),
        "adsorbate_rows": int(len(adsorption_rows)),
        "computed_adsorption_rows": int(len(computed)),
        "max_abs_delta_vs_reaction_energy_ev": max_abs_delta,
        "surface_count": int(analysed.get("surfaceComposition", pd.Series(dtype=object)).astype(str).nunique()),
    }
    return SelfTestResult(name="catalysis-hub", passed=passed, details=details)


def run_fair_provenance_audit(
    dataset_path: str | Path,
    *,
    require_reference_scheme: bool = False,
    require_publication_metadata: bool = False,
) -> SelfTestResult:
    """Audit whether a saved dataset carries reusable FAIR provenance metadata."""

    path = Path(dataset_path).expanduser()
    details: dict[str, Any] = {
        "dataset_path": str(path),
        "require_reference_scheme": bool(require_reference_scheme),
        "require_publication_metadata": bool(require_publication_metadata),
    }
    try:
        frame, manifest = load_dataset(path)
    except Exception as exc:
        return SelfTestResult(
            name="fair-provenance",
            passed=False,
            details={**details, "error": str(exc)},
        )

    details["rows"] = int(len(frame))
    details["columns"] = int(frame.shape[1])
    details["manifest_present"] = manifest is not None
    if manifest is None:
        return SelfTestResult(
            name="fair-provenance",
            passed=False,
            details={
                **details,
                "errors": ["Dataset has no OnePiece manifest; save it with save_dataset(...) first."],
                "warnings": [],
            },
        )

    details["dataset_id"] = manifest.dataset_id
    details["storage_format"] = manifest.storage_format
    details["source_path"] = manifest.source_path
    details["object_columns"] = list(manifest.object_columns)
    validation = validate_provenance_payload(
        manifest.provenance,
        require_reference_scheme=require_reference_scheme,
    )
    errors = list(validation.errors)
    warnings = list(validation.warnings)
    metadata = dict(manifest.metadata)
    details["metadata_keys"] = sorted(str(key) for key in metadata)
    if require_publication_metadata:
        required_metadata = ("license", "citation")
        missing_metadata = [key for key in required_metadata if not metadata.get(key)]
        if missing_metadata:
            errors.append(
                "Publication metadata is missing required manifest.metadata keys: "
                + ", ".join(missing_metadata)
                + "."
            )
        recommended_metadata = ("creators", "description", "doi")
        missing_recommended = [key for key in recommended_metadata if not metadata.get(key)]
        if missing_recommended:
            warnings.append(
                "Publication metadata should also include: "
                + ", ".join(missing_recommended)
                + "."
            )
    details["errors"] = errors
    details["warnings"] = warnings
    details["provenance_entities"] = len(manifest.provenance.get("entities", []))
    details["provenance_activities"] = len(manifest.provenance.get("activities", []))
    details["provenance_agents"] = len(manifest.provenance.get("agents", []))
    return SelfTestResult(name="fair-provenance", passed=not errors, details=details)


def format_self_test_result(result: SelfTestResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    lines = [f"[{status}] {result.name} self-test"]
    for key, value in result.details.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)
