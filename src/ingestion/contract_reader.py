"""Load Koncerninköp contracts using explicit headers, preserving source values."""
from collections import OrderedDict
from numbers import Integral, Real
import re

import pandas as pd

from src.ingestion.reference_reader import read_supplier_register
from src.models.supplier import ContractRegistry, Supplier
from src.supplier_matching.normalization import normalize_supplier

CONTRACT_FIELDS = ('supplier_name', 'organization_number', 'contract_name', 'reference_number',
                   'start_date', 'end_date', 'final_end_date', 'contract_id', 'contract_category',
                   'level_1', 'level_2', 'level_3')

USABLE_ORGANIZATION_NUMBER_STATUSES = frozenset({'ORGANIZATION_NUMBER_FORMAT'})


def organization_key(value):
    if pd.isna(value) or isinstance(value, bool):
        return None
    if isinstance(value, Integral) or isinstance(value, Real) and value.is_integer():
        value = str(int(value))
    text = str(value).strip()
    # Formatting only; no checksum, country or corporate-identity inference.
    digits = re.sub(r'[\s-]', '', text)
    return digits if digits.isdigit() else text or None


def classify_organization_number(value: object) -> tuple[str | None, str]:
    """Return a scalar's formatted key and technical validation status.

    Nonmissing invalid keys are retained; callers must check membership in
    USABLE_ORGANIZATION_NUMBER_STATUSES before using a key as an identity.
    Only ten ASCII digits with a valid Luhn checksum and third digit >= 2
    are usable. Technical validity does not verify a registered legal identity.
    """
    # Include numpy booleans from pandas without changing organization_key.
    if pd.api.types.is_bool(value):
        return None, 'MISSING'
    key = organization_key(value)
    if key is None:
        return None, 'MISSING'
    # organization_key removes every hyphen, including a leading minus sign. Reject
    # negative numbers and text with leading minus signs before that can collide
    # with a usable identity; the returned key keeps the sign so it stays distinct.
    if str(value).strip().startswith('-'):
        return (key if key.startswith('-') else '-' + key), 'INVALID_FORMAT'
    if re.fullmatch(r'[0-9]{10}', key) is None:
        return key, 'INVALID_FORMAT'
    total = 0
    for index, digit in enumerate(key):
        number = int(digit) * (2 if index % 2 == 0 else 1)
        total += number - 9 if number > 9 else number
    if total % 10:
        return key, 'INVALID_CHECKSUM'
    if key[2] < '2':
        return key, 'NOT_ORGANIZATION_NUMBER_FORMAT'
    return key, 'ORGANIZATION_NUMBER_FORMAT'


def registry_from_frame(data, *, columns=None, snapshot=None):
    """Group by technically usable organization numbers, preserving source evidence."""
    columns = columns or {field: [field] for field in CONTRACT_FIELDS}
    aliases = {}
    for field, names in columns.items():
        if field not in CONTRACT_FIELDS or not isinstance(names, list):
            raise ValueError('registry_columns måste mappa interna fält till listor av rubriker.')
        for name in names:
            if name in aliases and aliases[name] != field:
                raise ValueError(f'Tvetydig registermappning: {name}')
            aliases[name] = field
    mapped = data.rename(columns=lambda name: aliases.get(str(name).strip(), name)).copy(deep=True)
    issues = []
    for field in CONTRACT_FIELDS:
        count = list(mapped.columns).count(field)
        if count > 1 or (count == 0 and field in ('supplier_name', 'organization_number')):
            issues.append(f'Registerkolumn {field} saknas eller är tvetydig.')
    if issues:
        return ContractRegistry(data=data.copy(deep=True), issues=tuple(issues), snapshot_date=snapshot)
    missing_details = [field for field in ('contract_id', 'contract_name', 'start_date', 'end_date')
                       if field not in mapped.columns]
    if missing_details:
        issues.append('Avtalsdetaljer är ofullständiga; kolumner saknas: ' + ', '.join(missing_details) + '.')
    groups = OrderedDict()
    for position, (_, row) in enumerate(mapped.iterrows()):
        name = row['supplier_name']
        if not isinstance(name, str) or not normalize_supplier(name):
            issues.append(f'Registerrad {position + 1}: leverantörsnamn saknas; raden används inte för matchning.')
            continue
        org, org_status = classify_organization_number(row['organization_number'])
        if org_status not in USABLE_ORGANIZATION_NUMBER_STATUSES:
            org = None
        # Missing or invalid IDs cannot establish a shared supplier identity.
        key = 'org:' + org if org else f'unknown:{position}'
        group = groups.setdefault(key, {'names': [], 'org': org, 'org_status': org_status, 'contracts': []})
        if name not in group['names']:
            group['names'].append(name)
        contract = {field: row.get(field) for field in CONTRACT_FIELDS}
        contract['registry_row_position'] = position
        group['contracts'].append(contract)
        if org_status == 'MISSING':
            issues.append(f'Registerrad {position + 1}: organisationsnummer saknas; kräver manuell kontroll.')
        elif org is None:
            issues.append(f'Registerrad {position + 1}: organisationsnumret är inte tekniskt användbart '
                          f'({org_status}); kräver manuell kontroll.')
    suppliers = tuple(Supplier(key, tuple(group['names']), group['org'], tuple(group['contracts']),
                               organization_number_status=group['org_status'])
                      for key, group in groups.items())
    if not suppliers:
        issues.append('Registret innehåller inga användbara leverantörsrader.')
    return ContractRegistry(suppliers, data.copy(deep=True), bool(suppliers), tuple(issues), snapshot)


def read_contract_registry(path, *, config, snapshot=None):
    columns = config.get('registry_columns') or {field: [field] for field in CONTRACT_FIELDS}
    aliases = {name: field for field, names in columns.items() for name in names}
    result = read_supplier_register(path, sheet_name=config.get('registry_sheet', 0),
                                   delimiter=config.get('csv_delimiter', ';'),
                                   encoding=config.get('csv_encoding', 'utf-8-sig'),
                                   header_aliases=aliases, header_minimum_fields=2)
    if result.data is None:
        return ContractRegistry(issues=(f'Koncerninköpsregistret kunde inte läsas: {result.reason}',),
                                snapshot_date=snapshot)
    return registry_from_frame(result.data, columns=columns, snapshot=snapshot)
