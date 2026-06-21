"""Rendering for the Workflow Builder "Add Operation" tab."""

from __future__ import annotations

from typing import Any

import pandas as pd

from onepiece.adsorption import structure_columns_in_frame
from onepiece_studio.ui.workflow_session import (
    append_operation,
    append_operations,
    workflow_gas_reference_values,
)
from onepiece_studio.workflow_logic import (
    FILTER_OPERATORS,
    NUMERIC_OPERATORS,
    sanitize_identifier,
    standard_operation_recipe,
    suggest_contains_name,
    suggest_derived_name_binary,
    suggest_derived_name_scalar,
    valid_new_column,
)


def render_add_operation(st: Any, dataframe: pd.DataFrame) -> None:
    operation_type = st.segmented_control(
        "Operation type",
        ["Standard operation", "Add derived column", "Filter rows", "Flag rows"],
        default="Standard operation",
    )

    if operation_type == "Standard operation":
        _render_standard_operation_builder(st, dataframe)
    elif operation_type == "Add derived column":
        _render_add_derived_column(st, dataframe)
    elif operation_type == "Filter rows":
        render_add_filter(st, dataframe, keep_as_flag=False)
    else:
        render_add_filter(st, dataframe, keep_as_flag=True)


def _render_standard_operation_builder(st: Any, dataframe: pd.DataFrame) -> None:
    st.markdown("**Standard operations**")
    st.caption(
        "Choose a ready-made workflow step for common chemistry tasks. The selected recipe is "
        "added to the pipeline as one or several reproducible operations."
    )
    recipe = st.selectbox(
        "Recipe",
        [
            "Assign surface references and adsorption columns",
            "Calculate CO adsorption energy per CO",
            "CO adsorption analysis starter",
            "Adsorption + Gibbs analysis starter",
            "Count all detected elements",
            "Bader/VASP charge descriptors",
            "ASE geometry, site and QC descriptors",
        ],
    )
    gas_refs = workflow_gas_reference_values(st, dataframe)
    has_co_reference = gas_refs.get("CO") is not None
    operations, description = standard_operation_recipe(recipe, gas_refs)
    st.info(description)
    if recipe != "Assign surface references and adsorption columns":
        if has_co_reference:
            st.caption(f"Current CO(g) reference: {gas_refs['CO']:.6f} eV")
        else:
            st.caption("No CO(g) reference found yet. `E_ads_CO_eV` will remain empty until one is available.")
    st.caption(f"This recipe will add {len(operations)} workflow step{'s' if len(operations) != 1 else ''}.")
    if st.button(
        "Add standard operation",
        width="stretch",
        disabled="Name" not in dataframe.columns or "E" not in dataframe.columns,
    ):
        append_operations(st, operations)
        st.rerun()


def _render_add_derived_column(st: Any, dataframe: pd.DataFrame) -> None:
    numeric_columns = [
        column for column in dataframe.columns if pd.api.types.is_numeric_dtype(dataframe[column])
    ]
    all_columns = list(dataframe.columns)
    mode = st.selectbox(
        "Derived column mode",
        [
            "Arithmetic from two numeric columns",
            "Numeric column and scalar",
            "Text contains flag",
            "Set constant value",
            "Fill missing values",
            "Normalize categorical values",
            "Count element into a column",
            "Count all elements into columns",
            "Group rank",
            "Adsorption-energy columns from dataset references",
            "Custom pandas expression",
        ],
    )
    new_column = st.text_input("New column name", placeholder="e.g. adsorption_energy")

    if mode == "Arithmetic from two numeric columns":
        operation, suggested_name = _build_binary_operation(st, new_column, numeric_columns)
    elif mode == "Numeric column and scalar":
        operation, suggested_name = _build_scalar_operation(st, dataframe, new_column, numeric_columns)
    elif mode == "Text contains flag":
        operation, suggested_name = _build_contains_operation(st, new_column, all_columns)
    elif mode == "Set constant value":
        operation, suggested_name = _build_constant_operation(st, new_column)
    elif mode == "Fill missing values":
        operation, suggested_name = _build_fill_missing_operation(st, all_columns)
    elif mode == "Normalize categorical values":
        operation, suggested_name = _build_replace_value_operation(st, all_columns)
    elif mode == "Count element into a column":
        operation, suggested_name = _build_count_element_operation(st, dataframe, new_column)
    elif mode == "Count all elements into columns":
        operation, suggested_name = _build_count_all_elements_operation(st, dataframe)
    elif mode == "Group rank":
        operation, suggested_name = _build_group_rank_operation(st, new_column, numeric_columns, all_columns)
    elif mode == "Adsorption-energy columns from dataset references":
        operation, suggested_name = _build_adsorption_columns_operation(st, dataframe)
    else:
        operation, suggested_name = _build_expression_operation(st, new_column)

    effective_name = new_column or suggested_name
    needs_new_column = operation is not None and operation.get("kind") not in {
        "fill_missing",
        "replace_value",
        "derive_adsorption_columns",
    }
    if not new_column and suggested_name:
        st.caption(f"Using suggested column name: `{suggested_name}`")
    if st.button("Add derived-column operation"):
        if operation is None:
            st.error("Operation is not ready yet.")
        elif needs_new_column and not valid_new_column(effective_name):
            st.error("Column names must start with a letter or underscore and may only contain letters, numbers, and underscores.")
        else:
            append_operation(st, operation)
            st.rerun()


def _build_binary_operation(
    st: Any, new_column: str, numeric_columns: list[str]
) -> tuple[dict[str, Any] | None, str]:
    col1, op_col, col2 = st.columns(3)
    left = col1.selectbox("Left column", numeric_columns)
    operator = op_col.selectbox("Operator", list(NUMERIC_OPERATORS))
    right = col2.selectbox("Right column", numeric_columns, index=min(1, len(numeric_columns) - 1))
    suggested_name = suggest_derived_name_binary(left, operator, right)
    operation = {
        "kind": "derive_binary",
        "new_column": new_column or suggested_name,
        "left": left,
        "operator": operator,
        "right": right,
        "label": f"{new_column or suggested_name} = {left} {operator} {right}",
    }
    return operation, suggested_name


def _build_scalar_operation(
    st: Any, dataframe: pd.DataFrame, new_column: str, numeric_columns: list[str]
) -> tuple[dict[str, Any] | None, str]:
    col1, op_col, preset_col, scalar_col = st.columns(4)
    left = col1.selectbox("Column", numeric_columns)
    operator = op_col.selectbox("Operator", list(NUMERIC_OPERATORS))
    gas_refs = workflow_gas_reference_values(st, dataframe)
    preset_values = {
        f"Gas phase: {label} ({value:.6f} eV)": float(value)
        for label, value in gas_refs.items()
        if value is not None
    }
    preset_options = ["Manual"] + list(preset_values)
    selected_preset = preset_col.selectbox("Scalar preset", preset_options)
    default_scalar = 1.0
    if selected_preset != "Manual":
        default_scalar = preset_values[selected_preset]
    scalar = scalar_col.number_input("Scalar", value=float(default_scalar))
    suggested_name = suggest_derived_name_scalar(left, operator, scalar)
    operation = {
        "kind": "derive_scalar",
        "new_column": new_column or suggested_name,
        "left": left,
        "operator": operator,
        "scalar": scalar,
        "scalar_preset": selected_preset,
        "label": f"{new_column or suggested_name} = {left} {operator} {scalar:g}",
    }
    return operation, suggested_name


def _build_contains_operation(
    st: Any, new_column: str, all_columns: list[str]
) -> tuple[dict[str, Any] | None, str]:
    col1, col2 = st.columns(2)
    column = col1.selectbox("Text column", all_columns)
    token = col2.text_input("Contains text", placeholder="clean")
    suggested_name = suggest_contains_name(column, token)
    operation = {
        "kind": "derive_contains",
        "new_column": new_column or suggested_name,
        "column": column,
        "token": token,
        "label": f"{new_column or suggested_name} = {column} contains {token!r}",
    }
    return operation, suggested_name


def _build_constant_operation(st: Any, new_column: str) -> tuple[dict[str, Any] | None, str]:
    col1, col2 = st.columns(2)
    constant_type = col1.selectbox("Value type", ["text", "number", "boolean"])
    if constant_type == "number":
        constant_value = col2.number_input("Constant value", value=0.0)
    elif constant_type == "boolean":
        constant_value = col2.checkbox("Constant value", value=True)
    else:
        constant_value = col2.text_input("Constant value", placeholder="e.g. MgOCu-")
    suggested_name = "constant_value"
    operation = {
        "kind": "derive_constant",
        "new_column": new_column or suggested_name,
        "value": constant_value,
        "label": f"{new_column or suggested_name} = constant {constant_value!r}",
    }
    return operation, suggested_name


def _build_fill_missing_operation(st: Any, all_columns: list[str]) -> tuple[dict[str, Any] | None, str]:
    col1, col2, col3 = st.columns(3)
    column = col1.selectbox("Column", all_columns)
    fill_kind = col2.selectbox("Fill with", ["text", "number", "boolean"])
    if fill_kind == "number":
        fill_value = col3.number_input("Fill value", value=0.0)
    elif fill_kind == "boolean":
        fill_value = col3.checkbox("Fill value", value=False)
    else:
        fill_value = col3.text_input("Fill value", placeholder="e.g. 0 or unknown")
    suggested_name = column
    operation = {
        "kind": "fill_missing",
        "column": column,
        "value": fill_value,
        "label": f"fill missing {column} with {fill_value!r}",
    }
    return operation, suggested_name


def _build_replace_value_operation(st: Any, all_columns: list[str]) -> tuple[dict[str, Any] | None, str]:
    col1, col2, col3 = st.columns(3)
    column = col1.selectbox("Column", all_columns)
    from_value = col2.text_input("From value", placeholder="e.g. CHO")
    to_value = col3.text_input("To value", placeholder="e.g. HCO")
    suggested_name = column
    operation = {
        "kind": "replace_value",
        "column": column,
        "from_value": from_value,
        "to_value": to_value,
        "label": f"replace {column}: {from_value!r} -> {to_value!r}",
    }
    return operation, suggested_name


def _build_count_element_operation(
    st: Any, dataframe: pd.DataFrame, new_column: str
) -> tuple[dict[str, Any] | None, str]:
    structure_columns = structure_columns_in_frame(dataframe)
    if not structure_columns:
        st.info("This mode needs at least one column containing ASE Atoms objects.")
        return None, ""
    col1, col2 = st.columns(2)
    element = col1.text_input("Element symbol", value="C", max_chars=3)
    structure_column = col2.selectbox("Structure source column", structure_columns)
    suggested_name = f"{element}_count"
    operation = {
        "kind": "count_element",
        "new_column": new_column or suggested_name,
        "element": element,
        "structure_column": structure_column,
        "label": f"{new_column or suggested_name} = count element {element} from {structure_column}",
    }
    return operation, suggested_name


def _build_count_all_elements_operation(
    st: Any, dataframe: pd.DataFrame
) -> tuple[dict[str, Any] | None, str]:
    structure_columns = structure_columns_in_frame(dataframe)
    if not structure_columns:
        st.info("This mode needs at least one column containing ASE Atoms objects.")
        return None, ""
    suggested_name = "all_element_count_columns"
    structure_column = st.selectbox("Structure source column", structure_columns, key="onepiece_studio_count_all_elements_structure_column")
    st.caption(
        "Detects all elements present in the current dataset and adds one count column per element "
        f"using `{structure_column}` as the ASE structure source."
    )
    operation = {
        "kind": "count_all_elements",
        "structure_column": structure_column,
        "label": f"count all detected elements from {structure_column} into columns",
    }
    return operation, suggested_name


def _build_group_rank_operation(
    st: Any, new_column: str, numeric_columns: list[str], all_columns: list[str]
) -> tuple[dict[str, Any] | None, str]:
    if not numeric_columns:
        st.info("This mode needs at least one numeric column.")
        return None, ""
    col1, col2, col3, col4 = st.columns(4)
    value_column = col1.selectbox("Rank values in", numeric_columns)
    candidate_groups = [column for column in all_columns if column != value_column]
    group_columns = col2.multiselect("Group by", candidate_groups, default=candidate_groups[:2] if candidate_groups else [])
    ascending = col3.checkbox("Ascending", value=True)
    method = col4.selectbox("Method", ["min", "dense", "first", "average", "max"])
    suggested_name = sanitize_identifier(f"{value_column}_rank")
    operation = {
        "kind": "group_rank",
        "new_column": new_column or suggested_name,
        "value_column": value_column,
        "group_columns": group_columns,
        "ascending": ascending,
        "method": method,
        "label": f"{new_column or suggested_name} = rank {value_column} by {group_columns or ['all rows']}",
    }
    return operation, suggested_name


def _build_adsorption_columns_operation(
    st: Any, dataframe: pd.DataFrame
) -> tuple[dict[str, Any] | None, str]:
    suggested_name = "adsorption_columns"
    gas_refs = workflow_gas_reference_values(st, dataframe)
    st.caption(
        "This operation assigns clean surface references from the current dataset and "
        "adds adsorption columns such as `surface_ref_name`, `surface_ref_E`, "
        "`delta_E_to_surface_eV`, and gas-dependent adsorption energies where possible."
    )
    operation = {
        "kind": "derive_adsorption_columns",
        "gas_references": gas_refs,
        "label": "derive adsorption-energy columns from dataset references",
    }
    return operation, suggested_name


def _build_expression_operation(st: Any, new_column: str) -> tuple[dict[str, Any] | None, str]:
    st.caption(
        "Expression can use DataFrame column names directly. Example: "
        "`E / n_atoms` or `form_G / Area`. Use only existing numeric columns."
    )
    expression = st.text_area("Expression", placeholder="E / n_atoms")
    suggested_name = "derived_expression"
    operation = {
        "kind": "derive_expression",
        "new_column": new_column or suggested_name,
        "expression": expression,
        "label": f"{new_column or suggested_name} = {expression}",
    }
    return operation, suggested_name


def render_add_filter(st: Any, dataframe: pd.DataFrame, *, keep_as_flag: bool) -> None:
    columns = list(dataframe.columns)
    col1, col2, col3 = st.columns([0.34, 0.28, 0.38])
    column = col1.selectbox("Column", columns)
    operator = col2.selectbox("Condition", FILTER_OPERATORS)
    value = ""
    if operator not in {"is empty", "is not empty"}:
        value = col3.text_input("Value", placeholder="Cu, 0.05, clean")
    flag_column = ""
    if keep_as_flag:
        flag_column = st.text_input("Flag column name", value=f"{column}_flag")
    label = (
        f"{'flag' if keep_as_flag else 'filter'} {column} {operator}"
        + (f" {value!r}" if value else "")
    )
    operation = {
        "kind": "flag_filter" if keep_as_flag else "filter",
        "column": column,
        "operator": operator,
        "value": value,
        "new_column": flag_column,
        "label": label,
    }
    if st.button("Add operation", disabled=keep_as_flag and not valid_new_column(flag_column)):
        append_operation(st, operation)
        st.rerun()
