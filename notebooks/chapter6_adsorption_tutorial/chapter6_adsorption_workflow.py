from __future__ import annotations

import os

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd


try:
    import numpy.core as numpy_core

    sys.modules.setdefault("numpy._core", numpy_core)
    sys.modules.setdefault("numpy._core.multiarray", np.core.multiarray)
    sys.modules.setdefault("numpy._core.numeric", np.core.numeric)
except Exception:
    pass


ROOT = Path(__file__).resolve().parent
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

# Fill these values with gas-phase calculations from the same DFT setup.
# They are intentionally NaN so the workflow never pretends to know a reference
# energy that is not present in the provided slab HDF files.
GAS_REFERENCES_EV = {
    "CO": np.nan,
    "CH3OH": np.nan,
    "H2": np.nan,
}

ADSORBATE_TOKENS = (
    "CH3OH",
    "CH3O",
    "H2COOH",
    "HCOOH",
    "HCOO",
    "COOH",
    "CO2",
    "HCO",
    "CO",
)
ADSORBATE_PATTERN = re.compile(
    r"[-_%](CH3OH|CH3O|H2COOH|HCOOH|HCOO|COOH|CO2|HCO|CO)(?:[-_%].*|$)"
)
ELEMENT_PATTERN = re.compile(r"([A-Z][a-z]?)(\d*)")


def read_onepiece_hdf(path: Path, key: str = "df") -> pd.DataFrame:
    """Read a OnePiece pandas HDF table and keep provenance columns."""
    path = Path(path)
    frame = pd.read_hdf(path, key=key).copy()
    frame["dataset"] = path.stem
    frame["source_hdf"] = str(path)
    frame["source_row"] = np.arange(len(frame), dtype=int)
    return frame


def formula_counts(formula: object) -> dict[str, int]:
    if not isinstance(formula, str):
        return {}
    counts: dict[str, int] = {}
    for element, number in ELEMENT_PATTERN.findall(formula):
        counts[element] = counts.get(element, 0) + int(number or 1)
    return counts


def count_from_row(row: pd.Series, element: str) -> float:
    if element in row.index:
        value = pd.to_numeric(row[element], errors="coerce")
        if pd.notna(value):
            return float(value)
    return float(formula_counts(row.get("Formula")).get(element, 0))


def guess_adsorbate(name: object) -> str:
    if not isinstance(name, str):
        return ""
    match = ADSORBATE_PATTERN.search(name)
    if match:
        return match.group(1)
    return ""


def reference_name_guess(name: object) -> str:
    if not isinstance(name, str):
        return ""
    return ADSORBATE_PATTERN.sub("", name)


def choose_reference_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Choose one clean/reference row per local surface key inside one HDF file."""
    candidates = frame.loc[
        (frame["adsorbate"] == "")
        & frame["E"].notna()
        & (pd.to_numeric(frame["E"], errors="coerce") != 0)
    ].copy()
    if candidates.empty:
        return candidates

    candidates["reference_candidate_count"] = candidates.groupby("surface_key")["Name"].transform(
        "count"
    )
    candidates = candidates.sort_values(["surface_key", "E"], ascending=[True, True])
    refs = candidates.drop_duplicates("surface_key", keep="first").copy()
    refs["reference_ambiguous"] = refs["reference_candidate_count"] > 1
    return refs


def assign_surface_references_one_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Assign surface references before concatenating different HDF files."""
    df = frame.copy()
    df["E"] = pd.to_numeric(df.get("E"), errors="coerce")
    df["Name"] = df.get("Name", pd.Series([""] * len(df))).astype(str)
    df["adsorbate"] = df["Name"].map(guess_adsorbate)
    df["is_adsorbate"] = df["adsorbate"] != ""
    df["surface_key"] = df["Name"].map(reference_name_guess)

    refs = choose_reference_rows(df)
    reference_lookup = refs.set_index("surface_key") if not refs.empty else pd.DataFrame()

    df["surface_ref_name"] = df["surface_key"].map(
        reference_lookup["Name"] if "Name" in reference_lookup else pd.Series(dtype=object)
    )
    df["surface_ref_E"] = df["surface_key"].map(
        reference_lookup["E"] if "E" in reference_lookup else pd.Series(dtype=float)
    )
    df["surface_ref_formula"] = df["surface_key"].map(
        reference_lookup["Formula"] if "Formula" in reference_lookup else pd.Series(dtype=object)
    )
    df["surface_ref_ambiguous"] = df["surface_key"].map(
        reference_lookup["reference_ambiguous"]
        if "reference_ambiguous" in reference_lookup
        else pd.Series(dtype=bool)
    )

    df["surface_ref_status"] = "ok"
    df.loc[df["surface_ref_name"].isna(), "surface_ref_status"] = "missing"
    df.loc[df["surface_ref_ambiguous"].fillna(False), "surface_ref_status"] = "ambiguous"
    df.loc[~df["is_adsorbate"] & (df["surface_ref_status"] == "ok"), "surface_ref_status"] = "self"

    for element in ["C", "H", "O"]:
        current = df.apply(lambda row: count_from_row(row, element), axis=1)
        ref_counts = refs.set_index("surface_key").apply(
            lambda row: count_from_row(row, element), axis=1
        ) if not refs.empty else pd.Series(dtype=float)
        df[f"delta_{element}"] = current - df["surface_key"].map(ref_counts).fillna(0)

    df["delta_E_to_surface_eV"] = df["E"] - df["surface_ref_E"]
    return df


def assign_references_before_merge(hdf_files: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    enriched_frames = []
    reference_frames = []
    for label, path in hdf_files.items():
        frame = read_onepiece_hdf(path)
        enriched = assign_surface_references_one_frame(frame)
        enriched["dataset_label"] = label
        enriched_frames.append(enriched)
        reference_frames.append(
            enriched.loc[~enriched["is_adsorbate"], [
                "dataset_label",
                "Name",
                "Formula",
                "E",
                "surface_key",
                "surface_ref_status",
                "source_hdf",
                "source_row",
            ]]
        )
    combined = pd.concat(enriched_frames, ignore_index=True, sort=False)
    references = pd.concat(reference_frames, ignore_index=True, sort=False)
    return combined, references


def add_adsorption_energy_columns(
    frame: pd.DataFrame,
    gas_references_ev: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Add CO and methanol-derived adsorption energies.

    CO molecular adsorption:
        E_ads(CO) = (E(CO*) - E(*) - n_CO E(CO_gas)) / n_CO

    Methoxy from methanol, if the slab row is CH3O:
        * + CH3OH(g) -> CH3O* + 1/2 H2(g)
        E_ads = (E(CH3O*) + 0.5 n E(H2) - E(*) - n E(CH3OH)) / n
    """
    refs = GAS_REFERENCES_EV if gas_references_ev is None else gas_references_ev
    df = frame.copy()
    df["n_CO_adsorbates"] = np.where(df["adsorbate"].eq("CO"), df["delta_C"], np.nan)
    df["n_CH3O_adsorbates"] = np.where(df["adsorbate"].eq("CH3O"), df["delta_C"], np.nan)

    valid_co = df["n_CO_adsorbates"].fillna(0) > 0
    df["E_ads_CO_eV"] = np.nan
    df.loc[valid_co, "E_ads_CO_eV"] = (
        df.loc[valid_co, "E"]
        - df.loc[valid_co, "surface_ref_E"]
        - df.loc[valid_co, "n_CO_adsorbates"] * refs["CO"]
    ) / df.loc[valid_co, "n_CO_adsorbates"]

    valid_ch3o = df["n_CH3O_adsorbates"].fillna(0) > 0
    df["E_ads_CH3OH_to_CH3O_eV"] = np.nan
    df.loc[valid_ch3o, "E_ads_CH3OH_to_CH3O_eV"] = (
        df.loc[valid_ch3o, "E"]
        + 0.5 * df.loc[valid_ch3o, "n_CH3O_adsorbates"] * refs["H2"]
        - df.loc[valid_ch3o, "surface_ref_E"]
        - df.loc[valid_ch3o, "n_CH3O_adsorbates"] * refs["CH3OH"]
    ) / df.loc[valid_ch3o, "n_CH3O_adsorbates"]
    return df


def build_outputs() -> dict[str, Path]:
    combined, references = assign_references_before_merge(HDF_FILES)
    results = add_adsorption_energy_columns(combined)

    focused_columns = [
        "dataset_label",
        "Name",
        "Formula",
        "adsorbate",
        "surface_ref_name",
        "surface_ref_formula",
        "surface_ref_status",
        "E",
        "surface_ref_E",
        "delta_E_to_surface_eV",
        "delta_C",
        "delta_H",
        "delta_O",
        "n_CO_adsorbates",
        "E_ads_CO_eV",
        "n_CH3O_adsorbates",
        "E_ads_CH3OH_to_CH3O_eV",
        "fmax",
        "source_hdf",
        "source_row",
    ]
    focused = results.loc[results["is_adsorbate"], [
        column for column in focused_columns if column in results.columns
    ]].copy()

    paths = {
        "combined_pickle": OUTPUT_ROOT / "chapter6_combined_with_surface_references.pkl",
        "references_csv": OUTPUT_ROOT / "chapter6_surface_reference_assignments.csv",
        "adsorption_csv": OUTPUT_ROOT / "chapter6_adsorption_energy_table.csv",
        "summary_csv": OUTPUT_ROOT / "chapter6_adsorption_summary.csv",
        "delta_e_plot": OUTPUT_ROOT / "chapter6_delta_E_CO_CH3O_by_dataset.png",
    }
    results.to_pickle(paths["combined_pickle"])
    references.to_csv(paths["references_csv"], index=False)
    focused.to_csv(paths["adsorption_csv"], index=False)

    summary = focused.groupby(["dataset_label", "adsorbate", "surface_ref_status"]).agg(
        rows=("Name", "count"),
        median_delta_E_to_surface_eV=("delta_E_to_surface_eV", "median"),
        min_delta_E_to_surface_eV=("delta_E_to_surface_eV", "min"),
        max_delta_E_to_surface_eV=("delta_E_to_surface_eV", "max"),
    ).reset_index()
    summary.to_csv(paths["summary_csv"], index=False)

    try:
        import matplotlib.pyplot as plt

        plot_data = focused.loc[
            focused["surface_ref_status"].eq("ok")
            & focused["adsorbate"].isin(["CO", "CH3O"])
            & focused["delta_E_to_surface_eV"].notna()
            & focused["delta_E_to_surface_eV"].between(-80, 20)
        ].copy()
        if not plot_data.empty:
            labels = []
            values = []
            for (dataset, adsorbate), group in plot_data.groupby(["dataset_label", "adsorbate"]):
                labels.append(f"{dataset}\n{adsorbate}")
                values.append(group["delta_E_to_surface_eV"].to_numpy())

            fig, ax = plt.subplots(figsize=(12, 5.5))
            ax.boxplot(values, labels=labels, showfliers=False, patch_artist=True)
            ax.set_ylabel("Delta E to assigned clean surface / eV")
            ax.set_title("CO and CH3O rows after assigning local surface references")
            ax.grid(axis="y", alpha=0.25)
            fig.autofmt_xdate(rotation=35, ha="right")
            fig.tight_layout()
            fig.savefig(paths["delta_e_plot"], dpi=180)
            plt.close(fig)
    except Exception as exc:
        print(f"Plot creation skipped: {exc}")
    return paths


if __name__ == "__main__":
    written = build_outputs()
    for label, path in written.items():
        print(f"{label}: {path}")
