"""Rendering for the Workflow Builder "Notebook Automation" tab.

Each automation block turns a recurring notebook-style DataFrame command chain
into regular pipeline operations; the operation dicts themselves are built from
pure helpers in :mod:`onepiece_studio.workflow_logic`.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from onepiece_studio.ui.workflow_session import (
    append_operation,
    append_operations,
    workflow_gas_reference_values,
)
from onepiece_studio.workflow_logic import (
    adsorption_recipes_from_table,
    column_index,
    default_drop_rules_table,
    default_gas_reference_table,
    default_normalization_table,
    default_pdos_table,
    default_recipe_table,
    drop_rules_from_table,
    gas_reference_mapping_from_table,
    normalization_pairs_from_table,
    pdos_integrations_from_table,
    split_csv_tokens,
    split_nonempty_lines,
)


def render_notebook_automation(st: Any, dataframe: pd.DataFrame) -> None:
    st.markdown("**Notebook automation blocks**")
    st.caption(
        "Turn recurring notebook-style DataFrame command chains into configurable workflow blocks. "
        "Each block expands into normal OnePiece Studio pipeline operations that stay editable and reproducible."
    )
    block = st.selectbox(
        "Automation block",
        [
            "Source labeling and cleanup",
            "Element counting from formula",
            "Adsorbate normalization map",
            "Recipe-based adsorption energy",
            "VASP charge and projected DOS",
            "ASE geometry, site and QC descriptors",
            "Reaction network builder",
            "Curation engine",
            "Structure descriptor workbench",
            "Ranking within groups",
            "Drop named calculations",
        ],
    )

    if block == "Source labeling and cleanup":
        _render_source_cleanup_block(st, dataframe)
    elif block == "Element counting from formula":
        _render_element_count_block(st, dataframe)
    elif block == "Adsorbate normalization map":
        _render_normalization_block(st, dataframe)
    elif block == "Recipe-based adsorption energy":
        _render_recipe_adsorption_block(st, dataframe)
    elif block == "VASP charge and projected DOS":
        _render_vasp_charge_block(st, dataframe)
    elif block == "ASE geometry, site and QC descriptors":
        _render_ase_analysis_block(st, dataframe)
    elif block == "Reaction network builder":
        _render_reaction_network_block(st)
    elif block == "Curation engine":
        _render_curation_block(st)
    elif block == "Structure descriptor workbench":
        _render_structure_descriptors_block(st)
    elif block == "Ranking within groups":
        _render_group_rank_block(st, dataframe)
    else:
        _render_drop_named_block(st, dataframe)


def _numeric_columns(dataframe: pd.DataFrame) -> list[str]:
    return [
        column for column in dataframe.columns if pd.api.types.is_numeric_dtype(dataframe[column])
    ]


def _name_defaults(all_columns: list[str]) -> list[str]:
    return [column for column in all_columns if str(column).lower() == "name"] or all_columns


def _render_source_cleanup_block(st: Any, dataframe: pd.DataFrame) -> None:
    all_columns = list(dataframe.columns)
    numeric_columns = _numeric_columns(dataframe)
    st.info(
        "For notebook sequences like: set a source label, fill missing element counts with 0, "
        "exclude test/copt rows, and drop zero-energy calculations."
    )
    col1, col2 = st.columns(2)
    constant_column = col1.text_input("Constant column name", value="adsorbate_ref")
    constant_value = col2.text_input("Constant value", placeholder="e.g. MgOCu-")
    fill_columns = st.multiselect(
        "Fill missing values with 0 in these columns",
        all_columns,
        default=[column for column in ["Cu", "Ni", "Ga", "Zn", "Mg", "C", "H", "O", "N"] if column in all_columns],
    )
    name_column = st.selectbox("Name column", _name_defaults(all_columns), key="onepiece_studio_nb_name_cleanup")
    exclude_patterns = st.text_area(
        "Exclude rows whose names contain these tokens",
        value="test\ncopt",
        help="One token per line. Each token becomes a backend filter operation.",
    )
    energy_column = st.selectbox(
        "Energy column for nonzero filter",
        numeric_columns or all_columns,
        index=column_index(numeric_columns or all_columns, "E"),
        key="onepiece_studio_nb_energy_cleanup",
    )
    drop_zero = st.checkbox("Drop rows where energy equals 0", value=True)
    operations = []
    if constant_column.strip() and constant_value.strip():
        operations.append(
            {
                "kind": "derive_constant",
                "new_column": constant_column.strip(),
                "value": constant_value,
                "label": f"{constant_column.strip()} = constant {constant_value!r}",
            }
        )
    for column in fill_columns:
        operations.append(
            {
                "kind": "fill_missing",
                "column": column,
                "value": 0.0,
                "label": f"fill missing {column} with 0.0",
            }
        )
    for token in split_nonempty_lines(exclude_patterns):
        operations.append(
            {
                "kind": "filter",
                "column": name_column,
                "operator": "not contains",
                "value": token,
                "new_column": "",
                "label": f"filter {name_column} not contains {token!r}",
            }
        )
    if drop_zero:
        operations.append(
            {
                "kind": "filter",
                "column": energy_column,
                "operator": "not equals",
                "value": "0",
                "new_column": "",
                "label": f"filter {energy_column} not equals 0",
            }
        )
    st.caption(f"This block will add {len(operations)} workflow step{'s' if len(operations) != 1 else ''}.")
    if st.button("Add automation block", key="onepiece_studio_nb_cleanup_add", width="stretch"):
        append_operations(st, operations)
        st.rerun()


def _render_element_count_block(st: Any, dataframe: pd.DataFrame) -> None:
    all_columns = list(dataframe.columns)
    formula_defaults = [column for column in all_columns if "formula" in str(column).lower()] or all_columns
    st.info(
        "For notebook steps such as counting C, H, O, N or metal atoms from the `Formula` column "
        "into explicit numeric DataFrame columns."
    )
    col1, col2 = st.columns(2)
    formula_column = col1.selectbox("Formula column", formula_defaults, key="onepiece_studio_nb_formula_count")
    elements_text = col2.text_input("Elements", value="C,H,O,N")
    operations = [
        {
            "kind": "count_element",
            "new_column": f"{element}_count",
            "element": element,
            "formula_column": formula_column,
            "label": f"{element}_count = count element {element} from {formula_column}",
        }
        for element in split_csv_tokens(elements_text)
    ]
    st.caption(f"This block will add {len(operations)} workflow step{'s' if len(operations) != 1 else ''}.")
    if st.button("Add automation block", key="onepiece_studio_nb_count_add", width="stretch"):
        append_operations(st, operations)
        st.rerun()


def _render_normalization_block(st: Any, dataframe: pd.DataFrame) -> None:
    all_columns = list(dataframe.columns)
    st.info(
        "For notebook sequences like `unify_adsorbates(...)`, where several adsorbate labels are "
        "systematically renamed to a common standard."
    )
    col1, col2 = st.columns(2)
    column = col1.selectbox(
        "Column to normalize",
        [column for column in all_columns if pd.api.types.is_object_dtype(dataframe[column])] or all_columns,
        index=column_index(all_columns, "adsorbate"),
        key="onepiece_studio_nb_norm_column",
    )
    mapping_table = col2.data_editor(
        default_normalization_table(),
        hide_index=True,
        width="stretch",
        num_rows="dynamic",
        key="onepiece_studio_nb_norm_table_editor",
        column_config={
            "from_value": st.column_config.TextColumn("From"),
            "to_value": st.column_config.TextColumn("To"),
        },
    )
    operations = [
        {
            "kind": "replace_value",
            "column": column,
            "from_value": old,
            "to_value": new,
            "label": f"replace {column}: {old!r} -> {new!r}",
        }
        for old, new in normalization_pairs_from_table(mapping_table)
    ]
    st.caption(f"This block will add {len(operations)} workflow step{'s' if len(operations) != 1 else ''}.")
    if st.button("Add automation block", key="onepiece_studio_nb_norm_add", width="stretch"):
        append_operations(st, operations)
        st.rerun()


def _render_recipe_adsorption_block(st: Any, dataframe: pd.DataFrame) -> None:
    st.info(
        "For notebook functions like `ads_E(...)`: define gas-phase energies and recipes for adsorbates, "
        "then let OnePiece Studio compute total and per-adsorbate adsorption energies in the backend."
    )
    gas_defaults = workflow_gas_reference_values(st, dataframe)
    col1, col2 = st.columns(2)
    gas_editor = col1.data_editor(
        default_gas_reference_table(gas_defaults),
        hide_index=True,
        width="stretch",
        num_rows="dynamic",
        key="onepiece_studio_nb_recipe_gases_editor",
        column_config={
            "species": st.column_config.TextColumn("Gas species"),
            "energy_eV": st.column_config.NumberColumn("Energy / eV", format="%.6f"),
        },
    )
    recipe_editor = col2.data_editor(
        default_recipe_table(),
        hide_index=True,
        width="stretch",
        num_rows="dynamic",
        key="onepiece_studio_nb_recipe_table_editor",
        column_config={
            "adsorbate": st.column_config.TextColumn("Adsorbate"),
            "basis": st.column_config.TextColumn("Basis"),
            "CO": st.column_config.NumberColumn("CO", format="%.3f"),
            "H2": st.column_config.NumberColumn("H2", format="%.3f"),
            "H2O": st.column_config.NumberColumn("H2O", format="%.3f"),
            "CH3OH": st.column_config.NumberColumn("CH3OH", format="%.3f"),
            "CO2": st.column_config.NumberColumn("CO2", format="%.3f"),
            "NH3": st.column_config.NumberColumn("NH3", format="%.3f"),
        },
    )
    gases = gas_reference_mapping_from_table(gas_editor)
    recipes = adsorption_recipes_from_table(recipe_editor)
    operation = {
        "kind": "derive_recipe_adsorption",
        "gas_reference_values": gases,
        "recipes": recipes,
        "label": f"derive recipe-based adsorption energies for {list(recipes)}",
    }
    st.caption(
        f"This block will add 1 workflow step and currently defines {len(gases)} gas references and {len(recipes)} recipes."
    )
    if st.button("Add automation block", key="onepiece_studio_nb_recipe_add", width="stretch", disabled=not recipes):
        append_operation(st, operation)
        st.rerun()


def _render_vasp_charge_block(st: Any, dataframe: pd.DataFrame) -> None:
    all_columns = list(dataframe.columns)
    st.info(
        "Read `ACF.dat` or `CHGCAR` files from each calculation folder, derive atomic charge "
        "descriptors, then compare adsorbate-side charge against the matched clean surface and "
        "against gas-phase or valence-electron references where available."
    )
    path_candidates = [column for column in all_columns if "path" in str(column).lower()] or all_columns
    structure_candidates = [column for column in all_columns if "struc" in str(column).lower()] or all_columns
    col1, col2, col3, col4 = st.columns(4)
    calculation_path_column = col1.selectbox(
        "Calculation path column",
        path_candidates,
        index=column_index(path_candidates, "Path"),
        key="onepiece_studio_nb_vasp_path_column",
    )
    structure_column = col2.selectbox(
        "Structure column",
        structure_candidates,
        index=column_index(structure_candidates, "struc"),
        key="onepiece_studio_nb_vasp_structure_column",
    )
    charge_source_label = col3.selectbox(
        "Charge source",
        ["ACF.dat (default)", "CHGCAR integration"],
        key="onepiece_studio_nb_vasp_charge_source",
    )
    charge_source = "acf" if charge_source_label.startswith("ACF.dat") else "chgcar"
    add_pdos = col4.checkbox("Also integrate PDOS", value=False, key="onepiece_studio_nb_vasp_add_pdos")

    operations = [
        {
            "kind": "derive_vasp_charge_descriptors",
            "charge_source": charge_source,
            "calculation_path_column": calculation_path_column,
            "structure_column": structure_column,
            "label": f"derive {charge_source.upper()}-preferred charge descriptors and adsorption-style charge references",
        }
    ]
    pdos_integrations: list[dict[str, Any]] = []
    if add_pdos:
        pdos_table = st.data_editor(
            default_pdos_table(),
            hide_index=True,
            width="stretch",
            num_rows="dynamic",
            key="onepiece_studio_nb_vasp_pdos_editor",
            column_config={
                "column": st.column_config.TextColumn("Column name"),
                "elements": st.column_config.TextColumn("Elements (CSV)"),
                "orbitals": st.column_config.TextColumn("Orbitals (CSV)"),
                "emin": st.column_config.NumberColumn("E min / eV", format="%.2f"),
                "emax": st.column_config.NumberColumn("E max / eV", format="%.2f"),
                "spin": st.column_config.SelectboxColumn(
                    "Spin",
                    options=["sum", "up", "down"],
                ),
            },
        )
        pdos_integrations = pdos_integrations_from_table(pdos_table)
        if pdos_integrations:
            operations.append(
                {
                    "kind": "derive_vasp_pdos_descriptors",
                    "calculation_path_column": calculation_path_column,
                    "structure_column": structure_column,
                    "integrations": pdos_integrations,
                    "label": f"derive projected DOS descriptors for {len(pdos_integrations)} integrations",
                }
            )
    st.caption(
        "This block will add charge descriptors such as "
        "`adsorbate_net_charge_e`, `surface_net_charge_delta_vs_ref_e`, and "
        "`adsorbate_charge_delta_vs_ref_e`."
    )
    st.caption(
        "When `ACF.dat` is selected, OnePiece Studio uses Bader electron populations by default and "
        "falls back to `CHGCAR` integration only when no `ACF.dat` is available."
    )
    st.caption(
        f"This block will add {len(operations)} workflow step{'s' if len(operations) != 1 else ''}."
    )
    if st.button("Add automation block", key="onepiece_studio_nb_vasp_add", width="stretch"):
        append_operations(st, operations)
        st.rerun()


def _render_ase_analysis_block(st: Any, dataframe: pd.DataFrame) -> None:
    all_columns = list(dataframe.columns)
    st.info(
        "Build ASE-native slab, adsorption-site, local-environment, and quality-control descriptors. "
        "Optionally read DOSCAR to add metal d-band center and filling summaries."
    )
    path_candidates = [column for column in all_columns if "path" in str(column).lower()] or all_columns
    structure_candidates = [column for column in all_columns if "struc" in str(column).lower()] or all_columns
    col1, col2, col3 = st.columns(3)
    calculation_path_column = col1.selectbox(
        "Calculation path column",
        path_candidates,
        index=column_index(path_candidates, "Path"),
        key="onepiece_studio_nb_ase_path_column",
    )
    structure_column = col2.selectbox(
        "Structure column",
        structure_candidates,
        index=column_index(structure_candidates, "struc"),
        key="onepiece_studio_nb_ase_structure_column",
    )
    include_pdos = col3.checkbox(
        "Also derive DOSCAR d-band descriptors",
        value=False,
        key="onepiece_studio_nb_ase_include_pdos",
    )
    operation = {
        "kind": "derive_ase_analysis_descriptors",
        "calculation_path_column": calculation_path_column,
        "structure_column": structure_column,
        "include_pdos": include_pdos,
        "label": "derive ASE geometry, adsorption-site, QC, and optional d-band descriptors",
    }
    st.caption(
        "This block will add columns such as `adsorption_site`, `adsorbate_tilt_deg`, "
        "`surface_reconstruction_rmsd`, `adsorbate_is_dissociated`, `adsorbate_desorbed`, "
        "`min_interatomic_distance`, and optionally `metal_d_band_center_eV`."
    )
    if st.button("Add automation block", key="onepiece_studio_nb_ase_analysis_add", width="stretch"):
        append_operation(st, operation)
        st.rerun()


def _render_reaction_network_block(st: Any) -> None:
    st.info(
        "Annotate static states and constrained-optimization images into a reaction-network table "
        "with state labels, elementary-step families, and pathway roles."
    )
    operation = {
        "kind": "derive_reaction_network",
        "label": "annotate reaction-network states and copt pathways",
    }
    st.caption(
        "This block will add reaction columns such as `reaction_state`, `reaction_step_initial`, "
        "`reaction_step_final`, `reaction_family`, and `reaction_network_role`."
    )
    if st.button("Add automation block", key="onepiece_studio_nb_reaction_add", width="stretch"):
        append_operation(st, operation)
        st.rerun()


def _render_curation_block(st: Any) -> None:
    st.info(
        "Apply reproducible DFT quality-control rules: energy and structure presence, static and copt "
        "force thresholds, and name-based exclusion tokens."
    )
    col1, col2, col3 = st.columns(3)
    static_fmax_max = col1.number_input("Static fmax max", value=0.05, min_value=0.0, step=0.01)
    copt_fmax_max = col2.number_input("COPT fmax max", value=0.10, min_value=0.0, step=0.01)
    action = col3.selectbox("Action", ["exclude", "mark_review", "mark_excluded"])
    exclude_name_tokens = st.text_area(
        "Name tokens to flag",
        value="test\nconvergence\nfailed\nbroken",
        help="One token per line. Matching rows are flagged by the curation engine.",
    )
    operation = {
        "kind": "derive_curation",
        "static_fmax_max": float(static_fmax_max),
        "copt_fmax_max": float(copt_fmax_max),
        "exclude_name_tokens": split_nonempty_lines(exclude_name_tokens),
        "action": action,
        "label": f"curate calculations ({action}) with fmax thresholds {static_fmax_max:g}/{copt_fmax_max:g}",
    }
    if st.button("Add automation block", key="onepiece_studio_nb_curation_add", width="stretch"):
        append_operation(st, operation)
        st.rerun()


def _render_structure_descriptors_block(st: Any) -> None:
    st.info(
        "Build structure-derived catalytic descriptors from ASE `Atoms`: adsorbate composition, "
        "adsorbate size, cell volume, and height above the matched clean surface."
    )
    operation = {
        "kind": "derive_structure_descriptors",
        "label": "derive structure descriptors from ASE structures and clean references",
    }
    st.caption(
        "This block will add columns such as `adsorbate_formula`, `adsorbate_atom_count`, "
        "`cell_volume`, and `adsorbate_height_above_surface`."
    )
    if st.button("Add automation block", key="onepiece_studio_nb_descriptors_add", width="stretch"):
        append_operation(st, operation)
        st.rerun()


def _render_group_rank_block(st: Any, dataframe: pd.DataFrame) -> None:
    all_columns = list(dataframe.columns)
    numeric_columns = _numeric_columns(dataframe)
    st.info(
        "For notebook commands like `groupby(...)[\"E\"].rank(...)`, for example ranking "
        "adsorbates within each surface reference."
    )
    col1, col2, col3, col4 = st.columns(4)
    value_column = col1.selectbox(
        "Rank values in",
        numeric_columns or all_columns,
        index=column_index(numeric_columns or all_columns, "E"),
        key="onepiece_studio_nb_rank_value",
    )
    default_groups = [column for column in ["adsorbate_ref", "adsorbate", "surface_ref"] if column in all_columns]
    group_columns = col2.multiselect(
        "Group by",
        [column for column in all_columns if column != value_column],
        default=default_groups,
        key="onepiece_studio_nb_rank_groups",
    )
    ascending = col3.checkbox("Ascending", value=True, key="onepiece_studio_nb_rank_asc")
    method = col4.selectbox("Method", ["min", "dense", "first", "average", "max"], key="onepiece_studio_nb_rank_method")
    new_column = st.text_input("Rank column name", value="ranked", key="onepiece_studio_nb_rank_name")
    operation = {
        "kind": "group_rank",
        "new_column": new_column,
        "value_column": value_column,
        "group_columns": group_columns,
        "ascending": ascending,
        "method": method,
        "label": f"{new_column} = rank {value_column} by {group_columns or ['all rows']}",
    }
    if st.button("Add automation block", key="onepiece_studio_nb_rank_add", width="stretch"):
        append_operation(st, operation)
        st.rerun()


def _render_drop_named_block(st: Any, dataframe: pd.DataFrame) -> None:
    all_columns = list(dataframe.columns)
    st.info(
        "For notebook clean-up cells where known bad, test, or dissociated calculations are "
        "removed by curated matching rules."
    )
    name_column = st.selectbox("Name column", _name_defaults(all_columns), key="onepiece_studio_nb_drop_namecol")
    rules_table = st.data_editor(
        default_drop_rules_table(),
        hide_index=True,
        width="stretch",
        num_rows="dynamic",
        key="onepiece_studio_nb_drop_rules_editor",
        column_config={
            "pattern": st.column_config.TextColumn("Pattern"),
            "match_mode": st.column_config.SelectboxColumn(
                "Match mode",
                options=["exact", "contains", "regex"],
                required=True,
            ),
            "reason": st.column_config.TextColumn("Reason"),
        },
    )
    rules = drop_rules_from_table(rules_table)
    operation = {
        "kind": "exclude_by_match_rules",
        "column": name_column,
        "rules": rules,
        "label": f"drop {len(rules)} curated name rules from {name_column}",
    }
    if rules:
        exact_count = sum(1 for rule in rules if rule["match_mode"] == "exact")
        contains_count = sum(1 for rule in rules if rule["match_mode"] == "contains")
        regex_count = sum(1 for rule in rules if rule["match_mode"] == "regex")
        st.caption(
            f"This block will add 1 workflow step with {exact_count} exact, "
            f"{contains_count} contains, and {regex_count} regex rule"
            f"{'' if len(rules) == 1 else 's'}."
        )
    else:
        st.caption("This block will add 0 workflow steps until at least one valid rule is defined.")
    if st.button("Add automation block", key="onepiece_studio_nb_drop_add", width="stretch", disabled=not rules):
        append_operation(st, operation)
        st.rerun()
