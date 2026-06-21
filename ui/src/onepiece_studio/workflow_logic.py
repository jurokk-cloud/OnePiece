"""Pure workflow computation helpers shared by the Workflow Builder page.

Everything here is plain pandas/python: name suggestion, editor-table parsing,
and standard-operation recipes. Nothing in this module renders or imports
Streamlit, so it stays importable from scripts and tests on its own.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

WORKFLOW_GAS_LABELS = ("CO", "CO2", "CH3OH", "H2", "H2O")


NUMERIC_OPERATORS = {
    "+": "sum",
    "-": "difference",
    "*": "product",
    "/": "ratio",
}


FILTER_OPERATORS = [
    "contains",
    "not contains",
    "equals",
    "not equals",
    ">",
    ">=",
    "<",
    "<=",
    "is not empty",
    "is empty",
]


def valid_new_column(name: str) -> bool:
    return bool(name and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name))


def column_index(columns: list[str], column: str | None, *, fallback: int = 0) -> int:
    if not columns:
        return 0
    if column in columns:
        return columns.index(column)
    return min(max(fallback, 0), len(columns) - 1)


def sanitize_identifier(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", str(text).strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        return "derived_column"
    if cleaned[0].isdigit():
        cleaned = f"col_{cleaned}"
    return cleaned


def suggest_derived_name_binary(left: str, operator: str, right: str) -> str:
    suffix = {
        "+": "plus",
        "-": "minus",
        "*": "times",
        "/": "per",
    }.get(operator, "op")
    return sanitize_identifier(f"{left}_{suffix}_{right}")


def suggest_derived_name_scalar(left: str, operator: str, scalar: float) -> str:
    suffix = {
        "+": "plus",
        "-": "minus",
        "*": "times",
        "/": "per",
    }.get(operator, "op")
    scalar_label = str(scalar).replace(".", "_").replace("-", "neg_")
    return sanitize_identifier(f"{left}_{suffix}_{scalar_label}")


def suggest_contains_name(column: str, token: str) -> str:
    token_part = token or "match"
    return sanitize_identifier(f"{column}_{token_part}_flag")


def standard_operation_recipe(
    recipe: str,
    gas_refs: dict[str, float | None],
) -> tuple[list[dict[str, Any]], str]:
    adsorption_step = {
        "kind": "derive_adsorption_columns",
        "gas_references": gas_refs,
        "label": "assign surface references and derive adsorption columns",
    }
    if recipe == "Assign surface references and adsorption columns":
        return (
            [adsorption_step],
            "Adds `surface_ref_name`, `surface_ref_E`, `delta_E_to_surface_eV`, and the gas-dependent adsorption columns where the required references are available.",
        )
    if recipe == "Calculate CO adsorption energy per CO":
        return (
            [
                {
                    **adsorption_step,
                    "label": "calculate CO adsorption energy per CO from dataset references",
                    "preset": "co_adsorption_per_co",
                }
            ],
            "Calculates `n_CO_adsorbates` and `E_ads_CO_eV` from the dataset references. This is the direct workflow step for CO adsorption-energy analysis.",
        )
    if recipe == "CO adsorption analysis starter":
        return (
            [
                {
                    **adsorption_step,
                    "label": "calculate CO adsorption energy per CO from dataset references",
                    "preset": "co_adsorption_per_co",
                },
                {
                    "kind": "filter",
                    "column": "adsorbate",
                    "operator": "equals",
                    "value": "CO",
                    "new_column": "",
                    "label": "filter adsorbate equals 'CO'",
                },
                {
                    "kind": "filter",
                    "column": "E_ads_CO_eV",
                    "operator": "is not empty",
                    "value": "",
                    "new_column": "",
                    "label": "filter E_ads_CO_eV is not empty",
                },
            ],
            "Builds a ready-to-plot CO workflow: first derive the adsorption columns, then keep only CO rows with a filled `E_ads_CO_eV` value.",
        )
    if recipe == "Adsorption + Gibbs analysis starter":
        return (
            [
                {
                    **adsorption_step,
                    "label": "assign surface references and derive adsorption columns for thermochemistry-ready rows",
                },
                {
                    "kind": "derive_gibbs_free_energy",
                    "temperature": 298.15,
                    "energy_column": "E",
                    "output_column": "G",
                    "label": "derive Gibbs free energies at 298.15 K",
                },
                {
                    "kind": "derive_gibbs_adsorption",
                    "gas_references": gas_refs,
                    "temperature": 298.15,
                    "energy_column": "E",
                    "gibbs_column": "G",
                    "output_column": "adsorption_free_energy",
                    "label": "derive adsorption Gibbs free energies from dataset references",
                },
            ],
            "Builds a thermochemistry-ready workflow: assign clean surface references, derive `G`, then calculate `adsorption_free_energy` where the required row-local thermo columns and gas references are available.",
        )
    if recipe == "Count all detected elements":
        return (
            [
                {
                    "kind": "count_all_elements",
                    "label": "count all detected elements into columns",
                }
            ],
            "Scans the current dataset for all present elements and adds one count column per element. Structure columns are preferred, with Formula and existing element columns as fallback.",
        )
    if recipe == "Bader/VASP charge descriptors":
        return (
            [
                {
                    "kind": "derive_vasp_charge_descriptors",
                    "charge_source": "acf",
                    "calculation_path_column": "Path",
                    "structure_column": "struc",
                    "label": "derive ACF.dat-preferred charge descriptors and adsorption-style charge references",
                }
            ],
            "Reads `ACF.dat` files by default, falls back to `CHGCAR` if needed, and compares adsorbate-side charge against the clean surface reference and against gas-phase or valence references.",
        )
    if recipe == "ASE geometry, site and QC descriptors":
        return (
            [
                {
                    "kind": "derive_ase_analysis_descriptors",
                    "calculation_path_column": "Path",
                    "structure_column": "struc",
                    "include_pdos": False,
                    "label": "derive ASE geometry, adsorption-site, and QC descriptors",
                }
            ],
            "Adds ASE-native descriptors such as slab thickness, coordination, adsorption-site class, dissociation/desorption flags, and surface reconstruction metrics.",
        )
    raise ValueError(f"Unsupported standard operation recipe: {recipe}")


def display_preview(dataframe: pd.DataFrame) -> pd.DataFrame:
    display = dataframe.copy()
    for column in display.columns:
        if display[column].dtype == "object":
            display[column] = display[column].map(short_value)
    return display


def short_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return None
    except (TypeError, ValueError):
        pass
    text = str(value)
    return text if len(text) <= 180 else text[:177] + "..."


def split_nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text).splitlines() if line.strip()]


def split_csv_tokens(text: str) -> list[str]:
    tokens = [token.strip() for token in str(text).split(",")]
    return [token for token in tokens if token]


def default_normalization_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"from_value": "CHO", "to_value": "HCO"},
            {"from_value": "CO_NH2", "to_value": "NH2_CO"},
            {"from_value": "H2NHCO", "to_value": "H2NCHO"},
            {"from_value": "H2NHCO_H", "to_value": "H2NCHO_H"},
        ]
    )


def normalization_pairs_from_table(table: pd.DataFrame) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if table is None or table.empty:
        return pairs
    for row in table.to_dict("records"):
        old = str(row.get("from_value", "")).strip()
        new = str(row.get("to_value", "")).strip()
        if old and new:
            pairs.append((old, new))
    return pairs


def default_drop_rules_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"pattern": "test", "match_mode": "contains", "reason": "Temporary or exploratory calculations"},
            {"pattern": "copt", "match_mode": "contains", "reason": "Constrained optimization helper rows"},
            {"pattern": "-diss", "match_mode": "contains", "reason": "Known dissociated structures"},
        ]
    )


def drop_rules_from_table(table: pd.DataFrame) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    if table is None or table.empty:
        return rules
    for row in table.to_dict("records"):
        pattern = str(row.get("pattern", "")).strip()
        match_mode = str(row.get("match_mode", "exact")).strip().lower() or "exact"
        reason = str(row.get("reason", "")).strip()
        if not pattern or match_mode not in {"exact", "contains", "regex"}:
            continue
        rules.append({"pattern": pattern, "match_mode": match_mode, "reason": reason})
    return rules


def default_gas_reference_table(gas_defaults: dict[str, float | None]) -> pd.DataFrame:
    rows = []
    for species in ["CO", "H2", "H2O", "CH3OH", "CO2", "NH3"]:
        rows.append(
            {
                "species": species,
                "energy_eV": gas_defaults.get(species) if gas_defaults.get(species) is not None else np.nan,
            }
        )
    return pd.DataFrame(rows)


def default_recipe_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"adsorbate": "CO", "basis": "C", "CO": 1.0, "H2": 0.0, "H2O": 0.0, "CH3OH": 0.0, "CO2": 0.0, "NH3": 0.0},
            {"adsorbate": "CH3O", "basis": "C", "CO": 1.0, "H2": 1.5, "H2O": 0.0, "CH3OH": 0.0, "CO2": 0.0, "NH3": 0.0},
            {"adsorbate": "HCO", "basis": "C", "CO": 1.0, "H2": 0.5, "H2O": 0.0, "CH3OH": 0.0, "CO2": 0.0, "NH3": 0.0},
            {"adsorbate": "OH", "basis": "O", "CO": 0.0, "H2": -0.5, "H2O": 1.0, "CH3OH": 0.0, "CO2": 0.0, "NH3": 0.0},
        ]
    )


def default_pdos_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "column": "metal_d_pdos_below_ef",
                "elements": "Cu,Ni,Ga,Zn",
                "orbitals": "d",
                "emin": -2.0,
                "emax": 0.0,
                "spin": "sum",
            }
        ]
    )


def pdos_integrations_from_table(table: pd.DataFrame) -> list[dict[str, Any]]:
    integrations: list[dict[str, Any]] = []
    for _, row in table.iterrows():
        column = str(row.get("column", "")).strip()
        elements = split_csv_tokens(str(row.get("elements", "")))
        orbitals = split_csv_tokens(str(row.get("orbitals", "")))
        emin = pd.to_numeric(pd.Series([row.get("emin")]), errors="coerce").iloc[0]
        emax = pd.to_numeric(pd.Series([row.get("emax")]), errors="coerce").iloc[0]
        spin = str(row.get("spin", "sum")).strip() or "sum"
        if not column or not elements or not orbitals or pd.isna(emin) or pd.isna(emax):
            continue
        integrations.append(
            {
                "column": column,
                "elements": elements,
                "orbitals": orbitals,
                "energy_window": [float(emin), float(emax)],
                "spin": spin,
            }
        )
    return integrations


def gas_reference_mapping_from_table(table: pd.DataFrame) -> dict[str, float]:
    mapping: dict[str, float] = {}
    if table is None or table.empty:
        return mapping
    for row in table.to_dict("records"):
        species = str(row.get("species", "")).strip()
        value = pd.to_numeric(pd.Series([row.get("energy_eV")]), errors="coerce").iloc[0]
        if species and pd.notna(value):
            mapping[species] = float(value)
    return mapping


def adsorption_recipes_from_table(table: pd.DataFrame) -> dict[str, dict[str, object]]:
    recipes: dict[str, dict[str, object]] = {}
    if table is None or table.empty:
        return recipes
    excluded = {"adsorbate", "basis"}
    for row in table.to_dict("records"):
        adsorbate = str(row.get("adsorbate", "")).strip()
        basis = str(row.get("basis", "C")).strip() or "C"
        if not adsorbate:
            continue
        gas_refs: dict[str, float] = {}
        for key, value in row.items():
            if key in excluded:
                continue
            numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
            if pd.notna(numeric) and float(numeric) != 0.0:
                gas_refs[str(key)] = float(numeric)
        if gas_refs:
            recipes[adsorbate] = {"basis": basis, "gas_refs": gas_refs}
    return recipes
