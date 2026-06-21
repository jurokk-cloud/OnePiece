from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FRAME_DIR = Path("/private/tmp/onepiece_studio_ui_test_frames")
OUT_DIR = ROOT / "docs" / "ui_test_artifacts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from examples.chapter6_adsorption_streamlit import load_chapter6  # noqa: E402
from onepiece import add_adsorption_energies, assign_surface_references  # noqa: E402
from onepiece_studio.ui.adsorption import _gas_reference_candidates  # noqa: E402


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _wrapped(draw: ImageDraw.ImageDraw, text: str, width: int, font: ImageFont.ImageFont) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        probe = word if not current else f"{current} {word}"
        if draw.textlength(probe, font=font) <= width:
            current = probe
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _caption_frame(
    image_path: Path,
    *,
    title: str,
    body: str,
    accent: tuple[int, int, int] = (190, 76, 73),
) -> Image.Image:
    base = Image.open(image_path).convert("RGB")
    width, height = base.size
    pad = 36
    caption_h = 190
    canvas = Image.new("RGB", (width, height + caption_h), "white")
    canvas.paste(base, (0, 0))

    draw = ImageDraw.Draw(canvas)
    title_font = _font(34, bold=True)
    body_font = _font(24)

    draw.rectangle([0, height, width, height + caption_h], fill=(248, 246, 243))
    draw.rectangle([0, height, 14, height + caption_h], fill=accent)
    draw.text((pad, height + 24), title, font=title_font, fill=(35, 35, 35))
    y = height + 78
    for line in _wrapped(draw, body, width - 2 * pad, body_font):
        draw.text((pad, y), line, font=body_font, fill=(70, 70, 70))
        y += 32
    return canvas


def _table_frame(table: pd.DataFrame) -> Image.Image:
    width = 1280
    height = 900
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    title_font = _font(40, bold=True)
    body_font = _font(22)
    mono_font = _font(20)
    accent = (190, 76, 73)

    draw.rectangle([0, 0, width, height], fill=(252, 251, 249))
    draw.rectangle([0, 0, 16, height], fill=accent)
    draw.text((42, 34), "Neue Spalten nach dem Adsorptions-Schritt", font=title_font, fill=(35, 35, 35))
    intro = (
        "OnePiece Studio ordnet zuerst die passende saubere Referenzoberflaeche zu. Danach werden "
        "Spalten wie surface_ref_name, delta_E_to_surface_eV und E_ads_CO_eV direkt im "
        "DataFrame verfuergbar."
    )
    y = 96
    for line in _wrapped(draw, intro, width - 84, body_font):
        draw.text((42, y), line, font=body_font, fill=(70, 70, 70))
        y += 30

    text = table.to_string(index=False)
    box_top = y + 18
    draw.rounded_rectangle([42, box_top, width - 42, height - 42], radius=10, fill="white", outline=(220, 216, 210))
    tx = 60
    ty = box_top + 24
    for line in text.splitlines():
        draw.text((tx, ty), line, font=mono_font, fill=(40, 40, 40))
        ty += 24
    return canvas


def _plot_frame(analysis: pd.DataFrame) -> Path:
    subset = analysis.loc[
        analysis["adsorbate"].eq("CO")
        & analysis["E_ads_CO_eV"].notna()
        & analysis["surface_ref_name"].notna()
        & analysis["E"].notna()
    ].copy()
    counts = subset["surface_ref_name"].value_counts()
    keep = set(counts.head(10).index)
    subset["surface_ref_plot"] = subset["surface_ref_name"].where(
        subset["surface_ref_name"].isin(keep),
        "other references",
    )
    subset = subset.sort_values(["surface_ref_plot", "E_ads_CO_eV", "E"])

    fig, ax = plt.subplots(figsize=(13, 8), dpi=140)
    palette = list(plt.cm.tab20.colors) + list(plt.cm.Set3.colors)
    for idx, (label, group) in enumerate(subset.groupby("surface_ref_plot", sort=False)):
        ax.scatter(
            group["E"],
            group["E_ads_CO_eV"],
            s=42,
            alpha=0.82,
            color=palette[idx % len(palette)],
            edgecolors="white",
            linewidths=0.35,
            label=label,
        )

    ax.set_title("CO adsorption energy from OnePiece Studio workflow", fontsize=20, pad=16)
    ax.set_xlabel("DFT total energy E / eV", fontsize=14)
    ax.set_ylabel("Adsorption energy E_ads(CO) / eV", fontsize=14)
    ax.grid(alpha=0.22)
    ax.axhline(0.0, color="#777777", linewidth=1.0, alpha=0.5)
    ax.text(
        0.01,
        0.01,
        "Color = assigned surface reference\nTop 10 references shown separately; rarer references grouped",
        transform=ax.transAxes,
        fontsize=11,
        color="#555555",
        ha="left",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#dddddd", alpha=0.95),
    )
    ax.legend(
        title="surface_ref_name",
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        frameon=False,
        fontsize=10,
        title_fontsize=11,
    )
    fig.tight_layout()
    output = OUT_DIR / "onepiece_studio_adsorption_scatter_surface_reference.png"
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    workflow_frame = FRAME_DIR / "02_workflow_after_add.png"
    adsorption_frame = FRAME_DIR / "08_adsorption.png"
    for path in [workflow_frame, adsorption_frame]:
        if not path.exists():
            raise FileNotFoundError(f"Missing screenshot frame: {path}")

    raw = load_chapter6()
    gas_candidates = _gas_reference_candidates(raw)
    gas_refs = {
        label: float(frame.iloc[0]["E"])
        for label, frame in gas_candidates.items()
        if not frame.empty
    }
    analysis = add_adsorption_energies(assign_surface_references(raw.copy()), gas_refs)

    sample = analysis.loc[
        analysis["adsorbate"].eq("CO")
        & analysis["E_ads_CO_eV"].notna()
        & analysis["surface_ref_name"].notna(),
        ["dataset_label", "Name", "surface_ref_name", "delta_E_to_surface_eV", "E_ads_CO_eV"],
    ].head(8).copy()
    sample["delta_E_to_surface_eV"] = sample["delta_E_to_surface_eV"].map(lambda value: f"{value: .3f}")
    sample["E_ads_CO_eV"] = sample["E_ads_CO_eV"].map(lambda value: f"{value: .3f}")

    plot_path = _plot_frame(analysis)
    frames = [
        _caption_frame(
            workflow_frame,
            title="1. Workflow-Schritt anlegen",
            body=(
                "Im Workflow-Tab waehlt man bei Add derived column den Modus "
                "'Adsorption-energy columns from dataset references'. So werden "
                "Referenzoberflaechen und Adsorptionsspalten reproduzierbar Teil des Datenflusses."
            ),
        ),
        _caption_frame(
            adsorption_frame,
            title="2. Gasreferenzen werden automatisch erkannt",
            body=(
                "OnePiece Studio findet CO, CH3OH und H2 direkt in den geladenen Datensaetzen. "
                "Diese Werte koennen in der UI frei ueberschrieben werden; die Adsorptionsenergie "
                "wird danach sofort neu berechnet."
            ),
        ),
        _table_frame(sample),
        _caption_frame(
            plot_path,
            title="3. Visualisieren und vergleichen",
            body=(
                "Nach dem Rechenschritt kann E_ads(CO) sofort als Scatterplot dargestellt werden. "
                "Hier ist die Farbe die zugewiesene surface reference, damit gleiche Oberflaechen "
                "direkt zusammen gelesen werden koennen."
            ),
        ),
    ]

    gif_path = OUT_DIR / "pfui_adsorption_analysis_demo.gif"
    preview_path = OUT_DIR / "pfui_adsorption_analysis_demo_cover.png"
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=[1700, 1800, 2000, 2200],
        loop=0,
    )
    frames[-1].save(preview_path)
    print(gif_path)
    print(preview_path)


if __name__ == "__main__":
    main()
