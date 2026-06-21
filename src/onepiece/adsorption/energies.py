"""Adsorption-energy math on reference-annotated dataframes."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from onepiece.adsorption.formulas import (
    adsorbate_counts_from_structures,
    count_element,
    formula_counts,
    primary_structure,
)
from onepiece.adsorption.references import (
    GasReferences,
    annotate_adsorbates,
    assign_surface_references,
    infer_adsorption_recipes,
)
from onepiece.thermo import add_gibbs_free_energy


def add_adsorption_energies(
    frame: pd.DataFrame,
    gas_references_ev: Mapping[str, float] | GasReferences | None = None,
) -> pd.DataFrame:
    """Add CO and methanol-to-methoxy adsorption energy columns.

    CO:
        E_ads,total = E(CO*) - E(*) - n E(CO_gas)
        E_ads,per CO = E_ads,total / n

    Methoxy from methanol:
        * + CH3OH(g) -> CH3O* + 1/2 H2(g)
        E_ads,total = E(CH3O*) + 0.5 n E(H2) - E(*) - n E(CH3OH)
        E_ads,per adsorbate = E_ads,total / n

    The frame needs ``adsorbate``, ``delta_C``, ``E``, and ``surface_ref_E``
    columns, normally produced by
    :func:`onepiece.assign_references_before_merge`.

    Examples
    --------
    >>> import pandas as pd
    >>> import onepiece
    >>> frame = pd.DataFrame({
    ...     "Name": ["Cu211-CO"],
    ...     "adsorbate": ["CO"],
    ...     "delta_C": [1.0],
    ...     "E": [-120.0],
    ...     "surface_ref_E": [-104.0],
    ... })
    >>> out = onepiece.add_adsorption_energies(frame, {"CO": -14.8})
    >>> round(float(out.loc[0, "E_ads_CO_eV"]), 2)
    -1.2
    """
    refs = gas_references_ev if isinstance(gas_references_ev, GasReferences) else GasReferences.from_mapping(gas_references_ev)
    df = frame.copy()
    for column in ("delta_C", "E", "surface_ref_E"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df["n_CO_adsorbates"] = np.where(df["adsorbate"].eq("CO"), df["delta_C"], np.nan)
    df["n_CH3O_adsorbates"] = np.where(df["adsorbate"].eq("CH3O"), df["delta_C"], np.nan)

    valid_co = df["n_CO_adsorbates"].fillna(0) > 0
    df["E_ads_CO_total_eV"] = np.nan
    df["E_ads_CO_eV"] = np.nan
    df.loc[valid_co, "E_ads_CO_total_eV"] = (
        df.loc[valid_co, "E"]
        - df.loc[valid_co, "surface_ref_E"]
        - df.loc[valid_co, "n_CO_adsorbates"] * refs.co
    )
    df.loc[valid_co, "E_ads_CO_eV"] = (
        df.loc[valid_co, "E_ads_CO_total_eV"] / df.loc[valid_co, "n_CO_adsorbates"]
    )

    valid_ch3o = df["n_CH3O_adsorbates"].fillna(0) > 0
    df["E_ads_CH3OH_to_CH3O_total_eV"] = np.nan
    df["E_ads_CH3OH_to_CH3O_eV"] = np.nan
    df.loc[valid_ch3o, "E_ads_CH3OH_to_CH3O_total_eV"] = (
        df.loc[valid_ch3o, "E"]
        + 0.5 * df.loc[valid_ch3o, "n_CH3O_adsorbates"] * refs.h2
        - df.loc[valid_ch3o, "surface_ref_E"]
        - df.loc[valid_ch3o, "n_CH3O_adsorbates"] * refs.ch3oh
    )
    df.loc[valid_ch3o, "E_ads_CH3OH_to_CH3O_eV"] = (
        df.loc[valid_ch3o, "E_ads_CH3OH_to_CH3O_total_eV"]
        / df.loc[valid_ch3o, "n_CH3O_adsorbates"]
    )
    return df


def add_recipe_adsorption_energies(
    frame: pd.DataFrame,
    gas_reference_values: Mapping[str, float] | None,
    recipes: Mapping[str, Mapping[str, object]] | None,
) -> pd.DataFrame:
    """Add adsorption energies for arbitrary adsorbate recipes.

    Each recipe has the shape:
        {
            "basis": "C",
            "gas_refs": {"CO": 1.0, "H2": 1.5},
        }

    The total adsorption energy is:
        E_ads,total = E - E(surface_ref) - n_basis * sum_i coeff_i E(gas_i)

    and the per-adsorbate energy is:
        E_ads = E_ads,total / n_basis
    """
    df = frame.copy()
    if "adsorbate" not in df.columns or "surface_ref_E" not in df.columns:
        df = assign_surface_references(df)
    if "adsorbate" not in df.columns:
        df = annotate_adsorbates(df)
    active_recipes = recipes or infer_adsorption_recipes(df)
    if not active_recipes:
        return df
    df["E"] = pd.to_numeric(df.get("E"), errors="coerce")
    df["surface_ref_E"] = pd.to_numeric(df.get("surface_ref_E"), errors="coerce")

    normalized_gases = {
        str(key): float(value)
        for key, value in (gas_reference_values or {}).items()
        if value is not None and pd.notna(value)
    }

    for label, recipe in active_recipes.items():
        basis = str(recipe.get("basis", "C")).strip() or "C"
        gas_refs = recipe.get("gas_refs", {}) or {}
        n_column = str(recipe.get("count_column", f"n_{label}_adsorbates"))
        total_column = str(recipe.get("total_column", f"E_ads_{label}_total_eV"))
        per_column = str(recipe.get("per_column", f"E_ads_{label}_eV"))

        multiplier = _basis_multiplier(df, basis)
        df[n_column] = np.where(df["adsorbate"].astype(str).eq(str(label)), multiplier, np.nan)
        df[total_column] = np.nan
        df[per_column] = np.nan

        gas_total = 0.0
        missing = False
        for species, coefficient in gas_refs.items():
            if str(species) not in normalized_gases:
                missing = True
                break
            gas_total += float(coefficient) * normalized_gases[str(species)]
        if missing:
            continue

        valid = df["adsorbate"].astype(str).eq(str(label)) & pd.to_numeric(df[n_column], errors="coerce").fillna(0).gt(0)
        df.loc[valid, total_column] = (
            df.loc[valid, "E"]
            - df.loc[valid, "surface_ref_E"]
            - pd.to_numeric(df.loc[valid, n_column], errors="coerce") * gas_total
        )
        df.loc[valid, per_column] = (
            pd.to_numeric(df.loc[valid, total_column], errors="coerce")
            / pd.to_numeric(df.loc[valid, n_column], errors="coerce")
        )

    return df


def add_catalysis_hub_adsorption_energies(
    frame: pd.DataFrame,
    *,
    energy_column: str = "E",
    reaction_id_column: str = "reaction_id",
    system_name_column: str = "reaction_system_name",
    output_column: str = "adsorption_energy",
) -> pd.DataFrame:
    """Compute adsorption energies from Catalysis-Hub reaction-system rows.

    Catalysis-Hub reaction entries often store the surface reference (`star`),
    the gas-phase reference (for example `CO2gas`), and the adsorbate state
    (for example `CO2star`) under the same reaction id. For such rows, the
    adsorption energy is:

    ``E_ads = E(adsorbate*) - E(*) - E(gas)``

    The function adds the necessary helper columns and compares the calculated
    value against the published `reactionEnergy` when that column is present.

    Examples
    --------
    >>> import onepiece
    >>> frame = onepiece.read_hdf_path(onepiece.bundled_catalysis_hub_dataset(), key="df")
    >>> analysed = onepiece.add_catalysis_hub_adsorption_energies(frame)
    >>> computed = analysed["adsorption_energy"].dropna()
    >>> len(computed)
    9
    >>> round(float(computed.iloc[0]), 3)
    -2.067
    """
    df = frame.copy()
    system_names = df.get(system_name_column, pd.Series("", index=df.index)).astype(str)
    df["cathub_system_kind"] = "other"
    df.loc[system_names.eq("star"), "cathub_system_kind"] = "surface"
    df.loc[system_names.str.endswith("gas", na=False), "cathub_system_kind"] = "gas"
    df.loc[
        system_names.str.endswith("star", na=False) & ~system_names.eq("star"),
        "cathub_system_kind",
    ] = "adsorbate"
    df["cathub_adsorbate"] = np.where(
        df["cathub_system_kind"].isin(["gas", "adsorbate"]),
        system_names.str.replace(r"(gas|star)$", "", regex=True),
        "",
    )

    surface_refs = (
        df.loc[df["cathub_system_kind"].eq("surface"), [reaction_id_column, energy_column]]
        .dropna(subset=[energy_column])
        .drop_duplicates(reaction_id_column)
        .rename(columns={energy_column: "surface_ref_E"})
    )
    gas_refs = (
        df.loc[df["cathub_system_kind"].eq("gas"), [reaction_id_column, "cathub_adsorbate", energy_column]]
        .dropna(subset=[energy_column])
        .drop_duplicates([reaction_id_column, "cathub_adsorbate"])
        .rename(columns={energy_column: "gas_ref_E"})
    )

    df = df.merge(surface_refs, on=reaction_id_column, how="left")
    df = df.merge(gas_refs, on=[reaction_id_column, "cathub_adsorbate"], how="left")
    df[output_column] = np.nan
    valid = (
        df["cathub_system_kind"].eq("adsorbate")
        & pd.to_numeric(df.get(energy_column), errors="coerce").notna()
        & pd.to_numeric(df.get("surface_ref_E"), errors="coerce").notna()
        & pd.to_numeric(df.get("gas_ref_E"), errors="coerce").notna()
    )
    df.loc[valid, output_column] = (
        pd.to_numeric(df.loc[valid, energy_column], errors="coerce")
        - pd.to_numeric(df.loc[valid, "surface_ref_E"], errors="coerce")
        - pd.to_numeric(df.loc[valid, "gas_ref_E"], errors="coerce")
    )
    if "reactionEnergy" in df.columns:
        published = pd.to_numeric(df["reactionEnergy"], errors="coerce")
        df["adsorption_energy_delta_vs_reactionEnergy"] = pd.to_numeric(df[output_column], errors="coerce") - published
    return df


def add_elemental_adsorption_energy(
    frame: pd.DataFrame,
    gas_reference_values: Mapping[str, float] | GasReferences | None,
    *,
    energy_column: str = "E",
    surface_reference_energy_column: str | None = None,
    structure_columns: tuple[str, ...] = ("struc", "CONTCAR", "structure", "atoms"),
    surface_ref_name_column: str = "surface_ref_name",
    output_column: str = "adsorption_energy",
) -> pd.DataFrame:
    """Add a OnePiece-style adsorption-energy column from structure stoichiometry.

    The adsorbate stoichiometry is taken from the difference between the row's
    ASE ``Atoms`` object and the matched clean-surface reference structure.

    The chemical potentials follow the notebook convention used for the methanol
    reaction analysis:

    ``mu_H = 0.5 * E(H2)``
    ``mu_O = E(H2O) - E(H2)``
    ``mu_C = E(CO2) - E(H2O) + 0.5 * E(H2)``

    The adsorption energy is then

    ``E_ads = E - E_surface - n_C * mu_C - n_H * mu_H - n_O * mu_O``
    """
    refs = gas_reference_values if isinstance(gas_reference_values, GasReferences) else GasReferences.from_mapping(gas_reference_values)
    df = frame.copy()
    if surface_ref_name_column not in df.columns or "surface_ref_E" not in df.columns:
        df = assign_surface_references(df)

    reference_column = surface_reference_energy_column or ("surface_ref_E" if energy_column == "E" else f"surface_ref_{energy_column}")
    df[energy_column] = pd.to_numeric(df.get(energy_column), errors="coerce")
    if reference_column not in df.columns:
        reference_lookup = (
            df.loc[df["Name"].astype(str).eq(df[surface_ref_name_column].astype(str)), ["Name", energy_column]]
            .dropna(subset=[energy_column])
            .drop_duplicates("Name")
            .set_index("Name")[energy_column]
        )
        df[reference_column] = df[surface_ref_name_column].map(reference_lookup)
    df[reference_column] = pd.to_numeric(df.get(reference_column), errors="coerce")
    df["primary_atoms"] = df.apply(lambda row: primary_structure(row, structure_columns=structure_columns), axis=1)

    surface_rows = df.loc[
        df["Name"].astype(str).eq(df[surface_ref_name_column].astype(str)) & df["primary_atoms"].notna()
    ][["Name", "primary_atoms"]].drop_duplicates("Name")
    surface_atom_map = surface_rows.set_index("Name")["primary_atoms"].to_dict()
    df["surface_ref_atoms"] = df[surface_ref_name_column].map(surface_atom_map)
    df["adsorbate_counts"] = [
        adsorbate_counts_from_structures(total_atoms, surface_atoms)
        for total_atoms, surface_atoms in zip(df["primary_atoms"], df["surface_ref_atoms"], strict=False)
    ]
    for element in ("C", "H", "O"):
        df[f"{element}_ads"] = df["adsorbate_counts"].map(
            lambda counts, element=element: int(counts.get(element, 0))
        )

    mu_h = 0.5 * refs.h2 if pd.notna(refs.h2) else np.nan
    mu_o = refs.h2o - refs.h2 if pd.notna(refs.h2o) and pd.notna(refs.h2) else np.nan
    mu_c = refs.co2 - refs.h2o + 0.5 * refs.h2 if pd.notna(refs.co2) and pd.notna(refs.h2o) and pd.notna(refs.h2) else np.nan

    df["mu_C_eV"] = mu_c
    df["mu_H_eV"] = mu_h
    df["mu_O_eV"] = mu_o
    df[output_column] = (
        df[energy_column]
        - df[reference_column]
        - df["C_ads"] * mu_c
        - df["H_ads"] * mu_h
        - df["O_ads"] * mu_o
    )
    return df


def add_elemental_adsorption_free_energy(
    frame: pd.DataFrame,
    gas_reference_values: Mapping[str, float] | GasReferences | None,
    *,
    temperature: float | None = None,
    energy_column: str = "E",
    gibbs_column: str = "G",
    structure_columns: tuple[str, ...] = ("struc", "CONTCAR", "structure", "atoms"),
    surface_ref_name_column: str = "surface_ref_name",
    output_column: str = "adsorption_free_energy",
) -> pd.DataFrame:
    """Add a Gibbs adsorption free-energy column from structure stoichiometry.

    This follows the same reference construction as ``add_elemental_adsorption_energy``,
    but uses a Gibbs free-energy column for both adsorbates and gas references.
    """
    df = frame.copy()
    if gibbs_column not in df.columns:
        if temperature is None:
            raise ValueError(f"{gibbs_column} is missing and no temperature was provided to compute it.")
        df = add_gibbs_free_energy(df, temperature=temperature, energy_column=energy_column, output_column=gibbs_column)

    if surface_ref_name_column not in df.columns or "surface_ref_E" not in df.columns:
        df = assign_surface_references(df)

    df[gibbs_column] = pd.to_numeric(df.get(gibbs_column), errors="coerce")
    reference_lookup = (
        df.loc[df["Name"].astype(str).eq(df[surface_ref_name_column].astype(str)), ["Name", gibbs_column]]
        .dropna(subset=[gibbs_column])
        .drop_duplicates("Name")
        .set_index("Name")[gibbs_column]
    )
    df["surface_ref_G"] = df[surface_ref_name_column].map(reference_lookup)
    result = add_elemental_adsorption_energy(
        df,
        gas_reference_values,
        energy_column=gibbs_column,
        structure_columns=structure_columns,
        surface_ref_name_column=surface_ref_name_column,
        output_column=output_column,
    )
    result["surface_ref_G"] = pd.to_numeric(result.get("surface_ref_G"), errors="coerce")
    result["mu_C_G_eV"] = result["mu_C_eV"]
    result["mu_H_G_eV"] = result["mu_H_eV"]
    result["mu_O_G_eV"] = result["mu_O_eV"]
    return result


def _basis_multiplier(frame: pd.DataFrame, basis: str) -> pd.Series:
    delta_column = f"delta_{basis}"
    if delta_column in frame.columns:
        return pd.to_numeric(frame[delta_column], errors="coerce")

    current = frame.apply(lambda row: count_element(row, basis), axis=1)
    ref = frame.get("surface_ref_formula", pd.Series(index=frame.index, dtype=object)).map(
        lambda formula: float(formula_counts(formula).get(basis, 0))
    )
    return pd.to_numeric(current - ref.fillna(0), errors="coerce")


def adsorption_view(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a focused adsorption-analysis table for UI or notebook use.

    Keeps only the columns relevant to adsorption analysis (in a fixed order)
    and, when an ``is_adsorbate`` column is present, only the adsorbate rows.

    Examples
    --------
    >>> import pandas as pd
    >>> import onepiece
    >>> frame = pd.DataFrame({"Name": ["Cu211-CO"], "E": [-120.0], "k_point_density": [40]})
    >>> onepiece.adsorption_view(frame).columns.tolist()
    ['Name', 'E']
    """
    columns = [
        "dataset_label",
        "Name",
        "Formula",
        "adsorbate",
        "surface_ref_name",
        "surface_ref_formula",
        "surface_ref_status",
        "E",
        "surface_ref_E",
        "delta_E_to_surface_eV",
        "delta_C",
        "delta_H",
        "delta_O",
        "n_CO_adsorbates",
        "E_ads_CO_total_eV",
        "E_ads_CO_eV",
        "n_CH3O_adsorbates",
        "E_ads_CH3OH_to_CH3O_total_eV",
        "E_ads_CH3OH_to_CH3O_eV",
        "fmax",
        "source_hdf",
        "source_row",
    ]
    available = [column for column in columns if column in frame.columns]
    mask = frame["is_adsorbate"] if "is_adsorbate" in frame.columns else pd.Series(True, index=frame.index)
    return frame.loc[mask, available].copy()
