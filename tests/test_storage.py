from __future__ import annotations

from pathlib import Path

import pandas as pd
from ase import Atoms

from onepiece import (
    DatasetManifest,
    detect_storage_format,
    ensure_name_index,
    ensure_storage_layout,
    load_dataset,
    read_dataset_manifest,
    read_dataset_path,
    resolve_storage_config,
    save_dataset,
)
from onepiece.provenance import ReferenceScheme
from onepiece.workflows import apply_operations


def test_save_and_load_dataset_roundtrip_with_parquet_and_object_sidecar(tmp_path: Path) -> None:
    config = ensure_storage_layout(resolve_storage_config(tmp_path / ".onepiece"))
    frame = pd.DataFrame(
        {
            "Name": ["calc-a"],
            "E": [-1.23],
            "Path": ["/tmp/calc-a"],
            "struc": [Atoms("Cu2")],
            "input_kpoints_grid": [(4, 4, 1)],
        }
    )

    manifest_path = save_dataset(frame, dataset_id="cugA-study", config=config, storage_format="parquet")
    loaded, manifest = load_dataset(manifest_path.parent)

    assert manifest_path.exists()
    assert isinstance(manifest, DatasetManifest)
    assert manifest.storage_format == "parquet"
    assert manifest.provenance["schema_version"] == 1
    assert manifest.provenance["activities"][0]["kind"] == "save_dataset"
    assert manifest.provenance["activities"][0]["parameters"]["object_columns"] == ["struc", "input_kpoints_grid"]
    assert detect_storage_format(manifest_path.parent) == "parquet"
    assert loaded.index.name == "Name"
    assert loaded.index.tolist() == ["calc-a"]
    assert loaded.loc["calc-a", "input_kpoints_grid"] == (4, 4, 1)
    assert loaded.loc["calc-a", "struc"].__class__.__name__ == "Atoms"


def test_read_dataset_path_loads_manifest_backed_dataset(tmp_path: Path) -> None:
    config = ensure_storage_layout(resolve_storage_config(tmp_path / ".onepiece"))
    frame = ensure_name_index(pd.DataFrame({"Name": ["row-a"], "E": [1.0]}))
    manifest_path = save_dataset(frame, dataset_id="dataset-a", config=config)

    loaded = read_dataset_path(manifest_path.parent, key="df")

    assert loaded.index.tolist() == ["row-a"]
    assert loaded.loc["row-a", "E"] == 1.0
    reloaded_manifest = read_dataset_manifest(manifest_path)
    assert reloaded_manifest.dataset_id == "dataset-a"
    assert reloaded_manifest.provenance["fair"]["findable"]


def test_save_dataset_accepts_explicit_provenance_payload(tmp_path: Path) -> None:
    config = ensure_storage_layout(resolve_storage_config(tmp_path / ".onepiece"))
    frame = pd.DataFrame({"Name": ["row-a"], "E": [1.0]})
    provenance = {
        "schema_version": 1,
        "entities": [{"id": "raw:hdf", "kind": "source_dataset"}],
        "activities": [{"id": "activity:custom", "kind": "custom_import"}],
        "agents": [{"name": "test-suite", "role": "software"}],
    }

    manifest_path = save_dataset(
        frame,
        dataset_id="custom-provenance",
        config=config,
        provenance=provenance,
    )

    manifest = read_dataset_manifest(manifest_path)
    assert manifest.provenance == provenance


def test_save_dataset_accepts_reference_scheme_for_manifest_provenance(tmp_path: Path) -> None:
    config = ensure_storage_layout(resolve_storage_config(tmp_path / ".onepiece"))
    frame = pd.DataFrame({"Name": ["row-a"], "E": [1.0]})
    scheme = ReferenceScheme.computational_hydrogen_electrode(
        h2_eV=-6.77,
        h2o_eV=-14.22,
        potential_V_RHE=1.23,
        pH=14,
    )

    manifest_path = save_dataset(
        frame,
        dataset_id="mnvo-oer",
        config=config,
        reference_scheme=scheme,
    )

    manifest = read_dataset_manifest(manifest_path)
    reference_scheme = manifest.provenance["activities"][0]["parameters"]["reference_scheme"]
    assert reference_scheme["type"] == "computational_hydrogen_electrode"
    assert reference_scheme["gas_references_eV"]["H2O"] == -14.22
    assert reference_scheme["electrochemical_terms"]["pH"] == 14.0


def test_save_dataset_embeds_workflow_audit_log_in_manifest_provenance(tmp_path: Path) -> None:
    config = ensure_storage_layout(resolve_storage_config(tmp_path / ".onepiece"))
    frame = pd.DataFrame({"Name": ["row-a"], "E": [1.0]})
    workflow = apply_operations(
        frame,
        [
            {
                "kind": "derive_scalar",
                "label": "Shift energy",
                "left": "E",
                "operator": "+",
                "scalar": 0.2,
                "new_column": "E_shifted",
            }
        ],
    )

    manifest_path = save_dataset(
        workflow.dataframe,
        dataset_id="derived-dataset",
        config=config,
        workflow_audit_log=workflow.audit_log,
    )

    manifest = read_dataset_manifest(manifest_path)
    activities = manifest.provenance["activities"]
    assert [activity["kind"] for activity in activities] == ["save_dataset", "derive_scalar"]
    assert activities[1]["added_columns"] == ["E_shifted"]
    assert any(entity["id"] == "dataframe:step-0" for entity in manifest.provenance["entities"])
    assert any(entity["id"] == "dataframe:step-1" for entity in manifest.provenance["entities"])


def test_save_and_load_dataset_preserve_duplicate_names(tmp_path: Path) -> None:
    config = ensure_storage_layout(resolve_storage_config(tmp_path / ".onepiece"))
    frame = pd.DataFrame(
        {
            "Name": ["dup", "dup", "unique"],
            "E": [1.0, 2.0, 3.0],
            "struc": [Atoms("H"), Atoms("He"), Atoms("Li")],
        }
    )

    manifest_path = save_dataset(frame, dataset_id="dups", config=config, storage_format="parquet")
    loaded, _manifest = load_dataset(manifest_path.parent)

    assert len(loaded) == 3
    assert loaded["E"].tolist() == [1.0, 2.0, 3.0]
    assert int(loaded.index.duplicated().sum()) == 1
