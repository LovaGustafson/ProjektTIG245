"""Clickable summaries, exact row sets, home and source-linked evidence."""
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.models.result import CheckResult, CheckStatus
from src.ui_support import analyze_upload

APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'


def workbook(data):
    buffer = BytesIO()
    pd.DataFrame(data).to_excel(buffer, index=False)
    return buffer.getvalue()


def start():
    source = workbook({'Vernr': ['excluded', 'strong', 'ambiguous', 'absent', 'unknown'],
        'Vrad': [1] * 5, 'Verdatum': ['2026-09-01'] * 5,
        'Konto': ['7698', '4000', '4000', '4000', '4000'], 'Vertyp': ['X'] * 5,
        'Utfall': [1, 2, 3, 4, 'bad'],
        'Huvudtext': ['Alpha AB Prelb 0', 'Alpha AB Prelb 1', 'Nordmöbler Slutk 2',
                     'Obekant Testbolag AB Prelb 3', 'Original utan markör']})
    registry = workbook({'Leverantör': ['Alpha AB', 'Nordmöbler AB', 'Nordmöbler Göteborg AB'],
        'Organisationsnummer': ['1', '2', '3'], 'Namn': ['Avtal A', 'Avtal B', 'Avtal C'],
        'AvtalsID': ['a', 'b', 'c'], 'Startdatum': ['2026-01-01'] * 3, 'Slutdatum': ['2027-01-01'] * 3})
    review = analyze_upload(source, registry_content=registry)
    detection = review.result.detection_results[0]
    review.result.detection_results[0] = replace(detection, checks=detection.checks + (
        CheckResult(detection.verification_id, 'synthetic', CheckStatus.FLAGGED, 'Testorsak'),))
    app = AppTest.from_file(str(APP), default_timeout=20)
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    return app, review


@pytest.mark.parametrize('key,ids', [('all', ['strong', 'ambiguous', 'absent', 'unknown']),
    ('STRONG_MATCH', ['strong']), ('AMBIGUOUS_MATCH', ['ambiguous']),
    ('NO_MATCH', ['absent']), ('SUPPLIER_NOT_IDENTIFIED', ['unknown']),
    ('date_warning', ['strong', 'ambiguous', 'absent', 'unknown'])])
def test_supplier_cards_exact_rows_detail_and_home(key, ids):
    app, review = start()
    downloads = dict(review.downloads)
    original = review.result.original_data.copy(deep=True)
    app.button(key='supplier_' + key).click().run()
    assert not app.exception
    table = app.tabs[0].dataframe[0]
    assert table.value.Vernr.tolist() == ids
    assert app.button(key='supplier_' + key).label.startswith(f'**{len(ids)}**')
    assert any('Aktivt vyfilter:' in i.value for i in app.info)
    states = app._tree.get_widget_states()
    state = states.widgets.add()
    state.id = table.proto.id
    state.string_value = json.dumps({'selection': {'rows': [0], 'columns': [], 'cells': []}})
    app._run(states)
    assert not app.exception
    assert ids[0] in [t.value for t in app.text]
    expected_text = original.loc[original.Vernr == ids[0], 'Huvudtext'].iloc[0]
    assert expected_text in [t.value for t in app.text]
    assert any('Registerdatumvarning' in str(b.proto) for b in app.get('markdown'))
    if key == 'AMBIGUOUS_MATCH':
        candidates = next(e for e in app.expander if e.label == 'Leverantörskandidater och matchningsorsaker')
        assert candidates.dataframe[0].value.supplier_name.tolist() == ['Nordmöbler AB', 'Nordmöbler Göteborg AB']
        assert candidates.proto.expanded
        assert any('Manuell granskning krävs' in w.value for w in app.warning)
    if key == 'NO_MATCH':
        assert 'Sökt leverantörsnamn: Obekant Testbolag AB' in [t.value for t in app.text]
    app.button(key='home').click().run()
    assert not app.exception
    assert app.tabs[0].dataframe[0].value.Vernr.tolist() == ['strong', 'ambiguous', 'absent', 'unknown']
    assert 'selected_supplier' not in app.session_state
    assert not any(s.value == 'Vald rad – detaljer' for s in app.subheader)
    assert review.downloads == downloads
    pd.testing.assert_frame_equal(review.result.original_data, original)


@pytest.mark.parametrize('key,count', [('analyzed', 4), ('flagged', 1), ('validation', 1), ('not_checked', 16)])
def test_control_cards_show_exact_records_and_clear(key, count):
    app, _ = start()
    app.button(key='control_' + key).click().run()
    assert not app.exception
    assert len(app.tabs[2].dataframe[0].value) == count
    assert app.button(key='control_' + key).label.startswith(f'**{count}**')
    app.button(key='clear_drilldown_control').click().run()
    assert not app.exception
    assert 'selected_control' not in app.session_state


def test_home_clears_drilldown_and_temporary_filters_but_preserves_base_rules():
    app, review = start()
    base_rules = app.multiselect(key='excluded_types').value
    app.button(key='kpi_review').click().run()
    columns = review.result.original_data.columns.tolist()
    position = columns.index('Vernr')
    app.multiselect(key='vf:kpi_review_rows:columns').set_value([position]).run()
    app.text_input(key=f'vf:kpi_review_rows:c{position}:text').set_value('absent').run()
    assert len(app.dataframe[0].value) == 1
    assert app.button(key='vf:kpi_review_rows:clear_visible').label == 'Rensa vyfilter'
    app.button(key='home').click().run()
    assert not app.exception
    assert 'selected_kpi' not in app.session_state
    assert app.multiselect(key='excluded_types').value == base_rules
    app.button(key='kpi_review').click().run()
    assert len(app.dataframe[0].value) == 4
    app.button(key='clear_drilldown_dashboard').click().run()
    assert 'selected_kpi' not in app.session_state
