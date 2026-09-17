"""Identity and contract evidence independent of the identity resolution method."""
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

import pandas as pd


class SupplierMatchStatus(StrEnum):
    STRONG_MATCH = 'STRONG_MATCH'
    AMBIGUOUS_MATCH = 'AMBIGUOUS_MATCH'
    NO_MATCH = 'NO_MATCH'
    SUPPLIER_NOT_IDENTIFIED = 'SUPPLIER_NOT_IDENTIFIED'


@dataclass(frozen=True)
class Supplier:
    key: str
    names: tuple[str, ...]
    organization_number: str | None
    contracts: tuple[dict, ...]


@dataclass(frozen=True)
class SupplierCandidate:
    supplier: Supplier
    matched_name: str
    method: str
    score: float
    reason: str
    strong_eligible: bool


@dataclass(frozen=True)
class SupplierMatch:
    supplier_text_raw: str | None
    supplier_normalized: str
    status: SupplierMatchStatus
    method: str
    score: float | None
    reason: str
    candidates: tuple[SupplierCandidate, ...] = ()


@dataclass
class ContractRegistry:
    suppliers: tuple[Supplier, ...] = ()
    data: pd.DataFrame = field(default_factory=pd.DataFrame)
    available: bool = False
    issues: tuple[str, ...] = ()
    snapshot_date: date | None = None
