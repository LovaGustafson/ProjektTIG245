"""Selected supplier identity is isolated from alternative contracts and saved evidence."""
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
from unittest.mock import patch

import pandas as pd
import pytest
import yaml
from streamlit.testing.v1 import AppTest

from src.ingestion.contract_reader import registry_from_frame
from src.supplier_matching.analysis import analyze_suppliers, ROW_FIELDS, CANDIDATE_FIELDS, CONTRACT_COLUMNS
from src.supplier_matching.matcher import SupplierMatcher
from src.ui_supplier_matches import simple_match_rows, candidate_summary
from src.ui_support import analyze_upload, select_sample_method
from tests.test_feature_package import invoices, settings, workbook


def register_frame(start='2026-01-01', end='2026-12-31'):
    return pd.DataFrame({
        'supplier_name': ['Bonliva AB', 'Bonliva Care AB', 'Bonliva Sverige AB'],
        'organization_number': ['101', '202', '303'],
        'contract_id': ['selected', 'alternative-current', 'alternative-expired'],
        'start_date': [start, '2026-01-01', '2024-01-01'],
        'end_date': [end, '2026-12-31', '2025-12-31'],
    })


def source_rows():
    # Shared verification IDs must not merge source occurrence evidence.
    return pd.DataFrame({'verification_id': ['same'] * 2,
                         'header_text': ['Bonliva AB Prelb 1'] * 2,
                         'verification_date': ['2026-06-15'] * 2}, index=[11, 31])


@pytest.mark.parametrize('start,end,expected', [
    ('2026-01-01', '2026-12-31', 'PASS'),
    ('2024-01-01', '2025-12-31', 'FLAGGED'),
    ('2027-01-01', '2027-12-31', 'FLAGGED'),
    (None, None, 'NOT_CHECKED'),
    ('2026-06-15', '2026-12-31', 'NOT_CHECKED'),  # Unconfirmed boundary unchanged.
])
def test_only_selected_identity_is_period_checked(start, end, expected):
    source = source_rows()
    frame = register_frame(start, end)
    before_source, before_registry = source.copy(deep=True), frame.copy(deep=True)
    analysis = analyze_suppliers(source, registry_from_frame(frame))
    assert analysis.rows.supplier_match_status.eq('STRONG_MATCH').all()
    assert analysis.rows.matched_organization_number.eq('101').all()
    assert analysis.rows.candidate_count.eq(3).all()
    assert analysis.rows.contract_count.eq(1).all()
    selected = analysis.contracts.loc[analysis.contracts.organization_number.eq('101')]
    alternatives = analysis.contracts.loc[~analysis.contracts.organization_number.eq('101')]
    assert selected.contract_period_status.eq(expected).all()
    assert selected.supplier_match_status.eq('STRONG_MATCH').all()
    assert alternatives.contract_period_status.eq('NOT_CHECKED').all()
    assert alternatives.supplier_match_status.eq('AMBIGUOUS_MATCH').all()
    assert alternatives.contract_period_reason.str.contains('inte har valts').all()
    assert analysis.candidates.source_row_position.tolist() == [11] * 3 + [31] * 3
    assert analysis.contracts.source_row_position.tolist() == [11] * 3 + [31] * 3
    assert list(analysis.rows.columns) == ROW_FIELDS
    assert list(analysis.candidates.columns) == CANDIDATE_FIELDS
    assert list(analysis.contracts.columns) == CONTRACT_COLUMNS
    pd.testing.assert_frame_equal(source, before_source)
    pd.testing.assert_frame_equal(frame, before_registry)


def test_selected_identity_without_contract_rows_never_borrows_an_alternative_contract():
    registry = registry_from_frame(register_frame())
    registry.suppliers = tuple(replace(s, contracts=()) if s.organization_number == '101' else s
                               for s in registry.suppliers)
    analysis = analyze_suppliers(source_rows(), registry)
    assert analysis.rows.matched_organization_number.eq('101').all()
    assert analysis.rows.contract_count.eq(0).all()
    assert analysis.rows.supplier_match_status.eq('STRONG_MATCH').all()
    assert len(analysis.contracts) == 4
    assert analysis.contracts.contract_period_status.eq('NOT_CHECKED').all()
    assert not analysis.contracts.organization_number.eq('101').any()


def test_analysis_uses_explicit_selected_key_instead_of_first_candidate():
    registry = registry_from_frame(register_frame())
    result = SupplierMatcher(registry.suppliers).match('Bonliva AB')
    reordered = replace(result, candidates=tuple(reversed(result.candidates)))
    with patch.object(SupplierMatcher, 'match', return_value=reordered):
        analysis = analyze_suppliers(source_rows(), registry)
    assert analysis.rows.matched_organization_number.eq('101').all()
    assert analysis.contracts.loc[analysis.contracts.organization_number.eq('101')].contract_period_status.eq('PASS').all()
    assert analysis.contracts.loc[~analysis.contracts.organization_number.eq('101')].contract_period_status.eq('NOT_CHECKED').all()


def test_all_contracts_of_selected_alias_identity_keep_their_own_dates():
    frame = register_frame()
    aliases = frame.iloc[[0]].copy()
    aliases['supplier_name'] = 'Bonliva Aktiebolag'
    aliases['contract_id'] = 'selected-expired'
    aliases['end_date'] = '2025-12-31'
    aliases['start_date'] = '2024-01-01'
    analysis = analyze_suppliers(source_rows(), registry_from_frame(pd.concat([frame, aliases])))
    assert analysis.rows.contract_count.eq(2).all()
    assert analysis.rows.candidate_count.eq(3).all()
    selected = analysis.contracts.loc[analysis.contracts.organization_number.eq('101')]
    assert selected.contract_period_status.tolist() == ['PASS', 'FLAGGED'] * 2
    assert len(analysis.contracts) == 8
    assert analysis.contracts.loc[~analysis.contracts.organization_number.eq('101')].contract_period_status.eq('NOT_CHECKED').all()


@pytest.mark.parametrize('collision', ['exact-identity', 'missing-exact-identity', 'strong-fuzzy'])
def test_ambiguous_identities_never_check_any_candidates_contract(collision):
    frame = register_frame()
    if collision == 'strong-fuzzy':
        frame.loc[:1, 'supplier_name'] = ['Securitas Sverige AB', 'Securitas Svergie AB']
        source = source_rows().assign(header_text='Securitas Sverige AB Prelb 1')
    else:
        frame.loc[1, 'supplier_name'] = 'Bonliva Aktiebolag'
        if collision == 'missing-exact-identity':
            frame.loc[1, 'organization_number'] = None
        source = source_rows()
    analysis = analyze_suppliers(source, registry_from_frame(frame))
    assert analysis.rows.supplier_match_status.eq('AMBIGUOUS_MATCH').all()
    assert analysis.rows.matched_organization_number.isna().all()
    assert analysis.contracts.contract_period_status.eq('NOT_CHECKED').all()
    assert analysis.contracts.supplier_match_status.eq('AMBIGUOUS_MATCH').all()


@pytest.fixture
def review(tmp_path):
    path = settings(tmp_path)
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    # Confirmed identities below exist only in this synthetic fixture.
    rules = [dict(id=f'synthetic-{org}', match_field='organization_number', value=org,
                  classification=classification, reason='Syntetisk testregel', confirmed=True)
             for org, classification in [('101', 'EXTERNAL'), ('202', 'INTERNAL')]]
    config['sampling_supplier_rules'] = config['supplier_view_rules'] = rules
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
    source = invoices(22)
    source['Huvudtext'] = [f'Syntetisk komponent {i} AB Prelb 1' for i in range(22)]
    source.loc[[0, 19, 20], 'Huvudtext'] = [name + ' Prelb 1' for name in
                                          ['Bonliva Care AB', 'Bonliva AB', 'Bonliva Sverige AB']]
    return analyze_upload(workbook(source), registry_mode='uploaded', registry_content=workbook(register_frame()),
                          registry_name='synthetic.xlsx', settings_path=path, defer_downloads=True)


def assert_candidate_contracts(contracts, position=19):
    contracts = contracts.loc[contracts.source_row_position.eq(position)]
    selected = contracts.loc[contracts.organization_number.eq('101')]
    alternatives = contracts.loc[~contracts.organization_number.eq('101')]
    assert len(selected) == 1 and len(alternatives) == 2
    assert selected.contract_period_status.eq('PASS').all()
    assert selected.supplier_match_status.eq('STRONG_MATCH').all()
    assert alternatives.contract_period_status.eq('NOT_CHECKED').all()
    assert alternatives.supplier_match_status.eq('AMBIGUOUS_MATCH').all()


def test_selected_and_alternative_labels_follow_identity_even_in_partial_reordered_views(review):
    analysis = review.result.supplier_analysis
    before = deepcopy(analysis)
    matches = analysis.rows.loc[analysis.rows.source_row_position.eq(19)]
    candidates = analysis.candidates.loc[analysis.candidates.source_row_position.eq(19)]
    assert_candidate_contracts(analysis.contracts)
    for displayed in (candidates, candidates.iloc[::-1], candidates.iloc[1:]):
        shown = simple_match_rows(matches, displayed).set_index('supplier_name')
        for candidate in displayed.to_dict('records'):
            row = shown.loc[candidate['supplier_name']]
            assert row.score == candidate['score']
            if candidate['organization_number'] == '101':
                assert row.match_result == 'Stark namnmatchning'
                assert 'exakt namnmatchning har valts' in row.explanation
            else:
                assert row.match_result == 'Alternativ kandidat – inte vald'
                assert 'Avtalsperioden har inte bedömts' in row.explanation
                assert 'exakt namnmatchning har valts' not in row.explanation
    assert 'en har valts' in candidate_summary(matches.iloc[0])
    for field in ('rows', 'candidates', 'contracts'):
        pd.testing.assert_frame_equal(getattr(analysis, field), getattr(before, field))


def test_streamlit_detail_and_dashboard_use_selected_contract_evidence(review):
    analysis = review.result.supplier_analysis
    app = AppTest.from_string(
        'import streamlit as st\n'
        'from src.ui_supplier_panel import show_supplier_detail\n'
        'show_supplier_detail(st.session_state["analysis"], 19)')
    app.session_state['analysis'] = analysis
    app.run()
    assert not app.exception
    assert app.dataframe[0].value.match_result.tolist() == [
        'Stark namnmatchning', 'Alternativ kandidat – inte vald', 'Alternativ kandidat – inte vald']
    contracts = next(e for e in app.expander if e.label.startswith('Möjliga avtal')).dataframe[0].value
    assert contracts.contract_period_status.tolist() == ['PASS', 'NOT_CHECKED', 'NOT_CHECKED']
    assert any('inte sannolikheten' in caption.value for caption in app.caption)
    assert review.result.summary.strong_supplier_rows == 3
    assert review.result.summary.contract_status_counts == {'PASS': 2, 'NOT_CHECKED': 6, 'FLAGGED': 1}
    assert len(review.result.verifications) == review.result.summary.eligible_verifications == 22
    assert review.result.summary.flagged_verifications == 0


def test_saved_sampling_and_every_excel_export_preserve_selected_identity_and_schema(review, monkeypatch):
    seeds = iter([123, 456])
    monkeypatch.setattr('src.ui_support.new_sample_seed', lambda previous=None: next(seeds))
    original = review.result.original_data.copy(deep=True)
    # Neither switching nor regenerating a sample may rerun identity matching.
    with patch('src.supplier_matching.matcher.SupplierMatcher.match', side_effect=AssertionError('unexpected rematch')):
        randomized = select_sample_method(review, 'randomized')
        restored = select_sample_method(select_sample_method(randomized, 'systematic'), 'randomized')
        regenerated = select_sample_method(restored, 'randomized', regenerate=True)
        assert restored.result.sampling_result.seed == 123
        assert regenerated.result.sampling_result.seed == 456
        assert restored.result.sampling_result is randomized.result.sampling_result
        assert select_sample_method(randomized, 'systematic').result.sampling_result is review.result.sampling_result
        for current in (review, restored, regenerated):
            result, plan = current.result, current.result.sampling_result
            assert result.supplier_analysis is review.result.supplier_analysis
            assert_candidate_contracts(result.supplier_analysis.contracts)
            classified = plan.classification_rows.set_index('source_row_position')
            assert classified.loc[19, 'supplier_key'] == 'org:101'
            assert classified.loc[19, 'classification'] == 'EXTERNAL'
            assert classified.loc[0, 'classification'] == 'INTERNAL'
            assert plan.classification_counts['INTERNAL'] <= len(plan.sample) // 20
            view = result.supplier_view.set_index('source_row_position')
            assert view.loc[19, 'classification'] == 'EXTERNAL'
            assert view.loc[0, 'classification'] == 'INTERNAL'
            assert plan.decisions.loc[plan.decisions.decision.eq('SELECTED'), 'supplier_key'].is_unique
            assert result.summary.source_rows == result.summary.included_rows == 22
            for filename in current.downloads:
                sheets = pd.read_excel(BytesIO(current.downloads[filename]), sheet_name=None, dtype=object)
                metadata = sheets['Urvalsmetod'].iloc[0]
                assert metadata['Antal valda verifikationer'] == len(plan.sample)
                assert metadata['Populationens identitetsunderlag SHA-256'] == plan.population_fingerprint
                assert sheets['Urvalsbeslut'].decision.tolist() == plan.decisions.decision.tolist()
                if 'Leverantörsmatchning' in sheets:
                    assert list(sheets['Leverantörsmatchning'].columns) == ROW_FIELDS
                    assert list(sheets['Leverantörskandidater'].columns) == CANDIDATE_FIELDS
                    assert list(sheets['Möjliga avtal'].columns) == CONTRACT_COLUMNS
                if filename in ('samlad_kontrollfil.xlsx', 'cleaned_data.xlsx'):
                    assert_candidate_contracts(sheets['Möjliga avtal'])
                    matched = sheets['Leverantörsmatchning'].set_index('source_row_position').loc[19]
                    assert matched.matched_organization_number == '101' and matched.candidate_count == 3
                if filename == 'manual_sample.xlsx':
                    assert sheets['Källspårning'].source_row_position.tolist() == [
                        p for verification in plan.sample for p in verification.rows.index]
    pd.testing.assert_frame_equal(review.result.original_data, original)


def test_new_analysis_does_not_rewrite_saved_selection_or_lazy_export(review):
    saved_plan = review.result.sampling_result
    saved_analysis = deepcopy(review.result.supplier_analysis)
    # A later register omits the exact supplier. Its alternatives cannot supply its contracts.
    changed_register = register_frame().iloc[1:]
    fresh = analyze_upload(review.source_content, registry_mode='uploaded',
                           registry_content=workbook(changed_register), registry_name='synthetic-changed.xlsx',
                           settings_path=review.settings_path, defer_downloads=True)
    row = fresh.result.supplier_analysis.rows.set_index('source_row_position').loc[19]
    assert row.supplier_match_status == 'AMBIGUOUS_MATCH'
    assert pd.isna(row.matched_organization_number)
    assert review.result.sampling_result is saved_plan
    assert saved_plan.identity_rows.set_index('source_row_position').loc[19, 'supplier_key'] == 'org:101'
    assert fresh.result.sampling_result.identity_rows.set_index('source_row_position').loc[19, 'supplier_key'] == 'name:bonliva ab'
    exported = pd.read_excel(BytesIO(review.downloads['samlad_kontrollfil.xlsx']), sheet_name=None, dtype=object)
    assert_candidate_contracts(exported['Möjliga avtal'])
    for field in ('rows', 'candidates', 'contracts'):
        pd.testing.assert_frame_equal(getattr(review.result.supplier_analysis, field), getattr(saved_analysis, field))
