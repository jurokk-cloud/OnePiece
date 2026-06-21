# OnePiece Backend: Mental Model

This page explains the OnePiece backend as a data system for computational
heterogeneous catalysis. The intended reader is comfortable with Python,
`pandas`, ASE, and DFT-derived tables, but wants to know where each backend
piece belongs.

The simplest mental model is:

```text
calculation folders or downloaded records
        |
        v
crawl/import layer
        |
        v
pandas DataFrame with chemistry columns and optional ASE objects
        |
        v
normalization, references, descriptors, filters, workflows
        |
        v
managed OnePiece dataset: table + sidecars + manifest + provenance
        |
        v
Streamlit UI, QA audit, RO-Crate export, further Python analysis
```

OnePiece does not replace ASE. ASE remains the natural object model for atomic
structures. OnePiece provides the missing layer around a dataframe: source
identity, column semantics, adsorption references, workflow provenance,
storage, and UI-ready query operations.

## Backend Layers

### 1. Source and import layer

Main modules:

- `onepiece.sources.core`
- `onepiece.adsorption.references`
- `onepiece.dftdataframe_import`

Main responsibilities:

- read a local HDF file
- read an uploaded HDF file from the UI
- normalize the row identity column `Name`
- detect the dataset profile
- map adsorption-related columns into OnePiece conventions
- fingerprint source files for provenance
- crawl calculation folders into a dataframe

Typical entry points:

```python
from onepiece.sources import read_hdf_path, prepare_source_frame
from onepiece import crawl_root_to_frame, crawl_root_to_hdf
```

Use this layer when the question is: **where did the table come from and what
kind of scientific table is it?**

### 2. Scientific enrichment layer

Main modules:

- `onepiece.adsorption.energies`
- `onepiece.adsorption.references`
- `onepiece.adsorption.formulas`
- `onepiece.thermo`
- `onepiece.ase_analysis`
- `onepiece.vasp`
- `onepiece.phase_diagrams`

Main responsibilities:

- reconstruct adsorption energies
- assign clean-surface and gas-phase references
- add elemental adsorption/free-energy columns
- compute Gibbs free-energy corrections
- derive formula/element counts
- add ASE structure descriptors
- read `CHGCAR`, `ACF.dat`, and `DOSCAR`
- add charge, magnetic moment, and projected DOS descriptors
- evaluate simple phase-diagram scans

Typical entry points:

```python
from onepiece import add_catalysis_hub_adsorption_energies
from onepiece.adsorption import add_adsorption_energies
from onepiece.thermo import add_gibbs_free_energy
from onepiece.vasp import add_adsorbate_charge_descriptors
```

Use this layer when the question is: **what new physical or chemical quantity
can be derived from the existing rows?**

### 3. Query and workflow layer

Main modules:

- `onepiece.services.dataset_service`
- `onepiece.workflows.engine`
- `onepiece.workflows.registry`
- `onepiece.automation`

Main responsibilities:

- filter rows with a stable `DatasetQuery`
- run saved workflow operations
- apply curation rules
- annotate reaction networks
- add structure descriptors in a repeatable way
- return an audit log for each enabled operation

Typical entry points:

```python
from onepiece import DatasetQuery, apply_dataset_query
from onepiece.workflows import apply_operations
```

Use this layer when the question is: **how do I make dataframe manipulation
repeatable rather than notebook-only?**

### 4. Storage and provenance layer

Main modules:

- `onepiece.storage`
- `onepiece.provenance`
- `onepiece.qa`

Main responsibilities:

- save a dataframe as a managed dataset
- preserve non-tabular Python object columns in sidecars
- write `manifest.json`
- record dataset provenance
- record thermodynamic reference schemes
- validate FAIR metadata
- export RO-Crate-style JSON-LD metadata

Typical entry points:

```python
from onepiece.storage import resolve_storage_config, save_dataset, load_dataset
from onepiece.provenance import ReferenceScheme
from onepiece.qa import run_fair_provenance_audit
```

Use this layer when the question is: **can this table be reused by another
person without reading my notebook?**

## What The Backend Expects In A DataFrame

The backend is intentionally dataframe-first. The most useful columns are:

| Column | Meaning |
|---|---|
| `Name` | stable row identifier |
| `E` | total or row energy in eV |
| `Formula` | formula string |
| `struc` | optional ASE `Atoms` object or structure-like object |
| `Adsorbate` | adsorbate label such as `CO2`, `CO`, `OH`, `OOH` |
| `Substrate` | clean surface or catalyst label |
| `surfaceComposition` | surface material family |
| `facet` | surface facet |
| `reactionEnergy` | reaction energy from a reaction dataset |
| `activationEnergy` | barrier from a reaction dataset |
| `record_class` | semantic row type, for example gas, surface, adsorbate |

OnePiece can work with partial data. A Catalysis-Hub-style reaction table does
not need local `CHGCAR` or `DOSCAR` files. A local VASP crawl can add those
later.

## How This Maps To Catalysis Thinking

For adsorption and kinetics, the key separation is:

- **raw observations**: energies, structures, files, reaction rows
- **references**: clean surfaces, gas-phase molecules, CHE convention,
  corrections, temperature, pressure, pH, potential
- **derived quantities**: adsorption energy, free energy, charge transfer,
  d-band descriptors, kinetic branch comparisons
- **workflow provenance**: which operation produced which derived column

That separation matters for OER on MnVO/CuVO, CO2RR on perovskites, or
Cu/ZnO methanol chemistry. A number such as `-0.72 eV` is not reusable until
the reference state and the transformation that created it are explicit.

## Backend Function Map

The full source-derived function map is available here:

```{image} _static/onepiece_function_map.svg
:alt: Source-derived OnePiece function map
```

The full text inventory is linked from [](function_inventory.md).
