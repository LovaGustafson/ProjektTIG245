"""UI interactions and deferred exports preserve the same synthetic run evidence."""
from copy import deepcopy
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
import yaml
from streamlit.testing.v1 import AppTest

from src import pipeline
from src.output import report_generator
from src.ui_overview_details import verification_details
from src.ui_support import analyze_upload, DeferredDownloads
from tests.test_feature_package import invoices, registry, workbook, settings
from tests.test_ui_overview_details import overview_app, expander, evidence_table

APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'


def assert_same_analysis(left, right):
    for field in ('original_data', 'standardized_data', 'ungrouped_data', 'sampling_evidence', 'supplier_view'):
        pd.testing.assert_frame_equal(getattr(left, field), getattr(right, field))
    for field in ('cleaned_data', 'excluded_data'):
        pd.testing.assert_frame_equal(getattr(left.filtering, field), getattr(right.filtering, field))
    assert left.filtering.reasons == right.filtering.reasons
    assert left.filtering.rule_details == right.filtering.rule_details
    assert left.validation == right.validation
    assert left.summary == right.summary
    assert left.source_context == right.source_context
    for field in ('rows', 'candidates', 'contracts'):
        pd.testing.assert_frame_equal(getattr(left.supplier_analysis, field), getattr(right.supplier_analysis, field))
    for field in ('decisions', 'identity_rows'):
        pd.testing.assert_frame_equal(getattr(left.sampling_result, field), getattr(right.sampling_result, field))
    for old, new in zip(left.verifications + left.manual_sample, right.verifications + right.manual_sample, strict=True):
        assert old.verification_id == new.verification_id
        pd.testing.assert_frame_equal(old.rows, new.rows)
    for old, new in zip(left.detection_results, right.detection_results, strict=True):
        assert old.verification_id == new.verification_id
        assert old.checks == new.checks
        assert old.executed_rules == new.executed_rules
        assert old.disabled_rules == new.disabled_rules


def assert_same_workbook(left, right):
    old = pd.read_excel(BytesIO(left), sheet_name=None, dtype=object)
    new = pd.read_excel(BytesIO(right), sheet_name=None, dtype=object)
    assert list(old) == list(new)
    for sheet in old:
        pd.testing.assert_frame_equal(old[sheet], new[sheet])


@pytest.mark.parametrize('mode', ['matching', 'unavailable', 'all_excluded'])
def test_deferred_export_is_identical_and_serializes_only_requested_file(mode):
    data = invoices(43).astype(object)
    data.loc[0, ['Konto', 'Vertyp', 'Huvudtext']] = ['7698', 'FBFM', 'mall']
    data.loc[1, 'Vernr'] = None
    data.loc[3, 'Vernr'] = data.loc[2, 'Vernr']
    data.loc[4, 'Utfall'] = 'invalid'
    data.loc[5, 'Huvudtext'] = 'Input interiör Slutk2'
    data.loc[6, 'Verdatum'] = '2027-01-01'
    contracts = pd.concat([registry(), pd.DataFrame({
        'Leverantör': ['Input interiör AB', 'Input interiör Göteborg AB'],
        'Organisationsnummer': ['2', '3']})], ignore_index=True)
    options = dict(registry_content=None if mode == 'unavailable' else workbook(contracts),
                   registry_mode='disabled' if mode == 'unavailable' else 'uploaded',
                   excluded_verification_types=['X', 'FBFM'] if mode == 'all_excluded' else ['FBFM'])
    content = workbook(data)
    eager = analyze_upload(content, **options)
    with patch.object(report_generator, '_workbook', wraps=report_generator._workbook) as serialize:
        deferred = analyze_upload(content, defer_downloads=True, **options)
        assert serialize.call_count == 0
        assert_same_analysis(eager.result, deferred.result)
        for number, filename in enumerate(eager.downloads, 1):
            actual = deferred.downloads[filename]
            assert serialize.call_count == number
            assert_same_workbook(eager.downloads[filename], actual)
            assert deferred.downloads[filename] is actual
            assert serialize.call_count == number


def test_unreadable_register_preserves_exact_recorded_diagnostic_in_deferred_export():
    # The recorded error contains this run's random temporary path; do not
    # replace or normalize it when serializing the same completed evidence.
    eager = analyze_upload(workbook(invoices(2)), registry_content=b'invalid')
    downloads = DeferredDownloads(eager.result)
    for filename in ('granskning.xlsx', 'uncertain_suppliers.xlsx'):
        assert_same_workbook(downloads[filename], eager.downloads[filename])


def test_downloads_are_bound_to_result_snapshot_and_new_inputs(tmp_path):
    config_path = settings(tmp_path)
    config = yaml.safe_load(config_path.read_text())
    content = workbook(invoices(3))
    initial = dict(registry_content=workbook(registry()), registry_name='synthetic.xlsx',
                   settings_path=config_path, source_name='source.xlsx')
    original = analyze_upload(content, defer_downloads=True, **initial)
    expected = analyze_upload(content, **initial)
    # Even later in-memory display mutations cannot change a pending download.
    original.result.original_data.iloc[0, 0] = 'changed display copy'
    config['manual_sample_interval'] = 1
    config_path.write_text(yaml.safe_dump(config))
    variants = [
        (content, {'excluded_verification_types': ['X']}),
        (workbook(invoices(1)), {}),
        (content, {'registry_content': workbook(registry('Different AB'))}),
        (content, {'registry_snapshot_date': date(2026, 1, 1)}),
        (content, {}),  # Changed settings at the same path.
        (content, {'registry_content': None, 'registry_mode': 'disabled'}),
    ]
    for source, changes in variants:
        options = {**initial, **changes}
        fresh = analyze_upload(source, defer_downloads=True, **options)
        baseline = analyze_upload(source, **options)
        assert fresh.downloads is not original.downloads
        assert_same_analysis(fresh.result, baseline.result)
        assert_same_workbook(fresh.downloads['samlad_kontrollfil.xlsx'], baseline.downloads['samlad_kontrollfil.xlsx'])
    assert_same_workbook(original.downloads['granskning.xlsx'], expected.downloads['granskning.xlsx'])



def test_manual_supplier_names_use_source_links_and_keep_multiple_or_missing_names(tmp_path):
    data = invoices(5)
    data['Vernr'] = ['same', 'same', 'multi', 'multi', 'missing']
    data['Huvudtext'] = ['Alpha AB Slutk1', 'ALPHA Aktiebolag Slutk2',
                        'Beta AB Slutk3', 'Gamma AB Slutk4', 'Ingen markör']
    config_path = settings(tmp_path)
    config = yaml.safe_load(config_path.read_text())
    config['manual_sample_interval'] = 1
    config_path.write_text(yaml.safe_dump(config))
    upload = analyze_upload(workbook(data), settings_path=config_path, registry_mode='disabled', defer_downloads=True)
    groups, _ = verification_details(upload.result)
    assert groups.supplier.tolist() == ['Flera leverantörsnamn: Alpha AB; ALPHA Aktiebolag',
                                       'Flera leverantörsnamn: Beta AB; Gamma AB', 'Leverantör ej identifierad']
    selected, _ = verification_details(upload.result, 'selected')
    assert selected.verification_id.tolist() == ['same']
    assert selected.source_row_positions.tolist() == [[0, 1]]
    app = AppTest.from_file(str(APP), default_timeout=20)
    app.session_state['review'] = upload
    app.run()
    assert not app.exception
    assert app.tabs[4].dataframe[0].value.supplier.tolist() == selected.supplier.tolist()
    detail = expander(app, 'Utvalda ·')
    assert evidence_table(detail, 'supplier').supplier.tolist() == selected.supplier.tolist()



def test_filter_rerun_and_home_without_generating_exports():
    data = invoices(23)
    data.loc[0, 'Vertyp'] = 'FBFM'
    upload = analyze_upload(workbook(data), registry_mode='disabled', defer_downloads=True)
    app = AppTest.from_file(str(APP), default_timeout=20)
    app.session_state['review'] = upload
    with patch.object(report_generator, '_workbook', side_effect=AssertionError('no download requested')):
        app.run()
        assert not app.exception
        assert 'Exkluderingsregler' in [s.value for s in app.sidebar.subheader]
        assert not any('MoSCoW' in s.value for s in app.sidebar.subheader)
        app.button(key='kpi_review').click().run()
        assert not app.exception
        app.button(key='home').click().run()
        assert not app.exception
        app.multiselect(key='excluded_types').set_value(['X']).run()
        assert not app.exception
        changed = app.session_state['review']
        assert isinstance(changed.downloads, DeferredDownloads)
        assert not changed.downloads._bytes
        assert not expander(app, 'Kvarvarande ·').proto.expanded
        assert changed.result.filtering.cleaned_data.index.tolist() == [0]
    baseline = analyze_upload(upload.source_content, registry_source=upload.registry_source,
                              excluded_verification_types=['X'])
    assert_same_analysis(changed.result, baseline.result)
    assert_same_workbook(changed.downloads['manual_sample.xlsx'], baseline.downloads['manual_sample.xlsx'])

