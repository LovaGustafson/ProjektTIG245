"""Phase 3D.1: supplier-name structure and candidate relevance; synthetic data only.

Company names are illustrative or invented; no rule depends on a specific name.
"""
from difflib import SequenceMatcher
from itertools import permutations

import pandas as pd
import pytest

from src.ingestion.contract_reader import registry_from_frame
from src.supplier_matching.analysis import analyze_suppliers
from src.supplier_matching.matcher import SupplierMatcher
from src.supplier_matching.name_structure import analyze_name_structure, distinctive_names_related
from src.supplier_matching.normalization import normalize_supplier
from src.supplier_matching.settings import MatchSettings
from tests.synthetic_org import org

DESCRIPTORS = MatchSettings().geographic_descriptors


def structure(name):
    return analyze_name_structure(normalize_supplier(name), DESCRIPTORS)


def full_score(left, right):
    return SequenceMatcher(None, normalize_supplier(left), normalize_supplier(right), autojunk=False).ratio()


def match(query, rows):
    """Match in every register order; the decision must never depend on row order."""
    results = []
    for order in permutations(rows):
        frame = pd.DataFrame(list(order), columns=['supplier_name', 'organization_number'])
        result = SupplierMatcher(registry_from_frame(frame).suppliers).match(query)
        results.append(result)
    # unknown:<row position> keys legitimately follow row order; compare by number and name.
    summaries = {(r.status.value, r.selected_supplier_key if r.selected_supplier_key is None
                  or r.selected_supplier_key.startswith('org:') else 'unknown',
                  tuple(sorted((c.supplier.organization_number or '', c.matched_name, c.method, c.score,
                                c.name_strong, c.strong_eligible) for c in r.candidates))) for r in results}
    assert len(summaries) == 1, summaries
    return results[0]


def names(result):
    return sorted(c.matched_name for c in result.candidates)


# --- Name structure ---------------------------------------------------------------

@pytest.mark.parametrize('name, distinctive, descriptors, legal_form', [
    ('Securitas Sverige AB', ('securitas',), ('sverige',), 'ab'),
    ('Securitas Aktiebolaget', ('securitas',), (), 'ab'),
    ('Nordviks Bygg Svergie AB', ('nordviks', 'bygg'), ('svergie',), 'ab'),
    ('Securitas Sveri', ('securitas',), ('sveri',), None),
    ('Lindqvist Konsult HB', ('lindqvist', 'konsult'), (), 'hb'),
    ('Kontor2 Sverige KB', ('kontor2',), ('sverige',), 'kb'),
    ('Åkeriet Öst Sverige AB', ('åkeriet', 'öst'), ('sverige',), 'ab'),
])
def test_structure_separates_distinctive_name_descriptors_and_legal_form(name, distinctive, descriptors, legal_form):
    result = structure(name)
    assert result.distinctive_tokens == distinctive
    assert result.descriptor_tokens == descriptors
    assert result.legal_form == legal_form


@pytest.mark.parametrize('name, distinctive', [
    ('Sverige Trafik AB', ('sverige', 'trafik')),       # a leading geographic word is the name
    ('Sverige AB', ('sverige',)),                        # nothing but generic words: keep the name
    ('Göteborg Energi AB', ('göteborg', 'energi')),      # only configured descriptors are generic
    ('Alfa Sverige Logistik AB', ('alfa', 'logistik')),
    ('Alfa Sv', ('alfa', 'sv')),                         # too short to stand for a descriptor
    ('Alfa Sver Logistik AB', ('alfa', 'sver', 'logistik')),  # truncation only for the final word
    ('Synologen Servi', ('synologen', 'servi')),         # Servi is not a form of Sverige
    ('Alfa Sverigeservice AB', ('alfa', 'sverigeservice')),
])
def test_structure_keeps_meaningful_tokens(name, distinctive):
    assert structure(name).distinctive_tokens == distinctive


def test_legal_forms_stay_distinct_and_original_names_are_unchanged():
    original = 'Nordviks  Bygg, Aktiebolag'
    copy = str(original)
    assert structure(original).legal_form == 'ab'
    assert {structure(f'Nordviks Bygg {form}').legal_form for form in ('AB', 'HB', 'KB')} == {'ab', 'hb', 'kb'}
    assert original == copy


@pytest.mark.parametrize('descriptors', ['Sverige', ['Göteborg Stad'], ['AB'], [''], [3]])
def test_descriptor_setting_is_validated(descriptors):
    with pytest.raises(ValueError):
        MatchSettings(geographic_descriptors=descriptors)


def test_descriptor_setting_is_normalized():
    assert MatchSettings(geographic_descriptors=[' SVERIGE ', 'sverige']).geographic_descriptors == ('sverige',)
    assert MatchSettings().geographic_descriptors == ('sverige',)


@pytest.mark.parametrize('left, right, related', [
    ('Atea Sverige AB', 'Tele2 Sverige AB', False),
    ('Atea Sverige AB', 'Gartner Sverige AB', False),
    ('Securitas Sverige AB', 'Secure Sverige AB', False),
    ('Telia AB', 'Teli AB', True),
    ('Abc AB', 'Abd AB', True),
    ('Kontor2 Sverige AB', 'Kontor3 Sverige AB', True),
    ('Åkeriet Öst AB', 'Akeriet Ost AB', True),
    ('Bra Sverige AB', 'Bra Bygg Sverige AB', True),
    ('Lindqvist Konsult AB', 'Lundqvist Konsult AB', True),
])
def test_distinctive_relatedness_is_symmetric(left, right, related):
    assert distinctive_names_related(structure(left), structure(right), 0.82) is related
    assert distinctive_names_related(structure(right), structure(left), 0.82) is related


# --- A. Unrelated names sharing generic words -------------------------------------

@pytest.mark.parametrize('query, register', [
    ('Atea Sverige AB', 'Tele2 Sverige AB'),
    ('Atea Sverige AB', 'Gartner Sverige AB'),
    ('Securitas Sverige AB', 'Secure Sverige AB'),
    ('ATEA Sverige AB', 'Telia Sverige AB'),
    ('Brisk Sverige AB', 'Orka Sverige AB'),
    ('Lyra Sverige Aktiebolag', 'Tumla Sverige AB'),
    ('Nexo Sverige AB', 'Pento Sverige AB'),
])
def test_shared_generic_words_no_longer_create_candidates(query, register):
    # Precondition: the unchanged full-name score alone would have created a candidate.
    assert full_score(query, register) >= MatchSettings().fuzzy_candidate_threshold
    result = match(query, [(register, org(2))])
    assert result.status.value == 'NO_MATCH'
    assert result.candidates == ()


def test_previously_discovered_unrelated_pairs_had_high_full_name_scores():
    # Documents why they used to be candidates; the score calculation itself is unchanged.
    assert full_score('Atea Sverige AB', 'Tele2 Sverige AB') == pytest.approx(0.838710, abs=1e-6)
    assert full_score('Atea Sverige AB', 'Gartner Sverige AB') == pytest.approx(0.848485, abs=1e-6)
    assert full_score('Securitas Sverige AB', 'Secure Sverige AB') == pytest.approx(0.864865, abs=1e-6)


def test_names_without_shared_generic_words_stay_unrelated():
    assert match('Telia AB', [('Volvo Cars AB', org(2))]).status.value == 'NO_MATCH'
    assert match('Securitas Sverige', [('Secure Sverige AB', org(2))]).status.value == 'NO_MATCH'


# --- B. Same distinctive name, different legal designation -------------------------

def test_equivalent_legal_designations_remain_exact():
    for query, register in [('Securitas AB', 'Securitas Aktiebolaget'), ('Nordviks Bygg AB', 'Nordviks Bygg Aktiebolag')]:
        result = match(query, [(register, org(1))])
        assert result.status.value == 'STRONG_MATCH' and result.method == 'exact_normalized'


@pytest.mark.parametrize('query, register', [('Nordviks Bygg HB', 'Nordviks Bygg AB'),
                                             ('Nordviks Bygg HB', 'Nordviks Bygg KB')])
def test_different_legal_forms_are_not_interchangeable(query, register):
    result = match(query, [(register, org(1))])
    assert result.status.value == 'AMBIGUOUS_MATCH'
    assert names(result) == [register]
    assert 'Olika bolagsformer' in result.candidates[0].reason


# --- C. Geographic descriptors and variations (no new promotion in 3D.1) ------------

@pytest.mark.parametrize('query, register, method', [
    ('Securitas Sveri', 'Securitas Sverige AB', 'prefix'),
    ('Securitas Svergie', 'Securitas Sverige', 'fuzzy'),
    ('Nordviks Bygg Svergie AB', 'Nordviks Bygg Sverige AB', 'fuzzy'),
])
def test_existing_strong_descriptor_variations_are_unchanged(query, register, method):
    result = match(query, [(register, org(1))])
    assert result.status.value == 'STRONG_MATCH' and result.method == method


@pytest.mark.parametrize('query, register, expected', [
    ('Securitas Sverige AB', 'Securitas Sverige', 'AMBIGUOUS_MATCH'),
    ('Nordviks Bygg Sverige AB', 'Nordviks Bygg AB', 'AMBIGUOUS_MATCH'),
    ('Telia AB', 'Telia Sverige Aktiebolag', 'NO_MATCH'),
    ('Atea Sverige AB', 'Atea Aktiebolaget', 'NO_MATCH'),
])
def test_descriptor_differences_are_not_yet_promoted(query, register, expected):
    # Phase 3D.2 decides any strong-match policy for these; 3D.1 must not change them.
    assert match(query, [(register, org(1))]).status.value == expected


# --- D, I, J, K. Plausible spelling variants stay discoverable ---------------------

@pytest.mark.parametrize('query, register, score', [
    ('Telia AB', 'Teli AB', 0.933333),                       # short distinctive name
    ('Abc AB', 'Abd AB', 0.833333),                          # very short name, one substitution
    ('Lindqvist Konsult AB', 'Lundqvist Konsult AB', 0.95),  # distinctive-name spelling
    ('Kontor2 Sverige AB', 'Kontor3 Sverige AB', 0.944444),  # digits
    ('Tele2 Sverige AB', 'Tele 2 Sverige AB', 0.969697),     # digits with spacing
    ('Åkeriet Öst AB', 'Akeriet Ost AB', 0.857143),          # Swedish characters
])
def test_plausible_variants_remain_ambiguous_candidates_with_unchanged_scores(query, register, score):
    result = match(query, [(register, org(2))])
    assert result.status.value == 'AMBIGUOUS_MATCH'
    assert names(result) == [register]
    assert result.candidates[0].score == pytest.approx(score, abs=1e-6)
    assert not result.candidates[0].name_strong


# --- E. Additional distinctive words ----------------------------------------------

@pytest.mark.parametrize('query, register', [
    ('Securitas Sverige AB', 'Securitas Technology AB'),
    ('Bra Sverige AB', 'Bra Bygg Sverige AB'),
    ('Nordic Medical AB', 'Nordic Medical Supply AB'),
])
def test_additional_distinctive_words_stay_separate_reviewable_candidates(query, register):
    result = match(query, [(register, org(2))])
    assert result.status.value == 'AMBIGUOUS_MATCH'
    assert names(result) == [register]
    assert not result.candidates[0].name_strong


# --- L. Geographic words that are themselves distinctive ---------------------------

def test_distinctive_geographic_words_keep_candidates_related():
    assert names(match('Sverige Trafik AB', [('Sverige Transport AB', org(2))])) == ['Sverige Transport AB']
    result = match('Göteborg Energi AB', [('Göteborg Energi Sverige AB', org(1)), ('Stockholm Energi AB', org(2))])
    assert result.status.value == 'AMBIGUOUS_MATCH'
    assert names(result) == ['Göteborg Energi Sverige AB']


# --- F, G, H, M, N, O. Identities, organization numbers and selection safety -------

def test_exact_match_drops_irrelevant_alternatives_and_keeps_contract_isolation():
    rows = [('Atea Sverige AB', org(1)), ('Tele2 Sverige AB', org(2)), ('Gartner Sverige AB', org(3))]
    result = match('Atea Sverige AB', rows)
    assert result.status.value == 'STRONG_MATCH' and result.selected_supplier_key == f'org:{org(1)}'
    assert names(result) == ['Atea Sverige AB']
    frame = pd.DataFrame({'supplier_name': [r[0] for r in rows], 'organization_number': [r[1] for r in rows],
                          'contract_id': ['C1', 'C2', 'C3'], 'start_date': ['2026-01-01'] * 3,
                          'end_date': ['2026-12-31'] * 3})
    source = pd.DataFrame({'header_text': ['Atea Sverige AB Prelb 1'], 'verification_date': ['2026-06-15']})
    analysis = analyze_suppliers(source, registry_from_frame(frame))
    assert analysis.rows.candidate_count.tolist() == [1]
    assert analysis.contracts.contract_id.tolist() == ['C1']
    assert analysis.contracts.contract_period_status.tolist() == ['PASS']


def test_relevant_alternatives_with_other_valid_numbers_are_kept_beside_exact_match():
    result = match('Bolt Sverige AB', [('Bolt Sverige AB', org(1)), ('Bolta Sverige AB', org(2)),
                                       ('Kolt Sverige HB', org(3)), ('Tumla Sverige AB', org(4))])
    assert result.status.value == 'STRONG_MATCH' and result.selected_supplier_key == f'org:{org(1)}'
    assert names(result) == ['Bolt Sverige AB', 'Bolta Sverige AB', 'Kolt Sverige HB']
    assert len({c.supplier.key for c in result.candidates}) == 3


@pytest.mark.parametrize('identifier', [None, 'SAKNAS', '1212121212', '-' + org(9)])
def test_relevant_strong_names_without_usable_numbers_still_block(identifier):
    result = match('Securitas Sverige AB', [('Securitas Sverige AB', org(1)), ('Securitas Svergie AB', identifier)])
    assert result.status.value == 'AMBIGUOUS_MATCH' and result.selected_supplier_key is None
    assert len(result.candidates) == 2


@pytest.mark.parametrize('identifier', [None, 'SAKNAS', org(2)])
def test_irrelevant_candidates_are_dropped_whatever_their_number(identifier):
    assert match('Atea Sverige AB', [('Tele2 Sverige AB', identifier)]).candidates == ()


def test_strong_named_competitors_are_never_filtered():
    result = match('Gartner Sverige AB', [('Gartner Sverige AB', org(1)), ('Gartner Svergie AB', org(2))])
    assert result.status.value == 'AMBIGUOUS_MATCH'
    assert names(result) == sorted(['Gartner Sverige AB', 'Gartner Svergie AB'])
    assert all(c.name_strong for c in result.candidates)


def test_genuine_competing_spelling_variant_still_blocks_a_prefix_match():
    result = match('Brio Sverige', [('Brio Sverige AB', org(1)), ('Brio Sverie AB', org(2))])
    assert result.status.value == 'AMBIGUOUS_MATCH'
    assert len(result.candidates) == 2


@pytest.mark.parametrize('query, rows', [
    ('Atea Sverige', [('Atea Sverige AB', org(1)), ('Vexa Sverige', org(2))]),
    ('Gartner Sverige AB', [('Atea Sverige AB', org(1)), ('Gartner Svergie AB', org(2))]),
])
def test_filtering_never_promotes_an_ambiguous_row(query, rows):
    """Corrected after independent review: an earlier version of this test required
    STRONG_MATCH here, i.e. an indirect promotion caused only by removing an unrelated
    candidate. Phase 3D.1 must not change decisions, so the full candidate set is kept
    whenever filtering would alter the selection."""
    result = match(query, rows)
    assert result.status.value == 'AMBIGUOUS_MATCH' and result.selected_supplier_key is None
    assert names(result) == sorted(name for name, _ in rows)
    frame = pd.DataFrame({'supplier_name': [r[0] for r in rows], 'organization_number': [r[1] for r in rows],
                          'contract_id': ['C1', 'C2'], 'start_date': ['2026-01-01'] * 2,
                          'end_date': ['2026-12-31'] * 2})
    source = pd.DataFrame({'header_text': [f'{query} Prelb 1'], 'verification_date': ['2026-06-15']})
    analysis = analyze_suppliers(source, registry_from_frame(frame))  # invariant re-check passes
    assert analysis.contracts.contract_period_status.tolist() == ['NOT_CHECKED'] * 2


def test_matching_is_deterministic_across_repeated_calls():
    rows = [('Atea Sverige AB', org(1)), ('Tele2 Sverige AB', org(2)), ('Teli AB', org(3))]
    frame = pd.DataFrame(rows, columns=['supplier_name', 'organization_number'])
    engine = SupplierMatcher(registry_from_frame(frame).suppliers)
    first = [engine.match(q) for q in ('Atea Sverige AB', 'Telia AB', 'ATEA  sverige ab.')]
    second = [engine.match(q) for q in ('Atea Sverige AB', 'Telia AB', 'ATEA  sverige ab.')]
    assert first == second
    assert first[0].status == first[2].status and names(first[0]) == names(first[2])
