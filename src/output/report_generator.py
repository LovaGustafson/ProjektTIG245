"""Write already-prepared review results to new Excel workbooks."""

from collections.abc import Iterable, Mapping
from contextlib import ExitStack
from dataclasses import asdict, fields
from decimal import Decimal
from io import BytesIO
from itertools import chain
from pathlib import Path

import pandas as pd

from src.presentation import context_fields, check_message
from src.models.result import CheckResult
from src.models.verification import Verification


ROW_COLUMNS = ["verification_id", "verification_line_id"]
CHECK_COLUMNS = [field.name for field in fields(CheckResult)] + ["verification_date", "header_text", "code", "message"]


def _verification_rows(verifications: Iterable[Verification]) -> pd.DataFrame:
    frames = [verification.rows for verification in verifications]
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame(columns=ROW_COLUMNS)


def _workbook(sheets: Mapping[str, pd.DataFrame]) -> bytes:
    prepared = {}
    for name, data in sheets.items():
        # Keep decimal precision instead of pandas' float conversion.
        export_data = data.map(lambda value: str(value) if isinstance(value, Decimal) else value)
        for value in chain(export_data.columns, export_data.to_numpy().flat):
            if isinstance(value, str) and len(value) > 32767:
                raise ValueError(f"Worksheet {name}: text exceeds Excel's 32767-character cell limit")
        prepared[name] = export_data
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, export_data in prepared.items():
            export_data.to_excel(writer, sheet_name=name, index=False)
            # Source strings are evidence, not executable spreadsheet formulas.
            # Also retain strings such as '#N/A' as literal text on read-back.
            for row in writer.sheets[name].iter_rows():
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.data_type = "s"
    return buffer.getvalue()


def generate_reports(
    cleaned_data: pd.DataFrame, *,
    flagged_verifications: Iterable[Verification],
    flagged_checks: Iterable[CheckResult],
    manual_sample: Iterable[Verification],
    output_dir: str | Path,
    summary: Mapping[str, int] | None = None,
) -> dict[str, Path]:
    """Export three new workbooks and return their paths keyed by report name.

    Inputs must already be cleaned, flagged and sampled by their respective
    modules. Every supplied check is exported once, in order, with no status
    filtering or deduplication. The caller supplies complete verifications for
    those checks. This function does not run detection or choose a sample.

    cleaned_data.xlsx and manual_sample.xlsx contain a 'rows' worksheet.
    flagged_invoices.xlsx contains 'checks' (all CheckResult fields) and 'rows'
    (all rows of the supplied flagged verifications). Separate sheets avoid
    collisions between business columns and check metadata and retain null
    line IDs for verification-level checks. All columns and row order survive;
    pandas index labels, attrs and Excel styling are not business columns and
    are not exported. Empty outputs retain headers where a schema is supplied.

    Excel-native scalar values are supported; Decimal values are explicitly
    stored as exact text, and pandas serializes nested Python objects as text.
    Strings, including formula expressions, are
    exported literally. Excel cannot preserve arbitrary Python types/dtypes.

    Workbooks are serialized before any destination is created. Exclusive
    creation refuses every existing path, including symlinks, so source files
    and prior reports cannot be overwritten. On failure, only files created by
    this call are removed. Filesystem and serialization errors propagate.
    """
    flagged_verifications = list(flagged_verifications)
    checks = []
    for check in flagged_checks:
        record = asdict(check)
        record["status"] = check.status.value
        context = {}
        for verification in flagged_verifications:
            if verification.verification_id == check.verification_id:
                context = context_fields(verification.rows)
                break
        record.update(verification_date=context.get('verification_date'),
                      header_text=context.get('header_text'), code=None,
                      message=check_message(check))
        checks.append(record)
    workbooks = {
        "cleaned_data": _workbook({"rows": cleaned_data}),
        "flagged_invoices": _workbook({
            "checks": pd.DataFrame(checks, columns=CHECK_COLUMNS),
            "rows": _verification_rows(flagged_verifications),
            **({"Summary": pd.DataFrame([summary])} if summary is not None else {}),
        }),
        "manual_sample": _workbook({"rows": _verification_rows(manual_sample)}),
    }
    directory = Path(output_dir)
    paths = {name: directory / f"{name}.xlsx" for name in workbooks}
    directory.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        with ExitStack() as stack:
            streams = {}
            for name, path in paths.items():
                streams[name] = stack.enter_context(path.open("xb"))
                created.append(path)
            for name, content in workbooks.items():
                streams[name].write(content)
    except BaseException:
        for path in created:
            path.unlink()
        raise
    return paths
