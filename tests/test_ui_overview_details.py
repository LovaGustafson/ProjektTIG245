"""Overview disclosure and provenance use synthetic, unchanged pipeline evidence."""
from copy import deepcopy

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.models.result import CheckResult, CheckStatus
from src.pipeline import run_pipeline
from src.ui_overview_details import (
    source_rows, reason_counts, detection_details, supplier_details,
    contract_details, exclusion_details, verification_details,
)
from src.ui_run_summary import dashboard_tables
from src.ui_support import analyze_upload
from tests.test_feature_package import invoices, registry, workbook


@pytest.fixture(scope='module')
def review():
    data = invoices(44)
    data.loc[0, ['Konto', 'Vertyp', 'Huvudtext']] = ['7698', 'FBFM', 'mall']
    data.loc[[2, 10], 'Vernr'] = data.loc[1, 'Vernr']  # Same Vernr/Vrad, distinct occurrences.
    data.loc[1, 'Huvudtext'] = 'Input interiör Slutk2'
    data.loc[3, 'Huvudtext'] = 'Input interiör Slutk4'
    data.loc[4, 'Huvudtext'] = 'Okänd Testverksamhet AB Slutk5'
    data.loc[5, 'Huvudtext'] = 'Text utan markör'
    data.loc[6, 'Vernr'] = None  # Strongly matched but not in the sampling population.
    data.loc[7, 'Verdatum'] = None
    data.loc[8, 'Verdatum'] = '2026-01-01'
    contracts = pd.concat([
        registry(), registry().assign(**{'Avtals-ID': 'ended', 'Slutdatum': '2026-02-01'}),
        pd.DataFrame({'Leverantör': ['Input interiör AB', 'Input interiör Göteborg AB'],
                      'Organisationsnummer': ['2', '3']}),
    ], ignore_index=True)
    return analyze_upload(workbook(data), registry_mode='uploaded', registry_content=workbook(contracts))


def overview_app(result):
    app = AppTest.from_string(
        'import streamlit as st\n'
        'from src.ui_run_summary import show_run_summary\n'
        'show_run_summary(st.session_state["result"])', default_timeout=20)
    app.session_state['result'] = result
    app.run()
    assert not app.exception
    return app


def expander(app, prefix):
    return next(e for e in app.expander if e.label.startswith(prefix))


def evidence_table(container, column):
    return next(d.value for d in container.dataframe if column in d.value)


def test_supplier_drilldown_uses_exact_source_occurrences_and_backend_reasons(review):
    result = review.result
    matches, candidates, contracts, rows = supplier_details(result, 'AMBIGUOUS_MATCH')
    assert matches.source_row_position.tolist() == [1, 3]
    assert rows.source_row_position.tolist() == [1, 3]
    assert rows.source_excel_row.tolist() == [3, 5]
    assert rows.Huvudtext.tolist() == ['Input interiör Slutk2', 'Input interiör Slutk4']
    assert 2 not in rows.index and 10 not in rows.index  # Shared Vernr does not leak other rows.
    analysis = result.supplier_analysis
    pd.testing.assert_frame_equal(matches, analysis.rows.loc[analysis.rows.source_row_position.isin([1, 3])])
    pd.testing.assert_frame_equal(candidates, analysis.candidates.loc[analysis.candidates.source_row_position.isin([1, 3])])
    pd.testing.assert_frame_equal(contracts, analysis.contracts.loc[analysis.contracts.source_row_position.isin([1, 3])])
    assert set(candidates.supplier_name) == {'Input interiör AB', 'Input interiör Göteborg AB'}
    assert candidates.reason.str.len().gt(0).all()
    assert matches.matched_supplier_name.isna().all()
    assert reason_counts(matches, ['supplier_match_reason']).Antal.sum() == 2


def test_unverifiable_contracts_keep_actual_reasons_and_comparison_unit(review):
    result = review.result
    contracts, rows = contract_details(result, 'NOT_CHECKED')
    assert set(rows.source_row_position) == {1, 3, 7, 8}
    assert contracts.contract_period_status.eq('NOT_CHECKED').all()
    assert contracts.contract_period_reason.tolist() == result.supplier_analysis.contracts.loc[
        result.supplier_analysis.contracts.contract_period_status == 'NOT_CHECKED', 'contract_period_reason'].tolist()
    counts = reason_counts(contracts, ['contract_period_reason']).set_index('contract_period_reason').Antal.to_dict()
    assert counts == {
        'Ingen säker leverantörsidentitet; kandidatens avtalsperiod har inte bedömts.': 4,
        'Verifikationsdatum eller avtalets startdatum saknas eller kan inte läsas.': 2,
        'Datumet ligger på en periodgräns; regeln för giltighet på start-/slutdagen är inte bekräftad.': 2,
    }
    outside, _ = contract_details(result, 'FLAGGED')
    assert outside.contract_period_reason.str.contains('efter avtalets giltiga period').all()
    assert not set(contracts.index) & set(outside.index)
    assert not set(contracts.source_row_position) & {4, 5}  # No invented comparisons without candidates.


def test_detection_links_local_positions_and_keeps_statuses_separate(tmp_path):
    data = invoices(5)
    data.loc[0, 'Konto'] = '7698'
    data.loc[3, 'Vernr'] = data.loc[1, 'Vernr']
    source = tmp_path / 'synthetic.xlsx'
    source.write_bytes(workbook(data))

    def rule(v, context):
        if v.verification_id != '2':
            return [CheckResult(v.verification_id, 'synthetic', CheckStatus.PASS, 'Present')]
        return [
            CheckResult(v.verification_id, 'synthetic', CheckStatus.PASS, 'Present', row_position=0),
            CheckResult(v.verification_id, 'synthetic', CheckStatus.NOT_CHECKED, 'Evidence unavailable',
                        verification_line_id=1, field='image_reference', row_position=1),
            CheckResult(v.verification_id, 'synthetic', CheckStatus.NOT_CHECKED, 'Policy unconfirmed'),
            CheckResult(v.verification_id, 'synthetic', CheckStatus.FLAGGED, 'Missing information', row_position=0),
            CheckResult(v.verification_id, 'synthetic', CheckStatus.ERROR, 'Technical failure'),
        ]

    result = run_pipeline(source, output_dir=tmp_path / 'reports', use_default_registry=False,
                          rules={'synthetic': rule})
    checks, rows = detection_details(result, 'NOT_CHECKED')
    assert checks.status.tolist() == ['NOT_CHECKED', 'NOT_CHECKED']
    assert checks.reason.tolist() == ['Evidence unavailable', 'Policy unconfirmed']
    assert checks.source_row_positions.tolist() == [[3], [1, 3]]
    assert rows.source_row_position.tolist() == [1, 3]
    assert rows.source_excel_row.tolist() == [3, 5]
    assert checks.field.iloc[0] == 'image_reference'
    assert pd.isna(checks.field.iloc[1])
    assert reason_counts(checks, ['check_type', 'field', 'reason']).Antal.sum() == 2
    assert result.summary.check_status_counts == {'PASS': 3, 'NOT_CHECKED': 2, 'FLAGGED': 1, 'ERROR': 1}
    app = overview_app(result)
    not_checked = expander(app, 'Ej kontrollerad (NOT_CHECKED)')
    shown = evidence_table(not_checked, 'source_row_positions')
    assert shown.status.tolist() == ['NOT_CHECKED'] * 2
    assert shown.reason.tolist() == checks.reason.tolist()
    assert any('inte PASS eller godkänt' in m.value for m in not_checked.markdown)
    passed = evidence_table(expander(app, 'Utan flagga (PASS)'), 'source_row_positions')
    assert passed.status.tolist() == ['PASS'] * 3


def test_invalid_detection_position_is_not_mistaken_for_source_position(review):
    from dataclasses import replace
    result = deepcopy(review.result)
    detection = result.detection_results[0]
    result.detection_results = [replace(detection, checks=(
        CheckResult(detection.verification_id, 'synthetic', CheckStatus.NOT_CHECKED,
                    'Unattributable', row_position=-1),))]
    checks, rows = detection_details(result, 'NOT_CHECKED')
    assert checks.source_row_positions.tolist() == [[]]
    assert checks.reason.tolist() == ['Unattributable']
    assert rows.empty


def test_metrics_exclusion_overlap_and_sample_use_existing_populations(review):
    result = review.result
    assert result.summary.source_rows == 44
    assert result.summary.included_rows == 43
    assert result.summary.excluded_rows == 1
    assert result.summary.eligible_verifications == 40
    assert result.summary.strong_supplier_rows == 39
    assert result.summary.sampled_verifications == 2
    assert result.summary.sampled_rows == 2
    for rule in result.summary.exclusion_counts:
        rows = exclusion_details(result, rule)
        assert rows.source_row_position.tolist() == [0]
        assert rows.exclusion_reason.tolist() == [result.filtering.reasons[0]]
    assert len(result.summary.exclusion_counts) == 3
    groups, rows = verification_details(result)
    assert len(groups) == 40
    assert len(rows) == 42  # Grouped rows: excludes the ungrouped occurrence.
    assert groups.iloc[0].source_row_positions == [1, 2, 10]
    selected, sampled = verification_details(result, 'selected')
    assert selected.population_position.tolist() == [20, 40]
    assert sampled.source_row_position.tolist() == result.sampling_evidence.source_row_position.tolist()
    remaining, _ = verification_details(result, 'remaining')
    assert len(remaining) == 38
    assert 6 not in rows.source_row_position.tolist()
    assert 6 in supplier_details(result, 'STRONG_MATCH')[0].source_row_position.tolist()


def test_ui_progressive_disclosure_and_preserved_results(review):
    before = deepcopy(review.result)
    downloads = dict(review.downloads)
    app = overview_app(review.result)
    assert all(not e.proto.expanded for e in app.expander)
    exclusions = expander(app, 'Varför exkluderades rader?')
    assert len(exclusions.get('vega_lite_chart')) == 1
    assert sum(e.label.endswith('regelträffar') for e in exclusions.expander) == 3
    for table in exclusions.dataframe:
        assert table.value.source_row_position.tolist() == [0]
        assert table.value.exclusion_reason.tolist() == [before.filtering.reasons[0]]
    ambiguous = expander(app, 'Osäker träff ·')
    shown = evidence_table(ambiguous, 'supplier_match_status')
    assert shown.source_row_position.tolist() == [1, 3]
    assert shown.supplier_match_reason.tolist() == supplier_details(before, 'AMBIGUOUS_MATCH')[0].supplier_match_reason.tolist()
    assert evidence_table(ambiguous, 'Huvudtext').Huvudtext.tolist() == ['Input interiör', 'Input interiör']
    assert evidence_table(ambiguous, 'strong_eligible').supplier_name.tolist() == supplier_details(
        before, 'AMBIGUOUS_MATCH')[1].supplier_name.tolist()
    unverifiable = expander(app, 'Ej verifierbar ·')
    assert '8 avtalsjämförelser' in unverifiable.label
    assert evidence_table(unverifiable, 'contract_period_status').contract_period_reason.tolist() == contract_details(
        before, 'NOT_CHECKED')[0].contract_period_reason.tolist()
    assert any('inte att avtal saknas eller är ogiltigt' in m.value for m in unverifiable.markdown)
    explanation = expander(app, 'Vad betyder urvalspopulation')
    assert '40 verifikationer' in explanation.text[0].value
    assert '39 rader med stark leverantörsträff' in explanation.text[0].value
    for name in ('original_data', 'standardized_data', 'ungrouped_data', 'sampling_evidence'):
        pd.testing.assert_frame_equal(getattr(review.result, name), getattr(before, name))
    for name in ('rows', 'candidates', 'contracts'):
        pd.testing.assert_frame_equal(getattr(review.result.supplier_analysis, name), getattr(before.supplier_analysis, name))
    for name in ('cleaned_data', 'excluded_data'):
        pd.testing.assert_frame_equal(getattr(review.result.filtering, name), getattr(before.filtering, name))
    assert review.result.filtering.reasons == before.filtering.reasons
    assert review.result.summary == before.summary
    for old, new in zip(before.detection_results, review.result.detection_results, strict=True):
        assert new.verification_id == old.verification_id
        assert new.checks == old.checks
        assert new.status == old.status
        assert new.executed_rules == old.executed_rules
        assert new.disabled_rules == old.disabled_rules
    for old, new in zip(before.verifications + before.manual_sample,
                        review.result.verifications + review.result.manual_sample, strict=True):
        pd.testing.assert_frame_equal(old.rows, new.rows)
    for name, table in dashboard_tables(before).items():
        pd.testing.assert_frame_equal(table, dashboard_tables(review.result)[name])
    assert review.downloads == downloads


def test_source_provenance_does_not_overwrite_supplied_columns(review):
    result = deepcopy(review.result)
    result.original_data['source_row_position'] = 'original cell'
    rows = source_rows(result, [3, 1])
    assert rows.source_row_position.tolist() == ['original cell'] * 2
    assert rows._source_row_position.tolist() == [3, 1]
    assert rows.source_excel_row.tolist() == [5, 3]


@pytest.mark.parametrize('content', [None, b'unreadable register'])
def test_unavailable_register_exposes_rows_without_fabricated_statuses(content):
    upload = analyze_upload(workbook(invoices(2)), registry_mode='uploaded', registry_content=content)
    app = overview_app(upload.result)
    unavailable = expander(app, 'Matchning ej tillgänglig –')
    assert evidence_table(unavailable, 'source_row_position').source_row_position.tolist() == [0, 1]
    assert [t.value for t in unavailable.text] == list(upload.result.supplier_analysis.registry.issues)
    assert not any(e.label.startswith(('Ingen träff i registret', 'Ej verifierbar')) for e in app.expander)
