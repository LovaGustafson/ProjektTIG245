"""Temporary view filters. Never call the rule engine or alter source values."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from numbers import Number
import re

import pandas as pd

from src.mapping.column_mapper import COLUMN_ALIASES, COLUMN_MAPPING


FIELD_ORDER = (
    'verification_id', 'verification_line_id', 'verification_date', 'amount',
    'account', 'responsibility', 'counterparty', 'investment', 'project',
    'activity', 'cost_responsibility', 'vat_code', 'posting_group',
    'verification_type', 'Leverantör', 'header_text', 'line_text',
    'image_reference', 'signature', 'attestation',
)
FALSE_INDICATORS = {'0', 'false', 'nej', 'no', 'none', 'null', 'nan', 'n/a', 'saknas', 'ingen bild'}
TRUE_INDICATORS = {'1', 'true', 'ja', 'yes'}


def is_missing(value):
    return (not value.strip() if isinstance(value, str)
            else bool(pd.isna(value)) if pd.api.types.is_scalar(value) else False)


def numeric_value(value):
    """Parse finite numbers and decimal comma/point; do not guess ambiguous separators."""
    if is_missing(value) or isinstance(value, bool):
        return None
    text = str(value).strip().replace('\u2212', '-')
    # Only accept spaces as thousands separators when groups have three digits.
    if re.fullmatch(r'[+-]?\d{1,3}(?:[\s\u00a0]\d{3})+(?:[.,]\d+)?', text):
        text = ''.join(text.split())
    if not re.fullmatch(r'[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?', text):
        return None
    try:
        number = Decimal(text.replace(',', '.'))
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def date_value(value):
    """Native dates, ISO and explicit day/month/year formats; never Excel serial guessing."""
    if is_missing(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        for pattern in ('%d/%m/%Y', '%d.%m.%Y', '%d-%m-%Y'):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                pass
    return None


def has_information(value):
    """UI presence only: a reference/indicator, not proof an image/signature exists.

    TODO / AK: confirm the source's indicator vocabulary. The UI explicitly
    describes this provisional interpretation; detection rules do not use it.
    """
    if is_missing(value):
        return False
    if isinstance(value, str) and value.strip().casefold() in FALSE_INDICATORS:
        return False
    number = numeric_value(value)
    if number is not None:
        return number != 0
    if isinstance(value, Number):
        return isinstance(value, bool) and value
    return bool(value)


def category_value(value):
    if is_missing(value):
        return None
    if isinstance(value, Number) and not isinstance(value, bool):
        number = numeric_value(value)
        if number is not None and number == number.to_integral_value():
            return str(int(number))
    return str(value).strip()


@dataclass(frozen=True)
class FilterDefinition:
    position: int
    label: str
    kind: str
    choices: tuple[str, ...]


@dataclass(frozen=True)
class ViewFilter:
    categories: tuple[str, ...] = ()
    text: str = ''
    missing: str = 'all'
    presence: str = 'all'
    start: date | None = None
    end: date | None = None
    minimum: float | None = None
    maximum: float | None = None
    sign: str = 'all'


@dataclass
class FilteredView:
    data: pd.DataFrame
    positions: tuple[int, ...]
    active: tuple[str, ...] = ()
    notices: tuple[str, ...] = ()


def discover_filters(data):
    """Column positions distinguish duplicate headers; keep familiar source labels."""
    definitions = []
    source_names = {value: key for key, value in COLUMN_MAPPING.items()}
    order = {}
    for position, name in enumerate(data.columns):
        name = str(name).strip()
        internal = COLUMN_ALIASES.get(name, name)
        label = source_names.get(name, name)
        if list(data.columns).count(data.columns[position]) > 1:
            label += f' (kolumn {position + 1})'
        values = data.iloc[:, position].tolist()
        choices = tuple(sorted({category_value(v) for v in values} - {None}))
        boolean_like = bool(choices) and all(
            value.casefold() in TRUE_INDICATORS | FALSE_INDICATORS for value in choices)
        kind = ('date' if internal == 'verification_date' else
                'number' if internal == 'amount' else
                'presence' if internal == 'image_reference' or
                (internal in ('signature', 'attestation') and boolean_like) else
                'text' if internal in ('header_text', 'line_text') else 'category')
        definitions.append(FilterDefinition(position, label, kind, choices))
        order[position] = FIELD_ORDER.index(internal) if internal in FIELD_ORDER else len(FIELD_ORDER)
    return sorted(definitions, key=lambda definition: (order[definition.position], definition.position))


def apply_filters(data, filters: dict[int, ViewFilter]) -> FilteredView:
    """OR within category selections, AND across conditions/columns; return a copy.

    positions maps displayed rows back to the supplied view, independently of
    duplicate DataFrame indexes or invoice identities. Parsed values are only
    comparison values. Invalid dates/amounts are omitted only by an active
    date/amount condition, and remain in the source and exports.
    """
    keep = [True] * len(data)
    active, notices = [], []
    for definition in discover_filters(data):
        rule = filters.get(definition.position)
        if rule is None:
            continue
        values = data.iloc[:, definition.position].tolist()
        conditions, descriptions = [], []
        if rule.categories:
            conditions.append([category_value(v) in rule.categories for v in values])
            descriptions.append(', '.join(rule.categories))
        query = rule.text.strip().casefold()
        if query:
            conditions.append([not is_missing(v) and query in str(v).strip().casefold() for v in values])
            descriptions.append(f'innehåller ”{rule.text.strip()}”')
        if rule.missing != 'all':
            conditions.append([is_missing(v) == (rule.missing == 'missing') for v in values])
            descriptions.append('Saknar värde' if rule.missing == 'missing' else 'Har värde')
        if rule.presence != 'all':
            conditions.append([has_information(v) == (rule.presence == 'present') for v in values])
            if definition.label == 'Bild':
                descriptions.append('Bild finns' if rule.presence == 'present' else 'Ingen bild')
            else:
                descriptions.append('Finns' if rule.presence == 'present' else 'Saknas')
        if rule.start is not None or rule.end is not None:
            dates = [date_value(v) for v in values]
            conditions.append([v is not None and (rule.start is None or v >= rule.start)
                               and (rule.end is None or v <= rule.end) for v in dates])
            descriptions.append(f'{rule.start or "…"} – {rule.end or "…"}')
            if any(v is None for v in dates):
                notices.append(f'{definition.label}: {dates.count(None)} tomma eller ogiltiga datum '
                               'matchar inte datumintervallet.')
            if rule.start and rule.end and rule.start > rule.end:
                notices.append(f'{definition.label}: Från datum är senare än Till datum.')
        if rule.minimum is not None or rule.maximum is not None or rule.sign != 'all':
            numbers = [numeric_value(v) for v in values]
            lower = numeric_value(rule.minimum)
            upper = numeric_value(rule.maximum)
            conditions.append([
                v is not None and (lower is None or v >= lower) and (upper is None or v <= upper)
                and (rule.sign != 'positive' or v > 0) and (rule.sign != 'negative' or v < 0)
                and (rule.sign != 'zero' or v == 0) for v in numbers])
            if rule.minimum is not None or rule.maximum is not None:
                descriptions.append(f'{rule.minimum if lower is not None else "…"} – '
                                    f'{rule.maximum if upper is not None else "…"}')
            if rule.sign != 'all':
                descriptions.append({'positive': 'Endast positiva', 'negative': 'Endast negativa',
                                     'zero': 'Nollbelopp'}[rule.sign])
            if any(v is None for v in numbers):
                notices.append(f'{definition.label}: {numbers.count(None)} tomma eller icke-numeriska '
                               'värden matchar inte beloppsfiltret.')
            if lower is not None and upper is not None and lower > upper:
                notices.append(f'{definition.label}: Min belopp är större än Max belopp.')
        for condition in conditions:
            keep = [previous and hit for previous, hit in zip(keep, condition)]
        if descriptions:
            active.append(f'{definition.label}: ' + '; '.join(descriptions))
    positions = tuple(i for i, included in enumerate(keep) if included)
    return FilteredView(data.iloc[list(positions)].copy(deep=True), positions, tuple(active), tuple(notices))
