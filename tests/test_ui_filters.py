"""View filters operate on synthetic copies and never on engine classifications."""
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from src.ui_filters import (ViewFilter, apply_filters, discover_filters,
                            has_information, date_value, numeric_value)


@pytest.fixture
def data():
    return pd.DataFrame({
        'Vernr': ['001', '002', '003', '004', '005', '006'],
        'Konto': [5410, '7698', '7699', '5410', None, '7698'],
        'Vertyp': ['KR01', 'KR01', 'FHER', 'FHER', '', 'FHER'],
        'Bild': ['bilaga.pdf', '', None, False, 1, 0],
        'VerDat': [datetime(2026, 8, 1), '2026-08-31 12:30:00', '08/09/2026',
                   'fel', None, '2026-09-09'],
        'Utfall': [10000, '100 000,50', '-25,5', 0, 'text', None],
        'Radtext': ['  Medicin A ', 'annan text', 'MEDICIN', None, '', 'a.b'],
        'Huvudtext': ['Apotek', 'apoteket', 'Övrigt', '', None, 'APOTEK'],
        'Mm': [None, '', ' ', 0, '01', pd.NA],
        'Sign': ['aa', 'bb', None, 'aa', 'cc', 'bb'],
        'Att': [True, False, None, 'ja', 'nej', 1],
        'Extra originalfält': ['x'] * 6,
    }, dtype=object)


def filtered(data, **rules):
    definitions = {definition.label: definition.position for definition in discover_filters(data)}
    return apply_filters(data, {definitions[label]: rule for label, rule in rules.items()})


@pytest.mark.parametrize('rules,positions', [
    ({'Konto': ViewFilter(categories=('5410',))}, (0, 3)),
    ({'Konto': ViewFilter(categories=('5410', '7698'))}, (0, 1, 3, 5)),
    ({'Konto': ViewFilter(categories=('5410',)), 'Vertyp': ViewFilter(categories=('FHER',))}, (3,)),
    ({'Bild': ViewFilter(presence='present')}, (0, 4)),
    ({'Bild': ViewFilter(presence='missing')}, (1, 2, 3, 5)),
    ({'VerDat': ViewFilter(start=date(2026, 8, 1), end=date(2026, 9, 8))}, (0, 1, 2)),
    ({'Utfall': ViewFilter(minimum=10000, maximum=100001)}, (0, 1)),
    ({'Utfall': ViewFilter(sign='positive')}, (0, 1)),
    ({'Utfall': ViewFilter(sign='negative')}, (2,)),
    ({'Utfall': ViewFilter(sign='zero')}, (3,)),
    ({'Radtext': ViewFilter(text=' MEDiciN ')}, (0, 2)),
    ({'Radtext': ViewFilter(text='a.b')}, (5,)),
    ({'Huvudtext': ViewFilter(text=' apotek ')}, (0, 1, 5)),
    ({'Mm': ViewFilter(missing='missing')}, (0, 1, 2, 5)),
    ({'Mm': ViewFilter(missing='present')}, (3, 4)),
    ({'Konto': ViewFilter(categories=('1111',))}, ()),
])
def test_filter_conditions_and_original_copy(data, rules, positions):
    before = data.copy(deep=True)
    result = filtered(data, **rules)
    assert result.positions == positions
    pd.testing.assert_frame_equal(result.data, data.iloc[list(positions)])
    assert len(result.active) == len(rules)
    pd.testing.assert_frame_equal(data, before)
    if len(result.data):
        result.data.iloc[0, 0] = 'display edit'
        pd.testing.assert_frame_equal(data, before)


def test_no_filters_retains_invalid_values_and_empty_frame(data):
    result = apply_filters(data, {})
    pd.testing.assert_frame_equal(result.data, data)
    assert not result.active
    assert not result.notices
    empty = apply_filters(data.iloc[:0], {1: ViewFilter(categories=('5410',))})
    assert empty.data.empty
    assert empty.data.columns.tolist() == data.columns.tolist()


def test_discovery_available_columns_order_and_boolean_categories(data):
    definitions = discover_filters(data)
    assert [d.label for d in definitions] == [
        'Vernr', 'VerDat', 'Utfall', 'Konto', 'Mm', 'Vertyp', 'Huvudtext',
        'Radtext', 'Bild', 'Sign', 'Att', 'Extra originalfält']
    by_name = {d.label: d for d in definitions}
    assert by_name['Bild'].kind == 'presence'
    assert by_name['Sign'].kind == 'category'
    assert by_name['Att'].kind == 'presence'
    assert by_name['Konto'].choices == ('5410', '7698', '7699')
    assert by_name['Mm'].choices == ('0', '01')


@pytest.mark.parametrize('value', [None, pd.NA, float('nan'), '', ' ', False, 0, '0.0',
                                   'NEJ', 'false', 'None', float('inf'), Decimal('NaN')])
def test_presence_missing_indicators(value):
    assert not has_information(value)


@pytest.mark.parametrize('value', ['invoice.pdf', '  referens  ', True, 1, 42, 'ja'])
def test_presence_information(value):
    assert has_information(value)


def test_invalid_and_reversed_intervals_leave_source_intact(data):
    result = filtered(data, VerDat=ViewFilter(start=date(2026, 10, 1), end=date(2026, 8, 1)),
                      Utfall=ViewFilter(minimum=10, maximum=-10))
    assert result.data.empty
    assert len(result.notices) == 4
    assert data.loc[3, 'VerDat'] == 'fel'
    assert data.loc[4, 'Utfall'] == 'text'


def test_duplicate_indexes_headers_and_internal_labels():
    data = pd.DataFrame([['x', 'a', 1], ['y', 'b', 2]], columns=['Radtext', 'Radtext', 'account'], index=[7, 7])
    definitions = discover_filters(data)
    assert [d.label for d in definitions] == ['Konto', 'Radtext (kolumn 1)', 'Radtext (kolumn 2)']
    result = apply_filters(data, {1: ViewFilter(text='b')})
    assert result.positions == (1,)
    assert result.data.iloc[0].tolist() == ['y', 'b', 2]


def test_parsing_does_not_guess_excel_serials_or_ambiguous_numbers():
    assert date_value(45000) is None
    assert date_value('2026-09-08T23:00:00+02:00') == date(2026, 9, 8)
    assert date_value('31.08.2026') == date(2026, 8, 31)
    assert date_value('31/02/2026') is None
    assert numeric_value('10\u00a0000,50') == Decimal('10000.50')
    assert numeric_value('10 00') is None
    assert numeric_value('1,000.50') is None
    assert numeric_value(True) is None
    assert numeric_value('NaN') is None
