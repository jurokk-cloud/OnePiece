from __future__ import annotations

import pandas as pd

from onepiece.workflows import apply_operations


def test_apply_operations_records_audit_log_for_successful_steps() -> None:
    frame = pd.DataFrame({"Name": ["row-a", "row-b"], "E": [1.0, 2.0]})
    result = apply_operations(
        frame,
        [
            {
                "kind": "derive_scalar",
                "label": "Shift energy",
                "left": "E",
                "operator": "+",
                "scalar": 0.5,
                "new_column": "E_shifted",
            }
        ],
    )

    assert result.messages == []
    assert result.dataframe["E_shifted"].tolist() == [1.5, 2.5]
    assert len(result.audit_log) == 1
    activity = result.audit_log[0]
    assert activity["kind"] == "derive_scalar"
    assert activity["label"] == "Shift energy"
    assert activity["status"] == "ok"
    assert activity["row_count_before"] == 2
    assert activity["row_count_after"] == 2
    assert activity["added_columns"] == ["E_shifted"]
    assert activity["inputs"] == ["dataframe:step-0"]
    assert activity["outputs"] == ["dataframe:step-1"]


def test_apply_operations_records_failed_steps_without_losing_dataframe() -> None:
    frame = pd.DataFrame({"Name": ["row-a"], "E": [1.0]})
    result = apply_operations(
        frame,
        [
            {
                "kind": "derive_scalar",
                "label": "Broken step",
                "left": "missing_column",
                "operator": "+",
                "scalar": 0.5,
                "new_column": "bad",
            }
        ],
    )

    assert "bad" not in result.dataframe.columns
    assert len(result.messages) == 1
    assert result.audit_log[0]["status"] == "failed"
    assert "Broken step" in result.audit_log[0]["error"]
    assert result.audit_log[0]["row_count_after"] == 1
