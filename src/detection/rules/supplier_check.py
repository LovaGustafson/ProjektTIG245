"""Supplier rule placeholder; no supplier identity is inferred."""

from src.models.result import CheckResult, CheckStatus
from src.models.verification import Verification


def supplier_check(verification: Verification) -> tuple[CheckResult, ...]:
    """TODO: implement once AK confirms supplier identity and register matching.

    counterparty is not assumed to identify the supplier. No register format or
    procurement matching logic is invented, even if candidate fields exist.
    """
    return (CheckResult(verification.verification_id, "supplier_check", CheckStatus.NOT_CHECKED,
                        "TODO / awaiting AK confirmation: supplier identifier, supplier/procurement "
                        "register structure and reference data; counterparty is not assumed to be the supplier"),)
