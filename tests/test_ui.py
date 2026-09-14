from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src import ui_support
from src.models.result import CheckResult, CheckStatus


def workbook():
    buffer = BytesIO()
    pd.DataFrame({'Vernr': ['001'], 'Vrad': [1], 'Verdatum': ['2026-09-03'],
                  'Utfall': ['bad'], 'Konto': ['4000']}).to_excel(buffer, index=False)
    return buffer.getvalue()


def test_upload_round_trip_cleanup_and_summaries():
    content = workbook()
    before = bytes(content)
    review = ui_support.analyze_upload(content)
    assert content == before
    assert len(review.result.detection_results) == 1
    assert ui_support.flagged_table(review.result).empty
    assert len(ui_support.validation_table(review.result)) == 1
    assert set(review.downloads) == {'cleaned_data.xlsx', 'flagged_invoices.xlsx', 'manual_sample.xlsx'}
    for filename, data in review.downloads.items():
        assert pd.ExcelFile(BytesIO(data)).sheet_names
    assert all(not path.parent.parent.exists() for path in review.result.report_paths.values())


def test_failure_cleans_up_working_copy():
    paths = []
    def fail(path, **kwargs):
        paths.append(path)
        assert path.read_bytes() == b'bad upload'
        raise ValueError('synthetic failure')
    with patch.object(ui_support, 'run_pipeline', side_effect=fail):
        with pytest.raises(ValueError):
            ui_support.analyze_upload(b'bad upload')
    assert not paths[0].parent.exists()


def test_multiple_reasons_count_as_one_flagged_verification():
    from dataclasses import replace
    review = ui_support.analyze_upload(workbook())
    original = review.result.detection_results[0]
    review.result.detection_results[0] = replace(original, checks=tuple(
        CheckResult('001', 'synthetic', CheckStatus.FLAGGED, reason) for reason in ['First', 'Second']))
    table = ui_support.flagged_table(review.result)
    assert len(table) == 1
    assert table.iloc[0]['reasons'] == 'First\nSecond'


def test_streamlit_initial_screen():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py')).run()
    assert not app.exception
    assert app.button[0].disabled


def test_streamlit_result_screen():
    from streamlit.testing.v1 import AppTest
    review = ui_support.analyze_upload(workbook())
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'))
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    assert [m.value for m in app.metric] == ['1', '0', '1', '4']
    assert len(app.get('download_button')) == 3
    assert app.warning


def test_flagged_selection_shows_all_reasons():
    from dataclasses import replace
    from streamlit.testing.v1 import AppTest
    review = ui_support.analyze_upload(workbook())
    original = review.result.detection_results[0]
    review.result.detection_results[0] = replace(original, checks=tuple(
        CheckResult('001', 'synthetic', CheckStatus.FLAGGED, reason) for reason in ['First', 'Second']))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'))
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    assert app.metric[1].value == '1'
    assert app.selectbox[0].options == ['001']
    assert 'First' in [item.value for item in app.text]
    assert 'Second' in [item.value for item in app.text]
