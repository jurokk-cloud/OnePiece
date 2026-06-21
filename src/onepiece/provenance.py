from __future__ import annotations

import hashlib
import platform
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROVENANCE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ReferenceScheme:
    """Thermodynamic reference convention used to interpret derived energies.

    .. code-block:: python

        from onepiece import ReferenceScheme

        scheme = ReferenceScheme(name="RHE", scheme_type="electrochemical")
    """

    name: str
    scheme_type: str
    gas_references_eV: dict[str, float] = field(default_factory=dict)
    electrochemical_terms: dict[str, float] = field(default_factory=dict)
    corrections_eV: dict[str, float] = field(default_factory=dict)
    temperature_K: float | None = None
    pressure_bar: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["type"] = payload.pop("scheme_type")
        return {key: value for key, value in payload.items() if value not in ({}, None)}

    @classmethod
    def computational_hydrogen_electrode(
        cls,
        *,
        name: str = "CHE_H2_H2O",
        h2_eV: float | None = None,
        h2o_eV: float | None = None,
        potential_V_RHE: float | None = None,
        pH: float | None = None,
        corrections_eV: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReferenceScheme:
        gas_references = {}
        if h2_eV is not None:
            gas_references["H2"] = float(h2_eV)
        if h2o_eV is not None:
            gas_references["H2O"] = float(h2o_eV)
        electrochemical_terms = {}
        if potential_V_RHE is not None:
            electrochemical_terms["potential_V_RHE"] = float(potential_V_RHE)
        if pH is not None:
            electrochemical_terms["pH"] = float(pH)
        return cls(
            name=name,
            scheme_type="computational_hydrogen_electrode",
            gas_references_eV=gas_references,
            electrochemical_terms=electrochemical_terms,
            corrections_eV=corrections_eV or {},
            metadata=metadata or {},
        )

    @classmethod
    def gas_phase(
        cls,
        *,
        name: str,
        gas_references_eV: dict[str, float],
        temperature_K: float | None = None,
        pressure_bar: dict[str, float] | None = None,
        corrections_eV: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReferenceScheme:
        return cls(
            name=name,
            scheme_type="gas_phase_thermochemistry",
            gas_references_eV={str(key): float(value) for key, value in gas_references_eV.items()},
            temperature_K=None if temperature_K is None else float(temperature_K),
            pressure_bar={str(key): float(value) for key, value in (pressure_bar or {}).items()},
            corrections_eV=corrections_eV or {},
            metadata=metadata or {},
        )


@dataclass(frozen=True, slots=True)
class ProvenanceAgent:
    """Person, group, program, or service responsible for a provenance action."""

    name: str
    role: str = "software"
    identifier: str | None = None


@dataclass(frozen=True, slots=True)
class ProvenanceEntity:
    """Dataset, file, calculation, or derived table used in a provenance graph."""

    id: str
    kind: str
    path: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProvenanceActivity:
    """One transformation step in an AiiDA-like provenance chain."""

    id: str
    kind: str
    label: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    ended_at: str | None = None
    agent: str | None = None


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Portable provenance payload stored with a OnePiece dataset manifest.

    The shape is intentionally JSON-native so it can be written into
    ``manifest.json`` and translated later to PROV-O, RO-Crate, NOMAD metadata,
    or an AiiDA export boundary.
    """

    schema_version: int
    entities: list[ProvenanceEntity] = field(default_factory=list)
    activities: list[ProvenanceActivity] = field(default_factory=list)
    agents: list[ProvenanceAgent] = field(default_factory=list)
    fair: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProvenanceValidationResult:
    """Validation summary for a OnePiece provenance payload."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_checksum(path: str | Path, *, algorithm: str = "sha256", chunk_size: int = 1024 * 1024) -> str:
    """Return a stable checksum for a local file.

    Checksums make datasets findable and reusable because a later reader can
    verify that an HDF, parquet table, OUTCAR, CHGCAR, or derived report is the
    same byte sequence that the manifest describes.
    """

    digest = hashlib.new(algorithm)
    with Path(path).expanduser().open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return f"{algorithm}:{digest.hexdigest()}"


def entity_from_path(
    path: str | Path,
    *,
    kind: str = "file",
    entity_id: str | None = None,
    checksum: bool = True,
    metadata: dict[str, Any] | None = None,
) -> ProvenanceEntity:
    source = Path(path).expanduser()
    return ProvenanceEntity(
        id=entity_id or str(source),
        kind=kind,
        path=str(source),
        checksum=file_checksum(source) if checksum and source.is_file() else None,
        metadata=metadata or {},
    )


def onepiece_agent(*, version: str | None = None) -> ProvenanceAgent:
    identifier = f"onepiece/{version}" if version else "onepiece"
    return ProvenanceAgent(name="OnePiece", role="software", identifier=identifier)


def local_python_agent() -> ProvenanceAgent:
    return ProvenanceAgent(
        name="Python",
        role="runtime",
        identifier=f"{platform.python_implementation()} {platform.python_version()}",
    )


def build_dataset_provenance(
    *,
    dataset_id: str,
    source_path: str | Path | None = None,
    operation: str = "save_dataset",
    parameters: dict[str, Any] | None = None,
    outputs: list[ProvenanceEntity] | None = None,
    software_version: str | None = None,
    reference_scheme: ReferenceScheme | dict[str, Any] | None = None,
    fair: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> ProvenanceRecord:
    """Create a minimal FAIR/provenance record for a saved dataset.

    This does not try to replace AiiDA's full node graph. It gives OnePiece a
    local, lightweight provenance contract: entities, activities, agents, and
    enough FAIR metadata to make later export or audit possible.

    .. code-block:: python

        from onepiece import build_dataset_provenance

        record = build_dataset_provenance(dataset_id="cu-ga-surfaces")
    """

    entities: list[ProvenanceEntity] = []
    input_ids: list[str] = []
    if source_path is not None:
        source_entity = entity_from_path(source_path, kind="source_dataset")
        entities.append(source_entity)
        input_ids.append(source_entity.id)

    output_entities = outputs or [
        ProvenanceEntity(
            id=f"onepiece:{dataset_id}",
            kind="managed_dataset",
            metadata={"dataset_id": dataset_id},
        )
    ]
    entities.extend(output_entities)
    output_ids = [entity.id for entity in output_entities]

    activity_parameters = dict(parameters or {})
    if reference_scheme is not None:
        activity_parameters["reference_scheme"] = (
            reference_scheme.to_dict() if isinstance(reference_scheme, ReferenceScheme) else reference_scheme
        )

    software_agent = onepiece_agent(version=software_version)
    activity = ProvenanceActivity(
        id=f"activity:{dataset_id}:{operation}",
        kind=operation,
        label=f"OnePiece {operation}",
        inputs=input_ids,
        outputs=output_ids,
        parameters=activity_parameters,
        started_at=None,
        ended_at=now_utc_iso(),
        agent=software_agent.identifier,
    )

    return ProvenanceRecord(
        schema_version=PROVENANCE_SCHEMA_VERSION,
        entities=entities,
        activities=[activity],
        agents=[software_agent, local_python_agent()],
        fair=fair
        or {
            "findable": ["dataset_id", "manifest.json", "checksums"],
            "accessible": ["local_path", "open_manifest"],
            "interoperable": ["json_manifest", "parquet_or_hdf", "ase_atoms_sidecar"],
            "reusable": ["license", "citation", "workflow_parameters", "provenance_entities"],
        },
        notes=notes or [],
    )


def workflow_activity(
    *,
    step_index: int,
    operation: dict[str, Any],
    input_entity: str,
    output_entity: str,
    status: str,
    rows_before: int,
    rows_after: int | None = None,
    columns_before: list[str] | None = None,
    columns_after: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Return a JSON-native activity record for one dataframe workflow step."""

    kind = str(operation.get("kind", "unknown"))
    label = str(operation.get("label") or kind)
    before_columns = columns_before or []
    after_columns = columns_after or before_columns
    added_columns = [column for column in after_columns if column not in before_columns]
    removed_columns = [column for column in before_columns if column not in after_columns]
    payload: dict[str, Any] = {
        "id": f"workflow-step:{step_index}:{kind}",
        "kind": kind,
        "label": label,
        "status": status,
        "inputs": [input_entity],
        "outputs": [output_entity],
        "parameters": _json_safe_operation(operation),
        "started_at": None,
        "ended_at": now_utc_iso(),
        "agent": "onepiece.workflow",
        "row_count_before": int(rows_before),
        "row_count_after": None if rows_after is None else int(rows_after),
        "column_count_before": len(before_columns),
        "column_count_after": len(after_columns),
        "added_columns": added_columns,
        "removed_columns": removed_columns,
    }
    if error:
        payload["error"] = error
    return payload


def validate_provenance_payload(
    payload: ProvenanceRecord | dict[str, Any],
    *,
    require_reference_scheme: bool = False,
) -> ProvenanceValidationResult:
    """Validate the minimum FAIR/provenance contract for a saved dataset.

    .. code-block:: python

        from onepiece import validate_provenance_payload

        result = validate_provenance_payload(record)
    """

    data = payload.to_dict() if isinstance(payload, ProvenanceRecord) else dict(payload or {})
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PROVENANCE_SCHEMA_VERSION}.")

    entities = _list_field(data, "entities", errors)
    activities = _list_field(data, "activities", errors)
    agents = _list_field(data, "agents", errors)
    fair = data.get("fair")
    if not isinstance(fair, dict) or not fair:
        warnings.append("fair metadata is missing or empty.")

    entity_ids = _validate_entities(entities, errors, warnings)
    agent_ids = _validate_agents(agents, errors)
    _validate_activities(
        activities,
        entity_ids=entity_ids,
        agent_ids=agent_ids,
        require_reference_scheme=require_reference_scheme,
        errors=errors,
        warnings=warnings,
    )

    return ProvenanceValidationResult(passed=not errors, errors=errors, warnings=warnings)


def provenance_graph(payload: ProvenanceRecord | dict[str, Any]) -> dict[str, Any]:
    """Return a compact graph representation of entities, activities, and agents.

    .. code-block:: python

        from onepiece import provenance_graph

        graph = provenance_graph(record)
    """

    data = payload.to_dict() if isinstance(payload, ProvenanceRecord) else dict(payload or {})
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    for entity in data.get("entities", []) or []:
        nodes.append({"id": str(entity.get("id")), "node_type": "entity", **entity})
    for agent in data.get("agents", []) or []:
        agent_id = _agent_id(agent)
        nodes.append({"id": agent_id, "node_type": "agent", **agent})
    for activity in data.get("activities", []) or []:
        activity_id = str(activity.get("id"))
        nodes.append({"id": activity_id, "node_type": "activity", **activity})
        for entity_id in activity.get("inputs", []) or []:
            edges.append({"source": str(entity_id), "target": activity_id, "relation": "used"})
        for entity_id in activity.get("outputs", []) or []:
            edges.append({"source": activity_id, "target": str(entity_id), "relation": "generated"})
        if activity.get("agent"):
            edges.append({"source": str(activity.get("agent")), "target": activity_id, "relation": "wasAssociatedWith"})

    return {
        "schema_version": data.get("schema_version"),
        "nodes": nodes,
        "edges": edges,
    }


def ro_crate_metadata(
    payload: ProvenanceRecord | dict[str, Any],
    *,
    name: str = "OnePiece dataset",
    description: str | None = None,
) -> dict[str, Any]:
    """Return an RO-Crate-style JSON-LD metadata document for provenance.

    .. code-block:: python

        from onepiece import ro_crate_metadata

        crate = ro_crate_metadata(record, name="OnePiece dataset")
    """

    data = payload.to_dict() if isinstance(payload, ProvenanceRecord) else dict(payload or {})
    graph: list[dict[str, Any]] = [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": name,
            "description": description or "OnePiece managed dataset with FAIR provenance metadata.",
            "hasPart": [{"@id": str(entity.get("id"))} for entity in data.get("entities", []) or []],
            "mentions": [{"@id": str(activity.get("id"))} for activity in data.get("activities", []) or []],
        },
    ]

    for entity in data.get("entities", []) or []:
        graph.append(_entity_to_ro_crate(entity))
    for agent in data.get("agents", []) or []:
        graph.append(_agent_to_ro_crate(agent))
    for activity in data.get("activities", []) or []:
        graph.append(_activity_to_ro_crate(activity))

    return {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": graph,
    }


def attach_workflow_audit_log(
    payload: ProvenanceRecord | dict[str, Any],
    audit_log: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Attach workflow activities to a dataset provenance payload."""

    data = payload.to_dict() if isinstance(payload, ProvenanceRecord) else dict(payload or {})
    if not audit_log:
        return data

    entities = list(data.get("entities", []) or [])
    activities = list(data.get("activities", []) or [])
    known_entities = {str(entity.get("id")) for entity in entities if isinstance(entity, dict)}

    for activity in audit_log:
        if not isinstance(activity, dict):
            continue
        activity_copy = _json_safe_value(activity)
        activities.append(activity_copy)
        for entity_id in [*activity_copy.get("inputs", []), *activity_copy.get("outputs", [])]:
            entity_text = str(entity_id)
            if entity_text in known_entities:
                continue
            entities.append(
                {
                    "id": entity_text,
                    "kind": "dataframe",
                    "metadata": {"generated_by": activity_copy.get("id")},
                }
            )
            known_entities.add(entity_text)

    data["entities"] = entities
    data["activities"] = activities
    return data


def _entity_to_ro_crate(entity: dict[str, Any]) -> dict[str, Any]:
    entity_id = str(entity.get("id"))
    item_type = "File" if entity.get("path") else "Dataset"
    item: dict[str, Any] = {
        "@id": entity_id,
        "@type": item_type,
        "name": entity_id,
        "additionalType": entity.get("kind"),
    }
    if entity.get("path"):
        item["contentUrl"] = entity.get("path")
    if entity.get("checksum"):
        item["sha256"] = str(entity.get("checksum")).removeprefix("sha256:")
    if entity.get("metadata"):
        item["onepiece:metadata"] = entity.get("metadata")
    return item


def _agent_to_ro_crate(agent: dict[str, Any]) -> dict[str, Any]:
    agent_id = _agent_id(agent)
    item_type = "SoftwareApplication" if str(agent.get("role", "")).lower() in {"software", "runtime"} else "Organization"
    item: dict[str, Any] = {
        "@id": agent_id,
        "@type": item_type,
        "name": agent.get("name"),
    }
    if agent.get("identifier"):
        item["identifier"] = agent.get("identifier")
    if agent.get("role"):
        item["roleName"] = agent.get("role")
    return item


def _activity_to_ro_crate(activity: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "@id": str(activity.get("id")),
        "@type": "CreateAction",
        "name": activity.get("label") or activity.get("kind"),
        "actionStatus": "CompletedActionStatus" if activity.get("status", "ok") != "failed" else "FailedActionStatus",
        "object": [{"@id": str(entity_id)} for entity_id in activity.get("inputs", []) or []],
        "result": [{"@id": str(entity_id)} for entity_id in activity.get("outputs", []) or []],
        "onepiece:kind": activity.get("kind"),
        "onepiece:parameters": activity.get("parameters", {}),
    }
    if activity.get("agent"):
        item["agent"] = {"@id": str(activity.get("agent"))}
    if activity.get("ended_at"):
        item["endTime"] = activity.get("ended_at")
    if activity.get("error"):
        item["error"] = activity.get("error")
    return item


def _list_field(data: dict[str, Any], key: str, errors: list[str]) -> list[dict[str, Any]]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        errors.append(f"{key} must be a non-empty list.")
        return []
    invalid = [item for item in value if not isinstance(item, dict)]
    if invalid:
        errors.append(f"{key} must contain only dictionaries.")
        return []
    return value


def _validate_entities(
    entities: list[dict[str, Any]],
    errors: list[str],
    warnings: list[str],
) -> set[str]:
    ids: set[str] = set()
    for index, entity in enumerate(entities):
        entity_id = str(entity.get("id") or "")
        if not entity_id:
            errors.append(f"entities[{index}] is missing id.")
            continue
        ids.add(entity_id)
        if not entity.get("kind"):
            errors.append(f"entities[{index}] is missing kind.")
        if entity.get("path") and not entity.get("checksum"):
            warnings.append(f"entities[{index}] has a path but no checksum.")
    return ids


def _validate_agents(agents: list[dict[str, Any]], errors: list[str]) -> set[str]:
    ids: set[str] = set()
    for index, agent in enumerate(agents):
        if not agent.get("name"):
            errors.append(f"agents[{index}] is missing name.")
            continue
        ids.add(_agent_id(agent))
    return ids


def _validate_activities(
    activities: list[dict[str, Any]],
    *,
    entity_ids: set[str],
    agent_ids: set[str],
    require_reference_scheme: bool,
    errors: list[str],
    warnings: list[str],
) -> None:
    has_reference_scheme = False
    for index, activity in enumerate(activities):
        if not activity.get("id"):
            errors.append(f"activities[{index}] is missing id.")
        if not activity.get("kind"):
            errors.append(f"activities[{index}] is missing kind.")
        for entity_id in activity.get("inputs", []) or []:
            if str(entity_id) not in entity_ids:
                warnings.append(f"activities[{index}] input '{entity_id}' is not listed as an entity.")
        for entity_id in activity.get("outputs", []) or []:
            if str(entity_id) not in entity_ids:
                warnings.append(f"activities[{index}] output '{entity_id}' is not listed as an entity.")
        agent = activity.get("agent")
        if agent and str(agent) not in agent_ids:
            warnings.append(f"activities[{index}] agent '{agent}' is not listed as an agent.")
        parameters = activity.get("parameters", {})
        if isinstance(parameters, dict) and parameters.get("reference_scheme"):
            has_reference_scheme = True

    if require_reference_scheme and not has_reference_scheme:
        errors.append("at least one activity must include parameters.reference_scheme.")


def _agent_id(agent: dict[str, Any]) -> str:
    return str(agent.get("identifier") or agent.get("name") or "")


def _json_safe_operation(operation: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _json_safe_value(value) for key, value in operation.items()}


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe_value(item) for item in value]
    return str(value)
