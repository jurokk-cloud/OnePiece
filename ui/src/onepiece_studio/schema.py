from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:  # StrEnum is only available on Python 3.11+
    from enum import StrEnum
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Minimal StrEnum backport for Python 3.10."""

import pandas as pd


class ColumnKind(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    IMAGE = "image"
    STRUCTURE = "structure"
    JSON = "json"


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    name: str
    kind: ColumnKind
    nullable: bool
    unique_count: int
    sample: Any | None = None


def infer_schema(
    dataframe: pd.DataFrame,
    *,
    image_columns: list[str] | None = None,
    structure_columns: list[str] | None = None,
) -> list[ColumnSchema]:
    image_columns = image_columns or []
    structure_columns = structure_columns or []
    schemas: list[ColumnSchema] = []

    for column in dataframe.columns:
        series = dataframe[column]
        sample = _first_non_null(series)
        schemas.append(
            ColumnSchema(
                name=str(column),
                kind=_infer_kind(series, str(column), image_columns, structure_columns, sample),
                nullable=bool(series.isna().any()),
                unique_count=safe_unique_count(series),
                sample=sample,
            )
        )

    return schemas


def _infer_kind(
    series: pd.Series,
    column: str,
    image_columns: list[str],
    structure_columns: list[str],
    sample: Any | None,
) -> ColumnKind:
    if column in image_columns:
        return ColumnKind.IMAGE
    if column in structure_columns or sample.__class__.__name__ == "Atoms":
        return ColumnKind.STRUCTURE
    if pd.api.types.is_bool_dtype(series):
        return ColumnKind.BOOLEAN
    if pd.api.types.is_numeric_dtype(series):
        return ColumnKind.NUMBER
    if pd.api.types.is_datetime64_any_dtype(series):
        return ColumnKind.DATETIME
    if isinstance(sample, dict | list | tuple):
        return ColumnKind.JSON
    return ColumnKind.TEXT


def _first_non_null(series: pd.Series) -> Any | None:
    values = series.dropna()
    if values.empty:
        return None
    return values.iloc[0]


def safe_unique_count(series: pd.Series) -> int:
    try:
        return int(series.nunique(dropna=True))
    except TypeError:
        return int(series.dropna().map(repr).nunique(dropna=True))
