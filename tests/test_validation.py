"""Synthetic tests for row validation, independent of ingestion and mapping."""

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import numpy as np
import pytest

from src.validation.validator import REQUIRED_FIELDS, validate


def row(**changes):
    return {
        "verification_id": "00123",
        "verification_line_id": 1,
        "verification_date": "2026-09-03",
        "amount": Decimal("125.50"),
        "account": "7698",
        **changes,
    }


def frame(*rows):
    return pd.DataFrame(rows, dtype=object)


def codes(result, position=0):
    return {(error.field, error.code) for error in result.rows[position].validation_errors}


def test_valid_rows_optional_nulls_and_no_account_filtering():
    data = frame(row(signature=None), row(verification_line_id=2, account="7699"))
    result = validate(data)
    assert [r.validation_status for r in result.rows] == ["VALID", "VALID"]
    assert all(r.validation_errors == () for r in result.rows)
    assert result.schema_errors == ()


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
@pytest.mark.parametrize("value", [None, pd.NA, pd.NaT, float("nan"), "", " \t"])
def test_missing_required_values(field, value):
    result = validate(frame(row(**{field: value})))
    assert result.rows[0].validation_status == "INVALID"
    assert (field, "missing_value") in codes(result)


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_missing_required_column_marks_every_row(field):
    data = frame(row(), row(verification_line_id=2)).drop(columns=field)
    result = validate(data)
    assert result.schema_errors[0].field == field
    assert result.schema_errors[0].code == "missing_column"
    assert all(r.validation_status == "INVALID" for r in result.rows)
    assert all((field, "missing_column") in codes(result, i) for i in range(2))


@pytest.mark.parametrize("value", ["not a date", "2026-02-30", "03/04/2026", 45000, True, []])
def test_invalid_date(value):
    assert ("verification_date", "invalid_value") in codes(
        validate(frame(row(verification_date=value)))
    )


@pytest.mark.parametrize("value", [date(2026, 9, 3), datetime(2026, 9, 3),
                                  pd.Timestamp("2026-09-03"), "2026-09-03T12:30:00"])
def test_valid_date_representations(value):
    assert validate(frame(row(verification_date=value))).rows[0].validation_status == "VALID"


def test_explicit_date_format():
    result = validate(frame(row(verification_date="03/09/2026")), date_format="%d/%m/%Y")
    assert result.rows[0].validation_status == "VALID"


@pytest.mark.parametrize("value", ["abc", "12,50", "1_000", "=1+2", True,
                                  float("inf"), Decimal("Infinity"), 1j, [], {}])
def test_invalid_amount(value):
    assert ("amount", "invalid_value") in codes(validate(frame(row(amount=value))))


@pytest.mark.parametrize("value", [0, -12.5, "125.50", "1e3", Decimal("0.0001")])
def test_numeric_amount(value):
    assert validate(frame(row(amount=value))).rows[0].validation_status == "VALID"


@pytest.mark.parametrize("value", [1.5, "1.5", "abc", True, float("inf"), [], {}])
def test_invalid_line_id(value):
    assert ("verification_line_id", "invalid_value") in codes(
        validate(frame(row(verification_line_id=value)))
    )


@pytest.mark.parametrize("value", [0, -1, 2, 2.0, "02", Decimal("2")])
def test_integer_line_id_without_unconfirmed_range_rule(value):
    assert validate(frame(row(verification_line_id=value))).rows[0].validation_status == "VALID"


@pytest.mark.parametrize("field", ["verification_id", "account"])
@pytest.mark.parametrize("value", [3934106.5, np.float64(86.5), True, np.bool_(True),
                                   float('inf'), float('-inf'), [], {}])
def test_identifier_fields_reject_non_integral_and_unsupported_values(field, value):
    assert (field, "invalid_value") in codes(validate(frame(row(**{field: value}))))


@pytest.mark.parametrize('field', ['verification_id', 'account'])
@pytest.mark.parametrize('value', [3934106.0, 10001511.0, 86.0, 3934106, '3934106',
                                  np.int64(3934106), np.uint64(3934106),
                                  np.float64(10001511), np.float32(86), np.longdouble(86)])
def test_integral_excel_identifier_values_are_valid_without_changing_source(field, value):
    data = frame(row(**{field: value}))
    before = data.copy(deep=True)
    assert validate(data).rows[0].validation_status == 'VALID'
    pd.testing.assert_frame_equal(data, before)
    assert type(data[field].iloc[0]) is type(value)


@pytest.mark.parametrize('value', [np.int64(1), np.uint64(1), np.float64(1),
                                  np.float32(1), np.longdouble(1)])
def test_numpy_integral_line_ids_remain_valid(value):
    assert validate(frame(row(verification_line_id=value))).rows[0].validation_status == 'VALID'


@pytest.mark.parametrize('value', [np.float32(1.5), np.float64(1.5), np.bool_(True)])
def test_numpy_fractional_or_boolean_line_ids_remain_invalid(value):
    assert ('verification_line_id', 'invalid_value') in codes(validate(frame(row(verification_line_id=value))))


def test_numeric_and_text_verification_keys_share_duplicate_detection_without_merging_leading_zeros():
    data = frame(*(row(verification_id=value) for value in
                   [3934106.0, np.int64(3934106), '3934106', '03934106', '3934106.0']))
    result = validate(data)
    assert [r.validation_status for r in result.rows] == ['INVALID'] * 3 + ['VALID'] * 2
    assert all(('verification_id+verification_line_id', 'duplicate_identity') in codes(result, i)
               for i in range(3))


def test_footer_and_blank_rows_are_not_invoices_but_missing_transaction_ids_are_errors():
    data = frame(row(), {field: float('nan') for field in REQUIRED_FIELDS},
                 {'header_text': 'Summa', 'amount': 100},
                 {'verification_id': 'Totalt', 'amount': 100},
                 row(verification_id=None))
    result = validate(data)
    assert [r.validation_status for r in result.rows] == [
        'VALID', 'NOT_APPLICABLE', 'NOT_APPLICABLE', 'NOT_APPLICABLE', 'INVALID']
    assert all(not r.validation_errors and r.skipped_reason for r in result.rows[1:4])
    assert ('verification_id', 'missing_value') in codes(result, 4)


def test_float64_regression_with_4763_numeric_ids_and_two_report_rows():
    count = 4763
    data = pd.DataFrame({
        'verification_id': [float(3934106 + i) for i in range(count)] + [np.nan, np.nan],
        'verification_line_id': [1.0] * count + [np.nan, np.nan],
        'verification_date': ['2026-09-03'] * count + [None, None],
        'amount': [10.0] * count + [np.nan, 10.0 * count],
        'account': [4000.0] * count + [np.nan, np.nan],
        'header_text': [None] * (count + 1) + ['Summa'],
    })
    before = data.copy(deep=True)
    assert data.verification_id.dtype == np.dtype('float64')
    result = validate(data)
    assert sum(r.validation_status == 'VALID' for r in result.rows) == count
    assert sum(r.validation_status == 'NOT_APPLICABLE' for r in result.rows) == 2
    assert not any(r.validation_errors for r in result.rows)
    pd.testing.assert_frame_equal(data, before)


def test_all_duplicate_identities_marked_even_with_other_errors():
    data = frame(row(), row(verification_line_id="01", amount="bad"),
                 row(verification_line_id=1.0), row(verification_line_id=2),
                 row(verification_id="other"))
    result = validate(data)
    assert [r.validation_status for r in result.rows] == ["INVALID"] * 3 + ["VALID"] * 2
    for i in range(3):
        assert ("verification_id+verification_line_id", "duplicate_identity") in codes(result, i)
    assert ("amount", "invalid_value") in codes(result, 1)


def test_identifier_text_is_not_normalized():
    result = validate(frame(row(), row(verification_id="123"), row(verification_id="00123 ")))
    assert all(r.validation_status == "VALID" for r in result.rows)


def test_invalid_rows_do_not_stop_remaining_rows_and_input_is_unchanged():
    data = frame(row(verification_id=[], verification_date={}, amount=[1]),
                 row(verification_line_id=2), row(verification_id=None, amount="bad"))
    data.index = ["same", "same", "last"]
    data["validation_status"] = "original business column"
    data.attrs["source"] = "synthetic"
    before = deepcopy(data)
    result = validate(data)
    pd.testing.assert_frame_equal(data, before)
    assert data.attrs == before.attrs
    assert [r.row_position for r in result.rows] == [0, 1, 2]
    assert [r.validation_status for r in result.rows] == ["INVALID", "VALID", "INVALID"]
    assert len(result.rows[0].validation_errors) == 3


def test_invalid_identities_are_not_reported_as_duplicates():
    result = validate(frame(row(verification_id=None), row(verification_id=None)))
    assert all(e.code != "duplicate_identity" for r in result.rows for e in r.validation_errors)


def test_duplicate_required_column_is_reported_without_crashing():
    data = frame(row())
    data = pd.concat([data, data[["amount"]]], axis=1)
    result = validate(data)
    assert ("amount", "duplicate_column") in codes(result)
    assert result.schema_errors[0].code == "duplicate_column"


def test_empty_input_and_missing_schema():
    result = validate(pd.DataFrame(columns=REQUIRED_FIELDS))
    assert result.rows == ()
    assert result.schema_errors == ()
    missing = validate(pd.DataFrame())
    assert missing.rows == ()
    assert len(missing.schema_errors) == 5


def test_rows_with_no_columns_are_all_reported():
    result = validate(pd.DataFrame(index=[0, 1]))
    assert len(result.rows) == 2
    assert all(len(r.validation_errors) == 5 for r in result.rows)


def test_non_dataframe_has_clear_error():
    with pytest.raises(TypeError, match="pandas DataFrame"):
        validate([])
