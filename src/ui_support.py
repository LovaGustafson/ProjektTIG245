"""Presentation helpers and temporary upload handling; no analysis rules."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pyarrow as pa

from src.output.report_generator import review_workbooks
from src.presentation import context_fields, validation_records
from src.pipeline import PipelineResult, run_pipeline


@dataclass
class UploadResult:
    result: PipelineResult
    downloads: dict[str, bytes]
    source_content: bytes
    excluded_types: tuple[str, ...] | None


def analyze_upload(content: bytes, *, excluded_verification_types=None) -> UploadResult:
    """Analyze a private working copy; collect downloads before deleting files.

    Upload names are never used as paths. PipelineResult.report_paths refer to
    deleted temporary files after return; use downloads for all UI downloads.
    """
    with TemporaryDirectory(prefix='invoice-review-') as directory:
        root = Path(directory)
        source = root / 'upload.xlsx'
        source.write_bytes(content)
        result = run_pipeline(source, output_dir=root / 'reports',
                              excluded_verification_types=excluded_verification_types)
        downloads = {path.name: path.read_bytes() for path in result.report_paths.values()}
    downloads.update(review_workbooks(result.original_data, result.filtering))
    return UploadResult(result, downloads, bytes(content),
                        None if excluded_verification_types is None else tuple(sorted(excluded_verification_types)))


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
