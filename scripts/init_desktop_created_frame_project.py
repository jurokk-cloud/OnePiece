from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from onepiece_studio.demo import DEFAULT_LOCAL_HDF, local_default_source  # noqa: E402
from onepiece_studio.ui.workflow_builder import _apply_operation  # noqa: E402

DESKTOP_PROJECT_DIR = Path.home() / "Desktop" / "OnePiece_Studio_created_frame_Project"
WORKSPACES_DIR = DESKTOP_PROJECT_DIR / "workspaces"
DATA_LINKS_DIR = DESKTOP_PROJECT_DIR / "data_links"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _workspace_payload(*, workflow_operations: list[dict], source_rows: int, active_rows: int, title: str) -> dict:
    now = _now()
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


def _workflow_definitions() -> list[tuple[str, str, list[dict]]]:
    return [
        (
            "01_full_local_dataset.onepiece_studio.json",
            "Full local created_frame dataset",
            [],
        ),
        (
            "02_relaxed_structures_fmax_le_0_05.onepiece_studio.json",
            "Relaxed structures with fmax <= 0.05 eV/A",
            [
                {
                    "kind": "filter",
                    "column": "fmax",
                    "operator": "<=",
                    "value": "0.05",
                    "new_column": "",
                    "label": "filter fmax <= 0.05",
                    "enabled": True,
                    "created_at": _now(),
                }
            ],
        ),
        (
            "03_bulk_screening_ready.onepiece_studio.json",
            "Bulk screening with converged rows",
            [
                {
                    "kind": "filter",
                    "column": "Name",
                    "operator": "contains",
                    "value": "bulk",
                    "new_column": "",
                    "label": "filter Name contains 'bulk'",
                    "enabled": True,
                    "created_at": _now(),
                },
                {
                    "kind": "filter",
                    "column": "fmax",
                    "operator": "<=",
                    "value": "0.05",
                    "new_column": "",
                    "label": "filter fmax <= 0.05",
                    "enabled": True,
                    "created_at": _now(),
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
    (DESKTOP_PROJECT_DIR / ".streamlit").mkdir(parents=True, exist_ok=True)
    (DESKTOP_PROJECT_DIR / ".streamlit" / "config.toml").write_text(
        "[browser]\n"
        "gatherUsageStats = false\n",
        encoding="utf-8",
    )

    source, config = local_default_source()
    base = source.load()
    hdf_path = Path(DEFAULT_LOCAL_HDF).expanduser()
    if hdf_path.exists():
        _write_symlink(DATA_LINKS_DIR / hdf_path.name, hdf_path)

    source_rows = len(base)
    workspace_rows = []
    for filename, title, operations in _workflow_definitions():
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

    launch_script = DESKTOP_PROJECT_DIR / "launch_created_frame_ui.command"
    launch_script.write_text(
        "#!/bin/zsh\n"
        "export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false\n"
        f"cd {ROOT}\n"
        "python3 -m onepiece_studio.cli hdf \"$ONEPIECE_STUDIO_DEFAULT_HDF\"\n",
        encoding="utf-8",
    )
    launch_script.chmod(0o755)

    (DESKTOP_PROJECT_DIR / "hdf_sources_manifest.json").write_text(
        json.dumps(
            [
                {
                    "label": hdf_path.name,
                    "path": str(hdf_path),
                    "link": str(DATA_LINKS_DIR / hdf_path.name),
                    "exists": hdf_path.exists(),
                    "local_only": True,
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    (DESKTOP_PROJECT_DIR / "workspace_manifest.json").write_text(
        json.dumps(workspace_rows, indent=2),
        encoding="utf-8",
    )

    readme = DESKTOP_PROJECT_DIR / "README.md"
    readme.write_text(
        "# OnePiece Studio created_frame local project\n\n"
        "This desktop project uses the local `created_frame.hdf` file as the default OnePiece Studio input.\n\n"
        "## Local-only data\n"
        "- The project uses the local file referenced in `data_links/`\n"
        "- No remote storage is configured\n\n"
        "## Included OnePiece Studio workspaces\n"
        "- `workspaces/01_full_local_dataset.onepiece_studio.json`\n"
        "- `workspaces/02_relaxed_structures_fmax_le_0_05.onepiece_studio.json`\n"
        "- `workspaces/03_bulk_screening_ready.onepiece_studio.json`\n\n"
        "## How to use\n"
        "1. Start OnePiece Studio with `launch_created_frame_ui.command`\n"
        "2. In OnePiece Studio open `Data Management -> Project`\n"
        "3. Load one of the workspace files from `workspaces/`\n"
        "4. Continue filtering, visualization, and row inspection locally\n\n"
        "## Default UI input\n"
        f"- `{hdf_path}`\n"
        f"- UI title: `{config.title}`\n",
        encoding="utf-8",
    )

    print(DESKTOP_PROJECT_DIR)
    print(json.dumps(workspace_rows, indent=2))


if __name__ == "__main__":
    main()
