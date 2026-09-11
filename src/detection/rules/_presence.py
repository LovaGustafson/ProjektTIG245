"""Shared mechanics for explicitly configured presence checks; no default policy."""

from typing import Literal

import pandas as pd

from src.models.result import CheckResult, CheckStatus
from src.models.verification import Verification


PresenceScope = Literal["each_row", "any_row"]


def check_presence(
    verification: Verification, fields: tuple[str, ...], scope: PresenceScope,
    check_type: str,
) -> tuple[CheckResult, ...]:
    """Check each field separately, preserving all results and flag reasons.

    Nulls, absent columns and blank strings count as missing. Containers are
    uninterpretable and return ERROR, rather than being treated as present.
    any_row means at least one row per field, not necessarily the same row.
    An image_reference PASS only describes the reference cell, not the file.
    """
    def result(status, reason, field=None, line_id=None, position=None):
        return CheckResult(
            verification.verification_id, check_type, status, reason,
            verification_line_id=line_id, field=field, row_position=position,
        )

    rows = verification.rows
    if not isinstance(rows, pd.DataFrame) or len(rows) == 0:
        return (result(CheckStatus.ERROR, "Cannot check presence: no row data available"),)
    if scope not in ("each_row", "any_row"):
        return (result(CheckStatus.ERROR, "Unsupported presence scope"),)

    output = []
    for field in fields:
        columns = [i for i, name in enumerate(rows.columns)
                   if isinstance(name, str) and name == field]
        if len(columns) > 1:
            output.append(result(CheckStatus.ERROR, f"Ambiguous duplicate column: {field}", field))
            continue
        states = []
        for position in range(len(rows)):
            value = rows.iloc[position, columns[0]] if columns else None
            if isinstance(value, str):
                state = bool(value.strip())
            elif not pd.api.types.is_scalar(value):
                state = None
            else:
                try:
                    state = not bool(pd.isna(value))
                except (TypeError, ValueError):
                    state = None
            states.append(state)

        if scope == "any_row":
            if True in states:
                output.append(result(CheckStatus.PASS, f"{field}: information present on at least one row", field))
            elif None in states:
                output.append(result(CheckStatus.ERROR, f"{field}: presence could not be determined", field))
            else:
                output.append(result(CheckStatus.FLAGGED, f"Missing required information: {field}", field))
            continue

        line_columns = [i for i, name in enumerate(rows.columns)
                        if isinstance(name, str) and name == "verification_line_id"]
        for position, state in enumerate(states):
            if len(line_columns) != 1:
                output.append(result(CheckStatus.ERROR,
                                     "Cannot attribute row check: missing or ambiguous verification_line_id",
                                     field, position=position))
                continue
            line_id = rows.iloc[position, line_columns[0]]
            if not pd.api.types.is_scalar(line_id) or pd.isna(line_id):
                output.append(result(CheckStatus.ERROR, "Cannot attribute row check: missing verification_line_id",
                                     field, position=position))
                continue
            if state is None:
                status, reason = CheckStatus.ERROR, f"{field}: presence could not be determined"
            elif state:
                status, reason = CheckStatus.PASS, f"{field}: information present on row"
            else:
                status, reason = CheckStatus.FLAGGED, f"Missing required information: {field}"
            output.append(result(status, reason, field, line_id, position))
    return tuple(output)
