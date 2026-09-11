"""Technical file-loading statuses, separate from detection results."""

from enum import StrEnum


class ReadStatus(StrEnum):
    LOADED = "LOADED"
    MISSING_REFERENCE = "MISSING_REFERENCE"
    MISSING_FILE = "MISSING_FILE"
    UNSUPPORTED = "UNSUPPORTED"
    UNREADABLE = "UNREADABLE"
