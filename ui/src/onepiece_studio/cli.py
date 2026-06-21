from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import subprocess  # nosec B404
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
from pathlib import Path

from onepiece.provenance import ro_crate_metadata
from onepiece.qa import (
    bundled_catalysis_hub_dataset,
    format_self_test_result,
    run_catalysis_hub_self_test,
    run_fair_provenance_audit,
)
from onepiece.storage import STORAGE_MANIFEST_NAME, read_dataset_manifest

_STATUS_COLORS = {
    "[PASS]": "\033[32m",
    "[FAIL]": "\033[1;31m",
    "[WARN]": "\033[33m",
    "[INFO]": "\033[36m",
}
_RESET = "\033[0m"


def _use_color() -> bool:
    # https://no-color.org/ convention, plus only color real terminals so
    # piped output and CI logs stay plain.
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _colorize_status_tags(text: str) -> str:
    if not _use_color():
        return text
    for tag, code in _STATUS_COLORS.items():
        text = text.replace(tag, f"{code}{tag}{_RESET}")
    return text


def _studio_version() -> str:
    try:
        return _package_version("onepiece-studio")
    except PackageNotFoundError:
        return "unknown (package not installed)"


def main(argv: list[str] | None = None) -> int:
    prog_name = Path(sys.argv[0]).stem if sys.argv and sys.argv[0] else "onepiece-studio"
    parser = argparse.ArgumentParser(
        prog=prog_name,
        description=(
            "Launch OnePiece Studio. With no command, opens a welcome page "
            "where you can pick the tutorial dataset, a local file, or a recent file."
        ),
    )
    parser.add_argument("--version", action="version", version=f"onepiece-studio {_studio_version()}")
    subparsers = parser.add_subparsers(dest="command", required=False)
    subparsers.add_parser("demo", help="Run the OnePiece Studio Streamlit demo.")
    subparsers.add_parser(
        "tutorial",
        help="Open the bundled Catalysis-Hub tutorial dataset in OnePiece Studio.",
    )
    hdf_parser = subparsers.add_parser("hdf", help="Run OnePiece Studio for a pandas HDF file.")
    hdf_parser.add_argument("path", help="Path to a pandas HDF file.")
    hdf_parser.add_argument("--key", default="df", help="HDF key, defaults to 'df'.")
    hdf_parser.add_argument("--title", default=None, help="Optional UI title.")
    qa_parser = subparsers.add_parser("qa", help="Run bundled package self-tests.")
    qa_parser.add_argument(
        "--dataset",
        default=None,
        help="Optional path to a Catalysis-Hub-style HDF file. Defaults to the bundled reference dataset.",
    )
    fair_parser = subparsers.add_parser("fair-audit", help="Audit a managed dataset for FAIR provenance metadata.")
    fair_parser.add_argument("path", help="Path to a managed OnePiece dataset directory or manifest.json.")
    fair_parser.add_argument(
        "--require-reference-scheme",
        action="store_true",
        help="Require a thermodynamic reference scheme in the provenance payload.",
    )
    fair_parser.add_argument(
        "--require-publication-metadata",
        action="store_true",
        help="Require citation and license entries in manifest metadata.",
    )
    crate_parser = subparsers.add_parser("ro-crate", help="Export RO-Crate-style JSON-LD metadata.")
    crate_parser.add_argument("path", help="Path to a managed OnePiece dataset directory or manifest.json.")
    crate_parser.add_argument(
        "--output",
        default=None,
        help="Output path. Defaults to ro-crate-metadata.json next to the manifest.",
    )
    crate_parser.add_argument("--name", default="OnePiece dataset", help="Dataset name for the RO-Crate root node.")
    crate_parser.add_argument("--description", default=None, help="Optional dataset description.")
    subparsers.add_parser("doctor", help="Check whether this environment is ready for OnePiece Studio.")
    args = parser.parse_args(argv)

    if args.command == "qa":
        result = run_catalysis_hub_self_test(args.dataset)
        print(_colorize_status_tags(format_self_test_result(result)))
        return 0 if result.passed else 1

    if args.command == "fair-audit":
        result = run_fair_provenance_audit(
            args.path,
            require_reference_scheme=bool(args.require_reference_scheme),
            require_publication_metadata=bool(args.require_publication_metadata),
        )
        print(_colorize_status_tags(format_self_test_result(result)))
        return 0 if result.passed else 1

    if args.command == "ro-crate":
        output_path = _write_ro_crate_metadata(
            args.path,
            output=args.output,
            name=args.name,
            description=args.description,
        )
        print(f"[PASS] wrote RO-Crate metadata: {output_path}")
        return 0

    if args.command == "doctor":
        report = _installation_report()
        print(_colorize_status_tags(report))
        return 0 if "[FAIL]" not in report else 1

    if args.command in {None, "demo", "tutorial", "hdf"}:
        return _run_streamlit_app(args)

    return 0


def _run_streamlit_app(args: argparse.Namespace) -> int:
    app_path = Path(__file__).parent / "ui" / "streamlit_app.py"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--",
    ]
    if args.command == "demo":
        command.append("--demo")
    elif args.command == "tutorial":
        command.extend(
            [
                "--hdf",
                str(bundled_catalysis_hub_dataset()),
                "--key",
                "df",
                "--title",
                "OnePiece Studio Tutorial Dataset",
            ]
        )
    elif args.command == "hdf":
        command.extend(["--hdf", args.path, "--key", args.key])
        if args.title:
            command.extend(["--title", args.title])
    # Launches a fixed local Streamlit command assembled by the CLI itself.
    return subprocess.call(command)  # nosec B603


def _write_ro_crate_metadata(
    path: str | Path,
    *,
    output: str | Path | None = None,
    name: str = "OnePiece dataset",
    description: str | None = None,
) -> Path:
    manifest_path = _resolve_manifest_path(path)
    manifest = read_dataset_manifest(manifest_path)
    crate = ro_crate_metadata(manifest.provenance, name=name, description=description)
    output_path = Path(output).expanduser() if output else manifest_path.parent / "ro-crate-metadata.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(crate, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _resolve_manifest_path(path: str | Path) -> Path:
    source = Path(path).expanduser()
    if source.is_dir():
        source = source / STORAGE_MANIFEST_NAME
    if source.name != STORAGE_MANIFEST_NAME:
        raise ValueError("RO-Crate export requires a managed OnePiece dataset directory or manifest.json.")
    if not source.exists():
        raise FileNotFoundError(source)
    return source


def _installation_report() -> str:
    lines = [
        "[INFO] OnePiece Studio environment report",
        f"- python: {sys.version.split()[0]}",
        f"- platform: {platform.platform()}",
        f"- executable: {sys.executable}",
    ]
    failures = 0
    for module_name in ["streamlit", "pandas", "tables", "sympy", "ase", "plotly"]:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            lines.append(f"[FAIL] import {module_name}: {exc}")
            failures += 1
        else:
            version = getattr(module, "__version__", "unknown")
            lines.append(f"[PASS] import {module_name}: {version}")

    dataset = bundled_catalysis_hub_dataset()
    if dataset.exists():
        lines.append(f"[PASS] bundled dataset: {dataset}")
    else:
        lines.append(f"[FAIL] bundled dataset missing: {dataset}")
        failures += 1

    lines.append(
        "[PASS] ready to launch UI"
        if failures == 0
        else "[WARN] fix the failed checks above before using OnePiece Studio"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
