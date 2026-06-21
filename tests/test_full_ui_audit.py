from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from ase import Atoms
from onepiece_studio.ui.controlroom import _apply_controlroom_filters
from onepiece_studio.ui.data_management import _build_project_payload, _restore_project_payload
from onepiece_studio.ui.data_sources import (
    _apply_import_options,
    _combined_active_database,
    _detected_gas_reference_values,
    _prepare_source_frame,
)
from onepiece_studio.ui.workbook import EDIT_STATE_KEY, apply_session_edits
from onepiece_studio.ui.workflow_builder import _apply_operation, _workflow_gas_reference_values

from onepiece.automation import apply_curation_rules


class DummyStreamlit:
    def __init__(self, session_state: dict | None = None) -> None:
        self.session_state = session_state or {}
        self.rerun_called = False

    def rerun(self) -> None:
        self.rerun_called = True


def _cu_surface() -> Atoms:
    return Atoms(
        "Cu4",
        positions=[
            (0.0, 0.0, 0.0),
            (1.8, 0.0, 0.0),
            (0.0, 1.8, 0.0),
            (1.8, 1.8, 0.0),
        ],
        cell=[3.6, 3.6, 12.0],
        pbc=[True, True, False],
    )


def _surface_plus(symbols: str, positions: list[tuple[float, float, float]]) -> Atoms:
    base = _cu_surface().copy()
    extra = Atoms(symbols, positions=positions, cell=base.cell, pbc=base.pbc)
    return base + extra


def _full_fixture_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Name": [
                "gasphases-CO",
                "gasphases-CO2",
                "gasphases-H2",
                "gasphases-H2O",
                "gasphases-CH3OH",
                "Cu-211-clean",
                "Cu-211-clean-CO-1",
                "Cu-211-clean-CH3O-1",
                "Cu-211-clean-copt-CO2%COOH-pathA-0",
                "Cu-211-clean-test-broken",
            ],
            "Formula": [
                "CO",
                "CO2",
                "H2",
                "H2O",
                "CH4O",
                "Cu4",
                "Cu4CO",
                "Cu4CH3O",
                "Cu4CO2H",
                "Cu4",
            ],
            "E": [-10.0, -20.0, -6.0, -8.0, -30.0, -100.0, -112.0, -128.0, -119.5, 0.0],
            "fmax": [0.0, 0.0, 0.0, 0.0, 0.0, 0.01, 0.02, 0.03, 0.08, 0.25],
            "Path": [
                "refs/gas/CO",
                "refs/gas/CO2",
                "refs/gas/H2",
                "refs/gas/H2O",
                "refs/gas/CH3OH",
                "/calc/Cu-211-clean",
                "/calc/Cu-211-clean-CO-1",
                "/calc/Cu-211-clean-CH3O-1",
                "/calc/Cu-211-clean-copt-CO2%COOH-pathA-0",
                "/calc/Cu-211-clean-test-broken",
            ],
            "struc": [
                None,
                None,
                None,
                None,
                None,
                _cu_surface(),
                _surface_plus("CO", [(0.9, 0.9, 1.5), (0.9, 0.9, 2.6)]),
                _surface_plus(
                    "CH3O",
                    [
                        (0.9, 0.9, 1.2),
                        (0.9, 0.9, 2.4),
                        (1.6, 0.9, 2.6),
                        (0.2, 0.9, 2.6),
                        (0.9, 1.6, 2.6),
                    ],
                ),
                _surface_plus("CO2H", [(0.9, 0.9, 1.1), (0.9, 0.9, 2.2), (1.7, 0.9, 2.5), (0.2, 0.9, 2.5)]),
                None,
            ],
        }
    )


def test_full_workflow_pipeline_supports_adsorption_reaction_and_descriptors() -> None:
    frame = _full_fixture_frame()

    result = _apply_operation(
        frame,
        {"kind": "derive_adsorption_columns", "gas_references": {"CO": -10.0, "CH3OH": -30.0, "H2": -6.0}},
    )
    result = _apply_operation(
        result,
        {
            "kind": "derive_recipe_adsorption",
            "gas_reference_values": {"CO": -10.0, "H2": -6.0, "H2O": -8.0, "CH3OH": -30.0, "CO2": -20.0},
            "recipes": {
                "CO": {"basis": "C", "gas_refs": {"CO": 1.0}},
                "CH3O": {"basis": "C", "gas_refs": {"CO": 1.0, "H2": 1.5}},
                "OH": {"basis": "O", "gas_refs": {"H2O": 1.0, "H2": -0.5}},
            },
        },
    )
    result = _apply_operation(result, {"kind": "derive_reaction_network"})
    result = _apply_operation(result, {"kind": "derive_structure_descriptors"})

    co_row = result.loc[result["Name"] == "Cu-211-clean-CO-1"].iloc[0]
    copt_row = result.loc[result["Name"] == "Cu-211-clean-copt-CO2%COOH-pathA-0"].iloc[0]
    methoxy_row = result.loc[result["Name"] == "Cu-211-clean-CH3O-1"].iloc[0]

    assert co_row["surface_ref_name"] == "Cu-211-clean"
    assert co_row["E_ads_CO_total_eV"] == -2.0
    assert co_row["E_ads_CO_eV"] == -2.0
    assert methoxy_row["surface_ref_name"] == "Cu-211-clean"
    assert methoxy_row["adsorbate_formula"] == "CH3O"
    assert methoxy_row["adsorbate_atom_count"] == 5.0
    assert copt_row["reaction_step_initial"] == "CO2"
    assert copt_row["reaction_step_final"] == "COOH"
    assert copt_row["reaction_network_role"] == "pathway_image"


def test_source_import_and_project_roundtrip_handle_full_fixture_hdf(tmp_path: Path) -> None:
    frame = _full_fixture_frame()
    hdf_path = tmp_path / "full_fixture.hdf"
    frame.to_hdf(hdf_path, key="df")

    prepared = _apply_import_options(
        pd.read_hdf(hdf_path, key="df"),
        {
            "enable_adsorption_prep": True,
            "name_column": "Name",
            "energy_column": "E",
            "formula_column": "Formula",
            "path_column": "Path",
        },
    )

    st = DummyStreamlit(
        {
            "onepiece_studio_extra_hdf_sources": {
                "fixture": {
                    "label": hdf_path.name,
                    "path": str(hdf_path),
                    "hdf_key": "df",
                    "origin": "path",
                    "rows": len(prepared),
                    "columns": prepared.shape[1],
                    "enabled": True,
                    "dataframe": _prepare_source_frame(prepared, label=hdf_path.name, path=str(hdf_path), source_id="fixture"),
                }
            },
            "onepiece_studio_control_text_include": "Cu-211",
            "onepiece_studio_control_material_query": {"include_elements": ["Cu", "C"], "element_mode": "all"},
            "onepiece_studio_workflow_operations": [
                {"kind": "filter", "column": "Name", "operator": "contains", "value": "Cu-211", "label": "Cu subset"}
            ],
            "onepiece_studio_control_status": {"fixture::6": "review"},
            EDIT_STATE_KEY: {"fixture::6": {"E": -111.5}},
            "onepiece_studio_saved_views": {"cu_subset": {"state": {"onepiece_studio_control_text_include": "Cu-211"}}},
            "onepiece_studio_audit_log": [{"message": "loaded fixture"}],
        }
    )

    base = pd.DataFrame({"Name": ["base-row"], "E": [1.0]})
    combined = _combined_active_database(st, base)
    payload = _build_project_payload(st, combined, combined)
    restored = DummyStreamlit({})
    messages = _restore_project_payload(restored, json.loads(json.dumps(payload)))

    assert messages == []
    assert len(combined) == len(frame) + 1
    assert restored.session_state["onepiece_studio_workflow_operations"][0]["value"] == "Cu-211"
    assert restored.session_state[EDIT_STATE_KEY]["fixture::6"]["E"] == -111.5
    assert "fixture" in restored.session_state["onepiece_studio_extra_hdf_sources"]


def test_repeated_project_roundtrip_and_workbook_edits_do_not_drift_rows(tmp_path: Path) -> None:
    hdf_path = tmp_path / "fixture.hdf"
    _full_fixture_frame().to_hdf(hdf_path, key="df")
    frame = _prepare_source_frame(_full_fixture_frame(), label="fixture.hdf", path=str(hdf_path), source_id="fixture")
    st = DummyStreamlit(
        {
            "onepiece_studio_extra_hdf_sources": {
                "fixture": {
                    "label": "fixture.hdf",
                    "path": str(hdf_path),
                    "hdf_key": "df",
                    "origin": "path",
                    "rows": len(frame),
                    "columns": frame.shape[1],
                    "enabled": True,
                    "dataframe": frame,
                }
            },
            EDIT_STATE_KEY: {},
            "onepiece_studio_control_status": {},
            "onepiece_studio_control_visible_states": ["included", "review", "reference"],
            "onepiece_studio_control_use_status": True,
        }
    )
    base = pd.DataFrame({"Name": ["base-row"], "E": [1.0]})

    expected_rows = len(base) + len(frame)
    for cycle in range(5):
        combined = _combined_active_database(st, base)
        st.session_state[EDIT_STATE_KEY][f"fixture::{cycle}"] = {"quality_flag": f"cycle-{cycle}"}
        edited = apply_session_edits(st, combined)
        payload = _build_project_payload(st, combined, edited)
        restored = DummyStreamlit({})
        messages = _restore_project_payload(restored, json.loads(json.dumps(payload)))
        assert messages == []
        assert len(combined) == expected_rows
        assert restored.session_state[EDIT_STATE_KEY][f"fixture::{cycle}"]["quality_flag"] == f"cycle-{cycle}"
        st = restored


def test_detected_gas_reference_values_cover_thermochemistry_species() -> None:
    frame = _full_fixture_frame().loc[:4, ["Name", "Formula", "E", "Path"]]

    detected = _detected_gas_reference_values(frame)

    assert detected["CO"] == -10.0
    assert detected["CO2"] == -20.0
    assert detected["H2"] == -6.0
    assert detected["H2O"] == -8.0
    assert detected["CH3OH"] == -30.0


def test_workflow_gas_reference_values_cover_thermochemistry_species() -> None:
    st = DummyStreamlit({})
    frame = _full_fixture_frame().loc[:4, ["Name", "Formula", "E", "Path"]]

    values = _workflow_gas_reference_values(st, frame)

    assert values["CO2"] == -20.0
    assert values["H2O"] == -8.0


def test_curation_rules_keep_valid_gas_reference_rows_for_adsorption_workflows() -> None:
    curated = apply_curation_rules(_full_fixture_frame(), action="exclude")

    remaining = set(curated["Name"].tolist())
    assert "gasphases-CO" in remaining
    assert "gasphases-CO2" in remaining
    assert "gasphases-H2" in remaining
    assert "gasphases-H2O" in remaining


def test_controlroom_filters_work_after_soak_state_roundtrip() -> None:
    frame = _prepare_source_frame(_full_fixture_frame(), label="fixture.hdf", path="fixture.hdf", source_id="fixture")
    st = DummyStreamlit(
        {
            "onepiece_studio_control_text_include": "Cu-211",
            "onepiece_studio_control_text_exclude": "broken",
            "onepiece_studio_control_use_status": True,
            "onepiece_studio_control_status": {"fixture::9": "excluded"},
            "onepiece_studio_control_selected_facets": {},
            "onepiece_studio_control_numeric": {"E": (-130.0, -100.0)},
            "onepiece_studio_control_material_query": {"include_elements": ["Cu", "C"], "element_mode": "any"},
            "onepiece_studio_control_fmax_max": 0.10,
            "onepiece_studio_control_drop_convergence": False,
            "onepiece_studio_control_drop_test": False,
            "onepiece_studio_control_visible_states": ["included", "review", "reference"],
        }
    )

    filtered = _apply_controlroom_filters(st, frame)

    assert "Cu-211-clean-test-broken" not in filtered["Name"].tolist()
    assert "Cu-211-clean-CO-1" in filtered["Name"].tolist()
