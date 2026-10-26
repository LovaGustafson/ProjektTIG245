"""Phase 3D.2: structured names and competing identities, using synthetic data only."""
from io import BytesIO
from itertools import permutations
from unittest.mock import patch

import pandas as pd
import pytest

from src.ingestion.contract_reader import registry_from_frame
from src.models.verification import Verification
from src.output.report_generator import supplier_sheets, uncertain_supplier_rows
from src.sampling.manual_sample import plan_manual_sample, plan_random_sample
from src.supplier_matching.analysis import analyze_suppliers, ROW_FIELDS, CANDIDATE_FIELDS, CONTRACT_COLUMNS
from src.supplier_matching.matcher import SupplierMatcher, select_strong_candidate
from src.supplier_matching.name_structure import analyze_name_structure, structured_names_match
from src.supplier_matching.normalization import normalize_supplier
from src.supplier_matching.view_scope import classify_supplier_view, validate_classification_rules
from tests.synthetic_org import org


def registry(rows):
    data = pd.DataFrame(rows, columns=['supplier_name', 'organization_number'])
    data['contract_id'] = [f'synthetic-{i}' for i in range(len(data))]
    data['start_date'], data['end_date'] = '2026-01-01', '2026-12-31'
    return registry_from_frame(data)


def match_orders(query, rows):
    results = [SupplierMatcher(registry(order).suppliers).match(query) for order in permutations(rows)]
    evidence = {(r.status, r.selected_supplier_key, tuple(sorted(
        (c.matched_name, c.method, c.score, c.name_strong, c.strong_eligible) for c in r.candidates)))
        for r in results}
    assert len(evidence) == 1
    for result in results:
        for order in permutations(result.candidates):
            selected = select_strong_candidate(order)
            assert (selected.supplier.key if selected else None) == result.selected_supplier_key
    return results[0]


REFERENCE_CASES = [
    ('Securitas Sveri', 'Securitas Sverige AB', 'STRONG_MATCH'),
    ('Securitas Sverige AB', 'Securitas Sverige', 'STRONG_MATCH'),
    ('Telia AB', 'Telia Sverige Aktiebolag', 'STRONG_MATCH'),
    ('Atea Sverige AB', 'Atea Aktiebolaget', 'STRONG_MATCH'),
    ('Atea Sverige AB', 'Tele2 Sverige AB', 'NO_MATCH'),
    ('Securitas Sverige', 'Secure Sverige AB', 'NO_MATCH'),
    ('Telia AB', 'Teli AB', 'AMBIGUOUS_MATCH'),
]


@pytest.mark.parametrize('query,name,status', REFERENCE_CASES)
def test_reference_results(query, name, status):
    result = match_orders(query, [(name, org(1))])
    assert result.status == status
    assert (result.selected_supplier_key == f'org:{org(1)}') == (status == 'STRONG_MATCH')


@pytest.mark.parametrize('query,name', [
    ('Nexo AB', 'Nexo Sverige Aktiebolaget'),
    ('Nexo Sverige AB', 'Nexo AB'),
    ('Nordviks Bygg Sverige AB', 'Nordviks Bygg'),
    ('Nordviks Bygg', 'Nordviks Bygg Sverige Aktiebolag'),
    ('Åkeriet Öst Sverige HB', 'Åkeriet Öst Handelsbolag'),
    ('Nexo KB', 'Nexo Sverige Kommanditbolag'),
])
def test_invented_distinctive_names_forms_and_omission_in_both_directions(query, name):
    for source, target in ((query, name), (name, query)):
        result = match_orders(source, [(target, org(1))])
        assert result.status == 'STRONG_MATCH'
        assert result.method in ('prefix', 'structured_name')


@pytest.mark.parametrize('query,name', [
    ('Menigo Foodserv', 'Menigo Foodservice AB'),
    ('Nordverks Utrust', 'Nordverks Utrustning AB'),
])
def test_established_safe_distinctive_prefixes_remain_strong(query, name):
    result = match_orders(query, [(name, org(1))])
    assert result.status == 'STRONG_MATCH' and result.method == 'prefix'


@pytest.mark.parametrize('query,name', [
    ('Nexo AB', 'Nexo Supply AB'),
    ('Nexo Sverige AB', 'Nexo Supply Sverige AB'),
    ('Nexo Sverige AB', 'Nexo Sverige HB'),
    ('Nexo Sverige HB', 'Nexo KB'),
    ('Telia AB', 'Teli Sverige AB'),
    ('Nexo Sverige AB', 'Nxeo AB'),
    ('Göteborg Energi AB', 'Stockholm Energi Sverige AB'),
    ('Sverige Trafik AB', 'Trafik AB'),
    ('Nexo Sweden AB', 'Nexo AB'),
    ('Nexo Svergie AB', 'Nexo AB'),
    ('Nexo Sveri AB', 'Nexo AB'),
    ('Åkeriet Öst Sverige AB', 'Akeriet Öst AB'),
    ('AB', 'AB Sverige'),
    ('HB AB', 'HB Sverige AB'),
])
def test_no_new_strong_evidence_from_distinctive_edits_extra_words_or_unapproved_descriptors(query, name):
    left, right = [analyze_name_structure(normalize_supplier(s), ('sverige',)) for s in (query, name)]
    assert not structured_names_match(left, right, ('sverige',))
    result = match_orders(query, [(name, org(1))])
    assert result.status != 'STRONG_MATCH'


@pytest.mark.parametrize('left,right', [
    ('Nordviks Bygg Sverige AB', 'Bygg Nordviks AB'),
    ('Nordviks Nordviks Sverige AB', 'Nordviks AB'),
])
def test_structured_evidence_preserves_distinctive_order_and_multiplicity(left, right):
    a, b = [analyze_name_structure(normalize_supplier(s), ('sverige',)) for s in (left, right)]
    assert not structured_names_match(a, b, ('sverige',))


@pytest.mark.parametrize('number', [org(2), None, 'SAKNAS', '1212121212', '5590000028'])
@pytest.mark.parametrize('competitor', ['Teli Sverige AB', 'Telia Supply AB', 'Telia Sverige AB'])
def test_low_score_plausible_competitors_block_nonexact_structured_selection(number, competitor):
    result = match_orders('Telia AB', [('Telia Sverige Aktiebolag', org(1)), (competitor, number)])
    assert result.status == 'AMBIGUOUS_MATCH' and result.selected_supplier_key is None
    assert len(result.candidates) == 2
    assert all(c.score < 0.82 for c in result.candidates)


@pytest.mark.parametrize('number', [None, 'SAKNAS', '1212121212', '5590000028'])
def test_structured_name_requires_usable_register_identity(number):
    result = match_orders('Nexo AB', [('Nexo Sverige AB', number)])
    assert result.status == 'AMBIGUOUS_MATCH'
    assert result.candidates[0].name_strong and not result.candidates[0].strong_eligible
    assert result.candidates[0].supplier.organization_number is None


def test_same_valid_identity_aliases_keep_all_contract_occurrences():
    rows = [('Telia Sverige AB', org(1)), ('Telia Sverige Aktiebolaget', org(1)), ('Teli Sverige AB', org(1))]
    result = match_orders('Telia AB', rows)
    assert result.status == 'STRONG_MATCH' and len(result.candidates) == 1
    assert result.candidates[0].method == 'structured_name'
    assert len(result.candidates[0].supplier.contracts) == 3


@pytest.mark.parametrize('query,sibling', [('Bonliva AB', 'Bonliva Sverige AB'), ('Telia AB', 'Telia Sverige AB')])
@pytest.mark.parametrize('number', [org(2), None, 'SAKNAS'])
def test_exact_priority_keeps_structural_competitor_visible(query, sibling, number):
    result = match_orders(query, [(query, org(1)), (sibling, number)])
    assert result.status == 'STRONG_MATCH' and result.method == 'exact_normalized'
    assert result.selected_supplier_key == f'org:{org(1)}'
    assert sorted(c.matched_name for c in result.candidates) == sorted([query, sibling])
    assert not next(c for c in result.candidates if c.matched_name == sibling).strong_eligible
    assert 'annan juridisk identitet' in result.reason


@pytest.mark.parametrize('number', [org(2), None, 'SAKNAS'])
@pytest.mark.parametrize('query,aliases', [
    ('Securitas Sverige AB', ['Securitas Sverige', 'Securitas Svergie AB']),
    ('Lindqvist Konsult AB', ['Lindqvist Konsult Sverige AB', 'Lindqvista Konsult AB']),
])
def test_structural_alias_never_hides_existing_exact_blocker(query, aliases, number):
    result = match_orders(query, [(query, org(1)), *[(name, number) for name in aliases]])
    assert result.status == 'AMBIGUOUS_MATCH' and result.selected_supplier_key is None
    assert any(c.name_strong and c.method == 'fuzzy' for c in result.candidates)


def test_structured_matching_cannot_bypass_relevance_decision_preservation():
    result = match_orders('Atea Sverige AB', [('Atea AB', org(1)), ('Vexa Sverige AB', org(2))])
    assert result.status == 'AMBIGUOUS_MATCH' and len(result.candidates) == 2
    assert any(c.method == 'structured_name' and c.strong_eligible for c in result.candidates)


@pytest.mark.parametrize('competing', [False, True])
def test_downstream_selection_contracts_sampling_classification_exports_and_source_copy(competing):
    rows = [('Nexo Sverige AB', org(1)), ('Nexo Sverige Aktiebolaget', org(1))]
    if competing:
        rows.append(('Nex Sverige AB', org(2)))
    supplied = registry(rows)
    register_before = supplied.data.copy(deep=True)
    source = pd.DataFrame({'verification_id': ['same', 'same'], 'verification_line_id': [1, 1],
                           'header_text': ['Nexo AB Prelb 1'] * 2,
                           'verification_date': ['2026-06-15'] * 2}, index=[11, 31])
    before = source.copy(deep=True)
    analysis = analyze_suppliers(source, supplied)
    status = 'AMBIGUOUS_MATCH' if competing else 'STRONG_MATCH'
    assert analysis.rows.supplier_match_status.tolist() == [status] * 2
    assert analysis.rows.source_row_position.tolist() == [11, 31]
    assert analysis.contracts.contract_period_status.tolist() == (
        ['NOT_CHECKED'] * 6 if competing else ['PASS'] * 4)
    rule = dict(id='synthetic', match_field='organization_number', value=org(1),
                classification='EXTERNAL', reason='Synthetic only', confirmed=True)
    units = [Verification(str(i), source.loc[[position]]) for i, position in enumerate(source.index)]
    with patch.object(SupplierMatcher, 'match', side_effect=AssertionError('saved analysis must not rematch')):
        plans = [plan_manual_sample(units, interval=1, supplier_analysis=analysis, classification_rules=[rule]),
                 plan_random_sample(units, seed=7, supplier_analysis=analysis, classification_rules=[rule])]
        for plan in plans:
            assert len(plan.sample) == 1  # Two source occurrences, one supplier identity.
            assert plan.identity_rows.supplier_key.tolist() == (
                ['name:nexo ab'] * 2 if competing else [f'org:{org(1)}'] * 2)
            assert plan.classification_rows.classification.tolist() == (
                ['UNCLASSIFIED'] * 2 if competing else ['EXTERNAL'] * 2)
        view = classify_supplier_view(source, analysis, validate_classification_rules([rule]))
        assert view.classification.tolist() == (['UNCLASSIFIED'] * 2 if competing else ['EXTERNAL'] * 2)
        uncertain = uncertain_supplier_rows(source, analysis)
        assert uncertain.index.tolist() == ([11, 31] if competing else [])
        sheets = supplier_sheets(analysis)
        with BytesIO() as buffer:
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                for name, frame in sheets.items():
                    frame.to_excel(writer, sheet_name=name, index=False)
            exported = pd.read_excel(BytesIO(buffer.getvalue()), sheet_name=None)
        for name, fields in [('Leverantörsmatchning', ROW_FIELDS), ('Leverantörskandidater', CANDIDATE_FIELDS),
                             ('Möjliga avtal', CONTRACT_COLUMNS)]:
            assert exported[name].columns.tolist() == fields
            assert set(exported[name].source_row_position) == {11, 31}
    pd.testing.assert_frame_equal(source, before)
    pd.testing.assert_frame_equal(supplied.data, register_before)


def test_exact_selected_contracts_do_not_borrow_structural_alternative_contracts():
    source = pd.DataFrame({'header_text': ['Telia AB Prelb 1'], 'verification_date': ['2026-06-15']}, index=[41])
    analysis = analyze_suppliers(source, registry([('Telia AB', org(1)), ('Telia Sverige AB', org(2))]))
    assert analysis.rows.matched_organization_number.tolist() == [org(1)]
    assert analysis.contracts.contract_period_status.tolist() == ['PASS', 'NOT_CHECKED']
