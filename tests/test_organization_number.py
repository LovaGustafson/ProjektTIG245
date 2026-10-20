"""Phase 3C step 1: scalar validation only, with synthetic identifiers."""
import numpy as np
import pandas as pd
import pytest

from src.ingestion.contract_reader import (
    USABLE_ORGANIZATION_NUMBER_STATUSES,
    classify_organization_number,
    organization_key,
)
from tests.synthetic_org import org


@pytest.mark.parametrize('value', [
    None, pd.NA, pd.NaT, float('nan'), np.float64('nan'),
    True, False, np.bool_(True), np.bool_(False), '', ' \t\n', '\u00a0',
])
def test_missing_identifiers(value):
    assert classify_organization_number(value) == (None, 'MISSING')


@pytest.mark.parametrize('value', [
    'SAKNAS', 'N/A', '-', ' - ', '---', '0', 0, '101',
    '559000101', '55900010111', '165590001011', '16559000-1011',
    '559000+1011', 'SE559000101101', 'NO5590001011',
    '5590001011.0', '5.590001011e9', 5590001011.5,
    float('inf'), float('-inf'), '559000/1011', '559000_1011',
    '５５９０００１０１１', '٥٥٩٠٠٠١٠١١', '559000101\u00b9',
])
def test_placeholders_and_unsupported_formats(value):
    key, status = classify_organization_number(value)
    assert key == organization_key(value)
    assert status == 'INVALID_FORMAT'
    assert status not in USABLE_ORGANIZATION_NUMBER_STATUSES


@pytest.mark.parametrize('value', [
    '5590001012', '559000-1012', '1212121213', '0000000001',
])
def test_checksum_is_checked_before_organization_number_shape(value):
    assert classify_organization_number(value) == (organization_key(value), 'INVALID_CHECKSUM')


@pytest.mark.parametrize('value', ['0000000000', '1212121212', '121212-1212', '5500001010'])
def test_luhn_valid_values_with_third_digit_below_two_are_not_usable(value):
    key, status = classify_organization_number(value)
    assert key == organization_key(value)
    assert status == 'NOT_ORGANIZATION_NUMBER_FORMAT'
    assert status not in USABLE_ORGANIZATION_NUMBER_STATUSES


@pytest.mark.parametrize('value', [
    '5590001011', '559000-1011', ' 559000-1011 ', '559 000 1011',
    '559000\u00a01011', '559\t000-1011', '559-000-1011',
    5590001011, 5590001011.0, np.int64(5590001011), np.float64(5590001011),
])
def test_valid_identifiers_reuse_existing_formatting(value):
    assert classify_organization_number(value) == ('5590001011', 'ORGANIZATION_NUMBER_FORMAT')


@pytest.mark.parametrize('value', ['5520001016', '0290001015', '9990001019'])
def test_third_digit_two_is_allowed_and_first_digit_is_not_a_new_rule(value):
    assert classify_organization_number(value) == (value, 'ORGANIZATION_NUMBER_FORMAT')


def test_only_organization_number_format_is_usable():
    assert USABLE_ORGANIZATION_NUMBER_STATUSES == frozenset({'ORGANIZATION_NUMBER_FORMAT'})


def test_luhn_detects_every_single_digit_change():
    original = '5590001011'
    for position, current in enumerate(original):
        for digit in '0123456789':
            if digit != current:
                changed = original[:position] + digit + original[position + 1:]
                assert classify_organization_number(changed) == (changed, 'INVALID_CHECKSUM')


@pytest.mark.parametrize('value, expected', [
    (None, None), (pd.NA, None), (float('nan'), None), (True, None), (False, None),
    ('', None), (' \t', None), (' 559000-1011 ', '5590001011'),
    ('012345-6789', '0123456789'), (5590001011.0, '5590001011'),
    ('SAKNAS', 'SAKNAS'), (' N/A ', 'N/A'), ('-', '-'), ('101', '101'),
    ('5590001012', '5590001012'), ('121212-1212', '1212121212'),
    ('559000+1011', '559000+1011'), ('165590001011', '165590001011'),
])
def test_organization_key_remains_formatting_only(value, expected):
    assert organization_key(value) == expected


@pytest.mark.parametrize('sequence, expected', [
    (101, '5590001011'), (202, '5590002027'),
    (303, '5590003033'), (123, '5590001235'),
])
def test_synthetic_helper_matches_architecture_examples(sequence, expected):
    assert org(sequence) == expected
    assert classify_organization_number(expected) == (expected, 'ORGANIZATION_NUMBER_FORMAT')


def test_synthetic_helper_boundaries_and_distinct_sequences():
    values = [org(n) for n in (0, 1, 9, 10, 99, 100, 999998, 999999)]
    assert len(set(values)) == len(values)
    for value in values:
        assert value.startswith('559')
        assert classify_organization_number(value) == (value, 'ORGANIZATION_NUMBER_FORMAT')


@pytest.mark.parametrize('sequence', [-1, 1000000, True, False, 1.5, '101', None])
def test_synthetic_helper_rejects_invalid_sequences(sequence):
    with pytest.raises(ValueError, match='Synthetic organization sequence'):
        org(sequence)
