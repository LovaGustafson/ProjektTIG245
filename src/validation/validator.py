"""Data-quality checks for standardized invoice rows; no business transformations."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from numbers import Real
import re
from typing import Literal

import pandas as pd

from src.filtering.transaction_rows import non_transaction_reason
from src.mapping.identifiers import normalize_identifier


REQUIRED_FIELDS = (
    "verification_id",
    "verification_line_id",
    "verification_date",
    "amount",
    "account",
)


@dataclass(frozen=True)
class ValidationError:
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class RowValidationResult:
    row_position: int
    validation_status: Literal["VALID", "INVALID", "NOT_APPLICABLE"]
    validation_errors: tuple[ValidationError, ...]
    skipped_reason: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    rows: tuple[RowValidationResult, ...]
    schema_errors: tuple[ValidationError, ...]


def _missing(value: object) -> bool:
    if isinstance(value, str):
        return not value.strip()
    return pd.api.types.is_scalar(value) and bool(pd.isna(value))


def _number(value: object) -> Decimal | None:
    # Decimal avoids float rounding when checking integer identity or amounts.
    if isinstance(value, bool) or not isinstance(value, (str, Real, Decimal)):
        return None
    text = str(value).strip()
    if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text):
        return None
    try:
        number = Decimal(text)
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def _date_valid(value: object, date_format: str | None) -> bool:
    if isinstance(value, date):
        return True
    if not isinstance(value, str):
        return False
    try:
        if date_format is not None:
            datetime.strptime(value.strip(), date_format)
        else:
            datetime.fromisoformat(value.strip())
        return True
    except ValueError:
        return False


def validate(data: pd.DataFrame, *, date_format: str | None = None) -> ValidationResult:
    """Return metadata for every input row in its original positional order.

    row_position is zero-based and remains unambiguous with duplicate index
    labels. No data values, index labels, columns or dtypes are modified; the
    result contains only validation metadata, not a transformed DataFrame.
    Missing/duplicate required columns appear in schema_errors and each
    transaction row's errors. Recognized report rows retain their positions with
    NOT_APPLICABLE and a skipped_reason, without invoice-value errors. Missing
    IDs alone never identify a report row. Empty inputs retain schema errors.

    Identifier/account comparison keys accept nonblank text and finite integral
    Python/NumPy Excel numbers. Numbers normalize to integer text without
    rounding; source values remain unchanged. Text uses its exact spelling: no
    trimming, case folding, decimal parsing or removal of leading zeros.
    Line IDs accept finite integer-valued numbers or numeric
    strings; 1, 1.0 and '01' have the same integer identity. All occurrences of
    a duplicate identity are invalid, even if they have other errors. Incomplete
    or invalid identities are not compared for uniqueness.

    Numeric parsing accepts decimal-point notation and exponents; booleans,
    nonfinite values, currency labels and locale separators are invalid.
    Dates accept native date/datetime values and ISO date/datetime strings, or
    strings matching the caller's explicit date_format. Numeric Excel serials
    are not guessed. Nulls and blank strings are missing values.

    TODO: confirm source date formats, numeric locale and any line-ID range
    constraints. Only integrality is enforced; no positivity rule is invented.
    Optional business fields and config.required_fields are outside this check.
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame with standardized columns")
    if date_format is not None and not isinstance(date_format, str):
        raise TypeError("date_format must be a string or None")

    schema_errors = []
    positions = {}
    for field in REQUIRED_FIELDS:
        matches = [
            i for i, column in enumerate(data.columns)
            if isinstance(column, str) and column == field
        ]
        if len(matches) != 1:
            code = "missing_column" if not matches else "duplicate_column"
            schema_errors.append(ValidationError(field, code, f"{field}: {code}"))
        else:
            positions[field] = matches[0]

    errors_by_row = []
    skipped_rows = {}
    identities = defaultdict(list)
    # Include the index during iteration so even rows with no columns survive.
    for row_position, indexed_values in enumerate(data.itertuples(index=True, name=None)):
        values = indexed_values[1:]
        if len(data.columns):
            report_reason = non_transaction_reason(pd.Series(values, index=data.columns, dtype=object))
            if report_reason:
                skipped_rows[row_position] = report_reason
                errors_by_row.append([])
                continue
        errors = list(schema_errors)
        identity = {}
        for field, position in positions.items():
            value = values[position]
            if _missing(value):
                errors.append(ValidationError(field, "missing_value", f"Missing {field}"))
                continue
            if field in ("verification_id", "account"):
                normalized = normalize_identifier(value)
                valid = normalized is not None
                message = f"{field} must be nonblank text or a finite integer-valued Excel number"
                if valid and field == "verification_id":
                    identity[field] = normalized
            elif field == "verification_date":
                valid = _date_valid(value, date_format)
                message = "verification_date is not a valid date in the accepted format"
            else:
                number = _number(value)
                valid = number is not None
                message = f"{field} must be a finite numeric value"
                if field == "verification_line_id":
                    valid = valid and number == number.to_integral_value()
                    message = "verification_line_id must represent a finite integer"
                    if valid:
                        identity[field] = number
            if not valid:
                errors.append(ValidationError(field, "invalid_value", message))
        errors_by_row.append(errors)
        if len(identity) == 2:
            identities[(identity["verification_id"], identity["verification_line_id"])].append(
                row_position
            )

    for duplicate_positions in identities.values():
        if len(duplicate_positions) > 1:
            for position in duplicate_positions:
                errors_by_row[position].append(ValidationError(
                    "verification_id+verification_line_id",
                    "duplicate_identity",
                    "Duplicate verification_id + verification_line_id in dataset",
                ))

    return ValidationResult(
        rows=tuple(
            RowValidationResult(position,
                                "NOT_APPLICABLE" if position in skipped_rows else
                                "INVALID" if errors else "VALID",
                                tuple(errors), skipped_rows.get(position))
            for position, errors in enumerate(errors_by_row)
        ),
        schema_errors=tuple(schema_errors),
    )
