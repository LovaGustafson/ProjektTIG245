"""Apply identity resolution to each remaining transaction, retaining audit evidence."""
from dataclasses import dataclass, asdict, fields
import logging

import pandas as pd

from src.ingestion.contract_reader import CONTRACT_FIELDS
from src.models.supplier import ContractRegistry, SupplierMatchStatus as Status
from src.supplier_matching.date_warning import registry_date_check
from src.supplier_matching.extraction import extract_supplier, normalize_header_text
from src.supplier_matching.matcher import SupplierMatcher
from src.supplier_matching.contract_period import check_contract_period, ContractPeriodResult

LOGGER = logging.getLogger(__name__)
ROW_FIELDS = ['source_row_position', 'header_text_normalized', 'supplier_text_raw', 'supplier_normalized',
              'supplier_match_status', 'matched_supplier_name', 'matched_organization_number',
              'supplier_match_method', 'supplier_match_score', 'supplier_match_reason',
              'candidate_count', 'contract_count', 'registry_snapshot_date',
              'registry_date_warning', 'registry_date_check', 'registry_date_message']
CANDIDATE_FIELDS = ['source_row_position', 'supplier_key', 'supplier_name',
                    'organization_number', 'method', 'score', 'reason', 'strong_eligible',
                    'contract_count']
CONTRACT_COLUMNS = ['source_row_position', 'supplier_key', 'supplier_match_status',
                    'registry_row_position', *CONTRACT_FIELDS, 'verification_date',
                    *[f.name for f in fields(ContractPeriodResult)]]


@dataclass
class SupplierAnalysis:
    registry: ContractRegistry
    rows: pd.DataFrame
    candidates: pd.DataFrame
    contracts: pd.DataFrame

    def summary(self):
        counts = self.rows['supplier_match_status'].value_counts()
        return {'Leverantörsmatchning – analyserade rader': len(self.rows),
                'Starka leverantörsträffar': int(counts.get(Status.STRONG_MATCH, 0)),
                'Osäkra leverantörsträffar': int(counts.get(Status.AMBIGUOUS_MATCH, 0)),
                'Ingen match i aktuellt register': int(counts.get(Status.NO_MATCH, 0)),
                'Leverantör ej identifierad': int(counts.get(Status.SUPPLIER_NOT_IDENTIFIED, 0)),
                'Rader med datumvarning': int(self.rows['registry_date_warning'].sum())}


def analyze_suppliers(data, registry, *, settings=None, date_format=None, matcher=None, contract_policy=None):
    # An unavailable register must never be reported as an actual NO_MATCH.
    rows, candidates, contracts = [], [], []
    if not registry.available:
        return SupplierAnalysis(registry, pd.DataFrame(columns=ROW_FIELDS),
                                pd.DataFrame(columns=CANDIDATE_FIELDS),
                                pd.DataFrame(columns=CONTRACT_COLUMNS))
    engine = matcher or SupplierMatcher(registry.suppliers, settings)
    for position, row in data.iterrows():
        def value(field):
            return row[field] if list(data.columns).count(field) == 1 else None
        result = engine.match(extract_supplier(value('header_text')))
        strong = result.status == Status.STRONG_MATCH
        chosen = result.candidates[0] if strong else None
        warning, date_status, date_message = registry_date_check(
            value('verification_date'), registry.snapshot_date, date_format=date_format)
        rows.append(dict(source_row_position=position, header_text_normalized=normalize_header_text(value('header_text')),
            supplier_text_raw=result.supplier_text_raw,
            supplier_normalized=result.supplier_normalized, supplier_match_status=result.status.value,
            matched_supplier_name=chosen.matched_name if chosen else None,
            matched_organization_number=chosen.supplier.organization_number if chosen else None,
            supplier_match_method=result.method, supplier_match_score=result.score,
            supplier_match_reason=result.reason, candidate_count=len(result.candidates),
            contract_count=len(chosen.supplier.contracts) if chosen else 0,
            registry_snapshot_date=registry.snapshot_date, registry_date_warning=warning,
            registry_date_check=date_status, registry_date_message=date_message))
        for candidate in result.candidates:
            supplier = candidate.supplier
            candidates.append(dict(source_row_position=position, supplier_key=supplier.key,
                supplier_name=candidate.matched_name, organization_number=supplier.organization_number,
                method=candidate.method, score=candidate.score, reason=candidate.reason,
                strong_eligible=candidate.strong_eligible, contract_count=len(supplier.contracts)))
            for contract in supplier.contracts:
                period = check_contract_period(value('verification_date'), contract,
                    identity_confirmed=strong, date_format=date_format, policy=contract_policy)
                contracts.append(dict(contract, source_row_position=position,
                                      supplier_key=supplier.key, supplier_match_status=result.status.value,
                                      verification_date=value('verification_date'), **asdict(period)))
    analysis = SupplierAnalysis(registry, pd.DataFrame(rows, columns=ROW_FIELDS),
                                pd.DataFrame(candidates, columns=CANDIDATE_FIELDS),
                                pd.DataFrame(contracts, columns=CONTRACT_COLUMNS))
    LOGGER.info('Supplier matching counts: %s', analysis.summary())
    return analysis


def enrich_rows(data, analysis):
    """Join by source row position, not invoice/supplier ID; avoid source collisions."""
    result = data.copy(deep=True)
    if analysis is None or not analysis.registry.available:
        return result
    evidence = analysis.rows.set_index('source_row_position').reindex(data.index)
    for field in ROW_FIELDS:
        name = field
        while name in result.columns:
            name = '_' + name
        result[name] = list(data.index) if field == 'source_row_position' else evidence[field].tolist()
    return result
