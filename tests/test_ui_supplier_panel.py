"""Supplier review presentation uses existing, source-linked matching evidence."""
from dataclasses import replace

import pandas as pd
import pytest

from src.ingestion.contract_reader import registry_from_frame
from src.supplier_matching.analysis import analyze_suppliers
from src.ui_supplier_panel import STATUS_LABELS, supplier_review_table


@pytest.fixture
def supplier_review():
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': ['Alpha AB', 'Nordmöbler AB', 'Nordmöbler Göteborg AB', 'AJ Medical KB'],
        'organization_number': ['1', '2', '3', '4'],
    }))
    # Repeated business identifiers must not link evidence across source occurrences.
    source = pd.DataFrame({
        'Vernr': ['shared'] * 5,
        'Huvudtext': ['Alpha AB Prelb 1', 'Nordmöbler Slutk 2', 'AJ Medical HB Prelb 3',
                     'Obekant Testbolag AB Prelb 4', 'Original utan markör'],
    }, index=[2, 5, 9, 14, 18])
    analysis = analyze_suppliers(source.rename(columns={'Huvudtext': 'header_text'}), registry)
    return source, analysis


def test_ambiguous_candidates_and_reasons_follow_source_rows_and_backend_rank(supplier_review):
    source, analysis = supplier_review
    display = supplier_review_table(source.loc[[9, 5, 2]], analysis)

    assert display['Matchad avtalsleverantör'].tolist() == [
        'AJ Medical KB (kandidat)', 'Nordmöbler AB (kandidat)', 'Alpha AB']
    assert display['Leverantörsträff'].tolist() == [
        STATUS_LABELS['AMBIGUOUS_MATCH'], STATUS_LABELS['AMBIGUOUS_MATCH'],
        STATUS_LABELS['STRONG_MATCH']]
    reasons = analysis.rows.set_index('source_row_position')['supplier_match_reason']
    assert display['Orsak'].tolist() == reasons.loc[[9, 5, 2]].tolist()
    assert 'Olika bolagsformer: HB / KB.' in display.loc[9, 'Orsak']
    assert '2 möjliga leverantörsidentiteter; ingen har valts.' in display.loc[5, 'Orsak']


def test_missing_candidates_have_explicit_text_instead_of_none(supplier_review):
    source, analysis = supplier_review
    display = supplier_review_table(source, analysis)
    assert display.loc[[14, 18], 'Matchad avtalsleverantör'].tolist() == [
        'Ingen kandidat identifierad', 'Ingen kandidat identifierad']

    # Also handle an ambiguous row whose candidate evidence is unavailable.
    without_candidates = replace(analysis, candidates=analysis.candidates.iloc[:0].copy())
    display = supplier_review_table(source.loc[[5]], without_candidates)
    assert display.loc[5, 'Matchad avtalsleverantör'] == 'Ingen kandidat identifierad'
    assert display.loc[5, 'Leverantörsträff'] == STATUS_LABELS['AMBIGUOUS_MATCH']


def test_presentation_preserves_source_results_counts_and_original_column_values(supplier_review):
    source, analysis = supplier_review
    source = source.assign(Orsak='Ursprunglig orsak', **{'Matchad avtalsleverantör': 'Originalvärde'})
    before_source = source.copy(deep=True)
    before_frames = [frame.copy(deep=True) for frame in (analysis.rows, analysis.candidates, analysis.contracts)]
    before_counts = analysis.summary()

    display = supplier_review_table(source, analysis)
    pd.testing.assert_frame_equal(display, supplier_review_table(source, analysis))
    pd.testing.assert_frame_equal(display[source.columns], before_source)
    assert display.loc[5, '_Matchad avtalsleverantör'] == 'Nordmöbler AB (kandidat)'
    assert display.loc[9, '_Orsak'] == analysis.rows.set_index('source_row_position').loc[9, 'supplier_match_reason']
    pd.testing.assert_frame_equal(source, before_source)
    for actual, expected in zip((analysis.rows, analysis.candidates, analysis.contracts), before_frames):
        pd.testing.assert_frame_equal(actual, expected)
    assert analysis.summary() == before_counts
    ambiguous = analysis.rows['supplier_match_status'].eq('AMBIGUOUS_MATCH')
    assert analysis.rows.loc[ambiguous, ['matched_supplier_name', 'matched_organization_number']].isna().all().all()


def test_unavailable_matching_does_not_fabricate_missing_candidates(supplier_review):
    source, _ = supplier_review
    unavailable = analyze_suppliers(source, registry_from_frame(pd.DataFrame()))
    pd.testing.assert_frame_equal(supplier_review_table(source, unavailable), source)
    pd.testing.assert_frame_equal(supplier_review_table(source, None), source)
