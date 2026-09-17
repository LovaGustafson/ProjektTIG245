"""The grouped invoice data supplied to later verification-level checks."""

from dataclasses import dataclass

import pandas as pd


@dataclass(eq=False)
class Verification:
    """One grouping key and its complete, independently editable row data.

    Valid verification keys are strings; integral Excel numbers normalize only
    for this key. Text keys retain their spelling. Invalid/null grouping keys
    remain the caller's responsibility because validation is a separate step.
    rows retains all input columns, dtypes, index labels and row order.
    """

    verification_id: object
    rows: pd.DataFrame
