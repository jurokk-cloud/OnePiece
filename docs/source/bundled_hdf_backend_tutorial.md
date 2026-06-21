# Bundled HDF Backend Tutorial

This tutorial uses the HDF file that ships with OnePiece:

```text
src/onepiece/data/catalysis_hub_co2_subset.hdf
```

We treat it as if it were produced by a crawl. In other words, the HDF is the
frozen table that came out of a previous data-acquisition step.

## 1. Load The HDF

```python
import pandas as pd

from onepiece import bundled_catalysis_hub_dataset
from onepiece.sources import read_hdf_path

path = bundled_catalysis_hub_dataset()
frame = read_hdf_path(path, key="df")

frame.shape
```

Expected shape:

```text
(133, 31)
```

Important columns:

```python
[
    "Name",
    "Equation",
    "surfaceComposition",
    "facet",
    "reactionEnergy",
    "activationEnergy",
    "dftCode",
    "dftFunctional",
    "publication_doi",
    "E",
    "Formula",
    "Adsorbate",
    "Substrate",
    "struc",
    "record_class",
]
```

## 2. Inspect The Scientific Meaning

The bundled HDF is reaction-centric. It contains rows that describe reaction
energies and barriers from Catalysis-Hub-style data. It is not a full local VASP
folder crawl with `CHGCAR` and `DOSCAR`.

Useful first checks:

```python
frame["record_class"].value_counts(dropna=False)
frame["surfaceComposition"].value_counts().head(10)
frame[["Equation", "reactionEnergy", "activationEnergy"]].head()
```

Read these columns chemically:

- `reactionEnergy`: thermodynamic driving force for the reaction row
- `activationEnergy`: kinetic barrier
- `surfaceComposition`: catalyst identity
- `facet`: surface orientation where available
- `Adsorbate` and `Substrate`: row-level surface chemistry labels

## 3. Add Adsorption Energies

The backend can reconstruct adsorption-style quantities from the Catalysis-Hub
reaction rows:

```python
from onepiece import add_catalysis_hub_adsorption_energies

analysed = add_catalysis_hub_adsorption_energies(frame)

[
    column
    for column in analysed.columns
    if "adsorption" in column.lower()
]
```

This step is a semantic transformation. It turns reaction-row bookkeeping into
columns that are easier to compare across surfaces.

For CO2 reduction, this is the move from:

```text
CO2(g) + * -> CO2*
```

to a row-wise adsorption-energy quantity with an explicit surface and gas
reference interpretation.

## 4. Use A Repeatable Workflow

OnePiece workflows make dataframe transformations explicit:

```python
from onepiece.workflows import apply_operations

workflow = apply_operations(
    analysed,
    operations=[
        {
            "kind": "derive_constant",
            "label": "Mark tutorial source",
            "enabled": True,
            "params": {
                "column": "dataset_family",
                "value": "catalysis_hub_co2_subset",
            },
        },
    ],
)

active = workflow.dataframe
workflow.audit_log
```

The important part is `workflow.audit_log`. It records which operation created
the derived column. That is the dataframe-scale equivalent of saying which
calculation produced which result in a workflow engine.

## 5. Save As A Managed OnePiece Dataset

```python
from onepiece.provenance import ReferenceScheme
from onepiece.storage import resolve_storage_config, save_dataset

reference_scheme = ReferenceScheme.gas_phase(
    name="Catalysis-Hub CO2 tutorial references",
    gas_references_eV={
        "CO2": -22.1,
        "H2": -6.8,
    },
    description=(
        "Example gas-phase reference scheme for the bundled tutorial. "
        "Replace values with the actual project reference table for publication."
    ),
)

config = resolve_storage_config(".onepiece")

manifest_path = save_dataset(
    active,
    dataset_id="catalysis_hub_co2_subset_tutorial",
    config=config,
    source_path=str(path),
    reference_scheme=reference_scheme,
    workflow_audit_log=workflow.audit_log,
    metadata={
        "project": "CO2 reduction tutorial",
        "source": "bundled Catalysis-Hub subset",
        "dft_code": "multiple, inherited from source rows",
        "reaction_family": "CO2 reduction",
        "license": "check upstream source license",
        "citation": "Catalysis-Hub-derived OnePiece tutorial subset",
    },
)
```

This writes:

```text
.onepiece/workspace/catalysis_hub_co2_subset_tutorial/
  manifest.json
  table.parquet
  object_columns.pkl   # only when object columns need a sidecar
```

## 6. Audit Before Sharing

```bash
onepiece-studio fair-audit \
  .onepiece/workspace/catalysis_hub_co2_subset_tutorial \
  --require-reference-scheme \
  --require-publication-metadata
```

This catches the common scientific failure mode: a table that contains numbers
but not the information needed to interpret those numbers.

## 7. Open In The UI

Open the original HDF:

```bash
onepiece-studio hdf src/onepiece/data/catalysis_hub_co2_subset.hdf \
  --key df \
  --title "Catalysis-Hub CO2 Tutorial"
```

Or open the bundled tutorial shortcut:

```bash
onepiece-studio tutorial
```

The UI is only the front end. The scientific logic should remain in the backend
functions shown above.

## Chemistry Interpretation

For a catalysis user, the useful reading order is:

1. Check `surfaceComposition` and `facet`.
2. Check `Equation`.
3. Compare `reactionEnergy` and `activationEnergy`.
4. Reconstruct adsorption energies where the row semantics support it.
5. Save the reference scheme.
6. Save the workflow audit log.

This is the same discipline needed for OER on MnVO/CuVO or CO2RR on
perovskites: the dataframe is only trustworthy when the thermodynamic
bookkeeping is visible.
