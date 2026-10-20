"""Phase 3C name evidence and identity eligibility use synthetic registers only."""
from itertools import permutations

import pandas as pd
import pytest

from src.ingestion.contract_reader import registry_from_frame
from src.supplier_matching.matcher import SupplierMatcher, select_strong_candidate
from tests.synthetic_org import org
from tests.test_supplier_exact_priority import CASES


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('query, rows, expected, count', CASES)
def test_selection_function_preserves_phase3b_decisions_in_any_candidate_order(query, rows, expected, count, reverse):
    frame = pd.DataFrame(list(reversed(rows)) if reverse else rows,
                         columns=['supplier_name', 'organization_number'])
    result = SupplierMatcher(registry_from_frame(frame).suppliers).match(query)
    assert result.status == expected
    assert len(result.candidates) == count
    for order in permutations(result.candidates):
        selected = select_strong_candidate(order)
        assert (selected is not None) == (expected == 'STRONG_MATCH')
        assert (selected.supplier.key if selected else None) == result.selected_supplier_key


def test_empty_candidate_set_has_no_selected_identity():
    assert select_strong_candidate(()) is None


UNUSABLE_IDENTIFIERS = [
    pytest.param(None, 'MISSING', id='missing'),
    pytest.param('', 'MISSING', id='empty'),
    pytest.param('  ', 'MISSING', id='blank'),
    pytest.param('SAKNAS', 'INVALID_FORMAT', id='placeholder'),
    pytest.param('N/A', 'INVALID_FORMAT', id='not-applicable'),
    pytest.param('5590002028', 'INVALID_CHECKSUM', id='checksum'),
    pytest.param('202', 'INVALID_FORMAT', id='short-format'),
    pytest.param('1212121212', 'NOT_ORGANIZATION_NUMBER_FORMAT', id='personal-number-form'),
    pytest.param('0000000000', 'NOT_ORGANIZATION_NUMBER_FORMAT', id='zeros'),
    pytest.param('165590002027', 'INVALID_FORMAT', id='twelve-digits'),
    pytest.param('NO5590002027', 'INVALID_FORMAT', id='foreign-format'),
]
STRONG_NAMES = [
    pytest.param('Securitas Sverige AB', 'Securitas Svergie AB', 'fuzzy', 0.95, id='fuzzy'),
    pytest.param('Securitas Sverige', 'Securitas Sverige AB', 'prefix', 0.85, id='prefix'),
    pytest.param('Bonliva AB', 'BONLIVA Aktiebolag.', 'exact_normalized', 1.0, id='exact'),
]


def match_rows(query, rows):
    frame = pd.DataFrame(rows, columns=['supplier_name', 'organization_number'])
    return SupplierMatcher(registry_from_frame(frame).suppliers).match(query)


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('identifier, identifier_status', UNUSABLE_IDENTIFIERS)
@pytest.mark.parametrize('query, competing_name, method, score', STRONG_NAMES)
def test_strong_competing_names_block_even_without_usable_identity(
        query, competing_name, method, score, identifier, identifier_status, reverse):
    rows = [(query, org(101)), (competing_name, identifier)]
    result = match_rows(query, list(reversed(rows)) if reverse else rows)
    assert result.status == 'AMBIGUOUS_MATCH'
    assert result.selected_supplier_key is None
    assert result.score == 1
    assert len(result.candidates) == 2
    exact, competing = result.candidates
    assert exact.supplier.organization_number == org(101)
    assert exact.name_strong and exact.strong_eligible
    assert competing.supplier.organization_number is None
    assert competing.supplier.organization_number_status == identifier_status
    assert competing.name_strong and not competing.strong_eligible
    assert competing.matched_name == competing_name
    assert competing.method == method and competing.score == score
    for order in permutations(result.candidates):
        assert select_strong_candidate(order) is None


@pytest.mark.parametrize('identifier, identifier_status', UNUSABLE_IDENTIFIERS)
@pytest.mark.parametrize('query, name, method, score', [
    ('Bonliva AB', 'Bonliva Care AB', 'related_name', 0.8),
    ('ATEA Stockholm Sverige AB', 'Telia Stockholm Sverige AB', 'fuzzy', 0.941176),
    ('Alpha AB', 'Alpha AB Sverige', 'uncertain_prefix', 0.5),
])
def test_weak_unusable_competitors_do_not_block_unique_valid_exact_match(
        query, name, method, score, identifier, identifier_status):
    result = match_rows(query, [(name, identifier), (query, org(101))])
    assert result.status == 'STRONG_MATCH'
    assert result.selected_supplier_key == f'org:{org(101)}'
    assert len(result.candidates) == 2
    selected, alternative = result.candidates
    assert selected.name_strong and selected.strong_eligible
    assert not alternative.name_strong and not alternative.strong_eligible
    assert alternative.method == method and alternative.score == score
    assert alternative.supplier.organization_number_status == identifier_status
    assert alternative.matched_name == name
    assert select_strong_candidate(tuple(reversed(result.candidates))) is selected


@pytest.mark.parametrize('identifier, identifier_status', UNUSABLE_IDENTIFIERS)
@pytest.mark.parametrize('query, name, method, score', STRONG_NAMES)
def test_strong_name_alone_never_selects_an_unusable_identity(
        query, name, method, score, identifier, identifier_status):
    result = match_rows(query, [(name, identifier)])
    assert result.status == 'AMBIGUOUS_MATCH'
    assert result.selected_supplier_key is None
    assert result.method == method and result.score == score
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.name_strong and not candidate.strong_eligible
    assert candidate.supplier.organization_number is None
    assert candidate.supplier.organization_number_status == identifier_status
    assert select_strong_candidate(result.candidates) is None
    reason = ('Organisationsnummer saknas i registret.' if identifier_status == 'MISSING' else
              'Organisationsnumret i registret är inte ett tekniskt giltigt organisationsnummer.')
    assert candidate.reason.endswith(reason)
    if identifier_status != 'MISSING':
        assert identifier not in candidate.reason


def test_one_eligible_fuzzy_identity_among_weak_alternatives_still_requires_review():
    result = match_rows('Securitas Sverige AB', [
        ('Securitas Svergie AB', org(101)), ('Securitas Care AB', None)])
    assert result.status == 'AMBIGUOUS_MATCH' and result.selected_supplier_key is None
    assert result.candidates[0].name_strong and result.candidates[0].strong_eligible
    assert result.candidates[0].method == 'fuzzy'
    assert not result.candidates[1].name_strong
    assert select_strong_candidate(result.candidates) is None


def test_invalid_weak_alias_cannot_hide_a_separate_strong_competitor():
    rows = [('Securitas Sverige AB', org(101)),
            ('Securitas Care AB', 'SAKNAS'), ('Securitas Svergie AB', 'SAKNAS')]
    for order in permutations(rows):
        result = match_rows('Securitas Sverige AB', order)
        assert result.status == 'AMBIGUOUS_MATCH'
        assert result.selected_supplier_key is None and len(result.candidates) == 3
        assert [(c.matched_name, c.method, c.score, c.name_strong, c.strong_eligible)
                for c in result.candidates] == [
            ('Securitas Sverige AB', 'exact_normalized', 1.0, True, True),
            ('Securitas Svergie AB', 'fuzzy', 0.95, True, False),
            ('Securitas Care AB', 'related_name', 0.810811, False, False),
        ]


def test_identifiers_do_not_change_candidate_scores_order_names_or_cached_name_evidence():
    query = 'Securitas Sverige AB'
    frame = pd.DataFrame({
        'supplier_name': [query, 'Securitas Svergie AB', 'Securitas Care AB'],
        'organization_number': [org(101), org(202), org(303)],
    })
    before = match_rows(query, frame.itertuples(index=False, name=None))
    frame.loc[1:, 'organization_number'] = ['SAKNAS', None]
    engine = SupplierMatcher(registry_from_frame(frame).suppliers)
    after = engine.match(query)
    evidence = lambda r: [(c.matched_name, c.method, c.score, c.name_strong) for c in r.candidates]
    assert evidence(after) == evidence(before)
    assert before.status == after.status == 'AMBIGUOUS_MATCH'
    cached = engine.match(' SECURITAS Sverige Aktiebolag. ')
    assert cached.candidates == after.candidates
    assert cached.status == after.status and cached.selected_supplier_key is None
    assert cached.supplier_text_raw == ' SECURITAS Sverige Aktiebolag. '
