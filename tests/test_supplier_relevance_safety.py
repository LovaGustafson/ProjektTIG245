"""Phase 3D.1 correction: relevance filtering never changes a matching decision.

Synthetic names and organization numbers only; no rule depends on a specific name.
"""
from itertools import permutations

import pandas as pd
import pytest

import src.supplier_matching.matcher as matcher_module
from src.ingestion.contract_reader import registry_from_frame
from src.models.verification import Verification
from src.output.report_generator import uncertain_supplier_rows
from src.sampling.manual_sample import plan_manual_sample, plan_random_sample
from src.supplier_matching.analysis import analyze_suppliers
from src.supplier_matching.matcher import SupplierMatcher
from src.supplier_matching.name_structure import analyze_name_structure, distinctive_names_related
from src.supplier_matching.normalization import normalize_supplier
from src.supplier_matching.view_scope import classify_supplier_view, validate_classification_rules
from tests.synthetic_org import org

# Review counterexamples: a strong-named identity plus a plausible competitor that the
# first Phase 3D.1 filter removed, which promoted the row to STRONG_MATCH.
COMPETING = [
    pytest.param('Alfa Bygg Sverige AB', 'Alfa Bygg Svergie AB', 'Alfa Byggservice Sverige AB', id='compound'),
    pytest.param('Alfa Bygg Sverige AB', 'Alfa Bygg Svergie AB', 'Alfa B Sverige AB', id='abbreviation'),
    pytest.param('Nordverk Sverige AB', 'Nordverk Svergie AB', 'Nordv Sverige AB', id='truncation'),
    pytest.param('ABC Sverige', 'ABC Sverige AB', 'A.B.C Sverige', id='initials'),
    # Invented generalizations of the same patterns.
    pytest.param('Lundqvist Konsult Sverige AB', 'Lundqvist Konsult Svergie AB', 'Lundqvist K Sverige AB',
                 id='abbreviated-second-word'),
    pytest.param('Bergs El Sverige AB', 'Bergs El Svergie AB', 'Bergsel Sverige AB', id='joined-compound'),
]
COMPETITOR_NUMBERS = [
    pytest.param(org(2), id='other-valid-number'),
    pytest.param(None, id='missing-number'),
    pytest.param('SAKNAS', id='placeholder'),
    pytest.param('1212121212', id='personal-number-form'),
    pytest.param('5590000028', id='bad-checksum'),
]


def frame(rows):
    return pd.DataFrame(list(rows), columns=['supplier_name', 'organization_number'])


def match_all_orders(query, rows):
    results = [SupplierMatcher(registry_from_frame(frame(order)).suppliers).match(query)
               for order in permutations(rows)]
    summary = {(r.status.value, r.selected_supplier_key,
                tuple(sorted((c.matched_name, c.method, c.score) for c in r.candidates))) for r in results}
    assert len(summary) == 1, summary
    return results[0]


def unfiltered(query, rows):
    original = matcher_module.distinctive_names_related
    matcher_module.distinctive_names_related = lambda *args: True
    try:
        return SupplierMatcher(registry_from_frame(frame(rows)).suppliers).match(query)
    finally:
        matcher_module.distinctive_names_related = original


def contract_register(rows):
    data = frame(rows)
    data['contract_id'] = [f'C{i}' for i in range(len(data))]
    data['start_date'], data['end_date'] = '2026-01-01', '2026-12-31'
    return registry_from_frame(data)


def source(query):
    return pd.DataFrame({'verification_id': ['1'], 'verification_line_id': [1],
                         'header_text': [f'{query} Prelb 1'], 'verification_date': ['2026-06-15']}, index=[7])


# 1-5. Competing identities stay competing, whatever their number and row order ------

@pytest.mark.parametrize('competitor_number', COMPETITOR_NUMBERS)
@pytest.mark.parametrize('query, target, competitor', COMPETING)
def test_plausible_competitor_is_kept_and_row_stays_ambiguous(query, target, competitor, competitor_number):
    result = match_all_orders(query, [(target, org(1)), (competitor, competitor_number)])
    assert result.status.value == 'AMBIGUOUS_MATCH'
    assert result.selected_supplier_key is None
    assert sorted(c.matched_name for c in result.candidates) == sorted([target, competitor])


@pytest.mark.parametrize('query, target, competitor', COMPETING)
def test_competing_distinctive_names_are_related_in_both_directions(query, target, competitor):
    left = analyze_name_structure(normalize_supplier(query), ('sverige',))
    right = analyze_name_structure(normalize_supplier(competitor), ('sverige',))
    assert distinctive_names_related(left, right, 0.82)
    assert distinctive_names_related(right, left, 0.82)


# 6-8. Short names, compounds, abbreviations, initials ------------------------------

@pytest.mark.parametrize('left, right', [
    ('alfa bygg', 'alfa byggservice'), ('alfa bygg', 'alfa b'), ('nordverk', 'nordv'), ('abc', 'a b c'),
    ('kix', 'k i x'), ('tele2', 'tele 2'), ('mora el', 'mora elservice'), ('ab', 'a'),
])
def test_abbreviations_compounds_and_initials_are_related_symmetrically(left, right):
    a, b = analyze_name_structure(left), analyze_name_structure(right)
    assert distinctive_names_related(a, b, 0.82) and distinctive_names_related(b, a, 0.82)


@pytest.mark.parametrize('left, right', [
    ('atea', 'tele2'), ('atea', 'gartner'), ('securitas', 'secure'), ('kix', 'moxa'), ('alfa bygg', 'tumla bygg'),
])
def test_unrelated_distinctive_names_stay_unrelated_symmetrically(left, right):
    a, b = analyze_name_structure(left), analyze_name_structure(right)
    assert not distinctive_names_related(a, b, 0.82) and not distinctive_names_related(b, a, 0.82)


def test_short_name_with_spelling_variant_keeps_competitor_beside_exact_match():
    result = match_all_orders('Kix Sverige AB', [('Kix Sverige Aktiebolag', org(1)), ('Kax Sverige AB', org(2))])
    assert result.status.value == 'STRONG_MATCH' and result.selected_supplier_key == f'org:{org(1)}'
    assert sorted(c.matched_name for c in result.candidates) == ['Kax Sverige AB', 'Kix Sverige Aktiebolag']


# 9. Directional relevance -----------------------------------------------------------

@pytest.mark.parametrize('query, register', [('Rima Tideservice AB', 'Rima Dietservice AB'),
                                             ('Rima Dietservice AB', 'Rima Tideservice AB')])
def test_relevance_is_symmetric_without_changing_raw_scores(query, register):
    a = analyze_name_structure(normalize_supplier(query), ('sverige',))
    b = analyze_name_structure(normalize_supplier(register), ('sverige',))
    assert distinctive_names_related(a, b, 0.82) == distinctive_names_related(b, a, 0.82) is True
    result = match_all_orders(query, [(register, org(2))])
    assert result.status.value == 'AMBIGUOUS_MATCH'
    assert [c.matched_name for c in result.candidates] == [register]
    assert result.candidates[0].score == unfiltered(query, [(register, org(2))]).candidates[0].score


# 10. Multiple aliases per identity --------------------------------------------------

def test_identity_is_relevant_when_any_alias_is_relevant():
    rows = [('Alfa Bygg Svergie AB', org(1)), ('Alfa Bygd Sverige AB', org(2)), ('Tumla Bygg Sverige AB', org(2))]
    result = match_all_orders('Alfa Bygg Sverige AB', rows)
    assert result.status.value == 'AMBIGUOUS_MATCH'
    assert sorted(c.supplier.key for c in result.candidates) == sorted([f'org:{org(1)}', f'org:{org(2)}'])


def test_aliases_of_the_selected_identity_are_not_affected():
    rows = [('Alfa Bygg Sverige AB', org(1)), ('Alfa Bygg Aktiebolag', org(1)), ('Tumla Bygg Sverige AB', org(3))]
    result = match_all_orders('Alfa Bygg Sverige AB', rows)
    assert result.status.value == 'STRONG_MATCH' and result.selected_supplier_key == f'org:{org(1)}'
    assert [c.matched_name for c in result.candidates] == ['Alfa Bygg Sverige AB']


# 11-12. Decision preservation against the unfiltered matcher -----------------------

DECISION_CASES = [
    ('Atea Sverige AB', [('Atea Sverige AB', org(1)), ('Tele2 Sverige AB', org(2)), ('Gartner Sverige AB', org(3))]),
    ('Atea Sverige', [('Atea Sverige AB', org(1)), ('Vexa Sverige', org(2))]),
    ('Gartner Sverige AB', [('Atea Sverige AB', org(1)), ('Gartner Svergie AB', org(2))]),
    ('Alfa Bygg Sverige AB', [('Alfa Bygg Svergie AB', org(1)), ('Alfa Byggservice Sverige AB', org(2))]),
    ('ABC Sverige', [('ABC Sverige AB', org(1)), ('A.B.C Sverige', org(2))]),
    ('Securitas Sverige AB', [('Secure Sverige AB', org(2))]),
    ('Kix Sverige AB', [('Kix Sverige AB', org(1)), ('Moxa Sverige AB', org(2))]),
]


@pytest.mark.parametrize('query, rows', DECISION_CASES)
def test_filtering_never_changes_status_or_selected_identity(query, rows):
    filtered, original = match_all_orders(query, rows), unfiltered(query, rows)
    assert filtered.selected_supplier_key == original.selected_supplier_key
    if filtered.status != original.status:
        # The only permitted change: every candidate was unrelated, so none is reported.
        assert (original.status.value, filtered.status.value) == ('AMBIGUOUS_MATCH', 'NO_MATCH')
        assert filtered.candidates == ()
    assert {c.supplier.key for c in filtered.candidates} <= {c.supplier.key for c in original.candidates}


def test_exact_match_with_unrelated_alternatives_still_drops_them():
    result = match_all_orders(*DECISION_CASES[0])
    assert result.status.value == 'STRONG_MATCH' and [c.matched_name for c in result.candidates] == ['Atea Sverige AB']


def test_previously_ambiguous_rows_keep_all_original_evidence():
    for query, rows in DECISION_CASES[1:5]:
        result, original = match_all_orders(query, rows), unfiltered(query, rows)
        assert result.status.value == 'AMBIGUOUS_MATCH'
        assert result.candidates == original.candidates


# 13-16. Downstream: contracts, sampling, uncertain export, classification ----------

@pytest.mark.parametrize('query, target, competitor', COMPETING)
def test_downstream_evidence_stays_conservative(query, target, competitor):
    data = source(query)
    analysis = analyze_suppliers(data, contract_register([(target, org(1)), (competitor, org(2))]))
    # 13. No contract is assessed for an ambiguous row.
    assert analysis.rows.supplier_match_status.tolist() == ['AMBIGUOUS_MATCH']
    assert analysis.contracts.contract_period_status.tolist() == ['NOT_CHECKED', 'NOT_CHECKED']
    # 14. Sampling uses the normalized-name fallback, never the strong organization key.
    unit = [Verification('1', data)]
    for plan in (plan_manual_sample(unit, interval=1, supplier_analysis=analysis),
                 plan_random_sample(unit, seed=3, supplier_analysis=analysis)):
        assert plan.identity_rows.supplier_key.tolist() == [f'name:{normalize_supplier(query)}']
        assert plan.identity_rows.identity_basis.tolist() == ['NORMALIZED_HEADER_NAME']
    # 15. The row stays in the uncertain-supplier export.
    exported = uncertain_supplier_rows(data, analysis)
    assert exported.index.tolist() == [7]
    assert exported.supplier_match_status.tolist() == ['AMBIGUOUS_MATCH']
    # 16. Organization classification rules apply only to strong matches.
    rules = validate_classification_rules([dict(id='org-rule', match_field='organization_number', value=org(1),
                                                classification='INTERNAL', reason='Syntetisk.', confirmed=True)])
    assert classify_supplier_view(data, analysis, rules).classification.tolist() == ['UNCLASSIFIED']
    plan = plan_manual_sample(unit, interval=1, supplier_analysis=analysis, classification_rules=[
        dict(id='org-rule', match_field='organization_number', value=org(1), classification='INTERNAL',
             reason='Syntetisk.', confirmed=True)])
    assert plan.classification_rows.classification.tolist() == ['UNCLASSIFIED']
