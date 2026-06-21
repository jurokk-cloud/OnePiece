from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from onepiece_studio import cli

from onepiece.provenance import ReferenceScheme
from onepiece.qa import SelfTestResult
from onepiece.storage import ensure_storage_layout, resolve_storage_config, save_dataset


def test_doctor_report_includes_core_checks() -> None:
    report = cli._installation_report()

    assert "[INFO] OnePiece Studio environment report" in report
    assert "python:" in report
    assert "bundled dataset:" in report


def test_main_tutorial_launches_bundled_dataset(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, list[str]] = {}

    def _fake_call(command: list[str]) -> int:
        captured["command"] = command
        return 0

    dataset = tmp_path / "tutorial.hdf"
    dataset.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(cli, "bundled_catalysis_hub_dataset", lambda: dataset)
    monkeypatch.setattr(cli.subprocess, "call", _fake_call)

    code = cli.main(["tutorial"])

    assert code == 0
    assert captured["command"][-6:] == [
        "--hdf",
        str(dataset),
        "--key",
        "df",
        "--title",
        "OnePiece Studio Tutorial Dataset",
    ]


def test_status_tags_colored_only_on_tty(monkeypatch) -> None:
    report = "[INFO] header\n[PASS] check one\n[FAIL] check two\n[WARN] hint"

    monkeypatch.setattr(cli, "_use_color", lambda: True)
    colored = cli._colorize_status_tags(report)
    assert "\033[32m[PASS]\033[0m" in colored
    assert "\033[1;31m[FAIL]\033[0m" in colored

    monkeypatch.setattr(cli, "_use_color", lambda: False)
    assert cli._colorize_status_tags(report) == report


def test_no_color_environment_disables_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert cli._use_color() is False


def test_fair_audit_command_passes_publication_metadata_flag(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def _fake_audit(path: str, *, require_reference_scheme: bool, require_publication_metadata: bool):
        captured["path"] = path
        captured["require_reference_scheme"] = require_reference_scheme
        captured["require_publication_metadata"] = require_publication_metadata
        return SelfTestResult(name="fair-provenance", passed=True, details={})

    dataset = tmp_path / "managed-dataset"
    monkeypatch.setattr(cli, "run_fair_provenance_audit", _fake_audit)

    code = cli.main(
        [
            "fair-audit",
            str(dataset),
            "--require-reference-scheme",
            "--require-publication-metadata",
        ]
    )

    assert code == 0
    assert captured == {
        "path": str(dataset),
        "require_reference_scheme": True,
        "require_publication_metadata": True,
    }


def test_ro_crate_command_writes_metadata_for_managed_dataset(tmp_path: Path) -> None:
    config = ensure_storage_layout(resolve_storage_config(tmp_path / ".onepiece"))
    manifest_path = save_dataset(
        pd.DataFrame({"Name": ["row-a"], "E": [1.0]}),
        dataset_id="crate-dataset",
        config=config,
        reference_scheme=ReferenceScheme.gas_phase(
            name="CO2_H2",
            gas_references_eV={"CO2": -22.1, "H2": -6.8},
        ),
    )
    output = tmp_path / "ro-crate-metadata.json"

    code = cli.main(["ro-crate", str(manifest_path.parent), "--output", str(output), "--name", "Crate Dataset"])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["@context"] == "https://w3id.org/ro/crate/1.1/context"
    assert any(item["@id"] == "./" and item["name"] == "Crate Dataset" for item in payload["@graph"])
