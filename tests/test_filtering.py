import pandas as pd
from src.filtering.filter_engine import filter_rows


def test_confirmed_exclusions_and_unresolved_types_preserve_input():
    source = pd.DataFrame({'account': ['7698', '7699', '4000', None, 7698],
                           'verification_type': ['X'] * 5})
    before = source.copy(deep=True)
    result = filter_rows(source)
    assert result.cleaned_data.index.tolist() == [2, 3]
    assert result.excluded_data.index.tolist() == [0, 1, 4]
    assert not result.todos
    pd.testing.assert_frame_equal(source, before)


def test_configurable_types_and_empty_input(tmp_path):
    path = tmp_path / 'settings.yaml'
    path.write_text('excluded_accounts: []\nexcluded_verification_types: [X]\n')
    source = pd.DataFrame({'account': ['4000'], 'verification_type': ['X']})
    assert filter_rows(source, settings_path=path).cleaned_data.empty
    assert filter_rows(source.iloc[:0], settings_path=path).cleaned_data.empty


def test_all_standard_types_numeric_accounts_overlap_and_duplicate_indexes():
    from src.filtering.filter_engine import load_exclusions
    types = load_exclusions()['excluded_verification_types']
    assert len(types) == len(set(types)) == 42
    assert types.count('FMATB') == 1
    source = pd.DataFrame({'verification_type': types + ['X'] * 5 + [None],
                           'account': ['4000'] * 42 + [7698, 7699.0, ' 7698.0 ', '7699 ', None, '4000']},
                          index=[0] * 48)
    before = source.copy(deep=True)
    result = filter_rows(source)
    assert len(result.excluded_data) == 46
    assert len(result.cleaned_data) == 2
    assert result.account_count == 4
    assert result.verification_type_count == 42
    assert all(result.reasons[:46])
    pd.testing.assert_frame_equal(source, before)
    overlap = filter_rows(pd.DataFrame({'account': [7698], 'verification_type': [' KR01 ']}))
    assert overlap.reasons == ('Exkluderad – konto 7698; verifikationstyp KR01',)
    assert overlap.account_count == overlap.verification_type_count == 1


def test_reinclude_all_types_and_missing_columns():
    from src.filtering.filter_engine import filter_column_errors
    source = pd.DataFrame({'account': ['4000', '7699'], 'verification_type': ['KR01'] * 2})
    result = filter_rows(source, excluded_verification_types=[])
    assert result.cleaned_data.index.tolist() == [0]
    assert result.excluded_data.index.tolist() == [1]
    for field in source.columns:
        incomplete = source.drop(columns=field)
        assert filter_column_errors(incomplete)
        result = filter_rows(incomplete)
        assert len(result.cleaned_data) + len(result.excluded_data) == len(source)
