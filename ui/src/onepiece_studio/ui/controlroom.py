"""Filter page: build the active database view from the loaded rows.

This module only renders. Filter application lives in
:func:`onepiece_studio.adapters.apply_controlroom_filters`; the pure
computation helpers (notebook commands, widget option discovery, display
shaping) live in :mod:`onepiece_studio.filter_logic`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from onepiece.adsorption import get_all_elements
from onepiece.services import (
    filter_text,
    query_description,
    row_atom_counts,
    row_element_counts,
)
from onepiece_studio.adapters import (
    apply_controlroom_filters,
    ensure_controlroom_state,
)
from onepiece_studio.filter_logic import (
    clamp_float,
    display_command_frame,
    facet_columns,
    finite_values,
    materials_property_columns,
    name_options,
    numeric_filter_columns,
    quality_flag_options,
    record_type_options,
    run_command,
    status_table,
)
from onepiece_studio.state import (
    CONTROL_DROP_CONVERGENCE,
    CONTROL_DROP_TEST,
    CONTROL_FMAX_MAX,
    CONTROL_MATERIAL_QUERY,
    CONTROL_NUMERIC,
    CONTROL_SELECTED_FACETS,
    CONTROL_STATUS,
    CONTROL_TEXT_EXCLUDE,
    CONTROL_TEXT_INCLUDE,
    CONTROL_USE_STATUS,
    CONTROL_VISIBLE_STATES,
    CONTROLROOM_ACTIVE_DATAFRAME,
)
from onepiece_studio.ui.row_actions import (
    render_action_grid,
    selected_dataframe_index,
    selected_row_summary,
)

# Compatibility aliases: tests and scripts import these helpers from this
# module even though the implementations moved to the split-out modules.
__all__ = [
    "ControlroomResult",
    "apply_controlroom_filters",
    "render_controlroom",
    "_apply_controlroom_filters",
    "_available_elements",
    "_clamp_float",
    "_filter_text",
]

_apply_controlroom_filters = apply_controlroom_filters
_available_elements = get_all_elements
_clamp_float = clamp_float
_filter_text = filter_text


@dataclass(frozen=True, slots=True)
class ControlroomResult:
    dataframe: pd.DataFrame
    summary: dict[str, Any]


def render_controlroom(st: Any, dataframe: pd.DataFrame) -> ControlroomResult:
    ensure_controlroom_state(st, dataframe)

    st.subheader("Filter")
    st.caption(
        "Build the active database view from your rows. "
        "The resulting selection is used by Records, Visualize, and Analyze."
    )

    left, right = st.columns([0.34, 0.66], gap="large")

    with left:
        _render_filter_presets(st, dataframe)
        _render_inclusion_editor(st, dataframe)
        _render_name_filters(st)
        _render_materials_search(st, dataframe)
        _render_domain_filters(st, dataframe)
        _render_numeric_controls(st, dataframe)

    active = apply_controlroom_filters(st, dataframe)
    with right:
        _render_control_summary(st, dataframe, active)
        _render_commands(st, active)
        _render_preview(st, active)

    return ControlroomResult(
        dataframe=active,
        summary={"rows": len(active), "total_rows": len(dataframe)},
    )


def _render_filter_presets(st: Any, dataframe: pd.DataFrame) -> None:
    st.markdown("**Filter presets**")
    preset_columns = st.columns(2)
    if preset_columns[0].button("All rows", width="stretch"):
        _reset_filters(st)
    if preset_columns[1].button("Surface rows", width="stretch"):
        _set_text_filter(st, include="surf surface slab hkl 100 110 111 211")
    if preset_columns[0].button("Clean refs", width="stretch"):
        _set_text_filter(st, include="clean", exclude="adsorbate convergence test")
    if preset_columns[1].button("Ga rows", width="stretch"):
        _set_text_filter(st, include="Ga")
    if "fmax" in dataframe.columns and preset_columns[0].button("fmax ok", width="stretch"):
        st.session_state[CONTROL_FMAX_MAX] = 0.05
    if preset_columns[1].button("Needs review", width="stretch"):
        _set_status_filter(st, ["review"])


def _render_inclusion_editor(st: Any, dataframe: pd.DataFrame) -> None:
    with st.expander("Inclusion states", expanded=True):
        st.checkbox(
            "Use inclusion state",
            key=CONTROL_USE_STATUS,
            help="Rows marked excluded are removed from the active view.",
        )
        st.multiselect(
            "Visible states",
            ["included", "review", "reference", "excluded"],
            default=st.session_state.get(
                CONTROL_VISIBLE_STATES, ["included", "review", "reference"]
            ),
            key=CONTROL_VISIBLE_STATES,
        )
        row_options = name_options(dataframe)
        selected = st.selectbox("Mark row", [""] + row_options, index=0)
        new_state = st.segmented_control(
            "Set state",
            ["included", "review", "reference", "excluded"],
            default="included",
        )
        if st.button("Apply state", disabled=not selected, width="stretch"):
            key = selected.split(" | ", 1)[0]
            st.session_state[CONTROL_STATUS][key] = new_state

        states = status_table(st.session_state.get(CONTROL_STATUS, {}), dataframe)
        if not states.empty:
            st.dataframe(states, hide_index=True, width="stretch", height=180)


def _render_name_filters(st: Any) -> None:
    with st.expander("Name / text filters", expanded=True):
        st.text_input(
            "Include text",
            key=CONTROL_TEXT_INCLUDE,
            placeholder="e.g. Cu-211 Ga clean",
        )
        st.text_input(
            "Exclude text",
            key=CONTROL_TEXT_EXCLUDE,
            placeholder="e.g. convergence test broken",
        )


def _render_materials_search(st: Any, dataframe: pd.DataFrame) -> None:
    with st.expander("Materials Search", expanded=True):
        st.caption(
            "Structured local search inspired by Materials Project and OQMD: formula, "
            "chemical system, element sets, composition size, structure size and "
            "property windows."
        )
        query = st.session_state.setdefault(CONTROL_MATERIAL_QUERY, {})
        elements = get_all_elements(dataframe)

        formula_col, chemsys_col = st.columns(2)
        query["formula"] = formula_col.text_input(
            "Formula contains",
            value=query.get("formula", ""),
            placeholder="e.g. Ni3Ga, CO, CH3O",
            key="onepiece_studio_material_formula",
        )
        query["anonymous_formula"] = formula_col.text_input(
            "Anonymous formula",
            value=query.get("anonymous_formula", ""),
            placeholder="e.g. AB, A2B3, AB2",
            help="Formula pattern with element identities removed. Example: Ni3Ga -> AB3.",
            key="onepiece_studio_material_anonymous_formula",
        )
        query["chemsys"] = chemsys_col.text_input(
            "Chemical system",
            value=query.get("chemsys", ""),
            placeholder="e.g. Ni-Ga-O or C-H-O",
            help="Use '-' or spaces between elements.",
            key="onepiece_studio_material_chemsys",
        )
        query["chemsys_mode"] = chemsys_col.segmented_control(
            "Chemical system mode",
            ["contains all", "exact"],
            default=query.get("chemsys_mode", "contains all"),
            key="onepiece_studio_material_chemsys_mode",
        )

        element_col, exclude_col = st.columns(2)
        query["include_elements"] = element_col.multiselect(
            "Required / optional elements",
            elements,
            default=[element for element in query.get("include_elements", []) if element in elements],
            key="onepiece_studio_material_include_elements",
        )
        query["element_mode"] = element_col.segmented_control(
            "Element mode",
            ["all", "any", "exact"],
            default=query.get("element_mode", "all"),
            help="all = every selected element must appear; any = at least one; exact = only selected elements.",
            key="onepiece_studio_material_element_mode",
        )
        query["exclude_elements"] = exclude_col.multiselect(
            "Exclude elements",
            elements,
            default=[element for element in query.get("exclude_elements", []) if element in elements],
            key="onepiece_studio_material_exclude_elements",
        )
        query["record_types"] = exclude_col.multiselect(
            "Record classes",
            record_type_options(dataframe),
            default=query.get("record_types", []),
            key="onepiece_studio_material_record_types",
        )

        size_cols = st.columns(3)
        element_counts = row_element_counts(dataframe)
        min_elements = int(max(0, element_counts.min())) if not dataframe.empty else 0
        max_elements = int(max(element_counts.max(), min_elements)) if not dataframe.empty else 0
        if max_elements > min_elements:
            default_nelements = query.get("nelements", (min_elements, max_elements))
            query["nelements"] = size_cols[0].slider(
                "Number of elements",
                min_value=min_elements,
                max_value=max_elements,
                value=(
                    max(min_elements, min(int(default_nelements[0]), max_elements)),
                    max(min_elements, min(int(default_nelements[1]), max_elements)),
                ),
                key="onepiece_studio_material_nelements",
            )
        else:
            query["nelements"] = None
            size_cols[0].info("Only one element count available.")

        atom_counts = row_atom_counts(dataframe)
        if atom_counts.notna().any():
            min_atoms = int(max(1, atom_counts.dropna().min()))
            max_atoms = int(max(min_atoms, atom_counts.dropna().max()))
            if max_atoms > min_atoms:
                default_natoms = query.get("natoms", (min_atoms, max_atoms))
                query["natoms"] = size_cols[1].slider(
                    "Number of atoms",
                    min_value=min_atoms,
                    max_value=max_atoms,
                    value=(
                        max(min_atoms, min(int(default_natoms[0]), max_atoms)),
                        max(min_atoms, min(int(default_natoms[1]), max_atoms)),
                    ),
                    key="onepiece_studio_material_natoms",
                )
            else:
                query["natoms"] = None
                size_cols[1].info(f"Atom count fixed at {min_atoms}.")
        else:
            query["natoms"] = None
            size_cols[1].info("No atom-count information.")

        quality_options = quality_flag_options(dataframe)
        query["quality_flags"] = size_cols[2].multiselect(
            "Quality flags",
            quality_options,
            default=[flag for flag in query.get("quality_flags", []) if flag in quality_options],
            key="onepiece_studio_material_quality_flags",
        )

        property_columns = materials_property_columns(dataframe)
        query["property_columns"] = st.multiselect(
            "Property windows",
            property_columns,
            default=[column for column in query.get("property_columns", []) if column in property_columns],
            help="Range-filter numeric fields such as energy above hull, formation energy, fmax, band gap, atom counts, etc.",
            key="onepiece_studio_material_property_columns",
        )
        property_ranges = query.get("property_ranges", {})
        updated_ranges = {}
        for column in query["property_columns"]:
            finite = finite_values(pd.to_numeric(dataframe[column], errors="coerce"))
            if finite.empty or finite.min() == finite.max():
                continue
            default = property_ranges.get(column, (float(finite.min()), float(finite.max())))
            updated_ranges[column] = st.slider(
                f"{column} range",
                min_value=float(finite.min()),
                max_value=float(finite.max()),
                value=(
                    max(float(finite.min()), min(float(default[0]), float(finite.max()))),
                    max(float(finite.min()), min(float(default[1]), float(finite.max()))),
                ),
                key=f"onepiece_studio_material_property_{column}",
            )
        query["property_ranges"] = updated_ranges

        st.code(query_description(query), language="text")


def _render_domain_filters(st: Any, dataframe: pd.DataFrame) -> None:
    with st.expander("Materials facets", expanded=True):
        selected: dict[str, list[str]] = {}
        for column in facet_columns(dataframe):
            options = sorted(dataframe[column].dropna().astype(str).unique().tolist())
            current = st.session_state[CONTROL_SELECTED_FACETS].get(column, [])
            selected[column] = st.multiselect(column, options, default=current)
        st.session_state[CONTROL_SELECTED_FACETS] = selected

        st.checkbox("Hide convergence calculations by name", key=CONTROL_DROP_CONVERGENCE)
        st.checkbox("Hide test calculations by name", key=CONTROL_DROP_TEST)


def _render_numeric_controls(st: Any, dataframe: pd.DataFrame) -> None:
    with st.expander("Numeric filters", expanded=False):
        if "fmax" in dataframe.columns and pd.api.types.is_numeric_dtype(dataframe["fmax"]):
            finite = finite_values(dataframe["fmax"])
            if not finite.empty:
                default_value = clamp_float(
                    st.session_state.get(CONTROL_FMAX_MAX),
                    minimum=float(finite.min()),
                    maximum=float(finite.max()),
                    fallback=float(finite.max()),
                )
                value = st.number_input(
                    "Maximum fmax",
                    min_value=float(finite.min()),
                    max_value=float(finite.max()),
                    value=default_value,
                    step=0.01,
                )
                st.session_state[CONTROL_FMAX_MAX] = value

        numeric_columns = numeric_filter_columns(dataframe)
        selected = st.multiselect(
            "Additional numeric columns",
            numeric_columns,
            default=list(st.session_state[CONTROL_NUMERIC].keys()),
        )
        numeric_state: dict[str, tuple[float, float]] = {}
        for column in selected:
            finite = finite_values(dataframe[column])
            if finite.empty or finite.min() == finite.max():
                continue
            default = st.session_state[CONTROL_NUMERIC].get(
                column, (float(finite.min()), float(finite.max()))
            )
            numeric_state[column] = st.slider(
                column,
                min_value=float(finite.min()),
                max_value=float(finite.max()),
                value=(
                    max(float(finite.min()), float(default[0])),
                    min(float(finite.max()), float(default[1])),
                ),
            )
        st.session_state[CONTROL_NUMERIC] = numeric_state


def _render_control_summary(st: Any, source: pd.DataFrame, active: pd.DataFrame) -> None:
    top = st.columns(2, gap="small")
    bottom = st.columns(2, gap="small")
    top[0].metric("Active rows", f"{len(active):,}")
    top[1].metric("Total rows", f"{len(source):,}")
    bottom[0].metric("Hidden rows", f"{len(source) - len(active):,}")
    if "dataset" in active.columns:
        bottom[1].metric("Datasets", f"{active['dataset'].nunique():,}")
    else:
        bottom[1].metric("Columns", f"{active.shape[1]:,}")

    if "dataset" in active.columns:
        counts = active["dataset"].astype(str).value_counts().rename_axis("dataset").reset_index(name="rows")
        st.dataframe(counts, hide_index=True, width="stretch", height=220)


def _render_commands(st: Any, dataframe: pd.DataFrame) -> None:
    st.markdown("**Notebook commands**")
    command = st.selectbox(
        "Select command",
        [
            "Show active DataFrame",
            "Top low-energy candidates",
            "Find clean reference rows",
            "Find adsorption-like rows",
            "Find quality problems",
            "Phase-diagram candidate table",
            "Column focus review",
            "Column context table",
            "Export active rows",
        ],
    )

    result = run_command(command, dataframe)
    if command == "Export active rows":
        csv = dataframe.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download active rows as CSV",
            csv,
            file_name="onepiece_studio_controlroom_active_rows.csv",
            mime="text/csv",
            width="stretch",
        )
    else:
        command_height = 520 if command == "Show active DataFrame" else 300
        display = display_command_frame(result)
        event = st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            height=command_height,
            selection_mode="single-row",
            on_select="rerun",
            key=f"onepiece_studio_command_table_{command}",
        )
        selected_index = selected_dataframe_index(event, display)
        if selected_index is not None and selected_index in result.index:
            _render_row_actions(st, result.loc[selected_index], selected_index, key_prefix="command")


def _render_preview(st: Any, dataframe: pd.DataFrame) -> None:
    st.markdown("**Active DataFrame**")
    st.caption(f"{len(dataframe):,} active rows")
    display = display_command_frame(dataframe)
    event = st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        height=640,
        selection_mode="single-row",
        on_select="rerun",
        key=CONTROLROOM_ACTIVE_DATAFRAME,
    )
    selected_index = selected_dataframe_index(event, display)
    if selected_index is not None and selected_index in dataframe.index:
        _render_row_actions(st, dataframe.loc[selected_index], selected_index, key_prefix="active")


def _render_row_actions(st: Any, row: pd.Series, index: Any, *, key_prefix: str) -> None:
    st.markdown("**Selected calculation**")
    st.dataframe(selected_row_summary(row), hide_index=True, width="stretch")
    render_action_grid(st, row, index, key_prefix=key_prefix, namespace="onepiece_studio_control")


def _reset_filters(st: Any) -> None:
    st.session_state[CONTROL_TEXT_INCLUDE] = ""
    st.session_state[CONTROL_TEXT_EXCLUDE] = ""
    st.session_state[CONTROL_SELECTED_FACETS] = {}
    st.session_state[CONTROL_NUMERIC] = {}
    st.session_state[CONTROL_MATERIAL_QUERY] = {}
    st.session_state[CONTROL_FMAX_MAX] = None
    st.session_state[CONTROL_VISIBLE_STATES] = ["included", "review", "reference"]
    st.session_state[CONTROL_DROP_CONVERGENCE] = False
    st.session_state[CONTROL_DROP_TEST] = False


def _set_text_filter(st: Any, *, include: str = "", exclude: str = "") -> None:
    st.session_state[CONTROL_TEXT_INCLUDE] = include
    st.session_state[CONTROL_TEXT_EXCLUDE] = exclude


def _set_status_filter(st: Any, states: list[str]) -> None:
    st.session_state[CONTROL_VISIBLE_STATES] = states
