# From Notebook To FAIR Dataset

This page shows the intended end-to-end workflow for turning an exploratory
ASE/pandas notebook into a reusable OnePiece dataset.

## 1. Start With A DataFrame

```python
import pandas as pd

from onepiece import read_hdf_path

frame = read_hdf_path("created_frame.hdf", key="df")
```

The table should follow the canonical schema:

```text
Name, E, Formula, Path, struc, fmax
```

## 2. Add Scientific Operations

```python
from onepiece.workflows import apply_operations

workflow = apply_operations(
    frame,
    [
        {"kind": "count_all_elements", "label": "Count elements"},
        {"kind": "derive_structure_descriptors", "label": "Structure descriptors"},
        {"kind": "derive_curation", "label": "Quality flags"},
    ],
)

derived = workflow.dataframe
audit_log = workflow.audit_log
```

The audit log records which operation created which columns.

## 3. Attach Reference Metadata

```python
from onepiece import ReferenceScheme

scheme = ReferenceScheme.gas_phase(
    name="CO2_H2_H2O",
    gas_references_eV={"CO2": -22.1, "H2": -6.8, "H2O": -14.2},
)
```

For electrochemical work, use:

```python
scheme = ReferenceScheme.computational_hydrogen_electrode(
    h2_eV=-6.8,
    h2o_eV=-14.2,
    potential_V_RHE=1.23,
    pH=14,
)
```

## 4. Save A Managed Dataset

```python
from onepiece import save_dataset
from onepiece.storage import ensure_storage_layout, resolve_storage_config

config = ensure_storage_layout(resolve_storage_config(".onepiece"))
manifest_path = save_dataset(
    derived,
    dataset_id="my-catalysis-dataset",
    config=config,
    source_path="created_frame.hdf",
    reference_scheme=scheme,
    workflow_audit_log=audit_log,
    metadata={
        "license": "CC-BY-4.0",
        "citation": "Replace with article or internal dataset citation.",
        "description": "Derived OnePiece dataset from local ASE/VASP workflow.",
    },
)
```

This writes:

```text
.onepiece/workspace/my-catalysis-dataset/manifest.json
.onepiece/workspace/my-catalysis-dataset/table.parquet
.onepiece/workspace/my-catalysis-dataset/object_columns.pkl
```

## 5. Audit The Dataset

```bash
onepiece-studio fair-audit .onepiece/workspace/my-catalysis-dataset \
  --require-reference-scheme \
  --require-publication-metadata
```

## 6. Export Metadata

```bash
onepiece-studio ro-crate .onepiece/workspace/my-catalysis-dataset
```

This creates an RO-Crate-style `ro-crate-metadata.json` next to the manifest.

## 7. Open In The UI

```bash
onepiece-studio hdf created_frame.hdf --key df
```

For managed datasets, use the Python API or add a UI entry point that loads the
manifest-backed dataset through `onepiece.load_dataset(...)`.

## What The Workflow Preserves

The final dataset preserves:

- table columns
- ASE objects through object sidecars
- source path and source fingerprint
- workflow operations
- reference scheme
- software agents
- citation and license metadata

That is the difference between a useful notebook and a reusable scientific
dataset.

