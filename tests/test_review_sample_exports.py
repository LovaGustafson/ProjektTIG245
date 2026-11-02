"""Synthetic row-download samples preserve review columns and exact occurrences."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from random import Random, getstate
from unittest.mock import patch

import pandas as pd
import pytest
from openpyxl import load_workbook

from src.output import report_generator
from src.output.report_generator import REVIEW_SAMPLE_FILES
from src.sampling.review_sample import REVIEW_SAMPLE_SEED, review_sample_positions
from src.ui_support import analyze_upload, select_sample_method
from tests.test_feature_package import invoices, registry, settings, workbook
from tests.test_ui_ux import assert_same_analysis, assert_same_workbook


@pytest.mark.parametrize('size', [0, 1, 19, 20, 21, 39, 40, 41, 60, 61, 100, 401])
def test_row_sample_boundaries_count_order_and_no_replacement(size):
    systematic = review_sample_positions(size, 'systematic')
    randomized = review_sample_positions(size, 'randomized')
    assert systematic == list(range(19, size, 20))
    assert len(randomized) == len(systematic) == size // 20
    assert len(set(randomized)) == len(randomized)
    assert randomized == sorted(randomized)
    assert all(0 <= position < size for position in randomized)


def test_row_random_seed_is_repeatable_and_isolated_from_global_random_state():
    state = getstate()
    assert review_sample_positions(100, 'randomized') == [3, 14, 35, 81, 94]
    assert review_sample_positions(100, 'randomized') == review_sample_positions(100, 'randomized', seed=42)
    assert review_sample_positions(100, 'randomized', seed=7) != review_sample_positions(100, 'randomized')
    assert getstate() == state


def test_row_sampler_rejects_invalid_method_or_population():
    with pytest.raises(ValueError, match='Unknown'):
        review_sample_positions(40, 'unknown')
    with pytest.raises(ValueError, match='non-negative'):
        review_sample_positions(-1, 'systematic')


@pytest.mark.parametrize('deferred', [False, True])
@pytest.mark.parametrize('matching', [False, True])
def test_row_downloads_preserve_review_columns_values_and_source_occurrences(tmp_path, deferred, matching):
    data = invoices(87).astype(object)
    # Repeated/missing IDs and invalid values remain separate review occurrences.
    data['Vernr'] = 'same'
    data.loc[0, 'Konto'] = '7698'
    data.loc[1, 'Vertyp'] = 'LR91S'
    data.loc[2, 'Huvudtext'] = 'mall'
    data.loc[3, 'Vertyp'] = 'LR95S'
    data.loc[30, 'Konto'] = '7699'
    data.loc[65, 'Vertyp'] = 'FBFM'
    data.loc[23, 'Vernr'] = None
    data.loc[43, 'Utfall'] = 'invalid'
    data['Källnotering'] = [f'Förekomst {i}' for i in range(len(data))]
    data.loc[23, 'Källnotering'] = '=1+1'
    content = workbook(data)
    review = analyze_upload(content, defer_downloads=deferred,
        registry_mode='uploaded' if matching else 'disabled',
        registry_content=workbook(registry()) if matching else None,
        settings_path=settings(tmp_path), source_name='syntetiskt-underlag.xlsx')
    before = deepcopy(review.result)
    full = pd.read_excel(BytesIO(review.downloads['granskning.xlsx']), 'Granskning', dtype=object)
    population = [i for i in range(87) if i not in {0, 1, 2, 3, 30, 65}]
    assert len(full) == len(population) == 81

    for filename, method in REVIEW_SAMPLE_FILES.items():
        sheets = pd.read_excel(BytesIO(review.downloads[filename]), sheet_name=None, dtype=object)
        # Derive expected random selection independently from recorded seed.
        metadata = sheets['Urvalsmetod'].iloc[0]
        offsets = (list(range(19, len(full), 20)) if method == 'systematic' else
                   sorted(Random(int(metadata.Seed)).sample(range(len(full)), len(full) // 20)))
        positions = [population[i] for i in offsets]
        rows = sheets['Granskning']
        pd.testing.assert_frame_equal(rows, full.iloc[offsets].reset_index(drop=True))
        assert metadata['Antal rader i populationen'] == 81
        assert metadata['Antal valda rader'] == metadata['Önskat antal rader'] == 4
        assert 'inläsningsordning' in metadata.Ordning
        assert 'Källrad' in metadata.Urvalsenhet
        assert sheets['Urvalspopulation'].source_row_position.tolist() == population
        assert sheets['Urvalspopulation'].selected.tolist() == [i in offsets for i in range(81)]
        selected = sheets['Urvalspositioner']
        assert selected.population_position.tolist() == [i + 1 for i in offsets]
        assert selected.source_row_position.tolist() == positions
        assert selected.export_row.tolist() == list(range(2, 6))
        trace = sheets['Källspårning']
        assert trace.source_row_position.tolist() == positions
        assert trace.source_excel_row.tolist() == [p + 2 for p in positions]
        assert trace.export_sheet.tolist() == ['Granskning'] * 4
        assert trace.export_row.tolist() == list(range(2, 6))
        assert trace.source_name.tolist() == ['syntetiskt-underlag.xlsx'] * 4
        assert trace.source_sha256.tolist() == [sha256(content).hexdigest()] * 4
        assert 'Urvalsbeslut' not in sheets  # No unrelated verification-sample decisions.
        if matching:
            assert sheets['Leverantörsmatchning'].source_row_position.tolist() == positions
            assert set(sheets['Möjliga avtal'].source_row_position).issubset(positions)
        if method == 'randomized':
            book = load_workbook(BytesIO(review.downloads[filename]))
            seed_column = [c.value for c in book['Urvalsmetod'][1]].index('Seed') + 1
            seed = book['Urvalsmetod'].cell(2, seed_column)
            assert seed.value == str(REVIEW_SAMPLE_SEED) and seed.data_type == 's'
            assert 'random.Random.sample' in metadata.Slumpgenerator
            book.close()

    assert_same_analysis(before, review.result)
    assert review.source_content == content


@pytest.mark.parametrize('count,all_excluded', [(0, False), (1, False), (19, False), (20, False), (41, True)])
def test_empty_small_and_all_excluded_downloads_keep_headers(count, all_excluded):
    data = invoices(count)
    if all_excluded:
        data['Konto'] = '7699'
    review = analyze_upload(workbook(data), registry_mode='disabled', defer_downloads=True)
    for filename in REVIEW_SAMPLE_FILES:
        sheets = pd.read_excel(BytesIO(review.downloads[filename]), sheet_name=None)
        assert sheets['Granskning'].columns.tolist() == data.columns.tolist()
        expected = 0 if all_excluded else count // 20
        assert len(sheets['Granskning']) == len(sheets['Källspårning']) == expected
        assert len(sheets['Urvalspositioner']) == expected
        assert len(sheets['Urvalspopulation']) == (0 if all_excluded else count)


def test_deferred_row_downloads_use_snapshot_and_refiltered_population(tmp_path):
    data = invoices(61)
    data.loc[0, 'Vertyp'] = 'LR91S'
    content = workbook(data)
    options = dict(registry_mode='disabled', settings_path=settings(tmp_path))
    original = analyze_upload(content, defer_downloads=True, **options)
    baseline = analyze_upload(content, **options)
    original.result.original_data.iloc[:, 0] = 'changed after snapshot'
    with patch.object(report_generator, '_workbook', wraps=report_generator._workbook) as serialize:
        for number, filename in enumerate(REVIEW_SAMPLE_FILES, 1):
            actual = original.downloads[filename]
            assert serialize.call_count == number
            assert actual is original.downloads[filename]
            assert_same_workbook(actual, baseline.downloads[filename])
    refiltered = analyze_upload(content, excluded_verification_types=[], defer_downloads=True, **options)
    switched = select_sample_method(baseline, 'randomized')
    for filename in REVIEW_SAMPLE_FILES:
        initial = pd.read_excel(BytesIO(baseline.downloads[filename]), sheet_name=None)
        changed = pd.read_excel(BytesIO(refiltered.downloads[filename]), sheet_name=None)
        assert initial['Urvalspopulation'].source_row_position.tolist() == list(range(1, 61))
        assert changed['Urvalspopulation'].source_row_position.tolist() == list(range(61))
        # The verification-level method and seed cannot change these row draws.
        for sheet in ('Granskning', 'Urvalsmetod', 'Urvalspopulation', 'Urvalspositioner', 'Källspårning'):
            restored = pd.read_excel(BytesIO(switched.downloads[filename]), sheet_name=sheet)
            pd.testing.assert_frame_equal(initial[sheet], restored)
