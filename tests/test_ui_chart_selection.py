"""Real Streamlit widget events select existing evidence, without reanalysis."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.filtering.filter_engine import load_exclusions
from src.ui_chart_selection import selected_category
from src.ui_run_summary import dashboard_tables
from src.ui_support import analyze_upload
from tests.test_feature_package import invoices, workbook
from tests.test_ui_overview_details import review, overview_app, expander, evidence_table
from tests.test_ui_ux import assert_same_analysis, assert_same_workbook


APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'


def chart_element(app, chart):
    return next(c for c in app.get('vega_lite_chart') if f':{chart}:event:' in c.proto.id)


def rerun(app, chart=None, category=None):
    states = app._tree.get_widget_states()
    # AppTest does not serialize unknown Vega widgets. Include every chart's
    # current state, as the browser does, alongside the changed widget event.
    for element in app.get('vega_lite_chart'):
        event = states.widgets.add()
        event.id = element.proto.id
        value = app.session_state[event.id]
        if chart is not None and f':{chart}:event:' in event.id:
            value = {'selection': {'category': [] if category is None else [{'Status': category}]}}
        event.string_value = json.dumps(value)
    app._run(states)
    assert not app.exception
    return app


def select(app, chart, category):
    return rerun(app, chart, category)


@pytest.mark.parametrize('event', [None, {}, {'selection': None}, {'selection': {'category': None}},
    {'selection': {'category': []}}, {'selection': {'category': ['included']}},
    {'selection': {'category': [{'Kategori': 'Kvarvarande'}]}},
    {'selection': {'category': [{'Status': 'stale'}]}},
    {'selection': {'category': [{'Status': 'included'}, {'Status': 'excluded'}]}}])
def test_invalid_or_empty_selection_cannot_invent_a_population(event):
    assert selected_category(event, ['included', 'excluded']) is None


def test_exact_key_parsing():
    assert selected_category({'selection': {'category': [{'Status': 'included'}]}}, ['included']) == 'included'
    assert selected_category({'selection': {'category': [{'Status': 'account: 7698'}]}}, ['account: 7698']) == 'account: 7698'


def test_all_chart_categories_open_exact_existing_evidence(review):
    result = review.result
    before = deepcopy(result)
    app = overview_app(result)
    charts = dashboard_tables(result)
    for chart, counts in charts.items():
        for item in counts.itertuples(index=False):
            select(app, 'chart_' + chart, item.Status)
            detail = expander(app, item.Kategori + ' ·')
            assert detail.proto.expanded
            assert any(i.value.startswith(f'Visar {item.Antal} ') and i.value.endswith('– ' + item.Kategori)
                       for i in app.info)
            rows = evidence_table(detail, 'source_excel_row') if item.Antal else pd.DataFrame()
            if chart == 'population':
                expected = (result.filtering.cleaned_data if item.Status == 'included' else result.filtering.excluded_data)
                assert rows.source_row_position.tolist() == expected.index.tolist()
                assert len(rows) == item.Antal
            elif chart == 'exclusions':
                kind, _, value = item.Status.partition(': ')
                assert rows.source_row_position.tolist() == result.filtering.rule_details[kind][value]
                assert len(rows) == item.Antal
            elif chart == 'suppliers':
                expected = result.supplier_analysis.rows.loc[lambda d: d.supplier_match_status.eq(item.Status)]
                matches = evidence_table(detail, 'supplier_match_status')
                pd.testing.assert_frame_equal(matches, expected, check_dtype=False)
                assert rows.source_row_position.tolist() == expected.source_row_position.tolist()
                assert len(rows) == item.Antal
            elif chart == 'contracts':
                expected = result.supplier_analysis.contracts.loc[lambda d: d.contract_period_status.eq(item.Status)]
                assert len(expected) == item.Antal
                if item.Antal:
                    actual = evidence_table(detail, 'contract_period_status')
                    pd.testing.assert_frame_equal(actual, expected, check_dtype=False)
                    assert set(rows.source_row_position) == set(expected.source_row_position)
                else:
                    assert not detail.dataframe
            else:
                groups = evidence_table(detail, 'population_position')
                assert len(groups) == item.Antal
                expected = [p for v in result.manual_sample for p in v.rows.index]
                if item.Status == 'selected':
                    assert rows.source_row_position.tolist() == expected
                else:
                    all_grouped = [p for v in result.verifications for p in v.rows.index]
                    assert rows.source_row_position.tolist() == [p for p in all_grouped if p not in expected]
                assert groups.row_count.sum() == len(rows)
    assert_same_analysis(result, before)


def test_switch_reset_home_and_chart_isolation(review):
    app = AppTest.from_file(str(APP), default_timeout=20)
    app.session_state['review'] = review
    app.run()
    select(app, 'chart_population', 'included')
    select(app, 'chart_suppliers', 'AMBIGUOUS_MATCH')
    assert expander(app, 'Kvarvarande ·').proto.expanded
    assert expander(app, 'Osäker träff ·').proto.expanded
    select(app, 'chart_population', 'excluded')
    assert not expander(app, 'Kvarvarande ·').proto.expanded
    assert expander(app, 'Exkluderade ·').proto.expanded
    rerun(app)  # Unrelated rerun keeps both selections.
    assert expander(app, 'Exkluderade ·').proto.expanded
    assert expander(app, 'Osäker träff ·').proto.expanded
    old_id = chart_element(app, 'chart_population').proto.id
    app.button(key='overview_chart:chart_population:reset').click()
    rerun(app)
    assert not app.exception
    assert chart_element(app, 'chart_population').proto.id != old_id
    assert not expander(app, 'Exkluderade ·').proto.expanded
    assert expander(app, 'Osäker träff ·').proto.expanded
    select(app, 'chart_suppliers', None)  # Chart's native double-click clear.
    assert not expander(app, 'Osäker träff ·').proto.expanded
    select(app, 'chart_population', 'included')
    app.button(key='home').click()
    rerun(app)
    assert not app.exception
    assert not expander(app, 'Kvarvarande ·').proto.expanded
    assert not any(b.label == 'Rensa diagramval' for b in app.button)


def test_new_result_resets_even_same_categories_and_counts(review):
    app = overview_app(review.result)
    select(app, 'chart_population', 'included')
    previous_id = chart_element(app, 'chart_population').proto.id
    app.session_state['result'] = deepcopy(review.result)
    app.run()
    assert not app.exception
    assert chart_element(app, 'chart_population').proto.id != previous_id
    assert not expander(app, 'Kvarvarande ·').proto.expanded


def test_view_scoped_suppliers_and_full_run_contracts(review):
    result = deepcopy(review.result)
    result.supplier_view.loc[result.supplier_view.source_row_position.eq(1), 'excluded_from_view'] = True
    app = overview_app(result)
    select(app, 'chart_suppliers', 'AMBIGUOUS_MATCH')
    detail = expander(app, 'Osäker träff ·')
    assert detail.label == 'Osäker träff · 1 rader'
    assert evidence_table(detail, 'source_excel_row').source_row_position.tolist() == [3]
    select(app, 'chart_contracts', 'NOT_CHECKED')
    detail = expander(app, 'Ej verifierbar ·')
    assert detail.label == 'Ej verifierbar · 8 avtalsjämförelser'
    assert evidence_table(detail, 'source_excel_row').source_row_position.tolist() == [1, 3, 7, 8]


def test_zero_category_and_unavailable_new_result(review):
    app = overview_app(review.result)
    select(app, 'chart_contracts', 'ERROR')
    empty = expander(app, 'Tekniskt fel ·')
    assert empty.proto.expanded and not empty.dataframe
    assert any(c.value == 'Inga poster i denna kategori.' for c in empty.caption)
    fresh = analyze_upload(workbook(invoices(1)), registry_mode='disabled', defer_downloads=True)
    app.session_state['result'] = fresh.result
    app.run()
    assert not app.exception
    assert not any(':chart_contracts:event:' in c.proto.id or ':chart_suppliers:event:' in c.proto.id
                   for c in app.get('vega_lite_chart'))
    select(app, 'chart_population', 'excluded')
    assert expander(app, 'Exkluderade · 0').proto.expanded


def test_refilter_and_new_upload_clear_chart_state_without_changing_analysis_or_exports(review):
    upload = analyze_upload(review.source_content, registry_source=review.registry_source, defer_downloads=True)
    original = deepcopy(upload.result)
    app = AppTest.from_file(str(APP), default_timeout=20)
    app.session_state['review'] = upload
    app.run()
    with patch('src.ui_support.run_pipeline', side_effect=AssertionError('chart must not reanalyze')):
        for chart, category in [('population', 'included'), ('suppliers', 'STRONG_MATCH'),
                                ('contracts', 'PASS'), ('sample', 'remaining')]:
            select(app, 'chart_' + chart, category)
    assert not upload.downloads._bytes
    assert_same_analysis(original, upload.result)
    assert_same_workbook(upload.downloads['samlad_kontrollfil.xlsx'], review.downloads['samlad_kontrollfil.xlsx'])
    previous_id = chart_element(app, 'chart_population').proto.id
    app.multiselect(key='excluded_types').set_value(['X', 'FBFM']).run()
    assert not app.exception
    assert chart_element(app, 'chart_population').proto.id != previous_id
    assert not any(b.label == 'Rensa diagramval' for b in app.button)
    fresh = app.session_state['review']
    baseline = analyze_upload(review.source_content, registry_source=review.registry_source,
                              excluded_verification_types=['X', 'FBFM'], defer_downloads=True)
    assert_same_analysis(fresh.result, baseline.result)
    select(app, 'chart_population', 'excluded')
    replacement = analyze_upload(workbook(invoices(2)), registry_mode='disabled', defer_downloads=True)
    app.session_state['review'] = replacement
    app.multiselect(key='excluded_types').set_value(load_exclusions()['excluded_verification_types'])
    app.run()
    assert not app.exception
    assert not expander(app, 'Exkluderade ·').proto.expanded
