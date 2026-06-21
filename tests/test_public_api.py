"""Contract tests for the curated top-level ``onepiece`` namespace.

The top level exposes a small curated API (``__all__``); every name that was
exported before the curation must stay importable, either directly or through
a deprecation alias that points at its submodule home.
"""

from __future__ import annotations

import importlib
import re
import warnings

import pytest

import onepiece

CURATED_EXPORTS = {
    # Load data
    "bundled_catalysis_hub_dataset",
    "crawl_root_to_frame",
    "load_dataset",
    "read_dataset_path",
    "read_hdf_path",
    "save_dataset",
    # FAIR/provenance
    "ReferenceScheme",
    "build_dataset_provenance",
    "provenance_graph",
    "ro_crate_metadata",
    "validate_provenance_payload",
    # Adsorption energetics
    "GasReferences",
    "add_adsorption_energies",
    "add_catalysis_hub_adsorption_energies",
    "adsorption_view",
    "assign_references_before_merge",
    # Thermochemistry
    "add_gibbs_free_energy",
    "adsorbate_free_energy",
    "gas_free_energy",
    # Plotting
    "plot_adsorption_energy_vs_frequency",
    "plot_row_metric_3d",
    "plot_structure_value_3d",
    "save_dataframe_metric_plots_3d",
    # Electronic descriptors
    "add_atomic_magnetic_moment_descriptors",
    "add_atomic_reference_difference_descriptors",
}

# Everything `from onepiece import *` provided before the namespace was
# curated (commit 4e0ab2a). Removing a name from this contract breaks
# existing notebooks; new names must not be added here.
LEGACY_EXPORTS = frozenset(
    """
    ChgcarData DEFAULT_CO_FREQUENCY_SCALING DEFAULT_IR_TOLERANCE_CM1 DatasetManifest DatasetQuery
    DoscarData GasReferences GroupedPhaseDiagramResult NamedPhaseFieldResult PhaseFieldResult
    PhaseScanResult REFERENCE_IR_BANDS SelfTestResult StorageConfig WorkflowResult
    add_adsorbate_charge_descriptors add_adsorption_energies add_ase_analysis_descriptors
    add_atomic_charge_descriptors add_catalysis_hub_adsorption_energies add_element_count_columns
    add_elemental_adsorption_energy add_elemental_adsorption_free_energy add_gibbs_free_energy
    add_input_parameter_checks add_ir_peak_matches add_projected_dos_descriptors
    add_recipe_adsorption_energies add_structure_descriptors adsorbate_atom_indices_from_structures
    adsorbate_free_energy adsorbate_orientation_angle adsorbate_surface_distance_summary
    adsorption_frequency_plot_table adsorption_view annotate_reaction_network apply_curation_rules
    apply_dataset_kind apply_dataset_query apply_import_options apply_materials_search
    apply_operation apply_operations assign_references_before_merge assign_surface_references
    atomic_charge_long_table build_corrected_phase_expressions
    build_grouped_surface_phase_diagrams build_phase_field_grid build_project_payload
    build_surface_free_energy_expressions build_surface_phase_diagram
    bundled_catalysis_hub_dataset cache_key_for_paths chgcar_cumulative_axis_profile
    chgcar_line_profile chgcar_planar_average chgcar_plane_integrated_electrons chgcar_to_xarray
    classify_adsorption_site combined_active_database compare_structures_rmsd
    compute_atomic_charges compute_d_band_center compute_d_band_filling coordination_numbers
    copt_barrier_summary copt_profile_points count_element crawl_calculation_directories
    crawl_calculation_paths crawl_root_to_frame crawl_root_to_hdf create_calculation_frame
    dataset_directory dataset_manifest_path default_phase_variables
    default_room_temperature_phase detect_adsorbate_desorption detect_adsorbate_dissociation
    detect_overlapping_atoms detect_source_profile detect_storage_format detect_unphysical_bonds
    detected_gas_reference_values doscar_integrated_pdos doscar_orbital_band_center
    doscar_projected_long_table doscar_select_energy_window doscar_to_xarray
    enrich_electronic_summaries ensure_name_index ensure_storage_layout
    estimate_phase_scan_slopes evaluate_expression filter_any_token filter_text
    format_self_test_result gas_free_energy gas_reference_candidates
    generalized_coordination_numbers get_all_elements identify_surface_atom_indices
    infer_adsorbate_recipe infer_adsorption_recipes infer_atomic_layers
    infer_reference_equation_from_formula integrate_atomic_electron_populations
    integrate_projected_dos integrate_total_dos load_dataset map_adsorption_columns
    map_atoms_by_species_and_position match_ir_frequencies
    matched_surface_atom_indices_from_structures merge_entropies_file
    nearest_neighbor_distances parse_reference_equation phase_symbol_locals
    plot_adsorption_energy_vs_frequency prepare_source_frame query_description
    reaction_path_geometry_summary read_acf_dat read_cache_payload read_chgcar
    read_dataset_manifest read_dataset_path read_doscar read_hdf_path read_uploaded_hdf
    read_vasp_valence_electrons reference_ir_bands resolve_storage_config
    restore_project_payload restore_source_descriptors row_element_count_map row_elements
    row_name run_catalysis_hub_self_test save_dataset slab_thickness solve_phase_boundaries
    source_descriptors source_profile_summary stable_phase_scan store_source
    substitute_variables summarize_charge_transfer_by_layer summarize_phase_field_stability
    surface_reconstruction_metrics to_sympy_expression vacuum_thickness write_cache_payload
    """.split()
)


def test_all_is_exactly_the_curated_set() -> None:
    assert len(onepiece.__all__) == len(set(onepiece.__all__))
    assert set(onepiece.__all__) == CURATED_EXPORTS


def test_curated_names_resolve_without_deprecation_warning() -> None:
    for name in onepiece.__all__:
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            assert getattr(onepiece, name) is not None


def test_curated_names_are_listed_by_dir() -> None:
    assert CURATED_EXPORTS <= set(dir(onepiece))


def test_every_legacy_export_is_still_available() -> None:
    available = set(onepiece.__all__) | set(onepiece._DEPRECATED_ALIASES)
    missing = LEGACY_EXPORTS - available
    assert not missing, f"legacy exports lost from the top level: {sorted(missing)}"


def test_deprecated_aliases_do_not_shadow_curated_names() -> None:
    overlap = set(onepiece.__all__) & set(onepiece._DEPRECATED_ALIASES)
    assert not overlap


@pytest.mark.parametrize("name", sorted(onepiece._DEPRECATED_ALIASES))
def test_deprecated_alias_warns_and_matches_its_new_home(name: str) -> None:
    target_module = onepiece._DEPRECATED_ALIASES[name]
    with pytest.warns(DeprecationWarning, match=re.escape(f"{target_module}.{name}")):
        value = getattr(onepiece, name)
    assert value is getattr(importlib.import_module(target_module), name)


def test_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="no_such_name"):
        onepiece.no_such_name  # noqa: B018
