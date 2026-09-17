"""Keep procurement compliance unassessed; supplier identity is reported separately."""

from src.models.result import CheckResult, CheckStatus
from src.models.verification import Verification


def supplier_check(verification: Verification, *, identity_matching_available=False) -> tuple[CheckResult, ...]:
    """A name match never establishes which contract covers the purchase.

    The row-level identity result is separate from this verification-level
    compliance check. TODO / AK: purchase-to-contract scope and compliance rules.
    Missing evidence retains the previous unresolved-control result.
    """
    if identity_matching_available:
        return (CheckResult(verification.verification_id, 'supplier_check', CheckStatus.NOT_CHECKED,
                            'Leverantörsmatchning redovisas separat per transaktionsrad. '
                            'Avtalstrohet har inte kontrollerats; vilket avtal fakturan avser är inte fastställt.'),)
    return (CheckResult(verification.verification_id, "supplier_check", CheckStatus.NOT_CHECKED,
                        "TODO / awaiting AK confirmation: supplier identifier, supplier/procurement "
                        "register structure and reference data; counterparty is not assumed to be the supplier"),)
