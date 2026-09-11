"""Shared, immutable result from one detection check."""

from dataclasses import dataclass
from enum import StrEnum


class CheckStatus(StrEnum):
    PASS = "PASS"
    FLAGGED = "FLAGGED"
    ERROR = "ERROR"
    NOT_CHECKED = "NOT_CHECKED"


@dataclass(frozen=True)
class CheckResult:
    verification_id: object
    check_type: str
    status: CheckStatus
    reason: str
    verification_line_id: object = None
    field: str | None = None
    row_position: int | None = None

    def __post_init__(self):
        object.__setattr__(self, "status", CheckStatus(self.status))
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Every check result must include a nonblank reason")
