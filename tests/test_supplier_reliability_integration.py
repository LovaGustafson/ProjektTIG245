"""Synthetic downstream evidence when a high-score candidate loses strong status."""
from io import BytesIO
from unittest.mock import patch

import pandas as pd
import pytest
import yaml
from streamlit.testing.v1 import AppTest

from src.sampling.manual_sample import plan_manual_sample, plan_random_sample
from src.supplier_matching.view_scope import classify_supplier_view, validate_classification_rules
from src.ui_support import analyze_upload, select_sample_method
from tests.test_feature_package import invoices, registry, settings, workbook


SOURCE = 'ATEA Stockholm Sverige AB'
CANDIDATE = 'Telia Stockholm Sverige AB'
REASON = 'Leverantörsnamnen är delvis lika, men särskiljande namnled skiljer sig åt.'


@pytest.fixture
def review(tmp_path):
    path = settings(tmp_path)
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    # Explicit synthetic rule, never a classification of these companies in production.
    rule = dict(id='synthetic-org', match_field='organization_number', value='123',
                classification='INTERNAL', reason='Syntetisk testregel', confirmed=True)
    config['sampling_supplier_rules'] = config['supplier_view_rules'] = [rule]
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
    source = invoices(22)
    source['Huvudtext'] = [f'Syntetisk komponent {i} AB Prelb 1' for i in range(22)]
    source.loc[[0, 19], 'Huvudtext'] = SOURCE + ' Prelb 1'
    source.loc[20, 'Huvudtext'] = CANDIDATE + ' Prelb 1'
    second_line = source.loc[[20]].assign(Vernr='1', Vrad=2)
    source = pd.concat([source, second_line], ignore_index=True)
    register = pd.concat([registry(CANDIDATE)] * 2, ignore_index=True)
    register['Avtals-ID'] = ['synthetic-1', 'synthetic-2']
    return analyze_upload(workbook(source), registry_mode='uploaded',
                          registry_content=workbook(register), registry_name='synthetic.xlsx',
                          settings_path=path, defer_downloads=True)


def test_downgrade_preserves_analysis_candidates_contracts_and_original_values(review):
    result = review.result
    analysis = result.supplier_analysis
    matches = analysis.rows.set_index('source_row_position')
    uncertain = matches.loc[[0, 19]]
    assert uncertain.supplier_match_status.eq('AMBIGUOUS_MATCH').all()
    assert uncertain.matched_organization_number.isna().all()
    assert uncertain.matched_supplier_name.isna().all()
    assert uncertain.supplier_match_score.eq(0.941176).all()
    assert uncertain.supplier_match_reason.str.contains(REASON, regex=False).all()
    assert matches.loc[[20, 22]].supplier_match_status.eq('STRONG_MATCH').all()
    assert matches.loc[[20, 22]].matched_organization_number.eq('123').all()
    assert analysis.candidates.source_row_position.tolist() == [0, 19, 20, 22]
    assert analysis.candidates.organization_number.eq('123').all()
    assert analysis.contracts.source_row_position.tolist() == [0, 0, 19, 19, 20, 20, 22, 22]
    contracts = analysis.contracts
    assert contracts.loc[contracts.source_row_position.isin([0, 19])].contract_period_status.eq('NOT_CHECKED').all()
    assert contracts.loc[contracts.source_row_position.isin([20, 22])].contract_period_status.eq('PASS').all()
    assert contracts.start_date.eq('2026-01-01').all()
    assert contracts.end_date.eq('2026-12-31').all()
    assert contracts.verification_date.eq('2026-06-15').all()
    assert result.original_data.loc[[0, 19], 'Huvudtext'].eq(SOURCE + ' Prelb 1').all()
    assert len(result.original_data) == len(result.filtering.cleaned_data) == 23
    assert len(result.verifications) == 22
    assert result.summary.flagged_verifications == 0


@pytest.mark.parametrize('method', ['systematic', 'randomized'])
def test_classification_and_sampling_use_fallback_without_selecting_candidate_org(review, method):
    result = review.result
    plan = (result.sampling_result if method == 'systematic' else
            plan_random_sample(result.verifications, seed=123, supplier_analysis=result.supplier_analysis,
                               classification_rules=result.sampling_result.classification_rules))
    rows = plan.classification_rows.set_index('source_row_position')
    assert rows.loc[[0, 19]].supplier_key.eq('name:atea stockholm sverige ab').all()
    assert rows.loc[[0, 19]].identity_basis.eq('NORMALIZED_HEADER_NAME').all()
    assert rows.loc[[0, 19]].classification.eq('UNCLASSIFIED').all()
    assert rows.loc[[0, 19]].matched_organization_number.isna().all()
    assert rows.loc[[20, 22]].supplier_key.eq('org:123').all()
    assert rows.loc[[20, 22]].classification.eq('INTERNAL').all()
    view = result.supplier_view.set_index('source_row_position')
    assert view.loc[[0, 19]].classification.eq('UNCLASSIFIED').all()
    assert not view.loc[[0, 19]].excluded_from_view.any()
    assert view.loc[[20, 22]].classification.eq('INTERNAL').all()
    assert not plan.decisions.iloc[0].identity_usable  # Two different keys in Vernr 1.
    assert plan.classification_counts['INTERNAL'] <= len(plan.sample) // 20
    # Force the mixed verification to be examined by either existing selection method.
    mixed = result.verifications[:1]
    checked = (plan_manual_sample(mixed, interval=1, supplier_analysis=result.supplier_analysis)
               if method == 'systematic' else
               plan_random_sample(mixed, seed=123, supplier_analysis=result.supplier_analysis))
    assert checked.decisions.decision.tolist() == ['UNUSABLE_IDENTITY']
    assert not checked.sample


def test_explicit_name_classification_still_works_for_uncertain_match(review):
    rule = dict(id='synthetic-name', match_field='supplier_name', value=SOURCE,
                classification='EXTERNAL', reason='Syntetisk testregel', confirmed=True)
    result = review.result
    plan = plan_manual_sample(result.verifications, supplier_analysis=result.supplier_analysis,
                              classification_rules=[rule])
    rows = plan.classification_rows.set_index('source_row_position')
    assert rows.loc[[0, 19]].classification.eq('EXTERNAL').all()
    view = classify_supplier_view(result.filtering.cleaned_data, result.supplier_analysis,
                                  validate_classification_rules([rule])).set_index('source_row_position')
    assert view.loc[[0, 19]].classification.eq('EXTERNAL').all()


def test_saved_plans_and_all_exports_share_the_recorded_evidence(review, monkeypatch):
    monkeypatch.setattr('src.ui_support.new_sample_seed', lambda previous=None: 123)
    before = review.result.original_data.copy(deep=True)
    # Switching method and exporting must consume this analysis, not rerun matching.
    with patch('src.supplier_matching.matcher.SupplierMatcher.match', side_effect=AssertionError('unexpected rematch')):
        randomized = select_sample_method(review, 'randomized')
        restored = select_sample_method(select_sample_method(randomized, 'systematic'), 'randomized')
        assert restored.result.sampling_result is randomized.result.sampling_result
        assert select_sample_method(randomized, 'systematic').result.sampling_result is review.result.sampling_result
        for current in (review, restored):
            plan = current.result.sampling_result
            assert current.result.supplier_analysis is review.result.supplier_analysis
            for filename in current.downloads:
                sheets = pd.read_excel(BytesIO(current.downloads[filename]), sheet_name=None, dtype=object)
                metadata = sheets['Urvalsmetod'].iloc[0]
                assert metadata['Antal valda verifikationer'] == len(plan.sample)
                assert metadata['Genereringstidpunkt (UTC)'] == plan.generated_at
                assert metadata['Populationens identitetsunderlag SHA-256'] == plan.population_fingerprint
                assert metadata['Klassificeringsunderlag SHA-256'] == plan.classification_fingerprint
                assert sheets['Urvalsbeslut'].decision.tolist() == plan.decisions.decision.tolist()
                assert sheets['Urvalsidentiteter'].supplier_key.tolist() == plan.identity_rows.supplier_key.tolist()
                if plan.method == 'randomized':
                    assert metadata['Seed'] == str(plan.seed)
                if filename == 'manual_sample.xlsx':
                    assert sheets['Källspårning'].source_row_position.tolist() == [
                        p for verification in plan.sample for p in verification.rows.index]
                if filename in ('uncertain_suppliers.xlsx', 'samlad_kontrollfil.xlsx'):
                    rows = sheets['Leverantörsmatchning'].set_index('source_row_position').loc[[0, 19]]
                    assert rows.supplier_match_status.eq('AMBIGUOUS_MATCH').all()
                    assert rows.matched_organization_number.isna().all()
                    assert rows.supplier_match_score.eq(0.941176).all()
                    assert rows.supplier_match_reason.str.contains(REASON, regex=False).all()
                    contracts = sheets['Möjliga avtal']
                    assert contracts.loc[contracts.source_row_position.isin([0, 19])].contract_period_status.eq('NOT_CHECKED').all()
    pd.testing.assert_frame_equal(review.result.original_data, before)


def test_reanalysis_can_change_selection_but_does_not_rewrite_saved_legacy_plan(review):
    # Bypass only the new guard to reproduce Phase 1, keeping all downstream rules identical.
    with patch('src.supplier_matching.matcher._fuzzy_tokens_compatible', return_value=True):
        legacy = analyze_upload(review.source_content, registry_mode='uploaded',
                                registry_content=review.registry_content, registry_name='synthetic.xlsx',
                                settings_path=review.settings_path, defer_downloads=True)
    saved = legacy.result.sampling_result
    assert [v.verification_id for v in saved.sample] == ['22']
    assert [v.verification_id for v in review.result.sampling_result.sample] == ['20']
    assert saved.decisions.iloc[19].decision == 'INTERNAL_QUOTA'
    assert review.result.sampling_result.decisions.iloc[19].decision == 'SELECTED'
    assert select_sample_method(legacy, 'systematic').result.sampling_result is saved
    assert saved.identity_rows.loc[saved.identity_rows.source_row_position.eq(19)].supplier_key.tolist() == ['org:123']
    exported = pd.read_excel(BytesIO(legacy.downloads['manual_sample.xlsx']), 'Källspårning')
    assert exported.source_row_position.tolist() == [21]


def test_ui_explains_downgrade_and_keeps_candidate_and_raw_score(review):
    app = AppTest.from_string(
        'import streamlit as st\n'
        'from src.ui_supplier_panel import show_supplier_detail\n'
        'show_supplier_detail(st.session_state["analysis"], 19)')
    app.session_state['analysis'] = review.result.supplier_analysis
    app.run()
    assert not app.exception
    display = app.dataframe[0].value
    assert display.supplier_text_raw.tolist() == [SOURCE]
    assert display.supplier_name.tolist() == [CANDIDATE]
    assert display.match_result.tolist() == ['Osäker namnmatchning']
    assert display.score.tolist() == [0.941176]
    assert REASON in display.explanation.iloc[0]
    assert any('inte sannolikheten' in caption.value for caption in app.caption)
