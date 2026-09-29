"""Separate date evidence for synthetic contracts; no compliance inference."""
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import pytest

from src.ingestion.contract_reader import registry_from_frame
from src.supplier_matching.analysis import analyze_suppliers
from src.supplier_matching.contract_period import (
    ACTIVE, ENDED, NOT_STARTED, UNVERIFIABLE, ContractDatePolicy, check_contract_period,
)
from src.ui_support import analyze_upload


@pytest.mark.parametrize('transaction, start, end, status, label', [
    ('2025-12-31', '2026-01-01', '2026-12-31', 'FLAGGED', NOT_STARTED),
    ('2026-06-15', '2026-01-01', '2026-12-31', 'PASS', ACTIVE),
    ('2027-01-01', '2026-01-01', '2026-12-31', 'FLAGGED', ENDED),
    (date(2026, 6, 15), datetime(2026, 1, 1), datetime(2026, 12, 31), 'PASS', ACTIVE),
    (None, '2026-01-01', '2026-12-31', 'NOT_CHECKED', UNVERIFIABLE),
    ('2026-06-15', None, '2026-12-31', 'NOT_CHECKED', UNVERIFIABLE),
    ('2026-06-15', '2026-01-01', None, 'NOT_CHECKED', UNVERIFIABLE),
    ('2026-06-15', '2026-12-31', '2026-01-01', 'NOT_CHECKED', UNVERIFIABLE),
    ('2026-06-15', 'fel', '2026-12-31', 'NOT_CHECKED', UNVERIFIABLE),
    ('2026-06-15', '2026-01-01', '=A1', 'NOT_CHECKED', UNVERIFIABLE),
    (45000, '2026-01-01', '2026-12-31', 'NOT_CHECKED', UNVERIFIABLE),
])
def test_period_before_during_after_and_missing_dates(transaction, start, end, status, label):
    contract = {'start_date': start, 'end_date': end}
    before = dict(contract)
    result = check_contract_period(transaction, contract, identity_confirmed=True)
    assert (result.contract_period_status, result.contract_period_result) == (status, label)
    assert result.contract_period_reason
    assert contract == before


@pytest.mark.parametrize('day', ['2026-01-01', '2026-12-31'])
def test_unconfirmed_boundaries_are_not_guessed(day):
    contract = {'start_date': '2026-01-01', 'end_date': '2026-12-31'}
    assert check_contract_period(day, contract, identity_confirmed=True).contract_period_status == 'NOT_CHECKED'
    # Explicit policies exercise implementation, not approval of a default rule.
    inclusive = check_contract_period(day, contract, identity_confirmed=True,
                                     policy=ContractDatePolicy(inclusive_boundaries=True))
    assert inclusive.contract_period_status == 'PASS'
    exclusive = check_contract_period(day, contract, identity_confirmed=True,
                                     policy=ContractDatePolicy(inclusive_boundaries=False))
    assert exclusive.contract_period_status == 'FLAGGED'


def test_final_end_date_conflicts_and_missing_ordinary_end_need_a_confirmed_rule():
    contract = {'start_date': '2026-01-01', 'end_date': '2026-07-01', 'final_end_date': '2026-12-31'}
    unresolved = check_contract_period('2026-08-01', contract, identity_confirmed=True)
    assert unresolved.contract_period_status == 'NOT_CHECKED'
    assert unresolved.evaluated_end_date is None
    end = check_contract_period('2026-08-01', contract, identity_confirmed=True,
                                policy=ContractDatePolicy(end_date_field='end_date'))
    final = check_contract_period('2026-08-01', contract, identity_confirmed=True,
                                  policy=ContractDatePolicy(end_date_field='final_end_date'))
    assert end.contract_period_result == ENDED
    assert final.contract_period_result == ACTIVE
    assert final.evaluated_end_date == date(2026, 12, 31)
    assert final.contract_end_date_basis == 'final_end_date'
    contract['end_date'] = None
    assert check_contract_period('2026-08-01', contract, identity_confirmed=True).contract_period_status == 'NOT_CHECKED'


def test_agreeing_end_dates_and_custom_format_can_be_checked_without_precedence():
    contract = {'start_date': '01/01/2026', 'end_date': '31/12/2026', 'final_end_date': '31/12/2026'}
    result = check_contract_period('15/06/2026', contract, identity_confirmed=True, date_format='%d/%m/%Y')
    assert result.contract_period_result == ACTIVE
    assert result.contract_end_date_basis == 'end_date = final_end_date'


def test_ambiguous_identity_never_gets_an_active_contract_conclusion():
    result = check_contract_period('2026-06-15', {'start_date': '2026-01-01', 'end_date': '2026-12-31'},
                                    identity_confirmed=False)
    assert result.contract_period_status == 'NOT_CHECKED'
    assert 'leverantörsidentitet' in result.contract_period_reason


def test_multiple_contracts_keep_distinct_periods_and_do_not_change_supplier_confidence():
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': ['Syntetisk Leverantör AB'] * 3, 'organization_number': ['123'] * 3,
        'contract_id': ['past', 'current', 'future'],
        'start_date': ['2024-01-01', '2026-01-01', '2028-01-01'],
        'end_date': ['2025-12-31', '2027-12-31', '2029-12-31']}))
    data = pd.DataFrame({'header_text': ['Syntetisk Leverantör AB Slutk1'],
                         'verification_date': ['2026-06-15']}, index=[41])
    before = data.copy(deep=True)
    result = analyze_suppliers(data, registry)
    assert result.rows.supplier_match_status.tolist() == ['STRONG_MATCH']
    assert result.contracts.contract_id.tolist() == ['past', 'current', 'future']
    assert result.contracts.contract_period_result.tolist() == [ENDED, ACTIVE, NOT_STARTED]
    assert result.contracts.source_row_position.tolist() == [41] * 3
    assert result.contracts.registry_row_position.tolist() == [0, 1, 2]
    assert result.contracts.verification_date.tolist() == ['2026-06-15'] * 3
    pd.testing.assert_frame_equal(data, before)


def test_period_evidence_export_original_dates_and_summary():
    def workbook(data):
        stream = BytesIO()
        data.to_excel(stream, index=False)
        return stream.getvalue()
    source = pd.DataFrame({'Vernr': ['1', '2', '3'], 'Vrad': [1] * 3,
        'Verdatum': ['2025-06-15', '2026-06-15', '2027-06-15'],
        'Konto': ['4000'] * 3, 'Vertyp': ['X'] * 3, 'Utfall': [1] * 3,
        'Huvudtext': ['Syntetisk Leverantör AB Slutk1'] * 3})
    register = pd.DataFrame({'Leverantör': ['Syntetisk Leverantör AB'], 'Organisationsnummer': ['123'],
        'Avtals-ID': ['Avtal-001'], 'Startdatum': ['2026-01-01'],
        'Slutdatum': ['2026-12-31'], 'Sista slutdatum': ['2026-12-31']})
    review = analyze_upload(workbook(source), registry_content=workbook(register), registry_name='synthetic.xlsx')
    result = review.result
    assert result.summary.contract_status_counts == {'FLAGGED': 2, 'PASS': 1}
    assert result.summary.flagged_verifications == 0  # Separate from procurement/control flags.
    assert result.summary.strong_supplier_rows == 3
    evidence = pd.read_excel(BytesIO(review.downloads['samlad_kontrollfil.xlsx']), 'Möjliga avtal')
    assert evidence.contract_id.tolist() == ['Avtal-001'] * 3
    assert evidence.start_date.tolist() == ['2026-01-01'] * 3
    assert evidence.end_date.tolist() == evidence.final_end_date.tolist() == ['2026-12-31'] * 3
    assert evidence.contract_period_result.tolist() == [NOT_STARTED, ACTIVE, ENDED]
    assert evidence.source_row_position.tolist() == [0, 1, 2]
    assert evidence.contract_period_rule.tolist() == ['contract_period_v1'] * 3
    counts = pd.read_excel(BytesIO(review.downloads['samlad_kontrollfil.xlsx']), 'Sammanfattning').set_index('Mått')['Antal']
    assert counts['Avtalsperioder (avtalsjämförelser): FLAGGED'] == 2
    assert counts['Avtalsperioder (avtalsjämförelser): PASS'] == 1
