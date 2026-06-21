from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def is_gas_phase_row(row: pd.Series) -> bool:
    """Heuristically identify gas-phase reference rows."""
    record_class = str(row.get("record_class", "")).strip().lower()
    if record_class in {"gas", "gas_reference", "gas-phase", "gas_phase"}:
        return True
    for column in ("Name", "Path", "path"):
        text = str(row.get(column, "")).lower()
        if "gasphases" in text or "/gas/" in text or "-gas-" in text:
            return True
    return False


def gas_free_energy(row: pd.Series, temperature: float, energy_column: str = "E") -> float:
    """Compute gas-phase Gibbs free energy for one row.

    Adds zero-point energy and translational, rotational, and vibrational
    heat-capacity terms, minus ``T * S`` from the matching entropy columns.
    Energies are in eV, entropies in eV/K, temperature in K.

    Examples
    --------
    >>> import pandas as pd
    >>> import onepiece
    >>> row = pd.Series({"E": -14.0, "E_ZPE": 0.1,
    ...                  "Cv_trans": 0.04, "Cv_rot": 0.03, "Cv_vib": 0.01,
    ...                  "S_trans": 0.0015, "S_rot": 0.0005, "S_vib": 0.0001})
    >>> round(onepiece.gas_free_energy(row, temperature=300.0), 2)
    -14.45
    """
    return (
        float(row[energy_column])
        + float(row["E_ZPE"])
        + float(row["Cv_trans"])
        + float(row["Cv_rot"])
        + float(row["Cv_vib"])
        - float(temperature) * (float(row["S_trans"]) + float(row["S_rot"]) + float(row["S_vib"]))
    )


def adsorbate_free_energy(row: pd.Series, temperature: float, energy_column: str = "E") -> float:
    """Compute adsorbate or surface Gibbs free energy for one row.

    Like :func:`gas_free_energy` but in the harmonic limit: only zero-point
    energy and vibrational contributions, since translation and rotation are
    frustrated on the surface.

    Examples
    --------
    >>> import pandas as pd
    >>> import onepiece
    >>> row = pd.Series({"E": -120.0, "E_ZPE": 0.2, "Cv_vib": 0.05, "S_vib": 0.001})
    >>> round(onepiece.adsorbate_free_energy(row, temperature=300.0), 2)
    -120.05
    """
    return (
        float(row[energy_column])
        + float(row["E_ZPE"])
        + float(row["Cv_vib"])
        - float(temperature) * float(row["S_vib"])
    )


def add_gibbs_free_energy(
    frame: pd.DataFrame,
    temperature: float,
    *,
    energy_column: str = "E",
    output_column: str = "G",
) -> pd.DataFrame:
    """Add a Gibbs free-energy column using available thermochemistry data.

    Gas-phase rows use translational, rotational, and vibrational contributions.
    Adsorbate and surface rows use vibrational contributions only. Rows missing
    the required thermochemistry columns keep ``NaN`` in the output column.

    Examples
    --------
    >>> import pandas as pd
    >>> import onepiece
    >>> frame = pd.DataFrame([{"Name": "Cu211-CO", "E": -120.0, "E_ZPE": 0.2,
    ...                        "Cv_vib": 0.05, "S_vib": 0.001}])
    >>> out = onepiece.add_gibbs_free_energy(frame, temperature=300.0)
    >>> round(float(out.loc[0, "G"]), 2)
    -120.05
    """
    df = frame.copy()
    df[output_column] = np.nan
    required_adsorbate = [energy_column, "E_ZPE", "Cv_vib", "S_vib"]
    required_gas = [energy_column, "E_ZPE", "Cv_trans", "Cv_rot", "Cv_vib", "S_trans", "S_rot", "S_vib"]

    def _coerce(value: Any) -> float:
        return float(pd.to_numeric(value, errors="coerce"))

    for index, row in df.iterrows():
        try:
            if is_gas_phase_row(row):
                if any(pd.isna(pd.to_numeric(row.get(column), errors="coerce")) for column in required_gas):
                    continue
                df.at[index, output_column] = gas_free_energy(row, temperature=temperature, energy_column=energy_column)
            else:
                if any(pd.isna(pd.to_numeric(row.get(column), errors="coerce")) for column in required_adsorbate):
                    continue
                df.at[index, output_column] = adsorbate_free_energy(row, temperature=temperature, energy_column=energy_column)
        except (KeyError, TypeError, ValueError):
            continue
    return df
