from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from onepiece._polars import dataframe_is_polars_safe, get_polars
from onepiece.adsorption import (
    add_adsorption_energies,
    add_element_count_columns,
    add_elemental_adsorption_free_energy,
    add_recipe_adsorption_energies,
    assign_surface_references,
    count_element_in_structure,
    structure_columns_in_frame,
)
from onepiece.ase_analysis import add_ase_analysis_descriptors
from onepiece.automation import (
    add_structure_descriptors,
    annotate_reaction_network,
    apply_curation_rules,
)
from onepiece.dftdataframe_import import add_input_parameter_checks
from onepiece.ir import add_ir_peak_matches
from onepiece.provenance import workflow_activity
from onepiece.thermo import add_gibbs_free_energy
from onepiece.vasp import (
    add_adsorbate_charge_descriptors,
    add_projected_dos_descriptors,
)


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    dataframe: pd.DataFrame
    messages: list[str]
    audit_log: list[dict[str, Any]]


def apply_operations(dataframe: pd.DataFrame, operations: list[dict[str, Any]]) -> WorkflowResult:
    active = dataframe.copy()
    messages: list[str] = []
    audit_log: list[dict[str, Any]] = []
    for index, operation in enumerate(operations, start=1):
        if not operation.get("enabled", True):
            continue
        before = active
        input_entity = f"dataframe:step-{index - 1}"
        output_entity = f"dataframe:step-{index}"
        try:
            active = apply_operation(active, operation)
            audit_log.append(
                workflow_activity(
                    step_index=index,
                    operation=operation,
                    input_entity=input_entity,
                    output_entity=output_entity,
                    status="ok",
                    rows_before=len(before),
                    rows_after=len(active),
                    columns_before=[str(column) for column in before.columns],
                    columns_after=[str(column) for column in active.columns],
                )
            )
        except Exception as exc:
            error = f"Step {index} failed: {operation.get('label', operation.get('kind'))}: {exc}"
            messages.append(error)
            audit_log.append(
                workflow_activity(
                    step_index=index,
                    operation=operation,
                    input_entity=input_entity,
                    output_entity=output_entity,
                    status="failed",
                    rows_before=len(before),
                    rows_after=len(before),
                    columns_before=[str(column) for column in before.columns],
                    columns_after=[str(column) for column in before.columns],
                    error=error,
                )
            )
    return WorkflowResult(dataframe=active, messages=messages, audit_log=audit_log)


def apply_operation(dataframe: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    kind = str(operation.get("kind", ""))
    handler = _OPERATION_HANDLERS.get(kind)
    if handler is None:
        return dataframe.copy()
    return handler(dataframe.copy(), operation)


def _derive_binary(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    left = _numeric(df, operation["left"])
    right = _numeric(df, operation["right"])
    df[operation["new_column"]] = _apply_numeric_operator(left, right, operation["operator"])
    return df


def _derive_scalar(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    left = _numeric(df, operation["left"])
    scalar = float(operation["scalar"])
    df[operation["new_column"]] = _apply_numeric_operator(left, scalar, operation["operator"])
    return df


def _derive_contains(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    df[operation["new_column"]] = df[operation["column"]].astype(str).str.contains(
        str(operation.get("token", "")), case=False, na=False, regex=False
    )
    return df


def _derive_constant(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    df[operation["new_column"]] = operation.get("value")
    return df


def _fill_missing(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    df[operation["column"]] = df[operation["column"]].where(df[operation["column"]].notna(), operation.get("value"))
    return df


def _replace_value(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    df[operation["column"]] = df[operation["column"]].replace(operation.get("from_value"), operation.get("to_value"))
    return df


def _count_element(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    element = str(operation.get("element", "")).strip()
    structure_column = str(operation.get("structure_column", "")).strip()
    structure_columns = (
        (structure_column,)
        if structure_column
        else tuple(structure_columns_in_frame(df))
    )
    df[operation["new_column"]] = df.apply(
        lambda row: count_element_in_structure(row, element, structure_columns=structure_columns),
        axis=1,
    )
    return df


def _count_all_elements(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return add_element_count_columns(
        df,
        structure_column=str(operation.get("structure_column", "")).strip() or None,
    )


def _group_rank(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    value_column = operation["value_column"]
    group_columns = operation.get("group_columns") or []
    accelerated = _group_rank_with_polars(df, operation)
    if accelerated is not None:
        return accelerated
    rank_source = _numeric(df, value_column)
    if group_columns:
        df[operation["new_column"]] = rank_source.groupby(
            [df[column] for column in group_columns], dropna=False
        ).rank(
            method=str(operation.get("method", "min")),
            ascending=bool(operation.get("ascending", True)),
        )
    else:
        df[operation["new_column"]] = rank_source.rank(
            method=str(operation.get("method", "min")),
            ascending=bool(operation.get("ascending", True)),
        )
    return df


def _group_rank_with_polars(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame | None:
    pl = get_polars()
    value_column = str(operation.get("value_column", ""))
    group_columns = [str(column) for column in operation.get("group_columns") or []]
    new_column = str(operation.get("new_column", ""))
    if pl is None or not value_column or not new_column:
        return None
    needed_columns = [value_column, *group_columns]
    if any(column not in df.columns for column in needed_columns):
        return None
    if not dataframe_is_polars_safe(df, needed_columns):
        return None

    prepared = pd.DataFrame({"__rowid__": np.arange(len(df), dtype=np.int64)}, index=df.index)
    prepared[value_column] = pd.to_numeric(df[value_column], errors="coerce")
    for column in group_columns:
        prepared[column] = df[column]

    try:
        frame = pl.from_pandas(prepared, include_index=False)
    except Exception:
        return None

    method = str(operation.get("method", "min")).lower()
    polars_method = {"first": "ordinal"}.get(method, method)
    if polars_method not in {"min", "dense", "ordinal", "average", "max"}:
        return None
    rank_expr = pl.col(value_column).rank(
        method=polars_method,
        descending=not bool(operation.get("ascending", True)),
    )
    if group_columns:
        rank_expr = rank_expr.over(group_columns)

    try:
        ranked = frame.with_columns(rank_expr.alias(new_column)).sort("__rowid__").select(new_column).to_series().to_list()
    except Exception:
        return None
    result = df.copy()
    result[new_column] = ranked
    return result


def _derive_recipe_adsorption(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return add_recipe_adsorption_energies(
        assign_surface_references(df),
        operation.get("gas_reference_values"),
        operation.get("recipes"),
    )


def _derive_reaction_network(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return annotate_reaction_network(df)


def _derive_curation(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    action = str(operation.get("action", "exclude"))
    normalized_action = "exclude" if action == "exclude" else ("mark_excluded" if action == "mark_excluded" else "mark_review")
    return apply_curation_rules(
        df,
        static_fmax_max=float(operation.get("static_fmax_max", 0.05)),
        copt_fmax_max=float(operation.get("copt_fmax_max", 0.10)),
        exclude_name_tokens=[str(token) for token in operation.get("exclude_name_tokens", []) if str(token)],
        action=normalized_action,
    )


def _derive_structure_descriptors(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return add_structure_descriptors(df)


def _derive_vasp_charge_descriptors(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return add_adsorbate_charge_descriptors(
        df,
        charge_source=str(operation.get("charge_source", "acf")),
        acf_path_column=str(operation.get("acf_path_column", "acf_path")),
        chgcar_path_column=str(operation.get("chgcar_path_column", "chgcar_path")),
        calculation_path_column=str(operation.get("calculation_path_column", "Path")),
        structure_column=str(operation.get("structure_column", "struc")),
        acf_filename=str(operation.get("acf_filename", "ACF.dat")),
        filename=str(operation.get("filename", "CHGCAR")),
    )


def _derive_vasp_pdos_descriptors(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return add_projected_dos_descriptors(
        df,
        operation.get("integrations", []),
        doscar_path_column=str(operation.get("doscar_path_column", "doscar_path")),
        calculation_path_column=str(operation.get("calculation_path_column", "Path")),
        structure_column=str(operation.get("structure_column", "struc")),
        filename=str(operation.get("filename", "DOSCAR")),
    )


def _derive_ase_analysis_descriptors(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return add_ase_analysis_descriptors(
        df,
        structure_column=str(operation.get("structure_column", "struc")),
        include_pdos=bool(operation.get("include_pdos", False)),
        calculation_path_column=str(operation.get("calculation_path_column", "Path")),
        doscar_path_column=str(operation.get("doscar_path_column", "doscar_path")),
        dos_filename=str(operation.get("filename", "DOSCAR")),
    )


def _derive_input_parameter_checks(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return add_input_parameter_checks(
        df,
        encut_column=str(operation.get("encut_column", "input_encut")),
        kpoints_grid_column=str(operation.get("kpoints_grid_column", "input_kpoints_grid")),
    )


def _derive_ir_peak_matches(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return add_ir_peak_matches(
        df,
        tolerance_cm1=float(operation.get("tolerance_cm1", 30.0)),
        frequency_column=str(operation.get("frequency_column", "frequencies_cm1")),
        species_column=str(operation.get("species_column", "adsorbate")),
        references=operation.get("references"),
    )


def _exclude_exact_names(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    column = str(operation.get("column", "Name"))
    names = [str(name) for name in operation.get("names", []) if str(name)]
    if names:
        df = df[~df[column].astype(str).isin(names)]
    return df


def _exclude_by_match_rules(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    column = str(operation.get("column", "Name"))
    rules = operation.get("rules", []) or []
    if rules:
        text = df[column].astype(str)
        exclude_mask = pd.Series(False, index=df.index)
        for rule in rules:
            pattern = str(rule.get("pattern", "")).strip()
            match_mode = str(rule.get("match_mode", "exact")).strip().lower()
            if not pattern:
                continue
            if match_mode == "contains":
                exclude_mask = exclude_mask | text.str.contains(pattern, case=False, na=False, regex=False)
            elif match_mode == "regex":
                exclude_mask = exclude_mask | text.str.contains(pattern, case=False, na=False, regex=True)
            else:
                exclude_mask = exclude_mask | (text == pattern)
        df = df[~exclude_mask]
    return df


def _derive_adsorption_columns(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return add_adsorption_energies(
        assign_surface_references(df),
        _normalized_gas_references(operation.get("gas_references")),
    )


def _derive_gibbs_free_energy(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return add_gibbs_free_energy(
        df,
        temperature=float(operation.get("temperature", 298.15)),
        energy_column=str(operation.get("energy_column", "E")),
        output_column=str(operation.get("output_column", "G")),
    )


def _derive_gibbs_adsorption(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return add_elemental_adsorption_free_energy(
        df,
        _normalized_gas_references(operation.get("gas_references")),
        temperature=float(operation.get("temperature", 298.15)),
        energy_column=str(operation.get("energy_column", "E")),
        gibbs_column=str(operation.get("gibbs_column", "G")),
        output_column=str(operation.get("output_column", "adsorption_free_energy")),
    )


def _derive_expression(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    df[operation["new_column"]] = _evaluate_expression(df, str(operation.get("expression", "")))
    return df


def _filter_rows(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return df[_filter_mask(df, operation)]


def _flag_filter(df: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    df[operation["new_column"]] = _filter_mask(df, operation)
    return df


_OPERATION_HANDLERS = {
    "derive_binary": _derive_binary,
    "derive_scalar": _derive_scalar,
    "derive_contains": _derive_contains,
    "derive_constant": _derive_constant,
    "fill_missing": _fill_missing,
    "replace_value": _replace_value,
    "count_element": _count_element,
    "count_all_elements": _count_all_elements,
    "group_rank": _group_rank,
    "derive_recipe_adsorption": _derive_recipe_adsorption,
    "derive_reaction_network": _derive_reaction_network,
    "derive_curation": _derive_curation,
    "derive_structure_descriptors": _derive_structure_descriptors,
    "derive_ase_analysis_descriptors": _derive_ase_analysis_descriptors,
    "derive_input_parameter_checks": _derive_input_parameter_checks,
    "derive_ir_peak_matches": _derive_ir_peak_matches,
    "derive_vasp_charge_descriptors": _derive_vasp_charge_descriptors,
    "derive_vasp_pdos_descriptors": _derive_vasp_pdos_descriptors,
    "exclude_exact_names": _exclude_exact_names,
    "exclude_by_match_rules": _exclude_by_match_rules,
    "derive_adsorption_columns": _derive_adsorption_columns,
    "derive_gibbs_free_energy": _derive_gibbs_free_energy,
    "derive_gibbs_adsorption": _derive_gibbs_adsorption,
    "derive_expression": _derive_expression,
    "filter": _filter_rows,
    "flag_filter": _flag_filter,
}


def _apply_numeric_operator(left: Any, right: Any, operator: str) -> Any:
    if operator == "+":
        return left + right
    if operator == "-":
        return left - right
    if operator == "*":
        return left * right
    if operator == "/":
        return left / right
    raise ValueError(f"Unsupported operator: {operator}")


def _filter_mask(df: pd.DataFrame, operation: dict[str, Any]) -> pd.Series:
    column = operation["column"]
    operator = operation["operator"]
    value = operation.get("value", "")
    series = df[column]
    if operator == "contains":
        return series.astype(str).str.contains(str(value), case=False, na=False, regex=False)
    if operator == "not contains":
        return ~series.astype(str).str.contains(str(value), case=False, na=False, regex=False)
    if operator == "equals":
        numeric = pd.to_numeric(series, errors="coerce")
        threshold = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.notna(threshold) and numeric.notna().any():
            return numeric == float(threshold)
        return series.astype(str) == str(value)
    if operator == "not equals":
        numeric = pd.to_numeric(series, errors="coerce")
        threshold = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.notna(threshold) and numeric.notna().any():
            return numeric != float(threshold)
        return series.astype(str) != str(value)
    if operator == "is not empty":
        return series.notna() & (series.astype(str) != "")
    if operator == "is empty":
        return series.isna() | (series.astype(str) == "")

    numeric = pd.to_numeric(series, errors="coerce")
    threshold = float(value)
    if operator == ">":
        return numeric > threshold
    if operator == ">=":
        return numeric >= threshold
    if operator == "<":
        return numeric < threshold
    if operator == "<=":
        return numeric <= threshold
    raise ValueError(f"Unsupported filter operator: {operator}")


def _evaluate_expression(df: pd.DataFrame, expression: str) -> pd.Series:
    if not expression.strip():
        raise ValueError("Expression is empty.")
    allowed_names = {
        column: pd.to_numeric(df[column], errors="coerce")
        for column in df.columns
        if _valid_identifier(column)
    }
    allowed_names.update({"np": np})
    return pd.eval(expression, local_dict=allowed_names, engine="python")


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(df[column], errors="coerce")


def _valid_identifier(name: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(name)))


def _normalized_gas_references(values: dict[str, float | None] | None) -> dict[str, float] | None:
    if values is None:
        return None
    normalized: dict[str, float] = {}
    for key, value in values.items():
        try:
            normalized[key] = float(value) if value is not None else float("nan")
        except (TypeError, ValueError):
            normalized[key] = float("nan")
    return normalized
