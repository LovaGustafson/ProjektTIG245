"""Group standardized rows into verifications without changing business data."""

from copy import deepcopy

import pandas as pd

from src.models.verification import Verification


def build_verifications(data: pd.DataFrame) -> list[Verification]:
    """Return verifications in first-appearance order, retaining every input row.

    Expects a DataFrame with one verification_id column containing standardized,
    groupable IDs. Mapping and validation belong to upstream components.
    IDs are not trimmed, converted or normalized. Rows within each verification
    remain in input order; line IDs are neither sorted nor deduplicated.

    Every group contains an independent DataFrame, including copies of mutable
    object-cell contents. No columns are aggregated or promoted to verification
    fields. Empty input with the expected schema returns an empty list.

    Null grouping keys are retained using pandas' dropna=False semantics, so
    they cannot silently discard rows. This is not a valid-identity decision.
    TODO: the pipeline must define how to route rows with invalid identities
    after validation; a null-key group must not imply one real verification.
    """
    verifications = []
    for _, group in data.groupby("verification_id", sort=False, dropna=False, observed=True):
        rows = group.copy(deep=True)
        # pandas deep copies its arrays, but not objects held inside those arrays.
        for column_position, dtype in enumerate(rows.dtypes):
            if pd.api.types.is_object_dtype(dtype):
                for row_position in range(len(rows)):
                    rows.iat[row_position, column_position] = deepcopy(
                        rows.iat[row_position, column_position]
                    )
        verifications.append(Verification(
            verification_id=deepcopy(rows["verification_id"].iloc[0]),
            rows=rows,
        ))
    return verifications
