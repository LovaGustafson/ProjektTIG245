"""Check each identified supplier's register periods, never purchase applicability."""
from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.models.result import CheckStatus
from src.supplier_matching.date_warning import parse_review_date

ACTIVE = 'Aktivt avtal vid verifikationsdatum'
NOT_STARTED = 'Avtal ännu inte startat'
ENDED = 'Avtal avslutat'
UNVERIFIABLE = 'Avtalsdatum saknas/kan inte verifieras'


@dataclass(frozen=True)
class ContractDatePolicy:
    # None means unconfirmed. A configured choice requires business approval.
    end_date_field: str | None = None
    inclusive_boundaries: bool | None = None

    def __post_init__(self):
        if self.end_date_field not in (None, 'end_date', 'final_end_date'):
            raise ValueError('contract_period.end_date_field must be end_date, final_end_date or null')
        if self.inclusive_boundaries is not None and type(self.inclusive_boundaries) is not bool:
            raise ValueError('contract_period.inclusive_boundaries must be boolean or null')


@dataclass(frozen=True)
class ContractPeriodResult:
    contract_period_status: str
    contract_period_result: str
    contract_period_reason: str
    verification_date_checked: date | None
    evaluated_start_date: date | None
    evaluated_end_date: date | None
    contract_end_date_basis: str | None
    contract_inclusive_boundaries: bool | None
    contract_period_rule: str = 'contract_period_v1'


def check_contract_period(verification_date, contract, *, identity_confirmed,
                          date_format=None, policy=None):
    policy = policy or ContractDatePolicy()
    transaction = parse_review_date(verification_date, date_format=date_format)
    start = parse_review_date(contract.get('start_date'), date_format=date_format)
    end = None
    basis = None

    def result(status, label, reason):
        return ContractPeriodResult(status.value, label, reason, transaction, start, end, basis,
                                    policy.inclusive_boundaries)

    def unavailable(reason):
        return result(CheckStatus.NOT_CHECKED, UNVERIFIABLE, reason)

    if not identity_confirmed:
        return unavailable('Ingen säker leverantörsidentitet; kandidatens avtalsperiod har inte bedömts.')
    if transaction is None or start is None:
        return unavailable('Verifikationsdatum eller avtalets startdatum saknas eller kan inte läsas.')
    if policy.end_date_field is not None:
        basis = policy.end_date_field
        end = parse_review_date(contract.get(basis), date_format=date_format)
    else:
        # Ordinary end_date is usable without inventing an extension rule only
        # when final_end_date is absent or agrees. Disagreements stay unassessed.
        end = parse_review_date(contract.get('end_date'), date_format=date_format)
        final_raw = contract.get('final_end_date')
        final_present = (pd.api.types.is_scalar(final_raw) and not pd.isna(final_raw)
                         and not (isinstance(final_raw, str) and not final_raw.strip()))
        if final_present:
            final = parse_review_date(final_raw, date_format=date_format)
            if end is None or final is None or final != end:
                end = None
                return unavailable('Slutdatum och sista slutdatum kan inte förenas utan en bekräftad datumregel.')
            basis = 'end_date = final_end_date'
        else:
            basis = 'end_date'
    if end is None:
        return unavailable('Slutdatum för den använda avtalsperioden saknas eller kan inte läsas.')
    if end < start:
        return unavailable('Avtalets slutdatum ligger före startdatum; perioden kan inte verifieras.')
    if transaction in (start, end) and policy.inclusive_boundaries is None:
        return unavailable('Datumet ligger på en periodgräns; regeln för giltighet på start-/slutdagen är inte bekräftad.')
    if transaction < start or (transaction == start and policy.inclusive_boundaries is False):
        return result(CheckStatus.FLAGGED, NOT_STARTED, 'Verifikationsdatum ligger före avtalets giltiga period.')
    if transaction > end or (transaction == end and policy.inclusive_boundaries is False):
        return result(CheckStatus.FLAGGED, ENDED, 'Verifikationsdatum ligger efter avtalets giltiga period.')
    return result(CheckStatus.PASS, ACTIVE,
                  'Verifikationsdatum ligger inom registerpostens avtalsperiod. Köpets avtalstillhörighet har inte kontrollerats.')
