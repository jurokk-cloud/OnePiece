from __future__ import annotations

import os

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]
DATA_ROOT = Path(os.environ.get("ONEPIECE_DATA_ROOT", "data/chapter6"))


def md(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


def make_notebook():
    cells = [
        md(
            """
# OnePiece Tutorial: CO and CH3OH Adsorption Energies from Chapter 6 HDF Files

This notebook starts from the six local OnePiece/pandas HDF files:

- `CaO-slabs.hdf`
- `Ga2O3-slabs.hdf`
- `Ni-slabs.hdf`
- `Ni3Ga.hdf`
- `Ni5Ga3-slabs.hdf`
- `NiO-slabs.hdf`

The goal is to calculate adsorption-energy tables for CO and methanol chemistry.
The important workflow decision is:

**Assign the clean surface reference inside each HDF file before merging all
DataFrames.**

That prevents accidental matching of a Ni reference from one file with a similar
surface name in another file. Chemically, every adsorption energy must know which
clean slab belongs to the adsorbed slab.
"""
        ),
        md(
            """
## 1. Mental model for chemists: pandas like Excel, but reproducible

A pandas `DataFrame` is a table, very much like an Excel sheet:

- rows are calculations,
- columns are properties such as `Name`, `Formula`, `E`, `fmax`, `Path`, `struc`,
- filters select rows,
- formulas create new columns,
- `groupby` makes pivot-table-like summaries.

The difference is that every step is written as code, so the analysis can be
repeated exactly after the dataset grows.

ASE (`Atomic Simulation Environment`) usually represents structures as
`ase.Atoms` objects. In OnePiece-style databases, these structures can appear in
a column such as `struc`, while pandas manages the metadata around them.
"""
        ),
        code(
            f"""
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd

# Compatibility shim for HDF files written with a different NumPy/PyTables stack.
try:
    import numpy.core as numpy_core
    sys.modules.setdefault("numpy._core", numpy_core)
    sys.modules.setdefault("numpy._core.multiarray", np.core.multiarray)
    sys.modules.setdefault("numpy._core.numeric", np.core.numeric)
except Exception as exc:
    print("NumPy compatibility shim skipped:", exc)

PROJECT_ROOT = Path(r"{PROJECT_ROOT}")
TUTORIAL_ROOT = PROJECT_ROOT / "notebooks" / "chapter6_adsorption_tutorial"
OUTPUT_ROOT = TUTORIAL_ROOT / "outputs"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

DATA_ROOT = Path(r"{DATA_ROOT}")
HDF_FILES = {{
    "CaO-slabs": DATA_ROOT / "CaO-slabs.hdf",
    "Ga2O3-slabs": DATA_ROOT / "Ga2O3-slabs.hdf",
    "Ni-slabs": DATA_ROOT / "Ni-slabs.hdf",
    "Ni3Ga": DATA_ROOT / "Ni3Ga.hdf",
    "Ni5Ga3-slabs": DATA_ROOT / "Ni5Ga3-slabs.hdf",
    "NiO-slabs": DATA_ROOT / "NiO-slabs.hdf",
}}
"""
        ),
        md("## 2. Check that the input files exist"),
        code(
            """
file_check = pd.DataFrame(
    [{"dataset": label, "path": str(path), "exists": path.exists()} for label, path in HDF_FILES.items()]
)
file_check
"""
        ),
        md(
            """
## 3. Read one HDF file with OnePiece/pandas

The user-facing OnePiece idea is: the database gives us a pandas table. In these
files, the table is stored under the HDF key `df`, so the direct command is:

```python
pd.read_hdf(filename, key="df")
```
"""
        ),
        code(
            """
example = pd.read_hdf(HDF_FILES["Ni3Ga"], key="df")
print(example.shape)
example.head()
"""
        ),
        code(
            """
# Excel-like schema overview: column name, data type, filled cells, example value.
schema = pd.DataFrame({
    "column": example.columns,
    "dtype": [str(example[c].dtype) for c in example.columns],
    "non_null": [int(example[c].notna().sum()) for c in example.columns],
    "example": [
        repr(example[c].dropna().iloc[0])[:90] if example[c].notna().any() else ""
        for c in example.columns
    ],
})
schema
"""
        ),
        md(
            """
## 4. Load every file, but keep provenance

Before merging anything, each row gets:

- `dataset`: which HDF file it came from,
- `source_hdf`: absolute file path,
- `source_row`: original row number.

These columns are boring but essential. They let the UI open the exact
calculation later.
"""
        ),
        code(
            """
def read_onepiece_hdf(path, key="df"):
    path = Path(path)
    frame = pd.read_hdf(path, key=key).copy()
    frame["dataset"] = path.stem
    frame["source_hdf"] = str(path)
    frame["source_row"] = np.arange(len(frame), dtype=int)
    return frame

frames = {label: read_onepiece_hdf(path) for label, path in HDF_FILES.items()}

pd.DataFrame(
    {
        "dataset": label,
        "rows": len(frame),
        "columns": len(frame.columns),
        "first_name": frame["Name"].iloc[0] if "Name" in frame else "",
    }
    for label, frame in frames.items()
)
"""
        ),
        md(
            """
## 5. Recognize adsorbates from calculation names

For these files, the adsorbate is encoded in `Name`, for example:

- `Ni3Ga-111-clean-2x2x4-CO-1`
- `Ni5Ga3-211-clean-4x3x4-1-CH3O-1`

Important: the dataset contains many `CH3O` rows, but no direct `CH3OH` rows.
Chemically, `CH3O*` is methoxy. If we want to reference methanol gas, the
balanced reaction is usually written as:

\\[
* + \\mathrm{CH_3OH(g)} \\rightarrow \\mathrm{CH_3O*} + \\frac{1}{2}\\mathrm{H_2(g)}
\\]

Therefore the tutorial prepares both:

- CO molecular adsorption,
- methanol-to-methoxy adsorption convention.
"""
        ),
        code(
            r"""
ADSORBATE_PATTERN = re.compile(
    r"[-_%](CH3OH|CH3O|H2COOH|HCOOH|HCOO|COOH|CO2|HCO|CO)(?:[-_%].*|$)"
)

def guess_adsorbate(name):
    if not isinstance(name, str):
        return ""
    match = ADSORBATE_PATTERN.search(name)
    return match.group(1) if match else ""

def reference_name_guess(name):
    # Remove the adsorbate suffix and recover the expected clean slab name.
    if not isinstance(name, str):
        return ""
    return ADSORBATE_PATTERN.sub("", name)

names = pd.Series([
    "Ni3Ga-111-clean-2x2x4-CO-1",
    "Ni5Ga3-211-clean-4x3x4-1-CH3O-1",
    "Ga2O3-001-5-2x1x4-CO-top-1",
    "Ni-211-clean-3x3x4",
])

pd.DataFrame({
    "Name": names,
    "adsorbate": names.map(guess_adsorbate),
    "clean_reference_guess": names.map(reference_name_guess),
})
"""
        ),
        md(
            """
## 6. Assign the clean surface reference before merging

This is the core workflow.

For each HDF file separately:

1. Add an `adsorbate` column.
2. Build a `surface_key` by removing the adsorbate part from `Name`.
3. Use non-adsorbed rows as clean/reference surface candidates.
4. For each `surface_key`, pick the lowest-energy candidate as the reference.
5. Copy `surface_ref_name`, `surface_ref_E`, and `surface_ref_formula` onto adsorbed rows.

Only after that do we concatenate the DataFrames.
"""
        ),
        code(
            r"""
ELEMENT_PATTERN = re.compile(r"([A-Z][a-z]?)(\d*)")

def formula_counts(formula):
    if not isinstance(formula, str):
        return {}
    counts = {}
    for element, number in ELEMENT_PATTERN.findall(formula):
        counts[element] = counts.get(element, 0) + int(number or 1)
    return counts

def count_from_row(row, element):
    if element in row.index:
        value = pd.to_numeric(row[element], errors="coerce")
        if pd.notna(value):
            return float(value)
    return float(formula_counts(row.get("Formula")).get(element, 0))

def choose_reference_rows(frame):
    candidates = frame.loc[
        (frame["adsorbate"] == "")
        & frame["E"].notna()
        & (pd.to_numeric(frame["E"], errors="coerce") != 0)
    ].copy()
    candidates["reference_candidate_count"] = candidates.groupby("surface_key")["Name"].transform("count")
    candidates = candidates.sort_values(["surface_key", "E"], ascending=[True, True])
    refs = candidates.drop_duplicates("surface_key", keep="first").copy()
    refs["reference_ambiguous"] = refs["reference_candidate_count"] > 1
    return refs

def assign_surface_references_one_frame(frame):
    df = frame.copy()
    df["E"] = pd.to_numeric(df.get("E"), errors="coerce")
    df["Name"] = df.get("Name", pd.Series([""] * len(df))).astype(str)
    df["adsorbate"] = df["Name"].map(guess_adsorbate)
    df["is_adsorbate"] = df["adsorbate"] != ""
    df["surface_key"] = df["Name"].map(reference_name_guess)

    refs = choose_reference_rows(df)
    reference_lookup = refs.set_index("surface_key")

    df["surface_ref_name"] = df["surface_key"].map(reference_lookup["Name"])
    df["surface_ref_E"] = df["surface_key"].map(reference_lookup["E"])
    df["surface_ref_formula"] = df["surface_key"].map(reference_lookup["Formula"])
    df["surface_ref_ambiguous"] = df["surface_key"].map(reference_lookup["reference_ambiguous"])

    df["surface_ref_status"] = "ok"
    df.loc[df["surface_ref_name"].isna(), "surface_ref_status"] = "missing"
    df.loc[df["surface_ref_ambiguous"].fillna(False), "surface_ref_status"] = "ambiguous"
    df.loc[~df["is_adsorbate"] & (df["surface_ref_status"] == "ok"), "surface_ref_status"] = "self"

    for element in ["C", "H", "O"]:
        current = df.apply(lambda row: count_from_row(row, element), axis=1)
        ref_counts = refs.set_index("surface_key").apply(
            lambda row: count_from_row(row, element), axis=1
        )
        df[f"delta_{element}"] = current - df["surface_key"].map(ref_counts).fillna(0)

    df["delta_E_to_surface_eV"] = df["E"] - df["surface_ref_E"]
    return df

enriched_frames = {
    label: assign_surface_references_one_frame(frame)
    for label, frame in frames.items()
}
"""
        ),
        code(
            """
# Example: inspect the reference assignment before merging.
cols = ["Name", "Formula", "adsorbate", "surface_ref_name", "E", "surface_ref_E", "delta_E_to_surface_eV"]
enriched_frames["Ni3Ga"].loc[enriched_frames["Ni3Ga"]["is_adsorbate"], cols].head(10)
"""
        ),
        md("## 7. Merge after references are assigned"),
        code(
            """
combined = pd.concat(
    [frame.assign(dataset_label=label) for label, frame in enriched_frames.items()],
    ignore_index=True,
    sort=False,
)

combined[["dataset_label", "adsorbate", "surface_ref_status"]].value_counts().head(30)
"""
        ),
        md(
            """
Rows with `surface_ref_status == "missing"` are not automatically wrong. They
mean that the expected clean reference was not present under the simple name
rule. In the UI, these rows should be flagged for manual reference assignment or
excluded from adsorption-energy plots until resolved.
"""
        ),
        code(
            """
missing = combined.loc[
    combined["is_adsorbate"] & combined["surface_ref_status"].eq("missing"),
    ["dataset_label", "Name", "Formula", "adsorbate", "surface_key", "E"],
]
missing.head(20)
"""
        ),
        md(
            """
## 8. Adsorption energy formulas

### CO

For molecular CO adsorption:

\\[
E_{ads}(CO) =
\\frac{E(nCO*) - E(*) - nE(CO_{gas})}{n}
\\]

where:

- `E(nCO*)` is the DFT energy of the slab with CO,
- `E(*)` is the assigned clean surface reference,
- `n` is the number of CO molecules, here estimated from the C atom difference,
- `E(CO_gas)` must come from a gas-phase CO calculation with the same DFT setup.

### CH3OH to CH3O*

The provided files contain `CH3O`, not `CH3OH`. A transparent methanol convention is:

\\[
* + \\mathrm{CH_3OH(g)} \\rightarrow \\mathrm{CH_3O*} + \\frac{1}{2}\\mathrm{H_2(g)}
\\]

so:

\\[
E_{ads}(CH_3OH \\rightarrow CH_3O*) =
\\frac{E(nCH_3O*) + \\frac{n}{2}E(H_2) - E(*) - nE(CH_3OH)}{n}
\\]

Do not invent gas reference energies. Insert the gas energies from your own
OnePiece gas-phase database or from calculations with identical settings.
"""
        ),
        code(
            """
# Fill these values from gas-phase calculations with the same DFT settings.
# Leaving them as np.nan is safer than silently using wrong reference energies.
GAS_REFERENCES_EV = {
    "CO": np.nan,      # e.g. -14.01
    "CH3OH": np.nan,  # e.g. your methanol gas energy
    "H2": np.nan,     # needed for CH3OH -> CH3O* + 1/2 H2
}

def add_adsorption_energy_columns(frame, gas_references_ev):
    df = frame.copy()
    df["n_CO_adsorbates"] = np.where(df["adsorbate"].eq("CO"), df["delta_C"], np.nan)
    df["n_CH3O_adsorbates"] = np.where(df["adsorbate"].eq("CH3O"), df["delta_C"], np.nan)

    valid_co = df["n_CO_adsorbates"].fillna(0) > 0
    df["E_ads_CO_eV"] = np.nan
    df.loc[valid_co, "E_ads_CO_eV"] = (
        df.loc[valid_co, "E"]
        - df.loc[valid_co, "surface_ref_E"]
        - df.loc[valid_co, "n_CO_adsorbates"] * gas_references_ev["CO"]
    ) / df.loc[valid_co, "n_CO_adsorbates"]

    valid_ch3o = df["n_CH3O_adsorbates"].fillna(0) > 0
    df["E_ads_CH3OH_to_CH3O_eV"] = np.nan
    df.loc[valid_ch3o, "E_ads_CH3OH_to_CH3O_eV"] = (
        df.loc[valid_ch3o, "E"]
        + 0.5 * df.loc[valid_ch3o, "n_CH3O_adsorbates"] * gas_references_ev["H2"]
        - df.loc[valid_ch3o, "surface_ref_E"]
        - df.loc[valid_ch3o, "n_CH3O_adsorbates"] * gas_references_ev["CH3OH"]
    ) / df.loc[valid_ch3o, "n_CH3O_adsorbates"]
    return df

results = add_adsorption_energy_columns(combined, GAS_REFERENCES_EV)
"""
        ),
        md(
            """
## 9. Focused table for the UI

The UI should not show all columns at once. For adsorption analysis, the most
important columns are:

- identity: `dataset_label`, `Name`, `Formula`,
- chemistry: `adsorbate`, `delta_C`, `delta_H`, `delta_O`,
- reference: `surface_ref_name`, `surface_ref_E`, `surface_ref_status`,
- energy: `E`, `delta_E_to_surface_eV`, adsorption-energy columns,
- quality/provenance: `fmax`, `source_hdf`, `source_row`.
"""
        ),
        code(
            """
adsorption_columns = [
    "dataset_label", "Name", "Formula", "adsorbate",
    "surface_ref_name", "surface_ref_formula", "surface_ref_status",
    "E", "surface_ref_E", "delta_E_to_surface_eV",
    "delta_C", "delta_H", "delta_O",
    "n_CO_adsorbates", "E_ads_CO_eV",
    "n_CH3O_adsorbates", "E_ads_CH3OH_to_CH3O_eV",
    "fmax", "source_hdf", "source_row",
]

adsorption_table = results.loc[
    results["is_adsorbate"],
    [column for column in adsorption_columns if column in results.columns],
].copy()

adsorption_table.head(20)
"""
        ),
        code(
            """
summary = adsorption_table.groupby(["dataset_label", "adsorbate", "surface_ref_status"]).agg(
    rows=("Name", "count"),
    median_delta_E_to_surface_eV=("delta_E_to_surface_eV", "median"),
    min_delta_E_to_surface_eV=("delta_E_to_surface_eV", "min"),
    max_delta_E_to_surface_eV=("delta_E_to_surface_eV", "max"),
).reset_index()

summary.sort_values(["dataset_label", "adsorbate", "surface_ref_status"])
"""
        ),
        md(
            """
## 10. Plot a useful reference-check picture

Until gas-phase references are filled, `delta_E_to_surface_eV` is the useful
debug quantity:

\\[
\\Delta E = E(adsorbed\\ slab) - E(clean\\ slab)
\\]

It is not yet the final adsorption energy because it still contains the energy
of the adsorbate atoms. However, it immediately tells us whether reference
assignment worked and which datasets contain outliers.
"""
        ),
        code(
            """
import matplotlib.pyplot as plt

plot_data = adsorption_table.loc[
    adsorption_table["surface_ref_status"].eq("ok")
    & adsorption_table["adsorbate"].isin(["CO", "CH3O"])
    & adsorption_table["delta_E_to_surface_eV"].notna()
    & adsorption_table["delta_E_to_surface_eV"].between(-80, 20)
].copy()

labels = []
values = []
for (dataset, adsorbate), group in plot_data.groupby(["dataset_label", "adsorbate"]):
    labels.append(f"{dataset}\\n{adsorbate}")
    values.append(group["delta_E_to_surface_eV"].to_numpy())

fig, ax = plt.subplots(figsize=(12, 5.5))
ax.boxplot(values, labels=labels, showfliers=False, patch_artist=True)
ax.set_ylabel("Delta E to assigned clean surface / eV")
ax.set_title("CO and CH3O rows after assigning local surface references")
ax.grid(axis="y", alpha=0.25)
fig.autofmt_xdate(rotation=35, ha="right")
fig.tight_layout()
fig
"""
        ),
        md("## 11. Save tables for the UI"),
        code(
            """
results.to_pickle(OUTPUT_ROOT / "chapter6_combined_with_surface_references.pkl")
adsorption_table.to_csv(OUTPUT_ROOT / "chapter6_adsorption_energy_table.csv", index=False)
summary.to_csv(OUTPUT_ROOT / "chapter6_adsorption_summary.csv", index=False)

reference_table = results.loc[
    ~results["is_adsorbate"],
    ["dataset_label", "Name", "Formula", "E", "surface_key", "surface_ref_status", "source_hdf", "source_row"],
].copy()
reference_table.to_csv(OUTPUT_ROOT / "chapter6_surface_reference_assignments.csv", index=False)

OUTPUT_ROOT
"""
        ),
        md(
            """
## 12. How this maps to a OnePiece Studio control-room workflow

In the UI, this should become a workflow tab with these operations:

1. **Load HDF sources**: each HDF file becomes one input node.
2. **Annotate adsorbate**: derive `adsorbate` from `Name`.
3. **Assign surface reference per source**: create `surface_ref_*` columns before merge.
4. **Merge frames**: concatenate all enriched DataFrames.
5. **Filter quality**: exclude missing references, failed energies (`E == 0`), or high `fmax`.
6. **Set gas references**: choose CO, CH3OH, and H2 gas energies from a local reference table.
7. **Calculate adsorption energies**: add `E_ads_CO_eV` and `E_ads_CH3OH_to_CH3O_eV`.
8. **Export analysis view**: save a CSV and allow UI plots.

The key design rule is that reference assignment is not a cosmetic table
operation. It is part of the scientific model and should be visible, filterable,
and manually overridable in the interface.
"""
        ),
    ]

    nb = nbf.v4.new_notebook()
    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
    }
    return nb


if __name__ == "__main__":
    path = ROOT / "01_onepiece_adsorption_energy_CO_CH3OH.ipynb"
    nbf.write(make_notebook(), path)
    print(path)
