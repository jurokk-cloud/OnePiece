# API And CLI Usage

## Command Line Interface

Install the UI distribution for these commands:

```bash
pip install onepiece-studio
```

The package installs one primary command:

```bash
onepiece-studio
```

Available entry points:

### Demo

```bash
onepiece-studio demo
```

Starts the local demonstration UI.

### HDF

```bash
onepiece-studio hdf "/path/to/database.hdf" --key df --title "Local Database"
```

Starts the UI on a local pandas HDF file.

### QA

```bash
onepiece-studio qa
```

Runs the bundled package self-test with the packaged Catalysis-Hub reference
dataset.

You can also point it at a specific Catalysis-Hub-style dataset:

```bash
onepiece-studio qa --dataset "/path/to/catalysis_hub_subset.hdf"
```

## Python Backend API

Install the backend distribution for direct Python use:

```bash
pip install onepiece
```

To enable the optional Polars acceleration layer for large tabular filtering,
ranking, and metadata search paths:

```bash
pip install "onepiece[performance]"
```

The backend lives in `onepiece`.

Typical direct imports:

```python
from onepiece import (
    ReferenceScheme,
    DatasetQuery,
    apply_operations,
    assign_surface_references,
    add_adsorption_energies,
    add_gibbs_free_energy,
    add_atomic_charge_descriptors,
    add_projected_dos_descriptors,
    integrate_projected_dos,
    read_chgcar,
    read_doscar,
    ro_crate_metadata,
    run_catalysis_hub_self_test,
    save_dataset,
)
```

### Run A Workflow

```python
from onepiece import apply_operations

result = apply_operations(
    frame,
    [
        {"kind": "derive_adsorption_columns"},
        {"kind": "derive_structure_descriptors"},
    ],
)

active = result.dataframe
```

### Save A FAIR Dataset

```python
from onepiece import ReferenceScheme, save_dataset
from onepiece.storage import ensure_storage_layout, resolve_storage_config

scheme = ReferenceScheme.gas_phase(
    name="CO2_H2_H2O",
    gas_references_eV={"CO2": -22.1, "H2": -6.8, "H2O": -14.2},
)

config = ensure_storage_layout(resolve_storage_config(".onepiece"))
manifest_path = save_dataset(
    active,
    dataset_id="my-catalysis-dataset",
    config=config,
    source_path="created_frame.hdf",
    reference_scheme=scheme,
    workflow_audit_log=result.audit_log,
    metadata={
        "license": "CC-BY-4.0",
        "citation": "Replace with article or dataset citation.",
    },
)
```

Audit and export the saved dataset:

```bash
onepiece-studio fair-audit .onepiece/workspace/my-catalysis-dataset \
  --require-reference-scheme \
  --require-publication-metadata

onepiece-studio ro-crate .onepiece/workspace/my-catalysis-dataset
```

### Query A Dataset

```python
from onepiece import DatasetQuery, apply_dataset_query

query = DatasetQuery(
    text_include="Cu-211",
    drop_test=True,
    numeric_ranges={"E": (-130.0, -100.0)},
)

filtered = apply_dataset_query(frame, query)
```

### Run The Bundled Self-Test In Python

```python
from onepiece import run_catalysis_hub_self_test, format_self_test_result

result = run_catalysis_hub_self_test()
print(format_self_test_result(result))
```

## VASP File Integration

The backend can also read VASP `CHGCAR` and `DOSCAR` files directly.

```python
from onepiece import (
    add_atomic_charge_descriptors,
    add_projected_dos_descriptors,
    integrate_projected_dos,
    read_chgcar,
    read_doscar,
)

chgcar = read_chgcar("/path/to/CHGCAR")
doscar = read_doscar("/path/to/DOSCAR")
cu_d_states = integrate_projected_dos(
    doscar,
    atom_indices=[0, 1, 2, 3],
    orbitals=["d"],
    energy_window=(-2.0, 0.0),
)
```

For dataframe workflows, attach descriptors directly to rows:

```python
frame = add_atomic_charge_descriptors(frame, calculation_path_column="Path")
frame = add_projected_dos_descriptors(
    frame,
    [
        {
            "column": "cu_d_pdos_below_ef",
            "elements": ["Cu"],
            "orbitals": ["d"],
            "energy_window": (-2.0, 0.0),
        }
    ],
    calculation_path_column="Path",
)
```

## Crawl API

OnePiece can also build a dataframe directly from a calculation root.

The most important crawl inputs are:

- `root`: root folder containing many calculation folders
- `calc_file`: preferred structure file to read first, usually `final.traj`
- `thermo_filename`: per-folder thermochemistry file, usually `out.txt`
- `read_electronic_files`: whether `CHGCAR` and `DOSCAR` summaries should be
  read in a second stage
- `electronic_workers`: worker count for the parallel electronic enrichment
  stage
- `query`: optional `DataFrame.query(...)` filter applied after crawling

Example:

```python
from onepiece import crawl_root_to_frame, enrich_electronic_summaries

frame = crawl_root_to_frame(
    "path/to/calculations",
    calc_file="final.traj",
    thermo_filename="out.txt",
    read_electronic_files=True,
    electronic_workers=8,
    query="Cu > 0 and E < -10",
)

# Or in two explicit stages for very large datasets:
base = crawl_root_to_frame(
    "path/to/calculations",
    read_electronic_files=False,
)
enriched = enrich_electronic_summaries(base, workers=8)
```

## Python UI Usage

The frontend package lives in `onepiece_studio`.

### Existing DataFrame

```python
import pandas as pd

from onepiece_studio import DataFrameSource, OnePieceStudioConfig
from onepiece_studio.ui.streamlit_app import run_app

df = pd.DataFrame(
    {
        "id": ["mp-1", "mp-2"],
        "formula": ["Fe2O3", "TiO2"],
        "energy_ev": [-12.4, -8.2],
    }
)

source = DataFrameSource(df, name="materials")
config = OnePieceStudioConfig(primary_key="id")
run_app(source, config)
```

### HDF File

```python
from onepiece_studio import HDFSource, OnePieceStudioConfig
from onepiece_studio.ui.streamlit_app import run_app

source = HDFSource("/path/to/database.hdf", key="df")
config = OnePieceStudioConfig(
    title="Local Database",
    primary_key="Name",
    structure_columns=["struc", "CONTCAR"],
    metric_columns=["E", "fmax"],
)

run_app(source, config)
```

### OnePiece-Like Object

Objects with one of these interfaces can be wrapped:

- `to_dataframe()`
- `.dataframe`
- `.df`

```python
from onepiece_studio import OnePieceSource, OnePieceStudioConfig
from onepiece_studio.ui.streamlit_app import run_app

source = OnePieceSource(onepiece_database, name="analysis subset")
config = OnePieceStudioConfig(title="OnePiece-backed Database", primary_key="Name")
run_app(source, config)
```
