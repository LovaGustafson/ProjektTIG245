import pandas as pd
import pytest

from src.ingestion.contract_reader import registry_from_frame
from src.supplier_matching.matcher import SupplierMatcher
from src.supplier_matching.settings import MatchSettings


def matcher(*names):
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': names, 'organization_number': [str(i) for i in range(len(names))]}))
    return SupplierMatcher(registry.suppliers)


@pytest.mark.parametrize('query, name', [
    ('Telia Sverige A', 'Telia Sverige AB'),
    ('Securitas Sveri', 'Securitas Sverige Aktiebolag'),
    ('Menigo Foodserv', 'Menigo Foodservice AB'),
    ('Ahlsell Sverige', 'Ahlsell Sverige AB'),
    ('Bravida Säkerhe', 'Bravida Säkerhet Aktiebolag'),
    ('Taxi Göteborg e', 'Taxi Göteborg ek för'),
])
def test_strong_truncated_match(query, name):
    result = matcher(name).match(query)
    assert result.status == 'STRONG_MATCH'
    assert result.method == 'prefix'
    assert result.candidates[0].matched_name == name


def test_exact_normalized_and_fuzzy_and_unidentified():
    engine = matcher('Securitas Sverige Aktiebolag')
    assert engine.match('SECURITAS  SVERIGE AB.').method == 'exact_normalized'
    result = engine.match('Securitas Svergie AB')
    assert result.status == 'STRONG_MATCH' and result.method == 'fuzzy'
    assert engine.match('Helt Annat Bolag AB').status == 'NO_MATCH'
    assert engine.match(None).status == 'SUPPLIER_NOT_IDENTIFIED'


@pytest.mark.parametrize('query, names', [
    ('Input interiör', ['Input interiör AB', 'Input Interiör Göteborg AB']),
    ('Swedbank Pay AB', ['Swedbank AB']),
    ('Synologen Servi', ['Synologen AB']),
    ('AJ Medical HB', ['AJ Medical KB']),
    ('AJ Medical Utrustning Sverige HB', ['AJ Medical Utrustning Sverige KB']),
    ('Securitas Säkerhetsutrustning Sverige AB', ['Securitas Säkerhetsutrustning Sverige A AB']),
    ('Acme Medical Global AB', ['Acme Medical Global AB X AB']),
    ('Telia Sverige AB', ['Telia Sverige AB', 'Telia Sverige AB']),
    ('Telia Sverige AB', ['Telia Sverige AB', 'Telia Svergie AB']),
    ('AB', ['AB X']), ('Input', ['Input interiör AB']),
])
def test_ambiguity_is_never_auto_approved(query, names):
    result = matcher(*names).match(query)
    assert result.status == 'AMBIGUOUS_MATCH'
    assert result.candidates
    assert all(c.reason for c in result.candidates)


def test_legal_form_reason_and_missing_organization():
    assert 'HB / KB' in matcher('AJ Medical KB').match('AJ Medical HB').reason
    registry = registry_from_frame(pd.DataFrame({'supplier_name': ['Telia Sverige AB'],
                                                'organization_number': [None]}))
    assert SupplierMatcher(registry.suppliers).match('Telia Sverige AB').status == 'AMBIGUOUS_MATCH'


def test_same_organization_multiple_names_and_contracts_is_one_candidate():
    registry = registry_from_frame(pd.DataFrame({'supplier_name': ['Telia Sverige AB', 'Telia Sverige Aktiebolag'],
                                                'organization_number': ['123456-7890', '1234567890']}))
    result = SupplierMatcher(registry.suppliers).match('Telia Sverige A')
    assert result.status == 'STRONG_MATCH' and len(result.candidates) == 1
    assert len(result.candidates[0].supplier.contracts) == 2


def test_threshold_configuration_and_order_independence():
    with pytest.raises(ValueError):
        MatchSettings(fuzzy_strong_threshold=0.5)
    names = ['Input interiör AB', 'Input interiör Göteborg AB']
    assert matcher(*names).match('Input interiör').status == matcher(*reversed(names)).match('Input interiör').status


def test_stricter_configured_fuzzy_threshold_requires_manual_review():
    engine = matcher('Securitas Sverige AB')
    engine.settings = MatchSettings(fuzzy_strong_threshold=0.99)
    assert engine.match('Securitas Svergie AB').status == 'AMBIGUOUS_MATCH'
