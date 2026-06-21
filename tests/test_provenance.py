from __future__ import annotations

from pathlib import Path

from onepiece.provenance import (
    ReferenceScheme,
    attach_workflow_audit_log,
    build_dataset_provenance,
    entity_from_path,
    file_checksum,
    provenance_graph,
    ro_crate_metadata,
    validate_provenance_payload,
)


def test_file_checksum_and_entity_from_path(tmp_path: Path) -> None:
    source = tmp_path / "OUTCAR"
    source.write_text("energy = -1.23\n")

    checksum = file_checksum(source)
    entity = entity_from_path(source, kind="vasp_output")

    assert checksum.startswith("sha256:")
    assert entity.kind == "vasp_output"
    assert entity.checksum == checksum
    assert entity.path == str(source)


def test_build_dataset_provenance_records_source_activity_and_fair_metadata(tmp_path: Path) -> None:
    source = tmp_path / "created_frame.hdf"
    source.write_text("fake hdf content")

    record = build_dataset_provenance(
        dataset_id="cuvo-oer",
        source_path=source,
        parameters={"reference_scheme": "CHE_H2_H2O"},
        software_version="1.0.0",
    )
    payload = record.to_dict()

    assert payload["schema_version"] == 1
    assert payload["entities"][0]["kind"] == "source_dataset"
    assert payload["activities"][0]["inputs"] == [str(source)]
    assert payload["activities"][0]["parameters"]["reference_scheme"] == "CHE_H2_H2O"
    assert payload["fair"]["reusable"]
    assert any(agent["identifier"] == "onepiece/1.0.0" for agent in payload["agents"])


def test_reference_scheme_serializes_computational_hydrogen_electrode() -> None:
    scheme = ReferenceScheme.computational_hydrogen_electrode(
        h2_eV=-6.77,
        h2o_eV=-14.22,
        potential_V_RHE=1.23,
        pH=14,
        corrections_eV={"OH_solvation": -0.3, "OOH_solvation": -0.35},
        metadata={"surface_family": "MnVO"},
    )

    payload = scheme.to_dict()

    assert payload["name"] == "CHE_H2_H2O"
    assert payload["type"] == "computational_hydrogen_electrode"
    assert payload["gas_references_eV"]["H2"] == -6.77
    assert payload["electrochemical_terms"]["potential_V_RHE"] == 1.23
    assert payload["electrochemical_terms"]["pH"] == 14.0
    assert payload["corrections_eV"]["OOH_solvation"] == -0.35
    assert payload["metadata"]["surface_family"] == "MnVO"


def test_build_dataset_provenance_embeds_reference_scheme_object() -> None:
    scheme = ReferenceScheme.gas_phase(
        name="CO2_H2_H2O_CH3OH",
        gas_references_eV={"CO2": -22.1, "H2": -6.8, "H2O": -14.2, "CH3OH": -29.5},
        temperature_K=523.15,
        pressure_bar={"CO2": 30, "H2": 90},
    )

    record = build_dataset_provenance(dataset_id="cu-zno-methanol", reference_scheme=scheme)
    parameters = record.to_dict()["activities"][0]["parameters"]

    assert parameters["reference_scheme"]["type"] == "gas_phase_thermochemistry"
    assert parameters["reference_scheme"]["temperature_K"] == 523.15
    assert parameters["reference_scheme"]["pressure_bar"]["H2"] == 90.0


def test_validate_provenance_payload_passes_for_reference_bearing_record(tmp_path: Path) -> None:
    source = tmp_path / "created_frame.hdf"
    source.write_text("fake hdf content")
    scheme = ReferenceScheme.computational_hydrogen_electrode(h2_eV=-6.77, h2o_eV=-14.22)
    record = build_dataset_provenance(
        dataset_id="mnvo-oer",
        source_path=source,
        software_version="1.0.0",
        reference_scheme=scheme,
    )

    result = validate_provenance_payload(record, require_reference_scheme=True)

    assert result.passed is True
    assert result.errors == []


def test_validate_provenance_payload_requires_reference_scheme_when_requested() -> None:
    record = build_dataset_provenance(dataset_id="generic-dataset")

    result = validate_provenance_payload(record, require_reference_scheme=True)

    assert result.passed is False
    assert "reference_scheme" in result.errors[0]


def test_provenance_graph_exports_used_and_generated_edges(tmp_path: Path) -> None:
    source = tmp_path / "created_frame.hdf"
    source.write_text("fake hdf content")
    record = build_dataset_provenance(dataset_id="cuvo-oer", source_path=source)

    graph = provenance_graph(record)

    assert any(node["node_type"] == "entity" and node["id"] == str(source) for node in graph["nodes"])
    assert any(edge["source"] == str(source) and edge["relation"] == "used" for edge in graph["edges"])
    assert any(edge["target"] == "onepiece:cuvo-oer" and edge["relation"] == "generated" for edge in graph["edges"])


def test_attach_workflow_audit_log_adds_dataframe_entities_and_activities() -> None:
    record = build_dataset_provenance(dataset_id="derived")
    payload = attach_workflow_audit_log(
        record,
        [
            {
                "id": "workflow-step:1:derive_scalar",
                "kind": "derive_scalar",
                "inputs": ["dataframe:step-0"],
                "outputs": ["dataframe:step-1"],
                "parameters": {"new_column": "E_shifted"},
            }
        ],
    )

    assert payload["activities"][1]["kind"] == "derive_scalar"
    assert any(entity["id"] == "dataframe:step-0" for entity in payload["entities"])
    assert any(entity["id"] == "dataframe:step-1" for entity in payload["entities"])


def test_ro_crate_metadata_exports_entities_activities_and_agents(tmp_path: Path) -> None:
    source = tmp_path / "created_frame.hdf"
    source.write_text("fake hdf content")
    record = build_dataset_provenance(
        dataset_id="cuvo-oer",
        source_path=source,
        software_version="1.0.0",
    )

    crate = ro_crate_metadata(record, name="CuVO OER dataset")
    graph = crate["@graph"]

    assert crate["@context"] == "https://w3id.org/ro/crate/1.1/context"
    assert any(item["@id"] == "./" and item["name"] == "CuVO OER dataset" for item in graph)
    assert any(item["@id"] == str(source) and item["@type"] == "File" and item["sha256"] for item in graph)
    assert any(item["@type"] == "CreateAction" and item["onepiece:kind"] == "save_dataset" for item in graph)
    assert any(item["@type"] == "SoftwareApplication" and item["@id"] == "onepiece/1.0.0" for item in graph)
