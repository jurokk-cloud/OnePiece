from __future__ import annotations

import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from onepiece_studio.adapters import row_key_from_row, row_keys
from onepiece_studio.state import (
    CONTROL_STATUS,
    CONTROL_USE_STATUS,
    CONTROL_VISIBLE_STATES,
)

__all__ = [
    "first_atoms",
    "is_atoms",
    "open_atoms_in_ase",
    "render_action_grid",
    "row_key_from_row",
    "row_keys",
    "selected_dataframe_index",
    "selected_plot_index",
    "selected_row_summary",
    "set_row_status",
]


def set_row_status(st: Any, row_key: str, status: str) -> None:
    state = st.session_state.setdefault(CONTROL_STATUS, {})
    state[row_key] = status
    st.session_state[CONTROL_USE_STATUS] = True
    st.session_state.setdefault(CONTROL_VISIBLE_STATES, ["included", "review", "reference"])


def first_atoms(row: pd.Series) -> tuple[str | None, Any | None]:
    for column in ["struc", "CONTCAR", "structure", "atoms"]:
        if column in row.index and is_atoms(row[column]):
            return column, row[column]
    for column, value in row.items():
        if is_atoms(value):
            return str(column), value
    return None, None


def is_atoms(value: Any) -> bool:
    return value.__class__.__name__ == "Atoms"


def open_atoms_in_ase(value: Any, *, label: str) -> Path:
    from ase.io import write

    safe_label = "".join(character if character.isalnum() else "_" for character in label)[:80]
    directory = Path(tempfile.gettempdir()) / "onepiece_studio_ase_views"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{safe_label or 'structure'}_{id(value)}.traj"
    write(path, value)

    # Launches a local ASE viewer for a temporary trusted structure file.
    subprocess.Popen(  # nosec B603
        [
            sys.executable,
            "-c",
            (
                "from ase.io import read; "
                "from ase.visualize import view; "
                f"atoms = read({str(path)!r}); "
                "view(atoms)"
            ),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return path


def render_action_grid(
    st: Any,
    row: pd.Series,
    index: Any,
    *,
    key_prefix: str,
    namespace: str,
    exclude_label: str = "Exclude",
    review_label: str = "Review",
    reference_label: str = "Reference",
    open_label: str = "Open ASE",
) -> None:
    row_key = row_key_from_row(row, index)
    top = st.columns(2, gap="small")
    bottom = st.columns(2, gap="small")
    if top[0].button(exclude_label, key=f"{namespace}_{key_prefix}_exclude_{row_key}", width="stretch"):
        set_row_status(st, row_key, "excluded")
        st.rerun()
    if top[1].button(review_label, key=f"{namespace}_{key_prefix}_review_{row_key}", width="stretch"):
        set_row_status(st, row_key, "review")
        st.rerun()
    if bottom[0].button(reference_label, key=f"{namespace}_{key_prefix}_reference_{row_key}", width="stretch"):
        set_row_status(st, row_key, "reference")
        st.rerun()

    atoms_column, atoms = first_atoms(row)
    if atoms is None:
        bottom[1].button(open_label, disabled=True, key=f"{namespace}_{key_prefix}_ase_disabled_{row_key}", width="stretch")
        return
    if bottom[1].button(open_label, key=f"{namespace}_{key_prefix}_ase_{row_key}", width="stretch"):
        try:
            path = open_atoms_in_ase(atoms, label=str(row.get("Name", index)))
        except Exception as exc:
            st.error(f"Could not open ASE viewer: {exc}")
        else:
            st.success(f"Opened {atoms_column} in ASE viewer. Temporary file: {path}")


def selected_row_summary(row: pd.Series) -> pd.DataFrame:
    columns = [
        column
        for column in [
            "dataset",
            "dataset_label",
            "source_hdf",
            "source_row",
            "Name",
            "Formula",
            "E",
            "fmax",
            "form_G_per_Area",
            "form_G_per_alloy",
            "formation_energy_per_atom",
            "quality_flag",
            "Path",
        ]
        if column in row.index
    ]
    return pd.DataFrame([{column: _display_value(row[column]) for column in columns}])


def selected_dataframe_index(event: Any, display: pd.DataFrame) -> Any | None:
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    rows = getattr(selection, "rows", None)
    if rows is None and isinstance(selection, dict):
        rows = selection.get("rows")
    if not rows:
        return None
    position = int(rows[0])
    if position >= len(display):
        return None
    return display.index[position]


def selected_plot_index(event: Any) -> int | str | None:
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    points = getattr(selection, "points", None)
    if points is None and isinstance(selection, dict):
        points = selection.get("points")
    if not points:
        return None
    point = points[0]
    customdata = getattr(point, "customdata", None)
    if customdata is None and isinstance(point, dict):
        customdata = point.get("customdata")
    if not customdata:
        return None
    raw = customdata[0]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return raw


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
