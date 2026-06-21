from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib-onepiece-studio")

try:
    import numpy.core as numpy_core

    sys.modules.setdefault("numpy._core", numpy_core)
    sys.modules.setdefault("numpy._core.multiarray", np.core.multiarray)
    sys.modules.setdefault("numpy._core.numeric", np.core.numeric)
except Exception:
    pass


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]
OUTPUT_ROOT = ROOT / "outputs"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

DATA_ROOT = Path(os.environ.get("ONEPIECE_DATA_ROOT", "data/chapter6"))
HDF_FILES = {
    "CaO-slabs": DATA_ROOT / "CaO-slabs.hdf",
    "Ga2O3-slabs": DATA_ROOT / "Ga2O3-slabs.hdf",
    "Ni-slabs": DATA_ROOT / "Ni-slabs.hdf",
    "Ni3Ga": DATA_ROOT / "Ni3Ga.hdf",
    "Ni5Ga3-slabs": DATA_ROOT / "Ni5Ga3-slabs.hdf",
    "NiO-slabs": DATA_ROOT / "NiO-slabs.hdf",
}


def load_adsorption_module():
    """Import onepiece.adsorption, falling back to direct file import for old kernels."""
    src_root = PROJECT_ROOT / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    try:
        from onepiece import adsorption as ads

        return ads
    except Exception:
        module_path = src_root / "onepiece" / "adsorption.py"
        spec = importlib.util.spec_from_file_location("onepiece_adsorption_direct", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot import adsorption module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


ads = load_adsorption_module()


TOKENS = {
    "surface": "#FCFCFD",
    "panel": "#FFFFFF",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "axis": "#D7DBE7",
    "blue": "#5477C4",
    "blue_light": "#CEDFFE",
    "gold": "#B8A037",
    "orange": "#CC6F47",
    "olive": "#71B436",
    "pink": "#BD569B",
    "neutral": "#C5CAD3",
}


def build_tables(gas_references_ev: dict[str, float] | None = None):
    combined, references = ads.assign_references_before_merge(HDF_FILES)
    results = ads.add_adsorption_energies(combined, gas_references_ev)
    adsorption = ads.adsorption_view(results)
    copt_points = ads.copt_profile_points(results)
    barriers = ads.copt_barrier_summary(results)
    return results, references, adsorption, copt_points, barriers


def save_tables(results, references, adsorption, copt_points, barriers) -> dict[str, Path]:
    paths = {
        "combined": OUTPUT_ROOT / "chapter6_adsorption_barrier_dataset.pkl",
        "references": OUTPUT_ROOT / "surface_references.csv",
        "adsorption": OUTPUT_ROOT / "adsorption_energy_view.csv",
        "copt_points": OUTPUT_ROOT / "copt_barrier_points.csv",
        "barriers": OUTPUT_ROOT / "copt_barrier_summary.csv",
    }
    results.to_pickle(paths["combined"])
    references.to_csv(paths["references"], index=False)
    adsorption.to_csv(paths["adsorption"], index=False)
    copt_points.to_csv(paths["copt_points"], index=False)
    barriers.to_csv(paths["barriers"], index=False)
    return paths


def add_header(fig, title: str, subtitle: str) -> None:
    fig.text(0.08, 0.965, title, ha="left", va="top", fontsize=15, weight="bold", color=TOKENS["ink"])
    fig.text(0.08, 0.925, subtitle, ha="left", va="top", fontsize=10, color=TOKENS["muted"])


def style_axis(ax) -> None:
    ax.set_facecolor(TOKENS["panel"])
    ax.grid(axis="y", color=TOKENS["grid"], linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(TOKENS["axis"])
    ax.spines["bottom"].set_color(TOKENS["axis"])
    ax.tick_params(colors=TOKENS["muted"], labelsize=9)
    ax.yaxis.label.set_color(TOKENS["ink"])
    ax.xaxis.label.set_color(TOKENS["ink"])


def plot_reference_status(adsorption: pd.DataFrame) -> Path:
    import matplotlib.pyplot as plt

    counts = (
        adsorption.groupby(["dataset_label", "surface_ref_status"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )
    statuses = [status for status in ["ok", "missing", "ambiguous", "self"] if status in counts]
    colors = {
        "ok": TOKENS["blue"],
        "missing": TOKENS["orange"],
        "ambiguous": TOKENS["gold"],
        "self": TOKENS["neutral"],
    }

    fig, ax = plt.subplots(figsize=(10.5, 6), facecolor=TOKENS["surface"])
    bottom = np.zeros(len(counts))
    x = np.arange(len(counts))
    for status in statuses:
        values = counts[status].to_numpy()
        ax.bar(x, values, bottom=bottom, color=colors[status], edgecolor=TOKENS["ink"], linewidth=0.5, label=status)
        bottom += values
    ax.set_xticks(x)
    ax.set_xticklabels(counts.index, rotation=30, ha="right")
    ax.set_ylabel("Adsorption rows")
    ax.legend(ncol=len(statuses), frameon=False, loc="upper left", bbox_to_anchor=(0.0, 1.02))
    style_axis(ax)
    add_header(
        fig,
        "Reference assignment quality by HDF source",
        "Stacked counts of adsorbed rows after clean surfaces are assigned before merging.",
    )
    fig.subplots_adjust(top=0.82, left=0.08, right=0.98, bottom=0.2)
    path = OUTPUT_ROOT / "plot_reference_status.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def plot_adsorption_delta_distribution(adsorption: pd.DataFrame) -> Path:
    import matplotlib.pyplot as plt

    plot_data = adsorption.loc[
        adsorption["surface_ref_status"].eq("ok")
        & adsorption["adsorbate"].isin(["CO", "CH3O"])
        & adsorption["delta_E_to_surface_eV"].notna()
        & adsorption["delta_E_to_surface_eV"].between(-80, 25)
    ].copy()
    grouped = list(plot_data.groupby(["dataset_label", "adsorbate"], sort=True))
    labels = [f"{dataset}\n{adsorbate}" for (dataset, adsorbate), _ in grouped]
    values = [group["delta_E_to_surface_eV"].to_numpy() for _, group in grouped]
    colors = [TOKENS["blue_light"] if "CO" in label and "CH3O" not in label else "#FCDAD6" for label in labels]

    fig, ax = plt.subplots(figsize=(12.5, 6.3), facecolor=TOKENS["surface"])
    box = ax.boxplot(values, patch_artist=True, showfliers=False, labels=labels)
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_edgecolor(TOKENS["ink"])
        patch.set_linewidth(0.8)
    for median in box["medians"]:
        median.set_color(TOKENS["ink"])
        median.set_linewidth(1.2)
    ax.axhline(0, color=TOKENS["ink"], linewidth=0.9, linestyle=":")
    ax.set_ylabel("Delta E to clean surface / eV")
    style_axis(ax)
    add_header(
        fig,
        "CO and CH3O energy differences after surface matching",
        "Delta E is a reference-check quantity; final adsorption energies need gas-phase references.",
    )
    fig.subplots_adjust(top=0.82, left=0.08, right=0.98, bottom=0.24)
    path = OUTPUT_ROOT / "plot_adsorption_delta_distribution.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def plot_best_adsorption_candidates(adsorption: pd.DataFrame) -> Path:
    import matplotlib.pyplot as plt

    plot_data = adsorption.loc[
        adsorption["surface_ref_status"].eq("ok")
        & adsorption["adsorbate"].isin(["CO", "CH3O"])
        & adsorption["delta_E_to_surface_eV"].notna()
        & adsorption["delta_E_to_surface_eV"].between(-80, 25)
    ].copy()
    best = (
        plot_data.sort_values("delta_E_to_surface_eV")
        .groupby(["dataset_label", "adsorbate"])
        .head(3)
        .copy()
    )
    best["label"] = best["dataset_label"] + " | " + best["adsorbate"] + " | " + best["Name"].str.slice(0, 42)
    best = best.sort_values("delta_E_to_surface_eV").head(18).sort_values("delta_E_to_surface_eV", ascending=True)

    fig, ax = plt.subplots(figsize=(11.5, 8), facecolor=TOKENS["surface"])
    y = np.arange(len(best))
    bar_colors = np.where(best["adsorbate"].eq("CO"), TOKENS["blue"], TOKENS["pink"])
    ax.barh(y, best["delta_E_to_surface_eV"], color=bar_colors, edgecolor=TOKENS["ink"], linewidth=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(best["label"])
    ax.set_xlabel("Delta E to clean surface / eV")
    ax.axvline(0, color=TOKENS["ink"], linewidth=0.9)
    style_axis(ax)
    add_header(
        fig,
        "Most exothermic CO and CH3O rows by source",
        "Top candidates by Delta E after filtering to rows with assigned references and plausible ranges.",
    )
    fig.subplots_adjust(top=0.84, left=0.42, right=0.98, bottom=0.1)
    path = OUTPUT_ROOT / "plot_best_adsorption_candidates.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def plot_barrier_ranking(barriers: pd.DataFrame) -> Path:
    import matplotlib.pyplot as plt

    plot_data = barriers.loc[barriers["n_points"] >= 3].copy()
    plot_data = plot_data.sort_values("forward_barrier_eV", ascending=False).head(16)
    plot_data = plot_data.sort_values("forward_barrier_eV")
    plot_data["label"] = plot_data["copt_reaction"] + " | path " + plot_data["copt_path_id"].astype(str)

    fig, ax = plt.subplots(figsize=(10.5, 7), facecolor=TOKENS["surface"])
    y = np.arange(len(plot_data))
    ax.barh(y, plot_data["forward_barrier_eV"], color=TOKENS["gold"], edgecolor=TOKENS["ink"], linewidth=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(plot_data["label"])
    ax.set_xlabel("Apparent forward barrier / eV")
    style_axis(ax)
    add_header(
        fig,
        "Constrained-optimization barrier ranking",
        "Barrier is max(E along copt path) minus initial E; use as a scan diagnostic, not a NEB replacement.",
    )
    fig.subplots_adjust(top=0.84, left=0.31, right=0.98, bottom=0.11)
    path = OUTPUT_ROOT / "plot_barrier_ranking.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def plot_copt_profiles(copt_points: pd.DataFrame, barriers: pd.DataFrame) -> Path:
    import matplotlib.pyplot as plt

    keep = barriers.sort_values("forward_barrier_eV", ascending=False).head(8)["copt_series_id"]
    plot_data = copt_points.loc[copt_points["copt_series_id"].isin(keep)].copy()
    order = barriers.set_index("copt_series_id").loc[keep]

    fig, axes = plt.subplots(4, 2, figsize=(12, 10), facecolor=TOKENS["surface"], sharex=False)
    axes = axes.ravel()
    for ax, (series_id, meta) in zip(axes, order.iterrows()):
        group = plot_data.loc[plot_data["copt_series_id"].eq(series_id)].sort_values("copt_step")
        ax.plot(
            group["copt_step"],
            group["relative_E_from_initial_eV"],
            marker="o",
            color=TOKENS["blue"],
            linewidth=1.5,
        )
        ax.axhline(0, color=TOKENS["ink"], linewidth=0.8, linestyle=":")
        ax.set_title(f"{meta['copt_reaction']} | path {meta['copt_path_id']}", fontsize=10, color=TOKENS["ink"])
        ax.set_xlabel("copt step")
        ax.set_ylabel("rel. E / eV")
        style_axis(ax)
    for ax in axes[len(order):]:
        ax.axis("off")
    add_header(
        fig,
        "Highest constrained-optimization profiles",
        "Relative energy profiles for the largest apparent barriers found in the Chapter 6 HDF files.",
    )
    fig.subplots_adjust(top=0.87, left=0.08, right=0.98, bottom=0.07, hspace=0.55, wspace=0.28)
    path = OUTPUT_ROOT / "plot_copt_profiles.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def build_outputs(gas_references_ev: dict[str, float] | None = None) -> dict[str, Path]:
    results, references, adsorption, copt_points, barriers = build_tables(gas_references_ev)
    paths = save_tables(results, references, adsorption, copt_points, barriers)
    paths.update(
        {
            "reference_status_plot": plot_reference_status(adsorption),
            "adsorption_distribution_plot": plot_adsorption_delta_distribution(adsorption),
            "best_adsorption_plot": plot_best_adsorption_candidates(adsorption),
            "barrier_ranking_plot": plot_barrier_ranking(barriers),
            "copt_profiles_plot": plot_copt_profiles(copt_points, barriers),
        }
    )
    return paths


if __name__ == "__main__":
    written = build_outputs()
    for label, path in written.items():
        print(f"{label}: {path}")
