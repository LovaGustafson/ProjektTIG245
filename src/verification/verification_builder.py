"""Group standardized rows into verifications without changing business data."""

from copy import deepcopy

import pandas as pd

from src.models.verification import Verification
from src.mapping.identifiers import normalize_identifier


def build_verifications(data: pd.DataFrame) -> list[Verification]:
    """Return verifications in first-appearance order, retaining every input row.

    Expects a DataFrame with one verification_id column containing standardized,
    groupable IDs. Validation belongs to upstream components. Finite integral
    numeric IDs use the same text comparison key as validation; text IDs retain
    their exact spelling. The original ID cells and dtypes remain in rows.
    Rows within each verification
    remain in input order; line IDs are neither sorted nor deduplicated.

    Every group contains an independent DataFrame, including copies of mutable
    object-cell contents. No columns are aggregated or promoted to verification
    fields. Empty input with the expected schema returns an empty list.

    Null grouping keys are retained using pandas' dropna=False semantics, so
    they cannot silently discard rows. This is not a valid-identity decision.
    src/pipeline.py routes retained rows with unusable verification IDs to
    ungrouped_data before calling this builder. Final business disposition
    remains open (OPEN_QUESTIONS.md Q5); a null-key group created by a direct
    caller must not imply one real verification.
    """
    verifications = []
    def grouping_key(value):
        normalized = normalize_identifier(value)
        return normalized if normalized is not None else value
    keys = data['verification_id'].map(grouping_key)
    for _, group in data.groupby(keys, sort=False, dropna=False, observed=True):
        rows = group.copy(deep=True)
        # pandas deep copies its arrays, but not objects held inside those arrays.
        for column_position, dtype in enumerate(rows.dtypes):
            if pd.api.types.is_object_dtype(dtype):
                for row_position in range(len(rows)):
                    rows.iat[row_position, column_position] = deepcopy(
                        rows.iat[row_position, column_position]
                    )
        verifications.append(Verification(
            verification_id=deepcopy(grouping_key(rows["verification_id"].iloc[0])),
            rows=rows,
        ))
    return verifications
