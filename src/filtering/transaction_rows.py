"""Recognize structural report rows, without discarding incomplete invoices."""
import re

import pandas as pd

from src.mapping.column_mapper import COLUMN_ALIASES


def non_transaction_reason(row):
    values = [v for v in row if not (pd.api.types.is_scalar(v) and pd.isna(v))
              and not (isinstance(v, str) and not v.strip())]
    if not values:
        return 'tom rapportrad'
    headers = {COLUMN_ALIASES.get(v.strip(), v.strip()) for v in values if isinstance(v, str)}
    if len(headers & {'verification_id', 'verification_line_id', 'account',
                      'verification_date', 'amount', 'verification_type'}) >= 3:
        return 'upprepad tabellrubrik'
    # Never infer a report row merely from a missing/invalid invoice identity.
    def blank(field):
        value = row.get(field)
        return pd.api.types.is_scalar(value) and (pd.isna(value) or str(value).strip() == '')
    def report_label(value):
        return isinstance(value, str) and re.match(
            r'^(?:summa|totalt|totalsumma|delsumma|rapport|utskriftsdatum)(?:\s|:|$)',
            value.strip(), re.IGNORECASE)
    # Observed report footer: report title + page counter + print timestamp.
    # Require all three signals and no transaction identity; missing fields alone
    # must never hide an incomplete invoice. Do not interpret Mm or other fields.
    texts = [v.strip() for v in values if isinstance(v, str)]
    if (all(blank(field) for field in ('verification_id', 'verification_line_id',
                                      'verification_date', 'account', 'verification_type',
                                      'header_text', 'line_text'))
            and any(re.search(r'\bVerifikationslista\b', v, re.I) for v in texts)
            and any(re.fullmatch(r'-\s*\d+\s+av\s+\d+\s*-', v, re.I) for v in texts)
            and any(re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}[.:]\d{2}[.:]\d{2}(?:\s|$)', v)
                    for v in texts)):
        return 'rapportfot med rapporttitel, sidnumrering och utskriftstid'
    if (blank('verification_line_id') and blank('account') and blank('verification_type')
            and (blank('verification_id') or report_label(row.get('verification_id')))):
        if any(report_label(v) for v in values):
            return 'summa-/rapportrad utan transaktionsuppgifter'
    return ''
