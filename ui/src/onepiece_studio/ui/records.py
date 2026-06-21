from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from onepiece_studio.config import OnePieceStudioConfig
from onepiece_studio.images import resolve_image
from onepiece_studio.materials_columns import columns_for_profile, profile_names
from onepiece_studio.schema import ColumnKind
from onepiece_studio.state import PAGE_SIZE
from onepiece_studio.ui.row_actions import is_atoms, open_atoms_in_ase, render_action_grid


def render_records(
    st: Any,
    filtered: pd.DataFrame,
    full_dataframe: pd.DataFrame,
    schema: list[Any],
    config: OnePieceStudioConfig,
) -> None:
    """Render the Records page: metrics, paged table, and the detail panel."""
    _render_metrics(st, filtered, config)
    table_column, detail_column = st.columns([0.68, 0.32], gap="large")
    with table_column:
        st.subheader("Filtered Records")
        selected_index = _render_table(st, filtered, config, total_rows=len(full_dataframe))

    with detail_column:
        st.subheader("Record detail")
        if selected_index is None and not filtered.empty:
            selected_index = filtered.index[0]
        if selected_index is not None:
            selected_row = full_dataframe.loc[selected_index]
            if isinstance(selected_row, pd.DataFrame):
                # Duplicate index labels return a frame; show the first match.
                selected_row = selected_row.iloc[0]
            _render_detail(st, selected_row, schema, config)
        else:
            st.info("No record selected.")


def _render_metrics(st: Any, dataframe: pd.DataFrame, config: OnePieceStudioConfig) -> None:
    metric_columns = [
        column
        for column in config.metric_columns
        if column in dataframe.columns and pd.api.types.is_numeric_dtype(dataframe[column])
    ][:4]
    if not metric_columns:
        return

    rows = [st.columns(2, gap="small"), st.columns(2, gap="small")]
    slots = [column for row in rows for column in row]
    for widget_column, column in zip(slots, metric_columns, strict=False):
        finite = dataframe[column].replace([np.inf, -np.inf], np.nan).dropna()
        value = f"{finite.mean():.3g}" if not finite.empty else "n/a"
        widget_column.metric(column, value, help="Mean of filtered rows")


def _render_table(
    st: Any,
    dataframe: pd.DataFrame,
    config: OnePieceStudioConfig,
    *,
    total_rows: int,
) -> int | None:
    page_size = int(st.session_state.get(PAGE_SIZE, config.default_page_size))
    shown_rows = min(len(dataframe), page_size)
    st.caption(
        f"Showing {shown_rows:,} of {len(dataframe):,} filtered rows "
        f"from {total_rows:,} total records."
    )
    if dataframe.empty:
        st.info("No records match the current filters.")
        return None

    visible = dataframe.head(page_size).drop(columns=config.structure_columns, errors="ignore")
    focus = st.selectbox("Column focus", profile_names(), key="onepiece_studio_column_focus")
    visible = visible[columns_for_profile(focus, visible)]
    display = _display_dataframe(visible, image_columns=config.image_columns)
    event = st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        column_config={
            column: st.column_config.ImageColumn(column)
            for column in config.image_columns
            if column in visible.columns
        },
    )
    selected_rows = event.selection.rows
    if not selected_rows:
        return None
    return int(visible.index[selected_rows[0]])


def _display_dataframe(dataframe: pd.DataFrame, *, image_columns: list[str]) -> pd.DataFrame:
    display = dataframe.copy()
    for column in display.columns:
        if column in image_columns:
            continue
        if display[column].dtype == "object":
            display[column] = display[column].map(_display_value)
    return display


def _display_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return None
    except (TypeError, ValueError):
        pass
    text = str(value)
    return text if len(text) <= 240 else f"{text[:237]}..."


def _render_detail(
    st: Any,
    row: pd.Series,
    schema: list[Any],
    config: OnePieceStudioConfig,
) -> None:
    render_action_grid(st, row, row.name, key_prefix="detail", namespace="onepiece_studio_detail")

    for column in config.image_columns:
        if column in row:
            image = resolve_image(row[column], asset_root=config.normalized_asset_root())
            if image.display_uri:
                st.image(image.display_uri, caption=column, width="stretch")
            elif image.raw:
                st.warning(f"Image not found: {image.raw}")

    for column_schema in schema:
        column = column_schema.name
        if column in config.image_columns:
            continue
        value = row[column]
        if column_schema.kind == ColumnKind.STRUCTURE:
            st.code(_format_atoms(value), language="text")
            if is_atoms(value):
                button_key = f"onepiece_studio_ase_view_{column}_{row.name}"
                if st.button("Open in ASE viewer", key=button_key, width="stretch"):
                    try:
                        path = open_atoms_in_ase(value, label=str(row.get("Name", row.name)))
                    except Exception as exc:
                        st.error(f"Could not open ASE viewer: {exc}")
                    else:
                        st.success(f"Opened ASE viewer for {column}. Temporary file: {path}")
        else:
            st.write(f"**{column}**")
            st.write(value)


def _format_atoms(value: Any) -> str:
    if not is_atoms(value):
        return str(value)
    formula = value.get_chemical_formula()
    cell = value.cell.cellpar()
    return (
        f"ASE Atoms: {formula}\n"
        f"Atoms: {len(value)}\n"
        f"Cell: {', '.join(f'{number:.3f}' for number in cell)}"
    )
