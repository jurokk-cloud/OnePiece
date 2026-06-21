from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from ase import Atoms
from onepiece_studio.config import OnePieceStudioConfig
from onepiece_studio.state import AUDIT_LOG, WORKFLOW_OPERATIONS
from onepiece_studio.ui.controlroom import _available_elements, _clamp_float, _filter_text
from onepiece_studio.ui.data_management import (
    _build_project_payload,
    _capture_control_state,
    _restore_project_payload,
)
from onepiece_studio.ui.data_sources import (
    _apply_import_options,
    _apply_source_block_edits,
    _combined_active_database,
    _crawl_summary,
    _detected_gas_reference_values,
    _map_adsorption_columns,
    _prepare_source_frame,
    _set_crawl_output_hdf,
    detect_source_profile,
    restore_source_descriptors,
    source_descriptors,
)
from onepiece_studio.ui.streamlit_app import build_page_functions
from onepiece_studio.ui.visualize import (
    _chart_interpretation,
    _chart_presets,
    _column_plot_label,
)
from onepiece_studio.ui.workbook import EDIT_STATE_KEY, apply_session_edits
from onepiece_studio.ui.workflow_builder import (
    _adsorption_recipes_from_table,
    _apply_operation,
    _column_index,
    _default_drop_rules_table,
    _default_gas_reference_table,
    _default_normalization_table,
    _default_recipe_table,
    _drop_rules_from_table,
    _gas_reference_mapping_from_table,
    _normalization_pairs_from_table,
    _standard_operation_recipe,
    _suggest_contains_name,
    _suggest_derived_name_binary,
    _suggest_derived_name_scalar,
    _valid_new_column,
    _workflow_gas_reference_values,
)

from onepiece.adsorption import add_element_count_columns, get_all_elements
from onepiece.sources import (
    restore_source_descriptors as backend_restore_source_descriptors,
)
from onepiece.sources import (
    store_source as backend_store_source,
)


class DummySource:
    name = "dummy"
    display_name = "dummy"


class DummyStreamlit:
    def __init__(self, session_state: dict | None = None) -> None:
        self.session_state = session_state or {}
        self.rerun_called = False

    def rerun(self) -> None:
        self.rerun_called = True


def test_capture_control_state_includes_material_query() -> None:
    st = DummyStreamlit(
        {
            "onepiece_studio_control_text_include": "Ni",
            "onepiece_studio_control_material_query": {"include_elements": ["Ni", "Ga"], "chemsys": "Ni-Ga"},
            "onepiece_studio_control_numeric": {"E": (-5.0, 1.0)},
        }
    )

    captured = _capture_control_state(st)

    assert captured["onepiece_studio_control_text_include"] == "Ni"
    assert captured["onepiece_studio_control_material_query"]["chemsys"] == "Ni-Ga"
    assert captured["onepiece_studio_control_numeric"]["E"] == (-5.0, 1.0)


def test_streamlit_page_builder_stores_workflow_audit_log_in_session_state() -> None:
    st = DummyStreamlit(
        {
            WORKFLOW_OPERATIONS: [
                {
                    "kind": "derive_scalar",
                    "left": "E",
                    "operator": "+",
                    "scalar": 1.0,
                    "new_column": "E_plus_one",
                }
            ]
        }
    )
    frame = pd.DataFrame({"Name": ["row-a"], "E": [1.0]})

    page_functions = build_page_functions(st, DummySource(), OnePieceStudioConfig(), frame)

    assert page_functions["_total_count"] == 1
    assert st.session_state[AUDIT_LOG][0]["kind"] == "derive_scalar"
    assert st.session_state[AUDIT_LOG][0]["added_columns"] == ["E_plus_one"]


def test_clamp_float_keeps_numeric_widget_defaults_in_range() -> None:
    assert _clamp_float(17.364889, minimum=0.0, maximum=0.01, fallback=0.01) == 0.01
    assert _clamp_float(-4.0, minimum=0.0, maximum=0.01, fallback=0.01) == 0.0
    assert _clamp_float(None, minimum=0.0, maximum=0.01, fallback=0.01) == 0.01


def test_column_index_falls_back_safely() -> None:
    assert _column_index(["A", "B", "C"], "B") == 1
    assert _column_index(["A", "B", "C"], "Z", fallback=2) == 2
    assert _column_index(["A", "B", "C"], None, fallback=99) == 2


def test_apply_session_edits_overrides_dataframe_values_by_row_key() -> None:
    frame = pd.DataFrame(
        {
            "source_hdf": ["a.hdf", "a.hdf"],
            "source_row": ["0", "1"],
            "Name": ["row0", "row1"],
            "E": [1.0, 2.0],
            "quality_flag": ["ok", "review"],
        }
    )
    st = DummyStreamlit(
        {
            "onepiece_studio_cell_edits": {
                "a.hdf::1": {"E": -7.5, "quality_flag": "ok"},
            }
        }
    )

    edited = apply_session_edits(st, frame)

    assert edited.loc[1, "E"] == -7.5
    assert edited.loc[1, "quality_flag"] == "ok"
    assert edited.loc[0, "E"] == 1.0


def test_combined_active_database_respects_enabled_source_blocks() -> None:
    base = pd.DataFrame({"Name": ["base-row"], "E": [0.0]})
    extra = _prepare_source_frame(
        pd.DataFrame({"Name": ["extra-row"], "E": [1.0]}),
        label="extra.hdf",
        path="/tmp/extra.hdf",
        source_id="extra",
    )
    st = DummyStreamlit(
        {
            "onepiece_studio_extra_hdf_sources": {
                "extra": {
                    "label": "extra.hdf",
                    "path": "/tmp/extra.hdf",
                    "rows": 1,
                    "columns": extra.shape[1],
                    "enabled": False,
                    "dataframe": extra,
                }
            }
        }
    )

    disabled = _combined_active_database(st, base)
    st.session_state["onepiece_studio_extra_hdf_sources"]["extra"]["enabled"] = True
    enabled = _combined_active_database(st, base)

    assert len(disabled) == 1
    assert len(enabled) == 2
    assert "extra-row" in enabled["Name"].tolist()


def test_combined_active_database_uses_real_base_source_metadata() -> None:
    base = pd.DataFrame({"Name": ["row-a"], "E": [0.0]})
    st = DummyStreamlit({})

    combined = _combined_active_database(
        st,
        base,
        source_name="CuGa_211.hdf",
        source_path="/tmp/CuGa_211.hdf",
    )

    row = combined.iloc[0]
    assert row["dataset"] == "CuGa_211"
    assert row["dataset_label"] == "CuGa_211"
    assert row["source_hdf"] == "/tmp/CuGa_211.hdf"


def test_get_all_elements_and_count_columns_use_structure_symbols() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["surface", "adsorbate"],
            "struc": [
                Atoms("Cu2", positions=[(0, 0, 0), (1.8, 0, 0)]),
                Atoms("Cu2OH", positions=[(0, 0, 0), (1.8, 0, 0), (0.9, 0.9, 1.0), (0.9, 0.9, 1.9)]),
            ],
        }
    )

    elements = get_all_elements(frame)
    counted = add_element_count_columns(frame)

    assert elements == ["Cu", "H", "O"]
    assert counted.loc[0, "Cu"] == 2.0
    assert counted.loc[1, "O"] == 1.0
    assert counted.loc[1, "H"] == 1.0


def test_apply_source_block_edits_updates_enabled_flags() -> None:
    st = DummyStreamlit(
        {
            "onepiece_studio_extra_hdf_sources": {
                "extra": {"enabled": True, "label": "extra.hdf"},
            }
        }
    )
    edited = pd.DataFrame(
        [
            {"id": "base", "enabled": True},
            {"id": "extra", "enabled": False},
        ]
    )

    _apply_source_block_edits(st, edited)

    assert st.session_state["onepiece_studio_extra_hdf_sources"]["extra"]["enabled"] is False
    assert st.rerun_called is True


def test_filter_text_does_not_match_full_parent_paths() -> None:
    frame = pd.DataFrame(
        {
            "dataset": ["CaO-slabs", "Ga2O3-slabs"],
            "Name": ["CaO-clean", "Ga-clean"],
            "Formula": ["Ca32O32", "Ga16O24"],
            "source_hdf": [
                "/Users/test/Uni/Database/CaO-slabs.hdf",
                "/Users/test/Uni/Database/Ga2O3-slabs.hdf",
            ],
        }
    )

    filtered = _filter_text(frame, "Ni", include=True)

    assert filtered.empty


def test_material_search_element_options_follow_structure_elements() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["surface", "adsorbate"],
            "struc": [
                Atoms("Cu2", positions=[(0, 0, 0), (1.8, 0, 0)]),
                Atoms("Cu2NH3", positions=[(0, 0, 0), (1.8, 0, 0), (0.9, 0.9, 1.0), (0.9, 0.9, 1.9), (1.2, 0.9, 2.1), (0.6, 0.9, 2.1)]),
            ],
        }
    )

    assert _available_elements(frame) == ["Cu", "H", "N"]


def test_crawl_summary_reports_profile_columns_and_gas_refs() -> None:
    clean = Atoms("Ni4", positions=[(0, 0, 0), (1.8, 0, 0), (0, 1.8, 0), (1.8, 1.8, 0)])
    ads = clean + Atoms("CO", positions=[(0.9, 0.9, 1.5), (0.9, 0.9, 2.6)])
    frame = pd.DataFrame(
        {
            "Name": ["gasphases-CO", "Ni-clean", "Ni-clean-CO-1"],
            "Formula": ["CO", "Ni4", "CNi4O"],
            "E": [-10.0, -100.0, -112.0],
            "Path": ["refs/gas/CO", "/tmp/clean", "/tmp/co"],
            "struc": [None, clean, ads],
            "fmax": [0.0, 0.01, 0.02],
        }
    )

    summary = _crawl_summary(
        frame,
        root_text="/tmp/calculations",
        calc_file="final.traj",
        output_hdf="/tmp/calculations.hdf",
    )

    assert summary["rows"] == 3
    assert summary["profile"] == "surface_adsorption_local_hdf"
    assert "Name" in summary["important_columns"]
    assert "struc" in summary["structure_columns"]
    assert "CO" in summary["gas_reference_labels"]


def test_set_crawl_output_hdf_updates_session_state() -> None:
    session_state: dict[str, object] = {}
    _set_crawl_output_hdf(session_state, "/tmp/example.hdf")
    assert session_state["onepiece_studio_crawl_output_hdf"] == "/tmp/example.hdf"


def test_project_payload_roundtrip_restores_state(tmp_path: Path) -> None:
    base = pd.DataFrame({"Name": ["base-row"], "E": [0.0]})
    extra_path = tmp_path / "extra.hdf"
    pd.DataFrame({"Name": ["extra-row"], "E": [1.5]}).to_hdf(extra_path, key="df")

    source_state = {
        "extra": {
            "label": extra_path.name,
            "path": str(extra_path),
            "hdf_key": "df",
            "origin": "path",
            "rows": 1,
            "columns": 7,
            "enabled": True,
            "dataframe": _prepare_source_frame(
                pd.DataFrame({"Name": ["extra-row"], "E": [1.5]}),
                label=extra_path.name,
                path=str(extra_path),
                source_id="extra",
            ),
        }
    }
    st = DummyStreamlit(
        {
            "onepiece_studio_control_text_include": "Ni",
            "onepiece_studio_control_material_query": {"chemsys": "Ni-Ga"},
            "onepiece_studio_workflow_operations": [{"kind": "filter", "column": "Name", "operator": "contains", "value": "Ni"}],
            "onepiece_studio_control_status": {"base::0": "review"},
            EDIT_STATE_KEY: {"base::0": {"E": -1.0}},
            "onepiece_studio_saved_views": {"test": {"saved_at": "2026-01-01T00:00:00", "state": {"onepiece_studio_control_text_include": "Ni"}}},
            "onepiece_studio_audit_log": [{"message": "saved"}],
            "onepiece_studio_extra_hdf_sources": source_state,
        }
    )

    payload = _build_project_payload(st, base, base)
    raw = json.loads(json.dumps(payload))

    restored = DummyStreamlit({})
    messages = _restore_project_payload(restored, raw)

    assert messages == []
    assert restored.session_state["onepiece_studio_control_text_include"] == "Ni"
    assert restored.session_state["onepiece_studio_control_material_query"]["chemsys"] == "Ni-Ga"
    assert restored.session_state["onepiece_studio_workflow_operations"][0]["kind"] == "filter"
    assert restored.session_state["onepiece_studio_control_status"]["base::0"] == "review"
    assert restored.session_state[EDIT_STATE_KEY]["base::0"]["E"] == -1.0
    assert "extra" in restored.session_state["onepiece_studio_extra_hdf_sources"]
    descriptor = raw["sources"][0]
    assert descriptor["fingerprint"]["exists"] is True
    assert descriptor["fingerprint"]["checksum"].startswith("sha256:")
    restored_source = restored.session_state["onepiece_studio_extra_hdf_sources"]["extra"]
    assert restored_source["fingerprint"]["checksum"] == descriptor["fingerprint"]["checksum"]


def test_restore_source_descriptors_warns_when_checksum_changed(tmp_path: Path) -> None:
    source_path = tmp_path / "changing.hdf"
    pd.DataFrame({"Name": ["row-a"], "E": [1.0]}).to_hdf(source_path, key="df")
    st = DummyStreamlit({})
    source_id = backend_store_source(
        st.session_state,
        pd.read_hdf(source_path, key="df"),
        label=source_path.name,
        path=str(source_path),
    )
    descriptors = source_descriptors(st)
    assert descriptors[0]["fingerprint"]["checksum"].startswith("sha256:")

    pd.DataFrame({"Name": ["row-a"], "E": [2.0]}).to_hdf(source_path, key="df", mode="w")
    restored = DummyStreamlit({})
    messages = backend_restore_source_descriptors(restored.session_state, descriptors)

    assert source_id in restored.session_state["onepiece_studio_extra_hdf_sources"]
    assert any("checksum changed" in message for message in messages)


def test_source_descriptors_skip_uploaded_temp_sources() -> None:
    st = DummyStreamlit(
        {
            "onepiece_studio_extra_hdf_sources": {
                "upload_1": {
                    "label": "upload.hdf",
                    "path": "/tmp/upload.hdf",
                    "hdf_key": "df",
                    "origin": "upload",
                    "enabled": True,
                    "dataframe": pd.DataFrame({"Name": ["upload-row"]}),
                }
            }
        }
    )

    descriptors = source_descriptors(st)
    restored = DummyStreamlit({})
    messages = restore_source_descriptors(restored, descriptors)

    assert descriptors[0]["reloadable"] is False
    assert len(messages) == 1
    assert restored.session_state["onepiece_studio_extra_hdf_sources"] == {}


def test_map_adsorption_columns_uses_selected_import_columns() -> None:
    frame = pd.DataFrame(
        {
            "calc_name": ["Ni-clean", "Ni-clean-CO-1"],
            "energy_total": [-10.0, -25.0],
            "chem_formula": ["Ni4", "CNi4O"],
            "calc_path": ["/tmp/clean", "/tmp/co"],
        }
    )

    mapped = _map_adsorption_columns(
        frame,
        {
            "name_column": "calc_name",
            "energy_column": "energy_total",
            "formula_column": "chem_formula",
            "path_column": "calc_path",
        },
    )

    assert mapped["Name"].tolist() == frame["calc_name"].tolist()
    assert mapped["E"].tolist() == frame["energy_total"].tolist()
    assert mapped["Formula"].tolist() == frame["chem_formula"].tolist()
    assert mapped["Path"].tolist() == frame["calc_path"].tolist()


def test_apply_import_options_can_prepare_adsorption_columns() -> None:
    frame = pd.DataFrame(
        {
            "calc_name": ["gasphases-CO", "Ni-clean", "Ni-clean-CO-2"],
            "energy_total": [-13.0, -10.0, -38.0],
            "chem_formula": ["CO", "Ni4", "C2Ni4O2"],
            "calc_path": ["refs/gas/CO", "/tmp/clean", "/tmp/co2"],
        }
    )

    prepared = _apply_import_options(
        frame,
        {
            "enable_adsorption_prep": True,
            "dataset_kind": "auto",
            "name_column": "calc_name",
            "energy_column": "energy_total",
            "formula_column": "chem_formula",
            "path_column": "calc_path",
        },
    )

    co_row = prepared.loc[prepared["Name"] == "Ni-clean-CO-2"].iloc[0]
    assert "surface_ref_name" in prepared.columns
    assert "E_ads_CO_total_eV" in prepared.columns
    assert "E_ads_CO_eV" in prepared.columns
    assert co_row["surface_ref_name"] == "Ni-clean"
    assert co_row["n_CO_adsorbates"] == 2
    assert co_row["E_ads_CO_total_eV"] == -2.0
    assert co_row["E_ads_CO_eV"] == -1.0


def test_apply_import_options_can_force_gas_dataset_kind() -> None:
    frame = pd.DataFrame(
        {
            "calc_name": ["CO", "H2"],
            "energy_total": [-13.0, -7.0],
            "chem_formula": ["CO", "H2"],
            "calc_path": ["refs/gas/CO", "refs/gas/H2"],
        }
    )

    prepared = _apply_import_options(
        frame,
        {
            "enable_adsorption_prep": False,
            "dataset_kind": "gas",
            "name_column": "calc_name",
            "energy_column": "energy_total",
            "formula_column": "chem_formula",
            "path_column": "calc_path",
        },
    )

    assert prepared["onepiece_dataset_kind"].tolist() == ["gas", "gas"]
    assert prepared["record_class"].tolist() == ["gas_reference", "gas_reference"]


def test_detect_source_profile_respects_explicit_bulk_dataset_kind() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["Cu-fcc", "Ni-fcc"],
            "Formula": ["Cu4", "Ni4"],
            "E": [-10.0, -11.0],
            "onepiece_dataset_kind": ["bulk", "bulk"],
        }
    )

    profile = detect_source_profile(frame)

    assert profile["profile"] == "bulk_materials_local_hdf"
    assert "bulk_screening" in profile["capabilities"]


def test_detected_gas_reference_values_uses_default_suggestions() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["gasphases-CO", "gasphases-CH3OH", "gasphases-H2"],
            "Formula": ["CO", "CH4O", "H2"],
            "E": [-12.1, -27.7, -7.16],
            "Path": ["refs/gas/CO", "refs/gas/CH3OH", "refs/gas/H2"],
        }
    )

    detected = _detected_gas_reference_values(frame)

    assert detected == {"CO": -12.1, "CH3OH": -27.7, "H2": -7.16}


def test_workflow_derived_column_suggestions_are_valid_identifiers() -> None:
    names = [
        _suggest_derived_name_binary("E", "-", "surface_ref_E"),
        _suggest_derived_name_scalar("fmax", "*", 2.5),
        _suggest_contains_name("Name", "clean surface"),
    ]

    for name in names:
        assert _valid_new_column(name)


def test_workflow_adsorption_operation_adds_reference_columns() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["Ni-211-clean", "Ni-211-clean-CO-1"],
            "Formula": ["Ni48", "CNi48O"],
            "E": [-100.0, -112.0],
            "dataset": ["Ni-slabs", "Ni-slabs"],
        }
    )

    result = _apply_operation(frame, {"kind": "derive_adsorption_columns"})

    assert "surface_ref_name" in result.columns
    assert "surface_ref_E" in result.columns
    assert "delta_E_to_surface_eV" in result.columns


def test_workflow_adsorption_operation_uses_passed_co_gas_reference() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["Ni-211-clean", "Ni-211-clean-CO-1"],
            "Formula": ["Ni48", "CNi48O"],
            "E": [-100.0, -112.0],
            "dataset": ["Ni-slabs", "Ni-slabs"],
        }
    )

    result = _apply_operation(
        frame,
        {
            "kind": "derive_adsorption_columns",
            "gas_references": {"CO": -11.0, "CH3OH": None, "H2": None},
        },
    )

    assert "E_ads_CO_eV" in result.columns
    co_row = result.loc[result["Name"] == "Ni-211-clean-CO-1"].iloc[0]
    assert co_row["n_CO_adsorbates"] == 1
    assert co_row["E_ads_CO_eV"] == -1.0


def test_workflow_gas_reference_values_prefer_session_state() -> None:
    st = DummyStreamlit(
        {
            "onepiece_studio_ads_gas_value_CO": -12.0,
            "onepiece_studio_ads_gas_value_CH3OH": -28.5,
            "onepiece_studio_ads_gas_value_H2": -7.2,
        }
    )
    frame = pd.DataFrame({"Name": ["row"], "E": [0.0]})

    values = _workflow_gas_reference_values(st, frame)

    assert values == {"CO": -12.0, "CH3OH": -28.5, "H2": -7.2}


def test_workflow_gas_reference_values_fall_back_to_dataset_candidates() -> None:
    st = DummyStreamlit({})
    frame = pd.DataFrame(
        {
            "Name": ["gasphases-CO", "gasphases-CH3OH", "gasphases-H2"],
            "Formula": ["CO", "CH4O", "H2"],
            "E": [-12.1, -27.7, -7.16],
            "Path": ["refs/gas/CO", "refs/gas/CH3OH", "refs/gas/H2"],
        }
    )

    values = _workflow_gas_reference_values(st, frame)

    assert values["CO"] == -12.1
    assert values["CH3OH"] == -27.7
    assert values["H2"] == -7.16


def test_standard_operation_recipe_co_adsorption_analysis_starter_builds_bundle() -> None:
    operations, description = _standard_operation_recipe(
        "CO adsorption analysis starter",
        {"CO": -12.1, "CH3OH": None, "H2": None},
    )

    assert len(operations) == 3
    assert operations[0]["kind"] == "derive_adsorption_columns"
    assert operations[1]["kind"] == "filter"
    assert operations[1]["column"] == "adsorbate"
    assert operations[1]["value"] == "CO"
    assert operations[2]["kind"] == "filter"
    assert operations[2]["column"] == "E_ads_CO_eV"
    assert "ready-to-plot CO workflow" in description


def test_standard_operation_recipe_count_all_detected_elements_builds_bundle() -> None:
    operations, description = _standard_operation_recipe(
        "Count all detected elements",
        {},
    )

    assert len(operations) == 1
    assert operations[0]["kind"] == "count_all_elements"
    assert "one count column per element" in description


def test_standard_operation_recipe_adsorption_gibbs_starter_builds_bundle() -> None:
    operations, description = _standard_operation_recipe(
        "Adsorption + Gibbs analysis starter",
        {"CO2": -20.0, "H2": -6.0, "H2O": -8.0},
    )

    assert len(operations) == 3
    assert operations[0]["kind"] == "derive_adsorption_columns"
    assert operations[1]["kind"] == "derive_gibbs_free_energy"
    assert operations[1]["temperature"] == 298.15
    assert operations[2]["kind"] == "derive_gibbs_adsorption"
    assert operations[2]["output_column"] == "adsorption_free_energy"
    assert "thermochemistry-ready workflow" in description


def test_chart_presets_include_adsorption_analysis_when_columns_exist() -> None:
    frame = pd.DataFrame(
        {
            "E": [-25.0, -26.0],
            "E_ads_CO_total_eV": [-2.0, -4.0],
            "E_ads_CO_eV": [-1.0, -2.0],
            "surface_ref_name": ["Ni-clean", "Ni-clean"],
            "dataset_label": ["Ni-slabs", "Ni-slabs"],
        }
    )

    numeric_columns = list(frame.select_dtypes(include="number").columns)
    categorical_columns = ["surface_ref_name", "dataset_label"]
    presets = _chart_presets(frame, numeric_columns, categorical_columns)

    assert "Adsorption analysis" in presets
    assert presets["Adsorption analysis"]["x"] == "E_ads_CO_total_eV"
    assert presets["Adsorption analysis"]["y"] == "E_ads_CO_eV"
    assert presets["Adsorption analysis"]["color"] == "surface_ref_name"


def test_chart_presets_include_ase_charge_and_d_band_views_when_columns_exist() -> None:
    frame = pd.DataFrame(
        {
            "E_ads_CO_eV": [-1.0, -0.5],
            "adsorbate_charge_delta_vs_ref_e": [0.2, -0.1],
            "surface_net_charge_delta_vs_ref_e": [-0.2, 0.1],
            "adsorbate_height_above_surface": [1.2, 1.5],
            "min_adsorbate_surface_distance": [1.1, 1.3],
            "adsorbate_tilt_deg": [5.0, 22.0],
            "metal_d_band_center_eV": [-1.8, -1.4],
            "metal_d_band_filling": [0.62, 0.71],
            "surface_reconstruction_rmsd": [0.05, 0.11],
            "adsorption_site": ["top", "bridge"],
            "surface_ref_name": ["Cu-211-clean", "Cu-211-clean"],
            "adsorbate": ["CO", "CO"],
            "dataset_label": ["demo", "demo"],
        }
    )

    numeric_columns = list(frame.select_dtypes(include="number").columns)
    categorical_columns = ["adsorption_site", "surface_ref_name", "adsorbate", "dataset_label"]
    presets = _chart_presets(frame, numeric_columns, categorical_columns)

    assert "Charge transfer vs adsorption energy" in presets
    assert presets["Charge transfer vs adsorption energy"]["x"] == "adsorbate_charge_delta_vs_ref_e"
    assert "Surface polarization vs adsorbate height" in presets
    assert presets["Surface polarization vs adsorbate height"]["x"] == "adsorbate_height_above_surface"
    assert "d-band center vs adsorption energy" in presets
    assert presets["d-band center vs adsorption energy"]["x"] == "metal_d_band_center_eV"
    assert "Adsorption site families" in presets
    assert presets["Adsorption site families"]["color"] == "adsorption_site"


def test_plot_labels_and_interpretation_are_scientific_and_readable() -> None:
    assert _column_plot_label("E_ads_CO_eV") == "CO adsorption energy per CO / eV"
    assert _column_plot_label("adsorbate_tilt_deg") == "Adsorbate tilt / deg"
    text = _chart_interpretation(
        "d-band center vs adsorption energy",
        "metal_d_band_center_eV",
        "E_ads_CO_eV",
        "adsorption_site",
    )
    assert "Metal d-band center / eV" in text
    assert "CO adsorption energy per CO / eV" in text
    assert "Adsorption site" in text
    assert "electronic-structure" in text


def test_workflow_can_set_constant_column() -> None:
    frame = pd.DataFrame({"Name": ["a", "b"]})
    result = _apply_operation(
        frame,
        {"kind": "derive_constant", "new_column": "adsorbate_ref", "value": "MgOCu-"},
    )
    assert result["adsorbate_ref"].tolist() == ["MgOCu-", "MgOCu-"]


def test_workflow_can_fill_missing_values() -> None:
    frame = pd.DataFrame({"Cu": [1.0, None, 3.0]})
    result = _apply_operation(
        frame,
        {"kind": "fill_missing", "column": "Cu", "value": 0.0},
    )
    assert result["Cu"].tolist() == [1.0, 0.0, 3.0]


def test_workflow_can_replace_categorical_values() -> None:
    frame = pd.DataFrame({"adsorbate": ["CHO", "CO_NH2", "CHO"]})
    result = _apply_operation(
        frame,
        {"kind": "replace_value", "column": "adsorbate", "from_value": "CHO", "to_value": "HCO"},
    )
    assert result["adsorbate"].tolist() == ["HCO", "CO_NH2", "HCO"]


def test_workflow_can_count_element_into_column() -> None:
    frame = pd.DataFrame(
        {
            "struc": [
                Atoms("C2H4O", positions=[(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1)]),
                Atoms("CO2", positions=[(0, 0, 0), (1, 0, 0), (2, 0, 0)]),
                Atoms("Ni4", positions=[(0, 0, 0), (1.8, 0, 0), (0, 1.8, 0), (1.8, 1.8, 0)]),
            ]
        }
    )
    result = _apply_operation(
        frame,
        {"kind": "count_element", "new_column": "C_count", "element": "C", "structure_column": "struc"},
    )
    assert result["C_count"].tolist() == [2.0, 1.0, 0.0]


def test_workflow_can_count_all_elements_into_columns() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["surface", "adsorbate"],
            "struc": [
                Atoms("Cu2", positions=[(0, 0, 0), (1.8, 0, 0)]),
                Atoms("Cu2OH", positions=[(0, 0, 0), (1.8, 0, 0), (0.9, 0.9, 1.0), (0.9, 0.9, 1.9)]),
            ],
        }
    )

    result = _apply_operation(frame, {"kind": "count_all_elements", "label": "count all elements"})

    assert result["Cu"].tolist() == [2.0, 2.0]
    assert result["O"].tolist() == [0.0, 1.0]
    assert result["H"].tolist() == [0.0, 1.0]


def test_workflow_can_rank_within_groups() -> None:
    frame = pd.DataFrame(
        {
            "adsorbate_ref": ["A", "A", "B", "B"],
            "adsorbate": ["CO", "CO", "CO", "CO"],
            "E": [-10.0, -9.0, -4.0, -5.0],
        }
    )
    result = _apply_operation(
        frame,
        {
            "kind": "group_rank",
            "new_column": "ranked",
            "value_column": "E",
            "group_columns": ["adsorbate_ref", "adsorbate"],
            "ascending": True,
            "method": "min",
        },
    )
    assert result["ranked"].tolist() == [1.0, 2.0, 2.0, 1.0]


def test_workflow_can_exclude_exact_names() -> None:
    frame = pd.DataFrame({"Name": ["keep-1", "drop-1", "drop-2"]})
    result = _apply_operation(
        frame,
        {"kind": "exclude_exact_names", "column": "Name", "names": ["drop-1", "drop-2"]},
    )
    assert result["Name"].tolist() == ["keep-1"]


def test_workflow_can_exclude_by_match_rules() -> None:
    frame = pd.DataFrame(
        {
            "Name": [
                "keep-clean",
                "test-structure",
                "Ni-211-copt-run",
                "bad-diss-case",
                "exact-bad-row",
            ]
        }
    )
    result = _apply_operation(
        frame,
        {
            "kind": "exclude_by_match_rules",
            "column": "Name",
            "rules": [
                {"pattern": "test", "match_mode": "contains", "reason": "temporary"},
                {"pattern": "copt", "match_mode": "regex", "reason": "helper"},
                {"pattern": "exact-bad-row", "match_mode": "exact", "reason": "manual curation"},
            ],
        },
    )

    assert result["Name"].tolist() == ["keep-clean", "bad-diss-case"]


def test_numeric_not_equals_filter_handles_zero_as_number() -> None:
    frame = pd.DataFrame({"E": [0.0, -1.0, 2.0]})
    result = _apply_operation(
        frame,
        {"kind": "filter", "column": "E", "operator": "not equals", "value": "0"},
    )
    assert result["E"].tolist() == [-1.0, 2.0]


def test_workflow_recipe_adsorption_operation_computes_values() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["Ni-clean", "Ni-clean-CO-2"],
            "Formula": ["Ni4", "C2Ni4O2"],
            "E": [-10.0, -38.0],
            "Ni": [4, 4],
            "C": [0, 2],
            "O": [0, 2],
            "H": [0, 0],
        }
    )
    result = _apply_operation(
        frame,
        {
            "kind": "derive_recipe_adsorption",
            "gas_reference_values": {"CO": -13.0},
            "recipes": {"CO": {"basis": "C", "gas_refs": {"CO": 1.0}}},
        },
    )
    row = result.loc[result["Name"] == "Ni-clean-CO-2"].iloc[0]
    assert row["n_CO_adsorbates"] == 2
    assert row["E_ads_CO_total_eV"] == -2.0
    assert row["E_ads_CO_eV"] == -1.0


def test_workflow_reaction_network_operation_annotates_states_and_copt_steps() -> None:
    frame = pd.DataFrame(
        {
            "Name": [
                "Cu-211-Ga-CO2-1",
                "Cu-211-Ga-copt-HCOOH%H2COOH-1-00",
            ],
            "Formula": ["Cu4GaCO2", "Cu4GaCH2O2"],
            "E": [-20.0, -21.0],
            "Path": ["/tmp/co2", "/tmp/copt/00"],
        }
    )

    result = _apply_operation(frame, {"kind": "derive_reaction_network"})

    static_row = result.loc[result["Name"] == "Cu-211-Ga-CO2-1"].iloc[0]
    copt_row = result.loc[result["Name"] == "Cu-211-Ga-copt-HCOOH%H2COOH-1-00"].iloc[0]
    assert static_row["reaction_state"] == "CO2"
    assert static_row["reaction_network_role"] == "state"
    assert copt_row["reaction_step_initial"] == "HCOOH"
    assert copt_row["reaction_step_final"] == "H2COOH"
    assert copt_row["reaction_family"] == "HCOOH -> H2COOH"


def test_workflow_curation_operation_can_mark_review_without_dropping_rows() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["keep-clean", "test-structure"],
            "E": [-10.0, -11.0],
            "fmax": [0.01, 0.20],
            "struc": [Atoms("Ni4"), Atoms("Ni4")],
        }
    )

    result = _apply_operation(
        frame,
        {
            "kind": "derive_curation",
            "static_fmax_max": 0.05,
            "copt_fmax_max": 0.10,
            "exclude_name_tokens": ["test"],
            "action": "mark_review",
        },
    )

    assert len(result) == 2
    assert result.loc[result["Name"] == "keep-clean", "curation_status"].iloc[0] == "ok"
    assert result.loc[result["Name"] == "test-structure", "curation_status"].iloc[0] == "review"
    assert bool(result.loc[result["Name"] == "test-structure", "flag_any_bad"].iloc[0]) is True


def test_workflow_structure_descriptor_operation_derives_adsorbate_height_and_formula() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["Cu-211-Ga", "Cu-211-Ga-CO-1"],
            "Formula": ["Cu4Ga", "Cu4GaCO"],
            "E": [-10.0, -18.0],
            "struc": [
                Atoms("Cu4Ga", positions=[[0, 0, 0], [1, 0, 0.1], [0, 1, 0.2], [1, 1, 0.1], [0.5, 0.5, 0.15]]),
                Atoms("Cu4GaCO", positions=[[0, 0, 0], [1, 0, 0.1], [0, 1, 0.2], [1, 1, 0.1], [0.5, 0.5, 0.15], [0.2, 0.2, 1.6], [0.3, 0.2, 1.9]]),
            ],
        }
    )

    result = _apply_operation(frame, {"kind": "derive_structure_descriptors"})
    row = result.loc[result["Name"] == "Cu-211-Ga-CO-1"].iloc[0]

    assert row["adsorbate_formula"] == "CO"
    assert row["adsorbate_atom_count"] == 2.0
    assert row["surface_atom_count"] == 5.0
    assert row["adsorbate_height_above_surface"] > 1.0


def test_gas_reference_mapping_from_editor_table() -> None:
    table = _default_gas_reference_table({"CO": -14.0, "H2": -6.0})
    mapping = _gas_reference_mapping_from_table(table)

    assert mapping["CO"] == -14.0
    assert mapping["H2"] == -6.0
    assert "H2O" not in mapping


def test_adsorption_recipes_from_editor_table() -> None:
    table = _default_recipe_table()
    recipes = _adsorption_recipes_from_table(table)

    assert recipes["CO"]["basis"] == "C"
    assert recipes["CO"]["gas_refs"] == {"CO": 1.0}
    assert recipes["CH3O"]["gas_refs"] == {"CO": 1.0, "H2": 1.5}
    assert recipes["OH"]["basis"] == "O"
    assert recipes["OH"]["gas_refs"] == {"H2": -0.5, "H2O": 1.0}


def test_default_normalization_table_contains_expected_pairs() -> None:
    table = _default_normalization_table()
    pairs = _normalization_pairs_from_table(table)

    assert ("CHO", "HCO") in pairs
    assert ("CO_NH2", "NH2_CO") in pairs
    assert ("H2NHCO", "H2NCHO") in pairs


def test_normalization_pairs_from_table_ignores_incomplete_rows() -> None:
    table = pd.DataFrame(
        [
            {"from_value": "CHO", "to_value": "HCO"},
            {"from_value": "", "to_value": "skip"},
            {"from_value": "skip", "to_value": ""},
        ]
    )
    pairs = _normalization_pairs_from_table(table)

    assert pairs == [("CHO", "HCO")]


def test_default_drop_rules_table_contains_expected_patterns() -> None:
    table = _default_drop_rules_table()
    rules = _drop_rules_from_table(table)

    assert {"pattern": "test", "match_mode": "contains", "reason": "Temporary or exploratory calculations"} in rules
    assert any(rule["pattern"] == "copt" and rule["match_mode"] == "contains" for rule in rules)


def test_drop_rules_from_table_ignores_invalid_rows() -> None:
    table = pd.DataFrame(
        [
            {"pattern": "keep", "match_mode": "exact", "reason": "valid"},
            {"pattern": "", "match_mode": "contains", "reason": "skip empty"},
            {"pattern": "oops", "match_mode": "wildcard", "reason": "unsupported"},
        ]
    )

    rules = _drop_rules_from_table(table)

    assert rules == [{"pattern": "keep", "match_mode": "exact", "reason": "valid"}]
