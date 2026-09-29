"""Numbered booking markers are hidden only on customer-facing copies."""
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.presentation import context_fields
from src.supplier_matching.extraction import FINAL_BOOKING
from src.ui_support import analyze_upload, display_dataframe, review_row_detail


def workbook(data):
    buffer = BytesIO()
    data.to_excel(buffer, index=False)
    return buffer.getvalue()


HEADERS = ['Apoteket AB Slutk 12345', 'Apoteket AB Slutk12345',
           'Slutkund AB', 'Apoteket AB Slutk123abc', 'Apoteket AB Prelb 123',
           'Apoteket AB Slutk']
DISPLAY = ['Apoteket AB', 'Apoteket AB', *HEADERS[2:]]


@pytest.fixture(params=['available', 'disabled', 'unreadable'])
def review(request):
    data = pd.DataFrame({
        'Vernr': [str(i) for i in range(1, 24)] + [None],
        'Vrad': [1] * 24, 'Verdatum': ['2026-06-15'] * 24,
        'Utfall': [10] * 24, 'Konto': ['4000'] * 22 + ['7698', '4000'],
        'Vertyp': ['X'] * 24,
        'Huvudtext': HEADERS + ['Apoteket AB Slutk 987'] * 18,
    })
    registry = workbook(pd.DataFrame({'Leverantör': ['Apoteket AB'],
                                      'Organisationsnummer': ['123']}))
    content = workbook(data)
    upload = analyze_upload(content, registry_mode='disabled' if request.param == 'disabled' else 'uploaded',
                            registry_content=registry if request.param == 'available' else
                            b'unreadable' if request.param == 'unreadable' else None)
    assert upload.source_content == content
    return upload


def test_all_workbooks_hide_markers_and_preserve_internal_evidence(review):
    result = review.result
    assert result.original_data.Huvudtext.tolist() == HEADERS + ['Apoteket AB Slutk 987'] * 18
    assert result.standardized_data.header_text.tolist() == result.original_data.Huvudtext.tolist()
    assert result.filtering.cleaned_data.header_text.iloc[0] == HEADERS[0]
    assert result.filtering.excluded_data.header_text.iloc[0] == 'Apoteket AB Slutk 987'
    assert result.ungrouped_data.header_text.tolist() == ['Apoteket AB Slutk 987']
    assert result.manual_sample[0].verification_id == '20'
    assert result.manual_sample[0].rows.header_text.tolist() == ['Apoteket AB Slutk 987']
    assert result.verifications[0].rows.header_text.tolist() == [HEADERS[0]]

    for content in review.downloads.values():
        for table in pd.read_excel(BytesIO(content), sheet_name=None).values():
            for field in ('Huvudtext', 'header_text', 'header_text_normalized', 'supplier_text_raw'):
                if field in table:
                    assert not any(FINAL_BOOKING.search(value) for value in table[field]
                                   if isinstance(value, str))
    kept = pd.read_excel(BytesIO(review.downloads['granskning.xlsx']))
    assert kept.Huvudtext.tolist() == DISPLAY + ['Apoteket AB'] * 17
    excluded = pd.read_excel(BytesIO(review.downloads['bortfiltrerade.xlsx']))
    assert excluded.Huvudtext.tolist() == ['Apoteket AB']
    sample = pd.read_excel(BytesIO(review.downloads['manual_sample.xlsx']))
    assert sample.header_text.tolist() == ['Apoteket AB']
    provenance = pd.read_excel(BytesIO(review.downloads['granskning.xlsx']), sheet_name='Källspårning')
    assert provenance.source_row_position.tolist() == list(range(22)) + [23]

    if result.supplier_analysis.registry.available:
        analysis = result.supplier_analysis.rows
        assert analysis.supplier_match_status.tolist()[:6] == [
            'STRONG_MATCH', 'STRONG_MATCH', 'SUPPLIER_NOT_IDENTIFIED',
            'SUPPLIER_NOT_IDENTIFIED', 'STRONG_MATCH', 'STRONG_MATCH']
        assert analysis.supplier_text_raw.iloc[[0, 1, 4, 5]].tolist() == ['Apoteket AB'] * 4
        assert analysis.supplier_text_raw.iloc[[2, 3]].isna().all()


def test_ui_tables_details_and_kpi_drilldowns_hide_markers(review):
    original = review.result.original_data.copy(deep=True)
    fields, _ = review_row_detail(review.result, 0)
    assert fields.set_index('Fält').loc['Huvudtext', 'Källvärde'] == 'Apoteket AB'
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'),
                            default_timeout=20)
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    assert app.tabs[0].dataframe[0].value.Huvudtext.tolist()[:6] == DISPLAY
    for key in ('total', 'account', 'excluded'):
        app.button(key='kpi_' + key).click().run()
        assert not app.exception
        for table in app.dataframe:
            if 'Huvudtext' in table.value:
                assert not any(FINAL_BOOKING.search(value) for value in table.value.Huvudtext
                               if isinstance(value, str))
    pd.testing.assert_frame_equal(review.result.original_data, original)


@pytest.mark.parametrize('field', ['Huvudtext', ' Huvudtext ', 'header_text',
                                  'supplier_text_raw', '_supplier_text_raw'])
def test_display_handles_duplicate_columns_and_preserves_unrelated_values(field):
    values = HEADERS + [None, 123, '  Slutkund  AB  ', 'Slutk123', 'A Slutk1 extra Slutk 2']
    expected = DISPLAY + [None, 123, '  Slutkund  AB  ', '', 'A extra']
    source = pd.DataFrame([[value, value, value] for value in values],
                          columns=[field, field, 'Radtext'])
    before = source.copy(deep=True)
    displayed = display_dataframe(source)
    # Mixed types become strings solely for Arrow display compatibility.
    assert displayed.iloc[:, 0].tolist() == [pd.NA if v is None else str(v) for v in expected]
    assert displayed.iloc[:, 1].equals(displayed.iloc[:, 0])
    assert displayed.Radtext.iloc[0] == HEADERS[0]
    pd.testing.assert_frame_equal(source, before)


def test_flagged_context_cleans_each_header_and_keeps_multiline_context():
    source = pd.DataFrame({'header_text': ['Apoteket AB Slutk123', 'Annan AB Slutk 456']})
    context = context_fields(source)
    assert context['header_text'] == 'Apoteket AB\nAnnan AB'
    assert display_dataframe(pd.DataFrame([context])).header_text.iloc[0] == context['header_text']
    assert source.header_text.tolist() == ['Apoteket AB Slutk123', 'Annan AB Slutk 456']
