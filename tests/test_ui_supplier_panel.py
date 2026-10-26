"""Supplier review presentation uses existing, source-linked matching evidence."""
from dataclasses import replace
import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.ingestion.contract_reader import registry_from_frame
from src.supplier_matching.analysis import analyze_suppliers
from src.ui_supplier_panel import supplier_review_table
from src.ui_supplier_matches import MATCH_LABELS
from tests.synthetic_org import org


@pytest.fixture
def supplier_review():
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': ['Alpha AB', 'Nordmöbler AB', 'Nordmöbler Göteborg AB', 'AJ Medical KB'],
        'organization_number': [org(1), org(2), org(3), org(4)],
    }))
    # Repeated business identifiers must not link evidence across source occurrences.
    source = pd.DataFrame({
        'Vernr': ['shared'] * 5,
        'Huvudtext': ['Alpha AB Prelb 1', 'Nordmöbler Slutk 2', 'AJ Medical HB Prelb 3',
                     'Obekant Testbolag AB Prelb 4', 'Original utan markör'],
    }, index=[2, 5, 9, 14, 18])
    analysis = analyze_suppliers(source.rename(columns={'Huvudtext': 'header_text'}), registry)
    return source, analysis


def test_summary_preserves_full_heading_and_existing_drilldown(supplier_review):
    _, analysis = supplier_review
    before = [frame.copy(deep=True) for frame in (analysis.rows, analysis.candidates, analysis.contracts)]
    app = AppTest.from_string(
        'import streamlit as st\n'
        'from src.ui_supplier_panel import show_supplier_summary\n'
        'show_supplier_summary(st.session_state["analysis"])')
    app.session_state['analysis'] = analysis
    app.run()
    assert not app.exception
    assert app.subheader[0].value == 'Leverantörsmatchning mot Koncerninköp'
    assert app.button(key='supplier_all').label == (
        '**5**  \nLeverantörsmatchning – analyserade rader')
    app.button(key='supplier_all').click().run()
    assert not app.exception
    assert app.session_state['selected_supplier'] == 'all'
    for actual, expected in zip((analysis.rows, analysis.candidates, analysis.contracts), before, strict=True):
        pd.testing.assert_frame_equal(actual, expected)


def test_ambiguous_candidates_and_reasons_follow_source_rows_and_backend_rank(supplier_review):
    source, analysis = supplier_review
    display = supplier_review_table(source.loc[[9, 5, 2]], analysis)

    assert display['Leverantör i avtalsregistret'].tolist() == [
        'AJ Medical KB (kandidat)', 'Nordmöbler AB (kandidat)', 'Alpha AB']
    assert display['Matchningsresultat'].tolist() == [
        MATCH_LABELS['AMBIGUOUS_MATCH'], MATCH_LABELS['AMBIGUOUS_MATCH'],
        MATCH_LABELS['STRONG_MATCH']]
    assert display.loc[2, 'Varför detta resultat?'] == 'Leverantörsnamnen överensstämmer efter standardisering.'
    assert display['Matchningsscore'].tolist() == analysis.rows.set_index('source_row_position').loc[[9, 5, 2], 'supplier_match_score'].tolist()
    assert 'Olika bolagsformer: HB / KB.' in display.loc[9, 'Varför detta resultat?']
    assert 'Flera möjliga leverantörer hittades.' in display.loc[5, 'Varför detta resultat?']


def test_missing_candidates_have_explicit_text_instead_of_none(supplier_review):
    source, analysis = supplier_review
    display = supplier_review_table(source, analysis)
    assert display.loc[[14, 18], 'Leverantör i avtalsregistret'].tolist() == [
        'Ingen kandidat identifierad', 'Ingen kandidat identifierad']

    # Also handle an ambiguous row whose candidate evidence is unavailable.
    without_candidates = replace(analysis, candidates=analysis.candidates.iloc[:0].copy())
    display = supplier_review_table(source.loc[[5]], without_candidates)
    assert display.loc[5, 'Leverantör i avtalsregistret'] == 'Ingen kandidat identifierad'
    assert display.loc[5, 'Matchningsresultat'] == MATCH_LABELS['AMBIGUOUS_MATCH']


def test_presentation_preserves_source_results_counts_and_original_column_values(supplier_review):
    source, analysis = supplier_review
    source = source.assign(**{'Varför detta resultat?': 'Ursprunglig orsak', 'Leverantör i avtalsregistret': 'Originalvärde'})
    before_source = source.copy(deep=True)
    before_frames = [frame.copy(deep=True) for frame in (analysis.rows, analysis.candidates, analysis.contracts)]
    before_counts = analysis.summary()

    display = supplier_review_table(source, analysis)
    pd.testing.assert_frame_equal(display, supplier_review_table(source, analysis))
    pd.testing.assert_frame_equal(display[source.columns], before_source)
    assert display.loc[5, '_Leverantör i avtalsregistret'] == 'Nordmöbler AB (kandidat)'
    assert 'Olika bolagsformer: HB / KB.' in display.loc[9, '_Varför detta resultat?']
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


@pytest.mark.parametrize('position, label', [
    (2, '🟢 Stark namnmatchning'), (5, '🟡 Osäker namnmatchning – manuell granskning'),
])
def test_detail_labels_explain_register_origin_without_changing_evidence(supplier_review, position, label):
    _, analysis = supplier_review
    before = [frame.copy(deep=True) for frame in (analysis.rows, analysis.candidates, analysis.contracts)]
    app = AppTest.from_string(
        'import streamlit as st\n'
        'from src.ui_supplier_panel import show_supplier_detail\n'
        'show_supplier_detail(st.session_state["analysis"], st.session_state["position"])')
    app.session_state['analysis'] = analysis
    app.session_state['position'] = position
    app.run()
    assert not app.exception
    assert app.subheader[0].value == label
    assert any('juridisk identitet har inte verifierats mot internkontrollsfilen' in c.value for c in app.caption)
    simple = app.dataframe[0].value
    assert simple.match_result.eq(MATCH_LABELS[analysis.rows.set_index('source_row_position').loc[position, 'supplier_match_status']]).all()
    technical = next(e for e in app.expander if e.label == 'Visa tekniska matchningsdetaljer')
    assert not technical.proto.expanded
    details = technical.dataframe[0]
    assert json.loads(details.proto.columns)['matched_organization_number']['label'] == 'Organisationsnummer (från avtalsregistret)'
    expected = analysis.rows.loc[analysis.rows.source_row_position.eq(position)]
    pd.testing.assert_frame_equal(details.value, expected)
    if position == 2:
        assert details.value.matched_organization_number.iloc[0] == org(1)
        assert any(c.value.startswith('En stark namnmatchning har identifierats i avtalsregistret.') for c in app.caption)
    else:
        assert len(simple) == 2
        assert any('ingen leverantör har valts automatiskt' in w.value for w in app.warning)
    candidates = technical.dataframe[1]
    assert json.loads(candidates.proto.columns)['organization_number']['label'] == 'Organisationsnummer (från avtalsregistret)'
    for old, current in zip(before, (analysis.rows, analysis.candidates, analysis.contracts), strict=True):
        pd.testing.assert_frame_equal(old, current)


@pytest.mark.parametrize('query, name, organization, method, status, text', [
    ('Alpha AB', 'Alpha Aktiebolag', org(1), 'exact_normalized', 'STRONG_MATCH', 'överensstämmer efter standardisering'),
    ('Alpha AB', 'Alpha AB', None, 'exact_normalized', 'AMBIGUOUS_MATCH', 'Organisationsnummer saknas i avtalsregistret'),
    ('Input interiör', 'Input interiör AB', org(1), 'prefix', 'STRONG_MATCH', 'gemensam början'),
    ('Input', 'Input interiör AB', org(1), 'uncertain_prefix', 'AMBIGUOUS_MATCH', 'räcker inte för en stark namnmatchning'),
    ('Alphabolaget Sverige AB', 'Alphabolaget Svergie AB', org(1), 'fuzzy', 'STRONG_MATCH', 'mycket lika och har samma antal ord'),
    ('Securitas Sverige AB', 'Securitas Stockholm Sverige AB', org(1), 'related_name', 'AMBIGUOUS_MATCH', 'skiljer sig orden'),
    ('AJ Medical HB', 'AJ Medical KB', org(1), 'fuzzy', 'AMBIGUOUS_MATCH', 'Olika bolagsformer: HB / KB.'),
    ('Alpha AB', 'Alpha', org(1), 'related_name', 'AMBIGUOUS_MATCH', 'Bolagsformen i namnen kan inte bekräftas som samma.'),
    ('Alpha AB', 'Alpha AB Sverige', org(1), 'uncertain_prefix', 'AMBIGUOUS_MATCH', 'Bolagsformen följs av ytterligare text'),
])
def test_simplified_explanations_follow_actual_backend_results(query, name, organization, method, status, text):
    from src.ui_supplier_matches import simple_match_rows, candidate_summary
    source = pd.DataFrame({'header_text': [query + ' Prelb 1']})
    registry = registry_from_frame(pd.DataFrame({'supplier_name': [name], 'organization_number': [organization]}))
    analysis = analyze_suppliers(source, registry)
    row = analysis.rows.iloc[0]
    assert row.supplier_match_method == method
    assert row.supplier_match_status == status
    display = simple_match_rows(analysis.rows, analysis.candidates)
    assert display.match_result.iloc[0] == MATCH_LABELS[status]
    assert display.score.iloc[0] == analysis.candidates.score.iloc[0]
    assert text in display.explanation.iloc[0]
    assert candidate_summary(row) == '1 möjlig leverantör hittades.'
    if organization is None:
        assert display.score.iloc[0] == 1
        assert 'likheten räcker inte' not in display.explanation.iloc[0]
    for technical in ('exact_normalized', 'uncertain_prefix', 'fuzzy', 'STRONG_MATCH', 'AMBIGUOUS_MATCH'):
        assert technical not in display.explanation.iloc[0]


def test_unknown_reasons_are_preserved_and_counts_come_from_backend(supplier_review):
    from src.ui_supplier_matches import simple_match_rows, candidate_summary
    _, analysis = supplier_review
    matches = analysis.rows.loc[analysis.rows.source_row_position.eq(5)].copy(deep=True)
    candidates = analysis.candidates.loc[analysis.candidates.source_row_position.eq(5)].iloc[:1]
    # A partial candidate view must never recalculate the recorded population or status.
    shown = simple_match_rows(matches, candidates)
    assert len(shown) == 1
    assert shown.match_result.iloc[0] == 'Osäker namnmatchning'
    assert 'Flera möjliga leverantörer hittades.' in shown.explanation.iloc[0]
    assert candidate_summary(matches.iloc[0]) == '2 möjliga leverantörer hittades – kontrollera vilken som är rätt.'
    matches['supplier_match_reason'] = 'En ny registrerad orsak.'
    shown = simple_match_rows(matches, candidates)
    assert 'En ny registrerad orsak.' in shown.explanation.iloc[0]
    absent = analysis.rows.loc[analysis.rows.source_row_position.eq(14)].iloc[0]
    assert candidate_summary(absent) == 'Ingen möjlig leverantör hittades.'
