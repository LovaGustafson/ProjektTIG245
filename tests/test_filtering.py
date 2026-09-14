import pandas as pd
from src.filtering.filter_engine import filter_rows


def test_confirmed_exclusions_and_unresolved_types_preserve_input():
    source = pd.DataFrame({'account': ['7698', '7699', '4000', None, 7698],
                           'verification_type': ['X'] * 5})
    before = source.copy(deep=True)
    result = filter_rows(source)
    assert result.cleaned_data.index.tolist() == [2, 3, 4]
    assert result.excluded_data.index.tolist() == [0, 1]
    assert any('awaiting AK' in todo for todo in result.todos)
    pd.testing.assert_frame_equal(source, before)


def test_configurable_types_and_empty_input(tmp_path):
    path = tmp_path / 'settings.yaml'
    path.write_text('excluded_accounts: []\nexcluded_verification_types: [X]\n')
    source = pd.DataFrame({'account': ['4000'], 'verification_type': ['X']})
    assert filter_rows(source, settings_path=path).cleaned_data.empty
    assert filter_rows(source.iloc[:0], settings_path=path).cleaned_data.empty
