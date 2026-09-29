"""Extract supplier candidates only from explicit booking markers."""
import re

MARKER = re.compile(r'\b(?:Prelb\b|Slutk(?=\b|\d+\b))', re.IGNORECASE)
FINAL_BOOKING = re.compile(r'\bSlutk\s*\d+\b', re.IGNORECASE)


def normalize_header_text(header_text: object) -> str | None:
    """Remove numbered Slutk markers on a comparison copy; retain other text."""
    if not isinstance(header_text, str):
        return None
    return ' '.join(FINAL_BOOKING.sub(' ', header_text).split())


def extract_supplier(header_text: object) -> str | None:
    if not isinstance(header_text, str):
        return None
    marker = MARKER.search(header_text)
    return (header_text[:marker.start()].strip() or None) if marker else None
