"""Extract supplier candidates only from explicit booking markers."""
import re

MARKER = re.compile(r'\b(?:Prelb|Slutk)\b', re.IGNORECASE)


def extract_supplier(header_text: object) -> str | None:
    if not isinstance(header_text, str):
        return None
    marker = MARKER.search(header_text)
    return (header_text[:marker.start()].strip() or None) if marker else None
