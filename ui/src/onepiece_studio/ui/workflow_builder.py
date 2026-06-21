"""Workflow Builder page: pipeline overview, operation tabs, and preview.

Rendering for the individual tabs lives in
:mod:`onepiece_studio.ui.workflow_steps` (Add Operation) and
:mod:`onepiece_studio.ui.workflow_automation` (Notebook Automation);
pure computation lives in :mod:`onepiece_studio.workflow_logic`.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from onepiece.workflows import WorkflowResult, apply_operations
from onepiece.workflows import apply_operation as backend_apply_operation
from onepiece_studio.state import WORKFLOW_OPERATIONS
from onepiece_studio.ui.workflow_automation import render_notebook_automation
from onepiece_studio.ui.workflow_session import (
    init_workflow_state,
)
from onepiece_studio.ui.workflow_session import (
    workflow_gas_reference_values as _workflow_gas_reference_values,
)
from onepiece_studio.ui.workflow_steps import render_add_operation
from onepiece_studio.workflow_logic import (
    WORKFLOW_GAS_LABELS,
)
from onepiece_studio.workflow_logic import (
    adsorption_recipes_from_table as _adsorption_recipes_from_table,
)
from onepiece_studio.workflow_logic import (
    column_index as _column_index,
)
from onepiece_studio.workflow_logic import (
    default_drop_rules_table as _default_drop_rules_table,
)
from onepiece_studio.workflow_logic import (
    default_gas_reference_table as _default_gas_reference_table,
)
from onepiece_studio.workflow_logic import (
    default_normalization_table as _default_normalization_table,
)
from onepiece_studio.workflow_logic import (
    default_recipe_table as _default_recipe_table,
)
from onepiece_studio.workflow_logic import (
    display_preview as _display_preview,
)
from onepiece_studio.workflow_logic import (
    drop_rules_from_table as _drop_rules_from_table,
)
from onepiece_studio.workflow_logic import (
    gas_reference_mapping_from_table as _gas_reference_mapping_from_table,
)
from onepiece_studio.workflow_logic import (
    normalization_pairs_from_table as _normalization_pairs_from_table,
)
from onepiece_studio.workflow_logic import (
    standard_operation_recipe as _standard_operation_recipe,
)
from onepiece_studio.workflow_logic import (
    suggest_contains_name as _suggest_contains_name,
)
from onepiece_studio.workflow_logic import (
    suggest_derived_name_binary as _suggest_derived_name_binary,
)
from onepiece_studio.workflow_logic import (
    suggest_derived_name_scalar as _suggest_derived_name_scalar,
)
from onepiece_studio.workflow_logic import (
    valid_new_column as _valid_new_column,
)

# Compatibility aliases: tests and scripts import these helpers from this
# module even though the implementations moved to the split-out modules.
__all__ = [
    "WORKFLOW_GAS_LABELS",
    "apply_workflow_operations",
    "render_workflow_builder",
    "_adsorption_recipes_from_table",
    "_apply_operation",
    "_column_index",
    "_default_drop_rules_table",
    "_default_gas_reference_table",
    "_default_normalization_table",
    "_default_recipe_table",
    "_display_preview",
    "_drop_rules_from_table",
    "_gas_reference_mapping_from_table",
    "_normalization_pairs_from_table",
    "_standard_operation_recipe",
    "_suggest_contains_name",
    "_suggest_derived_name_binary",
    "_suggest_derived_name_scalar",
    "_valid_new_column",
    "_workflow_gas_reference_values",
]


def apply_workflow_operations(st: Any, dataframe: pd.DataFrame) -> WorkflowResult:
    operations = st.session_state.get(WORKFLOW_OPERATIONS, [])
    return apply_operations(dataframe, operations)


def render_workflow_builder(st: Any, source: pd.DataFrame, active: pd.DataFrame, messages: list[str]) -> None:
    init_workflow_state(st)
    st.subheader("Workflow Builder")
    st.caption(
        "Build a local data-flow pipeline before Controlroom filtering: add derived columns, "
        "filter rows, and keep the operations reproducible."
    )

    if messages:
        for message in messages:
            st.warning(message)

    _render_pipeline_metrics(st, source, active)
    _render_beginner_guidance(st, active)

    add_tab, automation_tab, pipeline_tab, preview_tab = st.tabs(
        ["Add Operation", "Notebook Automation", "Pipeline", "Preview"]
    )
    with add_tab:
        render_add_operation(st, active)
    with automation_tab:
        render_notebook_automation(st, active)
    with pipeline_tab:
        _render_pipeline(st)
    with preview_tab:
        _render_preview(st, source, active)


def _render_pipeline_metrics(st: Any, source: pd.DataFrame, active: pd.DataFrame) -> None:
    top = st.columns(2, gap="small")
    bottom = st.columns(2, gap="small")
    top[0].metric("Input rows", f"{len(source):,}")
    top[1].metric("Output rows", f"{len(active):,}")
    bottom[0].metric("Input columns", f"{source.shape[1]:,}")
    bottom[1].metric("Output columns", f"{active.shape[1]:,}")


def _render_beginner_guidance(st: Any, dataframe: pd.DataFrame) -> None:
    operations = st.session_state.get(WORKFLOW_OPERATIONS, [])
    if dataframe.empty:
        st.info(
            "Start by loading an HDF file or the bundled tutorial dataset from Data Sources. "
            "Once rows are present, this tab can add adsorption, Gibbs, charge, and geometry workflows."
        )
        return
    if operations:
        return
    with st.container(border=True):
        st.markdown("**Suggested first workflow**")
        st.caption(
            "For a first-day catalysis workflow, a good sequence is: "
            "1) assign adsorption references, 2) add Gibbs energies if thermo data exists, "
            "3) add charge or geometry descriptors, 4) inspect the results in Visualize."
        )
        suggestions = [
            "CO adsorption analysis starter",
            "Adsorption + Gibbs analysis starter",
            "Bader/VASP charge descriptors",
            "ASE geometry, site and QC descriptors",
        ]
        st.caption("Ready-made recipes available below: " + ", ".join(f"`{item}`" for item in suggestions))


def _render_pipeline(st: Any) -> None:
    operations = st.session_state.get(WORKFLOW_OPERATIONS, [])
    if not operations:
        st.info("No workflow operations yet.")
        return

    rows = []
    for index, operation in enumerate(operations):
        rows.append(
            {
                "step": index + 1,
                "enabled": operation.get("enabled", True),
                "kind": operation.get("kind", ""),
                "label": operation.get("label", ""),
                "created_at": operation.get("created_at", ""),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    selected = st.number_input("Step", min_value=1, max_value=len(operations), value=1, step=1)
    index = int(selected) - 1
    controls = st.columns(5)
    if controls[0].button("Toggle enabled", width="stretch"):
        operations[index]["enabled"] = not operations[index].get("enabled", True)
        st.rerun()
    if controls[1].button("Move up", width="stretch", disabled=index == 0):
        operations[index - 1], operations[index] = operations[index], operations[index - 1]
        st.rerun()
    if controls[2].button("Move down", width="stretch", disabled=index == len(operations) - 1):
        operations[index + 1], operations[index] = operations[index], operations[index + 1]
        st.rerun()
    if controls[3].button("Delete step", width="stretch"):
        operations.pop(index)
        st.rerun()
    if controls[4].button("Clear all", width="stretch"):
        st.session_state[WORKFLOW_OPERATIONS] = []
        st.rerun()

    st.download_button(
        "Download workflow JSON",
        pd.Series(operations).to_json(indent=2).encode("utf-8"),
        file_name="onepiece_studio_workflow.json",
        mime="application/json",
    )


def _render_preview(st: Any, source: pd.DataFrame, active: pd.DataFrame) -> None:
    st.markdown("**Data-flow preview**")
    st.caption("The table below is the DataFrame after workflow operations, before Controlroom filters.")
    st.dataframe(_display_preview(active.head(120)), hide_index=True, width="stretch", height=520)

    st.markdown("**Columns created by workflow**")
    created = [
        op.get("new_column")
        for op in st.session_state.get(WORKFLOW_OPERATIONS, [])
        if op.get("new_column") in active.columns and op.get("new_column") not in source.columns
    ]
    if created:
        overview = []
        for column in created:
            series = active[column]
            overview.append(
                {
                    "column": column,
                    "dtype": str(series.dtype),
                    "non_null": int(series.notna().sum()),
                    "sample": repr(series.dropna().iloc[0])[:120] if series.notna().any() else "",
                }
            )
        st.dataframe(pd.DataFrame(overview), hide_index=True, width="stretch")
    else:
        st.info("No workflow-created columns yet.")


def _apply_operation(dataframe: pd.DataFrame, operation: dict[str, Any]) -> pd.DataFrame:
    return backend_apply_operation(dataframe, operation)
