"""Comparison keys for Excel identifiers; never rewrite source cells."""
from numbers import Integral

import numpy as np


def normalize_identifier(value: object) -> str | None:
    """Accept text or finite integral Excel numbers without rounding.

    Text identifiers retain their exact spelling, including leading zeros and
    whitespace. Decimal-looking text is not reinterpreted as an Excel number:
    its provenance cannot be established from a string alone. Invalid/missing
    values return None; validation distinguishes missing from invalid values.
    """
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, (bool, np.bool_)):
        return None
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, (float, np.floating)) and np.isfinite(value) and value.is_integer():
        return str(int(value))
    return None
