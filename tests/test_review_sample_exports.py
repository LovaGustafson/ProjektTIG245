"""Supplier-unique verification downloads, complete source rows and a hard cap."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from random import getstate
from unittest.mock import patch

import pandas as pd
import pytest
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from src.output import report_generator
from src.output.report_generator import REVIEW_SAMPLE_FILES
from src.sampling.manual_sample import plan_manual_sample
from src.sampling.review_sample import REVIEW_SAMPLE_SEED, plan_review_sample
from src.ui_support import analyze_upload, select_sample_method, refresh_sample_downloads
from tests.test_feature_package import invoices, registry, settings, workbook
from tests.test_priority2 import units
from tests.test_sampling_quota import rule
from tests.test_ui_sampling import APP, population
from tests.test_ui_ux import assert_same_analysis, assert_same_workbook, fixed_sampling_time
from tests.synthetic_org import org


@pytest.mark.parametrize('method', ['systematic', 'randomized'])
@pytest.mark.parametrize('size', [0, 1, 19, 20, 21, 39, 40, 399, 400, 401, 800])
def test_download_boundaries_and_hard_cap(size, method):
    source = units([f'Synthetic supplier {i} AB' for i in range(size)])
    plan = plan_review_sample(source, method)
    target = min(size // 20, 20) if method == 'systematic' else 20
    assert plan.target_size == target
    assert len(plan.sample) == min(size, target)
    selected = plan.decisions.query("decision == 'SELECTED'")
    assert selected.supplier_key.is_unique
    assert selected.population_position.is_monotonic_increasing
    if method == 'systematic':
        assert selected.population_position.tolist() == list(range(20, target * 20 + 1, 20))


@pytest.mark.parametrize('method', ['systematic', 'randomized'])
def test_repeated_normalized_names_missing_identity_and_shortfall(method):
    source = units(['Synthetic Alpha AB', ' SYNTHETIC ALPHA Aktiebolag. ',
                    'Synthetic Beta AB', None] * 201)
    before = deepcopy(source)
    plan = plan_review_sample(source, method)
    assert len(plan.sample) == 2
    assert plan.target_size == 20
    assert '2 av önskade 20' in plan.shortfall_message
    assert plan.decisions.query("decision == 'SELECTED'").supplier_key.is_unique
    assert plan.decisions.decision.eq('DUPLICATE_SUPPLIER').any()
    assert plan.decisions.decision.eq('UNUSABLE_IDENTITY').any()
    assert len(plan.identity_rows) == len(source)
    for old, current in zip(before, source, strict=True):
        pd.testing.assert_frame_equal(old.rows, current.rows)


def test_random_repeatability_without_global_rng_changes():
    source = units([f'Synthetic supplier {i} AB' for i in range(85)])
    state = getstate()
    first = plan_review_sample(source, 'randomized')
    repeated = plan_review_sample(source, 'randomized', seed=REVIEW_SAMPLE_SEED)
    other = plan_review_sample(source, 'randomized', seed=7)
    pd.testing.assert_frame_equal(first.decisions, repeated.decisions)
    assert [v.verification_id for v in first.sample] != [v.verification_id for v in other.sample]
    assert getstate() == state


def test_cap_is_applied_before_quota_and_pipeline_default_is_unchanged():
    names = [f'Synthetic supplier {i} AB' for i in range(800)]
    source = units(names)
    rules = [rule(names[i]) for i in (19, 39)]
    legacy = plan_manual_sample(source, classification_rules=rules)
    capped = plan_review_sample(source, 'systematic', classification_rules=rules)
    assert legacy.target_size == len(legacy.sample) == 40
    assert legacy.classification_counts['INTERNAL'] == 2
    assert capped.target_size == len(capped.sample) == 20
    assert capped.classification_counts['INTERNAL'] == 1
    assert capped.decisions.iloc[39].decision == 'INTERNAL_QUOTA'
    assert capped.decisions.iloc[40].decision == 'SELECTED'


@pytest.mark.parametrize('cap', [0, -1, True, 1.5])
def test_invalid_cap_is_rejected(cap):
    with pytest.raises(ValueError, match='max_size'):
        plan_manual_sample([], interval=20, max_size=cap)


def test_unknown_download_method_is_rejected():
    with pytest.raises(ValueError, match='Unknown'):
        plan_review_sample([], 'unknown')


@pytest.mark.parametrize('deferred', [False, True])
def test_807_rows_no_longer_produce_40_sampled_verifications(tmp_path, deferred):
    data = population(415)
    data['Huvudtext'] = [f'Synthetic supplier {i % 40} AB Prelb 1' for i in range(415)]
    second_lines = data.iloc[:392].copy(deep=True)
    second_lines['Vrad'] = 2
    data = pd.concat([data, second_lines], ignore_index=True)
    assert len(data) == 807
    content = workbook(data)
    review = analyze_upload(content, registry_mode='disabled', settings_path=settings(tmp_path),
                            defer_downloads=deferred, source_name='synthetic-807.xlsx')
    before = deepcopy(review.result)
    full = pd.read_excel(BytesIO(review.downloads['granskning.xlsx']), 'Granskning', dtype=object)
    for filename in REVIEW_SAMPLE_FILES:
        sheets = pd.read_excel(BytesIO(review.downloads[filename]), sheet_name=None, dtype=object)
        assert list(sheets)[:2] == ['Stickprov', 'Granskning']
        summary, rows = sheets['Stickprov'], sheets['Granskning']
        decisions = sheets['Urvalsbeslut'].query("decision == 'SELECTED'")
        assert len(summary) == len(decisions) == 20
        assert summary.Leverantör.is_unique and decisions.supplier_key.is_unique
        assert rows.Vernr.nunique() == 20
        assert len(rows) > 20  # Complete bookkeeping groups, never truncated rows.
        assert summary.Bokföringsrader.sum() == len(rows)
        positions = sheets['Källspårning'].source_row_position.astype(int).tolist()
        pd.testing.assert_frame_equal(rows, full.iloc[positions].reset_index(drop=True))
        assert sheets['Källspårning'].source_excel_row.tolist() == [p + 2 for p in positions]
        assert sheets['Källspårning'].source_sha256.tolist() == [sha256(content).hexdigest()] * len(rows)
        assert sheets['Källspårning'].export_sheet.tolist() == ['Granskning'] * len(rows)
        selected = sheets['Urvalspositioner']
        assert selected.export_row.tolist() == list(range(2, len(rows) + 2))
        assert selected.sample_export_sheet.eq('Stickprov').all()
        assert selected.sample_export_row.nunique() == 20
        for row, record in enumerate(summary.itertuples(index=False), 2):
            assert int(selected.sample_export_row.eq(row).sum()) == record.Bokföringsrader
        metadata = sheets['Urvalsmetod'].iloc[0]
        assert metadata['Högsta antal verifikationer'] == metadata['Antal valda verifikationer'] == 20
        assert metadata['Antal valda rader'] == len(rows)
        assert metadata['Antal verifikationer i populationen'] == 415
    assert_same_analysis(before, review.result)
    assert review.source_content == content


@pytest.mark.parametrize('matching', [False, True])
def test_exclusions_ungrouped_multiple_identity_and_column_preservation(tmp_path, matching):
    data = population(85).astype(object)
    data.loc[0, 'Konto'] = '7698'
    data.loc[30, 'Vertyp'] = 'LR91S'
    data.loc[65, 'Huvudtext'] = 'mall'
    data.loc[1, 'Vernr'] = None
    data.loc[2, 'Huvudtext'] = None
    data.loc[4, 'Vernr'] = data.loc[3, 'Vernr']  # Conflicting supplier identities in one group.
    data.loc[43, 'Utfall'] = 'invalid'
    data['Källnotering'] = [f'Förekomst {i}' for i in range(len(data))]
    content = workbook(data)
    review = analyze_upload(content, registry_mode='uploaded' if matching else 'disabled',
        registry_content=workbook(registry()) if matching else None,
        settings_path=settings(tmp_path), defer_downloads=True)
    before = deepcopy(review.result)
    full = pd.read_excel(BytesIO(review.downloads['granskning.xlsx']), 'Granskning', dtype=object)
    for filename in REVIEW_SAMPLE_FILES:
        sheets = pd.read_excel(BytesIO(review.downloads[filename]), sheet_name=None, dtype=object)
        positions = sheets['Källspårning'].source_row_position.astype(int).tolist()
        assert not set(positions) & {0, 1, 2, 3, 4, 30, 65}
        assert sheets['Granskning'].columns.tolist() == full.columns.tolist()
        expected = full.set_index(pd.Index(before.filtering.cleaned_data.index)).loc[positions].reset_index(drop=True)
        pd.testing.assert_frame_equal(sheets['Granskning'], expected)
        pop = sheets['Urvalspopulation'].set_index('source_row_position')
        assert pop.index.tolist() == before.filtering.cleaned_data.index.tolist()
        assert not pop.loc[1, 'eligible'] and not pop.loc[1, 'selected']
        assert 'verifikations-ID' in pop.loc[1, 'reason']
        assert sheets['Urvalsbeslut'].query("decision == 'SELECTED'").supplier_key.is_unique
        if matching:
            assert set(sheets['Leverantörsmatchning'].source_row_position) == set(positions)
    assert_same_analysis(before, review.result)


def test_strong_aliases_with_one_organization_cannot_be_selected_twice(tmp_path):
    data = population(80)
    data['Huvudtext'] = [f'{name} Prelb 1' for name in (
        ['Synthetic Alpha AB', 'Synthetic Alias AB'] * 20 + ['Synthetic Beta AB'] * 40)]
    register = pd.DataFrame({'Leverantör': ['Synthetic Alpha AB', 'Synthetic Alias AB', 'Synthetic Beta AB'],
                             'Organisationsnummer': [org(1), org(1), org(2)]})
    review = analyze_upload(workbook(data), registry_content=workbook(register),
                            settings_path=settings(tmp_path), defer_downloads=True)
    for filename in REVIEW_SAMPLE_FILES:
        sheets = pd.read_excel(BytesIO(review.downloads[filename]), sheet_name=None, dtype=object)
        chosen = sheets['Urvalsbeslut'].query("decision == 'SELECTED'")
        assert len(sheets['Stickprov']) == len(chosen) == 2
        assert set(chosen.supplier_key) == {f'org:{org(1)}', f'org:{org(2)}'}
        assert sheets['Urvalspositioner'].identity_basis.eq('STRONG_MATCH_ORG').all()


@pytest.mark.parametrize('count,all_excluded', [(0, False), (1, False), (19, False), (20, False), (41, True)])
def test_small_or_empty_populations_keep_source_headers(count, all_excluded):
    data = population(count)
    if all_excluded:
        data['Konto'] = '7699'
    review = analyze_upload(workbook(data), registry_mode='disabled', defer_downloads=True)
    for filename, method in REVIEW_SAMPLE_FILES.items():
        sheets = pd.read_excel(BytesIO(review.downloads[filename]), sheet_name=None)
        expected = 0 if all_excluded else (count // 20 if method == 'systematic' else min(count, 20))
        assert len(sheets['Stickprov']) == len(sheets['Granskning']) == expected
        assert sheets['Granskning'].columns.tolist() == data.columns.tolist()
        assert len(sheets['Urvalspopulation']) == (0 if all_excluded else count)


def test_seed_text_precision_cache_snapshot_and_refiltering(tmp_path, fixed_sampling_time):
    data = population(61)
    data.loc[0, 'Vertyp'] = 'LR91S'
    content = workbook(data)
    options = dict(registry_mode='disabled', settings_path=settings(tmp_path))
    original = analyze_upload(content, defer_downloads=True, **options)
    baseline = analyze_upload(content, **options)
    original.result.original_data.iloc[:, 0] = 'changed after snapshot'
    with patch.object(report_generator, '_workbook', wraps=report_generator._workbook) as serialize:
        for number, filename in enumerate(REVIEW_SAMPLE_FILES, 1):
            actual = original.downloads[filename]
            assert actual is original.downloads[filename] and serialize.call_count == number
            assert_same_workbook(actual, baseline.downloads[filename])
    refiltered = analyze_upload(content, excluded_verification_types=[], defer_downloads=True, **options)
    switched = select_sample_method(baseline, 'randomized')
    for filename in REVIEW_SAMPLE_FILES:
        initial = pd.read_excel(BytesIO(baseline.downloads[filename]), sheet_name=None)
        changed = pd.read_excel(BytesIO(refiltered.downloads[filename]), sheet_name=None)
        assert initial['Urvalspopulation'].source_row_position.tolist() == list(range(1, 61))
        assert changed['Urvalspopulation'].source_row_position.tolist() == list(range(61))
        for sheet in ('Stickprov', 'Granskning', 'Urvalsmetod', 'Urvalspopulation', 'Urvalspositioner', 'Källspårning'):
            restored = pd.read_excel(BytesIO(switched.downloads[filename]), sheet_name=sheet)
            pd.testing.assert_frame_equal(initial[sheet], restored)
    book = load_workbook(BytesIO(original.downloads['manual_sample_randomized.xlsx']))
    metadata = book['Urvalsmetod']
    seed_column = [c.value for c in metadata[1]].index('Seed') + 1
    assert metadata.cell(2, seed_column).value == str(REVIEW_SAMPLE_SEED)
    assert metadata.cell(2, seed_column).data_type == 's'
    book.close()


@pytest.mark.parametrize('deferred', [False, True])
def test_open_session_discards_old_row_sample_cache_without_reanalysis(tmp_path, deferred):
    review = analyze_upload(workbook(population(80)), registry_mode='disabled',
                            settings_path=settings(tmp_path), defer_downloads=deferred)
    retained_bytes = review.downloads['granskning.xlsx']
    cache = review.downloads._bytes if deferred else review.downloads
    cache.update({filename: b'obsolete row-sample workbook' for filename in REVIEW_SAMPLE_FILES})
    del review.sample_export_version  # Simulate an instance from before the correction.
    before = deepcopy(review.result)
    with patch('src.ui_support.run_pipeline', side_effect=AssertionError('Unexpected reanalysis')):
        app = AppTest.from_file(str(APP), default_timeout=30)
        app.session_state['review'] = review
        app.run()
        assert not app.exception
        current = app.session_state['review']
        assert current is not review and current.result is review.result
        assert current.sampling_plans is review.sampling_plans
        assert refresh_sample_downloads(current) is current
        assert current.downloads['granskning.xlsx'] is retained_bytes
        assert not set(current.downloads._bytes) & set(REVIEW_SAMPLE_FILES)
        for filename in REVIEW_SAMPLE_FILES:
            sheets = pd.read_excel(BytesIO(current.downloads[filename]), sheet_name=None)
            assert len(sheets['Stickprov']) <= 20
            assert sheets['Urvalsbeslut'].query("decision == 'SELECTED'").supplier_key.is_unique
        assert_same_analysis(before, current.result)
