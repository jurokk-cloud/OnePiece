from __future__ import annotations

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]


def md(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


def make_notebook():
    cells = [
        md(
            """
# Software Notebook: Adsorption Energies and Constrained-Optimization Barriers

This notebook demonstrates the calculation workflow for a local Python package
that reads OnePiece/pandas HDF databases and produces:

- clean-surface reference assignments,
- CO adsorption-energy tables,
- methanol-to-methoxy (`CH3OH -> CH3O*`) adsorption-energy tables,
- constrained-optimization (`copt`) barrier profiles,
- all plots used to inspect the workflow.

The goal is software, not a thesis chapter: every calculation is delegated to
the reusable `onepiece.adsorption` module, while this notebook shows the scientific
and pandas reasoning step by step.
"""
        ),
        md(
            """
## 1. Computational chemistry model

For every adsorbed slab row, the software first finds the corresponding clean
surface row **inside the same HDF file**.

For CO adsorption:

\\[
E_{ads}(CO) = \\frac{E(nCO*) - E(*) - nE(CO_{gas})}{n}
\\]

For methoxy produced from methanol:

\\[
* + CH_3OH(g) \\rightarrow CH_3O* + \\frac{1}{2}H_2(g)
\\]

\\[
E_{ads}(CH_3OH \\rightarrow CH_3O*) =
\\frac{E(nCH_3O*) + \\frac{n}{2}E(H_2) - E(*) - nE(CH_3OH)}{n}
\\]

The HDF files provided here contain `CH3O` rows, not direct `CH3OH` rows. Gas
energies must come from matching DFT gas calculations; this notebook keeps them
as `NaN` until they are filled.
"""
        ),
        code(
            f"""
from pathlib import Path
import importlib.util
import os
import sys

import numpy as np
import pandas as pd
from IPython.display import Image, display

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib-onepiece-studio")

# Compatibility shim for HDF files written with another NumPy/PyTables stack.
try:
    import numpy.core as numpy_core
    sys.modules.setdefault("numpy._core", numpy_core)
    sys.modules.setdefault("numpy._core.multiarray", np.core.multiarray)
    sys.modules.setdefault("numpy._core.numeric", np.core.numeric)
except Exception as exc:
    print("NumPy compatibility shim skipped:", exc)

PROJECT_ROOT = Path(r"{PROJECT_ROOT}")
NOTEBOOK_ROOT = PROJECT_ROOT / "notebooks" / "adsorption_barrier_software"
OUTPUT_ROOT = NOTEBOOK_ROOT / "outputs"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

DATA_ROOT = Path(os.environ.get("ONEPIECE_DATA_ROOT", "data/chapter6"))
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
        md("## 2. Import the adsorption software"),
        code(
            """
def import_adsorption_module():
    src_root = PROJECT_ROOT / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    try:
        from onepiece import adsorption as ads
        return ads
    except Exception:
        module_path = src_root / "onepiece" / "adsorption.py"
        spec = importlib.util.spec_from_file_location("onepiece_adsorption_direct", module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

ads = import_adsorption_module()
ads
"""
        ),
        md("## 3. Inspect input files"),
        code(
            """
pd.DataFrame(
    [{"dataset": label, "path": str(path), "exists": path.exists()} for label, path in HDF_FILES.items()]
)
"""
        ),
        md(
            """
## 4. Assign references before merging

This is the central package call. Internally it reads each HDF file, derives
`adsorbate` and `surface_key`, chooses the clean reference per source, and only
then merges the frames.
"""
        ),
        code(
            """
combined, references = ads.assign_references_before_merge(HDF_FILES)
combined.shape, references.shape
"""
        ),
        code(
            """
reference_quality = (
    combined.loc[combined["is_adsorbate"]]
    .groupby(["dataset_label", "surface_ref_status"])
    .size()
    .unstack(fill_value=0)
)
reference_quality
"""
        ),
        md("## 5. Calculate adsorption energy columns"),
        code(
            """
# Replace these NaN values with gas-phase DFT energies from the same setup.
gas_references_ev = {
    "CO": np.nan,
    "CH3OH": np.nan,
    "H2": np.nan,
}

results = ads.add_adsorption_energies(combined, gas_references_ev)
adsorption = ads.adsorption_view(results)
adsorption.head(12)
"""
        ),
        code(
            """
adsorption_summary = adsorption.groupby(["dataset_label", "adsorbate", "surface_ref_status"]).agg(
    rows=("Name", "count"),
    median_delta_E_to_surface_eV=("delta_E_to_surface_eV", "median"),
    min_delta_E_to_surface_eV=("delta_E_to_surface_eV", "min"),
    max_delta_E_to_surface_eV=("delta_E_to_surface_eV", "max"),
).reset_index()
adsorption_summary.sort_values(["dataset_label", "adsorbate", "surface_ref_status"]).head(40)
"""
        ),
        md(
            """
## 6. Detect constrained-optimization barrier scans

The Chapter 6 HDF files contain `copt` paths such as:

`.../copt/CO_H%HCO/1/00` through `.../06`

The software parses:

- reaction family: `CO_H%HCO`,
- path id: `1`,
- step: `00`, `01`, ...,
- energy profile relative to step 0,
- apparent forward barrier: `max(E) - E_initial`.

This is an approximate constrained-optimization barrier, not a NEB transition
state proof.
"""
        ),
        code(
            """
copt_points = ads.copt_profile_points(results)
barriers = ads.copt_barrier_summary(results)

copt_points.shape, barriers.shape
"""
        ),
        code(
            """
barriers[
    ["copt_reaction", "copt_path_id", "n_points", "forward_barrier_eV", "reverse_barrier_eV", "reaction_energy_eV", "ts_step", "complete_scan"]
].sort_values("forward_barrier_eV", ascending=False).head(20)
"""
        ),
        md("## 7. Save all analysis tables"),
        code(
            """
table_paths = {
    "combined": OUTPUT_ROOT / "chapter6_adsorption_barrier_dataset.pkl",
    "references": OUTPUT_ROOT / "surface_references.csv",
    "adsorption": OUTPUT_ROOT / "adsorption_energy_view.csv",
    "copt_points": OUTPUT_ROOT / "copt_barrier_points.csv",
    "barriers": OUTPUT_ROOT / "copt_barrier_summary.csv",
}

results.to_pickle(table_paths["combined"])
references.to_csv(table_paths["references"], index=False)
adsorption.to_csv(table_paths["adsorption"], index=False)
copt_points.to_csv(table_paths["copt_points"], index=False)
barriers.to_csv(table_paths["barriers"], index=False)

table_paths
"""
        ),
        md(
            """
## 8. Plot workflow

The plotting code is kept in `run_adsorption_barrier_analysis.py` so the same
figures can be generated from a terminal or from this notebook. The cells below
show the pandas table behind each plot before calling the plotting function.
"""
        ),
        code(
            """
spec = importlib.util.spec_from_file_location(
    "adsorption_barrier_analysis",
    NOTEBOOK_ROOT / "run_adsorption_barrier_analysis.py",
)
workflow = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = workflow
spec.loader.exec_module(workflow)
"""
        ),
        md("### Plot 1: reference assignment quality"),
        code(
            """
reference_quality
"""
        ),
        code(
            """
path = workflow.plot_reference_status(adsorption)
display(Image(filename=str(path)))
"""
        ),
        md("### Plot 2: CO and CH3O delta-E distributions"),
        code(
            """
distribution_input = adsorption.loc[
    adsorption["surface_ref_status"].eq("ok")
    & adsorption["adsorbate"].isin(["CO", "CH3O"])
    & adsorption["delta_E_to_surface_eV"].notna()
    & adsorption["delta_E_to_surface_eV"].between(-80, 25)
]

distribution_input.groupby(["dataset_label", "adsorbate"]).agg(
    rows=("Name", "count"),
    median_delta_E=("delta_E_to_surface_eV", "median"),
    min_delta_E=("delta_E_to_surface_eV", "min"),
    max_delta_E=("delta_E_to_surface_eV", "max"),
)
"""
        ),
        code(
            """
path = workflow.plot_adsorption_delta_distribution(adsorption)
display(Image(filename=str(path)))
"""
        ),
        md("### Plot 3: most exothermic adsorption candidates"),
        code(
            """
best_candidates = (
    distribution_input.sort_values("delta_E_to_surface_eV")
    .groupby(["dataset_label", "adsorbate"])
    .head(3)
    .sort_values("delta_E_to_surface_eV")
)
best_candidates[["dataset_label", "adsorbate", "Name", "delta_E_to_surface_eV", "surface_ref_name"]].head(20)
"""
        ),
        code(
            """
path = workflow.plot_best_adsorption_candidates(adsorption)
display(Image(filename=str(path)))
"""
        ),
        md("### Plot 4: constrained-optimization barrier ranking"),
        code(
            """
barrier_ranking_input = barriers.loc[barriers["n_points"] >= 3].sort_values(
    "forward_barrier_eV", ascending=False
)
barrier_ranking_input[
    ["copt_reaction", "copt_path_id", "n_points", "forward_barrier_eV", "reaction_energy_eV", "complete_scan"]
].head(16)
"""
        ),
        code(
            """
path = workflow.plot_barrier_ranking(barriers)
display(Image(filename=str(path)))
"""
        ),
        md("### Plot 5: constrained-optimization profile small multiples"),
        code(
            """
top_series = barriers.sort_values("forward_barrier_eV", ascending=False).head(8)["copt_series_id"]
profile_input = copt_points.loc[copt_points["copt_series_id"].isin(top_series)]
profile_input[
    ["copt_reaction", "copt_path_id", "copt_step", "E", "relative_E_from_initial_eV", "Name"]
].head(30)
"""
        ),
        code(
            """
path = workflow.plot_copt_profiles(copt_points, barriers)
display(Image(filename=str(path)))
"""
        ),
        md(
            """
## 9. Software design notes for the UI

The package now has a clear analysis boundary:

- `onepiece.adsorption.assign_references_before_merge`: scientific data preparation,
- `onepiece.adsorption.add_adsorption_energies`: reaction-energy formulas,
- `onepiece.adsorption.adsorption_view`: UI-ready focused table,
- `onepiece.adsorption.copt_profile_points`: point-level barrier profiles,
- `onepiece.adsorption.copt_barrier_summary`: scan-level barrier metrics.

In the UI this should appear as an analysis workflow:

1. select HDF sources,
2. assign references per source,
3. inspect missing/ambiguous references,
4. choose gas-phase references,
5. calculate adsorption energies,
6. inspect constrained barriers,
7. export selected rows or exclude bad calculations.
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
    path = ROOT / "01_adsorption_energy_and_barrier_software.ipynb"
    nbf.write(make_notebook(), path)
    print(path)
