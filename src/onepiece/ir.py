from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

DEFAULT_IR_TOLERANCE_CM1 = 30.0
DEFAULT_CO_FREQUENCY_SCALING = 1.0089
REFERENCE_IR_BANDS: dict[str, list[float]] = {
    "CO": [1913.0, 1934.0, 2054.0, 2187.0],
    "CH3O": [1043.0],
}


def reference_ir_bands() -> dict[str, list[float]]:
    """Return a copy of the default experimental reference bands."""
    return {label: values.copy() for label, values in REFERENCE_IR_BANDS.items()}


def match_ir_frequencies(
    frequencies_cm1: Sequence[float] | None,
    reference_peaks_cm1: Sequence[float] | None,
    *,
    tolerance_cm1: float = DEFAULT_IR_TOLERANCE_CM1,
) -> list[dict[str, float | bool]]:
    """Match calculated positive frequencies against experimental reference peaks."""
    if not frequencies_cm1 or not reference_peaks_cm1:
        return []

    matches: list[dict[str, float | bool]] = []
    tolerance = abs(float(tolerance_cm1))
    for frequency in frequencies_cm1:
        try:
            value = float(frequency)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(value) or value <= 0.0:
            continue
        best_peak = min(reference_peaks_cm1, key=lambda peak: abs(value - float(peak)))
        delta = float(value) - float(best_peak)
        matches.append(
            {
                "calculated_frequency_cm1": float(value),
                "experimental_peak_cm1": float(best_peak),
                "delta_frequency_cm1": float(delta),
                "abs_delta_frequency_cm1": abs(float(delta)),
                "within_tolerance": bool(abs(float(delta)) <= tolerance),
            }
        )
    matches.sort(key=lambda item: (item["abs_delta_frequency_cm1"], item["calculated_frequency_cm1"]))
    return matches


def add_ir_peak_matches(
    frame: pd.DataFrame,
    *,
    tolerance_cm1: float = DEFAULT_IR_TOLERANCE_CM1,
    frequency_column: str = "frequencies_cm1",
    species_column: str = "adsorbate",
    references: Mapping[str, Sequence[float]] | None = None,
) -> pd.DataFrame:
    """Add IR peak-matching columns for rows that can be assigned to known adsorbates."""
    df = frame.copy()
    active_references = {
        str(label): [float(value) for value in values]
        for label, values in (references or REFERENCE_IR_BANDS).items()
        if values
    }

    df["ir_reference_species"] = None
    df["ir_experimental_peaks_cm1"] = None
    df["ir_peak_tolerance_cm1"] = float(abs(tolerance_cm1))
    df["ir_peak_matches"] = None
    df["ir_match_count"] = 0.0
    df["ir_within_tolerance_count"] = 0.0
    df["ir_best_calculated_frequency_cm1"] = np.nan
    df["ir_best_experimental_peak_cm1"] = np.nan
    df["ir_best_delta_cm1"] = np.nan
    df["ir_best_abs_delta_cm1"] = np.nan
    df["ir_best_within_tolerance"] = False

    if frequency_column not in df.columns:
        return df

    for index, row in df.iterrows():
        species = _resolve_ir_reference_species(
            row,
            references=active_references,
            species_column=species_column,
        )
        if species is None:
            continue
        frequencies = row.get(frequency_column)
        matches = match_ir_frequencies(
            frequencies if isinstance(frequencies, Sequence) and not isinstance(frequencies, str | bytes) else None,
            active_references.get(species),
            tolerance_cm1=tolerance_cm1,
        )
        if not matches:
            df.at[index, "ir_reference_species"] = species
            df.at[index, "ir_experimental_peaks_cm1"] = active_references.get(species)
            continue
        best = matches[0]
        df.at[index, "ir_reference_species"] = species
        df.at[index, "ir_experimental_peaks_cm1"] = active_references.get(species)
        df.at[index, "ir_peak_matches"] = matches
        df.at[index, "ir_match_count"] = float(len(matches))
        df.at[index, "ir_within_tolerance_count"] = float(sum(bool(item["within_tolerance"]) for item in matches))
        df.at[index, "ir_best_calculated_frequency_cm1"] = float(best["calculated_frequency_cm1"])
        df.at[index, "ir_best_experimental_peak_cm1"] = float(best["experimental_peak_cm1"])
        df.at[index, "ir_best_delta_cm1"] = float(best["delta_frequency_cm1"])
        df.at[index, "ir_best_abs_delta_cm1"] = float(best["abs_delta_frequency_cm1"])
        df.at[index, "ir_best_within_tolerance"] = bool(best["within_tolerance"])
    return df


def adsorption_frequency_plot_table(
    frame: pd.DataFrame,
    *,
    tolerance_cm1: float = DEFAULT_IR_TOLERANCE_CM1,
    references: Mapping[str, Sequence[float]] | None = None,
    co_frequency_scaling: float = DEFAULT_CO_FREQUENCY_SCALING,
) -> pd.DataFrame:
    """Build a plot-ready table for adsorption energy versus vibrational frequency."""
    enriched = frame.copy()
    if "ir_peak_matches" not in enriched.columns:
        enriched = add_ir_peak_matches(
            enriched,
            tolerance_cm1=tolerance_cm1,
            references=references,
        )

    rows: list[dict[str, object]] = []
    for index, row in enriched.iterrows():
        species = row.get("ir_reference_species")
        if species not in {"CO", "CH3O"}:
            continue
        adsorption_energy = _adsorption_energy_for_species(row, str(species))
        calculated_frequency = pd.to_numeric(pd.Series([row.get("ir_best_calculated_frequency_cm1")]), errors="coerce").iloc[0]
        experimental_peak = pd.to_numeric(pd.Series([row.get("ir_best_experimental_peak_cm1")]), errors="coerce").iloc[0]
        if pd.isna(adsorption_energy) or pd.isna(calculated_frequency):
            continue
        scale = float(co_frequency_scaling) if str(species) == "CO" else 1.0
        scaled_frequency = float(calculated_frequency) * scale
        scaled_delta = scaled_frequency - float(experimental_peak) if pd.notna(experimental_peak) else np.nan
        rows.append(
            {
                "Name": row.get("Name", index),
                "adsorbate": species,
                "surface_ref": row.get("surface_ref"),
                "adsorption_energy_eV": float(adsorption_energy),
                "calculated_frequency_cm1": float(calculated_frequency),
                "frequency_scaling_factor": float(scale),
                "scaled_frequency_cm1": float(scaled_frequency),
                "experimental_peak_cm1": float(experimental_peak) if pd.notna(experimental_peak) else np.nan,
                "scaled_delta_frequency_cm1": float(scaled_delta) if pd.notna(scaled_delta) else np.nan,
                "within_tolerance": bool(abs(float(scaled_delta)) <= abs(float(tolerance_cm1))) if pd.notna(scaled_delta) else False,
                "source_index": index,
            }
        )
    return pd.DataFrame(rows)


def plot_adsorption_energy_vs_frequency(
    frame: pd.DataFrame,
    *,
    tolerance_cm1: float = DEFAULT_IR_TOLERANCE_CM1,
    references: Mapping[str, Sequence[float]] | None = None,
    co_frequency_scaling: float = DEFAULT_CO_FREQUENCY_SCALING,
    frequency_window_cm1: float = 50.0,
):
    """Plot adsorption energy on x and matched frequency on y for CO and CH3O rows.

    Expects a frame that already carries adsorption energies and IR peak
    matches (see :func:`onepiece.ir.add_ir_peak_matches`). Returns a
    matplotlib ``(figure, axes)`` pair with one panel per adsorbate species.

    Examples
    --------
    .. code-block:: python

        import onepiece
        from onepiece.ir import add_ir_peak_matches

        combined, _refs = onepiece.assign_references_before_merge(
            {"demo": "calculations.hdf"}
        )
        combined = onepiece.add_adsorption_energies(
            combined, {"CO": -14.8, "CH3OH": -30.2, "H2": -6.8}
        )
        combined = add_ir_peak_matches(combined)
        fig, axes = onepiece.plot_adsorption_energy_vs_frequency(combined)
        fig.savefig("adsorption_vs_frequency.png")
    """
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except Exception as exc:  # pragma: no cover - exercised only when matplotlib is unavailable
        raise RuntimeError("matplotlib and seaborn are required for adsorption-energy/frequency plots.") from exc

    plot_data = adsorption_frequency_plot_table(
        frame,
        tolerance_cm1=tolerance_cm1,
        references=references,
        co_frequency_scaling=co_frequency_scaling,
    )
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8), sharex=False, sharey=False)
    axes = np.atleast_1d(axes)
    if plot_data.empty:
        for ax, species in zip(axes, ("CO", "CH3O"), strict=False):
            ax.set_xlabel("Adsorption energy / eV")
            ax.set_ylabel("Frequency / cm$^{-1}$")
            ax.set_title(species)
        fig.suptitle("Adsorption energy vs frequency")
        fig.tight_layout()
        return fig, axes

    sns.set_theme(style="whitegrid", context="talk")
    surface_refs = [value for value in plot_data["surface_ref"].dropna().unique().tolist() if str(value).strip()]
    palette = sns.color_palette("colorblind", n_colors=max(len(surface_refs), 1))
    color_map = {label: palette[index] for index, label in enumerate(surface_refs)}

    for ax, species in zip(axes, ("CO", "CH3O"), strict=False):
        group = plot_data.loc[plot_data["adsorbate"] == species].copy()
        if group.empty:
            ax.set_xlabel("Adsorption energy / eV")
            ax.set_ylabel("Frequency / cm$^{-1}$")
            ax.set_title(species)
            continue

        hue_order = [value for value in surface_refs if value in set(group["surface_ref"].dropna())]
        sns.scatterplot(
            data=group,
            x="adsorption_energy_eV",
            y="scaled_frequency_cm1",
            hue="surface_ref" if group["surface_ref"].notna().any() else None,
            hue_order=hue_order or None,
            palette=color_map if hue_order else None,
            style="surface_ref" if group["surface_ref"].notna().any() else None,
            s=90,
            alpha=0.92,
            edgecolor="white",
            linewidth=0.6,
            ax=ax,
        )
        ax.set_xlabel("Adsorption energy / eV")
        ax.set_ylabel("Frequency / cm$^{-1}$")
        ax.set_title(species)

        center = _frequency_window_center(group)
        half_window = abs(float(frequency_window_cm1)) / 2.0
        if np.isfinite(center) and half_window > 0.0:
            ax.set_ylim(center - half_window, center + half_window)

        handles, labels = ax.get_legend_handles_labels()
        if handles and labels and labels != ["surface_ref"]:
            ax.legend(title="surface_ref", frameon=True)
        else:
            legend = ax.get_legend()
            if legend is not None:
                legend.remove()

    fig.suptitle("Adsorption energy vs frequency")
    fig.tight_layout()
    return fig, axes


def _resolve_ir_reference_species(
    row: pd.Series,
    *,
    references: Mapping[str, Sequence[float]],
    species_column: str,
) -> str | None:
    for column in (species_column, "adsorbate", "Formula", "Name"):
        value = str(row.get(column, "")).strip()
        if not value:
            continue
        for label in references:
            if value.upper() == label.upper():
                return label
            if label.upper() in value.upper():
                return label
    return None


def _adsorption_energy_for_species(row: pd.Series, species: str) -> float:
    preferred_columns = {
        "CO": ("E_ads_CO_eV", "adsorption_energy", "adsorption_free_energy"),
        "CH3O": ("E_ads_CH3OH_to_CH3O_eV", "E_ads_CH3O_eV", "adsorption_energy", "adsorption_free_energy"),
    }.get(species, ("adsorption_energy", "adsorption_free_energy"))
    for column in preferred_columns:
        value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
        if pd.notna(value):
            return float(value)
    return float("nan")


def _frequency_window_center(plot_group: pd.DataFrame) -> float:
    experimental = pd.to_numeric(plot_group["experimental_peak_cm1"], errors="coerce").dropna()
    if not experimental.empty:
        return float(experimental.median())
    frequencies = pd.to_numeric(plot_group["scaled_frequency_cm1"], errors="coerce").dropna()
    if not frequencies.empty:
        return float(frequencies.median())
    return float("nan")
