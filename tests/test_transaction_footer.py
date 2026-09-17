"""Synthetic regression for the observed report footer layout."""
from io import BytesIO

import pandas as pd
import pytest

from src.filtering.transaction_rows import non_transaction_reason
from src.ui_support import analyze_upload, validation_table
from src.supplier_matching.settings import load_matching_settings
from src.ingestion.contract_reader import registry_from_frame


def footer():
    return dict(responsibility='1234 Verifikationslista urval TEST', vat_code='- 1 av 1 -',
                amount='2026-09-08 08.27.22 testuser')


def test_footer_is_excluded_from_review_validation_and_supplier_analysis():
    from src.mapping.column_mapper import COLUMN_ALIASES
    row = dict(verification_id='001', verification_line_id=1, verification_date='2026-08-01',
               account='4000', verification_type='X', amount=10, header_text='Test AB Slutk 1')
    data = pd.DataFrame([row, footer(), {**row, 'verification_id': None}])
    aliases = {v: k for k, v in COLUMN_ALIASES.items()}
    source, registry = BytesIO(), BytesIO()
    data.rename(columns=aliases).to_excel(source, index=False)
    pd.DataFrame({'Leverantör': ['Test AB'], 'Organisationsnummer': ['123']}).to_excel(registry, index=False)
    result = analyze_upload(source.getvalue(), registry_content=registry.getvalue()).result
    assert result.filtering.cleaned_data.index.tolist() == [0, 2]
    assert result.supplier_analysis.rows.source_row_position.tolist() == [0, 2]
    assert result.validation.rows[1].validation_status == 'NOT_APPLICABLE'
    assert validation_table(result).row_position.tolist() == [2]
    assert 'rapportfot' in result.filtering.reasons[1]


@pytest.mark.parametrize('field,value', [('verification_id', '001'), ('account', '4000'),
    ('verification_line_id', 1), ('verification_date', '2026-08-01'), ('header_text', 'Faktura')])
def test_footer_signals_do_not_hide_incomplete_transactions(field, value):
    assert not non_transaction_reason(pd.Series({**footer(), field: value}))


def test_partial_footer_signals_do_not_hide_invalid_amount():
    assert not non_transaction_reason(pd.Series({'amount': footer()['amount']}))


def test_swedish_contract_name_alias_preserves_name_and_detects_collision():
    data = pd.DataFrame({'Leverantör': ['Test AB'], 'Organisationsnummer': ['123'],
        'Namn': ['Testavtal'], 'AvtalsID': ['A'], 'Startdatum': ['2026-01-01'], 'Slutdatum': ['2027-01-01']})
    settings = load_matching_settings()
    registry = registry_from_frame(data, columns=settings['registry_columns'])
    assert not registry.issues
    assert registry.suppliers[0].contracts[0]['contract_name'] == 'Testavtal'
    assert not registry_from_frame(data.assign(Avtalsnamn='Annat'), columns=settings['registry_columns']).available
