from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from onepiece_studio import DataFrameSource, OnePieceStudioConfig
from onepiece_studio.materials_columns import enrich_materials_dataframe
from onepiece_studio.ui.streamlit_app import run_app

DATA_ROOT = Path(os.environ.get("ONEPIECE_DATA_ROOT", "data/surface_alloys"))

DATASETS = {
    "bulk": DATA_ROOT / "CuGabulk.hdf",
    "bulk_oxide": DATA_ROOT / "CuGabulk_oxide.hdf",
    "cluster": DATA_ROOT / "CuGacluster.hdf",
    "surface_all": DATA_ROOT / "CuGasurf.hdf",
    "surface_100": DATA_ROOT / "CuGasurf_100.hdf",
    "surface_110": DATA_ROOT / "CuGasurf_110.hdf",
    "surface_111": DATA_ROOT / "CuGasurf_111.hdf",
    "surface_211": DATA_ROOT / "CuGasurf_211.hdf",
}

CACHE_PATH = Path(__file__).resolve().parents[1] / "notebooks" / "phase_diagram_outputs" / "cuga_full_dataset.pkl"


def install_pickle_compat() -> None:
    """Compatibility for HDF files written with another NumPy/PyTables stack."""
    import ase.constraints  # noqa: F401
    import numpy.core as numpy_core
    import scipy.linalg  # noqa: F401

    sys.modules.setdefault("numpy._core", numpy_core)
    sys.modules.setdefault("numpy._core.multiarray", np.core.multiarray)
    sys.modules.setdefault("numpy._core.numeric", np.core.numeric)


def load_full_cuga() -> pd.DataFrame:
    if CACHE_PATH.exists():
        return pd.read_pickle(CACHE_PATH)

    install_pickle_compat()
    frames: list[pd.DataFrame] = []
    errors: list[str] = []

    for dataset, path in DATASETS.items():
        try:
            frame = pd.read_hdf(path, key="df").copy()
        except Exception as exc:  # pragma: no cover - shown inside the UI
            errors.append(f"{dataset}: {path.name}: {exc}")
            continue

        frame.insert(0, "dataset", dataset)
        frame.insert(1, "source_hdf", path.name)
        frame.insert(2, "source_row", frame.index.astype(str))
        frames.append(frame.reset_index(drop=True))

    if not frames:
        detail = "\n".join(errors) if errors else "No CuGa HDF files could be read."
        raise RuntimeError(detail)

    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined.attrs["load_errors"] = errors
    return combined


def main() -> None:
    dataframe = enrich_materials_dataframe(load_full_cuga())
    source = DataFrameSource(dataframe, name="Full CuGa HDF collection")
    config = OnePieceStudioConfig(
        title="OnePiece Studio: Full CuGa Local Dataset",
        primary_key="Name",
        structure_columns=["struc", "structure", "atoms"],
        image_columns=["preview_image", "image", "image_path", "thumbnail"],
        searchable_columns=[
            "dataset",
            "source_hdf",
            "Name",
            "Formula",
            "legend",
            "Path",
            "path",
        ],
        metric_columns=[
            "E",
            "formation_energy_per_atom",
            "form_G_per_Area",
            "form_G_per_alloy",
            "fmax",
        ],
    )
    run_app(source, config)


if __name__ == "__main__":
    main()
