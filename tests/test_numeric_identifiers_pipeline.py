"""Excel numeric identities, report rows and unchanged evidence end to end."""
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import pipeline
from src.ingestion.excel_reader import read_excel
from src.ui_support import analyze_upload, validation_table


def source(tmp_path):
    path = tmp_path / 'numeric-identifiers.xlsx'
    pd.DataFrame({
        'Vernr': [3934106.0, 3934106.0, 10001511.0, 86.0, 3934106.5, None, None, None],
        'Vrad': [1.0, 2.0, 1.0, 1.0, 1.0, 1.0, None, None],
        'Verdatum': ['2026-09-03'] * 6 + [None, None],
        'Konto': [4000.0] * 6 + [None, None],
        'Vertyp': ['X'] * 6 + [None, None],
        'Utfall': [10.0] * 6 + [None, 60.0],
        'Huvudtext': [None] * 7 + ['Summa'],
    }).to_excel(path, index=False)
    return path


@pytest.mark.parametrize('pandas_inferred_types', [False, True])
def test_numeric_identities_reach_detection_without_mutating_excel_or_dataframes(
        tmp_path, monkeypatch, pandas_inferred_types):
    path = source(tmp_path)
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    if pandas_inferred_types:
        monkeypatch.setattr(pipeline, 'read_excel', pd.read_excel)
    raw = pipeline.read_excel(path)
    if pandas_inferred_types:
        assert str(raw['Vernr'].dtype) == 'float64'
        assert str(raw['Vrad'].dtype) == 'float64'
        assert str(raw['Konto'].dtype) == 'float64'
    result = pipeline.run_pipeline(path, output_dir=tmp_path / 'out')
    assert [row.validation_status for row in result.validation.rows] == [
        'VALID', 'VALID', 'VALID', 'VALID', 'INVALID', 'INVALID',
        'NOT_APPLICABLE', 'NOT_APPLICABLE']
    assert [v.verification_id for v in result.verifications] == ['3934106', '10001511', '86']
    assert [r.verification_id for r in result.detection_results] == ['3934106', '10001511', '86']
    assert result.verifications[0].rows.index.tolist() == [0, 1]
    assert result.ungrouped_data.index.tolist() == [4, 5]
    assert result.filtering.excluded_data.index.tolist() == [6, 7]
    assert len(result.filtering.cleaned_data) == 6
    pd.testing.assert_frame_equal(result.original_data, raw)
    pd.testing.assert_series_equal(result.standardized_data['verification_id'], raw['Vernr'], check_names=False)
    pd.testing.assert_frame_equal(result.verifications[0].rows, result.standardized_data.iloc[[0, 1]])
    errors = validation_table(result)
    assert errors['row_position'].tolist() == [4, 5]
    assert errors['code'].tolist() == ['invalid_value', 'missing_value']
    assert errors['field'].tolist() == ['verification_id'] * 2
    exported = read_excel(result.report_paths['cleaned_data'])
    assert exported['verification_id'].iloc[0] == 3934106
    assert not isinstance(exported['verification_id'].iloc[0], str)
    assert exported['verification_id'].iloc[4] == 3934106.5
    assert path.read_bytes() == before and path.stat().st_mtime_ns == mtime


def test_streamlit_and_downloads_report_only_real_identifier_errors(tmp_path):
    path = source(tmp_path)
    review = analyze_upload(path.read_bytes())
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'))
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    assert next(metric for metric in app.metric if metric.label == 'Valideringsfel').value == '2'
    assert next(metric for metric in app.metric if metric.label == 'Analyserade').value == '3'
    exported = pd.read_excel(BytesIO(review.downloads['granskning.xlsx']))
    assert exported['Vernr'].iloc[0] == 3934106.0
    assert exported['Vernr'].iloc[4] == 3934106.5
    assert len(exported) == 6
