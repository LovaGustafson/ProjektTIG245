"""Deterministic supplier-name structure on normalized comparison copies.

Separates the distinctive name from a trailing legal designation and from
configured generic geographic descriptors. Supports candidate relevance and
conservative structured name evidence; it never establishes legal identity.
Original names and normalize_supplier output are never altered.
"""
from dataclasses import dataclass
from difflib import SequenceMatcher
import unicodedata

from src.supplier_matching.normalization import LEGAL_FORMS, split_legal_form

DESCRIPTOR_TRUNCATION_MIN_CHARACTERS = 4
DESCRIPTOR_TYPO_MIN_CHARACTERS = 6


def one_character_edit(left, right):
    """One insertion, deletion or substitution; transpositions are checked separately."""
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right):
        left, right = right, left
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return (left[index + 1:] == right[index + 1:] if len(left) == len(right)
                    else left[index:] == right[index + 1:])
    return len(right) == len(left) + 1


def adjacent_swap(left, right):
    """Exactly one swap of two neighbouring characters (e.g. sverige/svergie)."""
    if len(left) != len(right):
        return False
    differences = [i for i, (x, y) in enumerate(zip(left, right)) if x != y]
    if len(differences) != 2:
        return False
    i, j = differences
    return j == i + 1 and left[i] == right[j] and left[j] == right[i]


def _descriptor_form(token, descriptors, *, final):
    """Exact descriptor, a one-typo variant, or a truncation of the final token."""
    for descriptor in descriptors:
        if token == descriptor:
            return True
        if (min(len(token), len(descriptor)) >= DESCRIPTOR_TYPO_MIN_CHARACTERS
                and (one_character_edit(token, descriptor) or adjacent_swap(token, descriptor))):
            return True
        # A cut-off final word ("Sveri") may stand for a descriptor; inner words cannot.
        if (final and len(token) >= DESCRIPTOR_TRUNCATION_MIN_CHARACTERS
                and len(token) < len(descriptor) and descriptor.startswith(token)):
            return True
    return False


@dataclass(frozen=True)
class NameStructure:
    normalized: str
    legal_form: str | None
    core_tokens: tuple[str, ...]
    distinctive_tokens: tuple[str, ...]
    descriptor_tokens: tuple[str, ...]

    @property
    def distinctive(self) -> str:
        return ' '.join(self.distinctive_tokens)


def analyze_name_structure(normalized: str, descriptors=()) -> NameStructure:
    """Split a normalized name into legal form, descriptors and distinctive tokens.

    Only the first token is always distinctive, so a leading geographic word
    ("Sverige Trafik AB") is kept; later tokens matching a configured descriptor
    (or its one-typo/truncated form) are descriptors. Legal forms are separated by
    the existing split_legal_form, so AB, HB and KB stay distinct.
    """
    core, legal_form = split_legal_form(normalized)
    tokens = tuple(core.split())
    distinctive, generic = [], []
    for index, token in enumerate(tokens):
        if index and _descriptor_form(token, descriptors, final=index == len(tokens) - 1):
            generic.append(token)
        else:
            distinctive.append(token)
    return NameStructure(normalized, legal_form, tokens, tuple(distinctive), tuple(generic))


def structured_names_match(left: NameStructure, right: NameStructure, descriptors=()) -> bool:
    """Exact distinctive words, allowing only approved descriptors and legal omission.

    Relevance recognizes descriptor typos/truncations too, but those deliberately
    cannot supply new strong evidence here. Existing fuzzy/prefix rules handle
    their established cases independently. Explicit legal forms must agree.
    """
    return (bool(left.distinctive_tokens)
            and left.distinctive not in LEGAL_FORMS
            and left.distinctive_tokens == right.distinctive_tokens
            and all(token in descriptors for token in left.descriptor_tokens + right.descriptor_tokens)
            and not (left.legal_form and right.legal_form and left.legal_form != right.legal_form))


def _without_diacritics(text):
    """Relevance-only comparison copy: å/ä/ö and similar marks folded (Åkeriet/Akeriet)."""
    return ''.join(char for char in unicodedata.normalize('NFKD', text) if not unicodedata.combining(char))


def distinctive_names_related(left: NameStructure, right: NameStructure, threshold: float) -> bool:
    """Whether the distinctive names are plausibly the same supplier or a competing one.

    Symmetric by construction. Deliberately generous: it only decides whether a weak
    candidate is kept for review and never makes a candidate strong or selected.
    """
    for a, b in ((left.distinctive, right.distinctive),
                 (_without_diacritics(left.distinctive), _without_diacritics(right.distinctive))):
        if (a == b or one_character_edit(a, b) or adjacent_swap(a, b)
                or _symmetric_ratio(a, b) >= threshold
                or _shares_distinctive_words(a.split(), b.split())
                or _abbreviation_or_compound(a, b)):
            return True
    return False


def _symmetric_ratio(left, right):
    """SequenceMatcher is order-dependent; relevance uses the higher of both directions."""
    return max(SequenceMatcher(None, left, right, autojunk=False).ratio(),
               SequenceMatcher(None, right, left, autojunk=False).ratio())


def _abbreviation_or_compound(left, right):
    """Initials, abbreviations, truncations and compounds of the same distinctive name.

    "a b c"/"abc" (initials), "nordv"/"nordverk" (truncation), "alfa b"/"alfa bygg"
    (abbreviation), "alfa bygg"/"alfa byggservice" (compound): the space-free forms are
    equal or one is a prefix of the other, or the words align one by one with each
    word equal to, or a prefix of, its counterpart. Never proves identity.
    """
    compact_left, compact_right = left.replace(' ', ''), right.replace(' ', '')
    if compact_left and compact_right and (compact_left.startswith(compact_right)
                                           or compact_right.startswith(compact_left)):
        return True
    left_words, right_words = left.split(), right.split()
    return (len(left_words) == len(right_words) > 0
            and all(a.startswith(b) or b.startswith(a) for a, b in zip(left_words, right_words)))


def _shares_distinctive_words(left, right):
    """The shorter distinctive name occurs word for word, from the first word, in the other.

    Keeps possible siblings or the same company with an unlisted descriptor
    ("Skf Sverige" / "Skf Sweden") as candidates for review; never proves identity.
    """
    shorter, longer = sorted((left, right), key=len)
    if not shorter or shorter[0] != longer[0]:
        return False
    position = 0
    for token in shorter:
        try:
            position = longer.index(token, position) + 1
        except ValueError:
            return False
    return True
