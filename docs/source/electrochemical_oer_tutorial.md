# Electrochemical OER Tutorial

This tutorial describes the OnePiece workflow for oxygen evolution reaction
analysis on oxide surfaces such as MnVO, CuVO, perovskites, or related mixed
transition-metal oxides.

The emphasis is reference bookkeeping. OER trends are not reusable unless the
electrochemical convention, pH, potential, and corrections are visible.

## OER Reaction Network

A common four-step associative OER model is:

```text
* + H2O(l) -> OH* + H+ + e-
OH* -> O* + H+ + e-
O* + H2O(l) -> OOH* + H+ + e-
OOH* -> * + O2(g) + H+ + e-
```

With the computational hydrogen electrode, one usually replaces
`H+ + e-` by `1/2 H2` at 0 V versus RHE, then applies potential and pH
corrections explicitly.

## Define The Reference Scheme

Use `ReferenceScheme` to make the convention part of the saved dataset:

```python
from onepiece import ReferenceScheme

scheme = ReferenceScheme.computational_hydrogen_electrode(
    name="MnVO_OER_CHE",
    h2_eV=-6.77,
    h2o_eV=-14.22,
    potential_V_RHE=1.23,
    pH=14,
    corrections_eV={
        "OH_solvation": -0.30,
        "OOH_solvation": -0.35,
    },
    metadata={
        "surface_family": "MnVO",
        "functional": "PBE-D3 or project-specific setup",
        "reference_note": "Example values; replace with project-consistent DFT references.",
    },
)
```

The numbers above are placeholders for a tutorial. In a real project, the gas
references and corrections must come from the same DFT setup or a documented
external convention.

## Organize The DataFrame

The input table should identify clean surfaces and adsorbates explicitly:

```text
Name                 record_class    adsorbate
MnVO_001_clean       surface
MnVO_001_OH          adsorbate       OH
MnVO_001_O           adsorbate       O
MnVO_001_OOH         adsorbate       OOH
```

Required columns for a practical first pass:

```text
Name
E
Formula
struc
record_class
adsorbate
surface_ref_name
surface_ref_E
```

If `surface_ref_name` and `surface_ref_E` are missing, assign them first:

```python
from onepiece.adsorption import assign_surface_references

frame = assign_surface_references(frame)
```

## Add OER Energetics

OnePiece currently provides generic reference and adsorption infrastructure. For
OER, the recommended near-term pattern is to create explicit derived columns
whose names encode the convention:

```python
import numpy as np
import pandas as pd

df = frame.copy()
df["dG_OH_CHE_eV"] = np.nan
df["dG_O_CHE_eV"] = np.nan
df["dG_OOH_CHE_eV"] = np.nan

surface = pd.to_numeric(df["surface_ref_G"].fillna(df["surface_ref_E"]), errors="coerce")
energy = pd.to_numeric(df["G"].fillna(df["E"]), errors="coerce")

mu_h2 = scheme.gas_references_eV["H2"]
mu_h2o = scheme.gas_references_eV["H2O"]

is_oh = df["adsorbate"].eq("OH")
is_o = df["adsorbate"].eq("O")
is_ooh = df["adsorbate"].eq("OOH")

df.loc[is_oh, "dG_OH_CHE_eV"] = (
    energy[is_oh] - surface[is_oh] - (mu_h2o - 0.5 * mu_h2)
    + scheme.corrections_eV.get("OH_solvation", 0.0)
)
df.loc[is_o, "dG_O_CHE_eV"] = (
    energy[is_o] - surface[is_o] - (mu_h2o - mu_h2)
)
df.loc[is_ooh, "dG_OOH_CHE_eV"] = (
    energy[is_ooh] - surface[is_ooh] - (2.0 * mu_h2o - 1.5 * mu_h2)
    + scheme.corrections_eV.get("OOH_solvation", 0.0)
)
```

This explicit approach is better than hiding OER assumptions inside a generic
`adsorption_energy` column.

## Save With Provenance

When saving the derived dataset, attach the reference scheme:

```python
from onepiece import save_dataset
from onepiece.storage import ensure_storage_layout, resolve_storage_config

config = ensure_storage_layout(resolve_storage_config(".onepiece"))
manifest_path = save_dataset(
    df,
    dataset_id="mnvo-oer-che-screening",
    config=config,
    reference_scheme=scheme,
    metadata={
        "license": "CC-BY-4.0",
        "citation": "Replace with dataset or article citation.",
        "description": "MnVO OER intermediates with CHE reference metadata.",
    },
)
```

Then audit it:

```bash
onepiece-studio fair-audit .onepiece/workspace/mnvo-oer-che-screening \
  --require-reference-scheme \
  --require-publication-metadata
```

## What To Check Before Plotting Trends

Before comparing OER overpotentials, check:

- clean-surface references are not ambiguous
- all intermediates use the same slab size and termination
- adsorbate stoichiometry is consistent
- magnetic moments are chemically plausible for Mn/V/Cu oxidation states
- `fmax` thresholds are compatible across clean and adsorbed structures
- solvation and pH corrections are documented
- the same potential convention is used everywhere

For oxide OER, structural and magnetic consistency often matter as much as the
final free-energy number.

