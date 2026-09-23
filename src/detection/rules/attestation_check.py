"""Attestation rule placeholder pending confirmed business rules and register."""

from src.models.result import CheckResult, CheckStatus
from src.models.verification import Verification


def attestation_check(verification: Verification) -> tuple[CheckResult, ...]:
    """Do not infer authorization from the presence of signature or attestation.

    Any future implementation requires confirmed field meanings, authorization
    and flow rules, register structure and usable reference data. If it falls
    under current Won't Have scope, an explicit customer scope change is also
    required; rule confirmation alone does not authorize that work. See
    MOSCOW_CURRENT.md W1 and OPEN_QUESTIONS.md Q10.
    """
    return (CheckResult(verification.verification_id, "attestation_check", CheckStatus.NOT_CHECKED,
                        "TODO / awaiting AK confirmation: Sign/Att meanings, attestation flow and "
                        "authorization rules, and confirmed attestation reference data"),)
