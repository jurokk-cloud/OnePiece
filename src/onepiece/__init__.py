"""OnePiece backend for local scientific dataframe workflows.

The top level exposes the core notebook workflow: load a dataset, compute
adsorption energetics, add thermochemistry, plot. Everything else lives in
documented submodules:

- :mod:`onepiece.adsorption` -- formula parsing, reference assignment,
  adsorption-energy math, constrained-optimization paths
- :mod:`onepiece.ase_analysis` -- geometric/electronic structure descriptors
- :mod:`onepiece.automation` -- curation rules and reaction-network annotation
- :mod:`onepiece.dftdataframe_import` -- crawling calculation directories
- :mod:`onepiece.frame_utils` -- dataframe index helpers
- :mod:`onepiece.ir` -- IR frequency matching and plots
- :mod:`onepiece.phase_diagrams` -- surface phase diagrams
- :mod:`onepiece.provenance` -- FAIR metadata, reference schemes, and RO-Crate export
- :mod:`onepiece.projects` -- project save/restore payloads
- :mod:`onepiece.qa` -- bundled dataset and self-tests
- :mod:`onepiece.services` -- dataset queries and text filters
- :mod:`onepiece.sources` -- HDF/dataset reading and source management
- :mod:`onepiece.storage` -- dataset persistence and caching
- :mod:`onepiece.thermo` -- free-energy helpers
- :mod:`onepiece.vasp` -- CHGCAR/DOSCAR/Bader readers and descriptors
- :mod:`onepiece.workflows` -- recorded workflow operations
- :mod:`onepiece.xarray_vasp` -- xarray views of VASP volumetric data

Names that used to be re-exported here remain importable from the top level
through deprecation aliases; new code should import them from the submodule
named in the warning.

Examples
--------
The bundled tutorial dataset works out of the box:

>>> import onepiece
>>> frame = onepiece.read_hdf_path(onepiece.bundled_catalysis_hub_dataset(), key="df")
>>> analysed = onepiece.add_catalysis_hub_adsorption_energies(frame)
>>> len(analysed["adsorption_energy"].dropna())
9
"""

import importlib as _importlib
import warnings as _warnings
from importlib.metadata import PackageNotFoundError as _PackageNotFoundError
from importlib.metadata import version as _package_version

try:
    __version__ = _package_version("onepiece")
except _PackageNotFoundError:  # pragma: no cover - only when run from a source tree
    __version__ = "0.0.0+unknown"

from onepiece.adsorption import (
    GasReferences,
    add_adsorption_energies,
    add_catalysis_hub_adsorption_energies,
    adsorption_view,
    assign_references_before_merge,
)
from onepiece.ase_analysis import plot_row_metric_3d, plot_structure_value_3d, save_dataframe_metric_plots_3d
from onepiece.dftdataframe_import import crawl_root_to_frame
from onepiece.vasp import add_atomic_magnetic_moment_descriptors, add_atomic_reference_difference_descriptors
from onepiece.ir import plot_adsorption_energy_vs_frequency
from onepiece.provenance import (
    ReferenceScheme,
    build_dataset_provenance,
    provenance_graph,
    ro_crate_metadata,
    validate_provenance_payload,
)
from onepiece.qa import bundled_catalysis_hub_dataset
from onepiece.sources import read_dataset_path, read_hdf_path
from onepiece.storage import load_dataset, save_dataset
from onepiece.thermo import add_gibbs_free_energy, adsorbate_free_energy, gas_free_energy

__all__ = [
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
]

# Names removed from the curated top level, mapped to their submodule home.
# Accessing one still works but emits a DeprecationWarning (see __getattr__).
_DEPRECATED_ALIASES = {
    name: module
    for module, names in {
        "onepiece.adsorption": (
            "add_element_count_columns",
            "add_elemental_adsorption_energy",
            "add_elemental_adsorption_free_energy",
            "add_recipe_adsorption_energies",
            "assign_surface_references",
            "copt_barrier_summary",
            "copt_profile_points",
            "count_element",
            "default_room_temperature_phase",
            "get_all_elements",
            "infer_adsorbate_recipe",
            "infer_adsorption_recipes",
            "infer_reference_equation_from_formula",
            "parse_reference_equation",
            "row_element_count_map",
            "row_elements",
        ),
        "onepiece.ase_analysis": (
            "add_ase_analysis_descriptors",
            "adsorbate_orientation_angle",
            "adsorbate_surface_distance_summary",
            "classify_adsorption_site",
            "compare_structures_rmsd",
            "CoordinationEnvironment",
            "compute_d_band_center",
            "compute_d_band_filling",
            "coordination_environment",
            "coordination_numbers",
            "detect_adsorbate_desorption",
            "detect_adsorbate_dissociation",
            "detect_overlapping_atoms",
            "detect_unphysical_bonds",
            "generalized_coordination_numbers",
            "identify_surface_atom_indices",
            "infer_atomic_layers",
            "map_atoms_by_species_and_position",
            "nearest_neighbor_distances",
            "reaction_path_geometry_summary",
            "slab_thickness",
            "summarize_charge_transfer_by_layer",
            "surface_reconstruction_metrics",
            "vacuum_thickness",
        ),
        "onepiece.automation": (
            "add_structure_descriptors",
            "annotate_reaction_network",
            "apply_curation_rules",
        ),
        "onepiece.dftdataframe_import": (
            "add_input_parameter_checks",
            "crawl_calculation_directories",
            "crawl_calculation_paths",
            "crawl_root_to_hdf",
            "create_calculation_frame",
            "enrich_electronic_summaries",
            "merge_entropies_file",
        ),
        "onepiece.frame_utils": (
            "ensure_name_index",
            "row_name",
        ),
        "onepiece.ir": (
            "DEFAULT_CO_FREQUENCY_SCALING",
            "DEFAULT_IR_TOLERANCE_CM1",
            "REFERENCE_IR_BANDS",
            "add_ir_peak_matches",
            "adsorption_frequency_plot_table",
            "match_ir_frequencies",
            "reference_ir_bands",
        ),
        "onepiece.phase_diagrams": (
            "GroupedPhaseDiagramResult",
            "NamedPhaseFieldResult",
            "PhaseFieldResult",
            "PhaseScanResult",
            "build_corrected_phase_expressions",
            "build_grouped_surface_phase_diagrams",
            "build_phase_field_grid",
            "build_surface_free_energy_expressions",
            "build_surface_phase_diagram",
            "default_phase_variables",
            "estimate_phase_scan_slopes",
            "evaluate_expression",
            "phase_symbol_locals",
            "solve_phase_boundaries",
            "stable_phase_scan",
            "substitute_variables",
            "summarize_phase_field_stability",
            "to_sympy_expression",
        ),
        "onepiece.projects": (
            "build_project_payload",
            "restore_project_payload",
        ),
        "onepiece.provenance": (
            "ProvenanceActivity",
            "ProvenanceAgent",
            "ProvenanceEntity",
            "ProvenanceRecord",
            "ProvenanceValidationResult",
            "attach_workflow_audit_log",
            "entity_from_path",
            "file_checksum",
            "local_python_agent",
            "now_utc_iso",
            "onepiece_agent",
            "workflow_activity",
        ),
        "onepiece.qa": (
            "SelfTestResult",
            "format_self_test_result",
            "run_fair_provenance_audit",
            "run_catalysis_hub_self_test",
        ),
        "onepiece.services": (
            "DatasetQuery",
            "apply_dataset_query",
            "apply_materials_search",
            "filter_any_token",
            "filter_text",
            "query_description",
        ),
        "onepiece.sources": (
            "apply_dataset_kind",
            "apply_import_options",
            "combined_active_database",
            "detect_source_profile",
            "detected_gas_reference_values",
            "gas_reference_candidates",
            "map_adsorption_columns",
            "prepare_source_frame",
            "read_uploaded_hdf",
            "restore_source_descriptors",
            "source_descriptors",
            "source_profile_summary",
            "store_source",
        ),
        "onepiece.storage": (
            "DatasetManifest",
            "StorageConfig",
            "cache_key_for_paths",
            "dataset_directory",
            "dataset_manifest_path",
            "detect_storage_format",
            "ensure_storage_layout",
            "read_cache_payload",
            "read_dataset_manifest",
            "resolve_storage_config",
            "write_cache_payload",
        ),
        "onepiece.vasp": (
            "ChgcarData",
            "DoscarData",
            "add_adsorbate_charge_descriptors",
            "add_atomic_charge_descriptors",
            "add_projected_dos_descriptors",
            "adsorbate_atom_indices_from_structures",
            "atomic_charge_long_table",
            "compute_atomic_charges",
            "doscar_projected_long_table",
            "integrate_atomic_electron_populations",
            "integrate_projected_dos",
            "integrate_total_dos",
            "matched_surface_atom_indices_from_structures",
            "read_acf_dat",
            "read_chgcar",
            "read_doscar",
            "read_vasp_valence_electrons",
        ),
        "onepiece.workflows": (
            "WorkflowResult",
            "apply_operation",
            "apply_operations",
        ),
        "onepiece.xarray_vasp": (
            "chgcar_cumulative_axis_profile",
            "chgcar_line_profile",
            "chgcar_planar_average",
            "chgcar_plane_integrated_electrons",
            "chgcar_to_xarray",
            "doscar_integrated_pdos",
            "doscar_orbital_band_center",
            "doscar_select_energy_window",
            "doscar_to_xarray",
        ),
    }.items()
    for name in names
}


def __getattr__(name: str):
    target_module = _DEPRECATED_ALIASES.get(name)
    if target_module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    _warnings.warn(
        f"Importing {name!r} from the top-level 'onepiece' namespace is "
        f"deprecated; use '{target_module}.{name}' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return getattr(_importlib.import_module(target_module), name)


def __dir__() -> list[str]:
    # Advertise only the curated API to keep notebook tab-completion small;
    # deprecated aliases still resolve through __getattr__.
    return sorted(set(__all__) | set(globals()))
