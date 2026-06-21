from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from onepiece_studio.schema import safe_unique_count
from onepiece_studio.ui.row_actions import render_action_grid, selected_row_summary


def render_visualizations(st: Any, dataframe: pd.DataFrame) -> None:
    numeric_columns = list(dataframe.select_dtypes(include="number").columns)
    categorical_columns = _categorical_columns(dataframe, exclude=numeric_columns, max_unique=30)
    for preferred in ["surface_ref_name", "surface_ref_status", "adsorbate", "dataset_label"]:
        if preferred in dataframe.columns and preferred not in categorical_columns:
            categorical_columns.append(preferred)
    if not numeric_columns:
        st.info("No numeric columns available for plotting.")
        return

    presets = _chart_presets(dataframe, numeric_columns, categorical_columns)
    preset_labels = list(presets)
    st.write("Analysis preset")
    selected_preset = st.segmented_control(
        "Analysis preset",
        preset_labels,
        default=preset_labels[0],
        label_visibility="collapsed",
    )
    preset = presets[selected_preset]
    st.caption(preset["takeaway"])

    mode = st.segmented_control("Chart type", ["Scatter", "Histogram"], default="Scatter")
    if mode == "Scatter" and len(numeric_columns) >= 2:
        x_column, y_column, color_column = st.columns(3)
        x = x_column.selectbox("x", numeric_columns, index=_column_index(numeric_columns, preset["x"]))
        y = y_column.selectbox("y", numeric_columns, index=_column_index(numeric_columns, preset["y"], fallback=min(1, len(numeric_columns) - 1)))
        color_options = ["None", *categorical_columns]
        color = color_column.selectbox(
            "color",
            color_options,
            index=_column_index(color_options, preset.get("color", "None")),
        )
        kwargs = {
            "x": x,
            "y": y,
            "hover_data": [
                c for c in ["dataset", "source_hdf", "Name", "Formula", "legend"] if c in dataframe
            ],
        }
        if color != "None":
            kwargs["color"] = color
        st.caption(_chart_interpretation(preset["title"], x, y, color))
        try:
            import plotly.express as px

            chart_data = dataframe.replace([np.inf, -np.inf], np.nan).dropna(subset=[x, y]).copy()
            chart_data["__onepiece_studio_index"] = chart_data.index.astype(str)
            fig = px.scatter(
                chart_data,
                **kwargs,
                custom_data=["__onepiece_studio_index"],
                title=preset["title"],
                color_discrete_sequence=["#d33f49", "#2f4858", "#33658a", "#8a6f3d", "#3f7d20"],
            )
            fig.update_traces(
                hovertemplate=(
                    f"{x}: %{{x}}<br>"
                    f"{y}: %{{y}}<br>"
                    "row index: %{customdata[0]}<extra></extra>"
                )
            )
            fig.update_layout(
                font_family="system-ui",
                title_font_family="system-ui",
                paper_bgcolor="white",
                plot_bgcolor="white",
                margin=dict(l=8, r=8, t=56, b=8),
                xaxis_title=_column_plot_label(x),
                yaxis_title=_column_plot_label(y),
                legend_title_text=_column_plot_label(color) if color != "None" else None,
            )
            fig.update_traces(marker=dict(size=8, line=dict(width=0.5, color="#2f343d")))
            event = st.plotly_chart(
                fig,
                width="stretch",
                key="onepiece_studio_visualize_scatter",
                on_select="rerun",
                selection_mode="points",
            )
            _render_plot_selection_actions(st, event, chart_data, dataframe)
        except ImportError:
            st.scatter_chart(dataframe, x=x, y=y, width="stretch")
    else:
        column = st.selectbox("value", numeric_columns, index=_column_index(numeric_columns, preset["y"]))
        st.caption(f"Distribution view for {_column_plot_label(column)}.")
        try:
            import plotly.express as px

            chart_data = dataframe.replace([np.inf, -np.inf], np.nan).dropna(subset=[column])
            fig = px.histogram(
                chart_data,
                x=column,
                nbins=30,
                title=f"Distribution of {_column_plot_label(column)}",
                color_discrete_sequence=["#d33f49"],
            )
            fig.update_layout(
                font_family="system-ui",
                title_font_family="system-ui",
                paper_bgcolor="white",
                plot_bgcolor="white",
                margin=dict(l=8, r=8, t=56, b=8),
                xaxis_title=_column_plot_label(column),
                yaxis_title="Count",
            )
            st.plotly_chart(fig, width="stretch")
        except ImportError:
            st.bar_chart(dataframe[column].value_counts().sort_index(), width="stretch")


def _render_plot_selection_actions(
    st: Any,
    event: Any,
    chart_data: pd.DataFrame,
    dataframe: pd.DataFrame,
) -> None:
    selected_index = _selected_plot_index(event)
    if selected_index is None:
        st.caption("Click a scatter point to inspect, exclude, mark review, or open it in ASE.")
        return

    if selected_index not in dataframe.index:
        st.warning(f"Selected row {selected_index} is no longer in the active filtered dataset.")
        return

    row = dataframe.loc[selected_index]
    st.markdown("**Selected calculation**")
    st.dataframe(selected_row_summary(row), hide_index=True, width="stretch")

    render_action_grid(
        st,
        row,
        selected_index,
        key_prefix="plot",
        namespace="onepiece_studio_plot",
        exclude_label="Exclude calculation",
        review_label="Mark review",
        reference_label="Mark reference",
        open_label="Open ASE viewer",
    )


def _selected_plot_index(event: Any) -> int | str | None:
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    points = getattr(selection, "points", None)
    if points is None and isinstance(selection, dict):
        points = selection.get("points")
    if not points:
        return None
    point = points[0]
    customdata = getattr(point, "customdata", None)
    if customdata is None and isinstance(point, dict):
        customdata = point.get("customdata")
    if not customdata:
        return None
    raw = customdata[0]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return raw


def _categorical_columns(
    dataframe: pd.DataFrame,
    *,
    exclude: list[str],
    max_unique: int,
) -> list[str]:
    columns: list[str] = []
    for column in dataframe.columns:
        if column in exclude or not _is_simple_categorical(dataframe[column]):
            continue
        if safe_unique_count(dataframe[column]) <= max_unique:
            columns.append(column)
    return columns


def _is_simple_categorical(series: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(series):
        return True
    if series.dtype != "object":
        return False
    sample = _first_non_null(series)
    return isinstance(sample, str | bool)


def _first_non_null(series: pd.Series) -> Any | None:
    values = series.dropna()
    if values.empty:
        return None
    return values.iloc[0]


def _chart_presets(
    dataframe: pd.DataFrame,
    numeric_columns: list[str],
    categorical_columns: list[str],
) -> dict[str, dict[str, str]]:
    presets = {
        "Surface stability": {
            "x": _first_available(numeric_columns, ["Area", "Ga", "E"]),
            "y": _first_available(numeric_columns, ["form_G_per_Area", "form_G_per_alloy", "E"]),
            "color": _first_available(categorical_columns, ["slabsize", "hkl", "alloy"], default="None"),
            "title": "Surface stability across filtered candidates",
            "takeaway": "Use this view to compare formation energy at the same filtered observation grain.",
        },
        "Coordination vs stability": {
            "x": _first_available(numeric_columns, ["average_Ga_GCN", "average_Cu_GCN", "Ga"]),
            "y": _first_available(numeric_columns, ["form_G_per_alloy", "form_G_per_Area", "E"]),
            "color": _first_available(categorical_columns, ["alloy", "slabsize", "hkl"], default="None"),
            "title": "Coordination descriptors versus stability",
            "takeaway": "Scatter is appropriate here because each point is one structure candidate.",
        },
        "Charge descriptors": {
            "x": _first_available(numeric_columns, ["min_Ga_charge", "average_Ga_charge", "average_Cu_charge"]),
            "y": _first_available(numeric_columns, ["form_G_per_Area", "form_G_per_alloy", "E"]),
            "color": _first_available(categorical_columns, ["slabsize", "alloy", "hkl"], default="None"),
            "title": "Charge descriptor relationship",
            "takeaway": "Use charge descriptors to spot unusual candidates, then inspect exact rows in the table.",
        },
        "Relaxation quality": {
            "x": _first_available(numeric_columns, ["E", "Area", "Ga"]),
            "y": _first_available(numeric_columns, ["fmax", "form_G_per_Area", "E"]),
            "color": _first_available(categorical_columns, ["slabsize", "hkl", "alloy"], default="None"),
            "title": "Relaxation quality check",
            "takeaway": "High force values can flag records that should be reviewed before comparing energies.",
        },
    }
    if "adsorbate_charge_delta_vs_ref_e" in numeric_columns and "E_ads_CO_eV" in numeric_columns:
        presets = {
            "Charge transfer vs adsorption energy": {
                "x": _first_available(
                    numeric_columns,
                    ["adsorbate_charge_delta_vs_ref_e", "adsorbate_net_charge_e", "surface_net_charge_delta_vs_ref_e"],
                ),
                "y": _first_available(
                    numeric_columns,
                    ["E_ads_CO_eV", "E_ads_CH3OH_to_CH3O_eV", "adsorption_energy"],
                ),
                "color": _first_available(
                    categorical_columns,
                    ["adsorption_site", "surface_ref_name", "adsorbate", "dataset_label"],
                    default="None",
                ),
                "title": "Charge transfer versus adsorption energy",
                "takeaway": "Use this to see whether stronger binding correlates with more electron transfer into or out of the adsorbate.",
            },
            **presets,
        }
    if "surface_net_charge_delta_vs_ref_e" in numeric_columns and "adsorbate_height_above_surface" in numeric_columns:
        presets = {
            "Surface polarization vs adsorbate height": {
                "x": _first_available(
                    numeric_columns,
                    ["adsorbate_height_above_surface", "min_adsorbate_surface_distance", "adsorbate_tilt_deg"],
                ),
                "y": _first_available(
                    numeric_columns,
                    ["surface_net_charge_delta_vs_ref_e", "adsorbate_charge_delta_vs_ref_e", "surface_reconstruction_rmsd"],
                ),
                "color": _first_available(
                    categorical_columns,
                    ["adsorption_site", "adsorbate", "surface_ref_name", "dataset_label"],
                    default="None",
                ),
                "title": "Surface polarization versus adsorption geometry",
                "takeaway": "This view is useful when you want to connect geometric lift-off or tilt with charge rearrangement in the slab.",
            },
            **presets,
        }
    if "metal_d_band_center_eV" in numeric_columns:
        presets = {
            "d-band center vs adsorption energy": {
                "x": _first_available(
                    numeric_columns,
                    ["metal_d_band_center_eV", "metal_d_band_filling"],
                ),
                "y": _first_available(
                    numeric_columns,
                    ["E_ads_CO_eV", "adsorption_energy", "E"],
                ),
                "color": _first_available(
                    categorical_columns,
                    ["adsorption_site", "surface_ref_name", "adsorbate", "dataset_label"],
                    default="None",
                ),
                "title": "d-band descriptor versus adsorption energy",
                "takeaway": "Use this as the first electronic-structure screening plot when DOSCAR-based d-band descriptors are available.",
            },
            **presets,
        }
    if "adsorption_site" in categorical_columns and "E_ads_CO_eV" in numeric_columns:
        presets = {
            "Adsorption site families": {
                "x": _first_available(
                    numeric_columns,
                    ["adsorbate_tilt_deg", "min_adsorbate_surface_distance", "adsorbate_height_above_surface"],
                ),
                "y": _first_available(
                    numeric_columns,
                    ["E_ads_CO_eV", "adsorbate_charge_delta_vs_ref_e", "surface_reconstruction_rmsd"],
                ),
                "color": _first_available(
                    categorical_columns,
                    ["adsorption_site", "adsorbate", "surface_ref_name", "dataset_label"],
                    default="None",
                ),
                "title": "Adsorption-site families across filtered candidates",
                "takeaway": "Coloring by site type helps separate top, bridge, hollow, and defect-like binding motifs before you inspect exact structures.",
            },
            **presets,
        }
    if "E_ads_CO_eV" in numeric_columns:
        presets = {
            "Adsorption analysis": {
                "x": _first_available(numeric_columns, ["E_ads_CO_total_eV", "delta_E_to_surface_eV", "E"]),
                "y": _first_available(numeric_columns, ["E_ads_CO_eV", "E_ads_CH3OH_to_CH3O_eV", "E"]),
                "color": _first_available(categorical_columns, ["surface_ref_name", "adsorbate", "dataset_label"], default="None"),
                "title": "Adsorption energy per CO across filtered candidates",
                "takeaway": "Start here after HDF import with adsorption preparation: compare total adsorption energy and per-CO energy, colored by the assigned surface reference.",
            },
            **presets,
        }
    return presets


def _column_plot_label(column: str | None) -> str:
    labels = {
        "E": "Total energy / eV",
        "fmax": "Maximum force / eV/A",
        "Area": "Surface area / A^2",
        "form_G_per_Area": "Formation free energy / eV A^-2",
        "form_G_per_alloy": "Formation free energy per alloy atom / eV",
        "formation_energy_per_atom": "Formation energy per atom / eV",
        "E_ads_CO_total_eV": "CO adsorption energy (total) / eV",
        "E_ads_CO_eV": "CO adsorption energy per CO / eV",
        "E_ads_CH3OH_to_CH3O_eV": "CH3O adsorption energy / eV",
        "adsorption_energy": "Adsorption energy / eV",
        "adsorbate_charge_delta_vs_ref_e": "Adsorbate charge change vs ref / e",
        "adsorbate_net_charge_e": "Adsorbate net charge / e",
        "surface_net_charge_delta_vs_ref_e": "Surface charge change vs clean ref / e",
        "surface_net_charge_e": "Surface net charge / e",
        "adsorbate_height_above_surface": "Adsorbate height above surface / A",
        "min_adsorbate_surface_distance": "Minimum adsorbate-surface distance / A",
        "mean_adsorbate_surface_distance": "Mean adsorbate-surface distance / A",
        "adsorbate_tilt_deg": "Adsorbate tilt / deg",
        "surface_reconstruction_rmsd": "Surface reconstruction RMSD / A",
        "surface_reconstruction_max_displacement": "Maximum surface displacement / A",
        "mean_coordination": "Mean coordination number",
        "mean_generalized_coordination": "Mean generalized coordination number",
        "min_interatomic_distance": "Minimum interatomic distance / A",
        "min_bond_ratio": "Minimum bond-length ratio",
        "metal_d_band_center_eV": "Metal d-band center / eV",
        "metal_d_band_filling": "Metal d-band filling",
        "adsorption_site": "Adsorption site",
        "surface_ref_name": "Surface reference",
        "adsorbate": "Adsorbate",
        "dataset_label": "Dataset",
    }
    if not column or column == "None":
        return "None"
    return labels.get(column, column.replace("_", " "))


def _chart_interpretation(title: str, x: str, y: str, color: str) -> str:
    base = f"{_column_plot_label(x)} on x and {_column_plot_label(y)} on y."
    if color != "None":
        base += f" Points are colored by {_column_plot_label(color)}."
    if "d-band" in title.lower():
        return base + " This is the classic first-pass electronic-structure view for catalyst screening."
    if "charge" in title.lower():
        return base + " Use it to see whether charge transfer tracks binding strength or structural distortion."
    if "site" in title.lower():
        return base + " This helps separate geometric binding motifs before inspecting individual structures."
    if "polarization" in title.lower():
        return base + " This is useful for linking adsorbate geometry to slab charge response."
    return base


def _first_available(columns: list[str], preferred: list[str], *, default: str | None = None) -> str:
    for column in preferred:
        if column in columns:
            return column
    if columns:
        return columns[0]
    return default or "None"


def _column_index(columns: list[str], column: str | None, *, fallback: int = 0) -> int:
    if column in columns:
        return columns.index(column)
    return min(fallback, len(columns) - 1)
