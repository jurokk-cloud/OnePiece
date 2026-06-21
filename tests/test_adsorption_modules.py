"""Seam tests for the onepiece.adsorption subpackage split."""

from __future__ import annotations

import pandas as pd

import onepiece.adsorption as adsorption_package
from onepiece.adsorption import copt, energies, formulas, references

PUBLIC_NAMES = (
    # formulas
    "ADSORBATE_PATTERN",
    "DEFAULT_ADSORBATE_TOKENS",
    "FORMULA_PATTERN",
    "NAME_COPT_PATTERN",
    "add_element_count_columns",
    "adsorbate_counts_from_structures",
    "atom_counts",
    "count_element",
    "count_element_in_structure",
    "formula_counts",
    "get_all_elements",
    "guess_adsorbate",
    "primary_structure",
    "row_element_count_map",
    "row_elements",
    "structure_columns_in_frame",
    "surface_key_from_name",
    # references
    "DEFAULT_FORMULA_GAS_SPECIES",
    "EQUATION_TOKEN_PATTERN",
    "GasReferences",
    "NON_METAL_REFERENCE_ELEMENTS",
    "annotate_adsorbates",
    "assign_references_before_merge",
    "assign_surface_references",
    "choose_surface_references",
    "default_room_temperature_phase",
    "infer_adsorbate_recipe",
    "infer_adsorption_recipes",
    "infer_reference_equation_from_formula",
    "parse_reference_equation",
    "read_onepiece_hdf",
    "read_onepiece_hdfs",
    # energies
    "add_adsorption_energies",
    "add_catalysis_hub_adsorption_energies",
    "add_elemental_adsorption_energy",
    "add_elemental_adsorption_free_energy",
    "add_recipe_adsorption_energies",
    "adsorption_view",
    # copt
    "annotate_copt_paths",
    "copt_barrier_summary",
    "copt_profile_points",
    "is_constrained_optimization",
)


def test_package_reexports_every_previously_public_name() -> None:
    missing = [name for name in PUBLIC_NAMES if not hasattr(adsorption_package, name)]
    assert not missing


def test_submodule_objects_are_the_package_objects() -> None:
    assert adsorption_package.formula_counts is formulas.formula_counts
    assert adsorption_package.assign_surface_references is references.assign_surface_references
    assert adsorption_package.add_adsorption_energies is energies.add_adsorption_energies
    assert adsorption_package.copt_barrier_summary is copt.copt_barrier_summary


def test_formulas_module_parses_formula_counts_standalone() -> None:
    assert formulas.formula_counts("CH3Ni4O") == {"C": 1, "H": 3, "Ni": 4, "O": 1}
    assert formulas.guess_adsorbate("Ni-211-clean-1x1-CO-1") == "CO"
    assert formulas.surface_key_from_name("Ni-211-clean-1x1-CO-1") == "Ni-211-clean-1x1"


def test_references_module_assigns_surface_references_standalone() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["Ni-211-clean-1x1", "Ni-211-clean-1x1-CO-1"],
            "Formula": ["Ni4", "CNi4O"],
            "E": [-10.0, -25.0],
            "C": [0, 1],
            "H": [0, 0],
            "O": [0, 1],
        }
    )
    result = references.assign_surface_references(frame)
    row = result.loc[result["Name"] == "Ni-211-clean-1x1-CO-1"].iloc[0]
    assert row["surface_ref_name"] == "Ni-211-clean-1x1"
    assert row["surface_ref_status"] == "ok"


def test_energies_module_computes_co_adsorption_standalone() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["Ni-211-clean-1x1", "Ni-211-clean-1x1-CO-1"],
            "Formula": ["Ni4", "CNi4O"],
            "E": [-10.0, -25.0],
            "C": [0, 1],
            "H": [0, 0],
            "O": [0, 1],
        }
    )
    referenced = references.assign_surface_references(frame)
    result = energies.add_adsorption_energies(referenced, {"CO": -14.0})
    row = result.loc[result["Name"] == "Ni-211-clean-1x1-CO-1"].iloc[0]
    assert row["E_ads_CO_eV"] == -1.0


def test_copt_module_detects_constrained_optimization_rows() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["Ni-211-clean-1x1", "Ni-211-copt-CO_H%HCO-1-00"],
            "Path": ["/tmp/clean", "/tmp/copt/CO_H%HCO/1/00"],
            "E": [-10.0, -9.0],
        }
    )
    mask = copt.is_constrained_optimization(frame)
    assert mask.tolist() == [False, True]


def test_each_submodule_stays_focused() -> None:
    # The split's point: no module re-grows past the ~400-line budget.
    # Docstrings are excluded from the count: the curated-API work requires
    # examples in them, and the budget guards code complexity, not docs.
    import ast
    from pathlib import Path

    package_dir = Path(adsorption_package.__file__).parent
    for module in ("formulas.py", "references.py", "energies.py", "copt.py"):
        source = (package_dir / module).read_text()
        docstring_lines = 0
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                docstring_lines += body[0].end_lineno - body[0].lineno + 1
        line_count = len(source.splitlines()) - docstring_lines
        assert line_count < 400, f"{module} has {line_count} non-docstring lines"
