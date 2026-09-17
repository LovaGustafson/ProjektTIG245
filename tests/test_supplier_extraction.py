import pandas as pd
import pytest

from src.supplier_matching.extraction import extract_supplier


@pytest.mark.parametrize('text, expected', [
    ('Apoteket AB Slutk 3924632', 'Apoteket AB'),
    ('Telia Sverige A Slutk 3933806', 'Telia Sverige A'),
    ('  Företaget AB  Prelb 123', 'Företaget AB'),
    ('Företaget AB prelb 1 Slutk 2', 'Företaget AB'),
    ('Leverantör utan markör', None), ('Slutk 1', None),
    ('Bolaget Slutkund', None), (None, None), (float('nan'), None),
    (pd.NA, None), ('', None), ('   ', None),
])
def test_extract_supplier(text, expected):
    assert extract_supplier(text) == expected
