"""Presentation helpers and temporary upload handling; no analysis rules."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.presentation import context_fields, validation_records
from src.pipeline import PipelineResult, run_pipeline


@dataclass
class UploadResult:
    result: PipelineResult
    downloads: dict[str, bytes]


def analyze_upload(content: bytes) -> UploadResult:
    """Analyze a private working copy; collect downloads before deleting files.

    Upload names are never used as paths. PipelineResult.report_paths refer to
    deleted temporary files after return; use downloads for all UI downloads.
    """
    with TemporaryDirectory(prefix='invoice-review-') as directory:
        root = Path(directory)
        source = root / 'upload.xlsx'
        source.write_bytes(content)
        result = run_pipeline(source, output_dir=root / 'reports')
        downloads = {path.name: path.read_bytes() for path in result.report_paths.values()}
    return UploadResult(result, downloads)


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
