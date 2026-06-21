from __future__ import annotations

import os

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "created_frame_phd_analysis"
DATA_PATH = Path(os.environ.get("ONEPIECE_DATA_ROOT", "data")) / "created_frame.hdf"
DFTDATAFRAME_SRC = Path(os.environ.get("DFTDATAFRAME_SRC", "src"))


def md(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


def notebook(title: str, cells: list):
    nb = nbf.v4.new_notebook()
    nb["cells"] = [md(f"# {title}")] + cells
    nb["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
    }
    return nb


COMMON_SETUP = f"""
from pathlib import Path
from collections import Counter
import math
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, r"{DFTDATAFRAME_SRC}")
import DFTDataFrame.Tools as OP

pd = OP.pd
np = OP.np
plt = OP.plt

DATA_PATH = Path(r"{DATA_PATH}")
DFTDATAFRAME_SRC = Path(r"{DFTDATAFRAME_SRC}")

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams["figure.figsize"] = (10, 6)
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.spines.right"] = False
plt.rcParams["axes.titlesize"] = 14
plt.rcParams["axes.labelsize"] = 12


def load_onepiece_hdf(path=DATA_PATH, key="df"):
    \"\"\"Load the local OnePiece-style HDF table.

    This notebook uses the local DFTDataFrame package as the available
    OnePiece-compatible analysis layer. The actual HDF payload is read through
    the pandas namespace exposed by that package.
    \"\"\"
    path = Path(path)
    try:
        return OP.pd.read_hdf(path, key=key).copy()
    except Exception as original_error:
        helper_python = Path(sys.executable)
        if not helper_python.exists():
            raise original_error
        output = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".pkl", prefix="created_frame_").name)
        script = \"\"\"
from pathlib import Path
import sys
import numpy as np
import pandas as pd
try:
    import numpy.core as numpy_core
    sys.modules.setdefault("numpy._core", numpy_core)
    sys.modules.setdefault("numpy._core.multiarray", np.core.multiarray)
    sys.modules.setdefault("numpy._core.numeric", np.core.numeric)
    import ase.constraints  # noqa: F401
except Exception:
    pass
source = Path(sys.argv[1])
key = sys.argv[2]
target = Path(sys.argv[3])
pd.read_hdf(source, key=key).to_pickle(target)
\"\"\"
        completed = subprocess.run(
            [str(helper_python), "-c", script, str(path), key, str(output)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Could not read {{path}}. Helper reader failed: {{detail}}") from original_error
        return OP.pd.read_pickle(output).copy()


ADSORBATE_TOKENS = [
    "CH3OH", "CH3O", "HCOOH", "H2COOH", "HCOO", "COOH", "CO2", "HCO", "CO"
]


def guess_adsorbate(name):
    if not isinstance(name, str):
        return ""
    for token in sorted(ADSORBATE_TOKENS, key=len, reverse=True):
        if re.search(rf"(^|[-_%]){{re.escape(token)}}($|[-_%])", name):
            return token
    return ""


def guess_record_class(name, path=""):
    text = f"{{name}} {{path}}".lower()
    if "gasphases" in text:
        return "gas"
    if "copt" in text:
        return "copt"
    if "convergence" in text:
        return "convergence"
    if "bulk" in text:
        return "bulk"
    if "clean" in text:
        return "clean_surface"
    if guess_adsorbate(name):
        return "adsorbate"
    return "other"


def guess_facet(name):
    if not isinstance(name, str):
        return ""
    for facet in ["100", "110", "111", "211", "221"]:
        if facet in name:
            return facet
    return ""


def material_family(name):
    if not isinstance(name, str):
        return "unknown"
    token = name.split("-")[0]
    return token or "unknown"


def surface_key_from_name(name):
    if not isinstance(name, str):
        return ""
    key = name
    key = re.sub(r"-copt-.*$", "", key)
    key = re.sub(r"-(CH3OH|CH3O|HCOOH|H2COOH|HCOO|COOH|CO2|HCO|CO)([-_%].*)?$", "", key)
    key = re.sub(r"-[0-9]+$", "", key)
    return key


def add_taxonomy(df):
    out = df.copy()
    out["record_class"] = [guess_record_class(n, p) for n, p in zip(out["Name"], out["Path"], strict=False)]
    out["facet"] = out["Name"].map(guess_facet)
    out["material_family"] = out["Name"].map(material_family)
    out["adsorbate"] = out["Name"].map(guess_adsorbate)
    out["surface_key"] = out["Name"].map(surface_key_from_name)
    return out


def formula_counts(formula):
    counts = {{}}
    if not isinstance(formula, str):
        return counts
    for element, number in re.findall(r"([A-Z][a-z]?)(\\d*)", formula):
        counts[element] = counts.get(element, 0) + int(number or 1)
    return counts


def add_formula_features(df):
    out = df.copy()
    parsed = out["Formula"].map(formula_counts)
    all_elements = sorted({{el for counts in parsed for el in counts}})
    for el in all_elements:
        out[el] = parsed.map(lambda counts: counts.get(el, 0))
    out["n_elements"] = parsed.map(len)
    out["n_atoms_formula"] = parsed.map(lambda counts: sum(counts.values()))
    return out


def gas_reference_energy(df, token):
    pattern = rf"^gasphases-{{re.escape(token)}}(?:$|[-_].*)"
    subset = df[df["Name"].astype(str).str.contains(pattern, regex=True, case=False, na=False)]
    subset = subset[pd.to_numeric(subset["E"], errors="coerce").notna()]
    if subset.empty:
        return np.nan
    return float(subset["E"].iloc[0])


def assign_clean_references(df):
    out = df.copy()
    clean = out[out["record_class"] == "clean_surface"].copy()
    clean = clean[pd.to_numeric(clean["E"], errors="coerce").notna()]
    clean_map = clean.groupby("surface_key")["E"].min().to_dict()
    clean_name_map = clean.sort_values("E").drop_duplicates("surface_key").set_index("surface_key")["Name"].to_dict()
    out["clean_ref_E"] = out["surface_key"].map(clean_map)
    out["clean_ref_name"] = out["surface_key"].map(clean_name_map)
    out["delta_E_surface"] = pd.to_numeric(out["E"], errors="coerce") - pd.to_numeric(out["clean_ref_E"], errors="coerce")
    return out


def adsorption_energy_conventions(df):
    out = df.copy()
    e_co = gas_reference_energy(out, "CO")
    e_h2 = gas_reference_energy(out, "H2")
    e_ch3oh = gas_reference_energy(out, "CH3OH")
    e_hcooh = gas_reference_energy(out, "HCOOH")
    out["E_ads_CO"] = np.where(out["adsorbate"].eq("CO"), out["E"] - out["clean_ref_E"] - e_co, np.nan)
    out["E_ads_CH3O_from_CH3OH"] = np.where(
        out["adsorbate"].eq("CH3O"),
        out["E"] - out["clean_ref_E"] - e_ch3oh + 0.5 * e_h2,
        np.nan,
    )
    out["E_ads_HCOO_from_HCOOH"] = np.where(
        out["adsorbate"].eq("HCOO"),
        out["E"] - out["clean_ref_E"] - e_hcooh + 0.5 * e_h2,
        np.nan,
    )
    out["E_ads_COOH_from_HCOOH"] = np.where(
        out["adsorbate"].eq("COOH"),
        out["E"] - out["clean_ref_E"] - e_hcooh + 0.5 * e_h2,
        np.nan,
    )
    return out


df_raw = load_onepiece_hdf()
df = add_formula_features(add_taxonomy(df_raw))
df["E"] = pd.to_numeric(df["E"], errors="coerce")
df["fmax"] = pd.to_numeric(df["fmax"], errors="coerce")
df["has_structure"] = df["struc"].map(lambda value: value.__class__.__name__ == "Atoms")
df["has_contcar"] = df["CONTCAR"].map(lambda value: value.__class__.__name__ == "Atoms")
"""


def make_00():
    cells = [
        md(
            """
This first notebook establishes the chemical and materials-science map of
`created_frame.hdf`. The focus is not merely technical schema inspection,
but a first scientific answer to three PhD-level questions:

1. Which classes of calculations are present?
2. Which materials and surfaces dominate the database?
3. Is the dataset chemically rich enough for adsorption and pathway analysis?
"""
        ),
        code(COMMON_SETUP),
        md("## 1. Read the OnePiece-style HDF table"),
        code(
            """
print("rows, columns:", df.shape)
df[["Name", "Formula", "E", "fmax", "record_class", "facet", "material_family"]].head(12)
"""
        ),
        md("## 2. Schema and completeness"),
        code(
            """
schema = pd.DataFrame({
    "column": df.columns,
    "dtype": [str(df[c].dtype) for c in df.columns],
    "non_null": [int(df[c].notna().sum()) for c in df.columns],
    "fraction_non_null": [df[c].notna().mean() for c in df.columns],
})
schema.sort_values(["fraction_non_null", "column"], ascending=[False, True])
"""
        ),
        md("## 3. What kinds of calculations are present?"),
        code(
            """
class_counts = df["record_class"].value_counts().sort_values(ascending=False)
class_counts
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(8, 5))
class_counts.plot(kind="bar", ax=ax, color="#4c78a8")
ax.set_title("Database composition by record class")
ax.set_ylabel("number of calculations")
ax.set_xlabel("record class")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 4. Which surface families and facets dominate the database?"),
        code(
            """
surface_like = df[df["record_class"].isin(["clean_surface", "adsorbate", "copt"])].copy()
facet_counts = surface_like["facet"].replace("", np.nan).dropna().value_counts().sort_index()
material_counts = surface_like["material_family"].value_counts().head(20)
display(facet_counts.to_frame("rows"))
display(material_counts.to_frame("rows"))
"""
        ),
        code(
            """
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
facet_counts.plot(kind="bar", ax=axes[0], color="#72b7b2")
axes[0].set_title("Facet distribution")
axes[0].set_xlabel("Miller index")
axes[0].set_ylabel("rows")
material_counts.sort_values().plot(kind="barh", ax=axes[1], color="#f58518")
axes[1].set_title("Most frequent material families")
axes[1].set_xlabel("rows")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 5. Chemical formula landscape"),
        code(
            """
top_formulas = df["Formula"].astype(str).value_counts().head(25)
top_formulas
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(10, 7))
top_formulas.sort_values().plot(kind="barh", ax=ax, color="#54a24b")
ax.set_title("Most frequent formulas in created_frame.hdf")
ax.set_xlabel("rows")
ax.set_ylabel("formula")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 6. Gas references already contained in the dataset"),
        code(
            """
gas_refs = df[df["record_class"].eq("gas")][["Name", "Formula", "E", "Path"]].sort_values("Name")
gas_refs.head(30)
"""
        ),
        md("## 7. Thesis-level interpretation"),
        md(
            """
This atlas already shows that `created_frame.hdf` is not a narrow single-project
table. It is a chemically heterogeneous research database containing:

- bulk oxides and metals,
- clean surfaces across multiple Miller indices,
- adsorbates ranging from CO and CH3O to HCOO and COOH,
- constrained-optimization (`copt`) pathways,
- gas-phase references needed for thermochemical reaction conventions.

In other words, the file is large enough to support a dissertation-style
discussion of structure, convergence, adsorption chemistry and reaction paths.
"""
        ),
    ]
    return notebook("00 - Dataset Atlas for created_frame.hdf", cells)


def make_01():
    cells = [
        md(
            """
This notebook asks whether the database is numerically trustworthy enough for
materials-science interpretation. The key idea is simple:

- a chemically rich database is only useful if the calculations are converged,
- but convergence should be analyzed by material class, not only globally.

The `DFTDataFrame` package already contains the relevant helper functions:
`OP.converged(...)` and `OP.notconverged(...)`.
"""
        ),
        code(COMMON_SETUP),
        md("## 1. Split converged and non-converged calculations"),
        code(
            """
df_nonzero = df[df["E"].notna() & (df["E"] != 0)].copy()
df_converged = OP.converged(df_nonzero, force_col="fmax", convergence_threshold=0.01)
df_notconverged = OP.notconverged(df_nonzero, force_col="fmax", convergence_threshold=0.01)

summary = pd.DataFrame({
    "subset": ["all nonzero", "converged", "not converged"],
    "rows": [len(df_nonzero), len(df_converged), len(df_notconverged)],
    "fraction": [1.0, len(df_converged) / len(df_nonzero), len(df_notconverged) / len(df_nonzero)],
})
summary
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(8, 5))
ax.hist(df_nonzero["fmax"], bins=120, color="#4c78a8", alpha=0.75)
ax.set_yscale("log")
ax.axvline(0.01, color="crimson", linestyle="--", label="convergence threshold = 0.01 eV/Å")
ax.set_title("Distribution of fmax for nonzero-energy calculations")
ax.set_xlabel("fmax / eV Å$^{-1}$")
ax.set_ylabel("count (log scale)")
ax.legend()
plt.tight_layout()
plt.show()
"""
        ),
        md("## 2. Which record classes carry the convergence burden?"),
        code(
            """
class_conv = (
    df_nonzero.groupby("record_class")
    .agg(rows=("Name", "size"), mean_fmax=("fmax", "mean"), median_fmax=("fmax", "median"))
    .sort_values("rows", ascending=False)
)
class_conv["fraction_converged"] = [
    OP.converged(group, force_col="fmax", convergence_threshold=0.01).shape[0] / len(group)
    for _, group in df_nonzero.groupby("record_class")
]
class_conv
"""
        ),
        code(
            """
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
class_conv["fraction_converged"].sort_values().plot(kind="barh", ax=axes[0], color="#72b7b2")
axes[0].set_title("Fraction converged by record class")
axes[0].set_xlabel("fraction with fmax < 0.01")
class_conv["median_fmax"].sort_values().plot(kind="barh", ax=axes[1], color="#e45756")
axes[1].set_title("Median fmax by record class")
axes[1].set_xlabel("median fmax / eV Å$^{-1}$")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 3. Materials view: convergence by material family"),
        code(
            """
family_conv = (
    df_nonzero.groupby("material_family")
    .agg(rows=("Name", "size"), median_fmax=("fmax", "median"), mean_energy=("E", "mean"))
    .query("rows >= 20")
    .sort_values("rows", ascending=False)
)
family_conv["fraction_converged"] = [
    OP.converged(group, force_col="fmax", convergence_threshold=0.01).shape[0] / len(group)
    for _, group in df_nonzero.groupby("material_family")
    if len(group) >= 20
]
family_conv.head(20)
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(9, 6))
scatter = ax.scatter(
    family_conv["rows"],
    family_conv["median_fmax"],
    c=family_conv["fraction_converged"],
    s=90,
    cmap="viridis",
)
for label, x, y in zip(family_conv.index, family_conv["rows"], family_conv["median_fmax"], strict=False):
    ax.text(x, y, label, fontsize=8)
ax.set_title("Material-family convergence map")
ax.set_xlabel("number of rows")
ax.set_ylabel("median fmax / eV Å$^{-1}$")
fig.colorbar(scatter, ax=ax, label="fraction converged")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 4. Lowest-energy representatives by formula"),
        code(
            """
formula_candidates = df_converged[df_converged["Formula"].astype(str).ne("0")].copy()
formula_minima = OP.group_min(formula_candidates, group="Formula", value="E")
formula_minima[["Name", "Formula", "record_class", "material_family", "facet", "E", "fmax"]].sort_values("E").head(30)
"""
        ),
        md("## 5. Lattice-parameter distributions for bulk-like rows"),
        code(
            """
bulk = df_converged[df_converged["record_class"].eq("bulk")].copy()
bulk[["Name", "Formula", "a", "b", "c", "gamma", "E"]].head(20)
"""
        ),
        code(
            """
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
for ax, column in zip(axes.ravel(), ["a", "b", "c", "gamma"], strict=False):
    values = pd.to_numeric(bulk[column], errors="coerce").dropna()
    ax.hist(values, bins=25, color="#f58518", alpha=0.85)
    ax.set_title(f"Bulk distribution of {column}")
    ax.set_xlabel(column)
    ax.set_ylabel("count")
plt.tight_layout()
plt.show()
"""
        ),
        md(
            """
From a thesis perspective, the main conclusion is that convergence is not an
afterthought but part of the scientific interpretation. The database is large
and chemically diverse, yet most numerically meaningful rows sit in a low-fmax
regime. That makes it reasonable to proceed to adsorption chemistry.
"""
        ),
    ]
    return notebook("01 - Convergence, Energetics and Materials Taxonomy", cells)


def make_02():
    cells = [
        md(
            """
This notebook moves from database cartography to chemistry.

We now ask:

1. Which adsorbates are represented?
2. Which gas-phase references are available in the same database?
3. Can we estimate chemically meaningful adsorption energies using
   clean-surface references contained in the dataset itself?

The analysis focuses on CO, CH3O, HCOO and COOH because those are abundant
enough to support comparative materials discussion.
"""
        ),
        code(COMMON_SETUP),
        md("## 1. Build the adsorption-analysis table"),
        code(
            """
analysis = adsorption_energy_conventions(assign_clean_references(df))
ads = analysis[analysis["record_class"].isin(["adsorbate", "copt"])].copy()
ads = ads[ads["clean_ref_E"].notna()].copy()
ads[["Name", "adsorbate", "clean_ref_name", "E", "clean_ref_E", "delta_E_surface"]].head(20)
"""
        ),
        md("## 2. Normalize obvious naming variants with the OnePiece helper"),
        code(
            """
ads = OP.unify_adsorbates(ads, "HCOOH", "COOH", "adsorbate")
ads = OP.unify_adsorbates(ads, "H2COOH", "COOH", "adsorbate")
ads["adsorbate"].value_counts().head(15)
"""
        ),
        md("## 3. Gas-phase reference energies present in the file"),
        code(
            """
gas_reference_table = pd.DataFrame({
    "species": ["CO", "H2", "CH3OH", "HCOOH"],
    "E_gas / eV": [
        gas_reference_energy(analysis, "CO"),
        gas_reference_energy(analysis, "H2"),
        gas_reference_energy(analysis, "CH3OH"),
        gas_reference_energy(analysis, "HCOOH"),
    ],
})
gas_reference_table
"""
        ),
        md("## 4. Which adsorbates are abundant enough for comparison?"),
        code(
            """
adsorbate_counts = ads["adsorbate"].replace("", np.nan).dropna().value_counts()
adsorbate_counts.head(20)
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(9, 6))
adsorbate_counts.head(12).sort_values().plot(kind="barh", ax=ax, color="#54a24b")
ax.set_title("Most common adsorbates in the database")
ax.set_xlabel("rows")
ax.set_ylabel("adsorbate")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 5. Adsorption energies by convention"),
        code(
            """
energy_columns = [
    "E_ads_CO",
    "E_ads_CH3O_from_CH3OH",
    "E_ads_HCOO_from_HCOOH",
    "E_ads_COOH_from_HCOOH",
]
ads[["Name", "adsorbate", "facet", "material_family", *energy_columns]].head(20)
"""
        ),
        code(
            """
co_like = ads[ads["E_ads_CO"].notna()].copy()
ch3o_like = ads[ads["E_ads_CH3O_from_CH3OH"].notna()].copy()
hcoo_like = ads[ads["E_ads_HCOO_from_HCOOH"].notna()].copy()
cooh_like = ads[ads["E_ads_COOH_from_HCOOH"].notna()].copy()

summary = pd.DataFrame({
    "family": ["CO*", "CH3O*", "HCOO*", "COOH*"],
    "rows": [len(co_like), len(ch3o_like), len(hcoo_like), len(cooh_like)],
    "mean_energy": [
        co_like["E_ads_CO"].mean(),
        ch3o_like["E_ads_CH3O_from_CH3OH"].mean(),
        hcoo_like["E_ads_HCOO_from_HCOOH"].mean(),
        cooh_like["E_ads_COOH_from_HCOOH"].mean(),
    ],
})
summary
"""
        ),
        code(
            """
fig, axes = plt.subplots(2, 2, figsize=(13, 9))
plot_specs = [
    (co_like, "E_ads_CO", "CO adsorption"),
    (ch3o_like, "E_ads_CH3O_from_CH3OH", "CH3O adsorption from CH3OH + 1/2 H2"),
    (hcoo_like, "E_ads_HCOO_from_HCOOH", "HCOO adsorption from HCOOH - 1/2 H2"),
    (cooh_like, "E_ads_COOH_from_HCOOH", "COOH adsorption from HCOOH - 1/2 H2"),
]
for ax, (table, column, title) in zip(axes.ravel(), plot_specs, strict=False):
    values = pd.to_numeric(table[column], errors="coerce").dropna()
    ax.hist(values, bins=30, color="#4c78a8", alpha=0.85)
    ax.axvline(values.mean(), color="crimson", linestyle="--", linewidth=1.5, label=f"mean = {values.mean():.2f} eV")
    ax.set_title(title)
    ax.set_xlabel("adsorption energy / eV")
    ax.set_ylabel("count")
    ax.legend()
plt.tight_layout()
plt.show()
"""
        ),
        md("## 6. Surface dependence of CO adsorption"),
        code(
            """
co_surface = (
    co_like.groupby(["material_family", "facet"])
    .agg(rows=("Name", "size"), mean_Eads=("E_ads_CO", "mean"), std_Eads=("E_ads_CO", "std"))
    .query("rows >= 3")
    .sort_values(["material_family", "facet"])
)
co_surface.head(30)
"""
        ),
        code(
            """
plot_table = co_surface.reset_index()
labels = plot_table["material_family"] + "-" + plot_table["facet"].replace("", "na")
fig, ax = plt.subplots(figsize=(12, 6))
ax.errorbar(labels, plot_table["mean_Eads"], yerr=plot_table["std_Eads"].fillna(0), fmt="o", color="#e45756")
ax.axhline(0, color="black", linewidth=1)
ax.set_title("CO adsorption energy across material families and facets")
ax.set_ylabel("E_ads(CO) / eV")
ax.set_xlabel("surface family")
plt.xticks(rotation=70, ha="right")
plt.tight_layout()
plt.show()
"""
        ),
        md(
            """
The chemical value of this notebook is not that every convention is unique or
final, but that the database itself already contains the reference information
needed to formulate adsorption hypotheses. That is exactly what a thesis-scale
materials workflow needs: transparent conventions tied to explicit rows.
"""
        ),
    ]
    return notebook("02 - Adsorbate Chemistry and Reference Energies", cells)


def make_03():
    cells = [
        md(
            """
The next scientific step is to connect energetics with local structure.

Here we use the OnePiece-compatible `DFTDataFrame` tools directly for
structure-derived descriptors:

- `OP.distance_from_surface(...)`
- `OP.get_GCN(...)`

The purpose is not to calculate every imaginable descriptor, but to show how a
materials thesis can move from names and formulas to local atomic environments.
"""
        ),
        code(COMMON_SETUP),
        md("## 1. Focus on converged adsorption structures"),
        code(
            """
analysis = adsorption_energy_conventions(assign_clean_references(df))
ads = analysis[analysis["record_class"].eq("adsorbate")].copy()
ads = OP.converged(ads[ads["E"].notna() & ads["clean_ref_E"].notna()], force_col="fmax", convergence_threshold=0.01)
ads = OP.unify_adsorbates(ads, "HCOOH", "COOH", "adsorbate")
ads = ads[ads["has_structure"]].copy()
ads[["Name", "adsorbate", "material_family", "facet", "E", "fmax"]].head(15)
"""
        ),
        md("## 2. Distance of the adsorbate from the surface"),
        code(
            """
focused = ads[ads["adsorbate"].isin(["CO", "CH3O", "HCOO", "COOH"])].copy()
focused = focused.head(350).copy()  # structural descriptor pass on a representative subset
focused["Distance"] = focused.apply(
    OP.distance_from_surface,
    axis=1,
    struc="struc",
    adsorbate_atoms=["C", "O", "H"],
)
focused[["Name", "adsorbate", "Distance", "facet", "material_family"]].head(15)
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(9, 6))
for adsorbate, group in focused.groupby("adsorbate"):
    ax.hist(group["Distance"], bins=30, alpha=0.45, label=adsorbate)
ax.set_title("Adsorbate-to-surface distance distribution")
ax.set_xlabel("minimum adsorbate-surface distance / Å")
ax.set_ylabel("count")
ax.legend()
plt.tight_layout()
plt.show()
"""
        ),
        md("## 3. Generalized coordination numbers from the local structure"),
        code(
            """
def gcn_summary(row):
    try:
        gcn = OP.get_GCN(row, cutoff=3.0, structure_column="struc")
    except Exception:
        return pd.Series({"GCN_mean": np.nan, "GCN_min": np.nan, "GCN_max": np.nan})
    if len(gcn) == 0:
        return pd.Series({"GCN_mean": np.nan, "GCN_min": np.nan, "GCN_max": np.nan})
    return pd.Series({
        "GCN_mean": float(np.mean(gcn)),
        "GCN_min": float(np.min(gcn)),
        "GCN_max": float(np.max(gcn)),
    })

gcn_table = focused.apply(gcn_summary, axis=1)
focused = pd.concat([focused, gcn_table], axis=1)
focused[["Name", "adsorbate", "Distance", "GCN_mean", "GCN_min", "GCN_max"]].head(15)
"""
        ),
        code(
            """
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
axes[0].hist(focused["GCN_mean"].dropna(), bins=30, color="#72b7b2", alpha=0.85)
axes[0].set_title("Distribution of mean GCN")
axes[0].set_xlabel("mean GCN")
axes[0].set_ylabel("count")

co_focus = focused[focused["adsorbate"].eq("CO") & focused["E_ads_CO"].notna()].copy()
scatter = axes[1].scatter(
    co_focus["GCN_mean"],
    co_focus["E_ads_CO"],
    c=co_focus["Distance"],
    cmap="viridis",
    s=45,
)
axes[1].set_title("CO adsorption vs local coordination")
axes[1].set_xlabel("mean GCN")
axes[1].set_ylabel("E_ads(CO) / eV")
fig.colorbar(scatter, ax=axes[1], label="distance / Å")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 4. Lowest-energy representatives within each adsorbate family"),
        code(
            """
descriptor_ready = focused.copy()
descriptor_ready["adsorbate_surface"] = descriptor_ready["adsorbate"] + "::" + descriptor_ready["surface_key"]
descriptor_ready["descriptor_energy"] = descriptor_ready[
    ["E_ads_CO", "E_ads_CH3O_from_CH3OH", "E_ads_HCOO_from_HCOOH", "E_ads_COOH_from_HCOOH"]
].bfill(axis=1).iloc[:, 0]
lowest = OP.group_min(
    descriptor_ready[descriptor_ready["descriptor_energy"].notna()].copy(),
    group="adsorbate_surface",
    value="descriptor_energy",
)
lowest[["Name", "adsorbate", "material_family", "facet", "Distance", "GCN_mean", "descriptor_energy"]].head(30)
"""
        ),
        md(
            """
This notebook establishes a key materials-science bridge:

energetic trends can now be discussed alongside local coordination and
adsorbate-surface distance. That is exactly the level where mechanistic
arguments in a thesis become stronger than simple ranking tables.
"""
        ),
    ]
    return notebook("03 - Local Structure Descriptors and Coordination Chemistry", cells)


def make_04():
    cells = [
        md(
            """
The final notebook targets the most thesis-like part of the file:
reaction-pathway and constrained-optimization information.

The database contains many rows whose `Name` or `Path` include `copt`.
These are not static adsorption points, but snapshots along a constrained
optimization or pathway construction.

Here we convert that latent information into interpretable reaction profiles.
"""
        ),
        code(COMMON_SETUP),
        md("## 1. Select constrained-optimization rows"),
        code(
            """
copt = df[df["record_class"].eq("copt")].copy()
print("number of copt rows:", len(copt))
copt[["Name", "Path", "Formula", "E", "fmax"]].head(20)
"""
        ),
        md("## 2. Parse pathway identities and image indices from the names"),
        code(
            r"""
def parse_copt_name(name):
    if not isinstance(name, str) or "copt" not in name:
        return pd.Series({"pathway": "", "image": np.nan, "state_pair": ""})
    image_match = re.search(r"-(\d{2})$", name)
    image = int(image_match.group(1)) if image_match else np.nan
    state_match = re.search(r"copt-([^%]+)%([^-]+(?:-[^-]+)*)", name)
    if state_match:
        state_pair = state_match.group(1) + " -> " + state_match.group(2)
    else:
        state_pair = ""
    series_key = re.sub(r"-\d{2}$", "", name)
    return pd.Series({"pathway": series_key, "image": image, "state_pair": state_pair})

copt = pd.concat([copt, copt["Name"].apply(parse_copt_name)], axis=1)
copt[["Name", "pathway", "image", "state_pair", "E"]].head(20)
"""
        ),
        md("## 3. Which pathway families are present most often?"),
        code(
            """
pathway_counts = copt["state_pair"].replace("", np.nan).dropna().value_counts().head(15)
pathway_counts
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(10, 6))
pathway_counts.sort_values().plot(kind="barh", ax=ax, color="#b279a2")
ax.set_title("Most frequent constrained-optimization transformations")
ax.set_xlabel("rows")
ax.set_ylabel("state pair")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 4. Build image-resolved energy profiles"),
        code(
            """
profiles = (
    copt.dropna(subset=["image", "E"])
    .groupby("pathway")
    .agg(n_images=("image", "size"), min_image=("image", "min"), max_image=("image", "max"))
    .query("n_images >= 5")
    .sort_values("n_images", ascending=False)
)
profiles.head(20)
"""
        ),
        code(
            """
top_profiles = profiles.head(4).index.tolist()
fig, axes = plt.subplots(len(top_profiles), 1, figsize=(10, 3.4 * len(top_profiles)), sharex=False)
if len(top_profiles) == 1:
    axes = [axes]

for ax, pathway in zip(axes, top_profiles, strict=False):
    prof = copt[copt["pathway"].eq(pathway)].sort_values("image").copy()
    x = prof["image"].to_numpy()
    y = prof["E"].to_numpy()
    ax.plot(x, y, marker="o", color="#4c78a8")
    ax.set_title(pathway)
    ax.set_ylabel("E / eV")
    ax.set_xlabel("image index")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 5. Smooth one profile with the OnePiece barrier helper"),
        code(
            """
example_pathway = top_profiles[0]
example = copt[copt["pathway"].eq(example_pathway)].sort_values("image").head(3).copy()
example[["Name", "image", "E"]]
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(8, 5))
x = example["image"].to_numpy()
y = example["E"].to_numpy()
ax.scatter(x, y, color="black", zorder=3, label="calculated images")
if len(example) == 3:
    OP.barrier(float(x[0]), float(x[1]), float(x[2]), float(y[0]), float(y[1]), float(y[2]), color="crimson")
ax.set_title("Illustrative barrier interpolation with OP.barrier")
ax.set_xlabel("image index")
ax.set_ylabel("E / eV")
ax.legend()
plt.tight_layout()
plt.show()
"""
        ),
        md("## 6. Chemical reading of the pathway space"),
        md(
            """
At this point the HDF file can be read in a thesis-like way:

- static adsorption states provide thermodynamic anchors,
- clean surfaces provide reference energies,
- `copt` sequences provide mechanistic continuity between states,
- and the local `DFTDataFrame` tools already contain enough functionality to
  bridge tabular database work with atomistic interpretation.

That is exactly why a single, well-curated `.hdf` file can support a much
larger scientific narrative than a bare spreadsheet of energies.
"""
        ),
    ]
    return notebook("04 - Reaction Pathways and Constrained-Optimization Landscapes", cells)


def make_05():
    cells = [
        md(
            """
This notebook asks a focused chemistry question:

**Where does the dataset contain a credible surface reaction path toward
methanol, and which calculations should be discarded before we trust that
story?**

The point is not to force the entire database into a single mechanism. The
point is to perform a careful, thesis-like selection:

1. start from the full HDF archive,
2. remove calculations that are clearly unphysical or incomplete,
3. isolate methanol-relevant intermediates,
4. identify one surface family with an interpretable sequence of states,
5. visualize the thermodynamic and constrained-optimization evidence.
"""
        ),
        code(COMMON_SETUP),
        md("## 1. Build a transparent curation table"),
        code(
            r"""
METHANOL_TOKENS = [
    "CO2", "HCOO", "HCOO_H", "HCOOH", "H2COOH",
    "H2CO_OH", "H2CO_H", "CH3O", "CH3O_H", "H3COH", "OCH3OH"
]
SURFACE_STATE_TOKENS = [
    "OCH3OH", "CH3O_H", "H3COH", "CH3O", "H2CO_OH", "H2CO_H",
    "H2COOH_H", "H2COOH", "HCOOH_H", "HCOOH", "HCOO_H", "HCOO",
    "COOH", "CO2", "HCO_OH", "HCO_H", "HCO", "H2COO"
]


def is_bad_formula(value):
    text = "" if value is None else str(value).strip()
    return text in {"", "0", "nan", "None"}


def curation_flags(frame):
    out = frame.copy()
    out["flag_missing_energy"] = out["E"].isna()
    out["flag_zero_energy"] = out["E"].eq(0)
    out["flag_bad_formula"] = out["Formula"].map(is_bad_formula)
    out["flag_name_test"] = out["Name"].astype(str).str.contains(r"test", case=False, na=False)
    out["flag_name_convergence"] = out["Name"].astype(str).str.contains(r"convergence", case=False, na=False)
    out["flag_missing_structure"] = ~out["has_structure"] & ~out["has_contcar"]
    out["flag_high_fmax_static"] = out["record_class"].ne("copt") & out["fmax"].gt(0.05)
    out["flag_high_fmax_copt"] = out["record_class"].eq("copt") & out["fmax"].gt(0.10)
    out["flag_any_bad"] = out[
        [
            "flag_missing_energy",
            "flag_zero_energy",
            "flag_bad_formula",
            "flag_name_test",
            "flag_name_convergence",
            "flag_missing_structure",
            "flag_high_fmax_static",
            "flag_high_fmax_copt",
        ]
    ].any(axis=1)
    return out


def infer_surface_reference_name(name):
    text = "" if name is None else str(name)
    if "gasphases" in text or "convergence" in text or "test" in text:
        return ""
    if "-copt-" in text:
        return text.split("-copt-")[0]
    for token in SURFACE_STATE_TOKENS:
        marker = f"-{token}"
        if marker in text:
            return text.split(marker)[0]
    return text


curated = curation_flags(assign_clean_references(df))
curated["surface_ref_guess"] = curated["Name"].map(infer_surface_reference_name)
surface_reference_rows = curated[
    curated["Name"].eq(curated["surface_ref_guess"]) & ~curated["flag_any_bad"]
][["Name", "E"]].drop_duplicates("Name")
surface_reference_map = surface_reference_rows.set_index("Name")["E"].to_dict()
curated["surface_ref_E"] = curated["surface_ref_guess"].map(surface_reference_map)
curated["relative_to_surface_ref_eV"] = curated["E"] - curated["surface_ref_E"]

summary = pd.Series(
    {
        "all_rows": len(curated),
        "removed_rows": int(curated["flag_any_bad"].sum()),
        "kept_rows": int((~curated["flag_any_bad"]).sum()),
        "static_high_fmax_removed": int(curated["flag_high_fmax_static"].sum()),
        "copt_high_fmax_removed": int(curated["flag_high_fmax_copt"].sum()),
        "test_name_removed": int(curated["flag_name_test"].sum()),
        "bad_formula_removed": int(curated["flag_bad_formula"].sum()),
    }
)
summary
"""
        ),
        md(
            """
These rules are intentionally conservative.

- Static minima should be well relaxed, so we ask for `fmax <= 0.05`.
- Constrained images can be a bit rougher, so we allow `fmax <= 0.10`.
- Rows with `E = 0`, missing energy, missing formula, `test`, or
  `convergence` in the name are removed.

This is exactly the kind of curation logic that belongs in a thesis chapter:
explicit, reproducible, and open to discussion.
"""
        ),
        code(
            """
flag_counts = curated.filter(like="flag_").sum().sort_values(ascending=False)
flag_counts
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(10, 5.5))
flag_counts.drop(labels=["flag_any_bad"]).sort_values().plot(kind="barh", ax=ax, color="#e45756")
ax.set_title("How many rows are removed by each curation rule?")
ax.set_xlabel("rows")
ax.set_ylabel("curation flag")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 2. Keep only methanol-relevant intermediates"),
        code(
            r"""
methanol_mask = curated["Name"].astype(str).str.contains("|".join(METHANOL_TOKENS), regex=True, na=False)
methanol = curated[methanol_mask & ~curated["flag_any_bad"]].copy()

print("curated methanol-related rows:", len(methanol))
methanol["adsorbate_family"] = methanol["Name"].astype(str).map(
    lambda name: next((token for token in METHANOL_TOKENS if token in name), "")
)
methanol[["Name", "record_class", "material_family", "facet", "adsorbate_family", "E", "fmax"]].head(20)
"""
        ),
        code(
            """
family_counts = (
    methanol.groupby(["material_family", "facet"])
    .size()
    .sort_values(ascending=False)
    .head(12)
    .rename("rows")
)
family_counts
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(10, 6))
labels = [f"{material}-{facet or 'na'}" for material, facet in family_counts.index]
ax.barh(labels[::-1], family_counts.to_numpy()[::-1], color="#72b7b2")
ax.set_title("Where does the methanol-related chemistry live?")
ax.set_xlabel("curated rows")
ax.set_ylabel("material / facet")
plt.tight_layout()
plt.show()
"""
        ),
        md(
            """
At this point a clear case study emerges. The Cu(211) branch is especially
useful because it contains:

- static intermediates such as `HCOO_H`, `HCOOH`, `H2COOH`, `H2CO_OH`,
  `H2CO_H`, `CH3O`, `CH3O_H`, and `H3COH`,
- plus several explicit `copt` trajectories that connect neighboring states.

That is enough to tell a chemically meaningful story toward methanol.
"""
        ),
        md("## 3. Focus on the Cu(211) family"),
        code(
            r"""
cu211 = methanol[
    methanol["Name"].astype(str).str.contains(r"^Cu-211-", regex=True, na=False)
].copy()

cu211["surface_branch"] = cu211["Name"].astype(str).map(
    lambda name: "Cu-211-Ga" if name.startswith("Cu-211-Ga")
    else ("Cu-211-Zn" if name.startswith("Cu-211-Zn") else "Cu-211-clean")
)

branch_counts = cu211["surface_branch"].value_counts()
branch_counts
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(7.5, 4.5))
branch_counts.sort_values().plot(kind="barh", ax=ax, color="#4c78a8")
ax.set_title("Curated methanol-related rows inside the Cu(211) subset")
ax.set_xlabel("rows")
ax.set_ylabel("surface branch")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 4. Build thermodynamic anchors from static intermediates"),
        code(
            r"""
STATIC_SEQUENCE = [
    "CO2", "HCOO_H", "HCOOH", "H2COOH", "H2CO_OH", "H2CO_H", "CH3O", "CH3O_H", "H3COH"
]


def first_matching_token(name, tokens):
    for token in tokens:
        if token in str(name):
            return token
    return ""


static_cu211 = cu211[
    cu211["record_class"].ne("copt") & cu211["adsorbate_family"].isin(STATIC_SEQUENCE)
].copy()
static_cu211["state"] = static_cu211["Name"].map(lambda name: first_matching_token(name, STATIC_SEQUENCE))
static_cu211["relative_to_surface_ref_eV"] = static_cu211["relative_to_surface_ref_eV"]

anchors = (
    static_cu211
    .groupby(["surface_branch", "state"], as_index=False)
    .agg(
        n_structures=("Name", "size"),
        best_name=("Name", "first"),
        best_energy=("relative_to_surface_ref_eV", "min"),
        best_fmax=("fmax", "min"),
    )
)

anchors["state"] = pd.Categorical(anchors["state"], categories=STATIC_SEQUENCE, ordered=True)
anchors = anchors.sort_values(["surface_branch", "state"])
anchors.head(30)
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(11, 6))
for branch, branch_df in anchors.groupby("surface_branch"):
    ordered = branch_df.dropna(subset=["best_energy"]).sort_values("state")
    x = [STATIC_SEQUENCE.index(state) for state in ordered["state"].astype(str)]
    ax.plot(x, ordered["best_energy"], marker="o", linewidth=2, label=branch)

ax.set_xticks(range(len(STATIC_SEQUENCE)))
ax.set_xticklabels(STATIC_SEQUENCE, rotation=45, ha="right")
ax.set_ylabel(r"$E - E_{clean}$ / eV")
ax.set_title("Best curated Cu(211) intermediates along a methanol-oriented state sequence")
ax.legend()
plt.tight_layout()
plt.show()
"""
        ),
        md(
            """
This plot is not a full free-energy diagram. It is a **curated energy map of
available static intermediates**. That distinction matters.

A thesis should say clearly: these points tell us which intermediates are in
the database and how stable they are relative to the matching bare surface
reference for the same Cu(211) branch.
They do **not** by themselves guarantee a unique catalytic mechanism.
"""
        ),
        md("## 5. Parse the constrained-optimization trajectories that point toward methanol"),
        code(
            r"""
def parse_copt_name(name):
    if not isinstance(name, str) or "copt" not in name:
        return pd.Series({"pathway": "", "image": np.nan, "state_pair": "", "state_left": "", "state_right": ""})
    image_match = re.search(r"-(\d{2})$", name)
    image = int(image_match.group(1)) if image_match else np.nan
    state_match = re.search(r"copt-([^%]+)%(.+?)(?:-\d{2})$", name)
    if state_match:
        left = state_match.group(1)
        right = state_match.group(2)
        pair = left + " -> " + right
    else:
        left = ""
        right = ""
        pair = ""
    pathway = re.sub(r"-\d{2}$", "", name)
    return pd.Series({"pathway": pathway, "image": image, "state_pair": pair, "state_left": left, "state_right": right})


cu211_copt = cu211[cu211["record_class"].eq("copt")].copy()
cu211_copt = pd.concat([cu211_copt, cu211_copt["Name"].apply(parse_copt_name)], axis=1)

target_pairs = cu211_copt[
    cu211_copt["state_pair"].astype(str).str.contains(r"HCOO|HCOOH|H2COOH|H2CO_OH|H2CO_H|CH3O|H3COH", regex=True, na=False)
].copy()

pair_counts = target_pairs["state_pair"].value_counts()
pair_counts
"""
        ),
        code(
            """
fig, ax = plt.subplots(figsize=(10, 5.5))
pair_counts.sort_values().plot(kind="barh", ax=ax, color="#f58518")
ax.set_title("Cu(211) constrained transformations that feed the methanol discussion")
ax.set_xlabel("rows")
ax.set_ylabel("state pair")
plt.tight_layout()
plt.show()
"""
        ),
        md("## 6. Plot the most complete Cu(211) image sequences"),
        code(
            """
profiles = (
    target_pairs.dropna(subset=["image", "E"])
    .groupby(["surface_branch", "pathway", "state_pair"], as_index=False)
    .agg(n_images=("image", "size"), min_image=("image", "min"), max_image=("image", "max"))
)
profiles = profiles[profiles["n_images"] >= 5].sort_values(["surface_branch", "n_images"], ascending=[True, False])
profiles.head(20)
"""
        ),
        code(
            """
top_profiles = profiles.head(6)
fig, axes = plt.subplots(len(top_profiles), 1, figsize=(10, 3.2 * len(top_profiles)), sharex=False)
if len(top_profiles) == 1:
    axes = [axes]

for ax, (_, row) in zip(axes, top_profiles.iterrows(), strict=False):
    prof = target_pairs[target_pairs["pathway"].eq(row["pathway"])].sort_values("image")
    ax.plot(prof["image"], prof["E"], marker="o", color="#54a24b")
    ax.set_title(f"{row['surface_branch']}: {row['state_pair']}")
    ax.set_ylabel("E / eV")
    ax.set_xlabel("image index")

plt.tight_layout()
plt.show()
"""
        ),
        md("## 7. A compact methanol-pathway reading"),
        md(
            """
The curated Cu(211) subset supports the following chemistry-oriented reading:

1. **formate and formic-acid chemistry is present**:
   `HCOO_H`, `HCOOH`, and `H2COOH` are all available, with explicit `copt`
   links between neighboring states.
2. **deeper hydrogenation chemistry is also present**:
   `H2CO_OH`, `H2CO_H`, `CH3O`, `CH3O_H`, and `H3COH` occur as static states
   and partially as pathway images.
3. **the most complete methanol-endgame images are in Cu(211)**:
   - `H2CO_H -> CH3O`
   - `CH3O_H -> H3COH`
4. **the dataset is not perfectly uniform**:
   some branches are rich in statics, others in `copt`, and some promising
   pathways still have sparse coverage.

That is actually a realistic thesis conclusion. Good scientific curation does
not hide gaps; it identifies the mechanism-relevant parts of the archive and
states clearly where the evidence is strong and where it remains incomplete.
"""
        ),
        md("## 8. Export a table of the curated methanol pathway evidence"),
        code(
            """
evidence_table = target_pairs[
    ["Name", "surface_branch", "surface_ref_guess", "state_pair", "image", "E", "relative_to_surface_ref_eV", "fmax"]
].sort_values(["surface_branch", "state_pair", "image"])
evidence_table.head(40)
"""
        ),
    ]
    return notebook("05 - Curated Methanol Reaction Path on Cu(211)", cells)


def make_06():
    cells = [
        md(
            """
This notebook narrows the discussion even further to a single thesis-style
case study:

**Cu-211-Ga and its methanol-oriented hydrogenation sequence.**

The goal is not only to produce final figures. The goal is to document the
analysis path itself in a way that a new group member can follow line by line.
For that reason the code cells below are unusually heavily commented.

Important methodological choice:

**all energy plots in this notebook use adsorption-style energies only.**
We do not plot raw total energies. Instead we derive the adsorbate
stoichiometry directly from the ASE `Atoms` objects in `struc`, subtract the
matching clean-surface `Atoms` object, and evaluate

`E_ads = E - E_surface - n_C * mu_C - n_H * mu_H - n_O * mu_O`

with `mu_H = 1/2 E(H2)`, `mu_O = E(H2O) - E(H2)`, and
`mu_C = E(CO2) - E(H2O) + 1/2 E(H2)`.

This notebook therefore follows a water-hydrogen-based oxygen reference and
the matching carbon reference requested for the methanol analysis.
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 1. Start from the full database and explain the curation logic

We first define the same curation rules as in the broader methanol notebook,
but here we keep the code intentionally verbose and line-commented. In the
same step we also build the adsorption-energy reference used in all later
plots from the **structure-derived stoichiometric difference** between
`struc` and the matched clean-surface `struc`.
"""
        ),
        code(
            r"""
# Define the methanol-related tokens that we want to trace in the dataset.
METHANOL_TOKENS = ["CO2", "HCOO", "HCOO_H", "HCOOH", "H2COOH", "H2CO_OH", "H2CO_H", "CH3O", "CH3O_H", "H3COH"]
# Sort the tokens by length so that longer state names are matched before shorter substrings.
METHANOL_MATCH_TOKENS = sorted(METHANOL_TOKENS, key=len, reverse=True)

# Define tokens that signal an adsorbate or intermediate attached to a surface name.
SURFACE_STATE_TOKENS = ["CH3O_H", "H3COH", "CH3O", "H2CO_OH", "H2CO_H", "H2COOH_H", "H2COOH", "HCOOH_H", "HCOOH", "HCOO_H", "HCOO", "CO2", "HCO_OH", "HCO_H", "HCO", "H2COO"]

# Create a helper that recognizes empty or clearly broken formula entries.
def is_bad_formula(value):
    # Convert missing values into an empty string for safe testing.
    text = "" if value is None else str(value).strip()
    # Return True if the formula is missing or reduced to a placeholder.
    return text in {"", "0", "nan", "None"}

# Create a helper that reconstructs the bare-surface reference name from a row name.
def infer_surface_reference_name(name):
    # Normalize the input into text.
    text = "" if name is None else str(name)
    # Ignore gas-phase, convergence, and test rows because they are not surface references.
    if "gasphases" in text or "convergence" in text or "test" in text:
        return ""
    # Remove the copt suffix so that pathway images map back to the parent surface.
    if "-copt-" in text:
        return text.split("-copt-")[0]
    # Remove the adsorbate part if a known intermediate token appears in the name.
    for token in SURFACE_STATE_TOKENS:
        marker = f"-{token}"
        if marker in text:
            return text.split(marker)[0]
    # Fall back to the original name if no special token is found.
    return text

# Create a helper that selects the best available ASE structure object.
def primary_atoms_object(row):
    # Prefer the explicit `struc` column because that is the requested source.
    if row["has_structure"]:
        return row["struc"]
    # Fall back to CONTCAR only if `struc` is missing.
    if row["has_contcar"]:
        return row["CONTCAR"]
    # Return None when no structure is available.
    return None

# Create a helper that counts elements directly from an ASE Atoms object.
def atoms_counts(atoms):
    # Return an empty dictionary when no atoms object is available.
    if atoms is None or getattr(atoms, "__class__", type(None)).__name__ != "Atoms":
        return {}
    # Count all element symbols using the atomistic structure rather than the formula string.
    return dict(Counter(atoms.get_chemical_symbols()))

# Create a helper that subtracts the clean-surface composition from the full adsorbate-plus-surface composition.
def adsorbate_counts_from_structures(total_atoms, surface_atoms):
    # Count the elements in the full adsorbate-plus-surface structure.
    total_counts = atoms_counts(total_atoms)
    # Count the elements in the clean reference surface.
    surface_counts = atoms_counts(surface_atoms)
    # Collect all elements that appear in either structure.
    elements = set(total_counts) | set(surface_counts)
    # Subtract the clean surface stoichiometry to isolate the adsorbate composition.
    return {element: total_counts.get(element, 0) - surface_counts.get(element, 0) for element in elements}

# Start from a copy of the prepared dataframe that already contains taxonomy columns.
curated = df.copy()
# Flag rows with missing total energies.
curated["flag_missing_energy"] = curated["E"].isna()
# Flag rows with zero energies because those are not meaningful relaxed DFT values here.
curated["flag_zero_energy"] = curated["E"].eq(0)
# Flag rows with unusable formula information.
curated["flag_bad_formula"] = curated["Formula"].map(is_bad_formula)
# Flag rows explicitly labeled as tests.
curated["flag_name_test"] = curated["Name"].astype(str).str.contains(r"test", case=False, na=False)
# Flag convergence scans that should not be mixed with production adsorption data.
curated["flag_name_convergence"] = curated["Name"].astype(str).str.contains(r"convergence", case=False, na=False)
# Flag rows that do not carry either an ASE Atoms object or a CONTCAR structure.
curated["flag_missing_structure"] = ~curated["has_structure"] & ~curated["has_contcar"]
# Use a stricter force threshold for static states.
curated["flag_high_fmax_static"] = curated["record_class"].ne("copt") & curated["fmax"].gt(0.05)
# Use a slightly looser force threshold for constrained optimization images.
curated["flag_high_fmax_copt"] = curated["record_class"].eq("copt") & curated["fmax"].gt(0.10)
# Combine all curation flags into one master decision column.
curated["flag_any_bad"] = curated[
    [
        "flag_missing_energy",
        "flag_zero_energy",
        "flag_bad_formula",
        "flag_name_test",
        "flag_name_convergence",
        "flag_missing_structure",
        "flag_high_fmax_static",
        "flag_high_fmax_copt",
    ]
].any(axis=1)

# Infer the parent surface reference for every row.
curated["surface_ref_guess"] = curated["Name"].map(infer_surface_reference_name)
# Keep only rows that are themselves valid reference surfaces.
surface_reference_rows = curated[
    curated["Name"].eq(curated["surface_ref_guess"]) & ~curated["flag_any_bad"]
][["Name", "E"]].drop_duplicates("Name")
# Build a mapping from surface reference name to bare-surface energy.
surface_reference_map = surface_reference_rows.set_index("Name")["E"].to_dict()
# Attach the surface reference energy to every row.
curated["surface_ref_E"] = curated["surface_ref_guess"].map(surface_reference_map)

# Select the primary ASE structure for each row.
curated["primary_atoms"] = curated.apply(primary_atoms_object, axis=1)

# Keep the clean-surface structure object for every matched reference.
surface_atoms_rows = curated[
    curated["Name"].eq(curated["surface_ref_guess"]) & ~curated["flag_any_bad"]
][["Name", "primary_atoms"]].drop_duplicates("Name")
# Build a mapping from clean surface name to clean surface Atoms object.
surface_atoms_map = surface_atoms_rows.set_index("Name")["primary_atoms"].to_dict()
# Attach the clean surface structure to each row.
curated["surface_ref_atoms"] = curated["surface_ref_guess"].map(surface_atoms_map)

# Derive the adsorbate-only elemental composition by subtracting the clean surface Atoms object.
curated["adsorbate_counts"] = [
    adsorbate_counts_from_structures(total_atoms, surface_atoms)
    for total_atoms, surface_atoms in zip(curated["primary_atoms"], curated["surface_ref_atoms"], strict=False)
]
# Extract the carbon count of the adsorbate.
curated["C_ads"] = curated["adsorbate_counts"].map(lambda counts: counts.get("C", 0))
# Extract the hydrogen count of the adsorbate.
curated["H_ads"] = curated["adsorbate_counts"].map(lambda counts: counts.get("H", 0))
# Extract the oxygen count of the adsorbate.
curated["O_ads"] = curated["adsorbate_counts"].map(lambda counts: counts.get("O", 0))

# Read the gas-phase references that define the elemental chemical potentials.
E_CO2 = gas_reference_energy(curated, "CO2")
E_H2 = gas_reference_energy(curated, "H2")
E_H2O = gas_reference_energy(curated, "H2O")

# Derive the elemental chemical potentials from the gas references.
mu_H = 0.5 * E_H2
# Use water and hydrogen to define the oxygen chemical potential.
mu_O = E_H2O - E_H2
# Recover the carbon chemical potential from carbon dioxide, water, and hydrogen.
mu_C = E_CO2 - E_H2O + 0.5 * E_H2

# Store the gas references in a small table for transparent inspection.
gas_reference_table = pd.DataFrame(
    {
        "species": ["CO2", "H2", "H2O"],
        "energy_eV": [E_CO2, E_H2, E_H2O],
    }
)

# Store the elemental chemical potentials in a second table.
mu_reference_table = pd.DataFrame(
    {
        "species": ["mu_C", "mu_H", "mu_O"],
        "energy_eV": [mu_C, mu_H, mu_O],
    }
)

# Store the elemental chemical potentials in a second table.
mu_reference_table = pd.DataFrame(
    {
        "species": ["mu_C", "mu_H", "mu_O"],
        "energy_eV": [mu_C, mu_H, mu_O],
    }
)

# Compute the adsorption energy relative to the clean surface and the elemental chemical potentials.
curated["E_ads_mu_eV"] = (
    curated["E"]
    - curated["surface_ref_E"]
    - curated["C_ads"] * mu_C
    - curated["H_ads"] * mu_H
    - curated["O_ads"] * mu_O
)

# Print a compact summary so that the user sees how aggressive the filtering is.
pd.Series(
    {
        "all_rows": len(curated),
        "removed_rows": int(curated["flag_any_bad"].sum()),
        "kept_rows": int((~curated["flag_any_bad"]).sum()),
        "cu211_ga_reference_surfaces": int(curated["surface_ref_guess"].astype(str).str.startswith("Cu-211-Ga").sum()),
        "mu_C_eV": float(mu_C),
        "mu_H_eV": float(mu_H),
        "mu_O_eV": float(mu_O),
    }
)
"""
        ),
        code(
            """
# Count how often each flag contributes to row removal.
flag_counts = curated.filter(like="flag_").sum().sort_values(ascending=False)
# Show the counts as a table.
flag_counts
"""
        ),
        code(
            """
# Create a horizontal bar chart for the curation logic.
fig, ax = plt.subplots(figsize=(10, 5.5))
# Plot all individual flags except the combined summary flag.
flag_counts.drop(labels=["flag_any_bad"]).sort_values().plot(kind="barh", ax=ax, color="#e45756")
# Add an informative title.
ax.set_title("Curation rules applied before Cu-211-Ga mechanism analysis")
# Label the x axis.
ax.set_xlabel("rows removed or flagged")
# Label the y axis.
ax.set_ylabel("curation criterion")
# Tighten the layout to avoid clipped text.
plt.tight_layout()
# Display the plot inside the notebook.
plt.show()
"""
        ),
        code(
            """
# Display the gas reference table used to derive the elemental chemical potentials.
gas_reference_table
"""
        ),
        code(
            """
# Display the elemental chemical potentials used in the adsorption-energy expression.
mu_reference_table
"""
        ),
        md("## 2. Isolate only the Cu-211-Ga methanol branch"),
        code(
            r"""
# Keep only methanol-relevant names after applying the global curation mask.
methanol = curated[
    curated["Name"].astype(str).str.contains("|".join(METHANOL_TOKENS), regex=True, na=False) & ~curated["flag_any_bad"]
].copy()

# Restrict the dataset to the Cu-211-Ga branch because it is rich in static states and copt images.
cu211_ga = methanol[methanol["Name"].astype(str).str.startswith("Cu-211-Ga")].copy()

# Assign a simplified state label based on the first matching token in the row name.
cu211_ga["state"] = cu211_ga["Name"].astype(str).map(
    lambda name: next((token for token in METHANOL_MATCH_TOKENS if token in name), "")
)

# Show the first rows to confirm that the filter behaves as expected.
cu211_ga[["Name", "record_class", "state", "surface_ref_guess", "C_ads", "H_ads", "O_ads", "E_ads_mu_eV", "fmax"]].head(20)
"""
        ),
        code(
            """
# Count how many curated rows belong to each methanol-relevant state.
state_counts = cu211_ga["state"].value_counts().sort_values(ascending=False)
# Return the table for inspection.
state_counts
"""
        ),
        code(
            """
# Create a bar chart showing which states are well represented in the Cu-211-Ga subset.
fig, ax = plt.subplots(figsize=(10, 5))
# Plot the state counts from low to high for readability.
state_counts.sort_values().plot(kind="barh", ax=ax, color="#4c78a8")
# Add a title describing the chart.
ax.set_title("Cu-211-Ga methanol-related states after curation")
# Label the x axis.
ax.set_xlabel("curated rows")
# Label the y axis.
ax.set_ylabel("state token")
# Prevent label clipping.
plt.tight_layout()
# Render the figure in the notebook.
plt.show()
"""
        ),
        code(
            """
# Summarize the adsorption-energy distribution by chemical state.
state_adsorption_stats = (
    cu211_ga.groupby("state", as_index=False)
    .agg(
        n_rows=("Name", "size"),
        min_ads_E=("E_ads_mu_eV", "min"),
        median_ads_E=("E_ads_mu_eV", "median"),
        max_ads_E=("E_ads_mu_eV", "max"),
    )
    .sort_values("median_ads_E")
)
# Show the table before plotting it.
state_adsorption_stats
"""
        ),
        code(
            """
# Plot the median adsorption energy by state to get a first thermodynamic ranking.
fig, ax = plt.subplots(figsize=(10, 5))
# Draw the median adsorption energies as a horizontal bar chart.
ax.barh(state_adsorption_stats["state"], state_adsorption_stats["median_ads_E"], color="#72b7b2")
# Label the x axis in adsorption-energy language.
ax.set_xlabel(r"median adsorption energy / eV")
# Label the y axis.
ax.set_ylabel("state token")
# Add a title that makes the reference convention explicit.
ax.set_title("Median Cu-211-Ga adsorption energies on the CO2/H2/H2O reference")
# Tight layout keeps everything readable.
plt.tight_layout()
# Show the figure.
plt.show()
"""
        ),
        code(
            """
# Build a cross-tabulation of state versus record class.
state_class_table = pd.crosstab(cu211_ga["state"], cu211_ga["record_class"])
# Show the table so we can see where static rows and copt rows coexist.
state_class_table
"""
        ),
        code(
            """
# Plot the state-versus-record-class matrix as grouped bars.
fig, ax = plt.subplots(figsize=(11, 6))
# Draw the grouped bar chart directly from the cross-tab table.
state_class_table.plot(kind="bar", ax=ax)
# Title the figure so the intent is explicit.
ax.set_title("Static states and copt images within the Cu-211-Ga methanol branch")
# Label the x axis.
ax.set_xlabel("state token")
# Label the y axis.
ax.set_ylabel("rows")
# Rotate state labels so that long names remain readable.
ax.tick_params(axis="x", rotation=45)
# Keep the legend visible and compact.
ax.legend(title="record class")
# Tight layout avoids clipping of labels and legend.
plt.tight_layout()
# Show the plot.
plt.show()
"""
        ),
        md("## 3. Build the static adsorption-energy landscape along a methanol-oriented sequence"),
        code(
            r"""
# Define a chemically ordered sequence from early hydrogenation to methanol-like products.
STATE_SEQUENCE = ["CO2", "HCOO_H", "HCOOH", "H2COOH", "H2CO_OH", "H2CO_H", "CH3O", "CH3O_H", "H3COH"]

# Keep only non-copt rows because we want thermodynamic anchor points first.
static_rows = cu211_ga[cu211_ga["record_class"].ne("copt")].copy()

# Keep only rows that belong to the ordered state sequence.
static_rows = static_rows[static_rows["state"].isin(STATE_SEQUENCE)].copy()

# For each state, find the lowest adsorption-energy curated structure on the common gas reference.
best_static = (
    static_rows.groupby("state", as_index=False)
    .agg(
        n_structures=("Name", "size"),
        best_name=("Name", "first"),
        best_ads_E=("E_ads_mu_eV", "min"),
        median_ads_E=("E_ads_mu_eV", "median"),
        best_fmax=("fmax", "min"),
    )
)

# Convert the state column to an ordered categorical axis.
best_static["state"] = pd.Categorical(best_static["state"], categories=STATE_SEQUENCE, ordered=True)

# Sort the table according to the chemical sequence.
best_static = best_static.sort_values("state")

# Display the resulting anchor table.
best_static
"""
        ),
        code(
            """
# Plot the best static adsorption energies along the reaction-like sequence.
fig, ax = plt.subplots(figsize=(11, 5.5))
# Build the x positions from the ordered table.
x = range(len(best_static))
# Draw a line through the lowest adsorption energies.
ax.plot(list(x), best_static["best_ads_E"], marker="o", linewidth=2.5, color="#54a24b")
# Add text labels with the number of structures supporting each state.
for i, (_, row) in enumerate(best_static.iterrows()):
    ax.text(i, row["best_ads_E"] + 0.15, f"n={row['n_structures']}", ha="center", va="bottom", fontsize=9)
# Apply readable tick labels.
ax.set_xticks(list(x))
# Use the ordered state names on the x axis.
ax.set_xticklabels(best_static["state"].astype(str), rotation=45, ha="right")
# Label the energy axis in adsorption-energy language.
ax.set_ylabel(r"adsorption energy / eV")
# Add a chemically specific title.
ax.set_title("Lowest curated adsorption energies in the Cu-211-Ga methanol branch")
# Improve spacing around the figure.
plt.tight_layout()
# Render the figure.
plt.show()
"""
        ),
        code(
            """
# Create a scatter plot that shows every static Cu-211-Ga adsorption energy, not only the best one.
fig, ax = plt.subplots(figsize=(11, 5.5))
# Loop over the ordered states to place all points state by state.
for i, state in enumerate(STATE_SEQUENCE):
    # Select rows for the current state.
    sub = static_rows[static_rows["state"].eq(state)]
    # Skip empty states so the plot code stays robust.
    if sub.empty:
        continue
    # Scatter all adsorption energies with slight transparency to show multiplicity.
    ax.scatter([i] * len(sub), sub["E_ads_mu_eV"], s=55, alpha=0.75, label=state if i == 0 else None, color="#72b7b2")
# Overlay the lowest-adsorption-energy trend as a guide.
ax.plot(range(len(best_static)), best_static["best_ads_E"], color="black", linewidth=1.5, marker="o")
# Format x ticks with the ordered states.
ax.set_xticks(range(len(STATE_SEQUENCE)))
# Use the state sequence as labels even if some states have few points.
ax.set_xticklabels(STATE_SEQUENCE, rotation=45, ha="right")
# Label the y axis.
ax.set_ylabel("adsorption energy / eV")
# Title the plot as a distribution view.
ax.set_title("Adsorption-energy spread of all curated static Cu-211-Ga intermediates")
# Tight layout prevents clipping.
plt.tight_layout()
# Show the chart.
plt.show()
"""
        ),
        code(
            """
# Plot adsorption-energy boxplots so that the spread per state is easier to compare statistically.
fig, ax = plt.subplots(figsize=(11, 5.5))
# Draw the state-resolved boxplot on the adsorption-energy column.
static_rows.boxplot(column="E_ads_mu_eV", by="state", ax=ax, grid=False, rot=45)
# Remove the automatic pandas suptitle.
plt.suptitle("")
# Add a cleaner title.
ax.set_title("Adsorption-energy distribution across static Cu-211-Ga intermediates")
# Label the y axis.
ax.set_ylabel("adsorption energy / eV")
# Keep spacing comfortable.
plt.tight_layout()
# Show the figure.
plt.show()
"""
        ),
        code(
            """
# Plot force convergence quality for each static state to verify that the adsorption ranking is not hiding bad relaxations.
fig, ax = plt.subplots(figsize=(11, 5))
# Use a boxplot because it summarizes the spread of fmax values per state.
static_rows.boxplot(column="fmax", by="state", ax=ax, grid=False, rot=45)
# Remove the automatic pandas suptitle to keep the figure clean.
plt.suptitle("")
# Replace the default axes title with a more specific one.
ax.set_title("Force convergence distribution across static Cu-211-Ga intermediates")
# Label the y axis.
ax.set_ylabel("fmax")
# Tight layout keeps labels readable.
plt.tight_layout()
# Display the plot.
plt.show()
"""
        ),
        code(
            """
# Plot adsorption energy against fmax to check whether weakly converged structures dominate the trend.
fig, ax = plt.subplots(figsize=(8.5, 5))
# Scatter the force maximum against the adsorption energy.
ax.scatter(static_rows["fmax"], static_rows["E_ads_mu_eV"], s=55, alpha=0.8, color="#b279a2")
# Label the x axis.
ax.set_xlabel("fmax")
# Label the y axis.
ax.set_ylabel("adsorption energy / eV")
# Add a title that explains why this diagnostic matters.
ax.set_title("Do convergence quality and adsorption energy correlate strongly?")
# Tight layout prevents label clipping.
plt.tight_layout()
# Show the plot.
plt.show()
"""
        ),
        md("## 4. Parse and inspect the constrained optimization paths"),
        code(
            r"""
# Define a parser that extracts pathway names and image numbers from copt row names.
def parse_copt_name(name):
    # Return an empty structure if the row is not a copt entry.
    if not isinstance(name, str) or "copt" not in name:
        return pd.Series({"pathway": "", "image": np.nan, "state_pair": "", "state_left": "", "state_right": ""})
    # Extract the image index from the final two digits.
    image_match = re.search(r"-(\d{2})$", name)
    # Convert the matched image to an integer if present.
    image = int(image_match.group(1)) if image_match else np.nan
    # Extract the left and right states around the percent sign.
    state_match = re.search(r"copt-([^%]+)%(.+?)(?:-\d{2})$", name)
    # Build the pair description if parsing succeeds.
    if state_match:
        left = state_match.group(1)
        right = state_match.group(2)
        pair = left + " -> " + right
    else:
        left = ""
        right = ""
        pair = ""
    # Remove the trailing image suffix so all images in the same path share a common pathway key.
    pathway = re.sub(r"-\d{2}$", "", name)
    # Return all parsed fields as a pandas Series.
    return pd.Series({"pathway": pathway, "image": image, "state_pair": pair, "state_left": left, "state_right": right})

# Keep only the copt rows inside the Cu-211-Ga subset.
cu211_ga_copt = cu211_ga[cu211_ga["record_class"].eq("copt")].copy()

# Apply the parser and merge the parsed columns back into the dataframe.
cu211_ga_copt = pd.concat([cu211_ga_copt, cu211_ga_copt["Name"].apply(parse_copt_name)], axis=1)

# Show a preview so the user can verify the parser logic.
cu211_ga_copt[["Name", "pathway", "image", "state_pair", "E_ads_mu_eV", "fmax"]].head(20)
"""
        ),
        code(
            """
# Count how many images belong to each state pair.
pair_counts = cu211_ga_copt["state_pair"].replace("", np.nan).dropna().value_counts()
# Show the table before plotting.
pair_counts
"""
        ),
        code(
            """
# Plot the counts of copt images per transformation.
fig, ax = plt.subplots(figsize=(10, 4.5))
# Use a horizontal bar chart because pathway names are long.
pair_counts.sort_values().plot(kind="barh", ax=ax, color="#f58518")
# Title the figure clearly.
ax.set_title("Cu-211-Ga constrained transformations related to methanol chemistry")
# Label the x axis.
ax.set_xlabel("number of copt images")
# Label the y axis.
ax.set_ylabel("state pair")
# Tight layout improves readability.
plt.tight_layout()
# Render the chart.
plt.show()
"""
        ),
        code(
            """
# Group the parsed copt dataframe into pathway summaries.
profiles = (
    cu211_ga_copt.dropna(subset=["image", "E"])
    .groupby(["pathway", "state_pair"], as_index=False)
    .agg(
        state_left=("state_left", "first"),
        state_right=("state_right", "first"),
        n_images=("image", "size"),
        min_image=("image", "min"),
        max_image=("image", "max"),
        Emin_ads=("E_ads_mu_eV", "min"),
        Emax_ads=("E_ads_mu_eV", "max"),
    )
    .sort_values(["n_images", "state_pair"], ascending=[False, True])
)

# Display the summary table for the main trajectories.
profiles
"""
        ),
        code(
            """
# Plot the image-resolved adsorption energies for every well-populated Cu-211-Ga path.
top_profiles = profiles[profiles["n_images"] >= 5].copy()
# Create one subplot per pathway so that each trajectory can be read separately.
fig, axes = plt.subplots(len(top_profiles), 1, figsize=(10, 3.2 * len(top_profiles)), sharex=False)
# Normalize the axes object when there is only one profile.
if len(top_profiles) == 1:
    axes = [axes]

# Loop over the pathway summary rows.
for ax, (_, row) in zip(axes, top_profiles.iterrows(), strict=False):
    # Select the detailed profile belonging to the current pathway.
    prof = cu211_ga_copt[cu211_ga_copt["pathway"].eq(row["pathway"])].sort_values("image")
    # Plot adsorption energies only, because those are the chemically comparable quantities.
    ax.plot(prof["image"], prof["E_ads_mu_eV"], marker="o", linewidth=2.2, color="#e45756")
    # Use the state pair as the subplot title.
    ax.set_title(row["state_pair"])
    # Label the x axis.
    ax.set_xlabel("image index")
    # Label the y axis.
    ax.set_ylabel("adsorption energy / eV")

# Prevent crowding between panels.
plt.tight_layout()
# Show the full stack of pathway plots.
plt.show()
"""
        ),
        md("## 5. Focus on the two most methanol-relevant endgame transformations"),
        code(
            r"""
# Keep only the two endgame transformations that connect directly to methanol-like products.
endgame_pairs = [
    "H2COOH_AB_2 -> H2CO_OH_1-1",
    "CH3O_H_1_BB -> H3COH_1-1",
]

# Select only the matching copt rows.
endgame = cu211_ga_copt[cu211_ga_copt["state_pair"].isin(endgame_pairs)].copy()

# Show the filtered table so the user can inspect the exact rows involved.
endgame[["Name", "state_pair", "image", "E_ads_mu_eV", "fmax"]].head(30)
"""
        ),
        code(
            """
# Create a two-panel figure for the endgame transformations.
fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)

# Loop over the two target pairs and their subplot axes together.
for ax, pair in zip(axes, endgame_pairs, strict=False):
    # Select the images belonging to the current endgame pair.
    prof = endgame[endgame["state_pair"].eq(pair)].sort_values("image")
    # Plot the adsorption-energy profile because this is the quantity we want to compare mechanistically.
    ax.plot(prof["image"], prof["E_ads_mu_eV"], marker="o", linewidth=2.5, color="#54a24b")
    # Annotate each point with the image number for notebook readability.
    for _, row in prof.iterrows():
        ax.text(row["image"], row["E_ads_mu_eV"] + 0.08, str(int(row["image"])), ha="center", fontsize=9)
    # Title the subplot with the state pair.
    ax.set_title(pair)
    # Label the x axis.
    ax.set_xlabel("image index")

# Label the shared y axis once.
axes[0].set_ylabel("adsorption energy / eV")
# Tight layout improves spacing.
plt.tight_layout()
# Show the endgame figure.
plt.show()
"""
        ),
        code(
            """
# Quantify the span of each endgame path as a simple notebook-level diagnostic.
endgame_summary = (
    endgame.groupby("state_pair", as_index=False)
    .agg(
        n_images=("image", "size"),
        min_ads_E=("E_ads_mu_eV", "min"),
        max_ads_E=("E_ads_mu_eV", "max"),
    )
)
# Compute the energy span across each trajectory.
endgame_summary["energy_span_eV"] = endgame_summary["max_ads_E"] - endgame_summary["min_ads_E"]
# Display the result table.
endgame_summary
"""
        ),
        code(
            """
# Plot the energy span for the two endgame transformations.
fig, ax = plt.subplots(figsize=(8.5, 4.5))
# Use vertical bars because only two transformations are compared.
ax.bar(endgame_summary["state_pair"], endgame_summary["energy_span_eV"], color=["#72b7b2", "#b279a2"])
# Rotate the labels so the pair names stay readable.
ax.tick_params(axis="x", rotation=25)
# Label the y axis.
ax.set_ylabel("adsorption-energy span / eV")
# Add a clear title.
ax.set_title("How strongly do the Cu-211-Ga adsorption-energy trajectories vary along the path?")
# Tight layout avoids clipped labels.
plt.tight_layout()
# Show the chart.
plt.show()
"""
        ),
        code(
            """
# Compare the minimum adsorption energy of each endgame pair directly.
fig, ax = plt.subplots(figsize=(8.5, 4.5))
# Draw one bar per endgame transformation.
ax.bar(endgame_summary["state_pair"], endgame_summary["min_ads_E"], color=["#4c78a8", "#f58518"])
# Rotate labels for readability.
ax.tick_params(axis="x", rotation=25)
# Label the y axis.
ax.set_ylabel("minimum adsorption energy / eV")
# Add a compact title.
ax.set_title("Lowest adsorption-energy point reached along each endgame path")
# Tight layout avoids clipping.
plt.tight_layout()
# Show the figure.
plt.show()
"""
        ),
        md("## 6. Draw literature-style CO2-to-methanol reaction diagrams with barriers"),
        md(
            """
For a theoretical-chemistry reaction diagram, the states should follow a
chemical argument rather than the arbitrary order in which they appear in the
database.

Here we therefore interpret the Cu-211-Ga dataset along a hydrogenation route:

`CO2 -> HCOOH -> H2COOH -> H2CO_OH -> H2CO_H -> CH3O_H -> H3COH`

This is not a claim that every elementary step is fully resolved. It is a
disciplined way to combine:

- observed static minima,
- copt-derived barrier estimates where available,
- and explicit dashed gaps where the archive does not yet contain a direct
  transition-state path.

The last state is `H3COH`, because the Cu-211-Ga subset does not contain an
adsorbed `CH3OH` final state. In practice, `H3COH` is treated here as the
last methanol-like surface intermediate supported by the present data.
"""
        ),
        code(
            """
# Create a helper that maps a raw pathway label back to the closest canonical state token.
def canonical_state_token(text):
    # Scan the ordered token list from longest to shortest so longer labels win.
    for token in METHANOL_MATCH_TOKENS:
        # Return the first token that appears in the text.
        if token in str(text):
            return token
    # Fall back to an empty string if no canonical token is recognized.
    return ""

# Build a lookup from canonical state token to the best static adsorption energy.
static_energy_map = best_static.set_index("state")["best_ads_E"].to_dict()

# Keep only well-sampled pathways because sparse trajectories are poor barrier references.
transition_summary = profiles[profiles["n_images"] >= 5].copy()

# Convert the left pathway label into a canonical state token.
transition_summary["initial_token"] = transition_summary["state_left"].map(canonical_state_token)
# Convert the right pathway label into a canonical state token.
transition_summary["final_token"] = transition_summary["state_right"].map(canonical_state_token)

# Attach the best static adsorption energy for the initial state.
transition_summary["E_initial"] = transition_summary["initial_token"].map(static_energy_map)
# Attach the best static adsorption energy for the final state.
transition_summary["E_final"] = transition_summary["final_token"].map(static_energy_map)
# Interpret the highest copt image energy as an approximate transition-state energy.
transition_summary["E_TS"] = transition_summary["Emax_ads"]

# Compute the forward barrier relative to the initial minimum.
transition_summary["barrier_forward_eV"] = transition_summary["E_TS"] - transition_summary["E_initial"]
# Compute the reverse barrier relative to the final minimum.
transition_summary["barrier_reverse_eV"] = transition_summary["E_TS"] - transition_summary["E_final"]
# Compute the reaction energy between final and initial state minima.
transition_summary["reaction_energy_eV"] = transition_summary["E_final"] - transition_summary["E_initial"]

# Keep only transitions where both endpoints can be mapped to static minima.
transition_summary = transition_summary.dropna(subset=["E_initial", "E_final", "E_TS"]).copy()

# Display the literature-style transition summary table.
transition_summary[
    [
        "state_pair",
        "initial_token",
        "final_token",
        "n_images",
        "E_initial",
        "E_TS",
        "E_final",
        "barrier_forward_eV",
        "barrier_reverse_eV",
        "reaction_energy_eV",
    ]
]
"""
        ),
        code(
            """
# Plot the forward and reverse barriers for the observed Cu-211-Ga transitions.
fig, ax = plt.subplots(figsize=(11, 5.5))
# Place the transition labels on the x axis.
x = range(len(transition_summary))
# Plot the forward barrier as the first bar set.
ax.bar([value - 0.18 for value in x], transition_summary["barrier_forward_eV"], width=0.36, label="forward barrier", color="#e45756")
# Plot the reverse barrier as the second bar set.
ax.bar([value + 0.18 for value in x], transition_summary["barrier_reverse_eV"], width=0.36, label="reverse barrier", color="#4c78a8")
# Use the human-readable state pair labels on the axis.
ax.set_xticks(list(x))
# Rotate labels because pathway names are long.
ax.set_xticklabels(transition_summary["state_pair"], rotation=25, ha="right")
# Label the y axis.
ax.set_ylabel("barrier / eV")
# Title the figure in literature-style language.
ax.set_title("Approximate forward and reverse barriers from Cu-211-Ga copt trajectories")
# Keep the legend visible.
ax.legend()
# Tight layout avoids clipping.
plt.tight_layout()
# Show the figure.
plt.show()
"""
        ),
        code(
            """
# Plot reaction energy against forward barrier to classify the observed elementary steps.
fig, ax = plt.subplots(figsize=(7.5, 5.5))
# Scatter each transition as one point in barrier-reaction-energy space.
ax.scatter(
    transition_summary["reaction_energy_eV"],
    transition_summary["barrier_forward_eV"],
    s=110,
    color="#54a24b",
    alpha=0.9,
)
# Annotate each point with a short state-pair label.
for _, row in transition_summary.iterrows():
    ax.text(
        row["reaction_energy_eV"] + 0.03,
        row["barrier_forward_eV"] + 0.03,
        row["initial_token"] + " -> " + row["final_token"],
        fontsize=9,
    )
# Label the x axis.
ax.set_xlabel("reaction energy / eV")
# Label the y axis.
ax.set_ylabel("forward barrier / eV")
# Add a title.
ax.set_title("Barrier-reaction-energy map for Cu-211-Ga methanol-related steps")
# Add guide lines at zero.
ax.axvline(0, color="gray", linewidth=1, linestyle="--")
ax.axhline(0, color="gray", linewidth=1, linestyle="--")
# Tight layout keeps labels visible.
plt.tight_layout()
# Show the figure.
plt.show()
"""
        ),
        code(
            """
# Draw one literature-style reaction-coordinate panel per well-resolved copt transition.
fig, axes = plt.subplots(len(transition_summary), 1, figsize=(9.5, 2.9 * len(transition_summary)), sharex=False)
# Normalize the axes object for a single transition.
if len(transition_summary) == 1:
    axes = [axes]

# Loop over the transition table row by row.
for ax, (_, row) in zip(axes, transition_summary.iterrows(), strict=False):
    # Define a simple three-point reaction coordinate: initial minimum, transition state, final minimum.
    x_points = [0.0, 1.0, 2.0]
    y_points = [row["E_initial"], row["E_TS"], row["E_final"]]
    # Draw the literature-style reaction path.
    ax.plot(x_points, y_points, color="black", linewidth=1.8)
    # Mark the stationary points explicitly.
    ax.scatter(x_points, y_points, color=["#4c78a8", "#e45756", "#54a24b"], s=70, zorder=3)
    # Draw short horizontal line segments for the minima and the transition state.
    ax.hlines(row["E_initial"], -0.18, 0.18, color="#4c78a8", linewidth=3)
    ax.hlines(row["E_TS"], 0.82, 1.18, color="#e45756", linewidth=3)
    ax.hlines(row["E_final"], 1.82, 2.18, color="#54a24b", linewidth=3)
    # Annotate the state labels directly on the panel.
    ax.text(0.0, row["E_initial"] - 0.08, row["initial_token"], ha="center", va="top", fontsize=9)
    ax.text(1.0, row["E_TS"] + 0.08, "TS", ha="center", va="bottom", fontsize=9)
    ax.text(2.0, row["E_final"] - 0.08, row["final_token"], ha="center", va="top", fontsize=9)
    # Annotate the forward barrier near the transition state.
    ax.text(1.08, row["E_TS"], f\"Ea={row['barrier_forward_eV']:.2f} eV\", fontsize=9, va=\"center\")
    # Title each panel with the full state pair.
    ax.set_title(row["state_pair"])
    # Remove unused x ticks because the coordinate is schematic.
    ax.set_xticks([])
    # Label the y axis.
    ax.set_ylabel("adsorption energy / eV")

# Tight layout keeps all panels readable.
plt.tight_layout()
# Show the figure stack.
plt.show()
"""
        ),
        code(
            """
# Build a chemically reasoned CO2-hydrogenation sequence toward a methanol-like surface product.
mechanism_states = ["CO2", "HCOOH", "H2COOH", "H2CO_OH", "H2CO_H", "CH3O_H", "H3COH"]

# Build a transition-state lookup from the observed copt summaries.
ts_lookup = {
    (row["initial_token"], row["final_token"]): row["E_TS"]
    for _, row in transition_summary.iterrows()
}

# Build an ordered table of the mechanistic minima.
mechanism_table = pd.DataFrame(
    {
        "state": mechanism_states,
        "best_adsorption_energy_eV": [static_energy_map.get(state, np.nan) for state in mechanism_states],
    }
)

# Use adsorbed CO2 as the left-hand energy reference in the reaction diagram.
E_CO2_ads = static_energy_map.get("CO2", np.nan)
mechanism_table["relative_to_CO2_eV"] = mechanism_table["best_adsorption_energy_eV"] - E_CO2_ads

# Show the ordered mechanism table before plotting.
mechanism_table
"""
        ),
        code(
            """
# Plot the chemically ordered minima relative to adsorbed CO2.
fig, ax = plt.subplots(figsize=(11, 4.8))
# Keep only rows with real energy values.
plot_table = mechanism_table.dropna(subset=["best_adsorption_energy_eV"]).copy()
# Draw the ordered line of minima.
ax.plot(plot_table["state"], plot_table["relative_to_CO2_eV"], marker="o", linewidth=2.4, color="#1f77b4")
# Add a zero line at the CO2 adsorption reference.
ax.axhline(0, color="gray", linestyle="--", linewidth=1)
# Label the axes.
ax.set_ylabel(r"$E_{ads} - E_{ads}(CO2)$ / eV")
ax.set_xlabel("reaction intermediate")
# Rotate labels to keep them readable.
ax.tick_params(axis="x", rotation=30)
# Title the figure in chemistry language.
ax.set_title("CO2 hydrogenation sequence toward methanol-like surface products")
# Tight layout avoids clipping.
plt.tight_layout()
# Show the plot.
plt.show()
"""
        ),
        code(
            """
# Create a composite literature-style reaction coordinate from CO2 to the last methanol-like state.
fig, ax = plt.subplots(figsize=(12.5, 5.8))

# Define equally spaced x positions for the chemically ordered intermediates.
state_x = {state: 2.0 * idx for idx, state in enumerate(mechanism_states)}

# Draw the stable-state horizontal levels first, now relative to adsorbed CO2.
for state in mechanism_states:
    # Skip states that are absent from the current subset.
    if state not in static_energy_map:
        continue
    # Convert the minimum to the CO2-relative scale.
    y_state = static_energy_map[state] - E_CO2_ads
    # Draw a thick horizontal segment for the minimum.
    ax.hlines(y_state, state_x[state] - 0.28, state_x[state] + 0.28, color="black", linewidth=3)
    # Place the state label below the line.
    ax.text(state_x[state], y_state - 0.10, state, ha="center", va="top", fontsize=10)

# Define the mechanistic edges that express the chemical reasoning.
mechanism_edges = [
    ("CO2", "HCOOH"),
    ("HCOOH", "H2COOH"),
    ("H2COOH", "H2CO_OH"),
    ("H2CO_OH", "H2CO_H"),
    ("H2CO_H", "CH3O_H"),
    ("CH3O_H", "H3COH"),
]

# Draw each elementary step in sequence.
for left_state, right_state in mechanism_edges:
    # Skip the step if one endpoint is missing.
    if left_state not in static_energy_map or right_state not in static_energy_map:
        continue
    # Read the x and y coordinates of the two minima on the CO2-relative scale.
    x0 = state_x[left_state]
    x1 = state_x[right_state]
    y0 = static_energy_map[left_state] - E_CO2_ads
    y1 = static_energy_map[right_state] - E_CO2_ads
    # Check whether a direct copt-derived transition state is available.
    has_ts = (left_state, right_state) in ts_lookup
    # Use a barrier profile when the transition state exists.
    if has_ts:
        xts = 0.5 * (x0 + x1)
        yts = ts_lookup[(left_state, right_state)] - E_CO2_ads
        ax.plot([x0, xts, x1], [y0, yts, y1], color="#d62728", linewidth=2.2)
        ax.scatter([xts], [yts], color="#d62728", s=70, zorder=3)
        ax.text(xts, yts + 0.10, "TS", ha="center", fontsize=9)
        ax.text(xts + 0.10, yts, f"{yts - y0:.2f} eV", fontsize=8, va="center")
    else:
        ax.plot([x0, x1], [y0, y1], linestyle="--", color="gray", linewidth=1.5)
        ax.text(
            0.5 * (x0 + x1),
            0.5 * (y0 + y1) + 0.12,
            "no direct copt barrier",
            ha="center",
            fontsize=8,
            color="gray",
        )

# Add an annotation explaining the reactant-side interpretation.
ax.text(
    state_x["CO2"] - 0.8,
    0.35,
    "entry state: adsorbed CO2\\nwith H2 as the hydrogen reservoir",
    fontsize=9,
    ha="left",
)

# Add an annotation explaining the product-side interpretation.
if "H3COH" in static_energy_map:
    ax.text(
        state_x["H3COH"] + 0.35,
        static_energy_map["H3COH"] - E_CO2_ads + 0.18,
        "last available methanol-like state\\n(no adsorbed CH3OH in this subset)",
        fontsize=9,
        ha="left",
    )

# Remove metric x ticks because this is a schematic reaction coordinate.
ax.set_xticks([])
# Label the y axis.
ax.set_ylabel(r"$E_{ads} - E_{ads}(CO2)$ / eV")
# Title the full reaction diagram.
ax.set_title("Cu-211-Ga reaction coordinate for CO2 hydrogenation toward methanol-like products")
# Tight layout improves readability.
plt.tight_layout()
# Show the summary reaction diagram.
plt.show()
"""
        ),
        md("## 7. Create a structure presentation for the reaction-diagram states"),
        md(
            """
The `DFTDataFrame` package already contains a presentation helper that renders
top and side views for a set of structures and writes a Beamer-style LaTeX
slide deck.

In the next cells we use that existing function directly from inside the
notebook. The goal is to assemble a presentation of:

- the representative minima in the CO2-to-methanol sequence,
- and the representative transition-state images taken from the `copt` paths.

To keep the notebook lightweight, the code below writes the `.tex` file and
the structure images by default, but does not force a LaTeX compilation unless
you explicitly switch `compile_tex=True`.
"""
        ),
        code(
            """
# Import the presentation helper directly from the local DFTDataFrame package.
from DFTDataFrame.Presentation import presentation as dft_presentation

# Build a folder for the structure images created by the presentation helper.
presentation_root = Path("notebooks/created_frame_phd_analysis/cu211_ga_reaction_presentation")
presentation_root.mkdir(parents=True, exist_ok=True)

# Choose one representative minimum for each mechanistic state.
minimum_presentation_rows = []
for state in mechanism_states:
    # Select all static structures belonging to the current state.
    sub = static_rows[static_rows["state"].eq(state)].copy()
    # Skip states that are absent from the static subset.
    if sub.empty:
        continue
    # Sort by adsorption energy so the first row is the best minimum.
    sub = sub.sort_values("E_ads_mu_eV")
    # Take the lowest-energy representative.
    row = sub.iloc[0].copy()
    # Annotate the row with presentation metadata.
    row["slide_title"] = state + " minimum"
    row["sequence_index"] = mechanism_states.index(state)
    row["presentation_kind"] = "minimum"
    row["state_label"] = state
    minimum_presentation_rows.append(row)

# Choose one representative transition-state image for each resolved mechanistic copt step.
ts_presentation_rows = []
for left_state, right_state in mechanism_edges:
    # Select copt rows that match the current mechanistic edge.
    pair_rows = cu211_ga_copt[
        cu211_ga_copt["state_left"].map(canonical_state_token).eq(left_state)
        & cu211_ga_copt["state_right"].map(canonical_state_token).eq(right_state)
    ].copy()
    # Skip edges without direct copt support.
    if pair_rows.empty:
        continue
    # Sort so the highest adsorption-energy image is interpreted as the TS estimate.
    pair_rows = pair_rows.sort_values("E_ads_mu_eV", ascending=False)
    # Take the top-energy image as the transition-state representative.
    row = pair_rows.iloc[0].copy()
    # Annotate the row for the slide deck.
    row["slide_title"] = left_state + " to " + right_state + " TS"
    row["sequence_index"] = mechanism_edges.index((left_state, right_state)) + 0.5
    row["presentation_kind"] = "transition_state"
    row["state_label"] = left_state + " -> " + right_state
    ts_presentation_rows.append(row)

# Combine minima and transition states into one presentation dataframe.
presentation_frame = pd.DataFrame(minimum_presentation_rows + ts_presentation_rows).copy()

# Sort the rows along the reaction sequence.
presentation_frame = presentation_frame.sort_values(["sequence_index", "presentation_kind"]).reset_index(drop=True)

# Keep only the columns we want to show in the slide captions.
presentation_columns = [
    "state_label",
    "presentation_kind",
    "E_ads_mu_eV",
    "fmax",
]

# Preview the presentation frame before rendering images and slides.
presentation_frame[["slide_title", "state_label", "presentation_kind", "E_ads_mu_eV", "fmax", "Name"]]
"""
        ),
        code(
            """
# Define the target LaTeX file for the reaction presentation.
presentation_tex = presentation_root / "cu211_ga_reaction_structures.tex"

# Run the DFTDataFrame presentation helper.
dft_presentation(
    Frame=presentation_frame.copy(),
    Title="Cu-211-Ga CO2 hydrogenation reaction structures",
    columns=presentation_columns,
    figureroot=str(presentation_root),
    sorting=["sequence_index", "presentation_kind"],
    presentation_path_and_name=str(presentation_tex),
    slidetitles="slide_title",
    compile_tex=False,
    center_el="C",
)

# Return the key output paths so the user can inspect them directly.
pd.Series(
    {
        "presentation_tex": str(presentation_tex),
        "presentation_image_root": str(presentation_root),
        "n_slides_requested": len(presentation_frame),
    }
)
"""
        ),
        code(
            """
# Show the files created in the presentation folder.
sorted(path.name for path in presentation_root.iterdir())
"""
        ),
        code(
            """
# Preview a subset of the generated top and side images directly inside the notebook.
from IPython.display import display, Image as IPyImage, Markdown

# Loop over the first few presentation rows so the preview stays compact.
for _, row in presentation_frame.head(4).iterrows():
    # Recreate the sanitized figure name used by the DFTDataFrame presentation helper.
    figname = row["Name"]
    # Remove special characters except the dash, matching the presentation helper logic.
    for special in '!"#$%&\\'()*+,./:;<=>?@[\\\\]^`{|}~':
        if special == "-":
            continue
        figname = figname.replace(special, "")
    # Build the expected image paths.
    top_path = presentation_root / (figname + "-top.png")
    side_path = presentation_root / (figname + "-side.png")
    # Show a short header before the two structure views.
    display(Markdown(f"**{row['slide_title']}**"))
    # Display the top view if it exists.
    if top_path.exists():
        display(IPyImage(filename=str(top_path), width=280))
    # Display the side view if it exists.
    if side_path.exists():
        display(IPyImage(filename=str(side_path), width=280))
"""
        ),
        md("## 8. Didactic closing table"),
        code(
            """
# Build a final table that combines the best static anchor states with their adsorption energies.
anchor_table = best_static[["state", "n_structures", "best_name", "best_ads_E", "median_ads_E", "best_fmax"]].copy()
# Rename columns so the table reads naturally in a teaching context.
anchor_table.columns = ["state", "n_structures", "representative_structure", "best_adsorption_energy_eV", "median_adsorption_energy_eV", "best_fmax"]
# Display the final anchor table.
anchor_table
"""
        ),
        md(
            """
### Chemical reading

This Cu-211-Ga branch is useful because it contains both:

- a dense collection of curated static intermediates, and
- explicit constrained images for the late hydrogenation steps.

That combination lets a student see how a reaction-path narrative is assembled:
not by guessing a mechanism from one final plot, but by filtering the archive,
verifying the reference surfaces, checking convergence quality, ranking the
static intermediates by **adsorption energy**, and then using `copt`
sequences to connect neighboring chemical states on the same chemical
reference scale.
"""
        ),
    ]
    return notebook("06 - Cu-211-Ga Methanol Mechanism, Step by Step", cells)


def write_notebooks() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    notebooks = {
        "00_dataset_atlas_created_frame.ipynb": make_00(),
        "01_convergence_and_materials_taxonomy.ipynb": make_01(),
        "02_adsorbate_chemistry_and_reference_energies.ipynb": make_02(),
        "03_local_structure_descriptors_and_coordination.ipynb": make_03(),
        "04_reaction_pathways_and_copt_landscapes.ipynb": make_04(),
        "05_curated_methanol_reaction_path.ipynb": make_05(),
        "06_cu211_ga_methanol_mechanism_step_by_step.ipynb": make_06(),
    }
    written: list[Path] = []
    for name, nb in notebooks.items():
        path = OUT / name
        path.write_text(nbf.writes(nb), encoding="utf-8")
        written.append(path)
    readme = OUT / "README.md"
    readme.write_text(
        (
            "# created_frame.hdf analysis notebooks\n\n"
            "This notebook series analyzes the `created_frame.hdf` table referenced by\n"
            "`$ONEPIECE_DATA_ROOT/created_frame.hdf`\n"
            "with the local `DFTDataFrame` package as the available OnePiece-compatible\n"
            "analysis layer.\n\n"
            "Notebooks:\n\n"
            "1. `00_dataset_atlas_created_frame.ipynb`\n"
            "2. `01_convergence_and_materials_taxonomy.ipynb`\n"
            "3. `02_adsorbate_chemistry_and_reference_energies.ipynb`\n"
            "4. `03_local_structure_descriptors_and_coordination.ipynb`\n"
            "5. `04_reaction_pathways_and_copt_landscapes.ipynb`\n"
            "6. `05_curated_methanol_reaction_path.ipynb`\n"
            "7. `06_cu211_ga_methanol_mechanism_step_by_step.ipynb`\n\n"
            "All plots are written as interactive notebook plots with `plt.show()`.\n"
        ),
        encoding="utf-8",
    )
    written.append(readme)
    return written


if __name__ == "__main__":
    for path in write_notebooks():
        print(path)
