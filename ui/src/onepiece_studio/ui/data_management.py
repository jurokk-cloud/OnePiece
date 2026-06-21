from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from onepiece.projects import build_project_payload as backend_build_project_payload
from onepiece.projects import restore_project_payload as backend_restore_project_payload
from onepiece.sources import source_descriptors
from onepiece_studio.state import (
    AUDIT_LOG,
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
    SAVED_VIEWS,
    WORKFLOW_OPERATIONS,
)
from onepiece_studio.ui.workbook import EDIT_STATE_KEY, render_workbook

CONTROL_KEYS = [
    CONTROL_TEXT_INCLUDE,
    CONTROL_TEXT_EXCLUDE,
    CONTROL_USE_STATUS,
    CONTROL_VISIBLE_STATES,
    CONTROL_SELECTED_FACETS,
    CONTROL_NUMERIC,
    CONTROL_MATERIAL_QUERY,
    CONTROL_FMAX_MAX,
    CONTROL_DROP_CONVERGENCE,
    CONTROL_DROP_TEST,
]


def render_data_management(st: Any, source: pd.DataFrame, active: pd.DataFrame) -> None:
    _init_state(st)
    st.subheader("Data Management")
    st.caption(
        "Local-first tools for saved views, row-state management, reference resolution, "
        "column health and reproducible exports."
    )
    _render_top_metrics(st, source, active)

    project_tab, saved_views_tab, workbook_tab, row_states_tab, references_tab, column_health_tab, exports_tab = st.tabs(
        ["Project", "Saved Views", "Workbook", "Row States", "References", "Column Health", "Exports"]
    )

    with project_tab:
        _render_project_file_tools(st, source, active)
    with saved_views_tab:
        _render_saved_views(st)
    with workbook_tab:
        render_workbook(st, source, active)
    with row_states_tab:
        _render_row_states(st, source, active)
    with references_tab:
        _render_reference_preview(st, source, active)
    with column_health_tab:
        _render_column_health(st, source)
    with exports_tab:
        _render_exports(st, source, active)


def _init_state(st: Any) -> None:
    st.session_state.setdefault(SAVED_VIEWS, {})
    st.session_state.setdefault(AUDIT_LOG, [])
    st.session_state.setdefault(CONTROL_STATUS, {})


def _render_top_metrics(st: Any, source: pd.DataFrame, active: pd.DataFrame) -> None:
    states = st.session_state.get(CONTROL_STATUS, {})
    top = st.columns(3, gap="small")
    bottom = st.columns(2, gap="small")
    top[0].metric("Active rows", f"{len(active):,}")
    top[1].metric("Total rows", f"{len(source):,}")
    top[2].metric("Saved views", f"{len(st.session_state.get('onepiece_studio_saved_views', {})):,}")
    bottom[0].metric("State overrides", f"{len(states):,}")
    if "quality_flag" in source.columns:
        review_rows = int(source["quality_flag"].astype(str).str.contains("review", na=False).sum())
        bottom[1].metric("Quality review", f"{review_rows:,}")
    else:
        bottom[1].metric("Columns", f"{source.shape[1]:,}")


def _render_saved_views(st: Any) -> None:
    st.markdown("**Save and restore filter/controlroom states**")
    name = st.text_input("View name", placeholder="e.g. clean 211 surfaces with fmax ok")
    columns = st.columns([0.25, 0.25, 0.5])
    if columns[0].button("Save current view", disabled=not name, width="stretch"):
        st.session_state[SAVED_VIEWS][name] = {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "state": _capture_control_state(st),
        }
        _audit(st, f"Saved view: {name}")
        st.success(f"Saved view '{name}'.")

    saved = st.session_state.get(SAVED_VIEWS, {})
    selected = columns[2].selectbox("Saved views", [""] + sorted(saved))
    if columns[1].button("Restore", disabled=not selected, width="stretch"):
        _restore_control_state(st, saved[selected]["state"])
        _audit(st, f"Restored view: {selected}")
        st.rerun()

    if saved:
        rows = [
            {"view": key, "saved_at": value.get("saved_at", ""), "state_keys": len(value.get("state", {}))}
            for key, value in sorted(saved.items())
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    if selected and st.button("Delete selected view", type="secondary"):
        st.session_state[SAVED_VIEWS].pop(selected, None)
        _audit(st, f"Deleted view: {selected}")
        st.rerun()


def _render_row_states(st: Any, source: pd.DataFrame, active: pd.DataFrame) -> None:
    st.markdown("**Row-state board**")
    status = st.session_state.get(CONTROL_STATUS, {})
    board = _state_board(source, status)
    st.dataframe(board, hide_index=True, width="stretch")

    st.markdown("**Batch actions for active rows**")
    st.caption("These actions affect the active filtered rows currently visible in OnePiece Studio.")
    action_cols = st.columns(4)
    actions = [
        ("Mark active included", "included"),
        ("Mark active review", "review"),
        ("Mark active reference", "reference"),
        ("Exclude active", "excluded"),
    ]
    for column, (label, state) in zip(action_cols, actions, strict=False):
        if column.button(label, width="stretch", disabled=active.empty):
            _set_many_states(st, active, state)
            _audit(st, f"{label}: {len(active)} rows")
            st.rerun()

    if status:
        st.markdown("**Manual overrides**")
        rows = _status_rows(source, status)
        st.dataframe(rows, hide_index=True, width="stretch", height=280)
        if st.button("Clear all row-state overrides"):
            st.session_state[CONTROL_STATUS] = {}
            _audit(st, "Cleared all row-state overrides")
            st.rerun()


def _render_reference_preview(st: Any, source: pd.DataFrame, active: pd.DataFrame) -> None:
    st.markdown("**Reference resolver preview**")
    st.caption(
        "Preview how future adsorption-energy workflows can match adsorbate-like rows "
        "to clean surface references in the same local dataset."
    )
    target_scope = st.segmented_control(
        "Target rows",
        ["Active rows", "All rows"],
        default="Active rows",
    )
    frame = active if target_scope == "Active rows" else source
    preview = _reference_matches(source, frame)
    st.dataframe(preview, hide_index=True, width="stretch", height=420)
    if not preview.empty:
        counts = preview["match_status"].value_counts().rename_axis("match_status").reset_index(name="rows")
        st.dataframe(counts, hide_index=True, width="stretch")


def _render_column_health(st: Any, source: pd.DataFrame) -> None:
    st.markdown("**Column health and type stability**")
    health = _column_health(source)
    selected_mode = st.segmented_control(
        "Show",
        ["Important issues", "All columns"],
        default="Important issues",
    )
    if selected_mode == "Important issues":
        health = health[
            (health["non_null_pct"] < 100)
            | (health["mixed_python_types"] > 1)
            | (health["unique"] <= 2)
        ]
    st.dataframe(health, hide_index=True, width="stretch", height=520)


def _render_exports(st: Any, source: pd.DataFrame, active: pd.DataFrame) -> None:
    st.markdown("**Reproducible exports**")
    col1, col2 = st.columns(2)
    col1.download_button(
        "Download active rows CSV",
        active.to_csv(index=False).encode("utf-8"),
        file_name="onepiece_studio_active_rows.csv",
        mime="text/csv",
        width="stretch",
    )
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_rows": int(len(source)),
        "active_rows": int(len(active)),
        "columns": list(source.columns),
        "control_state": _capture_control_state(st),
        "saved_views": list(st.session_state.get(SAVED_VIEWS, {})),
        "row_state_overrides": st.session_state.get(CONTROL_STATUS, {}),
        "audit_log": st.session_state.get(AUDIT_LOG, []),
    }
    col2.download_button(
        "Download dataset manifest JSON",
        json.dumps(manifest, indent=2, default=str).encode("utf-8"),
        file_name="onepiece_studio_dataset_manifest.json",
        mime="application/json",
        width="stretch",
    )

    st.markdown("**Audit log**")
    audit = st.session_state.get(AUDIT_LOG, [])
    if audit:
        st.dataframe(pd.DataFrame(audit), hide_index=True, width="stretch")
    else:
        st.info("No data-management actions recorded in this session yet.")


def _render_project_file_tools(st: Any, source: pd.DataFrame, active: pd.DataFrame) -> None:
    st.markdown("**OnePiece Studio project file**")
    st.caption(
        "Save the current UI state, workflow, source blocks, row states, and workbook edits into "
        "one reusable project file. Reload it later to continue where you stopped."
    )

    project = _build_project_payload(st, source, active)
    json_bytes = json.dumps(project, indent=2, default=str).encode("utf-8")

    save_cols = st.columns([0.46, 0.22, 0.32])
    default_path = save_cols[0].text_input(
        "Project file path",
        value=str(Path.cwd() / "onepiece_studio_project.json"),
        key="onepiece_studio_project_file_path",
    )
    if save_cols[1].button("Save to path", width="stretch"):
        target = Path(default_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(json_bytes)
        _audit(st, f"Saved project file: {target}")
        st.success(f"Saved OnePiece Studio project file to {target}.")
    save_cols[2].download_button(
        "Download project file",
        json_bytes,
        file_name="onepiece_studio_project.json",
        mime="application/json",
        width="stretch",
    )

    st.markdown("**Reload project**")
    load_cols = st.columns(2)
    load_path = load_cols[0].text_input(
        "Load project file path",
        value=default_path,
        key="onepiece_studio_project_load_path",
    )
    if load_cols[0].button("Load from path", width="stretch"):
        try:
            payload = json.loads(Path(load_path).expanduser().read_text(encoding="utf-8"))
            messages = _restore_project_payload(st, payload)
        except Exception as exc:
            st.error(f"Could not load project file: {exc}")
        else:
            for message in messages:
                st.warning(message)
            _audit(st, f"Loaded project file: {Path(load_path).expanduser()}")
            st.success("Reloaded OnePiece Studio project state from file.")
            st.rerun()

    uploaded = load_cols[1].file_uploader(
        "Upload OnePiece Studio project file",
        type=["json"],
        key="onepiece_studio_project_upload",
    )
    if load_cols[1].button("Load uploaded project", width="stretch", disabled=uploaded is None):
        try:
            payload = json.loads(uploaded.getvalue().decode("utf-8"))
            messages = _restore_project_payload(st, payload)
        except Exception as exc:
            st.error(f"Could not load uploaded project file: {exc}")
        else:
            for message in messages:
                st.warning(message)
            _audit(st, f"Loaded uploaded project file: {uploaded.name}")
            st.success("Reloaded OnePiece Studio project state from uploaded file.")
            st.rerun()

    st.markdown("**What is inside the project file?**")
    st.dataframe(
        pd.DataFrame(
            [
                {"section": "workflow_operations", "items": len(st.session_state.get(WORKFLOW_OPERATIONS, []))},
                {"section": "control_state", "items": len(_capture_control_state(st))},
                {"section": "row_state_overrides", "items": len(st.session_state.get(CONTROL_STATUS, {}))},
                {"section": "workbook_edits", "items": len(st.session_state.get(EDIT_STATE_KEY, {}))},
                {"section": "source_blocks", "items": len(source_descriptors(st.session_state))},
                {"section": "saved_views", "items": len(st.session_state.get(SAVED_VIEWS, {}))},
            ]
        ),
        hide_index=True,
        width="stretch",
    )


def _capture_control_state(st: Any) -> dict[str, Any]:
    return {key: deepcopy(st.session_state.get(key)) for key in CONTROL_KEYS if key in st.session_state}


def _restore_control_state(st: Any, state: dict[str, Any]) -> None:
    for key, value in state.items():
        st.session_state[key] = deepcopy(value)


def _build_project_payload(st: Any, source: pd.DataFrame, active: pd.DataFrame) -> dict[str, Any]:
    return backend_build_project_payload(
        state=st.session_state,
        source_rows=len(source),
        active_rows=len(active),
        control_state=_capture_control_state(st),
    )


def _restore_project_payload(st: Any, payload: dict[str, Any]) -> list[str]:
    return backend_restore_project_payload(st.session_state, payload)


def _state_board(source: pd.DataFrame, status: dict[str, str]) -> pd.DataFrame:
    keys = _row_keys(source)
    states = keys.map(lambda key: status.get(key, "included"))
    rows = states.value_counts().rename_axis("state").reset_index(name="rows")
    rows["percent"] = 100 * rows["rows"] / max(len(source), 1)
    return rows.sort_values("state")


def _set_many_states(st: Any, dataframe: pd.DataFrame, state: str) -> None:
    status = st.session_state.setdefault(CONTROL_STATUS, {})
    for key in _row_keys(dataframe):
        status[key] = state
    st.session_state[CONTROL_USE_STATUS] = True


def _status_rows(source: pd.DataFrame, status: dict[str, str]) -> pd.DataFrame:
    key_to_index = {key: index for index, key in _row_keys(source).items()}
    rows = []
    for key, state in sorted(status.items()):
        index = key_to_index.get(key)
        row = source.loc[index] if index is not None else {}
        rows.append(
            {
                "row_key": key,
                "state": state,
                "dataset": row.get("dataset", "") if hasattr(row, "get") else "",
                "Name": row.get("Name", "") if hasattr(row, "get") else "",
                "Formula": row.get("Formula", "") if hasattr(row, "get") else "",
            }
        )
    return pd.DataFrame(rows)


def _reference_matches(source: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    if "Name" not in source.columns:
        return pd.DataFrame()
    adsorbates = targets[
        targets.get("is_adsorbate_like", pd.Series(False, index=targets.index)).fillna(False)
    ].copy()
    clean_refs = source[source.get("is_clean", pd.Series(False, index=source.index)).fillna(False)].copy()
    rows = []
    for index, row in adsorbates.head(200).iterrows():
        candidates = clean_refs.copy()
        for column in ["hkl", "slabsize", "dataset"]:
            if column in candidates.columns and column in row.index and pd.notna(row[column]):
                same = candidates[candidates[column].astype(str) == str(row[column])]
                if not same.empty:
                    candidates = same
        status = "missing"
        if len(candidates) == 1:
            status = "ok"
        elif len(candidates) > 1:
            status = "ambiguous"
        rows.append(
            {
                "target_uid": _row_key(row, index),
                "target_name": row.get("Name", ""),
                "adsorbate_guess": row.get("adsorbate_guess", ""),
                "hkl": row.get("hkl", ""),
                "slabsize": row.get("slabsize", ""),
                "match_status": status,
                "candidate_count": len(candidates),
                "first_reference": candidates.iloc[0].get("Name", "") if len(candidates) else "",
            }
        )
    return pd.DataFrame(rows)


def _column_health(source: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in source.columns:
        series = source[column]
        sample = ""
        if series.notna().any():
            sample = repr(series.dropna().iloc[0])[:120]
        try:
            unique = int(series.nunique(dropna=True))
        except TypeError:
            unique = int(series.dropna().map(repr).nunique())
        python_types = series.dropna().map(lambda value: type(value).__name__).unique().tolist()
        rows.append(
            {
                "column": column,
                "dtype": str(series.dtype),
                "non_null_pct": round(100 * float(series.notna().mean()), 1),
                "unique": unique,
                "mixed_python_types": len(python_types),
                "python_types": ", ".join(python_types[:5]),
                "sample": sample,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["mixed_python_types", "non_null_pct", "column"],
        ascending=[False, True, True],
    )


def _row_keys(dataframe: pd.DataFrame) -> pd.Series:
    if {"source_hdf", "source_row"}.issubset(dataframe.columns):
        return dataframe["source_hdf"].astype(str) + "::" + dataframe["source_row"].astype(str)
    return pd.Series(dataframe.index.astype(str), index=dataframe.index)


def _row_key(row: pd.Series, fallback: Any) -> str:
    if "source_hdf" in row.index and "source_row" in row.index:
        return f"{row['source_hdf']}::{row['source_row']}"
    return str(fallback)


def _audit(st: Any, action: str) -> None:
    st.session_state.setdefault(AUDIT_LOG, []).append(
        {"time": datetime.now().isoformat(timespec="seconds"), "action": action}
    )
