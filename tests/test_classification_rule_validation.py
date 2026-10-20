"""Organization-number rule values must be technically usable; synthetic data only."""
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from src.ingestion.contract_reader import classify_organization_number
from src.models.verification import Verification
from src.sampling.classification import classify_identities, load_sampling_rules, sampling_rules
from src.sampling.manual_sample import plan_manual_sample, plan_random_sample
from src.supplier_matching.view_scope import classify_supplier_view, load_view_rules, validate_classification_rules
from tests.synthetic_org import org

VALID = org(123)
WRONG_CHECKSUM = VALID[:-1] + str((int(VALID[-1]) + 1) % 10)
UNUSABLE = {
    'invalid Luhn checksum': (WRONG_CHECKSUM, 'INVALID_CHECKSUM'),
    'invalid Luhn checksum, hyphenated': (f'{WRONG_CHECKSUM[:6]}-{WRONG_CHECKSUM[6:]}', 'INVALID_CHECKSUM'),
    'placeholder SAKNAS': ('SAKNAS', 'INVALID_FORMAT'),
    'placeholder N/A': ('N/A', 'INVALID_FORMAT'),
    'placeholder dash': ('-', 'INVALID_FORMAT'),
    'personal identity number form': ('121212-1212', 'NOT_ORGANIZATION_NUMBER_FORMAT'),
    'personal identity number, compact': ('1212121212', 'NOT_ORGANIZATION_NUMBER_FORMAT'),
    'personal identity number, plus form': ('121212+1212', 'INVALID_FORMAT'),
    '12-digit 16-prefixed identifier': ('16' + VALID, 'INVALID_FORMAT'),
    '12-digit personal identity number': ('191212121212', 'INVALID_FORMAT'),
    'nine digits': (VALID[:9], 'INVALID_FORMAT'),
    'eleven digits': (VALID + '0', 'INVALID_FORMAT'),
    'foreign VAT identifier': ('SE' + VALID + '01', 'INVALID_FORMAT'),
    'foreign identifier': ('DE123456789', 'INVALID_FORMAT'),
    'all zeros': ('0000000000', 'NOT_ORGANIZATION_NUMBER_FORMAT'),
}


def rule(value, *, match_field='organization_number', classification='INTERNAL', rule_id='synthetic-rule'):
    return dict(id=rule_id, match_field=match_field, value=value, classification=classification,
                reason='Syntetisk bekräftad regel.', confirmed=True)


def write_settings(path, **rules):
    path.write_text(yaml.safe_dump(rules, allow_unicode=True), encoding='utf-8')
    return path


def units(names):
    return [Verification(str(i), pd.DataFrame({
        'verification_id': [str(i)], 'verification_line_id': [1],
        'header_text': [f'{name} Prelb 1'], 'counterparty': ['same metadata'],
    }, index=[i * 3])) for i, name in enumerate(names, 1)]


def test_unusable_fixture_statuses_come_from_the_step1_classifier():
    for value, status in UNUSABLE.values():
        assert classify_organization_number(value)[1] == status
    assert classify_organization_number(VALID) == (VALID, 'ORGANIZATION_NUMBER_FORMAT')


@pytest.mark.parametrize('value', [VALID, f'{VALID[:6]}-{VALID[6:]}', f' {VALID[:6]} {VALID[6:]} '])
@pytest.mark.parametrize('classification', ['INTERNAL', 'EXTERNAL'])
def test_valid_organization_rules_keep_compact_comparison_key_for_view_and_sampling(value, classification):
    for validate in (validate_classification_rules, sampling_rules):
        (validated,) = validate([rule(value, classification=classification)])
        assert validated['comparison_key'] == VALID
        assert validated['value'] == value  # The configured evidence is not rewritten.


@pytest.mark.parametrize('value,status', UNUSABLE.values(), ids=UNUSABLE.keys())
def test_unusable_organization_rules_raise_for_view_and_sampling(value, status):
    for validate in (validate_classification_rules, sampling_rules):
        with pytest.raises(ValueError) as error:
            validate([rule(value)])
        # Exact message: names the rule and status but never echoes the raw identifier.
        assert str(error.value) == ('Supplier view rule synthetic-rule needs a technically usable '
                                    f'Swedish organization number ({status})')


@pytest.mark.parametrize('value', ['SAKNAS', WRONG_CHECKSUM, '121212-1212'])
def test_all_rule_entry_points_reject_unusable_organization_rules(tmp_path, value):
    with pytest.raises(ValueError):
        load_view_rules(write_settings(tmp_path / 'view.yaml', supplier_view_rules=[rule(value)]))
    with pytest.raises(ValueError):
        load_sampling_rules(write_settings(tmp_path / 'sample.yaml', sampling_supplier_rules=[rule(value)]))
    with pytest.raises(ValueError):
        plan_manual_sample(units(['A AB']), interval=1, classification_rules=[rule(value)])
    with pytest.raises(ValueError):
        plan_random_sample(units(['A AB']), seed=1, classification_rules=[rule(value)])


@pytest.mark.parametrize('value', [None, '', '   ', 5590001230, True])
def test_missing_or_non_text_organization_values_still_fail_on_existing_shape_check(value):
    for validate in (validate_classification_rules, sampling_rules):
        with pytest.raises(ValueError, match='Each supplier view rule needs'):
            validate([rule(value)])


def test_one_unusable_rule_rejects_the_whole_rule_list():
    with pytest.raises(ValueError):
        validate_classification_rules([rule(VALID, rule_id='valid'), rule('SAKNAS', rule_id='placeholder')])


@pytest.mark.parametrize('value', ['SAKNAS', '1212121212', 'Synthetic AB', '16' + VALID, WRONG_CHECKSUM])
def test_supplier_name_rules_are_unchanged_and_never_organization_validated(value):
    (validated,) = validate_classification_rules([rule(value, match_field='supplier_name')])
    assert validated['comparison_key'] == value.lower()
    assert sampling_rules([rule(value, match_field='supplier_name')]) == (validated,)


def test_valid_organization_rule_still_classifies_only_strong_matches_in_view():
    data = pd.DataFrame({'header_text': ['Org Strong AB Prelb 1', 'Org Weak AB Prelb 1', 'Named AB Prelb 1']},
                        index=[4, 7, 9])
    analysis = SimpleNamespace(registry=SimpleNamespace(available=True), rows=pd.DataFrame({
        'source_row_position': [4, 7], 'supplier_match_status': ['STRONG_MATCH', 'AMBIGUOUS_MATCH'],
        'matched_organization_number': [VALID, VALID]}))
    rules = validate_classification_rules([rule(f'{VALID[:6]}-{VALID[6:]}', rule_id='org'),
                                           rule('Named AB', match_field='supplier_name', rule_id='name')])
    result = classify_supplier_view(data, analysis, rules)
    assert result.classification.tolist() == ['INTERNAL', 'UNCLASSIFIED', 'INTERNAL']
    assert result.rule_ids.tolist() == ['org', '', 'name']


def test_valid_organization_rule_still_classifies_only_strong_identities_in_sampling():
    identities = pd.DataFrame({
        'matched_organization_number': [VALID, VALID, None],
        'identity_basis': ['STRONG_MATCH_ORG', 'NORMALIZED_HEADER_NAME', 'NORMALIZED_HEADER_NAME'],
        'supplier_normalized': ['org strong', 'org weak', 'named']})
    rules = sampling_rules([rule(VALID, classification='EXTERNAL', rule_id='org'),
                            rule('Named', match_field='supplier_name', rule_id='name')])
    result = classify_identities(identities, rules)
    assert result.classification.tolist() == ['EXTERNAL', 'UNCLASSIFIED', 'INTERNAL']
