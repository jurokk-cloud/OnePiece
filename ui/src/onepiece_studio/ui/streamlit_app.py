from __future__ import annotations

import argparse
from typing import Any

import pandas as pd

from onepiece_studio.adapters import (
    DatabaseSource,
    apply_controlroom_filters,
    load_source_cached,
)
from onepiece_studio.config import OnePieceStudioConfig
from onepiece_studio.demo import demo_source, local_default_source
from onepiece_studio.schema import infer_schema
from onepiece_studio.state import AUDIT_LOG
from onepiece_studio.ui.adsorption import render_adsorption_workbench
from onepiece_studio.ui.controlroom import render_controlroom
from onepiece_studio.ui.data_management import render_data_management
from onepiece_studio.ui.data_sources import apply_data_sources, render_data_overview
from onepiece_studio.ui.records import render_records
from onepiece_studio.ui.visualize import render_visualizations
from onepiece_studio.ui.workflow_builder import apply_workflow_operations, render_workflow_builder


def run_app(source: DatabaseSource, config: OnePieceStudioConfig) -> None:
    import streamlit as st

    st.set_page_config(page_title=config.title, page_icon="PF", layout="wide")
    _inject_styles(st)

    try:
        base_dataframe = load_source_cached(source)
    except Exception as exc:
        st.error(
            f"**Could not load the dataset for this session.**\n\n{exc}\n\n"
            "If the file moved or changed, restart with "
            "`onepiece-studio hdf /path/to/database.hdf --key df`, or run "
            "`onepiece-studio doctor` to check your environment."
        )
        st.stop()
        return

    page_functions = build_page_functions(st, source, config, base_dataframe)
    filtered = page_functions.pop("_filtered_count")
    total = page_functions.pop("_total_count")

    with st.sidebar:
        st.markdown(f"**{config.title}**")
        st.caption(f"{filtered:,} of {total:,} records selected")

    navigation = st.navigation(
        {
            "Data": [
                st.Page(
                    page_functions["data"], title="Data", icon=":material/database:", url_path="data", default=True
                ),
            ],
            "Explore": [
                st.Page(page_functions["filter"], title="Filter", icon=":material/filter_alt:", url_path="filter"),
                st.Page(
                    page_functions["records"], title="Records", icon=":material/table_rows:", url_path="records"
                ),
                st.Page(
                    page_functions["visualize"],
                    title="Visualize",
                    icon=":material/monitoring:",
                    url_path="visualize",
                ),
            ],
            "Analyze": [
                st.Page(
                    page_functions["analyze"],
                    title="Adsorption & Barriers",
                    icon=":material/science:",
                    url_path="adsorption",
                ),
                st.Page(
                    page_functions["manage"], title="Manage & Export", icon=":material/inventory:", url_path="manage"
                ),
            ],
            "Advanced": [
                st.Page(
                    page_functions["workflow"],
                    title="Workflow Builder",
                    icon=":material/account_tree:",
                    url_path="workflow",
                ),
            ],
        }
    )
    navigation.run()


def build_page_functions(
    st: Any,
    source: DatabaseSource,
    config: OnePieceStudioConfig,
    base_dataframe: pd.DataFrame,
) -> dict[str, Any]:
    """Compute the session pipeline and return the per-page render callables.

    Exposed separately from :func:`run_app` so tests can render each page
    directly; the two count entries feed the sidebar summary.
    """
    source_name = getattr(source, "display_name", source.name)
    source_path = str(getattr(source, "path", source_name))

    dataframe = apply_data_sources(st, base_dataframe, str(source_name), source_path=source_path)
    workflow = apply_workflow_operations(st, dataframe)
    st.session_state[AUDIT_LOG] = workflow.audit_log
    workflow_dataframe = workflow.dataframe
    schema = infer_schema(
        workflow_dataframe,
        image_columns=config.image_columns,
        structure_columns=config.structure_columns,
    )
    filtered = apply_controlroom_filters(st, workflow_dataframe)

    def data_page() -> None:
        render_data_overview(
            st,
            base_dataframe,
            dataframe,
            schema,
            title=config.title,
            source_name=str(source_name),
            source_path=source_path,
        )

    def filter_page() -> None:
        render_controlroom(st, workflow_dataframe)

    def records_page() -> None:
        render_records(st, filtered, workflow_dataframe, schema, config)

    def visualize_page() -> None:
        render_visualizations(st, filtered)

    def analyze_page() -> None:
        render_adsorption_workbench(st, filtered, filtered, reference_source=workflow_dataframe)

    def manage_page() -> None:
        render_data_management(st, workflow_dataframe, filtered)

    def workflow_page() -> None:
        render_workflow_builder(st, dataframe, workflow_dataframe, workflow.messages)

    return {
        "data": data_page,
        "filter": filter_page,
        "records": records_page,
        "visualize": visualize_page,
        "analyze": analyze_page,
        "manage": manage_page,
        "workflow": workflow_page,
        "_filtered_count": len(filtered),
        "_total_count": len(workflow_dataframe),
    }


def _inject_styles(st: Any) -> None:
    st.markdown(
        """
        <style>
        html, body, [class*="css"], button, input, textarea, select,
        .stMarkdown, .stDataFrame, .stDataFrame *, h1, h2, h3, h4, h5, h6,
        [data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stMetric"],
        [data-testid="stTabs"], [data-testid="stCaptionContainer"] {
            font-family: system-ui, sans-serif !important;
        }
        .material-icons, .material-symbols-rounded, .material-symbols-outlined,
        [data-testid="stExpanderToggleIcon"], [data-testid="stBaseButton-header"] span {
            font-family: "Material Symbols Rounded", "Material Symbols Outlined", sans-serif !important;
        }
        .math, .math *, .MathJax, .MathJax *, .mjx-container, .mjx-container * {
            font-family: initial !important;
        }
        .block-container { padding-top: 2rem; padding-bottom: 3rem; }
        details[data-testid="stExpander"] summary {
            min-height: 2.75rem;
            align-items: center;
        }
        details[data-testid="stExpander"] summary p {
            line-height: 1.2;
            margin: 0;
        }
        div[data-testid="stMetricLabel"] p {
            white-space: normal;
            line-height: 1.15;
        }
        div[data-testid="stMetricValue"] {
            line-height: 1.0;
            font-size: clamp(1.8rem, 2vw, 2.7rem);
        }
        div[data-testid="stMetric"] {
            background: #f7f8fa;
            border: 1px solid #e4e7ec;
            border-radius: 8px;
            padding: 14px 16px;
            min-height: 112px;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid #e4e7ec;
            border-radius: 8px;
            overflow: hidden;
        }
        button[kind], div[data-testid="stButton"] > button {
            min-height: 2.6rem;
            white-space: normal;
        }
        [data-testid="stTabs"] button {
            white-space: nowrap;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--hdf")
    parser.add_argument("--key", default="df")
    parser.add_argument("--title")
    args = parser.parse_args()
    if args.demo:
        source, config = demo_source()
        run_app(source, config)
    elif args.hdf:
        import streamlit as st

        from onepiece_studio.state import WELCOME_SELECTION
        from onepiece_studio.ui.welcome import remember_recent_file, run_welcome

        remember_recent_file(args.hdf, args.key)
        st.session_state.setdefault(
            WELCOME_SELECTION,
            {"path": args.hdf, "key": args.key, "title": args.title},
        )
        run_welcome()
    else:
        source, config = local_default_source()
        if getattr(source, "name", "") == "empty-session":
            from onepiece_studio.ui.welcome import run_welcome

            run_welcome()
        else:
            run_app(source, config)


if __name__ == "__main__":
    _main()
