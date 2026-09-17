from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.mapping.identifiers import normalize_identifier


@pytest.mark.parametrize('value, expected', [
    (3934106.0, '3934106'), (10001511.0, '10001511'), (86.0, '86'),
    (3934106, '3934106'), ('3934106', '3934106'),
    (np.int64(3934106), '3934106'), (np.uint64(3934106), '3934106'),
    (np.float64(10001511), '10001511'), (np.float32(86), '86'),
    (np.longdouble(3934106), '3934106'),
    ('00123', '00123'), ('00123 ', '00123 '), ('A', 'A'),
    ('3934106.0', '3934106.0'), ('1e3', '1e3'),
])
def test_identifier_keys_preserve_text_and_exact_integral_values(value, expected):
    assert normalize_identifier(value) == expected


@pytest.mark.parametrize('value', [
    3934106.5, np.float64(3934106.5), np.float32(86.5),
    np.nextafter(86.0, np.inf), float('inf'), float('-inf'), float('nan'),
    np.float32('nan'), True, False, np.bool_(True), None, pd.NA, pd.NaT,
    '', '  ', [], {}, 1j, Decimal('86'),
])
def test_unsupported_identifiers_are_never_rounded_or_coerced(value):
    assert normalize_identifier(value) is None
