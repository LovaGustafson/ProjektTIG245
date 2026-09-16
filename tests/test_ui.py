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
    assert set(review.downloads) == {'cleaned_data.xlsx', 'flagged_invoices.xlsx', 'manual_sample.xlsx',
                                     'granskning.xlsx', 'bortfiltrerade.xlsx', 'samlad_kontrollfil.xlsx'}
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
    assert [m.value for m in app.metric] == ['1', '1', '0', '0', '0', '1', '0', '1', '4']
    assert [m.label for m in app.metric][5:] == ['Analyserade', 'Flaggade', 'Valideringsfel', 'Ej kontrollerade']
    assert [tab.label for tab in app.tabs] == ['Granskning', 'Bortfiltrerade', 'Kontroller', 'Export']
    assert len(app.get('download_button')) == 5
    assert app.warning
    assert 'inte att alla kontroller är godkända' in app.warning[0].value
    controls = app.tabs[2].dataframe[0].value
    assert controls['Status'].tolist() == ['Ej kontrollerad'] * 4
    assert len(app.tabs[0].dataframe[-1].value) == 1
    assert [button.label for button in app.download_button] == [
        'Kvar för granskning', 'Bortfiltrerade', 'Samlad kontrollfil', 'Hämta avvikelserapport', 'Hämta manuellt stickprov']


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
    assert app.metric[6].value == '1'
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
    schema, rows = [table.value for table in app.tabs[0].dataframe][1:]
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
    assert app.tabs[0].dataframe[1].value['status'].tolist() == ['Flaggad'] * 2
    assert app.tabs[2].dataframe[0].value['Status'].tolist() == ['Flaggad', 'Tekniskt fel'] * 2
    assert any('tekniska fel' in warning.value for warning in app.warning)
    app.selectbox[0].select(1).run()
    assert not app.exception
    assert 'Orsak för 002: <b>oförändrad text</b>' in [item.value for item in app.text]
    assert 'Orsak för 001: <b>oförändrad text</b>' not in [item.value for item in app.text]
    assert app.tabs[0].dataframe[2].value['verification_id'].tolist() == ['002']
    pd.testing.assert_frame_equal(ui_support.flagged_table(review.result), before)


@pytest.mark.parametrize('values', [
    [12.5, '2026-09-08 08.27.22 annsv203', None],
    [1, '2', pd.NA],
    [pd.Timestamp('2026-09-08'), 'okänt datum', None],
    [True, 'okänd status', None],
])
def test_display_copy_serializes_mixed_columns_without_changing_source(values):
    import pyarrow as pa
    source = pd.DataFrame({'mixed': pd.Series(values, dtype=object),
                           'numeric': [1.5, 2.5, 3.5]})
    before = source.copy(deep=True)
    display = ui_support.display_dataframe(source)
    pa.Table.from_pandas(display, preserve_index=False)
    assert display['mixed'].iloc[0] == str(values[0])
    assert display['mixed'].iloc[1] == str(values[1])
    assert pd.isna(display['mixed'].iloc[2])
    pd.testing.assert_series_equal(display['numeric'], source['numeric'])
    pd.testing.assert_frame_equal(source, before)


def test_mixed_amount_all_ui_tables_validation_and_export(tmp_path, caplog):
    from dataclasses import replace
    import pyarrow as pa
    from streamlit.testing.v1 import AppTest
    text = '2026-09-08 08.27.22 annsv203'
    path = tmp_path / 'mixed.xlsx'
    pd.DataFrame({'Vernr': ['001', '002', '003', '004'], 'Vrad': [1] * 4,
                  'Verdatum': ['2026-09-08'] * 4, 'Utfall': [12.5, text, 20, text],
                  'Konto': ['4000', '4000', '7698', '7699'], 'Vertyp': ['X'] * 4}).to_excel(path, index=False)
    content, mtime = path.read_bytes(), path.stat().st_mtime_ns
    review = ui_support.analyze_upload(content)
    original = review.result.original_data.copy(deep=True)
    standardized = review.result.standardized_data.copy(deep=True)
    downloads = dict(review.downloads)
    # Exercise the existing flagged summary and detail views as well.
    for i, result in enumerate(review.result.detection_results):
        review.result.detection_results[i] = replace(result, checks=(
            CheckResult(result.verification_id, 'synthetic', CheckStatus.FLAGGED, 'Testorsak'),))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'))
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    for table in app.dataframe:
        pa.Table.from_pandas(table.value, preserve_index=False)
    assert app.tabs[0].dataframe[0].value['Utfall'].tolist() == ['12.5', text]
    assert app.tabs[1].dataframe[0].value['Utfall'].iloc[1] == text
    app.selectbox[0].select(1).run()
    assert not app.exception
    assert not any('Serialization of dataframe to Arrow table was unsuccessful' in record.message
                   for record in caplog.records)
    errors = ui_support.validation_table(review.result)
    assert errors['field'].tolist() == ['amount', 'amount']
    assert errors['code'].tolist() == ['invalid_value', 'invalid_value']
    for filename, sheet in [('granskning.xlsx', 'Granskning'),
                            ('bortfiltrerade.xlsx', 'Bortfiltrerade')]:
        exported = pd.read_excel(BytesIO(review.downloads[filename]), sheet_name=sheet)
        assert isinstance(exported['Utfall'].iloc[0], (int, float))
        assert exported['Utfall'].iloc[1] == text
    pd.testing.assert_frame_equal(review.result.original_data, original)
    pd.testing.assert_frame_equal(review.result.standardized_data, standardized)
    assert review.downloads == downloads
    assert path.read_bytes() == content
    assert path.stat().st_mtime_ns == mtime
