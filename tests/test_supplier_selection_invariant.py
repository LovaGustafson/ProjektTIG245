"""Reject inconsistent matcher decisions before any contract-period assessment."""
from dataclasses import replace
from itertools import permutations
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.ingestion.contract_reader import registry_from_frame
from src.models.supplier import SupplierMatchStatus as Status
from src.supplier_matching.analysis import analyze_suppliers
from src.supplier_matching.contract_period import check_contract_period
from src.supplier_matching.matcher import SupplierMatcher
from tests.synthetic_org import org


def matching_case(query='Bonliva AB', rows=None):
    if rows is None:
        rows = [('Bonliva AB', org(101)), ('Bonliva Care AB', org(202)),
                ('Bonliva Sverige AB', org(303))]
    frame = pd.DataFrame(rows, columns=['supplier_name', 'organization_number'])
    frame['start_date'] = '2026-01-01'
    frame['end_date'] = '2026-12-31'
    registry = registry_from_frame(frame)
    source = pd.DataFrame({'header_text': [f'{query} Prelb 1' if query else None],
                           'verification_id': ['synthetic-source-reference'],
                           'verification_date': ['2026-06-15']}, index=[41])
    return source, registry, SupplierMatcher(registry.suppliers).match(query)


def injected_matcher(result):
    engine = Mock(spec=SupplierMatcher)
    engine.match.return_value = result
    return engine


def assert_rejected_before_contract_assessment(source, registry, result):
    before_source, before_registry = source.copy(deep=True), registry.data.copy(deep=True)
    engine = injected_matcher(result)
    with patch('src.supplier_matching.analysis.check_contract_period', wraps=check_contract_period) as period:
        with pytest.raises(ValueError) as error:
            analyze_suppliers(source, registry, matcher=engine)
        period.assert_not_called()
    engine.match.assert_called_once()
    message = str(error.value)
    assert '41' in message  # Original source position, not the iteration counter.
    private_values = [source.iloc[0]['header_text'], source.iloc[0]['verification_id'],
                      result.selected_supplier_key, result.supplier_text_raw, result.reason]
    for candidate in result.candidates:
        private_values.extend([candidate.supplier.key, candidate.supplier.organization_number,
                               candidate.matched_name])
    assert all(value not in message for value in private_values if value)
    pd.testing.assert_frame_equal(source, before_source)
    pd.testing.assert_frame_equal(registry.data, before_registry)


@pytest.mark.parametrize('key', [None, '', f'org:{org(999)}', f'org:{org(202)}'],
                         ids=['missing', 'empty', 'unknown-identity', 'weak-alternative'])
def test_strong_result_requires_the_expected_selected_key(key):
    source, registry, result = matching_case()
    assert result.status == Status.STRONG_MATCH
    assert result.selected_supplier_key == f'org:{org(101)}'
    assert not result.candidates[1].strong_eligible
    assert_rejected_before_contract_assessment(source, registry, replace(result, selected_supplier_key=key))


@pytest.mark.parametrize('status', [Status.AMBIGUOUS_MATCH, Status.NO_MATCH, Status.SUPPLIER_NOT_IDENTIFIED])
@pytest.mark.parametrize('keep_key', [False, True], ids=['no-key', 'selected-key'])
def test_eligible_exact_selection_cannot_be_reported_as_nonstrong(status, keep_key):
    source, registry, result = matching_case()
    inconsistent = replace(result, status=status,
                           selected_supplier_key=result.selected_supplier_key if keep_key else None)
    assert_rejected_before_contract_assessment(source, registry, inconsistent)


@pytest.mark.parametrize('status', [Status.AMBIGUOUS_MATCH, Status.NO_MATCH, Status.SUPPLIER_NOT_IDENTIFIED])
def test_nonstrong_result_without_eligible_selection_cannot_carry_an_identity(status):
    source, registry, result = matching_case(rows=[('Bonliva AB', org(101)), ('Bonliva AB', org(202))])
    assert result.status == Status.AMBIGUOUS_MATCH
    inconsistent = replace(result, status=status, selected_supplier_key=result.candidates[0].supplier.key)
    assert_rejected_before_contract_assessment(source, registry, inconsistent)


def test_eligible_fuzzy_candidate_among_weak_alternatives_cannot_be_promoted_to_strong():
    source, registry, result = matching_case('Securitas Sverige AB', [
        ('Securitas Svergie AB', org(101)), ('Securitas Care AB', org(202))])
    assert result.status == Status.AMBIGUOUS_MATCH
    fuzzy, weak = result.candidates
    assert fuzzy.method == 'fuzzy' and fuzzy.strong_eligible
    assert not weak.name_strong and not weak.strong_eligible
    # This contract would PASS if the inconsistent selection reached assessment.
    assert check_contract_period('2026-06-15', fuzzy.supplier.contracts[0],
                                 identity_confirmed=True).contract_period_status == 'PASS'
    for order in permutations(result.candidates):
        inconsistent = replace(result, status=Status.STRONG_MATCH,
                               selected_supplier_key=fuzzy.supplier.key, candidates=order)
        assert_rejected_before_contract_assessment(source, registry, inconsistent)


@pytest.mark.parametrize('identifier', [None, 'SAKNAS', '5590002028', '1212121212'])
def test_ineligible_exact_identity_cannot_be_promoted_to_strong(identifier):
    source, registry, result = matching_case(rows=[('Bonliva AB', identifier)])
    assert result.status == Status.AMBIGUOUS_MATCH
    candidate, = result.candidates
    assert candidate.name_strong and not candidate.strong_eligible
    inconsistent = replace(result, status=Status.STRONG_MATCH, selected_supplier_key=candidate.supplier.key)
    assert_rejected_before_contract_assessment(source, registry, inconsistent)


@pytest.mark.parametrize('key', [None, f'org:{org(101)}'])
def test_strong_result_without_candidates_is_rejected(key):
    source, registry, result = matching_case('Zyxwvu', [('Bonliva AB', org(101))])
    assert result.status == Status.NO_MATCH and not result.candidates
    inconsistent = replace(result, status=Status.STRONG_MATCH, selected_supplier_key=key)
    assert_rejected_before_contract_assessment(source, registry, inconsistent)


@pytest.mark.parametrize('order', list(permutations(range(3))))
def test_correct_selection_preserves_all_evidence_in_any_candidate_order(order):
    source, registry, result = matching_case()
    baseline = analyze_suppliers(source, registry)
    reordered = replace(result, candidates=tuple(result.candidates[i] for i in order))
    analysis = analyze_suppliers(source, registry, matcher=injected_matcher(reordered))
    pd.testing.assert_frame_equal(analysis.rows, baseline.rows)
    for name in ['candidates', 'contracts']:
        actual, expected = getattr(analysis, name), getattr(baseline, name)
        pd.testing.assert_frame_equal(actual.sort_values('supplier_key').reset_index(drop=True),
                                      expected.sort_values('supplier_key').reset_index(drop=True))
    assert analysis.candidates.supplier_key.tolist() == [c.supplier.key for c in reordered.candidates]
    selected = analysis.contracts.supplier_key.eq(result.selected_supplier_key)
    assert selected.sum() == 1
    assert analysis.contracts.loc[selected].contract_period_status.tolist() == ['PASS']
    assert analysis.contracts.loc[~selected].contract_period_status.tolist() == ['NOT_CHECKED'] * 2


@pytest.mark.parametrize('query, rows, status, period_status', [
    ('Bonliva AB', [('Bonliva AB', org(101))], Status.STRONG_MATCH, 'PASS'),
    ('Securitas Sverige AB', [('Securitas Svergie AB', org(101))], Status.STRONG_MATCH, 'PASS'),
    ('Securitas Sverige', [('Securitas Sverige AB', org(101))], Status.STRONG_MATCH, 'PASS'),
    ('Securitas Sverige AB', [('Securitas Svergie AB', org(101)), ('Securitas Care AB', org(202))],
     Status.AMBIGUOUS_MATCH, 'NOT_CHECKED'),
    ('Bonliva AB', [('Bonliva AB', 'SAKNAS')], Status.AMBIGUOUS_MATCH, 'NOT_CHECKED'),
    ('Zyxwvu', [('Bonliva AB', org(101))], Status.NO_MATCH, None),
    (None, [('Bonliva AB', org(101))], Status.SUPPLIER_NOT_IDENTIFIED, None),
], ids=['exact', 'fuzzy', 'prefix', 'ambiguous-fuzzy', 'invalid-identity', 'no-match', 'unidentified'])
def test_consistent_results_keep_their_existing_match_and_contract_outcomes(query, rows, status, period_status):
    source, registry, result = matching_case(query, rows)
    assert result.status == status
    analysis = analyze_suppliers(source, registry)
    row = analysis.rows.iloc[0]
    assert row.supplier_match_status == status
    assert row.supplier_match_method == result.method
    assert row.supplier_match_score == result.score
    assert row.candidate_count == len(result.candidates)
    assert analysis.candidates.supplier_key.tolist() == [c.supplier.key for c in result.candidates]
    assert analysis.candidates.score.tolist() == [c.score for c in result.candidates]
    if status == Status.STRONG_MATCH:
        assert row.matched_organization_number == org(101)
    else:
        assert pd.isna(row.matched_organization_number)
    if period_status is None:
        assert analysis.contracts.empty
    else:
        assert analysis.contracts.contract_period_status.tolist() == [period_status] * len(result.candidates)
