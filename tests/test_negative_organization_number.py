"""Negative identifiers must never become usable organization identities; synthetic data only."""
from decimal import Decimal
from io import BytesIO

import numpy as np
import pandas as pd
import pytest

from src.ingestion.contract_reader import (USABLE_ORGANIZATION_NUMBER_STATUSES, classify_organization_number,
                                           organization_key, registry_from_frame)
from src.models.verification import Verification
from src.sampling.manual_sample import plan_manual_sample, plan_random_sample
from src.supplier_matching.analysis import analyze_suppliers
from src.supplier_matching.matcher import SupplierMatcher
from src.supplier_matching.view_scope import validate_classification_rules
from src.ui_support import analyze_upload
from tests.synthetic_org import org
from tests.test_feature_package import invoices, settings, workbook

VALID = org(123)
NUMBER = int(VALID)
HYPHENATED = f'{VALID[:6]}-{VALID[6:]}'
NEGATIVE_FORMS = [
    pytest.param(-NUMBER, id='negative-int'),
    pytest.param(np.int64(-NUMBER), id='negative-numpy-int'),
    pytest.param(float(-NUMBER), id='negative-float'),
    pytest.param(np.float64(-NUMBER), id='negative-numpy-float'),
    pytest.param(Decimal(-NUMBER), id='negative-decimal'),
    pytest.param('-' + VALID, id='negative-text'),
    pytest.param('-' + HYPHENATED, id='negative-hyphenated-text'),
    pytest.param(' -' + VALID + ' ', id='negative-text-with-spaces'),
    pytest.param('- ' + VALID, id='minus-space-text'),
    pytest.param('--' + VALID, id='double-minus'),
    pytest.param('---' + HYPHENATED, id='triple-minus-hyphenated'),
    pytest.param('- -' + VALID, id='spaced-repeated-minus'),
]


def leading_zero_number():
    """A Luhn-valid ten-digit text value with a leading zero and third digit >= 2."""
    prefix = '023456789'
    total = sum(sum(divmod(int(d) * (2 if i % 2 == 0 else 1), 10)) for i, d in enumerate(prefix))
    return prefix + str(-total % 10)


def contract_frame(names, identifiers):
    count = len(names)
    return pd.DataFrame({'supplier_name': names, 'organization_number': identifiers,
                         'contract_id': [f'C{i}' for i in range(count)], 'contract_name': ['Testavtal'] * count,
                         'start_date': ['2026-01-01'] * count, 'end_date': ['2026-12-31'] * count})


def source(names):
    return pd.DataFrame({'verification_id': [str(i) for i in range(1, len(names) + 1)],
                         'verification_line_id': [1] * len(names),
                         'header_text': [f'{name} Prelb 1' for name in names],
                         'verification_date': ['2026-06-15'] * len(names)}, index=range(10, 10 + len(names)))


def units(data):
    return [Verification(row.verification_id, data.loc[[position]]) for position, row in data.iterrows()]


@pytest.mark.parametrize('value', NEGATIVE_FORMS)
def test_negative_identifiers_are_never_usable_and_never_collide(value):
    key, status = classify_organization_number(value)
    assert status == 'INVALID_FORMAT'
    assert status not in USABLE_ORGANIZATION_NUMBER_STATUSES
    assert key != VALID and key.startswith('-')


@pytest.mark.parametrize('value', [VALID, NUMBER, float(NUMBER), np.int64(NUMBER), HYPHENATED,
                                   f' {VALID[:6]} {VALID[6:]} ', f'{VALID[:6]} - {VALID[6:]}'])
def test_valid_positive_and_hyphenated_numbers_remain_usable(value):
    assert classify_organization_number(value) == (VALID, 'ORGANIZATION_NUMBER_FORMAT')


def test_valid_text_with_leading_zero_remains_usable_and_negative_form_does_not():
    number = leading_zero_number()
    assert classify_organization_number(number) == (number, 'ORGANIZATION_NUMBER_FORMAT')
    assert classify_organization_number(f'{number[:6]}-{number[6:]}') == (number, 'ORGANIZATION_NUMBER_FORMAT')
    assert classify_organization_number('-' + number)[1] == 'INVALID_FORMAT'


def test_organization_key_formatting_is_unchanged():
    assert organization_key(-NUMBER) == VALID
    assert organization_key('--' + HYPHENATED) == VALID


@pytest.mark.parametrize('negative', NEGATIVE_FORMS)
def test_negative_row_is_not_grouped_with_the_positive_identity(negative):
    registry = registry_from_frame(contract_frame(['Alpha AB', 'Beta AB'], [VALID, negative]))
    assert [s.key for s in registry.suppliers] == [f'org:{VALID}', 'unknown:1']
    assert registry.suppliers[1].organization_number is None
    assert registry.suppliers[1].organization_number_status == 'INVALID_FORMAT'
    assert registry.issues == ('Registerrad 2: organisationsnumret är inte tekniskt användbart '
                               '(INVALID_FORMAT); kräver manuell kontroll.',)


@pytest.mark.parametrize('negative', [-NUMBER, '-' + HYPHENATED, '--' + VALID])
def test_sole_negative_identity_gives_no_strong_match_or_contract_pass(negative):
    analysis = analyze_suppliers(source(['Bonliva AB']), registry_from_frame(contract_frame(['Bonliva AB'], [negative])))
    assert analysis.rows.supplier_match_status.tolist() == ['AMBIGUOUS_MATCH']
    assert analysis.rows.matched_organization_number.isna().all()
    assert analysis.candidates.organization_number.isna().all()
    assert analysis.contracts.contract_period_status.tolist() == ['NOT_CHECKED']


@pytest.mark.parametrize('negative', [-NUMBER, '-' + HYPHENATED, '--' + VALID])
def test_negative_alias_of_a_valid_number_competes_instead_of_merging(negative):
    frame = contract_frame(['Securitas Sverige AB', 'Securitas Svergie AB'], [VALID, negative])
    for order in (frame, frame.iloc[::-1]):
        result = SupplierMatcher(registry_from_frame(order).suppliers).match('Securitas Sverige AB')
        assert result.status == 'AMBIGUOUS_MATCH'
        assert result.selected_supplier_key is None
        assert len(result.candidates) == 2
    analysis = analyze_suppliers(source(['Securitas Sverige AB']), registry_from_frame(frame))
    assert analysis.rows.supplier_match_status.tolist() == ['AMBIGUOUS_MATCH']
    assert analysis.contracts.contract_period_status.eq('NOT_CHECKED').all()


def test_valid_positive_identity_keeps_strong_match_and_contract_pass():
    analysis = analyze_suppliers(source(['Bonliva AB']), registry_from_frame(contract_frame(['Bonliva AB'], [HYPHENATED])))
    assert analysis.rows.supplier_match_status.tolist() == ['STRONG_MATCH']
    assert analysis.rows.matched_organization_number.tolist() == [VALID]
    assert analysis.contracts.contract_period_status.tolist() == ['PASS']


def test_negative_alias_cannot_borrow_classification_or_sampling_identity():
    data = source(['Alpha AB', 'Beta AB'])
    analysis = analyze_suppliers(data, registry_from_frame(contract_frame(['Alpha AB', 'Beta AB'], [VALID, -NUMBER])))
    assert analysis.rows.supplier_match_status.tolist() == ['STRONG_MATCH', 'AMBIGUOUS_MATCH']
    rule = dict(id='synthetic-org', match_field='organization_number', value=VALID, classification='EXTERNAL',
                reason='Syntetisk bekräftad regel.', confirmed=True)
    for result in (plan_manual_sample(units(data), interval=1, supplier_analysis=analysis, classification_rules=[rule]),
                   plan_random_sample(units(data), seed=7, supplier_analysis=analysis, classification_rules=[rule])):
        assert result.identity_rows.supplier_key.tolist() == [f'org:{VALID}', 'name:beta ab']
        assert result.classification_rows.classification.tolist() == ['EXTERNAL', 'UNCLASSIFIED']
        assert sorted(v.verification_id for v in result.sample) == ['1', '2']
        assert 'DUPLICATE_SUPPLIER' not in result.decisions.decision.tolist()


@pytest.mark.parametrize('negative', ['-' + VALID, '--' + HYPHENATED])
def test_negative_classification_rule_values_are_rejected(negative):
    with pytest.raises(ValueError, match='INVALID_FORMAT'):
        validate_classification_rules([dict(id='negative', match_field='organization_number', value=negative,
                                            classification='INTERNAL', reason='Syntetisk.', confirmed=True)])


@pytest.mark.parametrize('negative', [-NUMBER, float(-NUMBER), '-' + HYPHENATED, '--' + VALID])
def test_excel_register_with_negative_identifier_never_matches_strongly_or_passes(tmp_path, negative):
    register = pd.DataFrame({'Leverantör': ['Syntetisk Leverantör AB'], 'Organisationsnummer': [negative],
                             'Avtals-ID': ['Avtal-001'], 'Startdatum': ['2026-01-01'], 'Slutdatum': ['2026-12-31']})
    upload = analyze_upload(workbook(invoices(1)), registry_mode='uploaded', registry_content=workbook(register),
                            registry_name='synthetic.xlsx', settings_path=settings(tmp_path))
    analysis = upload.result.supplier_analysis
    assert analysis.registry.available
    assert analysis.rows.supplier_match_status.tolist() == ['AMBIGUOUS_MATCH']
    assert analysis.contracts.contract_period_status.tolist() == ['NOT_CHECKED']
    with pd.ExcelFile(BytesIO(upload.downloads['granskning.xlsx'])) as book:
        rows = pd.read_excel(book, 'Leverantörsmatchning')
        candidates = pd.read_excel(book, 'Leverantörskandidater')
        contracts = pd.read_excel(book, 'Möjliga avtal')
    assert rows.supplier_match_status.tolist() == ['AMBIGUOUS_MATCH']
    assert rows.matched_organization_number.isna().all()
    assert candidates.organization_number.isna().all()
    assert contracts.contract_period_status.tolist() == ['NOT_CHECKED']


def test_excel_register_with_valid_identifier_still_matches_and_passes(tmp_path):
    register = pd.DataFrame({'Leverantör': ['Syntetisk Leverantör AB'], 'Organisationsnummer': [HYPHENATED],
                             'Avtals-ID': ['Avtal-001'], 'Startdatum': ['2026-01-01'], 'Slutdatum': ['2026-12-31']})
    upload = analyze_upload(workbook(invoices(1)), registry_mode='uploaded', registry_content=workbook(register),
                            registry_name='synthetic.xlsx', settings_path=settings(tmp_path))
    analysis = upload.result.supplier_analysis
    assert analysis.rows.supplier_match_status.tolist() == ['STRONG_MATCH']
    assert analysis.contracts.contract_period_status.tolist() == ['PASS']
    rows = pd.read_excel(BytesIO(upload.downloads['granskning.xlsx']), 'Leverantörsmatchning', dtype=str)
    assert rows.matched_organization_number.tolist() == [VALID]
