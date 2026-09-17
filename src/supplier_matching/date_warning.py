"""Snapshot freshness is separate from supplier identity and contract validity."""
from datetime import date, datetime

import pandas as pd

STALE_REGISTRY_MESSAGE = ('Avtalsregistret är äldre än transaktionen – resultatet behöver '
                          'verifieras mot senare register.')


def registry_date_check(value, snapshot, *, date_format=None):
    if snapshot is None:
        return False, 'UNKNOWN', 'Registerdatum saknas; registerålder kunde inte kontrolleras.'
    parsed = None
    if pd.api.types.is_scalar(value) and not pd.isna(value):
        if isinstance(value, datetime):
            parsed = value.date()
        elif isinstance(value, date):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = (datetime.strptime(value.strip(), date_format) if date_format else
                          datetime.fromisoformat(value.strip())).date()
            except ValueError:
                pass
    if parsed is None:
        return False, 'UNKNOWN', 'Transaktionsdatum saknas eller är ogiltigt; registerålder kunde inte kontrolleras.'
    if parsed > snapshot:
        return True, 'AFTER_SNAPSHOT', STALE_REGISTRY_MESSAGE
    return False, 'ON_OR_BEFORE_SNAPSHOT', ''
