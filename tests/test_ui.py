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
    assert app.title[0].value == 'Fakturagranskning'
    assert app.file_uploader[0].label == 'Välj Excel-fil'
    assert not app.metric
    assert not app.get('download_button')


def test_streamlit_result_screen():
    from streamlit.testing.v1 import AppTest
    review = ui_support.analyze_upload(workbook())
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'))
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    assert [m.value for m in app.metric] == ['1', '0', '1', '4']
    assert [m.label for m in app.metric] == ['Analyserade', 'Flaggade', 'Valideringsfel', 'Ej kontrollerade']
    assert [tab.label for tab in app.tabs] == ['Översikt', 'Avvikelser', 'Valideringsfel', 'Rapporter']
    assert len(app.get('download_button')) == 3
    assert app.warning
    assert 'inte att alla kontroller är godkända' in app.warning[0].value
    controls = app.tabs[0].dataframe[0].value
    assert controls['Status'].tolist() == ['Ej kontrollerad'] * 4
    assert len(app.tabs[2].dataframe[0].value) == 1
    assert [button.label for button in app.download_button] == [
        'Hämta rensat underlag', 'Hämta avvikelserapport', 'Hämta manuellt stickprov']


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


def test_validation_tab_separates_schema_and_row_errors_without_mutating_evidence():
    from streamlit.testing.v1 import AppTest
    buffer = BytesIO()
    # Missing Konto is a file error; the invalid amount is a separate row error.
    pd.DataFrame({'Vernr': ['001'], 'Vrad': [1], 'Verdatum': ['2026-09-03'],
                  'Utfall': ['bad']}).to_excel(buffer, index=False)
    review = ui_support.analyze_upload(buffer.getvalue())
    before = ui_support.validation_table(review.result).copy(deep=True)
    downloads = dict(review.downloads)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'))
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    schema, rows = [table.value for table in app.tabs[2].dataframe]
    assert schema['code'].tolist() == ['missing_column']
    assert schema['field'].tolist() == ['Konto']
    assert 'verification_id' not in schema.columns
    assert rows['code'].tolist() == ['invalid_value']
    assert rows['verification_id'].tolist() == ['001']
    assert rows['verification_line_id'].tolist() == [1]
    assert rows['row_position'].tolist() == [0]
    pd.testing.assert_frame_equal(ui_support.validation_table(review.result), before)
    assert review.downloads == downloads


def test_flagged_selection_retains_swedish_reasons_rows_and_error_status():
    from dataclasses import replace
    from streamlit.testing.v1 import AppTest
    buffer = BytesIO()
    pd.DataFrame({'Vernr': ['001', '002'], 'Vrad': [1, 1],
                  'Verdatum': ['2026-09-03'] * 2, 'Utfall': [10, 20],
                  'Konto': ['4000'] * 2}).to_excel(buffer, index=False)
    review = ui_support.analyze_upload(buffer.getvalue())
    for i, original in enumerate(review.result.detection_results):
        review.result.detection_results[i] = replace(original, checks=(
            CheckResult(original.verification_id, 'synthetic', CheckStatus.FLAGGED,
                        f'Orsak för {original.verification_id}: <b>oförändrad text</b>'),
            CheckResult(original.verification_id, 'synthetic', CheckStatus.ERROR,
                        'Tekniskt fel i kontrollen.'),
        ))
    before = ui_support.flagged_table(review.result).copy(deep=True)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'))
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    assert app.tabs[1].dataframe[0].value['status'].tolist() == ['Flaggad'] * 2
    assert app.tabs[0].dataframe[0].value['Status'].tolist() == ['Flaggad', 'Tekniskt fel'] * 2
    assert any('tekniska fel' in warning.value for warning in app.warning)
    app.selectbox[0].select(1).run()
    assert not app.exception
    assert 'Orsak för 002: <b>oförändrad text</b>' in [item.value for item in app.text]
    assert 'Orsak för 001: <b>oförändrad text</b>' not in [item.value for item in app.text]
    assert app.tabs[1].dataframe[1].value['verification_id'].tolist() == ['002']
    pd.testing.assert_frame_equal(ui_support.flagged_table(review.result), before)
