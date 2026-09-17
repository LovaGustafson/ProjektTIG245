"""Deterministic comparison keys; original names are never replaced."""
import re
import unicodedata

LEGAL_FORMS = {'ab', 'hb', 'kb', 'ek för'}


def normalize_supplier(value: object) -> str:
    if not isinstance(value, str):
        return ''
    text = unicodedata.normalize('NFKC', value).casefold()
    text = ''.join(' ' if unicodedata.category(char)[0] in ('P', 'Z') else char
                   for char in text)
    text = ' '.join(text.split())
    # Only equivalent, explicit legal designations. Never equate HB and KB.
    for pattern, replacement in [
        (r'\baktiebolag(?:et)?\b', 'ab'), (r'\bhandelsbolag\b', 'hb'),
        (r'\bkommanditbolag\b', 'kb'),
        (r'\bekonomisk förening\b', 'ek för'), (r'\bek förening\b', 'ek för'),
    ]:
        text = re.sub(pattern, replacement, text)
    return text


def split_legal_form(normalized: str) -> tuple[str, str | None]:
    for form in sorted(LEGAL_FORMS, key=len, reverse=True):
        if normalized.endswith(' ' + form):
            return normalized[:-len(form)].strip(), form
    return normalized, None
