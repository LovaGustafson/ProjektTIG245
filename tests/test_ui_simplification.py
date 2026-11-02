"""First-time view stays concise while synthetic evidence remains inspectable."""
from copy import deepcopy
from datetime import date
import json

import pytest
from streamlit.testing.v1 import AppTest

from src.ui_support import analyze_upload
from tests.test_feature_package import invoices, workbook, registry, settings
from src.supplier_matching.contract_period import ACTIVE, NOT_STARTED, ENDED, UNVERIFIABLE
from tests.test_ui_sampling import APP, population
from tests.test_ui_ux import assert_same_analysis
from tests.test_upload_panel import config  # Shared fixture disables any local default register.
from tests.test_priority2 import rule, write_rules


def visible_elements(block):
    """Ignore descendants of initially collapsed sections, as a new user sees them."""
    for element in block.children.values():
        if element.type == 'expander' and not element.proto.expanded:
            continue
        yield element
        if hasattr(element, 'children'):
            yield from visible_elements(element)


def visible_text(block):
    return '\n'.join(str(element.value) for element in visible_elements(block)
                     if element.type in ('caption', 'text', 'markdown', 'subheader', 'info', 'warning'))


def test_uploads_show_native_filenames_and_one_format_size_hint(config):
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    app.file_uploader[0].set_value(('underlag.xlsx', workbook(population(1)), mime)).run()
    app.file_uploader[1].set_value(('avtal.xlsx', workbook(registry()), mime)).run()
    assert not app.exception
    assert [u.value.name for u in app.file_uploader] == ['underlag.xlsx', 'avtal.xlsx']
    text = visible_text(app.sidebar)
    assert text.count('Excel (.xlsx)') == text.count('Max 200 MB per fil') == 1
    assert 'Uppladdat fakturaunderlag:' not in text and 'Aktivt avtalsregister:' not in text
    assert 'Registervarningar' in text  # Actionable register issues are still visible.
    date = next(e for e in app.sidebar.expander if e.label == 'Registerdatum (valfritt)')
    assert not date.proto.expanded
    assert date.date_input[0].value is None
    assert 'registeråldern inte kontrolleras' in date.date_input[0].proto.help
    assert not any(e.type == 'date_input' for e in visible_elements(app.sidebar))


@pytest.mark.parametrize('method', ['systematic', 'randomized'])
def test_manual_first_view_has_one_summary_and_audit_details_stay_available(config, tmp_path, monkeypatch, method):
    monkeypatch.setattr('src.ui_support.new_sample_seed', lambda previous=None: 123)
    data = population(44)
    data.loc[20, ['Vernr', 'Huvudtext']] = data.loc[19, ['Vernr', 'Huvudtext']]
    review = analyze_upload(workbook(data), registry_mode='disabled',
                            settings_path=settings(tmp_path), defer_downloads=True)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state['review'] = review
    app.run()
    if method == 'randomized':
        app.radio(key='manual_sample_method').set_value(method).run()
    assert not app.exception
    current = app.session_state['review']
    before = deepcopy(current.result)
    manual = next(tab for tab in app.tabs if tab.label == 'Manuellt stickprov')
    metrics = [e for e in visible_elements(manual) if e.type == 'metric']
    summary = current.result.summary
    assert [(e.label, e.value) for e in metrics] == [
        ('Verifikationer att välja från', str(summary.eligible_verifications)),
        ('Valda verifikationer', str(summary.sampled_verifications)),
        ('Rader i stickprovet', str(summary.sampled_rows)),
    ]
    text = visible_text(manual)
    assert 'En verifikation är en grupp bokföringsrader.' in text
    assert 'Interna leverantörer kan ingå.' in text
    assert all(value not in text for value in (
        'Seed:', 'Genereringstidpunkt', 'leverantörsnyckel', 'STRONG_MATCH',
        'Aktiv urvalsmetod:', 'population //', 'Granskningsstatus registreras inte',
    ))
    assert len([e for e in visible_elements(manual) if e.type == 'dataframe']) == 1
    assert not any(e.type == 'vega_lite_chart' for e in visible_elements(manual))
    audit = next(e for e in manual.expander if e.label == 'Urvalsbeslut, klassificering och källspårning')
    evidence = next(e for e in manual.expander if e.label == 'Så gjordes urvalet')
    rows = next(e for e in manual.expander if e.label.startswith('Visa stickprovets '))
    assert not audit.proto.expanded and not evidence.proto.expanded and not rows.proto.expanded
    assert any(c.value.startswith(f'Planerat antal: {current.result.sampling_result.target_size} ') for c in audit.caption)
    assert any(c.value.startswith('Genereringstidpunkt') for c in audit.caption)
    if method == 'randomized':
        assert any(t.value == 'Seed: 123' for t in audit.text)
    assert {m.label for m in audit.metric} == {
        'Bekräftat interna', 'Bekräftat externa', 'Oklassificerade',
        'Bortval på grund av kvotbegränsning', 'Bortval på grund av klassificeringskonflikter',
    }
    assert len(rows.dataframe[0].value) == summary.sampled_rows
    assert not any(c.value.startswith(('Visar ', 'Aktiva filter:')) for c in rows.caption)
    selected = next(table for table in manual.dataframe
                    if table.value.columns.tolist() == ['verification_id', 'supplier', 'supplier_classification'])
    assert json.loads(selected.proto.columns)['supplier_classification']['hidden'] is True
    exclusions = next(e for e in app.sidebar.expander if e.label == 'Exkluderingsregler')
    assert not exclusions.proto.expanded
    assert not any(e.type == 'multiselect' for e in visible_elements(app.sidebar))
    app.run()
    assert not app.exception
    assert app.session_state['review'] is current
    assert_same_analysis(before, current.result)
    assert not current.downloads._bytes


@pytest.mark.parametrize('snapshot, invalid_date, unknown_count', [
    (None, True, 3), (date(2026, 6, 1), True, 1), (date(2026, 6, 1), False, 0),
])
def test_supplier_first_view_separates_register_age_from_contract_periods(config, tmp_path, snapshot, invalid_date, unknown_count):
    data = invoices(3)
    if invalid_date:
        data.loc[2, 'Verdatum'] = 'ogiltigt datum'
    review = analyze_upload(workbook(data), registry_content=workbook(registry()),
        registry_mode='uploaded', registry_snapshot_date=snapshot,
        settings_path=settings(tmp_path), defer_downloads=True)
    before = deepcopy(review.result)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    supplier = next(tab for tab in app.tabs if tab.label == 'Leverantörsmatchning')
    text = visible_text(supplier)
    assert 'En namnträff bekräftar inte juridisk identitet eller att köpet omfattas av avtal.' in text
    assert 'Markera en rad för att se detaljer och eventuella valideringsfel.' in text
    assert all(value not in text for value in (
        'Matchningsscore är ett tekniskt mått', 'första registerkandidaten',
        'Avtalsperioder vid verifikationsdatum', 'avtalsjämförelser',
        '0 källrader', 'supplier_view_rules', 'Alla kvarvarande rader med ursprungliga',
    ))
    warnings = [e.value for e in visible_elements(supplier) if e.type == 'warning']
    if unknown_count:
        assert len(warnings) == 1
        assert f'för {unknown_count} rader' in warnings[0]
        assert 'registrets ålder' in warnings[0].lower()
        assert 'kunde inte datumkontrolleras' not in warnings[0]
        assert ('Registerutdragets datum är okänt' in warnings[0]) == (snapshot is None)
        assert ('datumet i underlaget saknas eller är ogiltigt' in warnings[0]) == (snapshot is not None)
    else:
        assert not warnings
    assert len([e for e in visible_elements(supplier) if e.type == 'dataframe']) == 1
    assert [b.key for b in supplier.button if b.key.startswith('supplier_')] == [
        'supplier_all', 'supplier_STRONG_MATCH', 'supplier_AMBIGUOUS_MATCH',
        'supplier_NO_MATCH', 'supplier_SUPPLIER_NOT_IDENTIFIED', 'supplier_date_warning',
    ]
    help_section = next(e for e in supplier.expander if e.label == 'Så fungerar leverantörsmatchningen')
    assert not help_section.proto.expanded
    assert any('Matchningsscore är ett tekniskt mått' in c.value for c in help_section.caption)
    assert any('första registerkandidaten' in c.value for c in help_section.caption)
    counts = before.supplier_analysis.contracts.contract_period_result.value_counts()
    assert [t.value for t in help_section.text] == [
        f'{label}: {int(counts.get(label, 0))} avtalsjämförelser'
        for label in (ACTIVE, NOT_STARTED, ENDED, UNVERIFIABLE)
    ]
    # An unknown extract date never makes otherwise usable contract dates unavailable.
    assert counts.get(ACTIVE, 0) == (2 if invalid_date else 3)
    assert counts.get(UNVERIFIABLE, 0) == int(invalid_date)
    scope = next(e for e in supplier.expander if e.label == 'Om leverantörsöversikten')
    assert not scope.proto.expanded
    assert any('0 källrader' in c.value for c in scope.caption)
    assert_same_analysis(before, review.result)
    assert not review.downloads._bytes


@pytest.mark.parametrize('conflict', [False, True])
def test_supplier_scope_keeps_actual_exclusions_and_conflicts_visible(config, tmp_path, conflict):
    path = settings(tmp_path)
    rules = [rule()]
    if conflict:
        rules.append({**rule(), 'id': 'synthetic-conflict', 'classification': 'EXTERNAL'})
    write_rules(path, rules)
    review = analyze_upload(workbook(invoices(1).assign(Huvudtext='Synthetic AB Prelb 1')),
                            registry_mode='disabled', settings_path=path, defer_downloads=True)
    before = deepcopy(review.result)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    supplier = next(tab for tab in app.tabs if tab.label == 'Leverantörsmatchning')
    text = visible_text(supplier)
    if conflict:
        assert 'Motstridiga leverantörsvyregler finns.' in text
        assert 'Rader som inte räknas i leverantörsöversikten:' not in text
    else:
        assert 'Rader som inte räknas i leverantörsöversikten: 1.' in text
        assert 'De finns kvar i granskningsunderlaget och exporterna.' in text
    scope = next(e for e in supplier.expander if e.label == 'Om leverantörsöversikten')
    assert not scope.proto.expanded
    # Hiding the zero-state explanation never hides an occurrence from review.
    assert len(supplier.dataframe[0].value) == 1
    assert_same_analysis(before, review.result)
