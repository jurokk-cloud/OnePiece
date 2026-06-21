"""Session-state helpers shared by the Workflow Builder rendering modules."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from onepiece_studio.state import WORKFLOW_OPERATIONS
from onepiece_studio.workflow_logic import WORKFLOW_GAS_LABELS

logger = logging.getLogger(__name__)


def init_workflow_state(st: Any) -> None:
    st.session_state.setdefault(WORKFLOW_OPERATIONS, [])


def append_operation(st: Any, operation: dict[str, Any] | None) -> None:
    if not operation:
        return
    operation = dict(operation)
    operation["enabled"] = True
    operation["created_at"] = datetime.now().isoformat(timespec="seconds")
    st.session_state.setdefault(WORKFLOW_OPERATIONS, []).append(operation)


def append_operations(st: Any, operations: list[dict[str, Any]]) -> None:
    for operation in operations:
        append_operation(st, operation)


def workflow_gas_reference_values(st: Any, dataframe: pd.DataFrame) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for label in WORKFLOW_GAS_LABELS:
        state_key = f"onepiece_studio_ads_gas_value_{label}"
        if state_key in st.session_state:
            try:
                values[label] = float(st.session_state[state_key])
                continue
            except (TypeError, ValueError):
                pass

    missing = [label for label in WORKFLOW_GAS_LABELS if label not in values]
    if missing:
        try:
            from onepiece.sources import gas_reference_candidates

            candidates = gas_reference_candidates(dataframe)
            for label in missing:
                frame = candidates.get(label)
                if frame is not None and not frame.empty:
                    values[label] = float(frame.iloc[0]["E"])
        except Exception as exc:
            logger.debug("Could not infer fallback gas references from the dataframe: %s", exc)
    return values
