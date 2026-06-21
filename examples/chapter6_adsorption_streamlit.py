from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from onepiece_studio import DataFrameSource, OnePieceStudioConfig
from onepiece_studio.ui.streamlit_app import run_app

from onepiece import add_adsorption_energies, assign_references_before_merge

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("ONEPIECE_DATA_ROOT", "data/chapter6"))
GAS_HDF = Path(os.environ.get("ONEPIECE_DATA_ROOT", "data/chapter6")).parent / "Gas.hdf"
CACHE_PATH = (
    PROJECT_ROOT
    / "notebooks"
    / "adsorption_barrier_software"
    / "outputs"
    / "chapter6_adsorption_barrier_dataset.pkl"
)
GAS_CACHE_PATH = (
    PROJECT_ROOT
    / "notebooks"
    / "adsorption_barrier_software"
    / "outputs"
    / "gas_references.pkl"
)

HDF_FILES = {
    "CaO-slabs": DATA_ROOT / "CaO-slabs.hdf",
    "Ga2O3-slabs": DATA_ROOT / "Ga2O3-slabs.hdf",
    "Ni-slabs": DATA_ROOT / "Ni-slabs.hdf",
    "Ni3Ga": DATA_ROOT / "Ni3Ga.hdf",
    "Ni5Ga3-slabs": DATA_ROOT / "Ni5Ga3-slabs.hdf",
    "NiO-slabs": DATA_ROOT / "NiO-slabs.hdf",
}


def install_pickle_compat() -> None:
    import ase.constraints  # noqa: F401
    import numpy.core as numpy_core
    import scipy.linalg  # noqa: F401

    sys.modules.setdefault("numpy._core", numpy_core)
    sys.modules.setdefault("numpy._core.multiarray", np.core.multiarray)
    sys.modules.setdefault("numpy._core.numeric", np.core.numeric)


def load_chapter6() -> pd.DataFrame:
    install_pickle_compat()
    if CACHE_PATH.exists():
        return _append_gas_references(pd.read_pickle(CACHE_PATH))

    combined, _references = assign_references_before_merge(HDF_FILES)
    return _append_gas_references(add_adsorption_energies(combined))


def _append_gas_references(dataframe: pd.DataFrame) -> pd.DataFrame:
    if not GAS_CACHE_PATH.exists() and not GAS_HDF.exists():
        return dataframe
    if "source_hdf" in dataframe.columns and dataframe["source_hdf"].astype(str).eq(str(GAS_HDF)).any():
        return dataframe

    if GAS_CACHE_PATH.exists():
        gas = pd.read_pickle(GAS_CACHE_PATH).copy()
    else:
        gas = pd.read_hdf(GAS_HDF, key="df").copy()
    gas.insert(0, "dataset", "gas")
    gas.insert(1, "dataset_label", "Gas")
    gas.insert(2, "source_hdf", str(GAS_HDF))
    gas.insert(3, "source_row", gas.index.astype(str))
    gas["record_type"] = "gas_reference"
    gas["is_adsorbate"] = False
    gas["adsorbate"] = ""
    gas["surface_ref_status"] = "gas"
    gas["surface_key"] = gas["Name"].astype(str)
    return pd.concat([dataframe, gas], ignore_index=True, sort=False)


def main() -> None:
    dataframe = load_chapter6()
    source = DataFrameSource(dataframe, name="Chapter 6 adsorption/barrier HDF collection")
    config = OnePieceStudioConfig(
        title="OnePiece Studio: Chapter 6 Adsorption & Barriers",
        primary_key="Name",
        structure_columns=["struc", "structure", "atoms"],
        image_columns=["preview_image", "image", "image_path", "thumbnail"],
        searchable_columns=[
            "dataset",
            "dataset_label",
            "source_hdf",
            "Name",
            "Formula",
            "Path",
            "adsorbate",
            "surface_ref_name",
            "copt_reaction",
        ],
        metric_columns=[
            "E",
            "surface_ref_E",
            "delta_E_to_surface_eV",
            "E_ads_CO_eV",
            "E_ads_CH3OH_to_CH3O_eV",
            "fmax",
        ],
    )
    run_app(source, config)


if __name__ == "__main__":
    main()
