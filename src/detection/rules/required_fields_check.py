"""Check business information only under an explicitly confirmed presence policy."""

from collections.abc import Sequence

from src.detection.rules._presence import PresenceScope, check_presence
from src.models.result import CheckResult, CheckStatus
from src.models.verification import Verification


def required_fields_check(
    verification: Verification, *,
    confirmed_required_fields: Sequence[str] | None = None,
    confirmed_scope: PresenceScope | None = None,
) -> tuple[CheckResult, ...]:
    """Return one result per required field (and per row for each_row scope).

    TODO / awaiting AK: mandatory information, field meanings and scope.
    Callers may supply confirmed standardized names and scope once established;
    supplying these arguments declares that policy confirmed. No defaults are
    inferred from examples or from the Validator's mandatory technical fields.
    Empty confirmed lists mean no check applies, not an invoice PASS.
    """
    if confirmed_required_fields is None or confirmed_scope is None:
        return (CheckResult(verification.verification_id, "required_fields_check",
                            CheckStatus.NOT_CHECKED,
                            "TODO / awaiting AK confirmation: required information and check scope"),)
    if (isinstance(confirmed_required_fields, str)
            or not isinstance(confirmed_required_fields, Sequence)
            or any(not isinstance(field, str) or not field.strip()
                   for field in confirmed_required_fields)):
        return (CheckResult(verification.verification_id, "required_fields_check",
                            CheckStatus.ERROR, "Required fields must be a sequence of nonblank field names"),)
    if not confirmed_required_fields:
        return (CheckResult(verification.verification_id, "required_fields_check",
                            CheckStatus.NOT_CHECKED, "No required information checks configured"),)
    return check_presence(verification, tuple(confirmed_required_fields), confirmed_scope,
                          "required_fields_check")
