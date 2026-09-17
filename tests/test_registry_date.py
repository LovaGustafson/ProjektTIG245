from datetime import date, datetime

import pandas as pd
import pytest

from src.supplier_matching.date_warning import registry_date_check, STALE_REGISTRY_MESSAGE


@pytest.mark.parametrize('value, warning, status', [
    ('2026-09-01', True, 'AFTER_SNAPSHOT'),
    (datetime(2026, 8, 31, 23, 59), False, 'ON_OR_BEFORE_SNAPSHOT'),
    (date(2026, 8, 30), False, 'ON_OR_BEFORE_SNAPSHOT'),
    (None, False, 'UNKNOWN'), (pd.NaT, False, 'UNKNOWN'),
    (pd.NA, False, 'UNKNOWN'), ('fel', False, 'UNKNOWN'), (46000, False, 'UNKNOWN'),
])
def test_snapshot_date_warning(value, warning, status):
    actual, actual_status, message = registry_date_check(value, date(2026, 8, 31))
    assert (actual, actual_status) == (warning, status)
    if warning:
        assert message == STALE_REGISTRY_MESSAGE


def test_configured_snapshot_and_explicit_date_format():
    assert not registry_date_check('2026-09-01', date(2026, 9, 2))[0]
    assert registry_date_check('01/09/2026', date(2026, 8, 31), date_format='%d/%m/%Y')[0]
    assert registry_date_check('2026-09-01', None)[1] == 'UNKNOWN'
