from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from examples.chapter6_adsorption_streamlit import GAS_HDF, HDF_FILES, load_chapter6  # noqa: E402
from onepiece_studio.ui.workflow_builder import _apply_operation  # noqa: E402

DESKTOP_PROJECT_DIR = Path.home() / "Desktop" / "OnePiece_Studio_Chapter6_Adsorption_Project"
WORKSPACES_DIR = DESKTOP_PROJECT_DIR / "workspaces"
DATA_LINKS_DIR = DESKTOP_PROJECT_DIR / "data_links"

GAS_REFS = {"CO": -12.0648225, "CH3OH": -27.74199745, "H2": -7.16386955}


def _workspace_payload(*, workflow_operations: list[dict], source_rows: int, active_rows: int, title: str) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "project_version": 1,
        "saved_at": now,
        "source_rows": int(source_rows),
        "active_rows": int(active_rows),
        "query": {},
        "workflow": workflow_operations,
        "row_states": {},
        "workbook_edits": {},
        "sources": [],
        "saved_views": {},
        "audit_log": [{"time": now, "action": f"Initialized desktop workspace: {title}"}],
    }


def _analysis_workspaces() -> list[tuple[str, str, list[dict]]]:
    return [
        (
            "01_full_dataset_with_adsorption_columns.onepiece_studio.json",
            "Full dataset with adsorption columns",
            [
                {
                    "kind": "derive_adsorption_columns",
                    "gas_references": GAS_REFS,
                    "label": "assign surface references and derive adsorption columns",
                    "enabled": True,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            ],
        ),
        (
            "02_co_adsorption_analysis_ready.onepiece_studio.json",
            "CO adsorption analysis ready",
            [
                {
                    "kind": "derive_adsorption_columns",
                    "gas_references": GAS_REFS,
                    "label": "calculate CO adsorption energy per CO from dataset references",
                    "preset": "co_adsorption_per_co",
                    "enabled": True,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
                {
                    "kind": "filter",
                    "column": "adsorbate",
                    "operator": "equals",
                    "value": "CO",
                    "new_column": "",
                    "label": "filter adsorbate equals 'CO'",
                    "enabled": True,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
                {
                    "kind": "filter",
                    "column": "E_ads_CO_eV",
                    "operator": "is not empty",
                    "value": "",
                    "new_column": "",
                    "label": "filter E_ads_CO_eV is not empty",
                    "enabled": True,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            ],
        ),
        (
            "03_ch3o_adsorption_analysis_ready.onepiece_studio.json",
            "CH3O adsorption analysis ready",
            [
                {
                    "kind": "derive_adsorption_columns",
                    "gas_references": GAS_REFS,
                    "label": "assign surface references and derive adsorption columns",
                    "enabled": True,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
                {
                    "kind": "filter",
                    "column": "adsorbate",
                    "operator": "equals",
                    "value": "CH3O",
                    "new_column": "",
                    "label": "filter adsorbate equals 'CH3O'",
                    "enabled": True,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
                {
                    "kind": "filter",
                    "column": "E_ads_CH3OH_to_CH3O_eV",
                    "operator": "is not empty",
                    "value": "",
                    "new_column": "",
                    "label": "filter E_ads_CH3OH_to_CH3O_eV is not empty",
                    "enabled": True,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            ],
        ),
    ]


def _workflow_result_rows(base, operations: list[dict]) -> int:
    frame = base.copy()
    for operation in operations:
        frame = _apply_operation(frame, operation)
    return len(frame)


def _write_symlink(link: Path, target: Path) -> None:
    if link.exists() or link.is_symlink():
        if link.resolve() == target.resolve():
            return
        link.unlink()
    link.symlink_to(target)


def main() -> None:
    DESKTOP_PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    DATA_LINKS_DIR.mkdir(parents=True, exist_ok=True)

    data_paths = {**HDF_FILES, "Gas": GAS_HDF}
    manifest = []
    for label, path in data_paths.items():
        path = Path(path)
        link = DATA_LINKS_DIR / path.name
        if path.exists():
            _write_symlink(link, path)
            exists = True
        else:
            exists = False
        manifest.append({"label": label, "path": str(path), "link": str(link), "exists": exists})

    base = load_chapter6()
    source_rows = len(base)
    workspace_rows = []
    for filename, title, operations in _analysis_workspaces():
        active_rows = _workflow_result_rows(base, operations)
        payload = _workspace_payload(
            workflow_operations=operations,
            source_rows=source_rows,
            active_rows=active_rows,
            title=title,
        )
        target = WORKSPACES_DIR / filename
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        workspace_rows.append({"file": filename, "title": title, "active_rows": active_rows})

    launch_script = DESKTOP_PROJECT_DIR / "launch_chapter6_ui.command"
    launch_script.write_text(
        "#!/bin/zsh\n"
        f"cd {ROOT}\n"
        "python3 -m onepiece_studio.cli hdf examples/chapter6_adsorption_demo.hdf\n",
        encoding="utf-8",
    )
    launch_script.chmod(0o755)

    (DESKTOP_PROJECT_DIR / "hdf_sources_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    (DESKTOP_PROJECT_DIR / "workspace_manifest.json").write_text(
        json.dumps(workspace_rows, indent=2),
        encoding="utf-8",
    )

    readme = DESKTOP_PROJECT_DIR / "README.md"
    readme.write_text(
        "# OnePiece Studio Chapter 6 Adsorption Project\n\n"
        "This desktop project contains prepared OnePiece Studio workspaces for the Chapter 6 adsorption/barrier dataset.\n\n"
        "## Included HDF data\n"
        "- Symlinks to the original HDF files are in `data_links/`\n"
        "- The full source list is in `hdf_sources_manifest.json`\n\n"
        "## Included OnePiece Studio workspaces\n"
        "- `workspaces/01_full_dataset_with_adsorption_columns.onepiece_studio.json`\n"
        "- `workspaces/02_co_adsorption_analysis_ready.onepiece_studio.json`\n"
        "- `workspaces/03_ch3o_adsorption_analysis_ready.onepiece_studio.json`\n\n"
        "## How to use\n"
        "1. Start the UI with `launch_chapter6_ui.command` or run the Streamlit command manually.\n"
        "2. In OnePiece Studio open `Data Management -> Project`.\n"
        "3. Load one of the `.onepiece_studio.json` files from `workspaces/`.\n"
        "4. Continue the saved workflow, inspect rows, and visualize the prepared adsorption columns.\n",
        encoding="utf-8",
    )

    print(DESKTOP_PROJECT_DIR)
    print(json.dumps(workspace_rows, indent=2))


if __name__ == "__main__":
    main()
