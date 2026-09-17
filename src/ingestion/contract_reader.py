"""Load Koncerninköp contracts using explicit headers, preserving source values."""
from collections import OrderedDict
from numbers import Integral, Real
import re

import pandas as pd

from src.ingestion.reference_reader import read_supplier_register
from src.models.supplier import ContractRegistry, Supplier
from src.supplier_matching.normalization import normalize_supplier

CONTRACT_FIELDS = ('supplier_name', 'organization_number', 'contract_name', 'reference_number',
                   'start_date', 'end_date', 'contract_id', 'contract_category',
                   'level_1', 'level_2', 'level_3')


def organization_key(value):
    if pd.isna(value) or isinstance(value, bool):
        return None
    if isinstance(value, Integral) or isinstance(value, Real) and value.is_integer():
        value = str(int(value))
    text = str(value).strip()
    # Formatting only; no checksum, country or corporate-identity inference.
    digits = re.sub(r'[\s-]', '', text)
    return digits if digits.isdigit() else text or None


def registry_from_frame(data, *, columns=None, snapshot=None):
    """Group only by supplied organization number; names alone are not unique IDs."""
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
        org = organization_key(row['organization_number'])
        # Missing IDs cannot prove that two rows belong to the same legal entity.
        key = 'org:' + org if org else f'unknown:{position}'
        group = groups.setdefault(key, {'names': [], 'org': org, 'contracts': []})
        if name not in group['names']:
            group['names'].append(name)
        contract = {field: row.get(field) for field in CONTRACT_FIELDS}
        contract['registry_row_position'] = position
        group['contracts'].append(contract)
        if not org:
            issues.append(f'Registerrad {position + 1}: organisationsnummer saknas; kräver manuell kontroll.')
    suppliers = tuple(Supplier(key, tuple(group['names']), group['org'], tuple(group['contracts']))
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
