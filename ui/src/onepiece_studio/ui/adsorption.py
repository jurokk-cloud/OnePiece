from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from onepiece.adsorption import (
    add_adsorption_energies,
    adsorption_view,
    assign_surface_references,
    copt_barrier_summary,
    copt_profile_points,
)
from onepiece_studio.ui.row_actions import (
    render_action_grid,
    selected_dataframe_index,
    selected_plot_index,
    selected_row_summary,
)

GAS_REFERENCE_DEFAULTS = {
    "CO": np.nan,
    "CO2": np.nan,
    "CH3OH": np.nan,
    "H2": np.nan,
    "H2O": np.nan,
}


def render_adsorption_workbench(
    st: Any,
    source: pd.DataFrame,
    active: pd.DataFrame,
    *,
    reference_source: pd.DataFrame | None = None,
) -> None:
    st.subheader("Adsorption & Barriers")
    st.caption(
        "Calculate adsorption-energy columns and constrained-optimization barriers from "
        "local OnePiece/pandas data. Surface references are assigned per source before "
        "the analysis table is merged."
    )

    if "Name" not in source.columns or "E" not in source.columns:
        st.info("This workflow needs at least `Name` and `E` columns.")
        return

    gas_reference_source = reference_source if reference_source is not None else source
    gas_refs = _render_gas_reference_inputs(st, gas_reference_source)
    max_fmax, status_filter, adsorbate_filter, use_active_rows = _render_analysis_controls(st, source)

    with st.spinner("Assigning surface references and calculating analysis tables..."):
        analysis = _analysis_frame(source, gas_refs)
        active_keys = set(_row_keys(active)) if use_active_rows else None
        adsorption = adsorption_view(analysis)
        if active_keys is not None:
            adsorption = adsorption.loc[_row_keys(adsorption).isin(active_keys)].copy()
        adsorption = _filter_adsorption(adsorption, max_fmax, status_filter, adsorbate_filter)
        copt_points = copt_profile_points(analysis)
        barriers = copt_barrier_summary(analysis)
        if active_keys is not None and not copt_points.empty:
            copt_points = copt_points.loc[_row_keys(copt_points).isin(active_keys)].copy()
            keep_series = set(copt_points["copt_series_id"].dropna())
            barriers = barriers.loc[barriers["copt_series_id"].isin(keep_series)].copy()

    _render_metrics(st, analysis, adsorption, copt_points, barriers, gas_refs)

    adsorption_tab, plots_tab, barriers_tab, tutorial_tab = st.tabs(
        ["Adsorption Table", "Energy Plots", "Barriers", "Method"]
    )
    with adsorption_tab:
        _render_adsorption_table(st, adsorption)
    with plots_tab:
        _render_adsorption_plots(st, adsorption, gas_refs)
    with barriers_tab:
        _render_barriers(st, copt_points, barriers)
    with tutorial_tab:
        _render_method(st)


def _render_gas_reference_inputs(st: Any, source: pd.DataFrame) -> dict[str, float]:
    st.markdown("**Gas-phase references**")
    st.caption(
        "OnePiece Studio first searches the loaded dataset for gas-like reference rows. You can then "
        "freely override every value; adsorption energies update immediately on rerun."
    )
    candidates = _gas_reference_candidates(source)
    _init_gas_reference_state(st, candidates)

    if st.button("Reset gas references from dataset candidates", key="onepiece_studio_ads_reset_gas_refs"):
        for label in GAS_REFERENCE_DEFAULTS:
            default = _candidate_default(candidates[label])
            st.session_state[f"onepiece_studio_ads_gas_value_{label}"] = _energy_or_zero(default)
            st.session_state[f"onepiece_studio_ads_gas_source_{label}"] = _candidate_key(default)
            if default is not None:
                st.session_state[f"onepiece_studio_ads_gas_last_source_{label}"] = _candidate_key(default)
        st.rerun()

    values: dict[str, float] = {}
    cols = st.columns(5)
    for col, label, help_text in [
        (cols[0], "CO", "Energy of CO(g) in eV."),
        (cols[1], "CO2", "Energy of CO2(g) in eV."),
        (cols[2], "CH3OH", "Energy of CH3OH(g) in eV."),
        (cols[3], "H2", "Energy of H2(g), needed for CH3OH -> CH3O* + 1/2 H2."),
        (cols[4], "H2O", "Energy of H2O(g) in eV."),
    ]:
        with col:
            values[label] = _render_one_gas_reference(st, label, help_text, candidates[label])

    return values


def _render_one_gas_reference(
    st: Any,
    label: str,
    help_text: str,
    candidates: pd.DataFrame,
) -> float:
    source_key = f"onepiece_studio_ads_gas_source_{label}"
    value_key = f"onepiece_studio_ads_gas_value_{label}"
    options = ["Manual"]
    option_to_energy: dict[str, float] = {}
    option_to_note: dict[str, str] = {}
    for _, row in candidates.iterrows():
        option = _candidate_key(row)
        options.append(option)
        option_to_energy[option] = float(row["E"])
        option_to_note[option] = str(row.get("Name", ""))

    current_source = st.session_state.get(source_key, "Manual")
    if current_source not in options:
        current_source = "Manual"
        st.session_state[source_key] = current_source

    selected = st.selectbox(
        f"{label} source",
        options,
        index=options.index(current_source),
        key=source_key,
        help="Choose a dataset row to copy its E value, or keep Manual for a free value.",
    )
    if selected != "Manual":
        copied = option_to_energy[selected]
        if st.session_state.get(f"onepiece_studio_ads_gas_last_source_{label}") != selected:
            st.session_state[value_key] = float(copied)
            st.session_state[f"onepiece_studio_ads_gas_last_source_{label}"] = selected
        st.caption(f"Dataset row: {option_to_note.get(selected, '')[:90]}")
    elif candidates.empty:
        st.caption("No unambiguous gas-phase row found; edit the manual starting value.")

    value = st.number_input(
        f"E({label}) / eV",
        key=value_key,
        format="%.8f",
        step=0.1,
        help=help_text,
    )
    return float(value)


def _init_gas_reference_state(st: Any, candidates: dict[str, pd.DataFrame]) -> None:
    for label in GAS_REFERENCE_DEFAULTS:
        value_key = f"onepiece_studio_ads_gas_value_{label}"
        source_key = f"onepiece_studio_ads_gas_source_{label}"
        if value_key in st.session_state and source_key in st.session_state:
            continue
        default = _candidate_default(candidates[label])
        st.session_state.setdefault(value_key, _energy_or_zero(default))
        st.session_state.setdefault(source_key, _candidate_key(default))
        if default is not None:
            st.session_state.setdefault(
                f"onepiece_studio_ads_gas_last_source_{label}",
                _candidate_key(default),
            )


def _gas_reference_candidates(source: pd.DataFrame) -> dict[str, pd.DataFrame]:
    from onepiece.sources import gas_reference_candidates

    return gas_reference_candidates(source)


def _candidate_default(candidates: pd.DataFrame) -> pd.Series | None:
    if candidates.empty:
        return None
    return candidates.iloc[0]


def _candidate_key(candidate: pd.Series | None) -> str:
    if candidate is None:
        return "Manual"
    name = str(candidate.get("Name", "reference"))
    energy = float(candidate.get("E"))
    row = candidate.get("source_row", candidate.name)
    return f"{name[:42]} | E={energy:.8f} | row={row}"


def _format_energy(candidate_or_value: pd.Series | float | None) -> str:
    if candidate_or_value is None:
        return ""
    if isinstance(candidate_or_value, pd.Series):
        value = candidate_or_value.get("E", np.nan)
    else:
        value = candidate_or_value
    return "" if pd.isna(value) else f"{float(value):.8f}"


def _energy_or_zero(candidate: pd.Series | None) -> float:
    if candidate is None:
        return 0.0
    value = candidate.get("E", np.nan)
    return 0.0 if pd.isna(value) else float(value)


def _parse_energy(text: str) -> float:
    stripped = str(text).strip()
    if not stripped or stripped.lower() in {"nan", "none", "null"}:
        return np.nan
    try:
        return float(stripped.replace(",", "."))
    except ValueError:
        return np.nan


def _normalize_text(value: object) -> str:
    text = str(value).upper().strip()
    return text.replace("\\", "/")


def _formula_signature(value: object) -> str:
    counts = _formula_counts(value)
    return "".join(f"{element}{counts[element]}" for element in sorted(counts))


def _formula_counts(value: object) -> dict[str, int]:
    import re

    counts: dict[str, int] = {}
    for element, number in re.findall(r"([A-Z][a-z]?)(\d*)", str(value)):
        counts[element] = counts.get(element, 0) + int(number or 1)
    return counts


def _render_analysis_controls(st: Any, source: pd.DataFrame) -> tuple[float | None, list[str], list[str], bool]:
    controls = st.columns([0.22, 0.28, 0.30, 0.20])
    max_fmax = None
    if "fmax" in source.columns:
        finite = pd.to_numeric(source["fmax"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        default = float(finite.quantile(0.95)) if not finite.empty else 0.05
        max_fmax = controls[0].number_input(
            "Max fmax",
            min_value=0.0,
            value=max(default, 0.0),
            step=0.01,
            format="%.4f",
            key="onepiece_studio_ads_max_fmax",
        )

    status_filter = controls[1].multiselect(
        "Reference status",
        ["ok", "missing", "ambiguous", "self"],
        default=["ok"],
        key="onepiece_studio_ads_status",
    )
    adsorbate_filter = controls[2].multiselect(
        "Adsorbates",
        ["CO", "CH3O", "CH3OH", "CO2", "HCO", "HCOO", "COOH", "HCOOH", "H2COOH"],
        default=["CO", "CH3O"],
        key="onepiece_studio_ads_adsorbates",
    )
    use_active_rows = controls[3].toggle(
        "Use active rows",
        value=True,
        help="Analyze only rows that remain after Workflow and Controlroom filters.",
        key="onepiece_studio_ads_use_active",
    )
    return max_fmax, status_filter, adsorbate_filter, use_active_rows


def _analysis_frame(source: pd.DataFrame, gas_refs: dict[str, float]) -> pd.DataFrame:
    groups = []
    group_column = _source_group_column(source)
    if group_column is None:
        groups.append(assign_surface_references(source))
    else:
        for _, group in source.groupby(group_column, dropna=False, sort=False):
            referenced = assign_surface_references(group)
            groups.append(referenced)
    analysis = pd.concat(groups, ignore_index=False, sort=False) if groups else source.copy()
    return add_adsorption_energies(analysis, gas_refs)


def _source_group_column(source: pd.DataFrame) -> str | None:
    for column in ["source_hdf", "dataset_label", "dataset"]:
        if column in source.columns:
            return column
    return None


def _filter_adsorption(
    adsorption: pd.DataFrame,
    max_fmax: float | None,
    statuses: list[str],
    adsorbates: list[str],
) -> pd.DataFrame:
    filtered = adsorption.copy()
    if statuses and "surface_ref_status" in filtered:
        filtered = filtered[filtered["surface_ref_status"].astype(str).isin(statuses)]
    if adsorbates and "adsorbate" in filtered:
        filtered = filtered[filtered["adsorbate"].astype(str).isin(adsorbates)]
    if max_fmax is not None and "fmax" in filtered:
        fmax = pd.to_numeric(filtered["fmax"], errors="coerce")
        filtered = filtered[fmax.isna() | (fmax <= max_fmax)]
    return filtered


def _render_metrics(
    st: Any,
    analysis: pd.DataFrame,
    adsorption: pd.DataFrame,
    copt_points: pd.DataFrame,
    barriers: pd.DataFrame,
    gas_refs: dict[str, float],
) -> None:
    top = st.columns(3, gap="small")
    bottom = st.columns(2, gap="small")
    top[0].metric("Adsorption rows", f"{len(adsorption):,}")
    ok = int(adsorption.get("surface_ref_status", pd.Series(dtype=str)).eq("ok").sum())
    top[1].metric("Reference ok", f"{ok:,}")
    missing = int(adsorption.get("surface_ref_status", pd.Series(dtype=str)).eq("missing").sum())
    top[2].metric("Missing refs", f"{missing:,}")
    bottom[0].metric("copt paths", f"{len(barriers):,}")
    gas_ready = sum(pd.notna(value) for value in gas_refs.values())
    bottom[1].metric("Gas refs set", f"{gas_ready}/3")

    if not analysis.empty and missing:
        st.warning(
            "Some adsorbed rows have no automatic clean-surface reference. Keep them visible "
            "for curation or exclude them from quantitative plots."
        )


def _render_adsorption_table(st: Any, adsorption: pd.DataFrame) -> None:
    st.markdown("**Calculated adsorption view**")
    if adsorption.empty:
        st.info("No adsorption rows match the current controls.")
        return
    preferred = [
        "dataset_label",
        "Name",
        "Formula",
        "adsorbate",
        "surface_ref_name",
        "surface_ref_status",
        "E",
        "surface_ref_E",
        "delta_E_to_surface_eV",
        "E_ads_CO_eV",
        "E_ads_CH3OH_to_CH3O_eV",
        "fmax",
        "source_hdf",
        "source_row",
    ]
    shown = adsorption[[column for column in preferred if column in adsorption.columns]].copy()
    event = st.dataframe(
        shown,
        hide_index=True,
        width="stretch",
        height=520,
        selection_mode="single-row",
        on_select="rerun",
        key="onepiece_studio_adsorption_table",
    )
    selected_index = selected_dataframe_index(event, shown)
    if selected_index is not None and selected_index in adsorption.index:
        _render_row_actions(st, adsorption.loc[selected_index], selected_index, key_prefix="ads_table")
    st.download_button(
        "Download adsorption table CSV",
        shown.to_csv(index=False).encode("utf-8"),
        file_name="onepiece_studio_adsorption_table.csv",
        mime="text/csv",
        width="stretch",
    )


def _render_adsorption_plots(st: Any, adsorption: pd.DataFrame, gas_refs: dict[str, float]) -> None:
    if adsorption.empty:
        st.info("No adsorption rows available for plotting.")
        return
    try:
        import plotly.express as px
    except ImportError:
        st.info("Install plotly to use interactive adsorption plots.")
        return

    value_options = [
        column
        for column in ["delta_E_to_surface_eV", "E_ads_CO_eV", "E_ads_CH3OH_to_CH3O_eV"]
        if column in adsorption.columns and adsorption[column].notna().any()
    ]
    if not value_options:
        st.info("No numeric adsorption-energy columns are available after filtering.")
        return

    value_column = st.selectbox(
        "Energy value",
        value_options,
        index=0,
        key="onepiece_studio_ads_plot_value",
    )
    plot_data = adsorption.replace([np.inf, -np.inf], np.nan).dropna(subset=[value_column]).copy()
    plot_data["row_label"] = plot_data.get("Name", plot_data.index.astype(str)).astype(str)
    plot_data["__onepiece_studio_index"] = plot_data.index.astype(str)

    if plot_data.empty:
        st.info("The selected energy value is empty for the current filters.")
        return

    if value_column.startswith("E_ads") and any(pd.isna(value) for value in gas_refs.values()):
        st.caption("Final adsorption-energy columns appear after the required gas references are set.")

    left, right = st.columns([0.5, 0.5])
    with left:
        fig = px.box(
            plot_data,
            x="dataset_label" if "dataset_label" in plot_data else "adsorbate",
            y=value_column,
            color="adsorbate" if "adsorbate" in plot_data else None,
            points="outliers",
            hover_data=[c for c in ["Name", "Formula", "surface_ref_name", "fmax"] if c in plot_data],
            custom_data=["__onepiece_studio_index"],
            color_discrete_sequence=["#5477C4", "#BD569B", "#B8A037", "#71B436", "#CC6F47"],
        )
        _style_plotly(fig, f"{value_column} distribution")
        event = st.plotly_chart(
            fig,
            width="stretch",
            key="onepiece_studio_adsorption_box",
            on_select="rerun",
            selection_mode="points",
        )
        _render_plot_actions(st, event, plot_data, key_prefix="ads_box")
    with right:
        rank = plot_data.sort_values(value_column).head(20)
        fig = px.bar(
            rank.sort_values(value_column, ascending=True),
            x=value_column,
            y="row_label",
            color="adsorbate" if "adsorbate" in rank else None,
            orientation="h",
            hover_data=[c for c in ["surface_ref_name", "Formula", "dataset_label"] if c in rank],
            custom_data=["__onepiece_studio_index"],
            color_discrete_sequence=["#5477C4", "#BD569B", "#B8A037", "#71B436", "#CC6F47"],
        )
        _style_plotly(fig, f"Lowest {value_column} rows")
        fig.update_layout(yaxis=dict(automargin=True), height=620)
        event = st.plotly_chart(
            fig,
            width="stretch",
            key="onepiece_studio_adsorption_rank",
            on_select="rerun",
            selection_mode="points",
        )
        _render_plot_actions(st, event, rank, key_prefix="ads_rank")


def _render_barriers(st: Any, copt_points: pd.DataFrame, barriers: pd.DataFrame) -> None:
    if barriers.empty:
        st.info("No constrained-optimization barrier paths were detected in the current data.")
        return
    try:
        import plotly.express as px
    except ImportError:
        st.dataframe(barriers, hide_index=True, width="stretch")
        return

    st.markdown("**Constrained-optimization barriers**")
    shown_columns = [
        "copt_reaction",
        "copt_path_id",
        "n_points",
        "forward_barrier_eV",
        "reverse_barrier_eV",
        "reaction_energy_eV",
        "ts_step",
        "complete_scan",
    ]
    barrier_display = barriers[[column for column in shown_columns if column in barriers.columns]].sort_values(
            "forward_barrier_eV",
            ascending=False,
        )
    st.dataframe(
        barrier_display,
        hide_index=True,
        width="stretch",
        height=320,
    )

    left, right = st.columns([0.44, 0.56])
    with left:
        rank = barriers.loc[barriers["n_points"] >= 3].sort_values("forward_barrier_eV").tail(20)
        rank = rank.assign(label=rank["copt_reaction"].astype(str) + " | path " + rank["copt_path_id"].astype(str))
        fig = px.bar(
            rank,
            x="forward_barrier_eV",
            y="label",
            orientation="h",
            color="complete_scan",
            color_discrete_map={True: "#5477C4", False: "#CC6F47"},
        )
        _style_plotly(fig, "Apparent copt barrier ranking")
        fig.update_layout(yaxis=dict(automargin=True), height=560)
        st.plotly_chart(fig, width="stretch")
    with right:
        options = barriers.sort_values("forward_barrier_eV", ascending=False)["copt_series_id"].tolist()
        selected = st.selectbox("copt path", options, format_func=_short_series_label)
        profile = copt_points[copt_points["copt_series_id"].eq(selected)].sort_values("copt_step")
        profile_display_columns = [
            column
            for column in ["dataset_label", "Name", "Formula", "copt_step", "E", "relative_E_from_initial_eV", "fmax"]
            if column in profile.columns
        ]
        if profile_display_columns:
            event = st.dataframe(
                profile[profile_display_columns],
                hide_index=True,
                width="stretch",
                height=220,
                selection_mode="single-row",
                on_select="rerun",
                key="onepiece_studio_copt_profile_table",
            )
            selected_index = selected_dataframe_index(event, profile[profile_display_columns])
            if selected_index is not None and selected_index in copt_points.index:
                _render_row_actions(st, copt_points.loc[selected_index], selected_index, key_prefix="copt_table")
        profile = profile.copy()
        profile["__onepiece_studio_index"] = profile.index.astype(str)
        fig = px.line(
            profile,
            x="copt_step",
            y="relative_E_from_initial_eV",
            markers=True,
            hover_data=[c for c in ["Name", "E", "fmax"] if c in profile],
            custom_data=["__onepiece_studio_index"],
        )
        _style_plotly(fig, "Selected copt energy profile")
        fig.add_hline(y=0, line_dash="dot", line_color="#1F2430")
        event = st.plotly_chart(
            fig,
            width="stretch",
            key="onepiece_studio_copt_profile_plot",
            on_select="rerun",
            selection_mode="points",
        )
        _render_plot_actions(st, event, profile, key_prefix="copt_plot")

    st.download_button(
        "Download barrier summary CSV",
        barriers.to_csv(index=False).encode("utf-8"),
        file_name="onepiece_studio_copt_barrier_summary.csv",
        mime="text/csv",
        width="stretch",
    )


def _render_plot_actions(st: Any, event: Any, dataframe: pd.DataFrame, *, key_prefix: str) -> None:
    selected_index = selected_plot_index(event)
    if selected_index is None:
        return
    if selected_index not in dataframe.index:
        st.warning(f"Selected row {selected_index} is no longer visible in this plot.")
        return
    _render_row_actions(st, dataframe.loc[selected_index], selected_index, key_prefix=key_prefix)


def _render_row_actions(st: Any, row: pd.Series, index: Any, *, key_prefix: str) -> None:
    st.markdown("**Selected calculation**")
    st.dataframe(selected_row_summary(row), hide_index=True, width="stretch")
    render_action_grid(st, row, index, key_prefix=key_prefix, namespace="onepiece_studio_ads")


def _render_method(st: Any) -> None:
    st.markdown(
        """
**Workflow**

1. Read local OnePiece/pandas tables.
2. Split by `source_hdf`, `dataset_label`, or `dataset`.
3. Detect adsorbates from calculation names, e.g. `-CO-1` or `-CH3O-1`.
4. Assign clean-surface references inside each source before merging.
5. Calculate `delta_E_to_surface_eV`.
6. Insert gas references to activate final adsorption-energy columns.
7. Parse `copt/.../step` paths into constrained-optimization profiles.

**Formulas**

CO adsorption:

`E_ads(CO) = (E(CO*) - E(*) - n E(CO_gas)) / n`

Methoxy from methanol:

`* + CH3OH(g) -> CH3O* + 1/2 H2(g)`

`E_ads = (E(CH3O*) + 0.5 n E(H2) - E(*) - n E(CH3OH)) / n`

The `copt` barrier is an apparent scan barrier:

`E_barrier = max(E along copt path) - E(initial step)`
"""
    )


def _style_plotly(fig: Any, title: str) -> None:
    fig.update_layout(
        title=title,
        font_family="system-ui",
        title_font_family="system-ui",
        paper_bgcolor="#FCFCFD",
        plot_bgcolor="#FFFFFF",
        margin=dict(l=12, r=12, t=56, b=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#E6E8F0", zerolinecolor="#1F2430")
    fig.update_yaxes(showgrid=True, gridcolor="#E6E8F0")


def _row_keys(dataframe: pd.DataFrame) -> pd.Series:
    if {"source_hdf", "source_row"}.issubset(dataframe.columns):
        return dataframe["source_hdf"].astype(str) + "::" + dataframe["source_row"].astype(str)
    return dataframe.index.astype(str).to_series(index=dataframe.index)


def _short_series_label(value: str) -> str:
    parts = str(value).split("|")
    if len(parts) >= 4:
        return f"{parts[-2]} | path {parts[-1]}"
    return str(value)
