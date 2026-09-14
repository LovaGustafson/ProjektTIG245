"""Apply configured row exclusions without changing source values."""
from dataclasses import dataclass
from pathlib import Path
import pandas as pd
import yaml

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[2] / 'config/settings.yaml'


@dataclass
class FilterResult:
    cleaned_data: pd.DataFrame
    excluded_data: pd.DataFrame
    todos: tuple[str, ...]


def filter_rows(data: pd.DataFrame, *, settings_path=DEFAULT_SETTINGS_PATH) -> FilterResult:
    """Exact-value exclusions; null configuration remains explicitly unresolved.

    Missing/ambiguous columns cannot support an exclusion and are retained.
    Numeric/blank/invalid values are not normalized or silently discarded.
    """
    with Path(settings_path).open(encoding='utf-8') as stream:
        settings = yaml.safe_load(stream)
    if not isinstance(settings, dict):
        raise ValueError('Settings must be a mapping')
    excluded = pd.Series(False, index=data.index)
    todos = []
    for field, key in [('account', 'excluded_accounts'),
                       ('verification_type', 'excluded_verification_types')]:
        values = settings.get(key)
        if values is None:
            todos.append(f'TODO / awaiting AK: {key}')
            continue
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError(f'{key} must be a list of strings or null')
        if list(data.columns).count(field) != 1:
            todos.append(f'TODO: exclusion unavailable for missing/ambiguous {field}')
            continue
        excluded |= data[field].isin(values)
    return FilterResult(data.loc[~excluded].copy(deep=True),
                        data.loc[excluded].copy(deep=True), tuple(todos))
