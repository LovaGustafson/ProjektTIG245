"""Excel report round trips with synthetic data only."""

from datetime import datetime
from decimal import Decimal
import errno

import pandas as pd
import pytest
from openpyxl import load_workbook
from openpyxl.utils.exceptions import IllegalCharacterError

from src.ingestion.excel_reader import read_excel
from src.models.result import CheckResult, CheckStatus
from src.models.verification import Verification
from src.output.report_generator import CHECK_COLUMNS, generate_reports


@pytest.fixture
def rows():
    return pd.DataFrame({
        "verification_id": ["001", "001", "002"],
        "verification_line_id": [1, 2, 1],
        "verification_date": [datetime(2026, 9, 3)] * 3,
        "amount": [125.5, -25.5, "invalid amount"],
        "account": ["7698", "0010", None],
        "line_text": ["=1+2", "#N/A", "NA"],
        "reason": ["original text", None, "extra column"],
    }, dtype=object)


def export(rows, directory):
    return generate_reports(
        rows,
        flagged_verifications=[Verification("001", rows.iloc[:2])],
        flagged_checks=[
            CheckResult("001", "synthetic_a", CheckStatus.FLAGGED, "First reason"),
            CheckResult("001", "synthetic_b", CheckStatus.FLAGGED, "Second reason",
                        verification_line_id=2, field="amount", row_position=1),
            CheckResult("001", "synthetic_a", CheckStatus.FLAGGED, "First reason"),
        ],
        manual_sample=[Verification("002", rows.iloc[2:])],
        output_dir=directory,
    )


def test_all_reports_read_back_with_complete_rows_and_multiple_reasons(tmp_path, rows):
    paths = export(rows, tmp_path / "reports")
    assert {path.name for path in paths.values()} == {
        "cleaned_data.xlsx", "flagged_invoices.xlsx", "manual_sample.xlsx", "uncertain_suppliers.xlsx"}
    for name, expected in [("cleaned_data", rows), ("flagged_invoices", rows.iloc[:2]),
                           ("manual_sample", rows.iloc[2:])]:
        actual = read_excel(paths[name], sheet_name="rows")
        pd.testing.assert_frame_equal(actual, expected.reset_index(drop=True), check_column_type=False)
    checks = read_excel(paths["flagged_invoices"], sheet_name="checks")
    assert checks.columns.tolist() == CHECK_COLUMNS
    assert checks["verification_id"].tolist() == ["001"] * 3
    assert checks["verification_line_id"].tolist() == [None, 2, None]
    assert checks["reason"].tolist() == ["First reason", "Second reason", "First reason"]
    assert checks["status"].tolist() == ["FLAGGED"] * 3
    assert checks["check_type"].tolist() == ["synthetic_a", "synthetic_b", "synthetic_a"]
    assert checks["field"].tolist() == [None, "amount", None]
    assert checks["row_position"].tolist() == [None, 1, None]


def test_source_file_and_in_memory_data_unchanged(tmp_path, rows):
    source = tmp_path / "source.xlsx"
    rows.to_excel(source, index=False)
    original_bytes = source.read_bytes()
    original_mtime = source.stat().st_mtime_ns
    before = rows.copy(deep=True)
    export(rows, tmp_path / "reports")
    pd.testing.assert_frame_equal(rows, before)
    assert source.read_bytes() == original_bytes
    assert source.stat().st_mtime_ns == original_mtime


@pytest.mark.parametrize("filename", ["cleaned_data.xlsx", "flagged_invoices.xlsx", "manual_sample.xlsx"])
def test_existing_files_never_overwritten_and_no_partial_reports(tmp_path, rows, filename):
    source = tmp_path / filename
    rows.to_excel(source, index=False)
    before = source.read_bytes()
    with pytest.raises(FileExistsError):
        export(rows, tmp_path)
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source]


def test_symlink_cannot_overwrite_source(tmp_path, rows):
    source = tmp_path / "source.xlsx"
    rows.to_excel(source, index=False)
    before = source.read_bytes()
    directory = tmp_path / "reports"
    directory.mkdir()
    try:
        (directory / "cleaned_data.xlsx").symlink_to(source)
    except NotImplementedError:
        pytest.skip("Symlink creation is not supported on this platform")
    except OSError as exc:
        if (getattr(exc, "winerror", None) == 1314
                or exc.errno in (errno.EPERM, errno.EACCES, errno.ENOSYS, errno.ENOTSUP)):
            pytest.skip(f"Symlink creation permission/support unavailable: {exc}")
        raise
    with pytest.raises(FileExistsError):
        export(rows, directory)
    assert source.read_bytes() == before


@pytest.mark.parametrize("with_schema", [False, True])
def test_empty_outputs_are_readable(tmp_path, rows, with_schema):
    cleaned = rows.iloc[:0] if with_schema else pd.DataFrame()
    paths = generate_reports(cleaned, flagged_verifications=[], flagged_checks=[],
                             manual_sample=[], output_dir=tmp_path)
    for name, path in paths.items():
        result = read_excel(path, sheet_name="rows")
        assert result.empty
        expected = cleaned.columns.tolist() if name in ('cleaned_data', 'uncertain_suppliers') else ["verification_id", "verification_line_id"]
        if name == 'uncertain_suppliers':
            expected += ['source_row_position', 'header_text_normalized', 'supplier_match_status',
                         'supplier_check_status', 'supplier_match_reason']
        assert result.columns.tolist() == expected
    checks = read_excel(paths["flagged_invoices"], sheet_name="checks")
    assert checks.empty
    assert checks.columns.tolist() == CHECK_COLUMNS


def test_strings_are_literal_and_decimal_precision_is_retained(tmp_path, rows):
    rows.loc[0, "amount"] = Decimal("12345678901234567890.12345")
    paths = export(rows, tmp_path)
    workbook = load_workbook(paths["cleaned_data"], data_only=False)
    try:
        assert workbook["rows"]["D2"].value == "12345678901234567890.12345"
        assert workbook["rows"]["F2"].value == "=1+2"
        assert workbook["rows"]["F2"].data_type == "s"
        assert workbook["rows"]["F3"].value == "#N/A"
        assert workbook["rows"]["F3"].data_type == "s"
    finally:
        workbook.close()


def test_serialization_error_does_not_create_partial_reports(tmp_path, rows):
    rows.loc[0, "line_text"] = "illegal\x00text"
    with pytest.raises(IllegalCharacterError):
        export(rows, tmp_path / "reports")
    assert not (tmp_path / "reports").exists()


def test_long_text_is_not_silently_truncated(tmp_path, rows):
    rows.loc[0, "line_text"] = "x" * 32768
    with pytest.raises(ValueError, match="cell limit"):
        export(rows, tmp_path / "reports")
    assert not (tmp_path / "reports").exists()
