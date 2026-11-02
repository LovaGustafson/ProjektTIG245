"""First-time view stays concise while synthetic evidence remains inspectable."""
from copy import deepcopy
import json

import pytest
from streamlit.testing.v1 import AppTest

from src.ui_support import analyze_upload
from tests.test_feature_package import workbook, registry, settings
from tests.test_ui_sampling import APP, population
from tests.test_ui_ux import assert_same_analysis
from tests.test_upload_panel import config  # Shared fixture disables any local default register.


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
