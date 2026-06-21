from __future__ import annotations

from pathlib import Path

import pandas as pd

from onepiece import bundled_catalysis_hub_dataset, run_catalysis_hub_self_test
from onepiece.provenance import ReferenceScheme
from onepiece.qa import run_fair_provenance_audit
from onepiece.storage import ensure_storage_layout, resolve_storage_config, save_dataset


def test_bundled_catalysis_hub_dataset_exists() -> None:
    path = bundled_catalysis_hub_dataset()

    assert isinstance(path, Path)
    assert path.exists()
    assert path.name == "catalysis_hub_co2_subset.hdf"


def test_catalysis_hub_self_test_passes_on_bundled_dataset() -> None:
    result = run_catalysis_hub_self_test()

    assert result.passed is True
    assert result.details["rows"] > 0
    assert result.details["adsorbate_rows"] > 0
    assert result.details["computed_adsorption_rows"] > 0
    assert result.details["max_abs_delta_vs_reaction_energy_ev"] is not None
    assert result.details["max_abs_delta_vs_reaction_energy_ev"] < 1e-8


def test_fair_provenance_audit_passes_for_managed_dataset_with_reference_scheme(tmp_path: Path) -> None:
    config = ensure_storage_layout(resolve_storage_config(tmp_path / ".onepiece"))
    scheme = ReferenceScheme.gas_phase(
        name="CO2_H2",
        gas_references_eV={"CO2": -22.1, "H2": -6.8},
    )
    manifest_path = save_dataset(
        pd.DataFrame({"Name": ["row-a"], "E": [1.0]}),
        dataset_id="fair-dataset",
        config=config,
        reference_scheme=scheme,
        metadata={
            "license": "CC-BY-4.0",
            "citation": "Doe et al., Example Catalysis Dataset, 2026.",
        },
    )

    result = run_fair_provenance_audit(
        manifest_path.parent,
        require_reference_scheme=True,
        require_publication_metadata=True,
    )

    assert result.passed is True
    assert result.details["manifest_present"] is True
    assert result.details["dataset_id"] == "fair-dataset"
    assert result.details["provenance_activities"] == 1
    assert result.details["metadata_keys"] == ["citation", "license"]


def test_fair_provenance_audit_fails_when_publication_metadata_required(tmp_path: Path) -> None:
    config = ensure_storage_layout(resolve_storage_config(tmp_path / ".onepiece"))
    manifest_path = save_dataset(
        pd.DataFrame({"Name": ["row-a"], "E": [1.0]}),
        dataset_id="missing-publication-metadata",
        config=config,
        reference_scheme=ReferenceScheme.gas_phase(
            name="CO2_H2",
            gas_references_eV={"CO2": -22.1, "H2": -6.8},
        ),
        metadata={"license": "CC-BY-4.0"},
    )

    result = run_fair_provenance_audit(
        manifest_path.parent,
        require_reference_scheme=True,
        require_publication_metadata=True,
    )

    assert result.passed is False
    assert "citation" in result.details["errors"][0]


def test_fair_provenance_audit_fails_for_bare_hdf(tmp_path: Path) -> None:
    path = tmp_path / "bare.hdf"
    pd.DataFrame({"Name": ["row-a"], "E": [1.0]}).to_hdf(path, key="df")

    result = run_fair_provenance_audit(path)

    assert result.passed is False
    assert result.details["manifest_present"] is False
    assert "save_dataset" in result.details["errors"][0]
