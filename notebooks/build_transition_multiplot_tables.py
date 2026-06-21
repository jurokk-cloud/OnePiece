from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd


OUT = Path(__file__).parent / "phase_diagram_outputs"
SUMMARY = OUT / "cuga_bulk_surface_transition_phase_summary.csv"
SURFACE_ALL = OUT / "cuga_surface_all_stable_phases.csv"
EXTENDED = OUT / "cuga_bulk_surface_transition_phase_summary_extended.csv"
HTML = OUT / "cuga_bulk_surface_transition_phase_multiplot.html"
PNG = "cuga_bulk_surface_transition_phase_multiplot.png"


def _fmt(value: object, digits: int = 4) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        if abs(value) >= 100:
            return f"{value:.1f}"
        if abs(value) >= 10:
            return f"{value:.2f}"
        if abs(value) >= 1:
            return f"{value:.3f}"
        return f"{value:.{digits}g}"
    return str(value)


def _counts_from_formula(formula: object) -> tuple[float | None, float | None]:
    if not isinstance(formula, str):
        return None, None
    counts = {"Cu": 0.0, "Ga": 0.0}
    for element, number in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
        if element in counts:
            counts[element] += float(number or 1)
    return counts["Cu"] or None, counts["Ga"] or None


def _phase_family(row: pd.Series) -> str:
    panel = str(row.get("panel", ""))
    if panel.startswith("Bulk"):
        return "bulk"
    if "clean" in str(row.get("Name", "")).lower():
        return "clean surface"
    return "Ga-covered surface"


def build_extended_summary() -> pd.DataFrame:
    summary = pd.read_csv(SUMMARY)
    surfaces = pd.read_csv(SURFACE_ALL)

    surface_extra = surfaces[
        [
            "hkl",
            "phase_id",
            "Name",
            "short_label",
            "Ga",
            "Cu",
            "Monolayer_alloy",
            "T_min_stable_K",
            "T_max_stable_K",
            "log10_ratio_min_stable",
            "log10_ratio_max_stable",
            "min_G_per_Area_eV_A2",
        ]
    ].copy()
    surface_extra["panel"] = "Surface hkl " + surface_extra["hkl"].astype(str)

    extended = summary.merge(
        surface_extra,
        on=["panel", "phase_id", "Name"],
        how="left",
        suffixes=("", "_surface"),
    )

    counts = extended["Formula"].apply(_counts_from_formula)
    extended["Cu_atoms"] = [cu for cu, _ in counts]
    extended["Ga_atoms"] = [ga for _, ga in counts]
    extended["Cu_atoms"] = extended["Cu"].combine_first(extended["Cu_atoms"])
    extended["Ga_atoms"] = extended["Ga"].combine_first(extended["Ga_atoms"])
    extended["hkl"] = extended["hkl"].fillna("")
    extended["surface_or_bulk"] = extended.apply(_phase_family, axis=1)
    extended["stable_percent"] = 100 * extended["stable_grid_fraction"]
    extended["T_span_K"] = extended["T_max_K"] - extended["T_min_K"]
    extended["log10_ratio_span"] = extended["log10_ratio_max"] - extended["log10_ratio_min"]
    extended["energy_column"] = extended["unit"].map(
        {"eV/atom": "formation_energy_per_atom", "eV/Å²": "G_per_Area_corrected"}
    )

    ordered = [
        "panel",
        "surface_or_bulk",
        "hkl",
        "phase_id",
        "Name",
        "Formula",
        "phase_label",
        "Ga_percent",
        "Monolayer_alloy",
        "Cu_atoms",
        "Ga_atoms",
        "stable_grid_fraction",
        "stable_percent",
        "T_min_K",
        "T_max_K",
        "T_span_K",
        "log10_ratio_min",
        "log10_ratio_max",
        "log10_ratio_span",
        "min_energy",
        "unit",
        "energy_column",
    ]
    extended = extended[ordered].sort_values(
        ["panel", "stable_grid_fraction", "phase_id"], ascending=[True, False, True]
    )
    extended.insert(0, "rank_in_panel", extended.groupby("panel").cumcount() + 1)
    return extended


def table_html(df: pd.DataFrame) -> str:
    columns = [
        ("rank_in_panel", "Rank"),
        ("surface_or_bulk", "Type"),
        ("hkl", "hkl"),
        ("phase_id", "ID"),
        ("Name", "Name"),
        ("Formula", "Formula"),
        ("phase_label", "Phase"),
        ("Ga_percent", "Ga %"),
        ("Monolayer_alloy", "ML %"),
        ("Cu_atoms", "Cu atoms"),
        ("Ga_atoms", "Ga atoms"),
        ("stable_grid_fraction", "Fraction"),
        ("stable_percent", "Stable %"),
        ("T_min_K", "T min [K]"),
        ("T_max_K", "T max [K]"),
        ("T_span_K", "T span [K]"),
        ("log10_ratio_min", "log10 ratio min"),
        ("log10_ratio_max", "log10 ratio max"),
        ("log10_ratio_span", "log10 span"),
        ("min_energy", "Min energy"),
        ("unit", "Unit"),
        ("energy_column", "Energy source"),
    ]
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    rows = []
    for _, row in df.iterrows():
        cells = "".join(
            f"<td>{html.escape(_fmt(row.get(key)))}</td>" for key, _ in columns
        )
        rows.append(f"<tr>{cells}</tr>")
    return f"<div class=\"table-wrap\"><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def build_html(extended: pd.DataFrame) -> str:
    panels = []
    for panel, panel_df in extended.groupby("panel", sort=False):
        panels.append(
            f"<section><h2>{html.escape(panel)}</h2>"
            f"<p class=\"note\">{len(panel_df)} stable transition phases shown with composition, stability window, and energy metadata.</p>"
            f"{table_html(panel_df)}</section>"
        )

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cu/Ga transition phase multiplot</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17212b;
      --muted: #5d6a75;
      --line: #d8e0e7;
      --soft: #f5f7f9;
      --accent: #256b75;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #fbfcfd;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      line-height: 1.45;
    }}
    header, main {{ width: min(1500px, calc(100vw - 48px)); margin: 0 auto; }}
    header {{ padding: 32px 0 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 34px; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 28px 0 6px; font-size: 22px; letter-spacing: 0; }}
    .sub, .note {{ color: var(--muted); margin: 0 0 14px; }}
    a {{ color: var(--accent); font-weight: 650; }}
    .downloads {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 6px 0 20px; }}
    img {{
      display: block;
      width: 100%;
      height: auto;
      border: 1px solid var(--line);
      background: white;
    }}
    .table-wrap {{
      width: 100%;
      overflow-x: auto;
      border: 1px solid var(--line);
      background: white;
    }}
    table {{ min-width: 1850px; width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }}
    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--soft);
      color: #26323d;
      font-weight: 700;
    }}
    tr:nth-child(even) td {{ background: #fafbfc; }}
    td:nth-child(5) {{ white-space: normal; min-width: 230px; }}
    section {{ margin-bottom: 30px; }}
  </style>
</head>
<body>
  <header>
    <h1>Cu/Ga transition-phase multiplot</h1>
    <p class="sub">Bulk and individual surface Miller indices in one view. x = Temperature, y = log10(pH2O/pH2). Colors indicate the stable phase region.</p>
  </header>
  <main>
    <nav class="downloads">
      <a href="cuga_bulk_surface_transition_phase_summary.csv">compact CSV</a>
      <a href="cuga_bulk_surface_transition_phase_summary_extended.csv">extended CSV</a>
      <a href="{PNG}">PNG image</a>
    </nav>
    <img src="{PNG}" alt="Cu/Ga bulk and surface transition phase multiplot">
    {''.join(panels)}
  </main>
</body>
</html>
"""


def main() -> None:
    extended = build_extended_summary()
    extended.to_csv(EXTENDED, index=False)
    HTML.write_text(build_html(extended), encoding="utf-8")
    print(EXTENDED)
    print(HTML)


if __name__ == "__main__":
    main()
