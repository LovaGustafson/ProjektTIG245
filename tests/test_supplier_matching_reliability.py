"""Supplier reliability regressions, including the 13 resolved Phase 1 failures.

All register identities, aliases and source occurrences below are synthetic.
"""
from itertools import permutations

import pandas as pd
import pytest

from src.ingestion.contract_reader import registry_from_frame
from src.supplier_matching.analysis import analyze_suppliers
from src.supplier_matching.matcher import SupplierMatcher
from src.supplier_matching.normalization import normalize_supplier
from tests.synthetic_org import org


def engine(*names, organization_numbers=None):
    if organization_numbers is None:
        organization_numbers = [org(i + 1) for i in range(len(names))]
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': names, 'organization_number': organization_numbers,
    }))
    return SupplierMatcher(registry.suppliers)


FALSE_STRONG_CASES = [
    pytest.param('ATEA Stockholm Sverige AB', 'Telia Stockholm Sverige AB',
                 0.941176, id='distinctive-first'),
    pytest.param('Stockholm ATEA Sverige AB', 'Stockholm Telia Sverige AB',
                 0.941176, id='distinctive-middle'),
    pytest.param('Stockholm Sverige ATEA AB', 'Stockholm Sverige Telia AB',
                 0.941176, id='distinctive-last'),
    pytest.param('ATEA Stockholm Sverige Aktiebolag', 'Telia Stockholm Sverige AB',
                 0.941176, id='equivalent-legal-suffix'),
    pytest.param('Acme Medical Global AB', 'Acne Medical Global AB',
                 0.954545, id='short-distinctive-name-difference'),
    pytest.param('Halland Energileveranser Sverige AB', 'Holland Energileveranser Sverige AB',
                 0.971429, id='geography-can-distinguish-identities'),
]


@pytest.mark.parametrize('reverse', [False, True], ids=['source-first', 'registry-first'])
@pytest.mark.parametrize('source, candidate, score', FALSE_STRONG_CASES)
def test_high_score_candidates_preserve_original_names_and_evidence(source, candidate, score, reverse):
    # These fixtures describe distinct identities, not approved supplier aliases.
    if reverse:
        source, candidate = candidate, source
    result = engine(candidate).match(source)
    assert result.supplier_text_raw == source
    assert result.score == pytest.approx(score, abs=1e-6)
    assert result.method == 'fuzzy'
    assert len(result.candidates) == 1
    assert result.candidates[0].matched_name == candidate
    assert result.candidates[0].reason


@pytest.mark.parametrize('reverse', [False, True], ids=['source-first', 'registry-first'])
@pytest.mark.parametrize('source, candidate, _score', FALSE_STRONG_CASES)
def test_conflicting_name_tokens_require_review_despite_high_score(source, candidate, _score, reverse):
    if reverse:
        source, candidate = candidate, source
    result = engine(candidate).match(source)
    assert result.status == 'AMBIGUOUS_MATCH'
    assert not result.candidates[0].strong_eligible
    assert 'särskiljande namnled skiljer sig åt' in result.reason


@pytest.mark.parametrize('source, candidate, expected', [
    ('ATEA Sverige AB', 'Telia Sverige AB', 'AMBIGUOUS_MATCH'),
    ('ATEA AB', 'Telia AB', 'NO_MATCH'),
    ('Syntetisk Stockholm Service AB', 'Syntetisk Göteborg Service AB', 'AMBIGUOUS_MATCH'),
])
def test_existing_conservative_results_with_shared_tokens_remain(source, candidate, expected):
    result = engine(candidate).match(source)
    assert result.status == expected
    if result.candidates:
        assert all(not candidate.strong_eligible for candidate in result.candidates)
    if source == 'ATEA Sverige AB':
        assert result.score == pytest.approx(0.903226, abs=1e-6)


@pytest.mark.parametrize('source, candidate', [
    ('Securtas Sverige AB', 'Securitas Sverige AB'),
    ('Securitas Svergie AB', 'Securitas Sverige AB'),
    ('Syntetiska Utrusnting AB', 'Syntetiska Utrustning AB'),
    ('Stockholm Securtas Sverige AB', 'Stockholm Securitas Sverige AB'),
    ('Sverige Stockholm Securtas AB', 'Sverige Stockholm Securitas AB'),
])
def test_existing_supported_spelling_variations_remain_strong(source, candidate):
    result = engine(candidate).match(source)
    assert result.status == 'STRONG_MATCH'
    assert result.method == 'fuzzy'
    assert len(result.candidates) == 1
    assert result.candidates[0].strong_eligible


@pytest.mark.parametrize('source, candidate', [
    ('ATEA Stockholm Sverige AB', 'ATEA Stockholm Sverige AB'),
    ('Sverige AB', 'Sverige AB'),
    ('  TELIA   Sverige Aktiebolag. ', 'Telia Sverige AB'),
    ('Syntetisk Kontroll Handelsbolag', 'Syntetisk Kontroll HB'),
    ('Syntetisk Kontroll Kommanditbolag', 'Syntetisk Kontroll KB'),
    ('Taxi Göteborg ekonomisk förening', 'Taxi Göteborg ek för'),
])
def test_exact_and_equivalent_legal_forms_remain_strong(source, candidate):
    result = engine(candidate).match(source)
    assert result.status == 'STRONG_MATCH'
    assert result.method == 'exact_normalized'
    assert result.score == 1
    assert result.supplier_text_raw == source


def test_normalization_keeps_geographic_name_information():
    assert normalize_supplier('ATEA Stockholm Sverige Aktiebolag') == 'atea stockholm sverige ab'
    assert normalize_supplier('Syntetisk Stockholm Service AB') != normalize_supplier(
        'Syntetisk Göteborg Service AB')


@pytest.mark.parametrize('source, candidate', [
    ('Syntetisk Medical Sverige HB', 'Syntetisk Medical Sverige KB'),
    ('Syntetisk Medical Sverige AB', 'Syntetisk Medical Sverige HB'),
])
def test_different_legal_forms_remain_ambiguous(source, candidate):
    result = engine(candidate).match(source)
    assert result.status == 'AMBIGUOUS_MATCH'
    assert len(result.candidates) == 1
    assert not result.candidates[0].strong_eligible
    assert 'Olika bolagsformer' in result.candidates[0].reason


def test_exact_name_without_organization_number_remains_ambiguous():
    result = engine('ATEA Stockholm Sverige AB', organization_numbers=[None]).match(
        'ATEA Stockholm Sverige AB')
    assert result.score == 1
    assert result.status == 'AMBIGUOUS_MATCH'
    assert not result.candidates[0].strong_eligible


@pytest.mark.parametrize('names', list(permutations([
    'ATEA Stockholm Sverige AB', 'Telia Stockholm Sverige AB',
])))
@pytest.mark.parametrize('source', ['ATEA Stockholm Sverige AB', 'Telia Stockholm Sverige AB'])
def test_unique_exact_identity_takes_priority_over_phase2_rejected_alternative(source, names):
    result = engine(*names).match(source)
    # Phase 3B explicitly permits this exception; Phase 2 still rejects the alternative.
    assert result.status == 'STRONG_MATCH'
    assert result.score == 1  # Even a perfect first-candidate score is not identity probability.
    assert len(result.candidates) == 2
    assert {candidate.matched_name for candidate in result.candidates} == set(names)
    assert result.candidates[0].matched_name == source
    assert result.candidates[0].method == 'exact_normalized'
    assert result.candidates[1].method == 'fuzzy'
    assert not result.candidates[1].strong_eligible
    assert result.selected_supplier_key == result.candidates[0].supplier.key
    assert all(candidate.reason for candidate in result.candidates)


@pytest.mark.parametrize('names', list(permutations([
    'Acne Medical Global AB', 'Acme Medical Gloabl AB',
])))
def test_explicit_same_organization_aliases_keep_one_identity_and_all_contract_rows(names):
    # Unlike the conflicting-identity fixture, the register explicitly assigns
    # both aliases to one entity. Inspect the reliable alias before alias reduction,
    # regardless of register order.
    result = engine(*names, organization_numbers=[org(1), org(1)]).match('Acme Medical Global AB')
    assert result.status == 'STRONG_MATCH'
    assert len(result.candidates) == 1
    assert result.candidates[0].supplier.organization_number == org(1)
    assert result.candidates[0].matched_name == 'Acme Medical Gloabl AB'
    assert len(result.candidates[0].supplier.contracts) == 2


@pytest.fixture
def false_strong_source_analysis():
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': ['Telia Stockholm Sverige AB'] * 2,
        'organization_number': [org(1)] * 2,
        'contract_id': ['synthetic-contract-1', 'synthetic-contract-2'],
    }))
    source = pd.DataFrame({
        'verification_id': ['repeated'] * 2,
        'header_text': ['ATEA Stockholm Sverige AB Prelb 1'] * 2,
    }, index=[11, 31])
    before = source.copy(deep=True)
    analysis = analyze_suppliers(source, registry)
    return source, before, analysis


def test_high_score_analysis_preserves_all_source_occurrences(false_strong_source_analysis):
    source, before, analysis = false_strong_source_analysis
    pd.testing.assert_frame_equal(source, before)
    assert analysis.rows.source_row_position.tolist() == [11, 31]
    assert analysis.candidates.source_row_position.tolist() == [11, 31]
    assert analysis.contracts.source_row_position.tolist() == [11, 11, 31, 31]


def test_false_strong_match_must_not_select_an_entity(false_strong_source_analysis):
    _, _, analysis = false_strong_source_analysis
    assert analysis.rows.supplier_match_status.eq('AMBIGUOUS_MATCH').all()
    assert analysis.rows.matched_supplier_name.isna().all()
    assert analysis.rows.matched_organization_number.isna().all()


@pytest.mark.parametrize('reverse', [False, True], ids=['source-first', 'registry-first'])
@pytest.mark.parametrize('source_tokens, candidate_tokens, expected', [
    pytest.param('abcdef', 'abcxdef', 'STRONG_MATCH', id='six-character-minimum-insertion'),
    pytest.param('abcde', 'abcxde', 'AMBIGUOUS_MATCH', id='five-characters-too-short'),
    pytest.param('abcdefghij', 'abcdxfghij', 'STRONG_MATCH', id='substitution-at-point-nine'),
    pytest.param('abcdefghi', 'abcdxfghi', 'AMBIGUOUS_MATCH', id='substitution-below-point-nine'),
    pytest.param('abcdef', 'abdcef', 'STRONG_MATCH', id='adjacent-transposition-exception'),
    pytest.param('abcde', 'abdce', 'AMBIGUOUS_MATCH', id='short-transposition-rejected'),
    pytest.param('abcdefghijklmnopqrst', 'abcdxfghijklmnypqrst', 'AMBIGUOUS_MATCH',
                 id='two-substitutions-despite-high-token-score'),
    pytest.param('abcdefghijklmnopqrst', 'abedcfghijklmnopqrst', 'AMBIGUOUS_MATCH',
                 id='nonadjacent-swap'),
    pytest.param('Leverantoren Utrustning', 'Leverantorer Utrustnig', 'AMBIGUOUS_MATCH',
                 id='two-individually-plausible-typos'),
    pytest.param('Nord Nord Syd', 'Nord Syd Syd', 'AMBIGUOUS_MATCH',
                 id='duplicate-counts-must-not-disappear'),
    pytest.param('Securtas Securitas', 'Securitas Securitas', 'STRONG_MATCH',
                 id='one-typo-next-to-repeated-token'),
    pytest.param('Nord Nord Syd', 'Nord Syd Nord', 'STRONG_MATCH',
                 id='identical-token-multiset-different-positions'),
])
def test_token_safeguard_boundaries_and_multiplicity(source_tokens, candidate_tokens, expected, reverse):
    # Long shared context deliberately makes the old whole-name score high.
    # Token strings are synthetic, not a catalogue of approved real-world aliases.
    suffix = ' Internationella Medicintekniska Utrustningsleveranser Stockholm Sverige AB'
    source, candidate = source_tokens + suffix, candidate_tokens + suffix
    if reverse:
        source, candidate = candidate, source
    result = engine(candidate).match(source)
    assert result.method == 'fuzzy'
    assert result.score >= 0.94
    assert result.status == expected
    assert len(result.candidates) == 1
    assert result.candidates[0].matched_name == candidate
    assert result.candidates[0].strong_eligible == (expected == 'STRONG_MATCH')


def test_plausible_short_spelling_error_is_conservatively_downgraded():
    result = engine('Acme Medical Global AB').match('Acem Medical Global AB')
    assert result.score == pytest.approx(0.954545, abs=1e-6)
    assert result.status == 'AMBIGUOUS_MATCH'
    assert len(result.candidates) == 1
    assert 'särskiljande namnled skiljer sig åt' in result.reason


def test_identical_token_multiset_does_not_bypass_existing_raw_score_threshold():
    suffix = ' Internationella Utrustningsleveranser Stockholm Sverige AB'
    result = engine('Nord Syd Nord' + suffix).match('Nord Nord Syd' + suffix)
    assert result.score == pytest.approx(0.930556, abs=1e-6)
    assert result.status == 'AMBIGUOUS_MATCH'
