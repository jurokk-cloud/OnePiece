# OnePiece Function Inventory

Generated from `src/onepiece/**/*.py` using Python AST parsing.

| Kind | Meaning |
|---|---|
| exported | Imported or declared in `onepiece.__init__` |
| function | Module-level public function |
| private_function | Module-level private helper |
| class | Class definition |
| method | Class method |

## `onepiece.__init__`

- `private_function` `__getattr__`
- `private_function` `__dir__`

## `onepiece._compat`

- `function` `install_numpy_pickle_compat`

## `onepiece._polars`

- `function` `get_polars`
- `function` `dataframe_is_polars_safe`
- `function` `series_is_polars_safe`
- `function` `first_non_null`
- `function` `is_polars_safe_value`

## `onepiece.adsorption.copt`

- `function` `is_constrained_optimization`
- `function` `annotate_copt_paths`
- `function` `copt_profile_points`
- `function` `copt_barrier_summary`
- `private_function` `_combined_text`
- `private_function` `_parse_copt_metadata`
- `private_function` `_safe_int`
- `private_function` `_extract_fixbond_constraints`

## `onepiece.adsorption.energies`

- `exported` `add_adsorption_energies`
- `function` `add_recipe_adsorption_energies`
- `exported` `add_catalysis_hub_adsorption_energies`
- `function` `add_elemental_adsorption_energy`
- `function` `add_elemental_adsorption_free_energy`
- `private_function` `_basis_multiplier`
- `exported` `adsorption_view`

## `onepiece.adsorption.formulas`

- `private_function` `_adsorbate_pattern`
- `function` `formula_counts`
- `function` `count_element`
- `function` `count_element_in_structure`
- `function` `row_element_count_map`
- `function` `row_elements`
- `function` `structure_columns_in_frame`
- `function` `get_all_elements`
- `function` `add_element_count_columns`
- `function` `primary_structure`
- `function` `atom_counts`
- `function` `adsorbate_counts_from_structures`
- `function` `guess_adsorbate`
- `function` `surface_key_from_name`

## `onepiece.adsorption.references`

- `exported` `GasReferences`
- `method` `GasReferences.from_mapping`
- `function` `parse_reference_equation`
- `function` `infer_reference_equation_from_formula`
- `function` `default_room_temperature_phase`
- `function` `infer_adsorbate_recipe`
- `function` `infer_adsorption_recipes`
- `private_function` `_default_basis_from_counts`
- `function` `read_onepiece_hdf`
- `function` `read_onepiece_hdfs`
- `function` `annotate_adsorbates`
- `function` `choose_surface_references`
- `function` `assign_surface_references`
- `exported` `assign_references_before_merge`

## `onepiece.ase_analysis`

- `class` `CoordinationEnvironment`
- `method` `CoordinationEnvironment.natoms`
- `method` `CoordinationEnvironment.neighbors_of`
- `method` `CoordinationEnvironment.to_neighbor_graph`
- `method` `CoordinationEnvironment.generalized_coordination_numbers`
- `function` `coordination_environment`
- `private_function` `_coerce_coordination_environment`
- `function` `infer_atomic_layers`
- `function` `identify_surface_atom_indices`
- `function` `slab_thickness`
- `function` `vacuum_thickness`
- `function` `nearest_neighbor_distances`
- `function` `coordination_numbers`
- `function` `generalized_coordination_numbers`
- `exported` `plot_structure_value_3d`
- `exported` `plot_row_metric_3d`
- `exported` `save_dataframe_metric_plots_3d`
- `function` `map_atoms_by_species_and_position`
- `function` `compare_structures_rmsd`
- `function` `adsorbate_surface_distance_summary`
- `function` `classify_adsorption_site`
- `function` `adsorbate_orientation_angle`
- `function` `detect_adsorbate_dissociation`
- `function` `surface_reconstruction_metrics`
- `function` `reaction_path_geometry_summary`
- `function` `compute_d_band_center`
- `function` `compute_d_band_filling`
- `function` `summarize_charge_transfer_by_layer`
- `function` `detect_overlapping_atoms`
- `function` `detect_unphysical_bonds`
- `function` `detect_adsorbate_desorption`
- `function` `add_ase_analysis_descriptors`
- `function` `neighbor_graph`
- `function` `connected_component_count`
- `function` `projected_dos_signal`
- `function` `resolve_row_file_path`
- `private_function` `_slugify`
- `function` `resolve_vasp_file`
- `private_function` `_window_mask`

## `onepiece.automation`

- `function` `annotate_reaction_network`
- `function` `apply_curation_rules`
- `function` `add_structure_descriptors`
- `private_function` `_infer_reaction_state`
- `private_function` `_infer_reaction_system_state`
- `private_function` `_best_reaction_token`
- `private_function` `_split_reaction_token`
- `private_function` `_formula_from_counts`
- `private_function` `_surface_top_z`
- `private_function` `_safe_cell_volume`
- `private_function` `_adsorbate_center_height`

## `onepiece.dftdataframe_import`

- `exported` `crawl_root_to_frame`
- `function` `crawl_root_to_hdf`
- `function` `crawl_calculation_directories`
- `function` `crawl_calculation_paths`
- `function` `create_calculation_frame`
- `function` `add_input_parameter_checks`
- `function` `enrich_electronic_summaries`
- `function` `merge_entropies_file`
- `private_function` `_merge_per_folder_thermochemistry`
- `private_function` `_parse_ase_thermo_output`
- `private_function` `_parse_modes_for_g`
- `private_function` `_active_thermo_filename`
- `private_function` `_walk_with_followlinks`
- `private_function` `_normalize_calculation_directory`
- `private_function` `_resolve_structure_file`
- `private_function` `_sorted_directory_files`
- `private_function` `_make_name`
- `private_function` `_read_structure`
- `private_function` `_load_optional_structure`
- `private_function` `_normalize_token`
- `private_function` `_first_float`
- `private_function` `_safe_energy`
- `private_function` `_safe_fmax`
- `private_function` `_safe_cell_parameter`
- `private_function` `_safe_volume`
- `private_function` `_update_record_with_input_summaries`
- `private_function` `_update_record_with_frequency_summaries`
- `private_function` `_extract_structure_input_parameters`
- `private_function` `_parse_incar_file`
- `private_function` `_parse_incar_value`
- `private_function` `_parse_kpoints_file`
- `private_function` `_coerce_float_parameter`
- `private_function` `_series_mode_scalar`
- `private_function` `_read_frequency_summary`
- `private_function` `_parse_ase_frequency_modes`
- `private_function` `_parse_outcar_frequencies`
- `private_function` `_update_record_with_electronic_summaries`
- `private_function` `_electronic_summary_with_cache`
- `private_function` `_ensure_electronic_summary_columns`
- `private_function` `_base_cache_path`
- `private_function` `_electronic_cache_path`
- `private_function` `_base_cache_key`
- `private_function` `_electronic_cache_key`
- `private_function` `_load_cached_record`
- `private_function` `_write_cached_record`
- `private_function` `_default_electronic_summary_record`
- `private_function` `_resolve_electronic_workers`
- `private_function` `_electronic_summary_from_path`

## `onepiece.frame_utils`

- `function` `ensure_name_index`
- `function` `row_name`
- `function` `first_present`

## `onepiece.ir`

- `function` `reference_ir_bands`
- `function` `match_ir_frequencies`
- `function` `add_ir_peak_matches`
- `function` `adsorption_frequency_plot_table`
- `exported` `plot_adsorption_energy_vs_frequency`
- `private_function` `_resolve_ir_reference_species`
- `private_function` `_adsorption_energy_for_species`
- `private_function` `_frequency_window_center`

## `onepiece.phase_diagrams`

- `class` `PhaseScanResult`
- `class` `PhaseFieldResult`
- `class` `NamedPhaseFieldResult`
- `class` `GroupedPhaseDiagramResult`
- `function` `default_phase_variables`
- `function` `phase_symbol_locals`
- `function` `to_sympy_expression`
- `function` `substitute_variables`
- `function` `evaluate_expression`
- `function` `stable_phase_scan`
- `function` `estimate_phase_scan_slopes`
- `function` `solve_phase_boundaries`
- `function` `build_surface_free_energy_expressions`
- `function` `build_corrected_phase_expressions`
- `function` `summarize_phase_field_stability`
- `function` `build_phase_field_grid`
- `function` `build_surface_phase_diagram`
- `function` `build_grouped_surface_phase_diagrams`

## `onepiece.projects.persistence`

- `function` `build_project_payload`
- `function` `restore_project_payload`

## `onepiece.provenance`

- `class` `ReferenceScheme`
- `method` `ReferenceScheme.to_dict`
- `method` `ReferenceScheme.computational_hydrogen_electrode`
- `method` `ReferenceScheme.gas_phase`
- `class` `ProvenanceAgent`
- `class` `ProvenanceEntity`
- `class` `ProvenanceActivity`
- `class` `ProvenanceRecord`
- `method` `ProvenanceRecord.to_dict`
- `class` `ProvenanceValidationResult`
- `function` `now_utc_iso`
- `function` `file_checksum`
- `function` `entity_from_path`
- `function` `onepiece_agent`
- `function` `local_python_agent`
- `function` `build_dataset_provenance`
- `function` `workflow_activity`
- `function` `validate_provenance_payload`
- `function` `provenance_graph`
- `function` `ro_crate_metadata`
- `function` `attach_workflow_audit_log`
- `private_function` `_entity_to_ro_crate`
- `private_function` `_agent_to_ro_crate`
- `private_function` `_activity_to_ro_crate`
- `private_function` `_list_field`
- `private_function` `_validate_entities`
- `private_function` `_validate_agents`
- `private_function` `_validate_activities`
- `private_function` `_agent_id`
- `private_function` `_json_safe_operation`
- `private_function` `_json_safe_value`

## `onepiece.qa`

- `class` `SelfTestResult`
- `exported` `bundled_catalysis_hub_dataset`
- `function` `run_catalysis_hub_self_test`
- `function` `run_fair_provenance_audit`
- `function` `format_self_test_result`

## `onepiece.services.dataset_service`

- `class` `DatasetQuery`
- `function` `apply_dataset_query`
- `function` `filter_text`
- `function` `filter_any_token`
- `function` `search_haystack`
- `function` `path_tail`
- `function` `apply_materials_search`
- `private_function` `_apply_scalar_filters`
- `private_function` `_apply_scalar_filters_with_polars`
- `private_function` `_filter_text_with_polars`
- `function` `query_description`
- `private_function` `_normalize_query`
- `private_function` `_fallback_row_keys`
- `private_function` `_row_elements`
- `function` `row_element_counts`
- `function` `row_atom_counts`
- `private_function` `_anonymous_formula`
- `private_function` `_normalize_anonymous_formula`
- `private_function` `_parse_element_tokens`
- `private_function` `_looks_like_element`
- `function` `record_type_series`
- `private_function` `_range_is_restrictive`
- `private_function` `_finite`

## `onepiece.sources.core`

- `function` `combined_active_database`
- `function` `store_source`
- `function` `source_descriptors`
- `function` `restore_source_descriptors`
- `function` `source_fingerprint`
- `function` `prepare_source_frame`
- `exported` `read_dataset_path`
- `exported` `read_hdf_path`
- `function` `read_uploaded_hdf`
- `function` `map_adsorption_columns`
- `function` `apply_import_options`
- `function` `apply_dataset_kind`
- `function` `gas_reference_candidates`
- `function` `detected_gas_reference_values`
- `function` `detect_source_profile`
- `function` `source_profile_summary`
- `private_function` `_explicit_dataset_kind`
- `private_function` `_find_gas_candidates`
- `private_function` `_find_gas_candidates_with_polars`
- `private_function` `_formula_signature`
- `private_function` `_formula_counts`
- `private_function` `_normalize_text`
- `private_function` `_source_id`
- `private_function` `_friendly_hdf_read_error`
- `private_function` `_hdf_keys`

## `onepiece.storage`

- `class` `StorageConfig`
- `class` `DatasetManifest`
- `function` `resolve_storage_config`
- `function` `ensure_storage_layout`
- `function` `dataset_directory`
- `function` `dataset_manifest_path`
- `exported` `save_dataset`
- `exported` `load_dataset`
- `function` `read_dataset_manifest`
- `function` `detect_storage_format`
- `function` `cache_key_for_paths`
- `function` `write_cache_payload`
- `function` `read_cache_payload`
- `private_function` `_load_manifest_dataset`
- `private_function` `_object_sidecar_columns`
- `private_function` `_is_simple_scalar`
- `private_function` `_is_nan_like`
- `private_function` `_slugify_dataset_id`
- `private_function` `_now_iso`
- `private_function` `_onepiece_version`

## `onepiece.thermo`

- `function` `is_gas_phase_row`
- `exported` `gas_free_energy`
- `exported` `adsorbate_free_energy`
- `exported` `add_gibbs_free_energy`

## `onepiece.vasp`

- `class` `ChgcarData`
- `method` `ChgcarData.grid_shape`
- `class` `DoscarData`
- `method` `DoscarData.natoms`
- `method` `DoscarData.spin_polarized`
- `function` `read_acf_dat`
- `function` `read_chgcar`
- `function` `integrate_atomic_electron_populations`
- `function` `read_vasp_valence_electrons`
- `function` `compute_atomic_charges`
- `function` `add_atomic_charge_descriptors`
- `function` `atomic_magnetic_moments_from_atoms`
- `exported` `add_atomic_magnetic_moment_descriptors`
- `function` `add_adsorbate_charge_descriptors`
- `exported` `add_atomic_reference_difference_descriptors`
- `function` `read_doscar`
- `function` `integrate_total_dos`
- `function` `integrate_projected_dos`
- `function` `add_projected_dos_descriptors`
- `function` `atomic_charge_long_table`
- `function` `doscar_projected_long_table`
- `function` `matched_surface_atom_indices_from_structures`
- `function` `adsorbate_atom_indices_from_structures`
- `private_function` `_read_doscar_fermi_level`
- `private_function` `_select_total_dos_channel`
- `private_function` `_resolve_orbital_names`
- `private_function` `_integrate_signal`
- `private_function` `_resolve_row_file_path`
- `private_function` `_resolve_existing_charge_path`
- `private_function` `_resolve_vasp_file`
- `private_function` `_resolve_atomic_populations`
- `private_function` `_compare_acf_coordinates`
- `private_function` `_gas_phase_charge_references`
- `private_function` `_gas_phase_atomic_array_references`
- `private_function` `_aligned_reference_difference_vector`
- `private_function` `_as_array`
- `private_function` `_row_atoms`
- `private_function` `_write_per_element_statistics`
- `private_function` `_parse_species_valence_values`
- `private_function` `_expand_species_values`
- `private_function` `_atom_indices_for_elements`

## `onepiece.workflows.engine`

- `class` `WorkflowResult`
- `function` `apply_operations`
- `function` `apply_operation`
- `private_function` `_derive_binary`
- `private_function` `_derive_scalar`
- `private_function` `_derive_contains`
- `private_function` `_derive_constant`
- `private_function` `_fill_missing`
- `private_function` `_replace_value`
- `private_function` `_count_element`
- `private_function` `_count_all_elements`
- `private_function` `_group_rank`
- `private_function` `_group_rank_with_polars`
- `private_function` `_derive_recipe_adsorption`
- `private_function` `_derive_reaction_network`
- `private_function` `_derive_curation`
- `private_function` `_derive_structure_descriptors`
- `private_function` `_derive_vasp_charge_descriptors`
- `private_function` `_derive_vasp_pdos_descriptors`
- `private_function` `_derive_ase_analysis_descriptors`
- `private_function` `_derive_input_parameter_checks`
- `private_function` `_derive_ir_peak_matches`
- `private_function` `_exclude_exact_names`
- `private_function` `_exclude_by_match_rules`
- `private_function` `_derive_adsorption_columns`
- `private_function` `_derive_gibbs_free_energy`
- `private_function` `_derive_gibbs_adsorption`
- `private_function` `_derive_expression`
- `private_function` `_filter_rows`
- `private_function` `_flag_filter`
- `private_function` `_apply_numeric_operator`
- `private_function` `_filter_mask`
- `private_function` `_evaluate_expression`
- `private_function` `_numeric`
- `private_function` `_valid_identifier`
- `private_function` `_normalized_gas_references`

## `onepiece.workflows.registry`

- `function` `operation_handlers`

## `onepiece.xarray_vasp`

- `function` `chgcar_to_xarray`
- `function` `chgcar_planar_average`
- `function` `chgcar_plane_integrated_electrons`
- `function` `chgcar_cumulative_axis_profile`
- `function` `chgcar_line_profile`
- `function` `doscar_to_xarray`
- `function` `doscar_select_energy_window`
- `function` `doscar_integrated_pdos`
- `function` `doscar_orbital_band_center`
- `private_function` `_ensure_chgcar_dataset`
- `private_function` `_ensure_doscar_dataset`
- `private_function` `_validate_chgcar_var`
- `private_function` `_select_site_projected_signal`
- `private_function` `_normalize_orbital_request`
