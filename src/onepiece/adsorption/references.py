"""Gas/surface reference assignment and OnePiece HDF source reading."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from onepiece.adsorption.copt import is_constrained_optimization
from onepiece.adsorption.formulas import (
    count_element,
    formula_counts,
    guess_adsorbate,
    surface_key_from_name,
)
from onepiece.frame_utils import ensure_name_index

EQUATION_TOKEN_PATTERN = re.compile(r"(?P<sign>[+-]?)\s*(?P<coef>\d*\.?\d*)\s*(?P<species>[A-Za-z0-9_]+)")
DEFAULT_FORMULA_GAS_SPECIES = ("CO2", "H2", "H2O", "NH3")
NON_METAL_REFERENCE_ELEMENTS = {"C", "H", "O", "N"}


@dataclass(frozen=True)
class GasReferences:
    """Gas-phase reference energies in eV from the same computational setup.

    Species you do not supply default to ``nan``, and the energy columns that
    depend on them simply stay empty.

    Examples
    --------
    >>> from onepiece import GasReferences
    >>> refs = GasReferences.from_mapping({"CO": -14.8, "H2": -6.8})
    >>> refs.co
    -14.8
    >>> refs.ch3oh
    nan
    """

    co: float = np.nan
    co2: float = np.nan
    ch3oh: float = np.nan
    h2: float = np.nan
    h2o: float = np.nan

    @classmethod
    def from_mapping(cls, values: Mapping[str, float] | None) -> GasReferences:
        if values is None:
            return cls()
        normalized = {str(key).lower(): value for key, value in values.items()}
        return cls(
            co=float(normalized.get("co", np.nan)),
            co2=float(normalized.get("co2", np.nan)),
            ch3oh=float(normalized.get("ch3oh", np.nan)),
            h2=float(normalized.get("h2", np.nan)),
            h2o=float(normalized.get("h2o", np.nan)),
        )


def parse_reference_equation(equation: str) -> dict[str, float]:
    """Parse a simple gas-reference equation like ``CO2+H2-H2O``."""
    text = str(equation or "").replace(" ", "")
    if not text:
        return {}
    refs: dict[str, float] = {}
    for match in EQUATION_TOKEN_PATTERN.finditer(text):
        species = str(match.group("species") or "").strip()
        if not species:
            continue
        sign = -1.0 if match.group("sign") == "-" else 1.0
        coef_text = str(match.group("coef") or "").strip()
        coefficient = float(coef_text) if coef_text else 1.0
        refs[species] = refs.get(species, 0.0) + sign * coefficient
    return {species: value for species, value in refs.items() if not np.isclose(value, 0.0)}


def infer_reference_equation_from_formula(formula: str) -> dict[str, float]:
    """Infer gas-reference coefficients from a CHON formula.

    The default basis is the combination of ``CO2``, ``H2``, ``H2O``, and
    ``NH3``. Coefficients may be fractional or negative.
    """
    counts = formula_counts(formula)
    if not counts:
        return {}
    if any(element not in NON_METAL_REFERENCE_ELEMENTS for element in counts):
        counts = {element: count for element, count in counts.items() if element in NON_METAL_REFERENCE_ELEMENTS}
    if not counts:
        return {}
    co2 = float(counts.get("C", 0))
    nh3 = float(counts.get("N", 0))
    h2o = float(counts.get("O", 0) - 2.0 * co2)
    h2 = 0.5 * (float(counts.get("H", 0)) - 2.0 * h2o - 3.0 * nh3)
    refs = {
        "CO2": co2,
        "H2": h2,
        "H2O": h2o,
        "NH3": nh3,
    }
    return {species: value for species, value in refs.items() if not np.isclose(value, 0.0)}


def default_room_temperature_phase(element: str) -> str:
    """Return the default bulk phase label used for metal references."""
    return "fcc"


def infer_adsorbate_recipe(
    adsorbate: str,
    *,
    formula: str | None = None,
    equation: str | None = None,
    basis: str | None = None,
) -> dict[str, object]:
    """Infer a backend recipe for one adsorbate from formula/equation information."""
    label = str(adsorbate or "").strip()
    active_formula = str(formula or label).strip()
    counts = formula_counts(active_formula)
    gas_refs = parse_reference_equation(str(equation)) if equation else infer_reference_equation_from_formula(active_formula)
    bulk_refs = {
        element: float(count)
        for element, count in counts.items()
        if element not in NON_METAL_REFERENCE_ELEMENTS and int(count) > 0
    }
    bulk_phases = {element: default_room_temperature_phase(element) for element in bulk_refs}
    chosen_basis = str(basis or _default_basis_from_counts(counts)).strip() or "C"
    recipe: dict[str, object] = {
        "basis": chosen_basis,
        "gas_refs": gas_refs,
        "formula": active_formula,
    }
    if equation:
        recipe["equation"] = str(equation)
    if bulk_refs:
        recipe["bulk_refs"] = bulk_refs
        recipe["bulk_phases"] = bulk_phases
    return recipe


def infer_adsorption_recipes(
    frame: pd.DataFrame,
    *,
    adsorbate_column: str = "adsorbate",
    adsorbate_formula_column: str = "adsorbate_formula",
    formula_column: str = "Formula",
    equation_columns: tuple[str, ...] = ("equation", "adsorbate_equation", "reaction_equation"),
) -> dict[str, dict[str, object]]:
    """Infer adsorption recipes for all adsorbates that appear in a dataframe."""
    df = frame.copy()
    if adsorbate_column not in df.columns:
        df = annotate_adsorbates(df)
    recipes: dict[str, dict[str, object]] = {}
    for _, row in df.iterrows():
        adsorbate = str(row.get(adsorbate_column, "")).strip()
        if not adsorbate:
            continue
        if adsorbate in recipes:
            continue
        formula_value = str(
            row.get(adsorbate_formula_column)
            or adsorbate
            or row.get(formula_column)
        ).strip()
        equation = next(
            (str(row.get(column)).strip() for column in equation_columns if str(row.get(column, "")).strip()),
            "",
        )
        recipes[adsorbate] = infer_adsorbate_recipe(
            adsorbate,
            formula=formula_value,
            equation=equation or None,
        )
    return recipes


def _default_basis_from_counts(counts: dict[str, int]) -> str:
    for element in ("C", "N", "O", "H"):
        if counts.get(element, 0) > 0:
            return element
    for element in sorted(counts):
        if counts.get(element, 0) > 0:
            return element
    return "C"


def read_onepiece_hdf(path: Path | str, key: str = "df", dataset_label: str | None = None) -> pd.DataFrame:
    """Read one OnePiece pandas HDF file and attach provenance columns."""
    path = Path(path)
    frame = pd.read_hdf(path, key=key).copy()
    frame["dataset"] = path.stem
    frame["dataset_label"] = dataset_label or path.stem
    frame["source_hdf"] = str(path)
    frame["source_row"] = np.arange(len(frame), dtype=int)
    return frame


def read_onepiece_hdfs(
    hdf_files: Mapping[str, Path | str],
    key: str = "df",
) -> dict[str, pd.DataFrame]:
    """Read several HDF files into source-labeled DataFrames."""
    return {
        label: read_onepiece_hdf(path, key=key, dataset_label=label)
        for label, path in hdf_files.items()
    }


def annotate_adsorbates(frame: pd.DataFrame) -> pd.DataFrame:
    """Add adsorbate, surface key, and basic energy columns."""
    df = ensure_name_index(frame)
    df["Name"] = df.get("Name", pd.Series([""] * len(df), index=df.index)).astype(str)
    df["E"] = pd.to_numeric(df.get("E"), errors="coerce")
    df["adsorbate"] = df["Name"].map(guess_adsorbate)
    df["is_adsorbate"] = df["adsorbate"] != ""
    df["surface_key"] = df["Name"].map(surface_key_from_name)
    return df


def choose_surface_references(frame: pd.DataFrame) -> pd.DataFrame:
    """Choose one clean/reference row per surface key in a single source table."""
    df = annotate_adsorbates(frame)
    candidates = df.loc[
        ~df["is_adsorbate"]
        & df["E"].notna()
        & (pd.to_numeric(df["E"], errors="coerce") != 0)
        & ~is_constrained_optimization(df)
    ].copy()
    if candidates.empty:
        return candidates

    candidates["reference_candidate_count"] = candidates.groupby("surface_key")["Name"].transform(
        "count"
    )
    candidates = candidates.sort_values(["surface_key", "E"], ascending=[True, True])
    references = candidates.drop_duplicates("surface_key", keep="first").copy()
    references["reference_ambiguous"] = references["reference_candidate_count"] > 1
    return references


def assign_surface_references(frame: pd.DataFrame) -> pd.DataFrame:
    """Assign clean-surface references before merging multiple HDF sources."""
    df = annotate_adsorbates(frame)
    refs = choose_surface_references(df)
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

    for element in ("C", "H", "O"):
        current = df.apply(lambda row, element=element: count_element(row, element), axis=1)
        ref_counts = (
            refs.set_index("surface_key").apply(
                lambda row, element=element: count_element(row, element),
                axis=1,
            )
            if not refs.empty
            else pd.Series(dtype=float)
        )
        df[f"delta_{element}"] = current - df["surface_key"].map(ref_counts).fillna(0)

    df["delta_E_to_surface_eV"] = df["E"] - df["surface_ref_E"]
    return df


def assign_references_before_merge(
    hdf_files: Mapping[str, Path | str],
    key: str = "df",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read, reference-annotate, and then merge HDF sources.

    Each HDF file is read separately, every row gets its clean-surface
    reference assigned (``surface_ref_name``, ``surface_ref_E``, ``delta_*``
    stoichiometry columns) *within that source*, and only then are the
    sources concatenated. Returns the combined frame and a table of the
    chosen surface references.

    Examples
    --------
    >>> import tempfile
    >>> from pathlib import Path
    >>> import pandas as pd
    >>> import onepiece
    >>> root = Path(tempfile.mkdtemp())
    >>> pd.DataFrame({
    ...     "Name": ["Cu211", "Cu211-CO"],
    ...     "Formula": ["Cu36", "Cu36CO"],
    ...     "E": [-100.0, -115.2],
    ... }).to_hdf(root / "calcs.hdf", key="df")
    >>> combined, references = onepiece.assign_references_before_merge(
    ...     {"demo": root / "calcs.hdf"}
    ... )
    >>> combined.loc["Cu211-CO", "surface_ref_name"]
    'Cu211'
    >>> round(float(combined.loc["Cu211-CO", "delta_E_to_surface_eV"]), 1)
    -15.2
    """
    enriched_frames = []
    reference_frames = []
    for label, path in hdf_files.items():
        frame = read_onepiece_hdf(path, key=key, dataset_label=label)
        enriched = assign_surface_references(frame)
        enriched["dataset_label"] = label
        enriched_frames.append(enriched)
        reference_frames.append(
            enriched.loc[
                ~enriched["is_adsorbate"],
                [
                    "dataset_label",
                    "Name",
                    "Formula",
                    "E",
                    "surface_key",
                    "surface_ref_status",
                    "source_hdf",
                    "source_row",
                ],
            ]
        )
    combined = ensure_name_index(pd.concat(enriched_frames, ignore_index=False, sort=False))
    references = ensure_name_index(pd.concat(reference_frames, ignore_index=False, sort=False))
    return combined, references
