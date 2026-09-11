"""Attestation rule placeholder pending confirmed business rules and register."""

from src.models.result import CheckResult, CheckStatus
from src.models.verification import Verification


def attestation_check(verification: Verification) -> tuple[CheckResult, ...]:
    """Do not infer authorization from the presence of signature or attestation.

    TODO: implement after AK confirms field meanings, authorization and flow
    rules, register structure, and usable reference data is supplied.
    """
    return (CheckResult(verification.verification_id, "attestation_check", CheckStatus.NOT_CHECKED,
                        "TODO / awaiting AK confirmation: Sign/Att meanings, attestation flow and "
                        "authorization rules, and confirmed attestation reference data"),)
