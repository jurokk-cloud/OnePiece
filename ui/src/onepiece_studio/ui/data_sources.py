from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from onepiece.dftdataframe_import import (
    crawl_root_to_frame as backend_crawl_root_to_frame,
)
from onepiece.dftdataframe_import import (
    crawl_root_to_hdf as backend_crawl_root_to_hdf,
)
from onepiece.qa import bundled_catalysis_hub_dataset
from onepiece.sources import (
    apply_import_options as backend_apply_import_options,
)
from onepiece.sources import (
    combined_active_database as backend_combined_active_database,
)
from onepiece.sources import (
    detect_source_profile,
    source_profile_summary,
)
from onepiece.sources import (
    detected_gas_reference_values as backend_detected_gas_reference_values,
)
from onepiece.sources import (
    map_adsorption_columns as backend_map_adsorption_columns,
)
from onepiece.sources import (
    prepare_source_frame as backend_prepare_source_frame,
)
from onepiece.sources import (
    read_hdf_path as backend_read_hdf_path,
)
from onepiece.sources import (
    read_uploaded_hdf as backend_read_uploaded_hdf,
)
from onepiece.sources import (
    restore_source_descriptors as backend_restore_source_descriptors,
)
from onepiece.sources import (
    source_descriptors as backend_source_descriptors,
)
from onepiece.sources import (
    store_source as backend_store_source,
)
from onepiece_studio.state import (
    CRAWL_OUTPUT_HDF,
)
from onepiece_studio.ui.workbook import apply_session_edits, init_workbook_state

SOURCE_STATE_KEY = "onepiece_studio_extra_hdf_sources"
LAST_CRAWL_SUMMARY_KEY = "onepiece_studio_last_crawl_summary"


def apply_data_sources(
    st: Any,
    base: pd.DataFrame,
    source_name: str,
    *,
    source_path: str = "base",
) -> pd.DataFrame:
    """Build the active database from session state without rendering anything."""
    _init_state(st)
    init_workbook_state(st)
    return apply_session_edits(st, _combined_active_database(st, base, source_name=source_name, source_path=source_path))


def render_data_overview(
    st: Any,
    base: pd.DataFrame,
    active: pd.DataFrame,
    schema: list[Any],
    *,
    title: str,
    source_name: str,
    source_path: str = "base",
) -> None:
    """Render the Data page body: onboarding, source manager, and schema."""
    st.title(title)
    st.caption(f"{len(base):,} base records from {source_name}")
    _render_session_onboarding(st, active)
    render_data_source_manager(
        st,
        base,
        source_name,
        source_path=source_path,
        expanded=active.empty,
    )
    with st.expander("Schema", expanded=False):
        _render_schema(st, schema)


def _render_session_onboarding(st: Any, dataframe: pd.DataFrame) -> None:
    if not dataframe.empty:
        return
    with st.container(border=True):
        st.markdown("**Welcome to OnePiece Studio**")
        st.caption(
            "This session is empty on purpose. Load the bundled tutorial dataset or your own HDF file from "
            "`Data Sources`, then use `Workflow` to derive adsorption, Gibbs, charge, or geometry columns."
        )
        st.caption(
            "Good first path for new catalysis users: 1) load the bundled tutorial dataset, "
            "2) add `Adsorption + Gibbs analysis starter`, 3) inspect `Records`, 4) compare candidates in `Visualize`."
        )


def _render_schema(st: Any, schema: list[Any]) -> None:
    rows = [
        {
            "column": column.name,
            "kind": column.kind.value,
            "nullable": column.nullable,
            "unique_count": column.unique_count,
            "sample": str(column.sample)[:160],
        }
        for column in schema
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_data_source_manager(
    st: Any,
    base: pd.DataFrame,
    source_name: str,
    *,
    source_path: str = "base",
    expanded: bool = False,
) -> pd.DataFrame:
    """Render session-level HDF source management and return the active database."""
    _init_state(st)
    init_workbook_state(st)

    with st.expander("Data Sources", expanded=expanded):
        st.caption(
            "Add local OnePiece/pandas HDF files to this session. Active sources are "
            "merged before the Workflow and Filter steps, so your filters define the "
            "database used by every other page."
        )
        _render_add_sources(st)
        _render_source_table(st, base, source_name, source_path=source_path)

    return apply_data_sources(st, base, source_name, source_path=source_path)


def _init_state(st: Any) -> None:
    st.session_state.setdefault(SOURCE_STATE_KEY, {})
    st.session_state.setdefault(LAST_CRAWL_SUMMARY_KEY, None)


def _render_add_sources(st: Any) -> None:
    _render_starter_sources(st)
    local_col, upload_col, crawl_col = st.columns(3)
    with local_col:
        st.markdown("**Add local HDF path**")
        path_text = st.text_input(
            "HDF path",
            placeholder="path/to/database.hdf",
            key="onepiece_studio_add_hdf_path",
        )
        key = st.text_input("HDF key", value="df", key="onepiece_studio_add_hdf_key")
        import_options = _render_import_options(st, key_prefix="onepiece_studio_add_hdf")
        if st.button("Load HDF path", disabled=not path_text.strip(), width="stretch"):
            try:
                frame = _read_hdf_path(Path(path_text).expanduser(), key=key)
            except Exception as exc:
                st.error(f"Could not load HDF file: {exc}")
            else:
                frame = _apply_import_options(frame, import_options)
                _store_source(
                    st,
                    frame,
                    label=Path(path_text).name,
                    path=str(Path(path_text).expanduser()),
                    hdf_key=key,
                    origin="path",
                    import_options=import_options,
                )
                st.success(f"Loaded {len(frame):,} rows from {Path(path_text).name}.")
                st.rerun()

    with upload_col:
        st.markdown("**Upload HDF file**")
        uploaded = st.file_uploader("HDF file", type=["hdf", "h5", "hdf5"], key="onepiece_studio_upload_hdf")
        upload_key = st.text_input("Upload HDF key", value="df", key="onepiece_studio_upload_hdf_key")
        import_options = _render_import_options(st, key_prefix="onepiece_studio_upload_hdf")
        if st.button("Load uploaded HDF", disabled=uploaded is None, width="stretch"):
            try:
                frame, path = _read_uploaded_hdf(uploaded, key=upload_key)
            except Exception as exc:
                st.error(f"Could not load uploaded HDF file: {exc}")
            else:
                frame = _apply_import_options(frame, import_options)
                _store_source(
                    st,
                    frame,
                    label=uploaded.name,
                    path=str(path),
                    hdf_key=upload_key,
                    origin="upload",
                    import_options=import_options,
                )
                st.success(f"Loaded {len(frame):,} rows from {uploaded.name}.")
                st.rerun()

    with crawl_col:
        st.markdown("**Crawl calculation root**")
        root_text = st.text_input(
            "Calculation root",
            placeholder="path/to/calculations",
            key="onepiece_studio_crawl_root",
        )
        suggested_output = _suggest_crawled_hdf_path(root_text)
        calc_file = st.text_input(
            "Calculation file",
            value="final.traj",
            key="onepiece_studio_crawl_calc_file",
        )
        query_text = st.text_input(
            "Optional DataFrame.query()",
            value="",
            key="onepiece_studio_crawl_query",
        )
        output_hdf = st.text_input(
            "Optional output HDF path",
            value="",
            placeholder="path/to/created_frame.hdf",
            key=CRAWL_OUTPUT_HDF,
        )
        st.caption(
            "Typical DFTDataFrame output columns include `Name`, `Formula`, `E`, `Path`, `struc`, "
            "`fmax`, and per-element count columns. OnePiece Studio can then layer workflow, "
            "reference, and visualization columns on top."
        )
        st.caption(
            "OnePiece Studio looks for `out.txt` inside each calculation folder and reads row-local "
            "thermochemistry automatically when it is present."
        )
        if suggested_output:
            st.caption(f"Suggested reusable HDF path: `{suggested_output}`")
            st.button(
                "Use suggested HDF path",
                width="stretch",
                key="onepiece_studio_use_suggested_crawl_hdf",
                on_click=_set_crawl_output_hdf,
                args=(st.session_state, suggested_output),
            )
        _render_last_crawl_summary(st)
        import_options = _render_import_options(st, key_prefix="onepiece_studio_crawl_root")
        if st.button("Crawl root folder", disabled=not root_text.strip(), width="stretch"):
            progress_box = st.container(border=True)
            progress_label = progress_box.empty()
            progress_bar = progress_box.progress(0, text="Preparing crawl...")

            def _update_crawl_progress(completed: int, total: int, current_path: str) -> None:
                safe_total = max(int(total), 1)
                fraction = min(max(float(completed) / float(safe_total), 0.0), 1.0)
                current_name = Path(current_path).parent.name or Path(current_path).name
                progress_label.caption(f"{completed:,} / {safe_total:,}: `{current_name}`")
                progress_bar.progress(
                    fraction,
                    text=f"Crawling {completed:,} of {safe_total:,} calculation folders",
                )

            try:
                if output_hdf.strip():
                    output_path = _crawl_root_to_hdf_with_optional_progress(
                        root_text=root_text,
                        output_hdf=output_hdf.strip(),
                        calc_file=calc_file.strip() or "final.traj",
                        query=query_text.strip() or None,
                        progress_callback=_update_crawl_progress,
                    )
                    frame = _read_hdf_path(Path(output_path), key="df")
                    origin = "path"
                    path = str(Path(output_path).expanduser())
                    label = Path(output_path).name
                else:
                    frame = _crawl_root_to_frame_with_optional_progress(
                        root_text=root_text,
                        calc_file=calc_file.strip() or "final.traj",
                        query=query_text.strip() or None,
                        progress_callback=_update_crawl_progress,
                    )
                    origin = "generated"
                    path = str(Path(root_text).expanduser())
                    label = Path(root_text).expanduser().name or "crawled_root"
            except Exception as exc:
                progress_bar.empty()
                progress_label.empty()
                st.error(f"Could not crawl root folder: {exc}")
            else:
                progress_label.caption(f"Finished crawl for `{label}`")
                progress_bar.progress(1.0, text="Crawl complete")
                frame = _apply_import_options(frame, import_options)
                st.session_state[LAST_CRAWL_SUMMARY_KEY] = _crawl_summary(
                    frame,
                    root_text=root_text,
                    calc_file=calc_file,
                    output_hdf=output_hdf.strip() or None,
                )
                _store_source(
                    st,
                    frame,
                    label=label,
                    path=path,
                    hdf_key="df",
                    origin=origin,
                    import_options=import_options,
                )
                success_text = (
                    f"Crawled {len(frame):,} rows and wrote {label}."
                    if output_hdf.strip()
                    else f"Crawled {len(frame):,} rows from {Path(root_text).expanduser().name}."
                )
                st.success(success_text)
                st.rerun()


def _render_starter_sources(st: Any) -> None:
    with st.container(border=True):
        st.markdown("**Starter sources**")
        st.caption(
            "If you are just getting started, load the bundled Catalysis-Hub tutorial dataset first. "
            "It gives you a known-good adsorption dataset for learning the UI before you crawl your own calculations."
        )
        cols = st.columns([0.34, 0.66])
        if cols[0].button("Load bundled tutorial dataset", width="stretch"):
            path = bundled_catalysis_hub_dataset()
            try:
                frame = _read_hdf_path(path, key="df")
            except Exception as exc:
                st.error(str(exc))
            else:
                _store_source(
                    st,
                    frame,
                    label=path.name,
                    path=str(path),
                    hdf_key="df",
                    origin="path",
                    import_options={},
                )
                st.success(f"Loaded {len(frame):,} rows from the bundled tutorial dataset.")
                st.rerun()
        cols[1].caption(
            "Recommended first pass: `Data Sources` -> bundled tutorial dataset, "
            "`Workflow` -> `Adsorption + Gibbs analysis starter`, then `Visualize` -> `Adsorption analysis`."
        )


def _suggest_crawled_hdf_path(root_text: str) -> str:
    text = str(root_text).strip()
    if not text:
        return ""
    root = Path(text).expanduser()
    if not root.name:
        return ""
    safe_name = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in root.name)
    return str((root.parent / f"{safe_name}.hdf").expanduser())


def _set_crawl_output_hdf(session_state: Any, output_path: str) -> None:
    session_state[CRAWL_OUTPUT_HDF] = output_path


def _crawl_summary(
    frame: pd.DataFrame,
    *,
    root_text: str,
    calc_file: str,
    output_hdf: str | None,
) -> dict[str, Any]:
    profile = detect_source_profile(frame)
    gas_refs = backend_detected_gas_reference_values(frame)
    important_columns = [
        column
        for column in ["Name", "Formula", "E", "Path", "struc", "CONTCAR", "structure", "atoms", "fmax"]
        if column in frame.columns
    ]
    structure_columns = [column for column in ["struc", "CONTCAR", "structure", "atoms"] if column in frame.columns]
    return {
        "root": str(Path(root_text).expanduser()),
        "calc_file": calc_file.strip() or "final.traj",
        "output_hdf": output_hdf,
        "rows": len(frame),
        "columns": frame.shape[1],
        "profile": profile["profile"],
        "capabilities": profile["capabilities"],
        "important_columns": important_columns,
        "structure_columns": structure_columns,
        "gas_reference_labels": sorted(gas_refs),
    }


def _render_last_crawl_summary(st: Any) -> None:
    summary = st.session_state.get(LAST_CRAWL_SUMMARY_KEY)
    if not summary:
        return
    with st.container(border=True):
        st.markdown("**Last crawl summary**")
        top = st.columns(2)
        bottom = st.columns(2)
        top[0].metric("Rows", f"{summary['rows']:,}")
        top[1].metric("Columns", f"{summary['columns']:,}")
        bottom[0].metric("Profile", summary["profile"])
        bottom[1].metric("Gas refs", str(len(summary["gas_reference_labels"])))
        st.caption(f"Root: `{summary['root']}`")
        st.caption(f"Calculation file: `{summary['calc_file']}`")
        if summary.get("output_hdf"):
            st.caption(f"Wrote HDF: `{summary['output_hdf']}`")
        if summary["structure_columns"]:
            st.caption(f"Structure columns: `{', '.join(summary['structure_columns'])}`")
        if summary["important_columns"]:
            st.caption(f"Detected key columns: `{', '.join(summary['important_columns'])}`")
        if summary["gas_reference_labels"]:
            st.caption(f"Detected gas-reference candidates: `{', '.join(summary['gas_reference_labels'])}`")
        if summary["capabilities"]:
            st.caption(f"Capabilities: `{', '.join(summary['capabilities'])}`")


def _crawl_root_to_frame_with_optional_progress(
    *,
    root_text: str,
    calc_file: str,
    query: str | None,
    progress_callback: Any,
) -> pd.DataFrame:
    try:
        return backend_crawl_root_to_frame(
            root_text,
            calc_file=calc_file,
            query=query,
            verbose=True,
            progress_callback=progress_callback,
        )
    except TypeError as exc:
        if "progress_callback" not in str(exc):
            raise
        return backend_crawl_root_to_frame(
            root_text,
            calc_file=calc_file,
            query=query,
            verbose=True,
        )


def _crawl_root_to_hdf_with_optional_progress(
    *,
    root_text: str,
    output_hdf: str,
    calc_file: str,
    query: str | None,
    progress_callback: Any,
) -> Path:
    try:
        return backend_crawl_root_to_hdf(
            root_text,
            output_hdf,
            calc_file=calc_file,
            query=query,
            verbose=True,
            progress_callback=progress_callback,
        )
    except TypeError as exc:
        if "progress_callback" not in str(exc):
            raise
        return backend_crawl_root_to_hdf(
            root_text,
            output_hdf,
            calc_file=calc_file,
            query=query,
            verbose=True,
        )


def _render_source_table(st: Any, base: pd.DataFrame, source_name: str, *, source_path: str) -> None:
    sources = st.session_state.get(SOURCE_STATE_KEY, {})
    base_profile = detect_source_profile(
        _prepare_source_frame(base, label=source_name, path=source_path, source_id="base")
    )
    rows = [
        {
            "id": "base",
            "label": source_name,
            "rows": len(base),
            "columns": base.shape[1],
            "enabled": True,
            "kind": "base",
            "profile": base_profile["profile"],
            "capabilities": ", ".join(base_profile["capabilities"][:4]),
        }
    ]
    rows.extend(
        {
            "id": source_id,
            "label": item["label"],
            "rows": item["rows"],
            "columns": item["columns"],
            "enabled": item.get("enabled", True),
            "kind": "extra_hdf",
            "profile": item.get("profile", "generic_dataframe"),
            "capabilities": ", ".join(item.get("capabilities", [])[:4]),
        }
        for source_id, item in sources.items()
    )
    st.markdown("**Source blocks**")
    edited = st.data_editor(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        height=240,
        disabled=["id", "label", "rows", "columns", "kind", "profile", "capabilities"],
        key="onepiece_studio_source_blocks_editor",
    )
    _apply_source_block_edits(st, edited)

    if sources:
        selected = st.selectbox(
            "Manage added source",
            list(sources),
            format_func=lambda source_id: sources[source_id]["label"],
        )
        actions = st.columns(3)
        current = sources[selected]
        st.caption(source_profile_summary(current.get("profile", "generic_dataframe"), current.get("capabilities", [])))
        toggle_label = "Disable source" if current.get("enabled", True) else "Enable source"
        if actions[0].button(toggle_label, width="stretch"):
            current["enabled"] = not current.get("enabled", True)
            st.rerun()
        if actions[1].button("Remove source", width="stretch"):
            sources.pop(selected, None)
            st.rerun()
        if actions[2].button("Clear all added", width="stretch"):
            sources.clear()
            st.rerun()


def _combined_active_database(
    st: Any,
    base: pd.DataFrame,
    *,
    source_name: str = "base",
    source_path: str = "base",
) -> pd.DataFrame:
    return backend_combined_active_database(
        st.session_state,
        base,
        base_label=source_name,
        base_path=source_path,
        base_source_id="base",
    )


def _apply_source_block_edits(st: Any, edited: pd.DataFrame) -> None:
    sources = st.session_state.get(SOURCE_STATE_KEY, {})
    rerun_needed = False
    for row in edited.to_dict("records"):
        source_id = row.get("id")
        if source_id == "base":
            continue
        if source_id not in sources:
            continue
        desired = bool(row.get("enabled", True))
        current = bool(sources[source_id].get("enabled", True))
        if desired != current:
            sources[source_id]["enabled"] = desired
            rerun_needed = True
    if rerun_needed:
        st.rerun()


def _store_source(
    st: Any,
    frame: pd.DataFrame,
    *,
    label: str,
    path: str,
    hdf_key: str = "df",
    origin: str = "path",
    import_options: dict[str, Any] | None = None,
) -> None:
    backend_store_source(
        st.session_state,
        frame,
        label=label,
        path=path,
        hdf_key=hdf_key,
        origin=origin,
        import_options=import_options,
    )


def source_descriptors(st: Any) -> list[dict[str, Any]]:
    return backend_source_descriptors(st.session_state)


def restore_source_descriptors(st: Any, descriptors: list[dict[str, Any]]) -> list[str]:
    return backend_restore_source_descriptors(st.session_state, descriptors)


def _prepare_source_frame(frame: pd.DataFrame, *, label: str, path: str, source_id: str) -> pd.DataFrame:
    return backend_prepare_source_frame(frame, label=label, path=path, source_id=source_id)


def _read_hdf_path(path: Path, *, key: str) -> pd.DataFrame:
    return backend_read_hdf_path(path, key=key)


def _read_uploaded_hdf(uploaded: Any, *, key: str) -> tuple[pd.DataFrame, Path]:
    return backend_read_uploaded_hdf(uploaded, key=key)


def _source_id(label: str, path: str, sources: dict[str, Any]) -> str:
    stem = Path(label).stem or "hdf"
    base = "".join(character if character.isalnum() else "_" for character in stem).strip("_")
    candidate = base or "hdf"
    counter = 2
    while candidate in sources:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _render_import_options(st: Any, *, key_prefix: str) -> dict[str, Any]:
    enable = st.checkbox(
        "Prepare adsorption-analysis columns on import",
        value=False,
        key=f"{key_prefix}_adsorption_enable",
    )
    with st.expander("Adsorption import options", expanded=False):
        st.caption(
            "Choose which HDF columns should be mapped to the standard adsorption-analysis names. "
            "Default suggestions work for most OnePiece tables."
        )
        dataset_kind = st.selectbox(
            "Dataset kind",
            ["auto", "mixed", "gas", "surface", "bulk"],
            index=0,
            key=f"{key_prefix}_dataset_kind",
        )
        name_column = st.text_input("Name column", value="Name", key=f"{key_prefix}_name_column")
        energy_column = st.text_input("Energy column", value="E", key=f"{key_prefix}_energy_column")
        formula_column = st.text_input("Formula column", value="Formula", key=f"{key_prefix}_formula_column")
        path_column = st.text_input("Path column", value="Path", key=f"{key_prefix}_path_column")
    return {
        "enable_adsorption_prep": bool(enable),
        "dataset_kind": dataset_kind,
        "name_column": name_column.strip(),
        "energy_column": energy_column.strip(),
        "formula_column": formula_column.strip(),
        "path_column": path_column.strip(),
    }


def _apply_import_options(frame: pd.DataFrame, options: dict[str, Any] | None) -> pd.DataFrame:
    return backend_apply_import_options(frame, options)


def _map_adsorption_columns(frame: pd.DataFrame, options: dict[str, Any]) -> pd.DataFrame:
    return backend_map_adsorption_columns(frame, options)


def _detected_gas_reference_values(frame: pd.DataFrame) -> dict[str, float]:
    return backend_detected_gas_reference_values(frame)
