"""Review presentation and upload isolation using actual synthetic upload flows."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import re
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import src.ingestion.registry_source as sources
import src.supplier_matching.settings as matching_settings
from tests.synthetic_org import org
from tests.test_feature_package import workbook


APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'
MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
RETAINED_IDS = ['strong', 'ambiguous', 'absent', 'unknown']
MATCH_COLUMNS = ['Leverantör i internkontrollsfilen', 'Leverantör i avtalsregistret',
                 'Matchningsresultat', 'Matchningsscore', 'Varför detta resultat?']
TOP_TABS = ['Analysöversikt', 'Avvikelser och avtalsperioder', 'Manuellt stickprov',
            'Leverantörsmatchning', 'Detaljer', 'Export']


@pytest.fixture
def local_register_only(monkeypatch):
    config = deepcopy(matching_settings.load_matching_settings())
    config.update(default_registry_path=None, registry_snapshot_date=None)
    load = lambda *args, **kwargs: deepcopy(config)
    monkeypatch.setattr(matching_settings, 'load_matching_settings', load)
    monkeypatch.setattr(sources, 'load_matching_settings', load)


def invoice_rows():
    return pd.DataFrame({
        'Vernr': ['excluded', *RETAINED_IDS], 'Vrad': [1] * 5,
        'Verdatum': ['2026-06-15'] * 5, 'Utfall': [100] * 5,
        'Konto': ['7698', '4000', '4000', '4000', '4000'], 'Vertyp': ['X'] * 5,
        'Huvudtext': ['Alpha AB Slutk1', 'Alpha AB Slutk2', 'Nordmöbler Slutk3',
                     'Obekant Testbolag AB Slutk4', 'Original utan markör'],
        'Radtext': ['Exkluderad', 'Stark', 'Osäker', 'Ingen träff', 'Ingen identitet'],
    })


def register_rows():
    return pd.DataFrame({
        'Leverantör': ['Alpha AB', 'Nordmöbler AB', 'Nordmöbler Göteborg AB',
                       'Manuell Registerleverantör AB'],
        'Organisationsnummer': [org(1), org(2), org(3), 'synthetic-invalid'],
        'Avtalsnamn': ['Syntetiskt avtal'] * 4, 'Avtals-ID': ['a', 'b', 'c', 'd'],
        'Startdatum': ['2026-01-01'] * 4, 'Slutdatum': ['2026-12-31'] * 4,
    })


def review_tab(app):
    return next(tab for tab in app.tabs if tab.label == 'Leverantörsmatchning')


def register_warnings(app):
    controls = next(tab for tab in app.tabs if tab.label == 'Kontroller')
    return next(expander for expander in controls.expander if expander.label == 'Registervarningar')


def start_uploaded_review():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.file_uploader[0].set_value(('syntetiskt-underlag.xlsx', workbook(invoice_rows()), MIME)).run()
    app.file_uploader[1].set_value(('syntetiskt-register.xlsx', workbook(register_rows()), MIME)).run()
    app.date_input[0].set_value(date(2026, 6, 1)).run()
    next(button for button in app.button if button.label == 'Starta analys').click().run()
    assert not app.exception
    return app, app.session_state['review']


def descendants(block):
    for child in block.children.values():
        yield child
        if hasattr(child, 'children'):
            yield from descendants(child)


def test_review_layout_is_preserved_and_register_warnings_stay_in_controls(local_register_only):
    app, saved = start_uploaded_review()
    issues = saved.result.supplier_analysis.registry.issues
    assert len(issues) == 1 and 'INVALID_FORMAT' in issues[0]
    main_tabs = list(app.main.get('tab_container')[0].children.values())
    assert [tab.label for tab in main_tabs] == TOP_TABS
    assert [tab.label for tab in main_tabs[4].get('tab_container')[0].children.values()] == [
        'Granskning', 'Bortfiltrerade', 'Kontroller']
    tab = review_tab(app)
    assert [heading.value for heading in tab.subheader] == [
        'Leverantörsmatchning mot Koncerninköp']
    details_review = next(tab for tab in app.tabs if tab.label == 'Granskning')
    assert [heading.value for heading in details_review.subheader] == [
        'Flaggade verifikationer', 'Valideringsfel']
    assert [button.key for button in tab.button if button.key and button.key.startswith('supplier_')] == [
        'supplier_all', 'supplier_STRONG_MATCH', 'supplier_AMBIGUOUS_MATCH',
        'supplier_NO_MATCH', 'supplier_SUPPLIER_NOT_IDENTIFIED', 'supplier_date_warning']
    assert [button.label.split('**')[1] for button in tab.button
            if button.key and button.key.startswith('supplier_')] == ['4', '1', '1', '1', '1', '4']

    table = tab.dataframe[0]
    assert table.value.Vernr.tolist() == RETAINED_IDS
    assert list(table.proto.column_order)[:5] == MATCH_COLUMNS
    assert set(invoice_rows().columns).issubset(table.value.columns)
    assert table.value.Huvudtext.tolist() == [
        'Alpha AB', 'Nordmöbler', 'Obekant Testbolag AB', 'Original utan markör']
    pd.testing.assert_series_equal(table.value['Matchningsscore'].reset_index(drop=True),
                                   saved.result.supplier_analysis.rows.supplier_match_score.reset_index(drop=True),
                                   check_names=False)
    assert 'Nordmöbler AB (kandidat)' in table.value['Leverantör i avtalsregistret'].tolist()
    ordered = list(descendants(tab))
    positions = {id(item): position for position, item in enumerate(ordered)}
    source_caption = next(item for item in tab.caption if item.value.startswith('Alla kvarvarande rader'))
    classification = next(item for item in tab.expander if item.label.startswith('Vyavgränsning'))
    assert positions[id(tab.subheader[0])] < positions[id(source_caption)] < positions[id(table)]
    assert positions[id(table)] < positions[id(classification)]
    assert len([item for item in app.expander if item.label.startswith('Vyavgränsning')]) == 1
    assert not any(item.label.startswith('Vyavgränsning') for item in main_tabs[0].expander)
    assert not any(button.key and button.key.startswith('supplier_') for button in main_tabs[0].button)
    assert not any(table.key == 'review_rows' for table in main_tabs[0].dataframe)

    assert [heading.value for heading in main_tabs[0].subheader] == ['Analysöversikt']
    assert [heading.value for heading in main_tabs[1].subheader] == ['Avvikelser och avtalsperioder']
    assert ('För rader utan någon leverantörskandidat finns ingen avtalsjämförelse i backend. '
            'De räknas inte i denna fördelning; deras evidens finns under Leverantörsmatchning.'
            in [item.value for item in main_tabs[1].caption])
    manual = main_tabs[2]
    sample_overview = next(container for container in manual.get('flex_container')
                           if container.proto.id.endswith('-sample_overview'))
    register_info = next(item for item in manual.text if item.value.startswith('Register för denna körning:'))
    method_heading = next(item for item in manual.subheader if item.value == 'Urvalsmetod')
    manual_positions = {id(item): position for position, item in enumerate(descendants(manual))}
    assert max(manual_positions[id(item)] for item in descendants(sample_overview)) < manual_positions[id(register_info)]
    assert manual_positions[id(register_info)] < manual_positions[id(method_heading)]
    assert register_info.value == 'Register för denna körning: syntetiskt-register.xlsx (matchning tillgänglig)'
    assert len([item for item in app.text if item.value.startswith('Register för denna körning:')]) == 1
    assert len(app.radio) == len(manual.radio) == 1
    assert manual.radio[0].key == 'manual_sample_method'
    assert len(app.download_button) == len(main_tabs[5].download_button) == 6

    assert not any('Registerrad' in warning.value for warning in tab.warning)
    warnings = register_warnings(app)
    assert not warnings.proto.expanded
    assert [item.value for item in warnings.text] == list(issues)
    assert saved.result.supplier_analysis.registry.issues == issues
    assert [upload.label for upload in app.sidebar.file_uploader] == [
        'Här laddar du upp fakturaunderlaget', 'Här laddar du upp koncernavtalsregistret']
    assert 'Uppladdat fakturaunderlag: syntetiskt-underlag.xlsx' in [item.value for item in app.sidebar.text]
    assert 'Filen har kontrollerats utan valideringsfel. Du kan fortsätta med granskningen.' in [
        item.value for item in app.sidebar.caption]
    review_text = '\n'.join(item.value for kind in ('caption', 'text', 'markdown', 'subheader')
                            for item in tab.get(kind))
    assert all(text not in review_text for text in (
        'Uppladdat fakturaunderlag:', 'Aktivt avtalsregister:', 'Kom igång med din granskning',
        'Ladda upp ditt fakturaunderlag till vänster', 'Filen har kontrollerats utan valideringsfel'))
    assert not any(container.proto.id.endswith('-empty_state') for container in app.main.get('flex_container'))


def test_review_filters_selection_and_navigation_preserve_completed_analysis(local_register_only):
    app, saved = start_uploaded_review()
    original = saved.result.original_data.copy(deep=True)
    matching = saved.result.supplier_analysis.rows.copy(deep=True)
    issues = saved.result.supplier_analysis.registry.issues
    base_exclusions = app.multiselect(key='excluded_types').value
    with patch('src.ui_support.run_pipeline', side_effect=AssertionError('View navigation must not reanalyze')):
        app.multiselect(key='vf:review_rows:columns').set_value([0]).run()
        app.text_input(key='vf:review_rows:c0:text').set_value('strong').run()
        assert review_tab(app).dataframe[0].value.Vernr.tolist() == ['strong']
        app.button(key='supplier_AMBIGUOUS_MATCH').click().run()
        assert not app.exception
        table = review_tab(app).dataframe[0]
        assert table.value.Vernr.tolist() == ['ambiguous']
        assert app.multiselect(key='vf:review_rows:columns').value == []
        states = app._tree.get_widget_states()
        selection = states.widgets.add()
        selection.id = table.proto.id
        selection.string_value = json.dumps({'selection': {'rows': [0], 'columns': [], 'cells': []}})
        app._run(states)
        assert not app.exception
        assert 'Vald rad – detaljer' in [heading.value for heading in review_tab(app).subheader]
        assert 'ambiguous' in [item.value for item in review_tab(app).text]
        assert any('Manuell granskning krävs' in item.value for item in review_tab(app).warning)
        technical = next(item for item in review_tab(app).expander if item.label == 'Visa tekniska matchningsdetaljer')
        assert technical.dataframe[1].value.supplier_name.tolist() == ['Nordmöbler AB', 'Nordmöbler Göteborg AB']
        app.button(key='home').click().run()
        assert not app.exception
        assert review_tab(app).dataframe[0].value.Vernr.tolist() == RETAINED_IDS
        assert 'selected_supplier' not in app.session_state
        assert 'Vald rad – detaljer' not in [heading.value for heading in review_tab(app).subheader]
        assert app.multiselect(key='excluded_types').value == base_exclusions
    pd.testing.assert_frame_equal(saved.result.original_data, original)
    pd.testing.assert_frame_equal(saved.result.supplier_analysis.rows, matching)
    assert saved.result.supplier_analysis.registry.issues == issues
    assert app.session_state['review'] is saved


def test_eager_tab_reruns_keep_random_sample_plans_and_deferred_exports(local_register_only):
    app, _ = start_uploaded_review()
    app.radio(key='manual_sample_method').set_value('randomized').run()
    assert not app.exception
    saved = app.session_state['review']
    plan = saved.result.sampling_result
    plans = saved.sampling_plans
    summary = saved.result.summary
    original = saved.result.original_data.copy(deep=True)
    matching = saved.result.supplier_analysis.rows.copy(deep=True)
    selected_positions = [position for verification in plan.sample for position in verification.rows.index]
    seed, generated_at = plan.seed, plan.generated_at
    assert seed is not None
    assert not saved.downloads._bytes

    # Native eager-tab clicks do not run Python. Ordinary reruns execute every
    # tab and must not create new analysis, sampling or download snapshots.
    with patch('src.ui_support.run_pipeline', side_effect=AssertionError('Unexpected reanalysis')), \
            patch('src.ui_support.plan_random_sample', side_effect=AssertionError('Unexpected sample regeneration')), \
            patch('src.supplier_matching.matcher.SupplierMatcher.match', side_effect=AssertionError('Unexpected rematch')), \
            patch('src.output.report_generator._workbook', side_effect=AssertionError('No download requested')):
        app.run()
        assert not app.exception
        app.button(key='control_analyzed').click().run()
        assert not app.exception
        app.button(key='home').click().run()
        assert not app.exception
        current = app.session_state['review']
        assert current is saved
        assert current.sampling_plans is plans
        assert current.result.sampling_result is plan
        assert current.result.summary is summary
        assert plan.seed == seed and plan.generated_at == generated_at
        assert [position for verification in plan.sample for position in verification.rows.index] == selected_positions
        assert app.radio(key='manual_sample_method').value == 'randomized'
        assert len([button for button in app.button if button.key == 'regenerate_manual_sample']) == 1
        assert not saved.downloads._bytes
    pd.testing.assert_frame_equal(saved.result.original_data, original)
    pd.testing.assert_frame_equal(saved.result.supplier_analysis.rows, matching)


@pytest.mark.parametrize('register_state', ['missing', 'unreadable'])
def test_unavailable_register_keeps_review_availability_feedback(local_register_only, register_state):
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.file_uploader[0].set_value(('underlag.xlsx', workbook(invoice_rows()), MIME)).run()
    if register_state == 'unreadable':
        app.file_uploader[1].set_value(('oläsbart-register.xlsx', b'not an Excel workbook', MIME)).run()
    next(button for button in app.button if button.label == 'Starta analys').click().run()
    assert not app.exception
    tab = review_tab(app)
    availability = tab.error if register_state == 'unreadable' else tab.info
    assert any('Leverantörsmatchningen kunde inte genomföras.' in item.value for item in availability)
    assert tab.dataframe[0].value.Vernr.tolist() == RETAINED_IDS
    assert not any(column in tab.dataframe[0].value for column in MATCH_COLUMNS)
    issues = app.session_state['review'].result.supplier_analysis.registry.issues
    assert [item.value for item in register_warnings(app).text] == list(issues)
    assert not register_warnings(app).proto.expanded
    manual = next(tab for tab in app.tabs if tab.label == 'Manuellt stickprov')
    name = 'oläsbart-register.xlsx' if register_state == 'unreadable' else 'Inget register'
    assert [item.value for item in manual.text if item.value.startswith('Register för denna körning:')] == [
        f'Register för denna körning: {name} (matchning ej tillgänglig)']
    deviations = next(tab for tab in app.tabs if tab.label == 'Avvikelser och avtalsperioder')
    assert 'Avtalsevidens saknas när leverantörsmatchningen är otillgänglig.' in [
        item.value for item in deviations.caption]


def test_invalid_invoice_replacement_restores_review_without_losing_register_date(local_register_only):
    app, _ = start_uploaded_review()
    app.file_uploader[0].set_value(('oläsbart.xlsx', b'not an Excel workbook', MIME)).run()
    next(button for button in app.button if button.label == 'Starta analys').click().run()
    assert not app.exception
    assert not app.tabs
    assert [item.value for item in app.sidebar.error] == [
        'Fakturaunderlaget kunde inte läsas. Ladda upp en giltig Excel-fil (.xlsx) och försök igen.']
    assert not app.main.error
    replacement = workbook(invoice_rows().iloc[[1]])
    app.file_uploader[0].set_value(('ersättning.xlsx', replacement, MIME)).run()
    assert not app.sidebar.error
    assert app.date_input[0].value == date(2026, 6, 1)
    assert 'Kom igång med din granskning' in [heading.value for heading in app.main.subheader]
    next(button for button in app.button if button.label == 'Starta analys').click().run()
    assert not app.exception
    assert review_tab(app).dataframe[0].value.Vernr.tolist() == ['strong']
    assert app.session_state['review'].source_content == replacement
    assert app.session_state['review'].registry_snapshot_date == date(2026, 6, 1)
    assert 'Uppladdat fakturaunderlag: ersättning.xlsx' in [item.value for item in app.sidebar.text]


def test_upload_css_override_cannot_hide_review_tabs_or_controls():
    css = (APP.parent / '.streamlit/style.css').read_text()
    rules = re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'/\*.*?\*/', '', css, flags=re.S))
    upload_rules = [(selectors.strip(), body.strip()) for selectors, body in rules
                    if 'stFileUploaderDropzoneInstructions' in selectors]
    assert len(upload_rules) == 1
    selectors, body = upload_rules[0]
    assert {selector.strip() for selector in selectors.split(',')} == {
        '.st-key-invoice_upload_panel [data-testid="stFileUploaderDropzoneInstructions"]',
        '.st-key-registry_upload_panel [data-testid="stFileUploaderDropzoneInstructions"]',
    }
    assert body == 'display: none;'
    # Existing shared tab presentation remains separate from uploader overrides.
    assert '[role="tablist"]' in css and '[role="tabpanel"]' in css
    assert '.st-key-supplier_kpis button' in css
