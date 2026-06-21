from __future__ import annotations

import pandas as pd
from streamlit.testing.v1 import AppTest

from onepiece.services import apply_dataset_query


def _welcome_app() -> None:
    from onepiece_studio.ui.welcome import run_welcome

    run_welcome()


def _all_pages_app() -> None:
    import streamlit as st
    from onepiece_studio.adapters import HDFSource, load_source_cached
    from onepiece_studio.ui.streamlit_app import build_page_functions
    from onepiece_studio.ui.welcome import standard_hdf_config

    from onepiece import bundled_catalysis_hub_dataset

    source = HDFSource(bundled_catalysis_hub_dataset(), key="df")
    config = standard_hdf_config("All pages probe")
    pages = build_page_functions(st, source, config, load_source_cached(source))
    for name in ["data", "filter", "records", "visualize", "analyze", "manage", "workflow"]:
        st.header(f"probe:{name}")
        pages[name]()


def test_apply_dataset_query_handles_duplicate_index_labels() -> None:
    frame = pd.DataFrame(
        {"E": [1.0, 2.0, 3.0]},
        index=pd.Index(["CO@Cu", "CO@Cu", "O@Pt"], name="Name"),
    )
    row_keys = pd.Series(frame.index.astype(str), index=frame.index)

    # Without the duplicate-label guard this raised
    # "Item wrong length N instead of M".
    result = apply_dataset_query(frame, {}, row_key_series=row_keys, status_map={})

    assert len(result) == 3


def test_welcome_page_renders_tutorial_and_open_actions() -> None:
    app = AppTest.from_function(_welcome_app, default_timeout=120)
    app.run()

    assert not app.exception
    assert [t.value for t in app.title] == ["OnePiece Studio"]
    labels = [b.label for b in app.button]
    assert "Open the tutorial dataset" in labels
    assert "Open file" in labels


def test_every_workbench_page_renders_with_tutorial_dataset() -> None:
    app = AppTest.from_function(_all_pages_app, default_timeout=180)
    app.run()

    assert not app.exception, [e.value for e in app.exception]
    rendered = [h.value for h in app.header if str(h.value).startswith("probe:")]
    assert len(rendered) == 7


def test_welcome_wrong_key_shows_recovery_panel_and_retry_works(tmp_path) -> None:
    from onepiece_studio.state import WELCOME_SELECTION

    hdf_path = tmp_path / "data.hdf"
    pd.DataFrame({"Name": ["a"], "E": [1.0]}).to_hdf(hdf_path, key="results")

    app = AppTest.from_function(_welcome_app, default_timeout=120)
    app.session_state[WELCOME_SELECTION] = {"path": str(hdf_path), "key": "df"}
    app.run()

    assert not app.exception
    assert app.error
    assert "Available keys: results" in app.error[0].value

    app.text_input[0].set_value("results")
    retry = next(b for b in app.button if b.label == "Retry")
    retry.click()
    app.run()

    assert not app.exception
    assert not app.error
    assert "records selected" in app.sidebar.caption[0].value


def test_welcome_tutorial_click_opens_workbench() -> None:
    app = AppTest.from_function(_welcome_app, default_timeout=120)
    app.run()

    tutorial_button = next(b for b in app.button if b.label == "Open the tutorial dataset")
    tutorial_button.click()
    app.run()

    assert not app.exception
    assert not app.error
    # The default Data page renders the workbench title and the sidebar
    # shows the pipeline summary, proving the full app booted.
    assert [t.value for t in app.title] == ["OnePiece Studio Tutorial Dataset"]
    assert "records selected" in app.sidebar.caption[0].value
