"""Swedish upload controls and register/date state; synthetic workbooks only."""
from copy import deepcopy
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import src.ingestion.registry_source as sources
import src.supplier_matching.settings as matching_settings
from tests.test_feature_package import invoices, registry, workbook

APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'
MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@pytest.fixture
def config(monkeypatch):
    configured = deepcopy(matching_settings.load_matching_settings())
    configured.update(default_registry_path=None, registry_snapshot_date=None)
    load = lambda *args, **kwargs: deepcopy(configured)
    monkeypatch.setattr(matching_settings, 'load_matching_settings', load)
    monkeypatch.setattr(sources, 'load_matching_settings', load)
    return configured


def app():
    result = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not result.exception
    assert not {'Ta bort register', 'Återställ standardregister'} & {b.label for b in result.button}
    return result


def start(review):
    next(b for b in review.button if b.label == 'Starta analys').click().run()
    assert not review.exception
    return review.session_state['review']


@pytest.mark.parametrize('mode', ['unconfigured', 'missing', 'directory'])
def test_missing_default_has_upload_instruction_without_filename_or_date(config, tmp_path, mode):
    if mode != 'unconfigured':
        config['default_registry_path'] = str(tmp_path if mode == 'directory' else tmp_path / 'missing.xlsx')
    config['registry_snapshot_date'] = '2026-08-31'  # Must remain invisible without a register.
    review = app()
    assert [u.label for u in review.file_uploader] == [
        'Här laddar du upp fakturaunderlaget', 'Här laddar du upp koncernavtalsregistret']
    assert all(list(u.proto.type) == ['.xlsx'] for u in review.file_uploader)
    assert all(not u.proto.multiple_files for u in review.file_uploader)
    assert not review.date_input
    assert not any('avtalsregister:' in t.value.lower() for t in review.text)
    assert [i.value for i in review.info] == [
        'Ladda upp ett koncernavtalsregister för att genomföra leverantörsmatchning.']
    assert 'I detta verktyg används Excel-filer (.xlsx)' in [c.value for c in review.caption]
    assert 'Det första kalkylbladet läses. Alla rader behandlas.' == review.file_uploader[0].proto.help
    assert next(b for b in review.button if b.label == 'Starta analys').disabled


@pytest.mark.parametrize('limit', [200, 75])
def test_swedish_size_caption_uses_actual_streamlit_limit(config, monkeypatch, limit):
    original = st.config.get_option
    def get_option(name):
        return limit if name == 'server.maxUploadSize' else original(name)
    monkeypatch.setattr(st.config, 'get_option', get_option)
    monkeypatch.setattr(st, 'get_option', get_option)
    review = app()
    assert [c.value for c in review.caption].count(f'Max {limit} MB per fil') == 2
    assert all(u.proto.max_upload_size_mb == limit for u in review.file_uploader)


def test_metadata_css_is_scoped_to_upload_panels_and_keeps_controls(config):
    review = app()
    css = (APP.parent / '.streamlit/style.css').read_text()
    rule = '\n'.join([
        '.st-key-invoice_upload_panel [data-testid="stFileUploaderDropzoneInstructions"],',
        '.st-key-registry_upload_panel [data-testid="stFileUploaderDropzoneInstructions"] {',
        '    display: none;',
        '}',
    ])
    assert rule in css
    assert any(rule in element.proto.body for element in review.get('html'))
    for key in ('invoice_upload_panel', 'registry_upload_panel'):
        panel = next(p for p in review.get('flex_container') if p.proto.id.endswith('-' + key))
        assert len(panel.file_uploader) == 1
        assert not panel.file_uploader[0].proto.disabled
        assert [c.value for c in panel.caption] == ['Max 200 MB per fil']
    # AppTest does not render CSS. Catch a renamed frontend hook on upgrades;
    # interaction is covered by the upload/replacement tests below.
    static = Path(st.__file__).parent / 'static'
    assert any('stFileUploaderDropzoneInstructions' in p.read_text()
               for p in static.rglob('FileUploader.*.js'))


def test_invoice_upload_keeps_first_sheet_all_rows_and_original_data(config):
    data = invoices(2)
    with BytesIO() as buffer:
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            data.to_excel(writer, sheet_name='Underlag', index=False)
            invoices(5).to_excel(writer, sheet_name='Andra bladet', index=False)
        content = buffer.getvalue()
    review = app()
    review.file_uploader[0].set_value(('underlag.xlsx', content, MIME)).run()
    result = start(review)
    assert result.source_content == content
    pd.testing.assert_frame_equal(result.result.original_data, data,
                                  check_dtype=False, check_column_type=False)
    assert result.result.summary.source_rows == 2
    assert not result.result.supplier_analysis.registry.available
    assert result.result.summary.supplier_unavailable_rows == 2


def test_uploaded_register_date_changes_only_freshness_and_preserves_exports(config):
    content = workbook(invoices())
    register_content = workbook(registry())
    review = app()
    review.file_uploader[0].set_value(('underlag.xlsx', content, MIME)).run()
    review.file_uploader[1].set_value(('koncernavtal.xlsx', register_content, MIME)).run()
    assert not review.exception
    assert [t.value for t in review.text] == ['Aktivt avtalsregister: koncernavtal.xlsx']
    assert review.date_input[0].value is None
    assert 'Utan datum kan registeråldern inte kontrolleras.' in review.caption[-1].value
    review.date_input[0].set_value(date(2026, 6, 1)).run()
    before = start(review)
    first = before.result.supplier_analysis
    assert first.rows.registry_date_check.tolist() == ['AFTER_SNAPSHOT']
    assert first.rows.supplier_match_status.tolist() == ['STRONG_MATCH']
    assert first.contracts.contract_period_status.tolist() == ['PASS']
    review.date_input[0].set_value(date(2026, 7, 1)).run()
    assert 'review' not in review.session_state
    after = start(review)
    second = after.result.supplier_analysis
    assert second.rows.registry_date_check.tolist() == ['ON_OR_BEFORE_SNAPSHOT']
    assert second.rows.supplier_match_status.tolist() == first.rows.supplier_match_status.tolist()
    pd.testing.assert_frame_equal(second.contracts, first.contracts)
    assert after.source_content == content and after.registry_content == register_content
    assert first.rows.registry_date_check.tolist() == ['AFTER_SNAPSHOT']  # Saved analysis remains intact.
    sheets = pd.read_excel(BytesIO(after.downloads['granskning.xlsx']), sheet_name=None)
    assert sheets['Leverantörsmatchning'].supplier_match_status.tolist() == ['STRONG_MATCH']
    assert sheets['Möjliga avtal'].contract_period_status.tolist() == ['PASS']
    assert sheets['Källspårning'].source_name.tolist() == ['underlag.xlsx']


def test_known_default_date_is_preserved_but_not_inherited_by_replacement(config, tmp_path):
    path = tmp_path / 'standard.xlsx'
    path.write_bytes(workbook(registry()))
    config.update(default_registry_path=str(path), default_registry_name='Visningsnamn',
                  registry_snapshot_date='2026-06-01')
    review = app()
    assert [t.value for t in review.text] == ['Aktivt avtalsregister: standard.xlsx']
    assert review.date_input[0].value == date(2026, 6, 1)
    review.date_input[0].set_value(date(2026, 6, 2)).run()
    review.file_uploader[1].set_value(('eget.xlsx', workbook(registry('Egen Leverantör AB')), MIME)).run()
    assert review.date_input[0].value is None
    review.file_uploader[0].set_value(('underlag.xlsx', workbook(invoices()), MIME)).run()
    result = start(review)
    assert result.registry_snapshot_date is None
    assert result.result.supplier_analysis.registry.snapshot_date is None
    assert result.result.supplier_analysis.rows.registry_date_check.tolist() == ['UNKNOWN']
    review.date_input[0].set_value(date(2026, 7, 1)).run()
    # Clearing the native upload uses normal default selection, without a restore button.
    review.file_uploader[1].set_value(None).run()
    assert not review.exception
    assert review.file_uploader[1].value is None
    assert review.date_input[0].value == date(2026, 6, 2)


def test_replacement_retains_each_date_and_old_button_state_cannot_disable_default(config, tmp_path):
    first = workbook(registry())
    second = workbook(registry('Annan Syntetisk Leverantör AB'))
    path = tmp_path / 'standard.xlsx'
    path.write_bytes(first)
    config['default_registry_path'] = str(path)
    review = AppTest.from_file(str(APP), default_timeout=20)
    # A session left open across the UI upgrade must not use obsolete button state.
    review.session_state['registry_enabled'] = False
    review.session_state['registry_upload_version'] = 9
    review.run()
    assert not review.exception
    assert [t.value for t in review.text] == ['Aktivt avtalsregister: standard.xlsx']
    assert not {'Ta bort register', 'Återställ standardregister'} & {b.label for b in review.button}
    review.file_uploader[0].set_value(('underlag.xlsx', workbook(invoices()), MIME)).run()
    review.file_uploader[1].set_value(('ett.xlsx', first, MIME)).run()
    review.date_input[0].set_value(date(2026, 6, 1)).run()
    original = start(review)
    review.file_uploader[1].set_value(('två.xlsx', second, MIME)).run()
    assert 'review' not in review.session_state
    assert [t.value for t in review.text] == ['Aktivt avtalsregister: två.xlsx']
    assert review.date_input[0].value is None
    review.date_input[0].set_value(date(2026, 7, 1)).run()
    review.file_uploader[1].set_value(('ett.xlsx', first, MIME)).run()
    assert review.date_input[0].value == date(2026, 6, 1)
    review.file_uploader[1].set_value(('två.xlsx', second, MIME)).run()
    assert review.date_input[0].value == date(2026, 7, 1)
    replacement = start(review)
    assert replacement.registry_content == second
    assert replacement.registry_source.name == 'två.xlsx'
    assert original.registry_content == first
    assert original.registry_snapshot_date == date(2026, 6, 1)


@pytest.mark.parametrize('content', [b'not excel', workbook(pd.DataFrame({'Fel kolumn': ['x']}))])
def test_unusable_register_has_no_active_filename_or_date_and_retains_validation(config, content):
    review = app()
    review.file_uploader[1].set_value(('felaktigt.xlsx', content, MIME)).run()
    assert not review.exception
    assert not review.date_input
    assert not any('Aktivt avtalsregister:' in t.value for t in review.text)
    assert any('Ladda upp ett giltigt register' in w.value for w in review.warning)
    review.file_uploader[0].set_value(('underlag.xlsx', workbook(invoices()), MIME)).run()
    result = start(review)
    assert not result.result.supplier_analysis.registry.available
    assert result.result.summary.supplier_unavailable_rows == 1


def test_register_validation_is_session_cached_for_ordinary_reruns(config, monkeypatch):
    validate = Mock(wraps=sources.load_contract_source)
    monkeypatch.setattr(sources, 'load_contract_source', validate)
    review = app()
    review.file_uploader[1].set_value(('register.xlsx', workbook(registry()), MIME)).run()
    assert validate.call_count == 1
    review.run()
    review.date_input[0].set_value(date(2026, 6, 1)).run()
    assert not review.exception
    assert validate.call_count == 1
    review.file_uploader[1].set_value(('nytt.xlsx', workbook(registry('Ny Leverantör AB')), MIME)).run()
    assert validate.call_count == 2
    assert review.date_input[0].value is None
