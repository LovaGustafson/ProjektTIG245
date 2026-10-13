"""Confirmed sampling quotas use synthetic identities only; production rules stay empty."""
from copy import deepcopy
from io import BytesIO
from random import Random
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml
from streamlit.testing.v1 import AppTest

from src.sampling.classification import NO_INTERNAL_RULES, load_sampling_rules
from src.sampling.manual_sample import DEFAULT_SETTINGS_PATH, plan_manual_sample, plan_random_sample
from src.ui_support import analyze_upload, select_sample_method
from tests.test_feature_package import settings, workbook
from tests.test_priority2 import units
from tests.test_random_sampling import ids
from tests.test_ui_sampling import APP, population


def rule(name, classification='INTERNAL', **overrides):
    return dict(id=f'{name}-{classification}', match_field='supplier_name', value=name,
                classification=classification, reason='Bekräftad syntetisk testregel',
                confirmed=True, **overrides)


@pytest.mark.parametrize('target,limit', [(19, 0), (20, 1), (21, 1), (39, 1), (40, 2)])
def test_systematic_actual_boundaries_keep_nominal_positions_and_forward_order(target, limit):
    names = [f'Synthetic {i} AB' for i in range(target * 20 + 10)]
    # First three nominal positions are internal. Replacements must move forward.
    internals = [names[p - 1] for p in (20, 40, 60)]
    source = units(names)
    before = deepcopy(source)
    plan = plan_manual_sample(source, classification_rules=[rule(n) for n in internals])
    expected = [p + (1 if i < 3 and i >= limit else 0)
                for i, p in enumerate(range(20, target * 20 + 1, 20))]
    assert ids(plan) == list(map(str, expected))
    assert len(plan.sample) == plan.target_size == target
    assert plan.classification_counts == {'INTERNAL': limit, 'EXTERNAL': 0, 'UNCLASSIFIED': target - limit}
    assert plan.quota_rejections == 3 - limit
    assert plan.decisions.query("decision == 'SELECTED'").supplier_key.is_unique
    assert plan.decisions.query("decision == 'SELECTED'").nominal_position.tolist() == list(range(20, target * 20 + 1, 20))
    assert not plan.shortfall_message
    for actual, original in zip(source, before):
        pd.testing.assert_frame_equal(actual.rows, original.rows)


def test_actual_denominator_is_rechecked_until_safe_without_backfill():
    names = ['Internal A', 'Internal B'] + [f'External {i}' for i in range(18)] + ['Internal A'] * 20
    plan = plan_manual_sample(units(names), interval=1,
        classification_rules=[rule(n) for n in names[:2]] + [rule(n, 'EXTERNAL') for n in names[2:20]])
    assert plan.target_size == 40
    # Provisional 20 included two internal; removing only one would leave 1/19.
    assert ids(plan) == list(map(str, range(3, 21)))
    assert plan.classification_counts == {'INTERNAL': 0, 'EXTERNAL': 18, 'UNCLASSIFIED': 0}
    assert plan.quota_rejections == 2
    assert plan.decisions.decision.tolist() == ['INTERNAL_QUOTA_REMOVED'] * 2 + ['SELECTED'] * 18 + ['DUPLICATE_SUPPLIER'] * 20
    assert '20 valda' in plan.decisions.iloc[1].selection_reason  # latest selected internal first
    assert '19 valda' in plan.decisions.iloc[0].selection_reason
    assert 'prövas inte igen' in plan.decisions.iloc[-1].selection_reason
    assert '18 av önskade 40' in plan.shortfall_message
    assert '2 vid slutkontroll' in plan.shortfall_message


@pytest.mark.parametrize('count,actual,internal', [(19, 18, 0), (20, 20, 1), (21, 20, 1), (39, 20, 1), (40, 20, 1)])
def test_random_boundaries_preserve_seed_draw_order_and_final_quota(count, actual, internal):
    names = [f'Synthetic {i}' for i in range(count)]
    order = list(range(count))
    Random(123).shuffle(order)
    rules = [rule(names[order[0]])]
    first = plan_random_sample(units(names), seed=123, classification_rules=rules)
    repeated = plan_random_sample(units(names), seed=123, classification_rules=rules)
    assert len(first.sample) == actual
    assert first.target_size == 20
    assert first.classification_counts['INTERNAL'] == internal
    assert first.seed == 123
    pd.testing.assert_frame_equal(first.decisions, repeated.decisions)
    expected = order[1:] if count == 19 else order[:20]
    assert ids(first) == [str(i + 1) for i in sorted(expected)]
    assert first.decisions.sort_values('draw_position').population_position.tolist() == [i + 1 for i in order]
    assert first.quota_rejections == (1 if count == 19 else 0)


def test_random_skips_internal_conflict_and_duplicates_without_new_draw():
    names = [f'Synthetic {i}' for i in range(60)]
    order = list(range(60))
    Random(7).shuffle(order)
    names[order[3]] = names[order[0]]
    rules = [rule(names[i]) for i in order[:2]]
    rules += [rule(names[order[2]]), rule(names[order[2]], 'EXTERNAL')]
    result = plan_random_sample(units(names), seed=7, classification_rules=rules)
    assert ids(result) == [str(i + 1) for i in sorted([order[0]] + order[4:23])]
    assert result.decisions.sort_values('draw_position').decision.iloc[:4].tolist() == [
        'SELECTED', 'INTERNAL_QUOTA', 'CLASSIFICATION_CONFLICT', 'DUPLICATE_SUPPLIER']
    assert result.classification_counts == {'INTERNAL': 1, 'EXTERNAL': 0, 'UNCLASSIFIED': 19}
    assert result.quota_rejections == result.conflict_rejections == 1


@pytest.mark.parametrize('classes,expected', [
    (['INTERNAL', None], 'INTERNAL'), (['EXTERNAL', None], 'UNCLASSIFIED'),
    (['INTERNAL', 'EXTERNAL'], 'CONFLICT'), (['EXTERNAL', 'EXTERNAL'], 'EXTERNAL'),
    ([None, None], 'UNCLASSIFIED'),
])
@pytest.mark.parametrize('method', ['systematic', 'randomized'])
def test_mixed_verification_classes_use_existing_single_identity(classes, expected, method):
    source = units(['Alias A'] + [f'Synthetic {i}' for i in range(20)])
    source[0].rows = pd.concat([source[0].rows, units(['Alias B'])[0].rows.set_axis([999])])
    # Same confirmed registry identity, two different source names in one verification.
    analysis = SimpleNamespace(registry=SimpleNamespace(available=True), rows=pd.DataFrame({
        'source_row_position': [3, 999], 'supplier_match_status': ['STRONG_MATCH'] * 2,
        'matched_organization_number': ['synthetic-org'] * 2}))
    rules = [rule(name, status) for name, status in zip(['Alias A', 'Alias B'], classes) if status]
    result = (plan_manual_sample(source, interval=1, supplier_analysis=analysis, classification_rules=rules)
              if method == 'systematic' else plan_random_sample(source, seed=123, supplier_analysis=analysis, classification_rules=rules))
    first = result.decisions.iloc[0]
    assert first.identity_usable
    assert first.supplier_classification == expected
    assert first.decision == ('CLASSIFICATION_CONFLICT' if expected == 'CONFLICT' else 'SELECTED')
    assert result.conflict_rejections == (1 if expected == 'CONFLICT' else 0)
    assert result.classification_rows.source_row_position.tolist() == [3, 999] + list(range(6, 64, 3))
    if expected != 'CONFLICT':
        assert result.sample[0].rows.index.tolist() == [3, 999]


def test_rules_are_exact_confirmed_and_organization_requires_strong_match():
    source = units(['Internal AB', 'Internal AB Region', 'Unconfirmed', 'Org A', 'Org B'])
    analysis = SimpleNamespace(registry=SimpleNamespace(available=True), rows=pd.DataFrame({
        'source_row_position': [12, 15], 'supplier_match_status': ['STRONG_MATCH', 'AMBIGUOUS_MATCH'],
        'matched_organization_number': ['123', '123']}))
    unconfirmed = rule('Unconfirmed')
    unconfirmed['confirmed'] = False
    org = rule('org', 'EXTERNAL')
    org.update(match_field='organization_number', value='123')
    result = plan_manual_sample(source, interval=1, supplier_analysis=analysis,
                                classification_rules=[rule(' INTERNAL Aktiebolag. '), unconfirmed, org])
    assert result.decisions.supplier_classification.tolist() == ['INTERNAL', 'UNCLASSIFIED', 'UNCLASSIFIED', 'EXTERNAL', 'UNCLASSIFIED']
    assert result.decisions.iloc[0].decision == 'INTERNAL_QUOTA'
    assert result.classification_rows.iloc[3].rule_ids == org['id']
    assert result.classification_rows.iloc[4].rule_ids == ''
    assert source[0].rows.header_text.iloc[0] == 'Internal AB Prelb 1'


def test_conflicting_rules_on_same_source_are_excluded_and_counted():
    result = plan_manual_sample(units(['Conflict', 'Unknown']), interval=1,
        classification_rules=[rule('Conflict'), rule('Conflict', 'EXTERNAL')])
    assert ids(result) == ['2']
    assert result.conflict_rejections == 1
    assert result.classification_rows.iloc[0].classification == 'CONFLICT'
    assert 'INTERNAL' in result.classification_rows.iloc[0].rule_ids
    assert 'EXTERNAL' in result.classification_rows.iloc[0].rule_ids
    assert '1 bortval på grund av klassificeringskonflikter' in result.shortfall_message


def test_empty_production_rules_preserve_membership_and_never_infer_external():
    assert load_sampling_rules(DEFAULT_SETTINGS_PATH) == ()
    source = units(['Försörjningsförvaltningen', 'Tolkförmedling', 'Apoteket AB', 'Göteborgs Energi'])
    result = plan_random_sample(source, seed=3)
    assert result.classification_counts == {'INTERNAL': 0, 'EXTERNAL': 0, 'UNCLASSIFIED': 4}
    assert result.internal_rules_active == result.quota_rejections == result.conflict_rejections == 0
    assert result.quota_metadata['Klassificeringsregelstatus'] == NO_INTERNAL_RULES
    assert ids(result) == ['1', '2', '3', '4']


def test_ui_and_every_export_share_classifications_rules_snapshot_and_decisions(tmp_path, monkeypatch):
    path = settings(tmp_path)
    config = yaml.safe_load(path.read_text())
    data = population(420)
    rules = [rule(f'Syntetisk leverantör {i} AB') for i in (19, 39, 59)]
    rules += [rule('Syntetisk leverantör 79 AB'), rule('Syntetisk leverantör 79 AB', 'EXTERNAL'),
              rule('Syntetisk leverantör 99 AB', 'EXTERNAL')]
    config['sampling_supplier_rules'] = rules
    path.write_text(yaml.safe_dump(config))
    review = analyze_upload(workbook(data), registry_mode='disabled', settings_path=path, defer_downloads=True)
    # Later configuration edits do not alter this analysis or trigger a new classification.
    config['sampling_supplier_rules'] = []
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr('src.ui_support.new_sample_seed', lambda previous=None: 123)
    random_review = select_sample_method(review, 'randomized')
    regenerated = select_sample_method(random_review, 'randomized', regenerate=True)
    for current in (review, random_review, regenerated):
        plan = current.result.sampling_result
        assert plan.internal_rules_active == 4
        assert plan.classification_rules == review.result.sampling_result.classification_rules
        assert plan.classification_fingerprint == review.result.sampling_result.classification_fingerprint
        assert sum(plan.classification_counts.values()) == len(plan.sample)
        for filename in current.downloads:
            sheets = pd.read_excel(BytesIO(current.downloads[filename]), sheet_name=None, dtype=object)
            meta = sheets['Urvalsmetod'].iloc[0]
            for key, value in plan.quota_metadata.items():
                assert meta[key] == value
            assert meta['Antal valda verifikationer'] == len(plan.sample)
            assert sheets['Urvalsbeslut'].supplier_classification.tolist() == plan.decisions.supplier_classification.tolist()
            assert sheets['Urvalsklassificering'].source_row_position.tolist() == plan.classification_rows.source_row_position.tolist()
            assert sheets['Urvalsklassificeringsregler'].id.tolist() == [r['id'] for r in rules]
        app = AppTest.from_file(str(APP), default_timeout=30)
        app.session_state['review'] = current
        app.session_state['registry_enabled'] = False
        app.run()
        assert not app.exception
        manual = next(tab for tab in app.tabs if tab.label == 'Manuellt urval')
        metrics = {m.label: m.value for m in manual.metric}
        assert metrics['Bekräftat interna'] == str(plan.classification_counts['INTERNAL'])
        assert metrics['Bekräftat externa'] == str(plan.classification_counts['EXTERNAL'])
        assert metrics['Oklassificerade'] == str(plan.classification_counts['UNCLASSIFIED'])
        assert metrics['Bortval på grund av kvotbegränsning'] == str(plan.quota_rejections)
        assert metrics['Bortval på grund av klassificeringskonflikter'] == str(plan.conflict_rejections)
        assert manual.dataframe[0].value.verification_id.tolist() == ids(plan)
        assert any('faktiska interna andelen kan vara högre' in c.value for c in manual.caption)
    # Unrelated pipeline results and the original supplied data remain identical.
    for field in ('original_data', 'standardized_data', 'filtering', 'verifications', 'detection_results', 'supplier_analysis'):
        assert getattr(review.result, field) is getattr(random_review.result, field)


def test_empty_rule_warning_is_visible_and_exported():
    review = analyze_upload(workbook(population(21)), registry_mode='disabled', defer_downloads=True)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    assert any(i.value == NO_INTERNAL_RULES for i in app.info)
    meta = pd.read_excel(BytesIO(review.downloads['manual_sample.xlsx']), sheet_name='Urvalsmetod').iloc[0]
    assert meta['Aktiva interna klassificeringsregler'] == 0
    assert meta['Klassificeringsregelstatus'] == NO_INTERNAL_RULES
    assert meta['Antal oklassificerade'] == meta['Antal valda verifikationer'] == 1


def test_final_quota_removal_shortfall_is_explained_in_ui_and_excel(tmp_path, monkeypatch):
    path = settings(tmp_path)
    config = yaml.safe_load(path.read_text())
    config['sampling_supplier_rules'] = [rule('Syntetisk leverantör 0 AB')]
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr('src.ui_support.new_sample_seed', lambda previous=None: 123)
    review = select_sample_method(analyze_upload(workbook(population(19)), registry_mode='disabled',
        settings_path=path, defer_downloads=True), 'randomized')
    plan = review.result.sampling_result
    assert len(plan.sample) == 18
    assert plan.decisions.iloc[0].decision == 'INTERNAL_QUOTA_REMOVED'
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    assert any(w.value == plan.shortfall_message for w in app.warning)
    details = next(e for e in app.expander if e.label == 'Urvalsbeslut, klassificering och källspårning')
    assert details.dataframe[0].value.iloc[0].decision == 'INTERNAL_QUOTA_REMOVED'
    sheets = pd.read_excel(BytesIO(review.downloads['manual_sample.xlsx']), sheet_name=None)
    meta = sheets['Urvalsmetod'].iloc[0]
    assert meta['Önskat antal verifikationer'] == 20
    assert meta['Antal valda verifikationer'] == 18
    assert meta['Varav borttagna vid slutkontroll av internkvot'] == 1
    assert meta['Förklaring till mindre stickprov'] == plan.shortfall_message
    assert sheets['Källspårning'].source_row_position.tolist() == list(range(1, 19))
    assert sheets['Urvalsbeslut'].iloc[0].decision == 'INTERNAL_QUOTA_REMOVED'
