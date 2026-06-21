"""Welcome screen shown when OnePiece Studio starts without a dataset."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from onepiece import bundled_catalysis_hub_dataset
from onepiece.sources.core import read_uploaded_hdf
from onepiece_studio.adapters import HDFSource
from onepiece_studio.config import OnePieceStudioConfig
from onepiece_studio.state import WELCOME_SELECTION

MAX_RECENT_FILES = 8


def standard_hdf_config(title: str) -> OnePieceStudioConfig:
    """Default workbench configuration for OnePiece-style HDF datasets."""
    return OnePieceStudioConfig(
        title=title,
        primary_key="Name",
        structure_columns=["struc", "CONTCAR", "structure", "atoms"],
        searchable_columns=[
            "Name",
            "Formula",
            "Path",
            "dataset",
            "dataset_label",
            "source_hdf",
        ],
        metric_columns=[
            "E",
            "fmax",
            "formation_energy_per_atom",
            "form_G_per_Area",
            "form_G_per_alloy",
            "a",
            "b",
            "c",
            "gamma",
            "timestamp",
        ],
    )


def tutorial_selection() -> dict[str, Any]:
    return {
        "path": str(bundled_catalysis_hub_dataset()),
        "key": "df",
        "title": "OnePiece Studio Tutorial Dataset",
    }


def source_from_selection(selection: dict[str, Any]) -> tuple[HDFSource, OnePieceStudioConfig]:
    path = Path(selection["path"])
    key = selection.get("key") or "df"
    title = selection.get("title") or f"OnePiece Studio: {path.name}"
    return HDFSource(path, key=key, name=path.name), standard_hdf_config(title)


def recent_files_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config_home / "onepiece-studio" / "recent_files.json"


def load_recent_files() -> list[dict[str, str]]:
    try:
        entries = json.loads(recent_files_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(entries, list):
        return []
    valid = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("path"):
            valid.append({"path": str(entry["path"]), "key": str(entry.get("key") or "df")})
    return valid[:MAX_RECENT_FILES]


def remember_recent_file(path: str | Path, key: str = "df") -> None:
    entry = {"path": str(Path(path).expanduser()), "key": key or "df"}
    entries = [item for item in load_recent_files() if item["path"] != entry["path"]]
    entries.insert(0, entry)
    target = recent_files_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(entries[:MAX_RECENT_FILES], indent=2), encoding="utf-8")
    except OSError:
        pass


def run_welcome() -> None:
    """Render the welcome page, or hand over to the workbench once a dataset is picked."""
    import streamlit as st

    from onepiece_studio.ui.streamlit_app import run_app

    selection = st.session_state.get(WELCOME_SELECTION)
    if selection:
        source, config = source_from_selection(selection)
        try:
            source.load()
        except Exception as exc:
            _render_load_failure(st, selection, exc)
            return
        run_app(source, config)
        return

    _render_welcome_page(st)


def _render_load_failure(st: Any, selection: dict[str, Any], exc: Exception) -> None:
    st.set_page_config(page_title="OnePiece Studio", page_icon="PF", layout="centered")
    st.title("OnePiece Studio")
    st.error(f"**Could not open this dataset.**\n\n{exc}")
    retry_key = st.text_input("Try a different HDF key", value=selection.get("key") or "df")
    action_columns = st.columns(2)
    if action_columns[0].button("Retry", type="primary"):
        st.session_state[WELCOME_SELECTION] = {**selection, "key": retry_key}
        st.rerun()
    if action_columns[1].button("Back to welcome page"):
        del st.session_state[WELCOME_SELECTION]
        st.rerun()


def _render_welcome_page(st: Any) -> None:
    st.set_page_config(page_title="OnePiece Studio", page_icon="PF", layout="centered")
    st.title("OnePiece Studio")
    st.caption(
        "A local workbench for atomistic simulation datasets: adsorption energies, "
        "thermochemistry, charges, and dataset QA."
    )

    st.subheader("New here?")
    st.write("Explore the bundled Catalysis-Hub dataset — nothing to download or configure.")
    if st.button("Open the tutorial dataset", type="primary"):
        st.session_state[WELCOME_SELECTION] = tutorial_selection()
        st.rerun()

    st.subheader("Open your data")
    path_column, key_column = st.columns([0.75, 0.25])
    path_text = path_column.text_input(
        "Path to a pandas HDF file or parquet dataset directory",
        placeholder="/path/to/database.hdf",
    )
    key_text = key_column.text_input("HDF key", value="df")
    if st.button("Open file", disabled=not path_text.strip()):
        path = Path(path_text.strip()).expanduser()
        if path.exists():
            remember_recent_file(path, key_text)
            st.session_state[WELCOME_SELECTION] = {"path": str(path), "key": key_text}
            st.rerun()
        else:
            st.error(f"No file or directory at `{path}`. Check the path and try again.")

    uploaded = st.file_uploader("...or upload an HDF file", type=["hdf", "h5", "hdf5"])
    if uploaded is not None:
        try:
            _frame, temp_path = read_uploaded_hdf(uploaded, key=key_text or "df")
        except Exception as exc:
            st.error(f"**Could not read the uploaded file.**\n\n{exc}")
        else:
            st.session_state[WELCOME_SELECTION] = {
                "path": str(temp_path),
                "key": key_text or "df",
                "title": f"OnePiece Studio: {uploaded.name}",
            }
            st.rerun()

    recent = load_recent_files()
    if recent:
        st.subheader("Recent files")
        for index, entry in enumerate(recent):
            entry_path = Path(entry["path"])
            label_column, button_column = st.columns([0.8, 0.2])
            label_column.write(f"`{entry_path}`")
            if button_column.button("Open", key=f"onepiece_studio_recent_{index}", disabled=not entry_path.exists()):
                remember_recent_file(entry_path, entry["key"])
                st.session_state[WELCOME_SELECTION] = {"path": entry["path"], "key": entry["key"]}
                st.rerun()

    st.divider()
    st.caption(
        "Tip: you can also launch directly with "
        "`onepiece-studio hdf /path/to/database.hdf --key df`, or run "
        "`onepiece-studio doctor` to check your installation."
    )
