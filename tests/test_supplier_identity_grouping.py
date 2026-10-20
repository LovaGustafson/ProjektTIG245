"""Phase 3C step 2: only technically usable IDs may merge register rows."""
from dataclasses import replace

import pandas as pd
import pytest

from src.ingestion.contract_reader import registry_from_frame
from src.models.supplier import Supplier
from tests.synthetic_org import org


@pytest.mark.parametrize('names', [('Alfa AB', 'Beta AB'), ('Alfa AB', 'Alfa AB')],
                         ids=['unrelated-names', 'identical-names'])
@pytest.mark.parametrize('identifier, status', [
    ('SAKNAS', 'INVALID_FORMAT'), ('N/A', 'INVALID_FORMAT'), ('-', 'INVALID_FORMAT'),
    ('101', 'INVALID_FORMAT'), ('559000101', 'INVALID_FORMAT'),
    ('55900010111', 'INVALID_FORMAT'), ('165590001011', 'INVALID_FORMAT'),
    ('SE559000101101', 'INVALID_FORMAT'), ('559000+1011', 'INVALID_FORMAT'),
    ('5590001012', 'INVALID_CHECKSUM'), ('559000-1012', 'INVALID_CHECKSUM'),
    ('1212121212', 'NOT_ORGANIZATION_NUMBER_FORMAT'),
    ('121212-1212', 'NOT_ORGANIZATION_NUMBER_FORMAT'),
    ('0000000000', 'NOT_ORGANIZATION_NUMBER_FORMAT'),
    (None, 'MISSING'), ('', 'MISSING'), (' \t', 'MISSING'),
    (pd.NA, 'MISSING'), (float('nan'), 'MISSING'), (True, 'MISSING'),
])
def test_unusable_identifiers_never_merge_rows_or_disclose_values(names, identifier, status):
    frame = pd.DataFrame({
        'supplier_name': names, 'organization_number': [identifier] * 2,
        'contract_id': ['same-contract-id'] * 2, 'contract_name': ['Testavtal'] * 2,
        'start_date': ['2026-01-01'] * 2, 'end_date': ['2026-12-31'] * 2,
    }, index=[41, 41])  # A repeated index or contract ID must not collapse occurrences.
    before = frame.copy(deep=True)
    registry = registry_from_frame(frame)
    assert registry.available
    assert [s.key for s in registry.suppliers] == ['unknown:0', 'unknown:1']
    assert [s.names for s in registry.suppliers] == [(names[0],), (names[1],)]
    assert all(s.organization_number is None for s in registry.suppliers)
    assert all(s.organization_number_status == status for s in registry.suppliers)
    assert [len(s.contracts) for s in registry.suppliers] == [1, 1]
    for position, supplier in enumerate(registry.suppliers):
        contract = supplier.contracts[0]
        assert contract['registry_row_position'] == position
        for field in frame.columns:
            actual, expected = contract[field], frame.iloc[position][field]
            if pd.isna(expected):
                assert pd.isna(actual)
            else:
                assert actual == expected
    explanation = ('organisationsnummer saknas' if status == 'MISSING' else
                   f'organisationsnumret är inte tekniskt användbart ({status})')
    assert registry.issues == tuple(
        f'Registerrad {position}: {explanation}; kräver manuell kontroll.' for position in (1, 2))
    pd.testing.assert_frame_equal(frame, before)
    pd.testing.assert_frame_equal(registry.data, before)


@pytest.mark.parametrize('formatted', [org(101), f'{org(101)[:6]}-{org(101)[6:]}',
                                      f' {org(101)[:6]} {org(101)[6:]} ',
                                      int(org(101)), float(org(101))])
def test_valid_formatted_aliases_share_identity_and_keep_every_contract(formatted):
    frame = pd.DataFrame({
        'supplier_name': ['Alfa AB', 'Alfa Aktiebolag', 'Alfa AB', 'Beta AB'],
        'organization_number': [org(101), formatted, org(101), org(202)],
        'contract_id': ['repeated'] * 4,
    })
    before = frame.copy(deep=True)
    registry = registry_from_frame(frame)
    assert [s.key for s in registry.suppliers] == [f'org:{org(101)}', f'org:{org(202)}']
    assert [s.organization_number for s in registry.suppliers] == [org(101), org(202)]
    assert all(s.organization_number_status == 'ORGANIZATION_NUMBER_FORMAT' for s in registry.suppliers)
    selected = registry.suppliers[0]
    assert selected.names == ('Alfa AB', 'Alfa Aktiebolag')
    assert [c['registry_row_position'] for c in selected.contracts] == [0, 1, 2]
    assert selected.contracts[1]['organization_number'] == formatted
    assert sum(len(s.contracts) for s in registry.suppliers) == len(frame)
    assert not any('Registerrad' in issue for issue in registry.issues)
    pd.testing.assert_frame_equal(frame, before)
    pd.testing.assert_frame_equal(registry.data, before)


def test_mixed_registry_retains_positions_aliases_raw_values_and_copy_independence():
    frame = pd.DataFrame({
        'supplier_name': [None, 'Alfa AB', 'Beta AB', 'Alfa Aktiebolag', 'Gamma AB', 'Beta AB'],
        'organization_number': [org(900), org(101), 'SAKNAS', org(101), 'SAKNAS', None],
        'contract_id': ['duplicate'] * 6, 'extra_source_field': list('abcdef'),
    }, index=[8, 8, 1, 99, 3, 3])
    before = frame.copy(deep=True)
    registry = registry_from_frame(frame)
    assert [s.key for s in registry.suppliers] == [f'org:{org(101)}', 'unknown:2', 'unknown:4', 'unknown:5']
    assert [[c['registry_row_position'] for c in s.contracts] for s in registry.suppliers] == [[1, 3], [2], [4], [5]]
    assert len(registry.data) == 6  # The nameless row stays in source evidence.
    assert any(issue.startswith('Registerrad 1: leverantörsnamn saknas') for issue in registry.issues)
    pd.testing.assert_frame_equal(frame, before)
    pd.testing.assert_frame_equal(registry.data, before)
    registry.data.iloc[0, 0] = 'Changed copy'
    registry.suppliers[0].contracts[0]['organization_number'] = 'Changed contract copy'
    pd.testing.assert_frame_equal(frame, before)


def test_supplier_status_is_optional_for_existing_constructors_and_replace():
    supplier = Supplier('unknown:0', ('Alfa AB',), None, ())
    assert supplier.organization_number_status is None
    classified = replace(supplier, organization_number_status='MISSING')
    assert classified.key == supplier.key and classified.names == supplier.names
    assert classified.organization_number is None and classified.contracts == ()
    assert classified.organization_number_status == 'MISSING'
