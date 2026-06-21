from __future__ import annotations

from pathlib import Path

import nbformat as nbf


NOTEBOOK = Path(__file__).parent / "cuga_muO_temperature_phase_diagram.ipynb"


def md(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


def make_notebook():
    nb = nbf.v4.new_notebook()
    nb["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "pygments_lexer": "ipython3",
        },
    }

    nb.cells = [
        md(
            r"""
# Cu/Ga-Phasendiagramm aus Temperatur und \(p_{\mathrm{H_2O}}/p_{\mathrm{H_2}}\)

Dieses Notebook ist als **Schritt-für-Schritt-Tutorial für Chemie-Masterstudierende**
geschrieben. Es setzt keine tiefe Programmiererfahrung voraus. Wenn du Excel
kennst, kannst du dir `pandas` zunächst wie ein sehr mächtiges Excel in Python
vorstellen.

Wir berechnen ein Phasendiagramm für Cu/Ga-Bulkphasen abhängig von:

- **x-Achse:** Temperatur \(T\) in Kelvin
- **y-Achse:** \(\log_{10}(p_{\mathrm{H_2O}}/p_{\mathrm{H_2}})\)
- **Farbe/Fläche:** Welche Phase bei diesen Bedingungen die niedrigste freie Energie hat

Die wichtigste chemische Idee ist:

> Für jede Phase berechnen wir \(G(T, p_{\mathrm{H_2O}}/p_{\mathrm{H_2}})\).
> Die Phase mit dem kleinsten \(G\) ist unter diesen Bedingungen stabil.

Das ist genau wie bei einer Tabelle in Excel: Für jede Bedingung vergleichen wir
mehrere Zahlen und nehmen das Minimum.
"""
        ),
        md(
            """
## Inhaltsübersicht

1. Python, pandas und das Denken in Tabellen
2. HDF-Datei laden: OnePiece-Daten als `DataFrame`
3. Wichtige pandas-Befehle mit kleinen Beispielen
4. Chemische Gleichung für \(\mu_O\)
5. Temperatur- und Gasdruck-Raster aufbauen
6. Energie jeder Phase auf dem Raster berechnen
7. Stabile Phase als Minimum bestimmen
8. 2D- und 3D-Phasendiagramme plotten
9. Ergebnis-Tabelle erstellen und chemisch interpretieren
10. Kleine Übungsaufgaben
"""
        ),
        md(
            """
## 0. Pakete importieren

In Python lädt man Werkzeuge mit `import`.

- `pandas` ist für Tabellen, ähnlich Excel.
- `numpy` ist für Zahlenfelder und schnelle Rechnungen.
- `sympy` kann Formeln symbolisch lesen und umformen.
- `matplotlib` und `plotly` erzeugen Diagramme.

Die HDF-Dateien wurden in einer bestimmten Python/NumPy-Umgebung geschrieben.
Deshalb gibt es am Anfang einen kleinen Kompatibilitätsblock, damit alte
gespeicherte Objekte gelesen werden können.
"""
        ),
        code(
            """
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
import sympy as sp

import matplotlib.pyplot as plt
import plotly.graph_objects as go

# Compatibility for HDF files written in environments whose pickles reference numpy._core.
# Keep this before pd.read_hdf.
try:
    import tables  # noqa: F401
    import scipy.linalg  # noqa: F401
    import ase.constraints  # noqa: F401
    import numpy.core as numpy_core

    sys.modules.setdefault("numpy._core", numpy_core)
    sys.modules.setdefault("numpy._core.multiarray", np.core.multiarray)
    sys.modules.setdefault("numpy._core.numeric", np.core.numeric)
except Exception as exc:
    print("HDF compatibility imports gave a warning:", exc)

warnings.filterwarnings("ignore", category=FutureWarning)

pd.set_option("display.max_columns", 80)
pd.set_option("display.precision", 4)
"""
        ),
        md(
            """
## 1. Was ist ein pandas DataFrame?

Ein `DataFrame` ist eine Tabelle:

- Spalten sind wie Excel-Spalten: `Name`, `Formula`, `E`, `Ga_percent`, ...
- Zeilen sind einzelne Rechnungen oder Phasen.
- Der Index links ist wie eine Zeilennummer.

Wir starten mit einer kleinen künstlichen Tabelle, bevor wir die echte HDF-Datei laden.
"""
        ),
        code(
            """
mini = pd.DataFrame(
    {
        "Phase": ["Cu", "CuGa", "CuGa2"],
        "Ga_percent": [0.0, 50.0, 66.7],
        "G_eV_per_atom": [0.00, -0.16, -0.38],
    }
)

mini
"""
        ),
        md(
            """
### Excel-Übersetzung

| Excel-Idee | pandas-Befehl |
|---|---|
| erste Zeilen ansehen | `df.head()` |
| Spaltennamen ansehen | `df.columns` |
| nach einer Spalte sortieren | `df.sort_values("Spalte")` |
| Zeilen filtern | `df[df["Spalte"] > Wert]` |
| neue Spalte berechnen | `df["neu"] = ...` oder `df.assign(...)` |
| Mittelwert/Minimum | `df["Spalte"].mean()`, `.min()` |
"""
        ),
        code(
            """
# Die stabilste Phase in dieser kleinen Tabelle ist die mit dem kleinsten G.
mini.sort_values("G_eV_per_atom")
"""
        ),
        code(
            """
# Filter: nur Phasen mit mehr als 10 Prozent Ga.
mini[mini["Ga_percent"] > 10]
"""
        ),
        code(
            """
# Neue Spalte berechnen: absolute Ga-Fraktion von Prozent in 0...1 umrechnen.
mini = mini.assign(Ga_fraction=mini["Ga_percent"] / 100)
mini
"""
        ),
        md(
            """
## 2. Echte OnePiece-HDF-Datei laden

Die OnePiece-Daten liegen als pandas-HDF-Datei vor. Der wichtige Befehl ist:

```python
pd.read_hdf(filename, key="df")
```

Die Datei enthält bereits eine Tabelle mit Phasen, Formeln und
Energieausdrücken. Einige Energieausdrücke sind nicht nur Zahlen, sondern
Formeln mit \(T\), \(p_{\mathrm{H_2O}}\) und \(p_{\mathrm{H_2}}\).
"""
        ),
        code(
            """
import os

DATA_DIR = Path(os.environ.get("ONEPIECE_DATA_ROOT", "data/surface_alloys"))
BULK_OXIDE_HDF = DATA_DIR / "CuGabulk_oxide.hdf"

raw = pd.read_hdf(BULK_OXIDE_HDF, key="df")

print("Datei:", BULK_OXIDE_HDF)
print("Anzahl Zeilen und Spalten:", raw.shape)
raw.head()
"""
        ),
        md(
            """
## 3. Die Tabelle kennenlernen

Bevor man rechnet, sollte man wie in Excel zuerst prüfen:

- Welche Spalten gibt es?
- Welche Spalten enthalten Zahlen?
- Welche Spalten enthalten Text/Formeln?
- Gibt es fehlende Werte?
"""
        ),
        code(
            """
# Alle Spaltennamen als Liste.
raw.columns.tolist()
"""
        ),
        code(
            """
# Datentypen: float = Zahl, object = meistens Text oder komplexes Objekt.
column_overview = pd.DataFrame(
    {
        "column": raw.columns,
        "dtype": [str(raw[c].dtype) for c in raw.columns],
        "non_empty": [int(raw[c].notna().sum()) for c in raw.columns],
        "example": [
            repr(raw[c].dropna().iloc[0])[:90] if raw[c].notna().any() else ""
            for c in raw.columns
        ],
    }
)

column_overview
"""
        ),
        code(
            """
# Wir kopieren die Rohdaten, damit raw unverändert bleibt.
# reset_index sorgt dafür, dass die Zeilen einfach von 0 bis n-1 nummeriert sind.
phase_df = raw.copy().reset_index(drop=True)

# phase_label wird später im Plot angezeigt.
if "legend" in phase_df.columns:
    phase_df["phase_label"] = phase_df["legend"].astype(str)
else:
    phase_df["phase_label"] = phase_df["Name"].astype(str)

important_columns = ["Name", "Formula", "Ga_percent", "phase_label", "formation_energy_per_atom"]
phase_df[important_columns].head(10)
"""
        ),
        md(
            """
### Kleine pandas-Beispiele mit dem echten Datensatz

Diese Zellen sind nicht zwingend für das Phasendiagramm nötig, aber sie zeigen,
wie man chemische Fragen an eine Tabelle stellt.
"""
        ),
        code(
            """
# Frage: Welche Phasen haben besonders viel Gallium?
phase_df[["Name", "Formula", "Ga_percent"]].sort_values("Ga_percent", ascending=False).head(8)
"""
        ),
        code(
            """
# Frage: Welche Phasen liegen zwischen 20 und 70 Prozent Ga?
mask = phase_df["Ga_percent"].between(20, 70)
phase_df.loc[mask, ["Name", "Formula", "Ga_percent"]].head(12)
"""
        ),
        code(
            """
# Frage: Wie viele Phasen gibt es ungefähr pro Ga-Bereich?
# pd.cut macht Klassen, ähnlich wie man in Excel Werte in Kategorien einteilt.
phase_df["Ga_bin"] = pd.cut(
    phase_df["Ga_percent"],
    bins=[0, 10, 25, 50, 75, 100],
    include_lowest=True,
)

phase_df.groupby("Ga_bin", observed=False)["Name"].count().rename("number_of_phases")
"""
        ),
        code(
            """
# Frage: Wie sieht ein Energieausdruck konkret aus?
example_row = phase_df.loc[phase_df["formation_energy_per_atom"].astype(str).str.contains("pH2O", na=False)].iloc[0]

print("Name:", example_row["Name"])
print("Formula:", example_row["Formula"])
print("Energieausdruck:")
print(example_row["formation_energy_per_atom"])
"""
        ),
        md(
            r"""
## 4. Chemischer Hintergrund: Sauerstoff-Chemical-Potential

Wir betrachten ein Gasgleichgewicht mit Wasserstoff und Wasser:

\[
\mathrm{H_2 + O \rightleftharpoons H_2O}
\]

Daraus wird ein effektives Sauerstoff-Chemical-Potential abgeleitet:

\[
\mu_O =
E_{\mathrm{H_2O}} - E_{\mathrm{H_2}}
- T(S_{\mathrm{H_2O}} - S_{\mathrm{H_2}})
+ k_B T \ln\left(\frac{p_{\mathrm{H_2O}}}{p_{\mathrm{H_2}}}\right)
\]

Chemisch gelesen:

- \(E_{\mathrm{H_2O}} - E_{\mathrm{H_2}}\): Energieunterschied der Moleküle
- \(-T\Delta S\): Entropiebeitrag, wichtig bei hohen Temperaturen
- \(k_B T \ln(p_{\mathrm{H_2O}}/p_{\mathrm{H_2}})\): Gasdruck-/Aktivitätsbeitrag

Wir verwenden später \(\log_{10}(p_{\mathrm{H_2O}}/p_{\mathrm{H_2}})\), weil
Druckverhältnisse oft über viele Größenordnungen variieren.
"""
        ),
        code(
            """
CONSTANTS = {
    "H2_E": -6.737,
    "H2O_E": -12.062,
    "H2_S": 1.5044e-3,
    "H2O_S": 2.2198e-3,
    "kb": 8.617333262145e-5,  # eV/K
}

pd.Series(CONSTANTS, name="value")
"""
        ),
        code(
            """
# SymPy-Symbole sind Platzhalter in einer Formel.
T, pH2O, pH2, kb = sp.symbols("T pH2O pH2 kb")
H2O_E, H2_E, H2O_S, H2_S = sp.symbols("H2O_E H2_E H2O_S H2_S")
logR = sp.symbols("logR")  # natural logarithm of pH2O/pH2

muO_expr = H2O_E - H2_E - T * (H2O_S - H2_S) + kb * T * sp.log(pH2O / pH2)
muO_expr
"""
        ),
        md(
            """
### Ein einzelnes Zahlenbeispiel

Bevor wir ein ganzes Raster berechnen, rechnen wir einen einzelnen Punkt aus:

- \(T = 800\) K
- \(p_{H2O}/p_{H2} = 10^{-6}\)

Das entspricht einem sehr kleinen Wasser/Wasserstoff-Verhältnis.
"""
        ),
        code(
            """
def muO_numeric(T_K, log10_ratio):
    # Calculate muO for one temperature and one log10 pressure ratio.
    ln_ratio = np.log(10.0) * log10_ratio
    return (
        CONSTANTS["H2O_E"]
        - CONSTANTS["H2_E"]
        - T_K * (CONSTANTS["H2O_S"] - CONSTANTS["H2_S"])
        + CONSTANTS["kb"] * T_K * ln_ratio
    )

muO_numeric(T_K=800, log10_ratio=-6)
"""
        ),
        code(
            """
# Wie verändert sich muO mit dem Gasverhältnis bei 800 K?
single_T_table = pd.DataFrame(
    {
        "log10_ratio": [-12, -9, -6, -3, 0],
    }
)
single_T_table["pH2O_over_pH2"] = 10.0 ** single_T_table["log10_ratio"]
single_T_table["muO_eV"] = single_T_table["log10_ratio"].map(lambda r: muO_numeric(800, r))
single_T_table
"""
        ),
        md(
            """
## 5. Symbolische Energieausdrücke lesbar machen

Die HDF-Datei enthält Energieausdrücke als Text oder SymPy-Objekte. Wir brauchen
eine Funktion, die daraus eine numerische Funktion macht:

```text
Energieausdruck aus Tabelle  ->  Funktion G(T, logR)
```

Dabei setzen wir \(p_{H2}=1\) und \(p_{H2O}=\exp(\log R)\). Dann ist
\(\log R = \ln(p_{H2O}/p_{H2})\).
"""
        ),
        code(
            """
LOCAL_DICT = {
    "T": T,
    "pH2O": pH2O,
    "pH2": pH2,
    "kb": kb,
    "H2O_E": H2O_E,
    "H2_E": H2_E,
    "H2O_S": H2O_S,
    "H2_S": H2_S,
    "log": sp.log,
    "ln": sp.log,
}

CONSTANT_SYMBOLS = {
    H2_E: CONSTANTS["H2_E"],
    H2O_E: CONSTANTS["H2O_E"],
    H2_S: CONSTANTS["H2_S"],
    H2O_S: CONSTANTS["H2O_S"],
    kb: CONSTANTS["kb"],
}


def to_sympy_expr(value):
    # Convert numeric/string/sympy HDF values into a SymPy expression.
    if isinstance(value, sp.Basic):
        return value
    if pd.isna(value):
        return sp.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return sp.Float(value)
    return sp.sympify(str(value), locals=LOCAL_DICT)


def expr_to_numeric_function(expr):
    # Return a function f(T_grid, natural_log_ratio_grid).
    expr = to_sympy_expr(expr)
    expr = expr.subs({pH2: 1, pH2O: sp.exp(logR)})
    expr = sp.simplify(expr.subs(CONSTANT_SYMBOLS))
    func = sp.lambdify((T, logR), expr, modules="numpy")
    return expr, func
"""
        ),
        code(
            """
ENERGY_COLUMN = "formation_energy_per_atom"

phase_df["G_expr"] = phase_df[ENERGY_COLUMN].map(to_sympy_expr)
phase_df["G_expr_substituted"] = [
    expr_to_numeric_function(value)[0]
    for value in phase_df[ENERGY_COLUMN]
]

phase_df[["Name", "Formula", "Ga_percent", "G_expr_substituted"]].head(8)
"""
        ),
        md(
            """
### Test an einer einzigen Phase

Wir nehmen eine Phase, wandeln ihren Energieausdruck in eine Funktion um und
berechnen \(G\) bei einer konkreten Bedingung. Das ist der wichtigste
Kontrollschritt.
"""
        ),
        code(
            """
row_id = 0
phase_name = phase_df.loc[row_id, "Name"]
expr, func = expr_to_numeric_function(phase_df.loc[row_id, ENERGY_COLUMN])

T_test = 800.0
log10_ratio_test = -6.0
ln_ratio_test = np.log(10.0) * log10_ratio_test

G_test = func(T_test, ln_ratio_test)

print("Phase:", phase_name)
print("G bei T=800 K und log10 ratio=-6:", float(G_test), "eV/atom")
"""
        ),
        md(
            """
## 6. Ein Raster wie ein Excel-Arbeitsblatt bauen

Wir wollen nicht nur einen Punkt berechnen, sondern viele Punkte:

- Temperaturen von 300 bis 1100 K
- \(\log_{10}(p_{H2O}/p_{H2})\) von -16 bis 4

In Excel könnte man Temperaturen in die Spalten schreiben und Gasverhältnisse in
die Zeilen. Genau das macht `np.meshgrid`.
"""
        ),
        code(
            """
T_min, T_max, n_T = 300.0, 1100.0, 161
log10_min, log10_max, n_R = -16.0, 4.0, 201

T_values = np.linspace(T_min, T_max, n_T)
log10_ratio_values = np.linspace(log10_min, log10_max, n_R)

TT, YY_log10 = np.meshgrid(T_values, log10_ratio_values)
LOGR_NATURAL = np.log(10.0) * YY_log10

print("Temperaturwerte:", T_values[:5], "...", T_values[-5:])
print("log10-ratio Werte:", log10_ratio_values[:5], "...", log10_ratio_values[-5:])
print("Rasterform:", TT.shape)
"""
        ),
        code(
            """
# Kleine Vorschau wie in Excel: Zeilen = Gasverhältnis, Spalten = Temperatur.
preview = pd.DataFrame(
    TT[:5, :5],
    index=[f"log10R={r:.1f}" for r in log10_ratio_values[:5]],
    columns=[f"T={t:.0f} K" for t in T_values[:5]],
)
preview
"""
        ),
        code(
            """
# muO für das gesamte Raster berechnen.
muO_grid = muO_numeric(TT, YY_log10)

print("kleinstes muO:", float(np.nanmin(muO_grid)))
print("größtes muO:", float(np.nanmax(muO_grid)))
"""
        ),
        md(
            """
## 7. Energiefläche für jede Phase berechnen

Jetzt passiert die eigentliche Arbeit:

1. Gehe durch jede Phase in der Tabelle.
2. Lies ihren Energieausdruck.
3. Berechne \(G\) für alle Rasterpunkte.
4. Speichere die ganze Fläche.

Das Ergebnis ist ein 3D-Zahlenblock:

```text
Achse 0: Phase
Achse 1: log10(pH2O/pH2)
Achse 2: Temperatur
```
"""
        ),
        code(
            """
energy_surfaces = []
valid_rows = []
skipped_rows = []

for row_index, row in phase_df.iterrows():
    expr, func = expr_to_numeric_function(row[ENERGY_COLUMN])
    try:
        Z = np.asarray(func(TT, LOGR_NATURAL), dtype=float)

        # Manche Ausdrücke sind konstante Zahlen. Dann macht SymPy nur eine Zahl,
        # aber wir brauchen eine komplette Fläche mit derselben Form wie TT.
        if Z.shape == ():
            Z = np.full_like(TT, float(Z))

        if not np.all(np.isnan(Z)):
            energy_surfaces.append(Z)
            valid_rows.append(row_index)
    except Exception as exc:
        skipped_rows.append((row_index, row.get("Name", ""), str(exc)))

energy_surfaces = np.stack(energy_surfaces, axis=0)
phases = phase_df.loc[valid_rows].reset_index(drop=True)

print("gültige Phasen:", len(phases))
print("übersprungene Phasen:", len(skipped_rows))
print("Form des Energieblocks:", energy_surfaces.shape)
"""
        ),
        code(
            """
# Eine chemische Plausibilitätsprüfung:
# Für jede Phase betrachten wir das kleinste G im berechneten Fenster.
phase_energy_overview = phases[["Name", "Formula", "Ga_percent", "phase_label"]].copy()
phase_energy_overview["min_G_in_window"] = np.nanmin(energy_surfaces, axis=(1, 2))
phase_energy_overview["max_G_in_window"] = np.nanmax(energy_surfaces, axis=(1, 2))

phase_energy_overview.sort_values("min_G_in_window").head(12)
"""
        ),
        md(
            """
## 8. Stabile Phase finden: Minimum über alle Phasen

Für jeden Rasterpunkt vergleichen wir alle Phasen und suchen die kleinste
Energie.

In Excel wäre das ähnlich wie:

```text
=MIN(B2:Z2)
```

Nur machen wir es hier für sehr viele Bedingungen gleichzeitig.
"""
        ),
        code(
            """
stable_index = np.nanargmin(energy_surfaces, axis=0)
stable_energy = np.nanmin(energy_surfaces, axis=0)

stable_phase_ids = np.unique(stable_index)
stable_names = phases.loc[stable_phase_ids, "phase_label"].astype(str).tolist()

print("Anzahl stabiler Phasen im betrachteten Fenster:", len(stable_phase_ids))
stable_names
"""
        ),
        md(
            """
### Einen einzelnen Punkt interpretieren

Wir wählen einen konkreten Punkt und lassen uns die besten Phasen anzeigen.
Das ist sehr hilfreich, um das Phasendiagramm nicht als Black Box zu behandeln.
"""
        ),
        code(
            """
def nearest_index(values, target):
    return int(np.abs(values - target).argmin())


T_query = 800.0
log10_query = -6.0

i_T = nearest_index(T_values, T_query)
i_R = nearest_index(log10_ratio_values, log10_query)

energies_at_point = pd.DataFrame(
    {
        "Name": phases["Name"],
        "Formula": phases["Formula"],
        "Ga_percent": phases["Ga_percent"],
        "G_eV_per_atom": energy_surfaces[:, i_R, i_T],
    }
).sort_values("G_eV_per_atom")

print("Bedingung:")
print("T =", T_values[i_T], "K")
print("log10(pH2O/pH2) =", log10_ratio_values[i_R])
energies_at_point.head(10)
"""
        ),
        code(
            """
# Energieabstand zwischen stabilster und zweitstabilster Phase.
winner = energies_at_point.iloc[0]
runner_up = energies_at_point.iloc[1]

delta_G = runner_up["G_eV_per_atom"] - winner["G_eV_per_atom"]

print("Stabilste Phase:", winner["Name"])
print("Zweitbeste Phase:", runner_up["Name"])
print("Abstand:", delta_G, "eV/atom")
"""
        ),
        md(
            """
## 9. 2D-Phasendiagramm

Der 2D-Plot zeigt, welche Phase an welcher Stelle stabil ist.

Wichtig:

- Jede Farbe ist eine Phase.
- Eine Grenze zwischen Farben bedeutet: zwei Phasen haben dort gleiche oder sehr ähnliche Energie.
- Die y-Achse ist logarithmisch: -6 bedeutet \(10^{-6}\), nicht -6 bar.
"""
        ),
        code(
            """
stable_phase_ids = np.unique(stable_index)
stable_names = phases.loc[stable_phase_ids, "phase_label"].astype(str).tolist()

remap = {old: new for new, old in enumerate(stable_phase_ids)}
stable_compact = np.vectorize(remap.get)(stable_index)

fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)
cmap = plt.get_cmap("tab20", len(stable_phase_ids))
mesh = ax.pcolormesh(TT, YY_log10, stable_compact, cmap=cmap, shading="auto")

cbar = fig.colorbar(mesh, ax=ax, ticks=np.arange(len(stable_phase_ids)) + 0.5)
cbar.ax.set_yticklabels(stable_names)
cbar.set_label("stabile Phase")

ax.set_xlabel("Temperatur T [K]")
ax.set_ylabel(r"$\\log_{10}(p_{H_2O}/p_{H_2})$")
ax.set_title(f"Cu/Ga Phasendiagramm aus {ENERGY_COLUMN}")

OUTPUT_DIR = Path("phase_diagram_outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
fig.savefig(OUTPUT_DIR / "cuga_phase_diagram_2d_teaching.png", dpi=200)
plt.show()
"""
        ),
        md(
            """
## 10. 3D-Plot der stabilen Energieflächen

Der 3D-Plot zeigt die Energieflächen, aber nur dort, wo die jeweilige Phase
wirklich stabil ist. Das ist leichter zu lesen als alle Flächen gleichzeitig.

Wenn dieser Plot in JupyterLab groß wirkt: Rechtsklick oder Browser-Zoom hilft.
"""
        ),
        code(
            """
fig3d = go.Figure()

for old_id in stable_phase_ids:
    label = str(phases.loc[old_id, "phase_label"])
    name = str(phases.loc[old_id, "Name"])
    Z = energy_surfaces[old_id]
    visible_surface = np.where(stable_index == old_id, Z, np.nan)

    fig3d.add_trace(
        go.Surface(
            x=TT,
            y=YY_log10,
            z=visible_surface,
            name=label,
            showscale=False,
            opacity=0.92,
            hovertemplate=(
                f"Phase: {label}<br>Name: {name}<br>"
                "T: %{x:.1f} K<br>"
                "log10(pH2O/pH2): %{y:.2f}<br>"
                "G: %{z:.4f} eV/atom<extra></extra>"
            ),
        )
    )

fig3d.update_layout(
    title="Stabile freie Energieflächen",
    font=dict(family="system-ui, sans-serif"),
    scene=dict(
        xaxis_title="Temperatur T [K]",
        yaxis_title="log10(pH2O/pH2)",
        zaxis_title="G [eV/atom]",
        camera=dict(eye=dict(x=1.55, y=-1.9, z=1.25)),
    ),
    width=1050,
    height=760,
    margin=dict(l=0, r=0, t=60, b=0),
)

fig3d.write_html(OUTPUT_DIR / "cuga_phase_diagram_3d_teaching.html")
fig3d.show()
"""
        ),
        md(
            """
## 11. Tabelle der stabilen Phasen

Ein Plot ist gut für den Überblick. Für wissenschaftliche Arbeit brauchen wir
aber zusätzlich eine Tabelle:

- Welche Phasen werden überhaupt stabil?
- In welchem Temperaturbereich?
- In welchem Gasverhältnisbereich?
- Wie groß ist der stabile Bereich?
"""
        ),
        code(
            """
stable_summary = []

for old_id in stable_phase_ids:
    mask = stable_index == old_id
    stable_summary.append(
        {
            "phase_id": int(old_id),
            "Name": phases.loc[old_id, "Name"],
            "Formula": phases.loc[old_id, "Formula"],
            "Ga_percent": phases.loc[old_id, "Ga_percent"],
            "phase_label": phases.loc[old_id, "phase_label"],
            "stable_grid_fraction": float(mask.mean()),
            "stable_percent": float(mask.mean() * 100),
            "T_min_stable_K": float(TT[mask].min()),
            "T_max_stable_K": float(TT[mask].max()),
            "log10_ratio_min_stable": float(YY_log10[mask].min()),
            "log10_ratio_max_stable": float(YY_log10[mask].max()),
            "min_G_eV_per_atom": float(energy_surfaces[old_id][mask].min()),
        }
    )

stable_summary = (
    pd.DataFrame(stable_summary)
    .sort_values("stable_grid_fraction", ascending=False)
    .reset_index(drop=True)
)

stable_summary
"""
        ),
        code(
            """
stable_summary.to_csv(OUTPUT_DIR / "cuga_stable_bulk_phases_teaching.csv", index=False)
OUTPUT_DIR / "cuga_stable_bulk_phases_teaching.csv"
"""
        ),
        md(
            """
### Tabelle chemisch lesen

`stable_grid_fraction` ist kein thermodynamischer Anteil. Es bedeutet nur:

> In welchem Anteil unseres gewählten Rechenfensters ist diese Phase die niedrigste?

Wenn eine Phase einen großen Wert hat, dominiert sie viel Fläche im betrachteten
\(T\)-/\(p\)-Fenster. Wenn sie einen sehr kleinen Wert hat, ist sie nur in einem
schmalen Bereich stabil.
"""
        ),
        code(
            """
# Beispiel: nur die drei größten Stabilitätsbereiche.
stable_summary.head(3)[
    [
        "Name",
        "Formula",
        "Ga_percent",
        "stable_percent",
        "T_min_stable_K",
        "T_max_stable_K",
        "log10_ratio_min_stable",
        "log10_ratio_max_stable",
    ]
]
"""
        ),
        md(
            """
## 12. Vergleich: Was passiert bei einer anderen Temperatur?

Jetzt verwenden wir pandas, um Fragen zu beantworten, wie man sie in der Chemie
stellen würde:

> Welche Phase ist bei festem \(T\) am stabilsten, wenn das Gasverhältnis variiert?
"""
        ),
        code(
            """
def stable_along_ratio_at_temperature(T_query):
    i_T = nearest_index(T_values, T_query)
    rows = []
    for i_R, ratio in enumerate(log10_ratio_values):
        phase_id = stable_index[i_R, i_T]
        rows.append(
            {
                "T_K": T_values[i_T],
                "log10_ratio": ratio,
                "stable_phase": phases.loc[phase_id, "Name"],
                "Formula": phases.loc[phase_id, "Formula"],
                "Ga_percent": phases.loc[phase_id, "Ga_percent"],
                "G_eV_per_atom": stable_energy[i_R, i_T],
            }
        )
    return pd.DataFrame(rows)


stable_800K = stable_along_ratio_at_temperature(800)
stable_800K.head()
"""
        ),
        code(
            """
# Wann ändert sich bei 800 K die stabile Phase?
stable_800K["previous_phase"] = stable_800K["stable_phase"].shift()
transition_rows = stable_800K[stable_800K["stable_phase"] != stable_800K["previous_phase"]]
transition_rows[["T_K", "log10_ratio", "stable_phase", "Formula", "Ga_percent"]]
"""
        ),
        md(
            """
## 13. Typische Fehlerquellen

1. **Logarithmen verwechseln:**  
   Die Achse ist \(\log_{10}\), die Thermodynamikformel nutzt aber \(\ln\).
   Deshalb rechnen wir mit `np.log(10) * log10_ratio`.

2. **Stabilitätsbereich überinterpretieren:**  
   `stable_percent` hängt vom gewählten Fenster ab. Wenn du \(T\)- oder
   Druckbereiche änderst, ändert sich auch dieser Wert.

3. **Einheiten vermischen:**  
   Hier ist die Energie `eV/atom`. Oberflächenrechnungen verwenden oft
   `eV/Å²`. Diese Größen darf man nicht direkt vergleichen.

4. **Alle Rechnungen blind verwenden:**  
   In echten Workflows sollte man schlechte oder falsche Rechnungen vorher
   ausschließen, z.B. über `fmax`, falsche Struktur oder falsche Referenz.
"""
        ),
        md(
            """
## 14. Übungen

Diese Aufgaben sind bewusst pandas-orientiert:

1. Ändere `T_query = 600.0` und schaue, welche Phasenübergänge bei 600 K auftreten.
2. Filtere `phase_df` auf Phasen mit `Ga_percent > 50`.
3. Sortiere `stable_summary` nach `T_min_stable_K`.
4. Ändere den Bereich der y-Achse von `-16...4` auf `-10...2` und berechne das Notebook neu.
5. Suche eine Phase im Plot und finde die zugehörige Originalzeile in `phase_df`.

Bonus:

Erstelle eine Tabelle, die für `T = 500`, `800` und `1000` K jeweils die
Phasenübergänge entlang der y-Achse zeigt.
"""
        ),
        md(
            """
## 15. Merksatz

Das ganze Notebook lässt sich chemisch auf einen Satz reduzieren:

> Wir berechnen für jede Phase eine freie Energie als Funktion der Umweltbedingungen
> und wählen an jedem Punkt die Phase mit der niedrigsten Energie.

pandas hilft uns dabei, die chemischen Daten sauber als Tabelle zu organisieren.
NumPy berechnet viele Bedingungen gleichzeitig. SymPy übersetzt Formeln aus der
HDF-Datei in berechenbare Funktionen. Die Plots zeigen danach nur das Ergebnis
dieses Minimum-Vergleichs.
"""
        ),
    ]
    return nb


if __name__ == "__main__":
    nbf.write(make_notebook(), NOTEBOOK)
    print(NOTEBOOK)
