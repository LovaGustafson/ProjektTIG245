"""Apply configured exclusions to comparison copies, retaining all source rows."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pandas as pd
import yaml
from src.filtering.transaction_rows import non_transaction_reason

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[2] / 'config/settings.yaml'


@dataclass
class FilterResult:
    cleaned_data: pd.DataFrame
    excluded_data: pd.DataFrame
    todos: tuple[str, ...]
    reasons: tuple[str, ...]
    account_count: int
    verification_type_count: int
    rule_details: dict[str, dict[str, list[int]]]


def normalize_type(value):
    return '' if pd.isna(value) else str(value).strip()


def normalize_account(value):
    text = normalize_type(value)
    try:
        number = Decimal(text)
        if number.is_finite() and number == number.to_integral_value():
            return str(int(number))
    except InvalidOperation:
        pass
    return text


def load_exclusions(settings_path=DEFAULT_SETTINGS_PATH):
    with Path(settings_path).open(encoding='utf-8') as stream:
        settings = yaml.safe_load(stream)
    if not isinstance(settings, dict):
        raise ValueError('Settings must be a mapping')
    result = {}
    for key in ('excluded_accounts', 'excluded_verification_types'):
        values = settings.get(key)
        if values is not None and (not isinstance(values, list) or
                                  any(not isinstance(v, str) for v in values)):
            raise ValueError(f'{key} must be a list of strings or null')
        result[key] = values
    return result


def filter_column_errors(data):
    return tuple(f"Kolumnen '{label}' saknas eller förekommer flera gånger. "
                 'Filtreringen kan inte genomföras fullständigt.'
                 for field, label in [('account', 'Konto'), ('verification_type', 'Vertyp')]
                 if list(data.columns).count(field) != 1)


def filter_rows(data: pd.DataFrame, *, settings_path=DEFAULT_SETTINGS_PATH,
                excluded_verification_types=None) -> FilterResult:
    settings = load_exclusions(settings_path)
    if excluded_verification_types is not None:
        settings['excluded_verification_types'] = list(excluded_verification_types)
    reasons = [[] for _ in range(len(data))]
    counts = []
    details = {}
    todos = list(filter_column_errors(data))
    for field, key, label, normalize in [
        ('account', 'excluded_accounts', 'konto', normalize_account),
        ('verification_type', 'excluded_verification_types', 'verifikationstyp', normalize_type),
    ]:
        values = settings[key]
        configured = sorted({normalize(v) for v in values or []} - {''})
        matches = {value: [] for value in configured}
        count = 0
        if values is None:
            todos.append(f'TODO / awaiting AK: {key}')
        elif list(data.columns).count(field) == 1:
            excluded = {normalize(v) for v in values} - {''}
            for position, value in enumerate(data[field]):
                normalized = normalize(value)
                if normalized in excluded:
                    matches[normalized].append(position)
                    reasons[position].append(f'{label} {normalized}')
                    count += 1
        counts.append(count)
        details[field] = matches
    for position, (_, row) in enumerate(data.iterrows()):
        structural_reason = non_transaction_reason(row)
        if structural_reason:
            reasons[position].append(structural_reason)
    mask = [bool(reason) for reason in reasons]
    return FilterResult(data.iloc[[i for i, hit in enumerate(mask) if not hit]].copy(deep=True),
                        data.iloc[[i for i, hit in enumerate(mask) if hit]].copy(deep=True),
                        tuple(todos), tuple('Exkluderad – ' + '; '.join(r) if r else '' for r in reasons),
                        *counts, details)
