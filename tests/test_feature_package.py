"""Synthetic feature-package acceptance and source-to-export regressions."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
import yaml
from openpyxl import Workbook
from streamlit.testing.v1 import AppTest

from src.filtering.filter_engine import DEFAULT_SETTINGS_PATH, filter_rows
from src.ingestion.registry_source import resolve_registry_source, load_contract_source
from src.supplier_matching.extraction import extract_supplier, normalize_header_text
from src.ui_support import analyze_upload

APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'


def workbook(data):
    buffer = BytesIO()
    data.to_excel(buffer, index=False)
    return buffer.getvalue()


def invoices(count=1):
    return pd.DataFrame({'Vernr': [str(i) for i in range(1, count + 1)],
                         'Vrad': [1] * count, 'Verdatum': ['2026-06-15'] * count,
                         'Utfall': [100] * count, 'Konto': ['4000'] * count,
                         'Vertyp': ['X'] * count,
                         'Huvudtext': ['Syntetisk Leverantör AB Slutk123'] * count})


def registry(name='Syntetisk Leverantör AB'):
    return pd.DataFrame({'Leverantör': [name], 'Organisationsnummer': ['123'],
                         'Avtals-ID': ['Avtal-001'], 'Startdatum': ['2026-01-01'],
                         'Slutdatum': ['2026-12-31']})


def settings(tmp_path, **matching):
    config = yaml.safe_load(DEFAULT_SETTINGS_PATH.read_text())
    config['supplier_matching'].update({'default_registry_path': None, **matching})
    target = tmp_path / 'settings.yaml'
    target.write_text(yaml.safe_dump(config, allow_unicode=True))
    return target


@pytest.mark.parametrize('text, cleaned, extracted', [
    ('Apoteket AB Slutk12345', 'Apoteket AB', 'Apoteket AB'),
    ('  Apoteket   AB sLuTk 123 ', 'Apoteket AB', 'Apoteket   AB'),
    ('Apoteket AB Slutk123 Slutk 456', 'Apoteket AB', 'Apoteket AB'),
    ('Apoteket AB Slutk123 extra text', 'Apoteket AB extra text', 'Apoteket AB'),
    ('Apoteket AB Prelb 123', 'Apoteket AB Prelb 123', 'Apoteket AB'),
    ('Slutkund AB', 'Slutkund AB', None),
    ('Apoteket AB Slutk123abc', 'Apoteket AB Slutk123abc', None),
    ('Slutk123', '', None),
    (None, None, None), (pd.NA, None, None),
])
def test_numbered_slutk_normalization(text, cleaned, extracted):
    assert normalize_header_text(text) == cleaned
    assert extract_supplier(text) == extracted


@pytest.mark.parametrize('text, rule', [
    (' FÖRSÖRJNINGSFÖRVALTNING Slutk123 ', 'Försörjningsförvaltning'),
    ('försörjnings förvaltning Prelb 1', 'Försörjningsförvaltning'),
    (' Fastighetstöd  Slutk 12', 'Fastighetstöd'),
    ('fastighet stöd', 'Fastighetstöd'),
    (' MALL ', 'mall'), ('mall Slutk1', 'mall'),
    ('Small AB Slutk1', None), ('Mallservice AB Slutk1', None),
    ('Fastighetstöd AB Slutk1', None), ('Extern AB mall Slutk1', None),
    ('Försörjningsförvaltning annan organisation', None),
])
def test_internal_supplier_exclusions_are_exact_and_traceable(text, rule):
    data = pd.DataFrame({'verification_id': ['1'], 'account': ['4000'],
                         'verification_type': ['X'], 'header_text': [text]}, index=[18])
    before = data.copy(deep=True)
    result = filter_rows(data)
    assert result.internal_supplier_count == int(rule is not None)
    if rule:
        assert result.excluded_data.index.tolist() == [18]
        assert result.reasons == (f'Exkluderad – Intern leverantör: {rule}',)
        assert result.rule_details['internal_supplier'][rule] == [0]
    else:
        assert result.cleaned_data.index.tolist() == [18]
    pd.testing.assert_frame_equal(data, before)


def test_sampling_counts_export_and_reproduction_with_exclusions_and_ungrouped_rows():
    data = invoices(104)
    data['Huvudtext'] = [f'Syntetisk leverantör {i} AB Prelb 1' for i in range(104)]
    data.loc[:2, 'Huvudtext'] = ['mall', 'Fastighetstöd', 'Försörjningsförvaltning']
    data.loc[0, 'Konto'] = '7698'  # Overlapping reasons still describe one occurrence.
    data.loc[103, 'Vernr'] = None
    content = workbook(data)
    first = analyze_upload(content, registry_mode='disabled')
    second = analyze_upload(content, registry_mode='disabled')
    s = first.result.summary
    assert (s.source_rows, s.included_rows, s.excluded_rows, s.ungrouped_rows) == (104, 101, 3, 1)
    assert (s.eligible_verifications, s.sample_interval, s.sampled_verifications, s.sampled_rows) == (100, 20, 5, 5)
    assert s.included_rows + s.excluded_rows == s.source_rows
    assert s.supplier_unavailable_rows == s.uncertain_supplier_rows == 101
    assert sum(s.exclusion_counts.values()) == 4
    assert [v.verification_id for v in first.result.manual_sample] == ['23', '43', '63', '83', '103']
    pd.testing.assert_frame_equal(first.result.sampling_evidence, second.result.sampling_evidence)
    with pd.ExcelFile(BytesIO(first.downloads['manual_sample.xlsx'])) as book:
        rows = pd.read_excel(book, 'rows')
        assert rows.verification_id.tolist() == [23, 43, 63, 83, 103]
        positions = pd.read_excel(book, 'Urvalspositioner')
        assert positions.population_position.tolist() == [20, 40, 60, 80, 100]
        assert positions.source_row_position.tolist() == [22, 42, 62, 82, 102]
        assert pd.read_excel(book, 'Urvalsmetod').iloc[0]['Antal verifikationer i populationen'] == 100
    excluded = pd.read_excel(BytesIO(first.downloads['bortfiltrerade.xlsx']), 'Bortfiltrerade')
    assert len(excluded) == 3
    assert excluded['Exkluderingsorsak'].str.contains('Intern leverantör').all()
    assert first.source_content == content


def test_uncertain_export_has_all_non_strong_occurrences_and_no_excluded_rows():
    data = invoices(6)
    data['Vernr'] = ['1', '1', '1', None, '2', '3']
    data['Huvudtext'] = ['Syntetisk Leverantör AB Slutk123', 'Input interiör Slutk 2',
                         'Okänd Testverksamhet AB Slutk3', 'Utan markör', 'mall', None]
    contracts = pd.concat([registry(),
        pd.DataFrame({'Leverantör': ['Input interiör AB', 'Input interiör Göteborg AB'],
                       'Organisationsnummer': ['2', '3']})], ignore_index=True)
    review = analyze_upload(workbook(data), registry_content=workbook(contracts),
                             registry_name='synthetic-register.xlsx')
    with pd.ExcelFile(BytesIO(review.downloads['uncertain_suppliers.xlsx'])) as book:
        rows = pd.read_excel(book, 'rows')
        assert rows.source_row_position.tolist() == [1, 2, 3, 5]
        assert rows.supplier_match_status.tolist() == ['AMBIGUOUS_MATCH', 'NO_MATCH',
                                                       'SUPPLIER_NOT_IDENTIFIED', 'SUPPLIER_NOT_IDENTIFIED']
        assert rows.header_text.iloc[0] == 'Input interiör'
        assert review.result.standardized_data.header_text.iloc[1] == data.Huvudtext.iloc[1]
        assert rows.header_text_normalized.iloc[0] == 'Input interiör'
        assert rows.supplier_match_reason.notna().all()
        info = pd.read_excel(book, 'Registerinformation')
        assert info.registry_name.iloc[0] == 'synthetic-register.xlsx'
        assert info.registry_sha256.iloc[0] == review.registry_source.sha256
        assert set(pd.read_excel(book, 'Leverantörskandidater').source_row_position) <= {1, 2, 3, 5}
    assert review.result.summary.strong_supplier_rows == 1
    assert review.result.summary.uncertain_supplier_rows == 4


@pytest.mark.parametrize('content', [None, b'unreadable register'])
def test_unavailable_register_exports_review_population_without_fabricated_no_match(content):
    review = analyze_upload(workbook(invoices(2)), registry_mode='uploaded', registry_content=content)
    rows = pd.read_excel(BytesIO(review.downloads['uncertain_suppliers.xlsx']), 'rows')
    assert rows.source_row_position.tolist() == [0, 1]
    assert rows.supplier_match_status.isna().all()
    assert rows.supplier_check_status.tolist() == ['NOT_CHECKED', 'NOT_CHECKED']
    assert rows.supplier_match_reason.notna().all()
    assert rows.header_text_normalized.tolist() == ['Syntetisk Leverantör AB'] * 2


def test_default_uploaded_disabled_and_restored_registry_sources(tmp_path):
    default = tmp_path / 'standard.xlsx'
    content = workbook(registry())
    default.write_bytes(content)
    mtime = default.stat().st_mtime_ns
    config_path = settings(tmp_path)
    config = yaml.safe_load(config_path.read_text())
    config['supplier_matching']['default_registry_path'] = str(default)
    config_path.write_text(yaml.safe_dump(config))
    source = resolve_registry_source(settings_path=config_path)
    assert (source.kind, source.name, source.content) == ('default', 'standard.xlsx', content)
    result = analyze_upload(workbook(invoices()), settings_path=config_path)
    assert result.result.summary.strong_supplier_rows == 1
    custom = workbook(registry('Annan Organisation AB'))
    replaced = analyze_upload(workbook(invoices()), settings_path=config_path,
                               registry_content=custom, registry_name='eget.xlsx')
    assert replaced.registry_source.kind == 'uploaded'
    assert replaced.registry_source.name == 'eget.xlsx'
    assert replaced.result.summary.strong_supplier_rows == 0
    disabled = resolve_registry_source(settings_path=config_path, mode='disabled', uploaded_content=custom)
    assert disabled.kind == 'disabled' and disabled.content is None
    assert resolve_registry_source(settings_path=config_path) == source
    assert default.read_bytes() == content and default.stat().st_mtime_ns == mtime
    # Refiltering a completed run reuses its exact snapshot, even if the local file changes.
    default.write_bytes(custom)
    repeated = analyze_upload(result.source_content, settings_path=config_path,
                               registry_source=result.registry_source, excluded_verification_types=[])
    assert repeated.registry_source == source
    assert repeated.result.summary.strong_supplier_rows == 1


def test_missing_default_register_is_unavailable_without_a_replacement(tmp_path):
    config_path = settings(tmp_path)
    source = resolve_registry_source(settings_path=config_path)
    assert source.kind == 'default' and source.content is None and source.issue
    loaded = load_contract_source(source, config=yaml.safe_load(config_path.read_text())['supplier_matching'])
    assert not loaded.available


def test_default_csv_format_is_independent_of_its_display_name(tmp_path):
    path = tmp_path / 'register.csv'
    registry().to_csv(path, sep=';', index=False, encoding='utf-8-sig')
    config_path = settings(tmp_path, default_registry_path=str(path), default_registry_name='Standardavtal')
    source = resolve_registry_source(settings_path=config_path)
    assert source.name == 'Standardavtal' and source.format_suffix == '.csv'
    loaded = load_contract_source(source, config=yaml.safe_load(config_path.read_text())['supplier_matching'])
    assert loaded.available
    assert loaded.suppliers[0].names == ('Syntetisk Leverantör AB',)


def test_export_source_locator_with_header_offset_and_repeated_identifiers():
    book = Workbook()
    sheet = book.active
    sheet.title = 'Syntetiskt underlag'
    sheet.append(['Metadata'])
    sheet.append(['Vernr', 'Vrad', 'Verdatum', 'Utfall', 'Konto', 'Vertyp', 'Huvudtext'])
    sheet.append(['001', 1, '2026-06-15', 10, '4000', 'X', 'mall'])
    sheet.append(['001', 1, '2026-06-15', 10, '4000', 'X', '=literal'])
    sheet.append([None, None, '2026-06-15', 10, '4000', 'X', 'Unidentified'])
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    content = buffer.getvalue()
    review = analyze_upload(content, source_name='källa.xlsx', registry_mode='disabled')
    for name, expected in [('granskning.xlsx', [1, 2]), ('bortfiltrerade.xlsx', [0]),
                           ('samlad_kontrollfil.xlsx', [1, 2, 0]), ('uncertain_suppliers.xlsx', [1, 2])]:
        trace = pd.read_excel(BytesIO(review.downloads[name]), 'Källspårning')
        assert trace.source_row_position.tolist() == expected
        assert trace.source_excel_row.tolist() == [p + 3 for p in expected]
        assert trace.source_name.tolist() == ['källa.xlsx'] * len(expected)
        assert trace.source_sha256.tolist() == [sha256(content).hexdigest()] * len(expected)
        assert trace.source_sheet.tolist() == ['Syntetiskt underlag'] * len(expected)
        if name == 'samlad_kontrollfil.xlsx':
            assert trace.export_sheet.tolist() == ['Granskning', 'Granskning', 'Bortfiltrerade']
            assert trace.export_row.tolist() == [2, 3, 2]


def test_dashboard_sampling_and_register_remove_restore():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    app.file_uploader[0].set_value(('synthetic.xlsx', workbook(invoices(100)), mime)).run()
    app.file_uploader[1].set_value(('custom.xlsx', workbook(registry()), mime)).run()
    app.button[0].click().run()
    assert not app.exception
    assert {m.label: m.value for m in app.metric} == {
        'Källpopulation · rader': '100', 'Kvarvarande · rader': '100',
        'Exkluderade · rader': '0', 'Flaggade · verifikationer': '0',
        'Manuellt urval · verifikationer': '1',
        'Verifikationer i urvalspopulationen': '100', 'Ordinarie urvalsintervall': 'Var 20:e',
        'Valda verifikationer': '1', 'Rader i stickprovet': '1'}
    assert any('1 av önskade 5' in warning.value for warning in app.warning)
    assert app.session_state['review'].registry_source.kind == 'uploaded'
    next(b for b in app.button if b.label == 'Ta bort register').click().run()
    assert 'review' not in app.session_state
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['review'].registry_source.kind == 'disabled'
    assert app.session_state['review'].result.summary.supplier_unavailable_rows == 100
    next(b for b in app.button if b.label == 'Återställ standardregister').click().run()
    assert not app.exception
    assert app.file_uploader[1].value is None
    app.button[0].click().run()
    assert app.session_state['review'].registry_source.kind == 'default'
    next(b for b in app.button if b.label == 'Ta bort register').click().run()
    app.file_uploader[1].set_value(('replacement.xlsx', workbook(registry()), mime)).run()
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['review'].registry_source.kind == 'uploaded'
    assert app.session_state['review'].registry_source.name == 'replacement.xlsx'
