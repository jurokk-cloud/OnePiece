# OnePiece + OnePiece Studio Architecture Blueprint

This document defines the architectural step for turning OnePiece Studio into a thin
frontend over a proper OnePiece backend.

## Recommended Package Name

The best name for the combined software stack is:

`onepiece-studio`

Why this name works:

- `onepiece` keeps the scientific and workflow identity that already exists
- `studio` communicates that this is not just a parser or a single-purpose tool,
  but a full local workbench for database analysis, curation, visualization, and
  reproducible workflows
- it keeps the product name aligned with the frontend package name and the public
  install surface

Recommended naming split:

- backend package: `onepiece`
- frontend package: `onepiece_studio`
- backend distribution: `onepiece`
- frontend distribution / product name: `onepiece-studio`

## Design Goal

The target architecture is:

- `onepiece` executes all DataFrame operations, scientific formulas, workflow
  steps, source detection, and project persistence semantics
- `onepiece_studio` only collects user intent, sends commands to the backend, and renders
  the results

This follows the useful part of SAP-style UI architecture:

- backend owns business logic
- frontend owns interaction and presentation
- metadata describes what the UI should offer

## Top-Level Monorepo Layout

```text
OnePiece Studio/
  pyproject.toml
  ui/
    pyproject.toml
  src/
    onepiece/
    onepiece_studio/
  tests/
    onepiece/
    onepiece_studio/
  docs/
  examples/
```

This is the cleanest first step because it avoids immediate multi-repo overhead
while still separating responsibilities.

## Backend Package: `onepiece`

The backend package should contain no Streamlit code.

```text
src/onepiece/
  __init__.py
  sources/
    __init__.py
    hdf.py
    dataframe.py
    detection.py
    catalog.py
  schema/
    __init__.py
    columns.py
    annotations.py
    capabilities.py
    profiles.py
  models/
    __init__.py
    dataset.py
    operation.py
    query.py
    result.py
    project.py
  operations/
    __init__.py
    filters.py
    derive.py
    references.py
    adsorption.py
    thermo.py
    curation.py
    reaction_network.py
    descriptors.py
    sources.py
  workflows/
    __init__.py
    engine.py
    recipes.py
    registry.py
    audit.py
  services/
    __init__.py
    dataset_service.py
    workflow_service.py
    analysis_service.py
    project_service.py
```

### What `onepiece` owns

- HDF loading and normalization
- source-family detection
- capability detection
- column metadata and annotations
- adsorption energy and Gibbs energy calculations
- surface-reference assignment
- reaction-network construction
- curation and descriptor generation
- workflow execution
- project-state semantics
- backend audit log

## Frontend Package: `onepiece_studio`

The frontend package should mostly be a controller and presentation layer.

```text
ui/src/onepiece_studio/
  __init__.py
  app.py
  cli.py
  session/
    __init__.py
    state.py
    mapping.py
  ui/
    __init__.py
    layout.py
    themes.py
    widgets.py
  pages/
    __init__.py
    workflow.py
    controlroom.py
    records.py
    visualize.py
    adsorption.py
    data_sources.py
    data_management.py
    schema.py
  presenters/
    __init__.py
    tables.py
    charts.py
    metrics.py
    details.py
  integrations/
    __init__.py
    ase_viewer.py
```

### What `onepiece_studio` owns

- Streamlit layout
- tabs, sections, and controls
- user input capture
- session-level UI state
- result rendering
- chart display
- ASE view trigger UI
- export buttons

### What `onepiece_studio` must stop owning

- direct scientific DataFrame transformations
- filter semantics
- adsorption formulas
- curation rules
- source-detection rules
- workflow execution internals

## Backend Contracts

The clean split depends on stable backend contracts.

### Dataset

```python
@dataclass
class Dataset:
    dataframe: pd.DataFrame
    source_profile: str
    capabilities: set[str]
    schema: DatasetSchema
    provenance: dict
```

### Operation

```python
@dataclass
class Operation:
    kind: str
    params: dict
    label: str | None = None
    enabled: bool = True
```

### Workflow Result

```python
@dataclass
class WorkflowResult:
    dataset: Dataset
    messages: list[str]
    audit_log: list[dict]
```

### Query

```python
@dataclass
class DatasetQuery:
    text_include: str = ""
    text_exclude: str = ""
    materials: dict | None = None
    numeric: dict | None = None
    visible_states: list[str] | None = None
```

## Metadata and Capability Layer

This is the SAP-like part that is most worth copying.

Each source should be classified into a `source_profile`, for example:

- `surface_adsorption_local_hdf`
- `reaction_database_local_hdf`
- `phase_diagram_local_hdf`
- `bulk_materials_local_hdf`
- `generic_dataframe`

Each dataset should also expose `capabilities`, for example:

- `filtering`
- `adsorption_energy`
- `gibbs_energy`
- `reaction_network`
- `curation`
- `structure_descriptors`
- `ase_structure_view`
- `phase_diagram`

The UI should read these and adapt what it offers.

## Command Flow

OnePiece Studio should build structured commands, and OnePiece should execute them.

Example:

```python
operations = [
    {"kind": "assign_surface_references", "params": {}},
    {"kind": "compute_adsorption_energy", "params": {"mode": "E"}},
    {"kind": "compute_gibbs_adsorption_energy", "params": {"temperature": 523.15}},
    {"kind": "curation", "params": {"action": "mark_review"}},
]
result = workflow_service.run(dataset, operations)
```

OnePiece Studio should never directly mutate the DataFrame for these operations.

## Query Flow

Controlroom should become a backend query client.

Example:

```python
query = DatasetQuery(
    text_include="Cu-211",
    text_exclude="broken",
    materials={"include_elements": ["Cu", "C"], "element_mode": "all"},
    numeric={"E": (-130.0, -100.0)},
    visible_states=["included", "review", "reference"],
)
result = dataset_service.query(dataset, query)
```

OnePiece Studio should render the controls and display `result.dataset.dataframe`.

## Project File Semantics

Project files should store backend-native concepts, not only Streamlit-local
state keys.

```json
{
  "project_version": 1,
  "sources": [],
  "workflow": [],
  "query": {},
  "row_states": {},
  "workbook_edits": {},
  "saved_views": {}
}
```

OnePiece Studio can still store presentational state separately, but the scientific state
must belong to OnePiece.

## First Migration Targets

These functions should move first because they currently sit too close to the UI:

- `onepiece_studio.ui.workflow_builder._apply_operation`
- Controlroom filter execution
- source import preparation
- gas-reference auto-detection
- standard workflow recipes
- project-payload semantics

Current source locations to extract from:

- `ui/src/onepiece_studio/ui/workflow_builder.py`
- `ui/src/onepiece_studio/ui/controlroom.py`
- `ui/src/onepiece_studio/ui/data_sources.py`
- `src/onepiece/adsorption.py`
- `src/onepiece/automation.py`
- `src/onepiece/thermo.py`

## Concrete Migration Phases

### Phase 1: Create `src/onepiece`

Move these modules into the backend:

- `onepiece_studio` adsorption logic -> `onepiece.operations.adsorption`
- `onepiece_studio` automation logic -> `onepiece.operations.reaction_network`,
  `onepiece.operations.curation`, `onepiece.operations.descriptors`
- `onepiece_studio` thermochemistry logic -> `onepiece.operations.thermo`

Goal:

- OnePiece Studio still imports successfully
- scientific logic gets a real backend home

### Phase 2: Move workflow execution out of the UI

Create:

- `onepiece.workflows.engine`
- `onepiece.workflows.registry`

Move:

- operation dispatch from `onepiece_studio.ui.workflow_builder`

Goal:

- OnePiece Studio no longer executes DataFrame operations itself
- OnePiece Studio calls OnePiece workflow services

### Phase 3: Move query and filter logic out of the UI

Create:

- `onepiece.operations.filters`
- `onepiece.services.dataset_service`

Move:

- Controlroom filter application
- materials search execution
- source query helpers

Goal:

- Controlroom becomes a frontend over backend query execution

### Phase 4: Move source detection and import preparation

Create:

- `onepiece.sources.detection`
- `onepiece.sources.hdf`

Move:

- gas-reference detection
- adsorption import mapping
- source-family detection

Goal:

- source behavior becomes metadata-driven

### Phase 5: Move project semantics

Create:

- `onepiece.projects.model`
- `onepiece.projects.persistence`

Move:

- project payload structure
- save/load semantics

Goal:

- saved projects remain valid independently of Streamlit widget internals

## Test Split

### OnePiece tests

Place under:

```text
tests/onepiece/
```

Should cover:

- scientific correctness
- adsorption energy
- Gibbs energy
- source detection
- workflow execution
- curation semantics
- reaction-network semantics
- descriptor correctness

