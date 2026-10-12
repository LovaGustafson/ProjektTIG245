"""Separate seeded sampling over synthetic verification populations."""
from copy import deepcopy
from random import getstate

import pandas as pd
import pytest

from src.sampling.manual_sample import plan_manual_sample, plan_random_sample
from tests.test_priority2 import units


def ids(plan):
    return [v.verification_id for v in plan.sample]


def test_random_uses_full_population_and_preserves_systematic_rule():
    population = units([f'Synthetic {i} AB' for i in range(400)])
    systematic = plan_manual_sample(population)
    random = plan_random_sample(population, seed=123)
    assert ids(systematic) == [str(i) for i in range(20, 401, 20)]
    assert systematic.target_size == random.target_size == len(random.sample) == 20
    assert len(set(ids(random))) == 20
    assert set(ids(random)) - set(ids(systematic))
    assert set(random.decisions.population_position) == set(range(1, 401))
    assert set(random.decisions.draw_position) == set(range(1, 401))
    assert random.decisions.loc[random.decisions.decision == 'SELECTED', 'supplier_key'].is_unique
    assert ids(random) == sorted(ids(random), key=int)  # Common display/export order.


@pytest.mark.parametrize('count, expected_systematic', [(0, 0), (7, 0), (19, 0), (20, 1), (100, 5), (600, 30)])
def test_sizes_and_explained_shortfalls(count, expected_systematic):
    population = units([f'Synthetic {i} AB' for i in range(count)])
    systematic = plan_manual_sample(population)
    random = plan_random_sample(population, seed=1)
    assert len(systematic.sample) == systematic.target_size == expected_systematic
    assert random.target_size == 20
    assert len(random.sample) == min(count, 20)
    if count < 20:
        assert f'{count} av önskade 20' in random.shortfall_message
        assert f'populationen om {count}' in random.shortfall_message
    else:
        assert random.shortfall_message == ''


def test_seed_reproduction_different_seeds_and_local_rng():
    population = units([f'Synthetic {i} AB' for i in range(100)])
    global_state = getstate()
    first = plan_random_sample(population, seed=123)
    repeated = plan_random_sample(population, seed=123)
    other = plan_random_sample(population, seed=456)
    assert ids(first) == ids(repeated)
    assert ids(first) != ids(other)
    pd.testing.assert_frame_equal(first.decisions, repeated.decisions)
    assert first.seed == repeated.seed == 123
    assert first.population_fingerprint == repeated.population_fingerprint == other.population_fingerprint
    assert global_state == getstate()


def test_random_supplier_uniqueness_missing_multiple_identity_and_complete_groups():
    population = units(['Alpha AB', ' ALPHA Aktiebolag. ', None, 'Beta AB', 'Gamma AB', 'Delta AB'])
    population[3].rows = pd.concat([population[3].rows, units(['Other AB'])[0].rows.set_axis([100])])
    population[4].rows = pd.concat([population[4].rows, population[4].rows.copy().set_axis([101])])
    before = deepcopy(population)
    result = plan_random_sample(population, seed=1)
    assert len(result.sample) == 3
    assert len(set(ids(result)) & {'1', '2'}) == 1
    assert {'5', '6'} <= set(ids(result))
    assert result.decisions.decision.value_counts().to_dict() == {
        'SELECTED': 3, 'UNUSABLE_IDENTITY': 2, 'DUPLICATE_SUPPLIER': 1}
    assert '3 av önskade 20' in result.shortfall_message
    assert '2 har saknad eller flera' in result.shortfall_message
    assert 'framåt' not in result.shortfall_message
    assert 'saknas' in result.decisions.iloc[2].identity_reason
    assert 'flera' in result.decisions.iloc[3].identity_reason
    for actual, expected in zip(population, before):
        pd.testing.assert_frame_equal(actual.rows, expected.rows)
    selected = next(v for v in result.sample if v.verification_id == '5')
    pd.testing.assert_frame_equal(selected.rows, population[4].rows)
    assert selected.rows.index.tolist() == [15, 101]
    selected.rows.iloc[0, 0] = 'edited'
    pd.testing.assert_frame_equal(population[4].rows, before[4].rows)


def test_many_repeated_suppliers_fill_twenty_when_possible():
    population = units([f'Synthetic {i % 25} AB' for i in range(400)])
    result = plan_random_sample(population, seed=7)
    assert len(result.sample) == 20
    selected = result.decisions.loc[result.decisions.decision == 'SELECTED']
    assert selected.supplier_key.nunique() == 20
    assert selected.population_position.nunique() == 20


@pytest.mark.parametrize('seed', [-1, True, 1.5, '123'])
def test_invalid_seeds_are_rejected(seed):
    with pytest.raises(ValueError, match='seed'):
        plan_random_sample([], seed=seed)
