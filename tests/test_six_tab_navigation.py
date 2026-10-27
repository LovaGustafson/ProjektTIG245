"""Six-tab sampling boundaries, stable sessions and deferred XLSX controls."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import src.ingestion.registry_source as sources
import src.supplier_matching.settings as matching_settings
from src.output import report_generator
from src.ui_support import analyze_upload, select_sample_method
from tests.test_feature_package import invoices, registry, workbook
from tests.test_ui_sampling import population, sample_ids
from tests.test_ui_ux import assert_same_analysis


APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'
DOWNLOADS = {
    'granskning.xlsx': 'Kvar för granskning',
    'bortfiltrerade.xlsx': 'Bortfiltrerade',
    'samlad_kontrollfil.xlsx': 'Samlad kontrollfil',
    'flagged_invoices.xlsx': 'Hämta avvikelserapport',
    'manual_sample.xlsx': 'Hämta manuellt stickprov',
    'uncertain_suppliers.xlsx': 'Hämta osäkra namnmatchningar',
}


@pytest.fixture
def no_local_default(monkeypatch):
    configured = deepcopy(matching_settings.load_matching_settings())
    configured.update(default_registry_path=None, registry_snapshot_date=None)
    load = lambda *args, **kwargs: deepcopy(configured)
    monkeypatch.setattr(matching_settings, 'load_matching_settings', load)
    monkeypatch.setattr(sources, 'load_matching_settings', load)


def run_review(review):
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    return app


def tab(app, label):
    return next(item for item in app.tabs if item.label == label)


def descendants(block):
    for child in block.children.values():
        yield child
        if hasattr(child, 'children'):
            yield from descendants(child)


@pytest.mark.parametrize('mode', ['uploaded', 'missing', 'unreadable'])
def test_manual_overview_then_dynamic_register_information_then_sampling_controls(no_local_default, mode):
    options = {'registry_mode': 'disabled'} if mode == 'missing' else {
        'registry_mode': 'uploaded', 'registry_name': 'syntetiskt-aktuellt-register.xlsx',
        'registry_content': workbook(registry()) if mode == 'uploaded' else b'invalid workbook',
    }
    review = analyze_upload(workbook(invoices(22)), defer_downloads=True, **options)
    app = run_review(review)
    manual = tab(app, 'Manuellt stickprov')
    overview = next(item for item in manual.get('flex_container') if item.key == 'sample_overview')
    expected = (
        'Register för denna körning: Inget register (matchning ej tillgänglig)' if mode == 'missing' else
        'Register för denna körning: syntetiskt-aktuellt-register.xlsx '
        + ('(matchning tillgänglig)' if mode == 'uploaded' else '(matchning ej tillgänglig)'))
    register_line = next(item for item in manual.text if item.value.startswith('Register för denna körning:'))
    assert register_line.value == expected
    assert [item.value for item in app.text if item.value.startswith('Register för denna körning:')] == [expected]
    method_heading = next(item for item in manual.subheader if item.value == 'Urvalsmetod')
    ordered = list(descendants(manual))
    positions = {id(item): index for index, item in enumerate(ordered)}
    assert max(positions[id(item)] for item in descendants(overview)) < positions[id(register_line)]
    assert positions[id(register_line)] < positions[id(method_heading)]
    assert len(app.radio) == len(manual.radio) == 1
    assert manual.radio[0].key == 'manual_sample_method'
    assert not any(button.key == 'regenerate_manual_sample' for button in app.button)
    assert app.session_state['review'] is review


def test_eager_tab_reruns_keep_saved_random_sample_and_chart_revision(no_local_default, monkeypatch):
    monkeypatch.setattr('src.ui_support.new_sample_seed', lambda previous=None: 123)
    review = select_sample_method(analyze_upload(workbook(population(44)),
        registry_mode='disabled', defer_downloads=True), 'randomized')
    before = deepcopy(review.result)
    plan, plans, downloads = review.result.sampling_result, review.sampling_plans, review.downloads
    with (patch('src.ui_support.run_pipeline', side_effect=AssertionError('navigation must not analyze')),
          patch('src.ui_support.plan_random_sample', side_effect=AssertionError('navigation must not sample')),
          patch.object(report_generator, '_workbook', side_effect=AssertionError('no download requested'))):
        app = run_review(review)
        revisions = dict(app.session_state['overview_charts:revisions'])
        app.run()
        app.button(key='kpi_review').click().run()
        app.multiselect(key='vf:manual:columns').set_value([0]).run()
        app.text_input(key='vf:manual:c0:text').set_value(sample_ids(review)[0]).run()
        assert not app.exception
        assert app.session_state['overview_charts:revisions'] == revisions
        assert app.session_state['overview_charts:result'] is review.result
        assert app.session_state['review'] is review
        assert review.result.sampling_result is plan
        assert review.sampling_plans is plans
        assert review.downloads is downloads and not downloads._bytes
        assert app.radio(key='manual_sample_method').value == 'randomized'
        assert len([button for button in app.button if button.key == 'regenerate_manual_sample']) == 1
        assert tab(app, 'Manuellt stickprov').button(key='regenerate_manual_sample')
    assert_same_analysis(before, review.result)


def test_six_existing_downloads_stay_in_export_and_generate_only_requested_workbooks(no_local_default):
    review = analyze_upload(workbook(invoices(22)), registry_content=workbook(registry()),
        registry_name='syntetiskt-register.xlsx', defer_downloads=True)
    with patch.object(report_generator, '_workbook', wraps=report_generator._workbook) as serialize:
        app = run_review(review)
        exports = tab(app, 'Export')
        assert [button.label for button in exports.download_button] == list(DOWNLOADS.values())
        assert len(app.download_button) == len(exports.download_button) == 6
        assert all(button.proto.ignore_rerun and button.proto.deferred_file_id
                   for button in exports.download_button)
        assert serialize.call_count == 0 and not review.downloads._bytes
        for index, filename in enumerate(DOWNLOADS):
            tab(app, 'Export').download_button[index].click().run()
            assert not app.exception
            content = review.downloads[filename]
            assert serialize.call_count == index + 1
            sheets = pd.read_excel(BytesIO(content), sheet_name=None)
            assert sheets
            assert all(not report_generator.XLSX_EXCLUDED_COLUMNS.intersection(data.columns)
                       for data in sheets.values())
            assert review.downloads[filename] is content
            assert serialize.call_count == index + 1
        assert set(review.downloads._bytes) == set(DOWNLOADS)
        assert app.session_state['review'] is review
