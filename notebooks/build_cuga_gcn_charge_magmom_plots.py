from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd

from onepiece import add_atomic_reference_difference_descriptors, save_dataframe_metric_plots_3d
from onepiece.ase_analysis import add_ase_analysis_descriptors

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "phase_diagram_outputs" / "cuga_full_dataset.pkl"
OUTPUT_DIR = ROOT / "phase_diagram_outputs" / "cuga_gcn_reference_plots"
MANIFEST = OUTPUT_DIR / "manifest.csv"


def load_dataset() -> pd.DataFrame:
    return pickle.loads(DATASET.read_bytes())


def build_plots() -> pd.DataFrame:
    frame = load_dataset()
    frame = add_atomic_reference_difference_descriptors(frame, charge_source="acf", structure_column="struc")
    frame = add_ase_analysis_descriptors(frame, structure_column="struc")
    metrics = [
        "atomic_generalized_coordination_numbers",
        "atomic_charge_delta_vs_surface_ref_e",
        "atomic_charge_delta_vs_gas_ref_e",
        "atomic_charge_delta_vs_valence_ref_e",
        "atomic_magnetic_moment_delta_vs_surface_ref",
        "atomic_magnetic_moment_delta_vs_gas_ref",
    ]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = save_dataframe_metric_plots_3d(frame, metrics, output_dir=OUTPUT_DIR)
    manifest.to_csv(MANIFEST, index=False)
    return manifest


if __name__ == "__main__":
    result = build_plots()
    print(f"generated {len(result)} plots in {OUTPUT_DIR}")
