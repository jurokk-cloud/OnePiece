from __future__ import annotations

import pandas as pd
from ase import Atoms

from onepiece.services import record_type_series, row_atom_counts, row_element_counts


def test_record_type_series_classifies_rows_and_respects_explicit_column() -> None:
    frame = pd.DataFrame(
        {
            "Name": ["Cu-211-clean", "Cu-211-CO-1", "slab-relax", "plain-row"],
            "record_type": [None, None, None, "custom"],
        }
    )

    labels = record_type_series(frame)

    assert labels.tolist() == ["clean_surface", "adsorbate", "calculation", "custom"]


def test_row_element_counts_counts_distinct_elements_from_structures() -> None:
    frame = pd.DataFrame({"struc": [Atoms("Cu3"), Atoms("CO2")]})

    counts = row_element_counts(frame)

    assert counts.tolist() == [1, 2]


def test_row_atom_counts_prefers_n_atoms_column() -> None:
    frame = pd.DataFrame({"n_atoms": [4, "7", None]})

    counts = row_atom_counts(frame)

    assert counts.tolist()[:2] == [4.0, 7.0]
    assert pd.isna(counts.tolist()[2])


def test_row_atom_counts_falls_back_to_structures() -> None:
    frame = pd.DataFrame({"struc": [Atoms("Cu3"), Atoms("CO2")]})

    counts = row_atom_counts(frame)

    assert counts.tolist() == [3.0, 3.0]
