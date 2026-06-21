# OnePiece Backend API Contract

This document captures the stable backend entry points that OnePiece Studio should use.
The goal is simple:

- `onepiece` owns dataset semantics, workflow execution, and project state
- `onepiece_studio` gathers user intent and renders the returned results

When new functionality is added, it should land in this contract first and only
then be surfaced in OnePiece Studio widgets.

## Design Rule

OnePiece Studio should not implement scientific DataFrame logic itself. It should call
backend functions that accept plain Python values or `pandas.DataFrame` objects
and return structured results.

Preferred pattern:

```python
from onepiece.workflows import apply_operations

result = apply_operations(frame, operations)
active = result.dataframe
```

Avoid this pattern in OnePiece Studio pages:

```python
# discouraged inside onepiece_studio.ui.*
frame["new_column"] = ...
frame = frame[frame["E"] < 0]
```

## Public Entry Points

## Source Handling

These functions describe what a dataset is and how it should be normalized when
it enters the application.

- `onepiece.read_hdf_path(path, key="df")`
- `onepiece.read_uploaded_hdf(uploaded, key="df")`
- `onepiece.prepare_source_frame(frame, label, path, source_id)`
- `onepiece.apply_import_options(frame, options)`
- `onepiece.map_adsorption_columns(frame, options)`
- `onepiece.detect_source_profile(frame)`
- `onepiece.source_profile_summary(profile, capabilities)`
- `onepiece.detected_gas_reference_values(frame)`
- `onepiece.gas_reference_candidates(frame)`
- `onepiece.store_source(state, frame, ...)`
- `onepiece.combined_active_database(state, base)`
- `onepiece.source_descriptors(state)`
- `onepiece.restore_source_descriptors(state, descriptors)`

### Source Profile Output

`detect_source_profile(...)` returns a dictionary with:

```python
{
    "profile": "surface_adsorption_local_hdf",
    "capabilities": ["adsorption_energy", "ase_structure_view", ...],
    "summary": "Surface adsorption dataset with structure and energy columns."
}
```

OnePiece Studio should use this metadata to decide what to show, rather than guessing from
its own widget code.

## Workflow Execution

These functions run ordered analysis steps on a DataFrame.

- `onepiece.apply_operation(frame, operation)`
- `onepiece.apply_operations(frame, operations)`
- `onepiece.WorkflowResult`

### Workflow Operation Shape

The stable workflow payload is:

```python
{
    "kind": "derive_constant",
    "params": {"column": "adsorbate_ref", "value": "Cu-211"},
    "label": "Set adsorbate reference",
    "enabled": True,
}
```

OnePiece Studio may help users compose these payloads, but it should not execute their
semantics itself.

`apply_operations(...)` returns a `WorkflowResult` with three fields:

- `dataframe`: the transformed DataFrame
- `messages`: recoverable failure messages
- `audit_log`: one JSON-native activity record per enabled operation

The audit log is the backend provenance contract for dataframe transformations.
Each activity records:

- operation kind and label
- input and output dataframe entities
- operation parameters
- row count before and after
- columns added or removed
- execution status
- error text for failed steps

This is intentionally close to AiiDA-style provenance thinking, but scoped to
post-processing workflows: the operation that created a derived column should be
recoverable from the saved project or manifest.

## Query and Controlroom Filtering

These functions define how the active dataset is filtered.

- `onepiece.DatasetQuery`
- `onepiece.apply_dataset_query(frame, query, row_states=None)`
- `onepiece.apply_materials_search(frame, query_dict)`
- `onepiece.filter_text(frame, query, columns)`
- `onepiece.filter_any_token(frame, tokens, columns)`
- `onepiece.query_description(query)`

OnePiece Studio should build a `DatasetQuery` instance from the visible controls and then
render the returned filtered DataFrame.

## Scientific Operations

These are the main scientific transforms currently exposed by the backend.

### Adsorption and References

- `onepiece.assign_surface_references(...)`
- `onepiece.assign_references_before_merge(...)`
- `onepiece.add_adsorption_energies(...)`
- `onepiece.add_elemental_adsorption_energy(...)`
- `onepiece.add_elemental_adsorption_free_energy(...)`
- `onepiece.add_recipe_adsorption_energies(...)`

For publication-grade catalysis work, adsorption operations should keep the
reference scheme visible. A value such as `adsorption_energy = -0.72 eV` is not
reusable without the clean-surface reference, gas/electrochemical basis, and
corrections used to construct it.
- `onepiece.add_catalysis_hub_adsorption_energies(...)`
- `onepiece.copt_profile_points(...)`
- `onepiece.copt_barrier_summary(...)`

### Thermochemistry

- `onepiece.gas_free_energy(...)`
- `onepiece.adsorbate_free_energy(...)`
- `onepiece.add_gibbs_free_energy(...)`

### VASP Charge And DOS

- `onepiece.read_chgcar(...)`
- `onepiece.integrate_atomic_electron_populations(...)`
- `onepiece.read_vasp_valence_electrons(...)`
- `onepiece.compute_atomic_charges(...)`
- `onepiece.add_atomic_charge_descriptors(...)`
- `onepiece.add_adsorbate_charge_descriptors(...)`
- `onepiece.read_doscar(...)`
- `onepiece.integrate_total_dos(...)`
- `onepiece.integrate_projected_dos(...)`
- `onepiece.add_projected_dos_descriptors(...)`

### Automation Blocks

- `onepiece.apply_curation_rules(...)`
- `onepiece.annotate_reaction_network(...)`
- `onepiece.add_structure_descriptors(...)`

## Provenance And FAIR Metadata

These functions define how derived datasets record scientific context:

- `onepiece.ReferenceScheme`
- `onepiece.build_dataset_provenance(...)`
- `onepiece.validate_provenance_payload(...)`
- `onepiece.provenance_graph(...)`
- `onepiece.ro_crate_metadata(...)`
- `onepiece.save_dataset(..., reference_scheme=..., workflow_audit_log=...)`

The key rule is that reference conventions are part of the data product. A
managed dataset that contains adsorption energies or free energies should carry
a `ReferenceScheme` in manifest provenance.

Recommended conventions:

- gas-phase thermochemistry: `ReferenceScheme.gas_phase(...)`
- electrochemistry: `ReferenceScheme.computational_hydrogen_electrode(...)`
- imported article data: record citation, DOI/URL, license, and conversion notes
  in manifest metadata

For external datasets from research articles, normalize the table first, then
save it as a managed OnePiece dataset with provenance before using it in the UI
or tutorial examples.

## Crawl And Import

These backend functions define the calculation-root crawl layer.

- `onepiece.crawl_root_to_frame(...)`
- `onepiece.crawl_root_to_hdf(...)`
- `onepiece.crawl_calculation_directories(...)`
- `onepiece.crawl_calculation_paths(...)`
- `onepiece.create_calculation_frame(...)`
- `onepiece.enrich_electronic_summaries(...)`
- `onepiece.merge_entropies_file(...)`

### Crawl Input Contract

The stable crawl parameters are:

- `root`: root directory containing the calculation folders
- `calc_file`: preferred structure file to read first
- `thermo_filename`: per-folder thermo filename such as `out.txt`
- `read_electronic_files`: whether to run the second-stage `CHGCAR`/`DOSCAR`
  enrichment
- `electronic_workers`: thread count for that enrichment stage
- `query`: optional post-crawl `DataFrame.query(...)` string
- `progress_callback`: callback with `(completed, total, current_path)`

Recommended large-dataset pattern:

```python
from onepiece import crawl_root_to_frame, enrich_electronic_summaries

base = crawl_root_to_frame(root, read_electronic_files=False)
enriched = enrich_electronic_summaries(base, workers=12)
```

## Project Persistence

Project files should be backend-native so that the saved meaning of a project is
not tied to Streamlit internals.

- `onepiece.build_project_payload(state, source_rows, active_rows, control_state)`
- `onepiece.restore_project_payload(state, payload)`

### Project Payload Shape

The backend payload currently stores:

```python
{
    "project_version": 1,
    "saved_at": "...",
    "query": {...},
    "workflow": [...],
    "row_states": {...},
    "workbook_edits": {...},
    "sources": [...],
    "saved_views": {...},
    "audit_log": [...],
}
```

The saved project format is defined by these backend-native keys.

## Responsibilities Boundary

### OnePiece owns

- scientific formulas
- dataset typing and capability detection
- query semantics
- workflow semantics
- project-state meaning
- reproducible transforms

### OnePiece Studio owns

- layouts, tabs, and widgets
- parameter capture
- chart rendering
- table presentation
- file downloads
- ASE open/view actions

If a new OnePiece Studio feature needs to answer the question "what does this operation
mean?", that logic probably belongs in `onepiece`.
