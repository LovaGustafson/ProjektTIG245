import pytest

from src.supplier_matching.normalization import normalize_supplier, split_legal_form


@pytest.mark.parametrize('value, expected', [
    ('  TELIA   Sverige AB ', 'telia sverige ab'),
    ('Säkerhet, Göteborg-Öst AB.', 'säkerhet göteborg öst ab'),
    ('Go\u0308teborg Aktiebolag', 'göteborg ab'),
    ('Taxi Göteborg ek. för.', 'taxi göteborg ek för'),
    ('AJ Medical HB', 'aj medical hb'), ('AJ Medical KB', 'aj medical kb'),
    (None, ''),
])
def test_normalization(value, expected):
    assert normalize_supplier(value) == expected


def test_legal_forms_and_swedish_characters_remain_distinct():
    assert normalize_supplier('AJ Medical HB') != normalize_supplier('AJ Medical KB')
    assert normalize_supplier('Ås AB') != normalize_supplier('As AB')
    assert split_legal_form(normalize_supplier('Telia Sverige Aktiebolag')) == ('telia sverige', 'ab')
