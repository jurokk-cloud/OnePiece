from __future__ import annotations

import os

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
OUT = ROOT / "onepiece_phase_tutorial"
DATA_ROOT = Path(os.environ.get("ONEPIECE_DATA_ROOT", "data/surface_alloys"))
OUTPUT_ROOT = ROOT / "phase_diagram_outputs"


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
import re
import sys

import numpy as np
import pandas as pd

# Compatibility shim for HDF files written in a different NumPy/PyTables stack.
# Keep this cell at the top before calling pd.read_hdf.
try:
    import numpy.core as npc
    sys.modules.setdefault("numpy._core", npc)
    sys.modules.setdefault("numpy._core.multiarray", np.core.multiarray)
    sys.modules.setdefault("numpy._core.numeric", np.core.numeric)
except Exception as exc:
    print("NumPy compatibility shim skipped:", exc)

DATA_ROOT = Path(r"{DATA_ROOT}")
PROJECT_ROOT = Path(r"{PROJECT_ROOT}")
OUTPUT_ROOT = Path(r"{OUTPUT_ROOT}")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

HDF_FILES = {{
    "bulk": DATA_ROOT / "CuGabulk.hdf",
    "bulk_oxide": DATA_ROOT / "CuGabulk_oxide.hdf",
    "surface_100": DATA_ROOT / "CuGasurf_100.hdf",
    "surface_110": DATA_ROOT / "CuGasurf_110.hdf",
    "surface_111": DATA_ROOT / "CuGasurf_111.hdf",
    "surface_211": DATA_ROOT / "CuGasurf_211.hdf",
}}

def read_onepiece_hdf(path, key="df"):
    \"\"\"Read a OnePiece-exported pandas HDF table.

    OnePiece stores simulation records in a pandas DataFrame. The HDF files in
    this tutorial are read with pd.read_hdf(filename, key="df").
    \"\"\"
    path = Path(path)
    frame = pd.read_hdf(path, key=key)
    frame.attrs["source_hdf"] = str(path)
    return frame

def formula_counts(formula):
    if not isinstance(formula, str):
        return {{}}
    counts = {{}}
    for element, number in re.findall(r"([A-Z][a-z]?)(\\d*)", formula):
        counts[element] = counts.get(element, 0) + int(number or 1)
    return counts
"""


def make_00():
    cells = [
        md(
            """
Dieses Notebook startet direkt bei den OnePiece-HDF-Dateien. Ziel ist, die
Daten als `pandas.DataFrame` zu laden, wichtige Spalten zu verstehen und zu
zeigen, wie ASE-Objekte in solchen Tabellen typischerweise vorkommen.

**Konzept:** OnePiece ist hier die Datenbank-Schicht. Pandas ist die tabellarische
Arbeitsfläche. ASE (`ase.Atoms`) beschreibt die atomaren Strukturen, die in
DataFrame-Spalten gespeichert oder aus Dateien referenziert werden können.
"""
        ),
        code(COMMON_SETUP),
        md("## HDF-Dateien prüfen"),
        code(
            """
for label, path in HDF_FILES.items():
    print(f"{label:12s}", path.exists(), path)
"""
        ),
        md("## Eine OnePiece-Tabelle als DataFrame laden"),
        code(
            """
df_111 = read_onepiece_hdf(HDF_FILES["surface_111"])
print(df_111.shape)
df_111.head()
"""
        ),
        md(
            """
Ein `DataFrame` ist eine Tabelle mit Zeilen und Spalten:

- Jede Zeile ist ein Datenbankeintrag, hier z.B. eine berechnete Struktur.
- Jede Spalte ist ein Descriptor, z.B. `Name`, `Formula`, `E`,
  `form_G_per_Area`, `Ga`, `Cu` oder Koordinations-/Ladungsgrößen.
- Pandas-Befehle wie `filter`, `query`, `groupby`, `sort_values` und
  `assign` sind die wichtigsten Werkzeuge.
"""
        ),
        code(
            """
summary = pd.DataFrame({
    "column": df_111.columns,
    "dtype": [str(df_111[c].dtype) for c in df_111.columns],
    "non_null": [int(df_111[c].notna().sum()) for c in df_111.columns],
    "example": [repr(df_111[c].dropna().iloc[0])[:90] if df_111[c].notna().any() else "" for c in df_111.columns],
})
summary
"""
        ),
        md("## Typische OnePiece Studio-Adapteridee"),
        code(
            """
import sys
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from onepiece_studio import DataFrameSource, HDFSource, OnePieceSource

hdf_source = HDFSource(HDF_FILES["surface_111"], key="df", name="CuGa 111")
df_from_onepiece_studio = hdf_source.load()
df_from_onepiece_studio.shape
"""
        ),
        code(
            """
class MinimalOnePieceLike:
    \"\"\"A small stand-in for a OnePiece database object.

    OnePiece Studio accepts real OnePiece objects if they expose .df, .dataframe,
    or to_dataframe().
    \"\"\"
    def __init__(self, df):
        self.df = df

onepiece_like = MinimalOnePieceLike(df_111)
df_from_onepiece_adapter = OnePieceSource(onepiece_like, name="minimal").load()
df_from_onepiece_adapter.head(3)
"""
        ),
        md("## ASE-Strukturspalten erkennen"),
        code(
            """
def looks_like_ase_atoms(value):
    return all(hasattr(value, attr) for attr in ["get_positions", "get_chemical_formula"])

object_columns = df_111.select_dtypes(include="object").columns.tolist()
ase_candidates = []
for column in object_columns:
    sample = df_111[column].dropna()
    if len(sample) and looks_like_ase_atoms(sample.iloc[0]):
        ase_candidates.append(column)

ase_candidates
"""
        ),
        code(
            """
if ase_candidates:
    atoms = df_111[ase_candidates[0]].dropna().iloc[0]
    print(type(atoms))
    print(atoms.get_chemical_formula())
    print("natoms:", len(atoms))
else:
    print("No direct ase.Atoms column detected. Structures may be stored via paths or derived descriptors.")
"""
        ),
        md("## Erste Datenbankfragen mit pandas"),
        code(
            """
cols = [c for c in ["Name", "Formula", "Ga", "Cu", "Monolayer_alloy", "form_G_per_Area", "form_G_per_alloy", "E"] if c in df_111]
df_111[cols].sort_values(cols[-1]).head(10)
"""
        ),
        code(
            """
numeric_cols = df_111.select_dtypes(include=np.number).columns
df_111[numeric_cols].describe().T.sort_values("std", ascending=False).head(15)
"""
        ),
    ]
    return notebook("00 - Von OnePiece HDF zu pandas und ASE", cells)


def make_01():
    cells = [
        md(
            """
Dieses Notebook zeigt die Bulk-Rechnung. Es lädt `CuGabulk_oxide.hdf`, wertet
die energieabhängigen Terme auf einem Raster aus Temperatur `T` und
`log10(pH2O/pH2)` aus und erzeugt eine stabile Bulk-Phasentabelle.
"""
        ),
        code(COMMON_SETUP),
        code(
            """
import sympy as sp
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

bulk = read_onepiece_hdf(HDF_FILES["bulk_oxide"])
print(bulk.shape)
bulk.head()
"""
        ),
        md("## Thermodynamisches Raster"),
        code(
            """
CONSTANTS = {
    "H2_E": -6.737,
    "H2O_E": -12.062,
    "H2_S": 1.5044e-3,
    "H2O_S": 2.2198e-3,
    "kb": 8.617333262145e-5,
}

T_values = np.linspace(300, 1100, 161)
log10_ratio_values = np.linspace(-16, 4, 201)
TT, YY_log10 = np.meshgrid(T_values, log10_ratio_values)
LOGR_NATURAL = np.log(10.0) * YY_log10

muO_grid = (
    CONSTANTS["H2O_E"]
    - CONSTANTS["H2_E"]
    - TT * (CONSTANTS["H2O_S"] - CONSTANTS["H2_S"])
    + CONSTANTS["kb"] * TT * LOGR_NATURAL
)

float(muO_grid.min()), float(muO_grid.max())
"""
        ),
        md("## Energieausdrücke aus der OnePiece-Tabelle evaluieren"),
        code(
            """
candidate_columns = [
    "formation_energy_per_atom",
    "formation_energy",
    "form_E_per_atom",
    "form_G_per_atom",
]
[c for c in candidate_columns if c in bulk.columns]
"""
        ),
        code(
            """
T, kb, pH2O, pH2, H2O_E, H2_E, H2O_S, H2_S = sp.symbols(
    "T kb pH2O pH2 H2O_E H2_E H2O_S H2_S"
)

def expression_to_grid(expr):
    \"\"\"Convert a symbolic/string/numeric energy expression to a 2D grid.\"\"\"
    if pd.isna(expr):
        return np.full_like(TT, np.nan, dtype=float)
    if isinstance(expr, (int, float, np.number)):
        return np.full_like(TT, float(expr), dtype=float)
    sym_expr = sp.sympify(str(expr))
    subs = {
        H2O_E: CONSTANTS["H2O_E"],
        H2_E: CONSTANTS["H2_E"],
        H2O_S: CONSTANTS["H2O_S"],
        H2_S: CONSTANTS["H2_S"],
        kb: CONSTANTS["kb"],
        pH2: 1,
        pH2O: sp.exp(sp.Symbol("logR")),
    }
    logR = sp.Symbol("logR")
    sym_expr = sym_expr.subs(subs)
    func = sp.lambdify((T, logR), sym_expr, "numpy")
    values = func(TT, LOGR_NATURAL)
    return np.asarray(values, dtype=float) + np.zeros_like(TT)

energy_column = next(c for c in candidate_columns if c in bulk.columns)
energy_surfaces = np.stack([expression_to_grid(v) for v in bulk[energy_column]])
stable_index = np.nanargmin(energy_surfaces, axis=0)
stable_energy = np.nanmin(energy_surfaces, axis=0)
energy_surfaces.shape, stable_index.shape
"""
        ),
        md("## Stabile Bulk-Phasen zusammenfassen"),
        code(
            """
def phase_label(row):
    if "Ga_percent" in row and pd.notna(row["Ga_percent"]):
        return f"{row['Ga_percent']:.1f}% Ga"
    counts = formula_counts(row.get("Formula"))
    total = sum(counts.values())
    ga_percent = 100 * counts.get("Ga", 0) / total if total else np.nan
    return f"{ga_percent:.1f}% Ga" if pd.notna(ga_percent) else str(row.get("Name"))

records = []
for phase_id in np.unique(stable_index):
    mask = stable_index == phase_id
    row = bulk.iloc[int(phase_id)]
    counts = formula_counts(row.get("Formula"))
    total = sum(counts.values())
    records.append({
        "phase_id": int(phase_id),
        "Name": row.get("Name", f"phase {phase_id}"),
        "Formula": row.get("Formula", ""),
        "phase_label": phase_label(row),
        "Cu_atoms": counts.get("Cu", np.nan),
        "Ga_atoms": counts.get("Ga", np.nan),
        "Ga_percent": 100 * counts.get("Ga", 0) / total if total else np.nan,
        "stable_grid_fraction": float(mask.mean()),
        "stable_percent": float(100 * mask.mean()),
        "T_min_K": float(TT[mask].min()),
        "T_max_K": float(TT[mask].max()),
        "log10_ratio_min": float(YY_log10[mask].min()),
        "log10_ratio_max": float(YY_log10[mask].max()),
        "min_energy": float(stable_energy[mask].min()),
        "unit": "eV/atom",
        "panel": "Bulk oxide-derived",
    })

bulk_summary = pd.DataFrame(records).sort_values("stable_grid_fraction", ascending=False)
bulk_summary
"""
        ),
        code(
            """
bulk_summary.to_csv(OUTPUT_ROOT / "tutorial_bulk_transition_summary.csv", index=False)
"""
        ),
        md("## Kontrollplot"),
        code(
            """
stable_phase_ids = np.unique(stable_index)
remap = {old: new for new, old in enumerate(stable_phase_ids)}
stable_compact = np.vectorize(remap.get)(stable_index)

fig, ax = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
cmap = plt.get_cmap("tab20", len(stable_phase_ids))
mesh = ax.pcolormesh(TT, YY_log10, stable_compact, cmap=cmap, shading="auto")
ax.set_xlabel("Temperature T [K]")
ax.set_ylabel("log10(pH2O/pH2)")
ax.set_title("Bulk stable phase fields")
cbar = fig.colorbar(mesh, ax=ax, ticks=np.arange(len(stable_phase_ids)) + 0.5)
cbar.ax.set_yticklabels([str(bulk.iloc[i].get("Name", i)) for i in stable_phase_ids])
fig.savefig(OUTPUT_ROOT / "tutorial_bulk_phase_fields.png", dpi=180)
plt.show()
"""
        ),
    ]
    return notebook("01 - Bulk-Phasentabelle aus HDF berechnen", cells)


def make_02():
    cells = [
        md(
            """
Dieses Notebook berechnet die Oberflächen-Phasentabellen für die Miller-Indizes
`100`, `110`, `111` und `211`. Ausgangspunkt sind wieder die HDF-Dateien.

Die Oberfläche wird pro Fläche verglichen. Für jede Temperatur und jedes
`pH2O/pH2` wird die korrigierte freie Energie pro Fläche berechnet; die
Struktur mit dem kleinsten Wert definiert das stabile Feld.
"""
        ),
        code(COMMON_SETUP),
        code(
            """
import matplotlib.pyplot as plt

SURFACE_KEYS = ["surface_100", "surface_110", "surface_111", "surface_211"]
surface_frames = {key: read_onepiece_hdf(HDF_FILES[key]) for key in SURFACE_KEYS}
{key: frame.shape for key, frame in surface_frames.items()}
"""
        ),
        md("## Chemische Potentiale und Korrekturformel"),
        code(
            """
CONSTANTS = {
    "H2_E": -6.737,
    "H2O_E": -12.062,
    "H2_S": 1.5044e-3,
    "H2O_S": 2.2198e-3,
    "kb": 8.617333262145e-5,
}

T_values = np.linspace(300, 1100, 161)
log10_ratio_values = np.linspace(-16, 4, 201)
TT, YY_log10 = np.meshgrid(T_values, log10_ratio_values)
LOGR_NATURAL = np.log(10.0) * YY_log10

muO = (
    CONSTANTS["H2O_E"]
    - CONSTANTS["H2_E"]
    - TT * (CONSTANTS["H2O_S"] - CONSTANTS["H2_S"])
    + CONSTANTS["kb"] * TT * LOGR_NATURAL
)
muGa = -1.5 * muO - 11.275508775
muZn = -3.9596642877 - muO

def first_existing(df, names, default=None):
    for name in names:
        if name in df.columns:
            return name
    return default

def corrected_surface_energy_grid(df):
    base_col = first_existing(df, ["form_G", "form_G_per_Area", "E"])
    area_col = first_existing(df, ["Area"], default=None)
    dga_col = first_existing(df, ["delta_Ga"], default=None)
    dzn_col = first_existing(df, ["delta_Zn", "delta_Cu"], default=None)
    muga_col = first_existing(df, ["mu_Ga"], default=None)
    muzn_col = first_existing(df, ["mu_Zn", "mu_Cu"], default=None)

    grids = []
    for _, row in df.iterrows():
        base = float(row[base_col])
        if base_col.endswith("per_Area"):
            area = 1.0
        else:
            area = float(row[area_col]) if area_col else 1.0
        dga = float(row[dga_col]) if dga_col and pd.notna(row[dga_col]) else 0.0
        dzn = float(row[dzn_col]) if dzn_col and pd.notna(row[dzn_col]) else 0.0
        muga_ref = float(row[muga_col]) if muga_col and pd.notna(row[muga_col]) else 0.0
        muzn_ref = float(row[muzn_col]) if muzn_col and pd.notna(row[muzn_col]) else 0.0
        corrected = base + dga * (muga_ref - muGa) + dzn * (muzn_ref - muZn)
        grids.append(corrected / area)
    return np.stack(grids)
"""
        ),
        md("## Stabile Phasen pro Miller-Index"),
        code(
            """
def surface_summary_for(key, df):
    hkl = key.split("_")[-1]
    energy = corrected_surface_energy_grid(df)
    stable_index = np.nanargmin(energy, axis=0)
    stable_energy = np.nanmin(energy, axis=0)
    records = []
    for phase_id in np.unique(stable_index):
        mask = stable_index == phase_id
        row = df.iloc[int(phase_id)]
        short_label = f"{row.get('Monolayer_alloy', np.nan):.1f}% ML" if pd.notna(row.get("Monolayer_alloy", np.nan)) else str(row.get("Name"))
        records.append({
            "hkl": hkl,
            "phase_id": int(phase_id),
            "Name": row.get("Name", f"phase {phase_id}"),
            "Formula": row.get("Formula", ""),
            "phase_label": f"{short_label} · {row.get('Name', phase_id)}",
            "short_label": short_label,
            "Ga": row.get("Ga", np.nan),
            "Cu": row.get("Cu", np.nan),
            "Monolayer_alloy": row.get("Monolayer_alloy", np.nan),
            "stable_grid_fraction": float(mask.mean()),
            "stable_percent": float(100 * mask.mean()),
            "T_min_stable_K": float(TT[mask].min()),
            "T_max_stable_K": float(TT[mask].max()),
            "log10_ratio_min_stable": float(YY_log10[mask].min()),
            "log10_ratio_max_stable": float(YY_log10[mask].max()),
            "min_G_per_Area_eV_A2": float(stable_energy[mask].min()),
        })
    return pd.DataFrame(records).sort_values("stable_grid_fraction", ascending=False), stable_index

surface_summaries = {}
surface_indices = {}
for key, df in surface_frames.items():
    summary, stable_index = surface_summary_for(key, df)
    surface_summaries[key] = summary
    surface_indices[key] = stable_index
    summary.to_csv(OUTPUT_ROOT / f"tutorial_{key}_stable_phases.csv", index=False)

pd.concat(surface_summaries, names=["dataset"]).reset_index(level=0).head(20)
"""
        ),
        md("## Ein einzelnes Oberflächenpanel ansehen"),
        code(
            """
key = "surface_211"
stable_index = surface_indices[key]
summary = surface_summaries[key]
stable_phase_ids = np.unique(stable_index)
remap = {old: new for new, old in enumerate(stable_phase_ids)}
stable_compact = np.vectorize(remap.get)(stable_index)

fig, ax = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
mesh = ax.pcolormesh(TT, YY_log10, stable_compact, cmap=plt.get_cmap("tab20", len(stable_phase_ids)), shading="auto")
ax.set_title("Surface 211 stable phase fields")
ax.set_xlabel("Temperature T [K]")
ax.set_ylabel("log10(pH2O/pH2)")
cbar = fig.colorbar(mesh, ax=ax, ticks=np.arange(len(stable_phase_ids)) + 0.5)
cbar.ax.set_yticklabels([str(surface_frames[key].iloc[i].get("Name", i)) for i in stable_phase_ids])
fig.savefig(OUTPUT_ROOT / "tutorial_surface_211_phase_fields.png", dpi=180)
plt.show()
summary
"""
        ),
        code(
            """
surface_all = pd.concat(surface_summaries.values(), ignore_index=True)
surface_all.to_csv(OUTPUT_ROOT / "tutorial_surface_all_stable_phases.csv", index=False)
surface_all
"""
        ),
    ]
    return notebook("02 - Oberflächen-Phasentabellen pro Miller-Index", cells)


def make_03():
    cells = [
        md(
            """
Dieses Notebook verbindet Bulk- und Oberflächen-Ergebnisse zu den Tabellen, die
unter dem Multiplot angezeigt werden. Es startet mit den HDF-Dateien, kann aber
auch die in den vorherigen Notebooks gespeicherten Tutorial-CSV-Dateien
verwenden.
"""
        ),
        code(COMMON_SETUP),
        md("## Vorhandene Zwischenergebnisse laden"),
        code(
            """
bulk_summary_path = OUTPUT_ROOT / "tutorial_bulk_transition_summary.csv"
surface_summary_path = OUTPUT_ROOT / "tutorial_surface_all_stable_phases.csv"

if not bulk_summary_path.exists() or not surface_summary_path.exists():
    raise FileNotFoundError(
        "Run notebooks 01 and 02 first, or copy their CSV outputs into phase_diagram_outputs."
    )

bulk_summary = pd.read_csv(bulk_summary_path)
surface_all = pd.read_csv(surface_summary_path)
bulk_summary.head(), surface_all.head()
"""
        ),
        md("## Spalten auf ein gemeinsames Schema bringen"),
        code(
            """
bulk_table = bulk_summary.copy()
bulk_table["surface_or_bulk"] = "bulk"
bulk_table["hkl"] = ""
bulk_table["Monolayer_alloy"] = np.nan
bulk_table["Cu_atoms"] = bulk_table.get("Cu_atoms", np.nan)
bulk_table["Ga_atoms"] = bulk_table.get("Ga_atoms", np.nan)
bulk_table["energy_column"] = "formation_energy_per_atom"

surface_table = surface_all.rename(columns={
    "T_min_stable_K": "T_min_K",
    "T_max_stable_K": "T_max_K",
    "log10_ratio_min_stable": "log10_ratio_min",
    "log10_ratio_max_stable": "log10_ratio_max",
    "min_G_per_Area_eV_A2": "min_energy",
})
surface_table["panel"] = "Surface hkl " + surface_table["hkl"].astype(str)
surface_table["surface_or_bulk"] = np.where(
    surface_table["Name"].str.contains("clean", case=False, na=False),
    "clean surface",
    "Ga-covered surface",
)
surface_table["Ga_percent"] = np.nan
surface_table["Cu_atoms"] = surface_table["Cu"]
surface_table["Ga_atoms"] = surface_table["Ga"]
surface_table["unit"] = "eV/Å²"
surface_table["energy_column"] = "G_per_Area_corrected"

columns = [
    "panel", "surface_or_bulk", "hkl", "phase_id", "Name", "Formula",
    "phase_label", "Ga_percent", "Monolayer_alloy", "Cu_atoms", "Ga_atoms",
    "stable_grid_fraction", "stable_percent", "T_min_K", "T_max_K",
    "log10_ratio_min", "log10_ratio_max", "min_energy", "unit", "energy_column",
]

combined = pd.concat([bulk_table[columns], surface_table[columns]], ignore_index=True)
combined["T_span_K"] = combined["T_max_K"] - combined["T_min_K"]
combined["log10_ratio_span"] = combined["log10_ratio_max"] - combined["log10_ratio_min"]
combined = combined.sort_values(["panel", "stable_grid_fraction"], ascending=[True, False])
combined.insert(0, "rank_in_panel", combined.groupby("panel").cumcount() + 1)
combined.head(12)
"""
        ),
        code(
            """
combined.to_csv(OUTPUT_ROOT / "tutorial_bulk_surface_transition_phase_summary_extended.csv", index=False)
combined
"""
        ),
        md("## Multiplot-Tabelle wie im HTML-Output"),
        code(
            """
for panel, table in combined.groupby("panel"):
    display_cols = [
        "rank_in_panel", "surface_or_bulk", "hkl", "Name", "Formula",
        "phase_label", "Monolayer_alloy", "Cu_atoms", "Ga_atoms",
        "stable_percent", "T_min_K", "T_max_K",
        "log10_ratio_min", "log10_ratio_max", "min_energy", "unit",
    ]
    print("\\n" + panel)
    display(table[display_cols])
"""
        ),
        md(
            """
## Verbindung zum vorhandenen Multiplot

Der vorhandene HTML-Multiplot verwendet dieselbe Idee:

1. Pro Rasterpunkt werden Energien für alle Kandidaten berechnet.
2. `argmin` bestimmt die stabile Phase.
3. Eine Summary-Tabelle zählt, wie oft jede Phase stabil ist.
4. Die Tabellen werden pro Panel gruppiert und als HTML ausgegeben.

Wenn du die bereits erzeugten finalen Dateien erweitern willst, nutze:
`notebooks/build_transition_multiplot_tables.py`.
"""
        ),
        code(
            """
final_existing = OUTPUT_ROOT / "cuga_bulk_surface_transition_phase_summary_extended.csv"
if final_existing.exists():
    final_table = pd.read_csv(final_existing)
    print(final_existing)
    display(final_table.head())
else:
    print("Final extended table not found yet.")
"""
        ),
    ]
    return notebook("03 - Kombinierte Multiplot-Tabellen erzeugen", cells)


def write_all():
    OUT.mkdir(parents=True, exist_ok=True)
    notebooks = {
        "00_hdf_onepiece_pandas_ase_intro.ipynb": make_00(),
        "01_bulk_phase_table_from_hdf.ipynb": make_01(),
        "02_surface_phase_tables_from_hdf.ipynb": make_02(),
        "03_multiplot_transition_tables.ipynb": make_03(),
    }
    for name, nb in notebooks.items():
        path = OUT / name
        nbf.write(nb, path)
        print(path)


if __name__ == "__main__":
    write_all()
