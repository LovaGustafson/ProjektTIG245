"""Streamlit regressions: independent views, clearing, source mapping and exports."""
from datetime import date
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.ui_support import analyze_upload

APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'


def source():
    data = pd.DataFrame({
        'Vernr': ['001', '002', '003', '004', '005', '006'], 'Vrad': [1] * 6,
        'VerDat': ['2026-08-01', '2026-08-02', '2026-08-03', '2026-09-01', '2026-09-08', 'fel'],
        'Utfall': [100, -200, 0, 500, 10000, 'fel'],
        'Konto': ['5410', '7698', '5410', '7699', '6000', '5410'],
        'Vertyp': ['NEW', 'NEW', 'KR01', 'KR01', 'NEW', 'NEW'],
        'Bild': ['a.pdf', None, 0, False, 'b.pdf', None],
        'Sign': ['aa', 'bb', None, 'cc', 'aa', None],
        'Att': [1, 0, None, 1, 0, None],
        'Radtext': ['Medicin', 'B', 'C', 'D', 'E', 'Sista raden'],
        'Huvudtext': ['Alpha', 'Beta', 'Alpha', 'Beta', 'Alpha', 'Gamma'],
        'Mm': [None, '01', '02', None, '03', None],
        'Pg': ['01'] * 6, 'Leverantör': ['Test AB'] * 6,
    })
    buffer = BytesIO()
    data.to_excel(buffer, index=False)
    return buffer.getvalue()


def start(content=None):
    review = analyze_upload(content or source())
    app = AppTest.from_file(str(APP), default_timeout=20)
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    return app, review


def choose(app, view, *labels):
    columns = app.session_state['review'].result.original_data.columns.tolist()
    app.multiselect(key=f'vf:{view}:columns').set_value([columns.index(label) for label in labels]).run()
    assert not app.exception


def key(app, view, label, suffix):
    index = app.session_state['review'].result.original_data.columns.tolist().index(label)
    return f'vf:{view}:c{index}:{suffix}'


def test_filters_are_per_view_clear_and_leave_engine_and_exports_unchanged():
    app, review = start()
    original = review.result.original_data.copy(deep=True)
    standardized = review.result.standardized_data.copy(deep=True)
    reasons = review.result.filtering.reasons
    downloads = dict(review.downloads)
    kpis = [app.button(key=f'kpi_{name}').label for name in ('total', 'review', 'account', 'verification_type', 'excluded')]
    with patch('src.ui_support.run_pipeline', side_effect=AssertionError('UI filters must not analyze again')):
        choose(app, 'review_rows', 'Konto', 'Vertyp')
        app.multiselect(key=key(app, 'review_rows', 'Konto', 'categories')).set_value(['5410']).run()
        app.multiselect(key=key(app, 'review_rows', 'Vertyp', 'categories')).set_value(['NEW']).run()
        assert app.tabs[0].dataframe[0].value['Vernr'].tolist() == ['001', '006']
        assert len(app.tabs[1].dataframe[0].value) == 3
        assert any(c.value == 'Visar 2 av 3 rader' for c in app.caption)
        assert any('Konto: 5410' in c.value and 'Vertyp: NEW' in c.value for c in app.caption)
        choose(app, 'excluded', 'Konto')
        app.multiselect(key=key(app, 'excluded', 'Konto', 'categories')).set_value(['7698']).run()
        assert app.tabs[1].dataframe[0].value['Vernr'].tolist() == ['002']
        app.button(key='vf:review_rows:clear').click().run()
        assert not app.exception
        assert app.multiselect(key='vf:review_rows:columns').value == []
        assert len(app.tabs[0].dataframe[0].value) == 3
        assert app.tabs[1].dataframe[0].value['Vernr'].tolist() == ['002']
    assert [app.button(key=f'kpi_{name}').label for name in ('total', 'review', 'account', 'verification_type', 'excluded')] == kpis
    pd.testing.assert_frame_equal(review.result.original_data, original)
    pd.testing.assert_frame_equal(review.result.standardized_data, standardized)
    assert review.result.filtering.reasons == reasons
    assert review.downloads == downloads


@pytest.mark.parametrize('label,widget,suffix,value,expected', [
    ('Bild', 'selectbox', 'presence', 'present', ['001', '005']),
    ('Bild', 'selectbox', 'presence', 'missing', ['006']),
    ('Mm', 'selectbox', 'missing', 'missing', ['001', '006']),
    ('Radtext', 'text_input', 'text', ' medicin ', ['001']),
    ('Huvudtext', 'text_input', 'text', 'ALPHA', ['001', '005']),
    ('Utfall', 'number_input', 'minimum', 1000.0, ['005']),
    ('Utfall', 'selectbox', 'sign', 'positive', ['001', '005']),
    ('VerDat', 'date_input', 'start', date(2026, 9, 1), ['005']),
])
def test_panel_controls_filter_mixed_values(label, widget, suffix, value, expected):
    app, _ = start()
    choose(app, 'review_rows', label)
    getattr(app, widget)(key=key(app, 'review_rows', label, suffix)).set_value(value).run()
    assert not app.exception
    assert app.tabs[0].dataframe[0].value['Vernr'].tolist() == expected


def test_filtered_selection_maps_to_original_row_and_clears_on_change():
    app, _ = start()
    choose(app, 'review_rows', 'Radtext')
    app.text_input(key=key(app, 'review_rows', 'Radtext', 'text')).set_value('Sista').run()
    table = app.tabs[0].dataframe[0]
    states = app._tree.get_widget_states()
    state = states.widgets.add()
    state.id = table.proto.id
    state.string_value = json.dumps({'selection': {'rows': [0], 'columns': [], 'cells': []}})
    app._run(states)
    assert not app.exception
    assert '006' in [t.value for t in app.text]
    assert 'Sista raden' in [t.value for t in app.text]
    assert any('Utfall' in warning.value for warning in app.warning)
    app.text_input(key=key(app, 'review_rows', 'Radtext', 'text')).set_value('Medicin').run()
    assert not app.exception
    assert app.tabs[0].dataframe[0].value['Vernr'].tolist() == ['001']
    assert not any(s.value == 'Vald rad – detaljer' for s in app.subheader)


def test_kpi_click_restores_exact_card_rows_and_reset_on_rule_change_and_new_upload():
    app, _ = start()
    app.button(key='kpi_review').click().run()
    choose(app, 'kpi_review_rows', 'Konto')
    app.multiselect(key=key(app, 'kpi_review_rows', 'Konto', 'categories')).set_value(['6000']).run()
    assert app.dataframe[0].value['Vernr'].tolist() == ['005']
    app.button(key='kpi_excluded').click().run()
    app.button(key='kpi_review').click().run()
    assert not app.exception
    # A fresh card click shows exactly its count, clearing only that view.
    assert app.dataframe[0].value['Vernr'].tolist() == ['001', '005', '006']
    assert len(app.tabs[0].dataframe[0].value) == 3
    app.multiselect(key='excluded_types').unselect('KR01').run()
    assert not app.exception
    assert app.multiselect(key='vf:kpi_review_rows:columns').value == []
    assert len(app.dataframe[0].value) == 4
    choose(app, 'review_rows', 'Konto')
    app.file_uploader[0].set_value(('new.xlsx', source(),
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')).run()
    assert not any(name.startswith('vf:') for name in app.session_state.filtered_state)


def test_manual_sample_has_original_fields_and_independent_filters():
    data = pd.DataFrame({'Vernr': [f'{i:03}' for i in range(1, 41)], 'Vrad': [1] * 40,
                         'VerDat': ['2026-09-08'] * 40, 'Utfall': range(40),
                         'Konto': ['5410'] * 40, 'Vertyp': ['NEW'] * 40,
                         'Radtext': [f'Rad {i}' for i in range(1, 41)]})
    buffer = BytesIO()
    data.to_excel(buffer, index=False)
    app, review = start(buffer.getvalue())
    manual = next(tab for tab in app.tabs if tab.label == 'Manuell kontroll')
    assert manual.dataframe[0].value['Vernr'].tolist() == ['020', '040']
    choose(app, 'manual', 'Radtext')
    app.text_input(key=key(app, 'manual', 'Radtext', 'text')).set_value('40').run()
    manual = next(tab for tab in app.tabs if tab.label == 'Manuell kontroll')
    assert manual.dataframe[0].value['Vernr'].tolist() == ['040']
    assert len(app.tabs[0].dataframe[0].value) == 40
    assert [v.verification_id for v in review.result.manual_sample] == ['020', '040']
    assert len(pd.read_excel(BytesIO(review.downloads['manual_sample.xlsx']))) == 2
