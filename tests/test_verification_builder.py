"""Synthetic tests for grouping only; no invoice files or business rules."""

from datetime import date
from decimal import Decimal

import pandas as pd

from src.models.verification import Verification
from src.verification.verification_builder import build_verifications


def invoice_row(verification_id="00100", verification_line_id=1, **values):
    return {
        "verification_id": verification_id,
        "verification_line_id": verification_line_id,
        "verification_date": date(2026, 9, 3),
        "amount": Decimal("125.50"),
        "account": "7698",
        "image_reference": None,
        "signature": "synthetic-signature",
        "attestation": None,
        "line_text": "Synthetic row",
        **values,
    }


def test_one_verification_with_one_row():
    data = pd.DataFrame([invoice_row()])
    result = build_verifications(data)
    assert len(result) == 1
    assert isinstance(result[0], Verification)
    assert result[0].verification_id == "00100"
    pd.testing.assert_frame_equal(result[0].rows, data)


def test_one_verification_with_multiple_rows_retains_line_order():
    data = pd.DataFrame([invoice_row(verification_line_id=i) for i in [3, 1, 2]])
    result = build_verifications(data)
    assert len(result) == 1
    assert result[0].rows["verification_line_id"].tolist() == [3, 1, 2]
    pd.testing.assert_frame_equal(result[0].rows, data)


def test_multiple_interleaved_verifications_group_only_by_verification_id():
    data = pd.DataFrame([
        invoice_row("B", 1), invoice_row("A", 1), invoice_row("B", 2),
        invoice_row("C", 1), invoice_row("A", 2),
    ], index=[8, 2, 8, 4, 2])
    result = build_verifications(data)
    assert [v.verification_id for v in result] == ["B", "A", "C"]
    for verification, positions in zip(result, [[0, 2], [1, 4], [3]]):
        pd.testing.assert_frame_equal(verification.rows, data.iloc[positions])
    assert sum(len(v.rows) for v in result) == len(data)


def test_input_and_dtypes_preserved_and_output_edits_are_independent():
    data = pd.DataFrame([invoice_row(), invoice_row("00200")])
    data["verification_line_id"] = data["verification_line_id"].astype("Int64")
    data.index.name = "source_row"
    data.attrs["source"] = "synthetic"
    before = data.copy(deep=True)
    result = build_verifications(data)
    pd.testing.assert_frame_equal(data, before)
    pd.testing.assert_frame_equal(result[0].rows, data.iloc[[0]])
    result[0].rows.iloc[0, result[0].rows.columns.get_loc("amount")] = Decimal("999")
    result[0].rows.drop(columns="signature", inplace=True)
    pd.testing.assert_frame_equal(data, before)
    assert data.attrs == before.attrs
    pd.testing.assert_frame_equal(result[1].rows, data.iloc[[1]])
    data.loc[1, "account"] = "changed input"
    assert result[1].rows.iloc[0]["account"] == "7698"


def test_nested_object_cells_are_independent():
    shared = {"notes": ["synthetic"]}
    data = pd.DataFrame([invoice_row(extra=shared), invoice_row("00200", extra=shared)])
    result = build_verifications(data)
    result[0].rows.iloc[0]["extra"]["notes"].append("output edit")
    assert data.iloc[0]["extra"] == {"notes": ["synthetic"]}
    assert result[1].rows.iloc[0]["extra"] == {"notes": ["synthetic"]}


def test_duplicate_lines_invalid_values_and_optional_columns_are_not_processed():
    data = pd.DataFrame([
        invoice_row(amount="not numeric", verification_date="not a date", extra="keep"),
        invoice_row(account="7699", extra="also keep"),
    ])
    result = build_verifications(data)
    assert result[0].rows["verification_line_id"].tolist() == [1, 1]
    pd.testing.assert_frame_equal(result[0].rows, data)


def test_ids_are_not_normalized():
    ids = ["00100", "100", "A", "a", "A "]
    data = pd.DataFrame([invoice_row(value) for value in ids])
    assert [v.verification_id for v in build_verifications(data)] == ids


def test_empty_dataframe_returns_no_verifications():
    data = pd.DataFrame(columns=invoice_row().keys())
    assert build_verifications(data) == []


def test_unused_categorical_ids_do_not_create_verifications():
    data = pd.DataFrame([invoice_row("B"), invoice_row("A")])
    data["verification_id"] = pd.Categorical(
        data["verification_id"], categories=["A", "B", "unused"]
    )
    result = build_verifications(data)
    assert [v.verification_id for v in result] == ["B", "A"]
    pd.testing.assert_frame_equal(result[0].rows, data.iloc[[0]])


def test_null_keys_do_not_silently_drop_rows():
    data = pd.DataFrame([invoice_row(None, 1), invoice_row("A", 2), invoice_row(None, 3)])
    result = build_verifications(data)
    assert len(result) == 2
    assert pd.isna(result[0].verification_id)
    pd.testing.assert_frame_equal(result[0].rows, data.iloc[[0, 2]])
    pd.testing.assert_frame_equal(result[1].rows, data.iloc[[1]])
