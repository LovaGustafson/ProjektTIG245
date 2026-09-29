"""Dashboard acceptance using synthetic pipeline evidence and real exports."""
from io import BytesIO
import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.models.result import CheckResult, CheckStatus
from src.models.supplier import SupplierMatchStatus
from src.pipeline import run_pipeline
from src.ui_run_summary import dashboard_tables
from src.ui_support import analyze_upload
from tests.test_feature_package import invoices, registry, workbook

APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'


def counts(table):
    return table.set_index('Status')['Antal'].to_dict()


def test_charts_reconcile_source_filters_sampling_and_export():
    data = invoices(46)
    data.loc[0, ['Konto', 'Vertyp', 'Huvudtext']] = ['7698', 'FBFM', 'mall']
    data.loc[1, 'Konto'] = '7699'
    data.loc[2, 'Vernr'] = None  # Retained, but not a sampling unit.
    data.loc[44, 'Vernr'] = data.loc[43, 'Vernr']  # One group with two occurrences.
    data.loc[45, :] = None  # Structural row, inside the supplied table.
    data = pd.concat([data, invoices(1).assign(Vernr='last')], ignore_index=True)
    review = analyze_upload(workbook(data), registry_mode='disabled')
    result = review.result
    charts = dashboard_tables(result)
    s = result.summary
    assert counts(charts['population']) == {'included': s.included_rows, 'excluded': s.excluded_rows}
    assert charts['population'].Antal.sum() == len(result.original_data) == s.source_rows
    actual_rules = {f'{rule}: {value}': len(positions)
                    for rule, values in result.filtering.rule_details.items()
                    for value, positions in values.items() if positions}
    assert counts(charts['exclusions']) == actual_rules == s.exclusion_counts
    assert charts['exclusions'].Antal.sum() > s.excluded_rows
    assert any(key.startswith('structural_row:') for key in actual_rules)
    assert any(key.startswith('internal_supplier:') for key in actual_rules)
    assert s.ungrouped_rows == 1
    assert charts['sample'].Antal.sum() == len(result.verifications)
    assert counts(charts['sample'])['selected'] == len(result.manual_sample) == 2
    assert s.sampled_rows == sum(len(v.rows) for v in result.manual_sample)
    exported = pd.read_excel(BytesIO(review.downloads['manual_sample.xlsx']), 'Körningsöversikt')
    exported_counts = dict(exported.itertuples(index=False, name=None))
    assert exported_counts['Inlästa källrader'] == charts['population'].Antal.sum()
    assert exported_counts['Exkluderade rader'] == counts(charts['population'])['excluded']
    assert exported_counts['Verifikationer för manuell granskning'] == counts(charts['sample'])['selected']


def test_supplier_statuses_and_contract_comparison_units_are_preserved():
    data = invoices(5)
    data['Huvudtext'] = ['Syntetisk Leverantör AB Slutk1', 'Input interiör Slutk2',
                         'Okänd Testverksamhet AB Slutk3', 'Utan markör', 'mall']
    contracts = pd.concat([
        registry(), registry().assign(**{'Avtals-ID': 'second', 'Slutdatum': '2026-02-01'}),
        pd.DataFrame({'Leverantör': ['Input interiör AB', 'Input interiör Göteborg AB'],
                      'Organisationsnummer': ['2', '3']}),
    ], ignore_index=True)
    review = analyze_upload(workbook(data), registry_content=workbook(contracts), registry_mode='uploaded')
    result = review.result
    before = result.supplier_analysis.rows.copy(deep=True)
    charts = dashboard_tables(result)
    assert counts(charts['suppliers']) == {status.value: 1 for status in SupplierMatchStatus}
    assert charts['suppliers'].Antal.sum() == result.summary.included_rows == 4
    assert counts(charts['contracts']) == {'PASS': 1, 'FLAGGED': 1, 'ERROR': 0, 'NOT_CHECKED': 2}
    assert charts['contracts'].Antal.sum() == len(result.supplier_analysis.contracts)
    pd.testing.assert_frame_equal(result.supplier_analysis.rows, before)


def test_all_check_statuses_remain_separate_without_inflating_flags(tmp_path):
    source = tmp_path / 'synthetic.xlsx'
    source.write_bytes(workbook(invoices(2)))

    def synthetic_rule(v, context):
        statuses = list(CheckStatus) if v.verification_id == '1' else [CheckStatus.NOT_CHECKED]
        return [CheckResult(v.verification_id, 'synthetic', status, f'Test: {status}') for status in statuses]

    result = run_pipeline(source, output_dir=tmp_path / 'reports', use_default_registry=False,
                          rules={'synthetic': synthetic_rule})
    assert counts(dashboard_tables(result)['checks']) == {'PASS': 1, 'FLAGGED': 1, 'ERROR': 1, 'NOT_CHECKED': 2}
    assert result.summary.flagged_verifications == 1
    assert result.summary.flagged_rows == 1


@pytest.mark.parametrize('register_content', [None, b'not an Excel file'])
def test_unavailable_register_has_no_fabricated_supplier_statuses(register_content):
    review = analyze_upload(workbook(invoices(3)), registry_mode='uploaded', registry_content=register_content)
    charts = dashboard_tables(review.result)
    assert charts['suppliers'].empty
    assert charts['contracts'].Antal.sum() == 0
    assert review.result.summary.supplier_unavailable_rows == 3
    assert counts(charts['checks'])['FLAGGED'] == 0
    assert counts(charts['checks'])['NOT_CHECKED'] == 12


@pytest.mark.parametrize('mode', ['empty', 'all_excluded', 'no_exclusions', 'matching'])
def test_dashboard_renders_zero_and_nonzero_results_before_detail_tables(mode):
    data = invoices(0 if mode == 'empty' else 3)
    if mode == 'all_excluded':
        data['Konto'] = '7698'
    review = analyze_upload(workbook(data), registry_mode='uploaded' if mode == 'matching' else 'disabled',
                            registry_content=workbook(registry()) if mode == 'matching' else None)
    source_before = review.result.original_data.copy(deep=True)
    downloads_before = dict(review.downloads)
    app = AppTest.from_file(str(APP), default_timeout=20)
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    assert app.subheader[0].value == 'Analysöversikt'
    assert any(h.value == 'Detaljer och granskning' for h in app.subheader)
    metrics = {m.label: m.value for m in app.metric}
    assert metrics['Källpopulation · rader'] == str(review.result.summary.source_rows)
    assert metrics['Flaggade · verifikationer'] == '0'
    assert metrics['Manuellt urval · verifikationer'] == '0'
    assert any('Granskningsstatus registreras inte' in c.value for c in app.caption)
    assert not app.get('progress')
    if mode != 'matching':
        assert any('Matchning ej tillgänglig' in info.value for info in app.info)
    if mode in ('empty', 'all_excluded'):
        assert any('Urvalspopulationen är tom' in info.value for info in app.info)
    chart_elements = app.get('vega_lite_chart')
    expected = dashboard_tables(review.result)
    assert len(chart_elements) == sum(not t.empty and t.Antal.sum() > 0 for t in expected.values())
    for chart in chart_elements:
        # Validate the actual browser spec, including exact count labels and units.
        import altair as alt
        spec = json.loads(chart.proto.spec)
        alt.LayerChart.from_dict(spec, validate=True)
        assert spec['encoding']['x']['field'] == 'Antal'
        assert spec['encoding']['x']['axis']['tickMinStep'] == 1
        assert spec['layer'][1]['encoding']['text']['field'] == 'Antal'
    elements = [node.type for node in app]
    if chart_elements:
        assert elements.index('vega_lite_chart') < elements.index('dataframe')
    assert len(app.download_button) == 6
    assert app.tabs[0].dataframe  # Existing source-linked detail views remain.
    pd.testing.assert_frame_equal(review.result.original_data, source_before)
    assert review.downloads == downloads_before
