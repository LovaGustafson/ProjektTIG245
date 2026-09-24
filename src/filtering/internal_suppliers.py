"""Exact internal-supplier expressions; no substring/fuzzy exclusions."""
import unicodedata

from src.supplier_matching.extraction import extract_supplier, normalize_header_text


def internal_supplier_key(value):
    if not isinstance(value, str):
        return ''
    return ''.join(unicodedata.normalize('NFKC', value).casefold().split())


def internal_supplier_rule(header_text, configured_names):
    candidate = extract_supplier(header_text) or normalize_header_text(header_text)
    key = internal_supplier_key(candidate)
    return next((name for name in configured_names
                 if key and key == internal_supplier_key(name)), None)
