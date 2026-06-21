"""Docstring-example contract for the curated top-level ``onepiece`` API.

Every curated export must carry a docstring with a short runnable example.
Examples written as doctests are executed here so they keep working; the two
examples that need external inputs (a calculation tree, a plotting backend)
are ``.. code-block:: python`` blocks and are only checked for presence.
"""

from __future__ import annotations

import doctest
import importlib

import pytest

import onepiece

# Modules that define the curated top-level names. Doctests are collected from
# the defining module, not from the re-exporting package.
CURATED_MODULES = (
    "onepiece",
    "onepiece.adsorption.energies",
    "onepiece.adsorption.references",
    "onepiece.dftdataframe_import",
    "onepiece.ir",
    "onepiece.qa",
    "onepiece.sources.core",
    "onepiece.storage",
    "onepiece.thermo",
)


@pytest.mark.parametrize("name", sorted(onepiece.__all__))
def test_curated_name_has_docstring_with_example(name: str) -> None:
    doc = getattr(onepiece, name).__doc__ or ""
    assert doc.strip(), f"curated export {name!r} has no docstring"
    assert ">>> " in doc or ".. code-block:: python" in doc, (
        f"curated export {name!r} has no runnable example in its docstring"
    )


@pytest.mark.parametrize("module_name", CURATED_MODULES)
def test_module_doctests_pass(module_name: str) -> None:
    module = importlib.import_module(module_name)
    result = doctest.testmod(module, optionflags=doctest.NORMALIZE_WHITESPACE, verbose=False)
    assert result.failed == 0, f"{result.failed} doctest example(s) failed in {module_name}"


def test_curated_modules_define_doctest_examples() -> None:
    finder = doctest.DocTestFinder()
    example_count = sum(
        len(test.examples)
        for module_name in CURATED_MODULES
        for test in finder.find(importlib.import_module(module_name))
    )
    assert example_count >= 30, (
        f"expected the curated modules to ship plenty of doctest examples, found {example_count}"
    )
