"""The grouped invoice data supplied to later verification-level checks."""

from dataclasses import dataclass

import pandas as pd


@dataclass(eq=False)
class Verification:
    """One grouping key and its complete, independently editable row data.

    Standardized verification IDs are strings. The builder retains the input
    key as supplied, including nulls, because validation is a separate step.
    rows retains all input columns, dtypes, index labels and row order.
    """

    verification_id: object
    rows: pd.DataFrame
