"""Approved Phase 3B decisions with synthetic register identities only."""
from itertools import permutations

import pandas as pd
import pytest

from src.ingestion.contract_reader import registry_from_frame
from src.supplier_matching.matcher import SupplierMatcher
from tests.synthetic_org import org


CASES = [
    pytest.param('Bonliva AB', [('Bonliva AB', org(101))], 'STRONG_MATCH', 1, id='A-single-exact'),
    pytest.param('Bonliva AB', [('Bonliva AB', org(101)), ('Bonliva Care AB', org(202)),
                              ('Bonliva Sverige AB', org(303))], 'STRONG_MATCH', 3, id='B-weaker-alternatives'),
    pytest.param('Telia Sverige AB', [('Telia Sverige AB', org(101)), ('TELIA Sverige Aktiebolag.', org(202))],
                 'AMBIGUOUS_MATCH', 2, id='C-exact-collision'),
    # Phase 3C: the former 1212121212 has personal-number form. Keep D's valid-alias intent.
    pytest.param('Bonliva AB', [('Bonliva AB', f'{org(121)[:6]}-{org(121)[6:]}'), ('Bonliva Aktiebolag', org(121)),
                              ('Bonliva Care AB', org(121))], 'STRONG_MATCH', 1, id='D-same-organization'),
    pytest.param('Bonliva AB', [('Bonliva AB', None)], 'AMBIGUOUS_MATCH', 1, id='E-no-organization'),
    pytest.param('Securitas Sverige AB', [('Securitas Sverige AB', org(101)), ('Securitas Svergie AB', org(202))],
                 'AMBIGUOUS_MATCH', 2, id='F-strong-fuzzy-competitor'),
    pytest.param('ATEA Stockholm Sverige AB', [('ATEA Stockholm Sverige AB', org(101)),
                 ('Telia Stockholm Sverige AB', org(202))], 'STRONG_MATCH', 2, id='G-exact-atea-weaker-telia'),
    pytest.param('ATEA Stockholm Sverige AB', [('Telia Stockholm Sverige AB', org(202))],
                 'AMBIGUOUS_MATCH', 1, id='H-phase2-no-exact'),
    pytest.param('Bonliva AB', [('Bonliva AB', org(101)), ('Bonliva AB', org(202))],
                 'AMBIGUOUS_MATCH', 2, id='I-identical-name-different-organizations'),
    pytest.param('Bonliva AB', [('Bonliva AB', org(101)), ('Bonliva Aktiebolag', None)],
                 'AMBIGUOUS_MATCH', 2, id='J-numberless-exact-collision'),
    pytest.param('Bonliva AB', [('Bonliva AB', org(101)), ('Bonliva Care AB', None)],
                 'STRONG_MATCH', 2, id='numberless-nonexact-alternative'),
    pytest.param('Securitas Sverige', [('Securitas Sverige', org(101)), ('Securitas Sverige AB', org(202))],
                 'AMBIGUOUS_MATCH', 2, id='strong-prefix-alternative-also-blocks'),
]


@pytest.mark.parametrize('reverse', [False, True], ids=['register-order', 'reversed-order'])
@pytest.mark.parametrize('query, rows, expected, count', CASES)
def test_approved_exact_priority_and_conservative_conflicts(query, rows, expected, count, reverse):
    rows = list(reversed(rows)) if reverse else rows
    frame = pd.DataFrame(rows, columns=['supplier_name', 'organization_number'])
    before = frame.copy(deep=True)
    registry = registry_from_frame(frame)
    result = SupplierMatcher(registry.suppliers).match(query)
    assert result.status == expected
    assert len(result.candidates) == count
    if expected == 'STRONG_MATCH':
        selected = next(c for c in result.candidates if c.supplier.key == result.selected_supplier_key)
        assert selected.method == 'exact_normalized'
        assert selected.strong_eligible and selected.score == result.score == 1
        assert selected.supplier.organization_number
        assert not any(c.strong_eligible for c in result.candidates if c is not selected)
        assert not any(c.name_strong for c in result.candidates if c is not selected)
    else:
        assert result.selected_supplier_key is None
    pd.testing.assert_frame_equal(frame, before)


def test_all_orders_keep_candidates_scores_and_selected_identity():
    rows = [('Bonliva AB', org(101)), ('Bonliva Care AB', org(202)), ('Bonliva Sverige AB', org(303))]
    for order in permutations(rows):
        registry = registry_from_frame(pd.DataFrame(order, columns=['supplier_name', 'organization_number']))
        engine = SupplierMatcher(registry.suppliers)
        result = engine.match('Bonliva AB')
        assert result.selected_supplier_key == f'org:{org(101)}'
        assert [(c.supplier.key, c.method, c.score, c.strong_eligible) for c in result.candidates] == [
            (f'org:{org(101)}', 'exact_normalized', 1, True), (f'org:{org(202)}', 'related_name', 0.8, False),
            (f'org:{org(303)}', 'related_name', 0.714286, False)]
        assert 'svagare alternativa kandidater' in result.reason
        cached = engine.match(' BONLIVA Aktiebolag. ')
        assert cached.selected_supplier_key == result.selected_supplier_key
        assert cached.candidates == result.candidates
        assert cached.supplier_text_raw == ' BONLIVA Aktiebolag. '


@pytest.mark.parametrize('missing', [None, '', '  ', True])
def test_any_numberless_exact_record_blocks_otherwise_unique_identity(missing):
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': ['Bonliva AB', 'Bonliva Aktiebolag'], 'organization_number': [org(101), missing]}))
    result = SupplierMatcher(registry.suppliers).match('Bonliva AB')
    assert result.status == 'AMBIGUOUS_MATCH'
    assert result.selected_supplier_key is None
    assert len(result.candidates) == 2


@pytest.mark.parametrize('aliases', list(permutations(['Acne Medical Global AB', 'Acme Medical Gloabl AB'])))
def test_any_strong_eligible_alias_of_competing_identity_blocks_exact_priority(aliases):
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': ['Acme Medical Global AB', *aliases], 'organization_number': [org(101), org(202), org(202)]}))
    result = SupplierMatcher(registry.suppliers).match('Acme Medical Global AB')
    assert result.status == 'AMBIGUOUS_MATCH'
    assert result.selected_supplier_key is None
    competitor = next(c for c in result.candidates if c.supplier.key == f'org:{org(202)}')
    assert competitor.strong_eligible and competitor.matched_name == 'Acme Medical Gloabl AB'
    assert len(competitor.supplier.contracts) == 2


def test_exact_priority_does_not_promote_multiple_fuzzy_candidates():
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': ['Securitas Sverige AB', 'Securitas Svergie AB'], 'organization_number': [org(101), org(202)]}))
    result = SupplierMatcher(registry.suppliers).match('Securtas Sverige AB')
    assert result.status == 'AMBIGUOUS_MATCH'
    assert result.selected_supplier_key is None
    assert all(c.method != 'exact_normalized' for c in result.candidates)
