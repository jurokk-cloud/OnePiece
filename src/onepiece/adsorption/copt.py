"""Constrained-optimization (copt) path annotation and barrier summaries."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from onepiece.adsorption.formulas import NAME_COPT_PATTERN, primary_structure
from onepiece.frame_utils import ensure_name_index, row_name


def is_constrained_optimization(frame: pd.DataFrame) -> pd.Series:
    """Identify constrained optimization rows, primarily copt path scans."""
    text = _combined_text(frame)
    return text.str.contains(r"(?:^|[-_/])copt(?:$|[-_/])", case=False, regex=True, na=False)


def annotate_copt_paths(frame: pd.DataFrame) -> pd.DataFrame:
    """Annotate constrained-optimization metadata from Path or Name."""
    df = ensure_name_index(frame)
    df["Name"] = df.get("Name", pd.Series([""] * len(df), index=df.index)).astype(str)
    df["Path"] = df.get("Path", pd.Series([""] * len(df), index=df.index)).astype(str)
    df["E"] = pd.to_numeric(df.get("E"), errors="coerce")
    df["is_copt"] = is_constrained_optimization(df)

    metadata = df.apply(_parse_copt_metadata, axis=1, result_type="expand")
    for column in metadata.columns:
        df[column] = metadata[column]
    return df


def copt_profile_points(frame: pd.DataFrame) -> pd.DataFrame:
    """Return point-level relative energies for constrained-optimization paths."""
    df = annotate_copt_paths(frame)
    points = df.loc[
        df["is_copt"]
        & df["copt_step"].notna()
        & df["copt_series_id"].notna()
        & df["E"].notna()
        & (df["E"] != 0)
    ].copy()
    if points.empty:
        return points

    points["copt_step"] = points["copt_step"].astype(int)
    points = points.sort_values(["copt_series_id", "copt_step", "E"])
    points = points.drop_duplicates(["copt_series_id", "copt_step"], keep="first")
    first_energy = points.groupby("copt_series_id")["E"].transform("first")
    min_energy = points.groupby("copt_series_id")["E"].transform("min")
    points["relative_E_from_initial_eV"] = points["E"] - first_energy
    points["relative_E_from_min_eV"] = points["E"] - min_energy
    return points


def copt_barrier_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Summarize apparent barriers from constrained-optimization path energies."""
    points = copt_profile_points(frame)
    if points.empty:
        return pd.DataFrame(
            columns=[
                "copt_series_id",
                "dataset_label",
                "copt_surface_base",
                "copt_reaction",
                "copt_path_id",
                "n_points",
                "initial_E_eV",
                "final_E_eV",
                "max_E_eV",
                "forward_barrier_eV",
                "reverse_barrier_eV",
                "reaction_energy_eV",
                "ts_step",
                "complete_scan",
            ]
        )

    rows = []
    for series_id, group in points.groupby("copt_series_id", sort=False):
        ordered = group.sort_values("copt_step")
        initial = float(ordered["E"].iloc[0])
        final = float(ordered["E"].iloc[-1])
        max_row = ordered.loc[ordered["E"].idxmax()]
        steps = set(ordered["copt_step"].astype(int))
        rows.append(
            {
                "copt_series_id": series_id,
                "dataset_label": ordered["dataset_label"].iloc[0]
                if "dataset_label" in ordered
                else ordered.get("dataset", pd.Series([""])).iloc[0],
                "copt_surface_base": ordered["copt_surface_base"].iloc[0],
                "copt_reaction": ordered["copt_reaction"].iloc[0],
                "copt_path_id": ordered["copt_path_id"].iloc[0],
                "n_points": int(len(ordered)),
                "initial_E_eV": initial,
                "final_E_eV": final,
                "max_E_eV": float(max_row["E"]),
                "forward_barrier_eV": float(max_row["E"] - initial),
                "reverse_barrier_eV": float(max_row["E"] - final),
                "reaction_energy_eV": float(final - initial),
                "ts_step": int(max_row["copt_step"]),
                "complete_scan": bool({0, 6}.issubset(steps) and len(steps) >= 5),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["copt_reaction", "forward_barrier_eV"], ascending=[True, False]
    )


def _combined_text(frame: pd.DataFrame) -> pd.Series:
    name = frame.get("Name", pd.Series([""] * len(frame), index=frame.index)).astype(str)
    path = frame.get("Path", pd.Series([""] * len(frame), index=frame.index)).astype(str)
    return name + " " + path


def _parse_copt_metadata(row: pd.Series) -> pd.Series:
    path_text = str(row.get("Path", ""))
    name_text = row_name(row)
    dataset = str(row.get("dataset_label", row.get("dataset", "")))
    atoms = primary_structure(row)

    parts = [part for part in Path(path_text).parts if part not in ("/", "")]
    lower_parts = [part.lower() for part in parts]
    if "copt" in lower_parts:
        idx = lower_parts.index("copt")
        surface_base = name_text.split("-copt-", 1)[0] if "-copt-" in name_text else ""
        if not surface_base and idx > 0:
            surface_base = parts[idx - 1]
        reaction = parts[idx + 1] if idx + 1 < len(parts) else ""
        path_id = parts[idx + 2] if idx + 2 < len(parts) else ""
        step = _safe_int(parts[idx + 3] if idx + 3 < len(parts) else None)
    else:
        match = NAME_COPT_PATTERN.match(name_text)
        surface_base = match.group("surface_base") if match else ""
        reaction = match.group("reaction") if match else ""
        path_id = match.group("path_id") if match else ""
        step = _safe_int(match.group("step") if match else None)

    series_id = None
    if surface_base and reaction and path_id:
        series_id = f"{dataset}|{surface_base}|{reaction}|{path_id}"

    initial_state = reaction.split("%", 1)[0] if "%" in reaction else ""
    final_state = reaction.split("%", 1)[1] if "%" in reaction else ""
    fixed_pairs, fixed_lengths = _extract_fixbond_constraints(atoms)

    return pd.Series(
        {
            "copt_surface_base": surface_base or np.nan,
            "copt_reaction": reaction or np.nan,
            "copt_path_id": path_id or np.nan,
            "copt_step": step if step is not None else np.nan,
            "copt_series_id": series_id,
            "copt_initial_state": initial_state or np.nan,
            "copt_final_state": final_state or np.nan,
            "copt_constraint_kind": "FixBondLengths" if fixed_pairs else np.nan,
            "copt_fixed_bond_pairs": fixed_pairs or None,
            "copt_fixed_bond_lengths_A": fixed_lengths or None,
        }
    )


def _safe_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _extract_fixbond_constraints(atoms: object) -> tuple[list[tuple[int, int]], list[float]]:
    if atoms is None or atoms.__class__.__name__ != "Atoms":
        return [], []
    pairs: list[tuple[int, int]] = []
    lengths: list[float] = []
    for constraint in getattr(atoms, "constraints", []) or []:
        if constraint.__class__.__name__ != "FixBondLengths":
            continue
        constraint_pairs = np.asarray(getattr(constraint, "pairs", []), dtype=int)
        for first, second in constraint_pairs:
            pairs.append((int(first), int(second)))
            try:
                lengths.append(float(atoms.get_distance(int(first), int(second), mic=True)))
            except Exception:
                lengths.append(float("nan"))
    return pairs, lengths
