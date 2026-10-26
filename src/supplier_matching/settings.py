"""Load and validate technical matching settings outside the match engine."""
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from src.filtering.filter_engine import DEFAULT_SETTINGS_PATH
from src.supplier_matching.normalization import LEGAL_FORMS, normalize_supplier


@dataclass(frozen=True)
class MatchSettings:
    fuzzy_strong_threshold: float = 0.94
    fuzzy_candidate_threshold: float = 0.82
    prefix_min_characters: int = 8
    prefix_min_tokens: int = 2
    prefix_min_coverage: float = 0.60
    related_first_token_min_characters: int = 6
    # Generic geographic words used only for candidate relevance (Phase 3D.1).
    geographic_descriptors: tuple[str, ...] = ('sverige',)

    def __post_init__(self):
        if not 0 < self.fuzzy_candidate_threshold <= self.fuzzy_strong_threshold <= 1:
            raise ValueError('Matchningströsklar måste uppfylla 0 < candidate <= strong <= 1.')
        if (self.prefix_min_characters < 1 or self.prefix_min_tokens < 1
                or self.related_first_token_min_characters < 1
                or not 0 < self.prefix_min_coverage <= 1):
            raise ValueError('Ogiltiga prefixinställningar.')
        descriptors = self.geographic_descriptors
        if isinstance(descriptors, str) or not all(isinstance(d, str) for d in descriptors):
            raise ValueError('geographic_descriptors måste vara en lista med ord.')
        normalized = tuple(dict.fromkeys(normalize_supplier(d) for d in descriptors))
        if any(not d or ' ' in d or d in LEGAL_FORMS for d in normalized):
            raise ValueError('geographic_descriptors måste vara enskilda ord och inte bolagsformer.')
        object.__setattr__(self, 'geographic_descriptors', normalized)


def load_matching_settings(settings_path=DEFAULT_SETTINGS_PATH):
    with Path(settings_path).open(encoding='utf-8') as stream:
        settings = yaml.safe_load(stream) or {}
    config = settings.get('supplier_matching') or {}
    return config


def snapshot_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError('Registerdatum måste vara ett giltigt ISO-datum (ÅÅÅÅ-MM-DD).') from exc
