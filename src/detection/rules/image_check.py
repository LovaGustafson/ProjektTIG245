"""Check image-reference presence only; never access or interpret documents."""

from src.detection.rules._presence import PresenceScope, check_presence
from src.models.result import CheckResult, CheckStatus
from src.models.verification import Verification


def image_check(
    verification: Verification, *, image_required_confirmed: bool = False,
    confirmed_scope: PresenceScope | None = None,
) -> tuple[CheckResult, ...]:
    """Run only after AK confirms image_reference meaning, requirement and scope.

    PASS means a reference value is present, not that the referenced image
    exists, can be read, or is correct. No file access or OCR is performed.
    TODO: establish the policy with AK; the default remains NOT_CHECKED.
    """
    if image_required_confirmed is not True or confirmed_scope is None:
        return (CheckResult(verification.verification_id, "image_check", CheckStatus.NOT_CHECKED,
                            "TODO / awaiting AK confirmation: image_reference meaning, requirement and scope"),)
    return check_presence(verification, ("image_reference",), confirmed_scope, "image_check")
