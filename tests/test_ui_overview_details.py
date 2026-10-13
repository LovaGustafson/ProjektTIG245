"""Overview disclosure and provenance use synthetic, unchanged pipeline evidence."""
from copy import deepcopy
import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.models.result import CheckResult, CheckStatus
from src.ingestion.contract_reader import registry_from_frame
from src.pipeline import run_pipeline
from src.supplier_matching.analysis import analyze_suppliers
from src.ui_overview_details import (
    source_rows, reason_counts, detection_details, supplier_details, supplier_candidate_comparisons,
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


@pytest.fixture
def candidate_analysis():
    source = pd.DataFrame({
        'verification_id': ['same'] * 4,
        'header_text': ['Securitas Sverige AB Slutk1', 'Alpha AB Prelb 2',
                        'SECURITAS SVERIGE A Slutk3', 'Text utan markör'],
        'verification_date': ['2026-06-15'] * 4,
    }, index=[42, 7, 105, 8])
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': ['Securitas Sverige Aktiebolag', 'Securitas Technology Sverige AB', 'Alpha AB'],
        'organization_number': ['001', '002', '003'],
        'start_date': ['2026-01-01'] * 3, 'end_date': ['2026-12-31'] * 3,
    }))
    return source, analyze_suppliers(source, registry)


def candidate_app(matches, candidates):
    app = AppTest.from_string(
        'import streamlit as st\n'
        'from src.ui_run_summary import show_supplier_candidates\n'
        'show_supplier_candidates(st.session_state["matches"], st.session_state["candidates"])')
    app.session_state['matches'] = matches
    app.session_state['candidates'] = candidates
    app.run()
    assert not app.exception
    return app


def test_candidate_comparisons_link_by_source_position_and_keep_all_backend_evidence(candidate_analysis):
    source, analysis = candidate_analysis
    before_source = source.copy(deep=True)
    before = deepcopy(analysis)
    # Deliberately unrelated frame indexes and order; repeated Vernr must not be a join key.
    candidates = analysis.candidates.iloc[[4, 0, 2, 3, 1]]
    display = supplier_candidate_comparisons(analysis.rows.iloc[::-1], candidates)
    assert display.source_row_position.tolist() == [105, 42, 7, 105, 42]
    assert display.supplier_text_raw.tolist() == [
        'SECURITAS SVERIGE A', 'Securitas Sverige AB', 'Alpha AB',
        'SECURITAS SVERIGE A', 'Securitas Sverige AB']
    assert display.supplier_match_status.tolist() == [
        'AMBIGUOUS_MATCH', 'AMBIGUOUS_MATCH', 'STRONG_MATCH', 'AMBIGUOUS_MATCH', 'AMBIGUOUS_MATCH']
    pd.testing.assert_frame_equal(display[candidates.columns], candidates)
    # An exact, individually eligible candidate does not make the source-row match strong.
    exact = display.loc[display.method.eq('exact_normalized') & display.source_row_position.eq(42)].iloc[0]
    assert exact.score == 1 and exact.strong_eligible
    assert exact.supplier_match_status == 'AMBIGUOUS_MATCH'
    assert analysis.contracts.loc[analysis.contracts.source_row_position.eq(42), 'contract_period_status'].eq('NOT_CHECKED').all()
    for field in ('rows', 'candidates', 'contracts'):
        pd.testing.assert_frame_equal(getattr(analysis, field), getattr(before, field))
    pd.testing.assert_frame_equal(source, before_source)


def test_candidate_table_shows_side_by_side_names_and_backend_status(candidate_analysis):
    _, analysis = candidate_analysis
    before = deepcopy(analysis)
    app = candidate_app(analysis.rows, analysis.candidates)
    table = app.dataframe[0]
    order = ['supplier_text_raw', 'supplier_name', 'match_result', 'score', 'explanation']
    assert list(table.proto.column_order) == order
    labels = json.loads(table.proto.columns)
    assert [labels[field]['label'] for field in order] == [
        'Leverantör i internkontrollsfilen', 'Leverantör i avtalsregistret', 'Matchningsresultat',
        'Matchningsscore', 'Varför detta resultat?']
    assert labels['supplier_text_raw']['width'] == labels['supplier_name']['width'] == 'large'
    assert table.value.supplier_text_raw.tolist() == [
        'Securitas Sverige AB', 'Securitas Sverige AB', 'Alpha AB',
        'SECURITAS SVERIGE A', 'SECURITAS SVERIGE A', 'Inget extraherat leverantörsnamn']
    assert table.value.match_result.tolist() == [
        'Osäker namnmatchning', 'Osäker namnmatchning', 'Stark namnmatchning',
        'Osäker namnmatchning', 'Osäker namnmatchning', 'Leverantör ej identifierad']
    assert list(table.value.columns) == order
    assert table.value.score.iloc[:5].tolist() == analysis.candidates.score.tolist()
    assert pd.isna(table.value.score.iloc[5])
    assert labels['score']['type_config']['format'] == '%.6f'
    assert any('0–1' in c.value and 'inte sannolikheten' in c.value for c in app.caption)
    technical = expander(app, 'Visa tekniska matchningsdetaljer')
    assert not technical.proto.expanded
    pd.testing.assert_frame_equal(technical.dataframe[0].value, analysis.rows)
    pd.testing.assert_frame_equal(technical.dataframe[1].value[analysis.candidates.columns], analysis.candidates)
    assert 'Flera möjliga leverantörer hittades.' in table.value.explanation.iloc[0]
    assert 'överensstämmer efter standardisering' in table.value.explanation.iloc[0]
    assert table.value.match_result.iloc[0] == 'Osäker namnmatchning' and table.value.score.iloc[0] == 1
    for field in ('rows', 'candidates', 'contracts'):
        pd.testing.assert_frame_equal(getattr(analysis, field), getattr(before, field))


@pytest.mark.parametrize('missing_name', [None, '', '   '])
def test_candidate_table_marks_missing_extracted_name_without_guessing(candidate_analysis, missing_name):
    _, analysis = candidate_analysis
    matches = analysis.rows.copy(deep=True)
    matches.loc[matches.source_row_position.eq(42), 'supplier_text_raw'] = missing_name
    shown = candidate_app(matches, analysis.candidates).dataframe[0].value
    assert shown.iloc[:2]['supplier_text_raw'].tolist() == [
        'Inget extraherat leverantörsnamn'] * 2
    assert len(shown) == len(analysis.candidates) + 1
    assert shown.iloc[:2]['match_result'].eq('Osäker namnmatchning').all()


def test_candidate_table_preserves_many_candidates_and_handles_empty_population(candidate_analysis):
    _, analysis = candidate_analysis
    candidates = pd.concat([analysis.candidates] * 120, ignore_index=True)
    app = candidate_app(analysis.rows, candidates)
    shown = app.dataframe[0].value
    assert len(shown) == 601
    assert shown.score.iloc[:600].tolist() == candidates.score.tolist()
    technical = expander(app, 'Visa tekniska matchningsdetaljer')
    pd.testing.assert_frame_equal(technical.dataframe[1].value[candidates.columns], candidates)
    unidentified = analysis.rows.loc[analysis.rows.source_row_position.eq(8)]
    empty = analysis.candidates.loc[analysis.candidates.source_row_position.eq(8)]
    app = candidate_app(unidentified, empty)
    assert len(app.dataframe[0].value) == 1
    assert pd.isna(app.dataframe[0].value.score.iloc[0])
    assert app.dataframe[0].value.match_result.iloc[0] == 'Leverantör ej identifierad'
    empty_app = candidate_app(unidentified.iloc[:0], empty)
    assert not empty_app.dataframe
    assert any(c.value == 'Inga poster i denna kategori.' for c in empty_app.caption)


def test_unverifiable_contracts_keep_actual_reasons_and_comparison_unit(review):
    result = review.result
    contracts, rows = contract_details(result, 'NOT_CHECKED')
    assert set(rows.source_row_position) == {1, 3, 7, 8}
    assert contracts.contract_period_status.eq('NOT_CHECKED').all()
    assert contracts.contract_period_reason.tolist() == result.supplier_analysis.contracts.loc[
        result.supplier_analysis.contracts.contract_period_status == 'NOT_CHECKED', 'contract_period_reason'].tolist()
    counts = reason_counts(contracts, ['contract_period_reason']).set_index('contract_period_reason').Antal.to_dict()
    assert counts == {
        'Ingen stark namnmatchning; kandidatens avtalsperiod har inte bedömts.': 4,
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
    assert not any('kontrollresultat' in e.label.lower() for e in app.expander)
    assert not any('check_type' in table.value for table in app.dataframe)
    # Rendering no longer exposes control placeholders, but preserves their evidence.
    pd.testing.assert_frame_equal(detection_details(result, 'NOT_CHECKED')[0], checks)
    assert result.summary.check_status_counts == {'PASS': 3, 'NOT_CHECKED': 2, 'FLAGGED': 1, 'ERROR': 1}


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
    assert result.summary.sampled_verifications == 1  # Repeated strongly matched supplier.
    assert result.summary.sampled_rows == 1
    assert result.sampling_result.target_size == 2
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
    assert selected.population_position.tolist() == [20]
    assert sampled.source_row_position.tolist() == result.sampling_evidence.source_row_position.tolist()
    remaining, _ = verification_details(result, 'remaining')
    assert len(remaining) == 39
    assert 6 not in rows.source_row_position.tolist()
    assert 6 in supplier_details(result, 'STRONG_MATCH')[0].source_row_position.tolist()


def test_ui_progressive_disclosure_and_preserved_results(review):
    before = deepcopy(review.result)
    downloads = dict(review.downloads)
    app = overview_app(review.result)
    assert not any('Detektionskontroller' in item.value for item in app.markdown)
    assert not any('check_type' in table.value for table in app.dataframe)
    assert all(not e.proto.expanded for e in app.expander)
    exclusions = expander(app, 'Varför exkluderades rader?')
    assert len(exclusions.get('vega_lite_chart')) == 1
    assert sum(e.label.endswith('regelträffar') for e in exclusions.expander) == 3
    for table in exclusions.dataframe:
        assert table.value.source_row_position.tolist() == [0]
        assert table.value.exclusion_reason.tolist() == [before.filtering.reasons[0]]
    ambiguous = expander(app, 'Osäker namnmatchning ·')
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
    assert '39 rader med stark namnmatchning' in explanation.text[0].value
    assert any('juridisk identitet har inte verifierats mot internkontrollsfilen' in c.value for c in app.caption)
    strong = expander(app, 'Stark namnmatchning ·')
    assert any('En stark namnmatchning har identifierats i avtalsregistret.' in m.value for m in strong.markdown)
    for container in (strong, ambiguous, unverifiable):
        for table in container.dataframe:
            for field in ('organization_number', 'matched_organization_number'):
                if field in table.value:
                    assert json.loads(table.proto.columns)[field]['label'] == 'Organisationsnummer (från avtalsregistret)'
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
