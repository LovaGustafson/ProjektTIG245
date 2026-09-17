"""Presentation helpers and temporary upload handling; no analysis rules."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pyarrow as pa

from src.output.report_generator import review_workbooks
from src.presentation import context_fields, validation_records, validation_message
from src.pipeline import PipelineResult, run_pipeline


@dataclass
class UploadResult:
    result: PipelineResult
    downloads: dict[str, bytes]
    source_content: bytes
    excluded_types: tuple[str, ...] | None
    registry_content: bytes | None = None
    registry_snapshot_date: object = None


def analyze_upload(content: bytes, *, excluded_verification_types=None,
                   registry_content=None, registry_snapshot_date=None) -> UploadResult:
    """Analyze a private working copy; collect downloads before deleting files.

    Upload names are never used as paths. PipelineResult.report_paths refer to
    deleted temporary files after return; use downloads for all UI downloads.
    """
    with TemporaryDirectory(prefix='invoice-review-') as directory:
        root = Path(directory)
        source = root / 'upload.xlsx'
        source.write_bytes(content)
        registry_path = None
        if registry_content is not None:
            registry_path = root / 'registry.xlsx'
            registry_path.write_bytes(registry_content)
        result = run_pipeline(source, output_dir=root / 'reports',
                              excluded_verification_types=excluded_verification_types,
                              supplier_register=registry_path,
                              registry_snapshot_date=registry_snapshot_date)
        downloads = {path.name: path.read_bytes() for path in result.report_paths.values()}
    downloads.update(review_workbooks(result.original_data, result.filtering, result.supplier_analysis))
    return UploadResult(result, downloads, bytes(content),
                        None if excluded_verification_types is None else tuple(sorted(excluded_verification_types)),
                        registry_content, registry_snapshot_date)


def flagged_table(result: PipelineResult) -> pd.DataFrame:
    rows = []
    for detection in result.detection_results:
        if not detection.flag_reasons:
            continue
        context = {}
        for verification in result.verifications:
            if verification.verification_id == detection.verification_id:
                context = context_fields(verification.rows)
                break
        rows.append(dict(verification_id=detection.verification_id, **context,
                         status=detection.status.value,
                         reasons='\n'.join(detection.flag_reasons)))
    return pd.DataFrame(rows, columns=['verification_id', 'verification_date', 'header_text',
                                       'status', 'amount', 'account', 'reasons'])


def validation_table(result: PipelineResult) -> pd.DataFrame:
    return pd.DataFrame(validation_records(result.standardized_data, result.validation),
                        columns=['scope', 'row_position', 'verification_id',
                                 'verification_line_id', 'field', 'code', 'message'])


def display_dataframe(data) -> pd.DataFrame:
    """Return an Arrow-compatible display copy, without changing source values.

    Keep supported column types. Only columns Arrow cannot represent are
    rendered as strings; missing values remain missing rather than literal text.
    This copy must never be used as analysis or export input.
    """
    display = pd.DataFrame(data).copy(deep=True)
    for position in range(len(display.columns)):
        column = display.iloc[:, position]
        try:
            pa.array(column, from_pandas=True)
        except (pa.ArrowException, TypeError, ValueError, OverflowError):
            display.isetitem(position, column.astype('string'))
    return display


REVIEW_EXPLANATION = (
    'Denna rad är kvar eftersom den inte träffar någon aktiv filterregel för konto '
    'eller verifikationstyp. Det betyder inte automatiskt att raden är felaktig '
    'eller en avvikelse. Den är kvar för fortsatt manuell kontroll.'
)


def filter_details(result, field):
    """Show evidence recorded by the filter engine, including overlapping hits."""
    matches = result.filtering.rule_details[field]
    label = 'Konto' if field == 'account' else 'Vertyp'
    counts = pd.DataFrame([(value, len(positions)) for value, positions in matches.items()],
                          columns=[label, 'Antal rader'])
    positions = sorted(position for group in matches.values() for position in group)
    return counts, result.original_data.iloc[positions].copy(deep=True)


def review_row_detail(result, selected_position):
    """Resolve a table position to its source row, never by invoice identity."""
    positions = [i for i, reason in enumerate(result.filtering.reasons) if not reason]
    source_position = positions[selected_position]
    row = result.original_data.iloc[source_position]
    fields = pd.DataFrame({'Fält': list(row.index), 'Källvärde': list(row.values)})
    warnings = [validation_message(error)
                for error in result.validation.rows[source_position].validation_errors]
    return fields, warnings
