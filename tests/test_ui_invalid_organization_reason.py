"""Readable explanations for unusable register organization numbers; synthetic data only."""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.ingestion.contract_reader import registry_from_frame
from src.supplier_matching.analysis import analyze_suppliers
from src.ui_supplier_matches import match_explanation, readable_reason, simple_match_rows
from src.ui_supplier_panel import supplier_review_table
from tests.synthetic_org import org

INVALID_CLAUSE = 'Organisationsnumret i registret är inte ett tekniskt giltigt organisationsnummer.'
MISSING_CLAUSE = 'Organisationsnummer saknas i registret.'
INVALID_TEXT = ('Organisationsnumret i avtalsregistret är inte ett giltigt svenskt organisationsnummer, '
                'vilket hindrar en stark namnmatchning. Numret kan vara felskrivet, ofullständigt '
                'eller ha ett annat format.')
MISSING_TEXT = 'Organisationsnummer saknas i avtalsregistret, vilket hindrar en stark namnmatchning.'
WRONG_CHECKSUM = org(202)[:-1] + str((int(org(202)[-1]) + 1) % 10)
INVALID_IDENTIFIERS = [
    pytest.param('SAKNAS', id='placeholder'),
    pytest.param(WRONG_CHECKSUM, id='checksum'),
    pytest.param(f'{WRONG_CHECKSUM[:6]}-{WRONG_CHECKSUM[6:]}', id='checksum-hyphenated'),
    pytest.param('121212-1212', id='personal-number-form'),
    pytest.param('191212121212', id='twelve-digit-personal-number'),
    pytest.param('16' + org(202), id='twelve-digits'),
    pytest.param('DE123456789', id='foreign-format'),
]


def analysis_for(identifier):
    registry = registry_from_frame(pd.DataFrame({'supplier_name': ['Bonliva AB'],
                                                 'organization_number': [identifier]}))
    source = pd.DataFrame({'Huvudtext': ['Bonliva AB Prelb 1']}, index=[7])
    return source, analyze_suppliers(source.rename(columns={'Huvudtext': 'header_text'}), registry)


def rendered_text(frame):
    return ' '.join(str(value) for value in frame.to_numpy().ravel())


def test_invalid_clause_is_translated_and_missing_clause_is_unchanged():
    assert readable_reason(f'Exakt normaliserat namn. {INVALID_CLAUSE}', 'exact_normalized') == (
        f'Leverantörsnamnen överensstämmer efter standardisering. {INVALID_TEXT}')
    assert readable_reason(f'Exakt normaliserat namn. {MISSING_CLAUSE}', 'exact_normalized') == (
        f'Leverantörsnamnen överensstämmer efter standardisering. {MISSING_TEXT}')
    assert INVALID_CLAUSE not in readable_reason(INVALID_CLAUSE, 'fuzzy')
    assert 'Okänd orsak.' == readable_reason('Okänd orsak.', 'fuzzy')  # Unknown clauses are retained.


@pytest.mark.parametrize('identifier', INVALID_IDENTIFIERS)
def test_invalid_register_number_is_explained_without_exposing_the_value(identifier):
    source, analysis = analysis_for(identifier)
    before = [frame.copy(deep=True) for frame in (analysis.rows, analysis.candidates, analysis.contracts)]
    row = analysis.rows.iloc[0]
    assert row.supplier_match_status == 'AMBIGUOUS_MATCH'  # Decision unchanged by presentation.
    assert pd.isna(row.matched_organization_number)
    simple = simple_match_rows(analysis.rows, analysis.candidates)
    review = supplier_review_table(source, analysis)
    for explanation in (simple.explanation.iloc[0], review['Varför detta resultat?'].iloc[0],
                        match_explanation(row)):
        assert INVALID_TEXT in explanation
        assert MISSING_TEXT not in explanation and INVALID_CLAUSE not in explanation
    assert simple.match_result.tolist() == ['Osäker namnmatchning']
    assert identifier not in rendered_text(simple)
    assert identifier not in rendered_text(review.drop(columns='Huvudtext'))
    for frame, expected in zip((analysis.rows, analysis.candidates, analysis.contracts), before):
        pd.testing.assert_frame_equal(frame, expected)


@pytest.mark.parametrize('identifier', [None, '', '  '])
def test_missing_register_number_keeps_existing_explanation(identifier):
    _, analysis = analysis_for(identifier)
    explanation = simple_match_rows(analysis.rows, analysis.candidates).explanation.iloc[0]
    assert analysis.rows.supplier_match_status.tolist() == ['AMBIGUOUS_MATCH']
    assert MISSING_TEXT in explanation and INVALID_TEXT not in explanation


def test_valid_register_number_has_neither_identifier_explanation():
    _, analysis = analysis_for(org(202))
    explanation = simple_match_rows(analysis.rows, analysis.candidates).explanation.iloc[0]
    assert analysis.rows.supplier_match_status.tolist() == ['STRONG_MATCH']
    assert analysis.rows.matched_organization_number.tolist() == [org(202)]
    assert INVALID_TEXT not in explanation and MISSING_TEXT not in explanation


@pytest.mark.parametrize('identifier', ['SAKNAS', '121212-1212', WRONG_CHECKSUM])
def test_rendered_candidate_panel_shows_explanation_and_no_raw_identifier(identifier):
    _, analysis = analysis_for(identifier)
    app = AppTest.from_string(
        'import streamlit as st\n'
        'from src.ui_supplier_matches import show_supplier_candidates\n'
        'analysis = st.session_state["analysis"]\n'
        'show_supplier_candidates(analysis.rows, analysis.candidates)')
    app.session_state['analysis'] = analysis
    app.run()
    assert not app.exception
    simple = app.dataframe[0].value
    assert INVALID_TEXT in simple.explanation.iloc[0]
    # The simple table and both technical tables in this panel omit the unusable value.
    assert len(app.dataframe) == 3
    for table in app.dataframe:
        assert identifier not in rendered_text(table.value)
