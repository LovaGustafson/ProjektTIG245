"""Presentation helpers and temporary upload handling; no analysis rules."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

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
    return pd.DataFrame([
        {'verification_id': r.verification_id, 'status': r.status.value,
         'reasons': '\n'.join(r.flag_reasons)}
        for r in result.detection_results if r.flag_reasons
    ], columns=['verification_id', 'status', 'reasons'])


def validation_table(result: PipelineResult) -> pd.DataFrame:
    # Schema errors also occur on each row; present them once at schema scope.
    schema = result.validation.schema_errors
    records = [{'scope': 'schema', 'row_position': None, 'field': e.field,
                'code': e.code, 'message': e.message} for e in schema]
    records += [{'scope': 'row', 'row_position': row.row_position, 'field': e.field,
                 'code': e.code, 'message': e.message}
                for row in result.validation.rows for e in row.validation_errors if e not in schema]
    return pd.DataFrame(records, columns=['scope', 'row_position', 'field', 'code', 'message'])
