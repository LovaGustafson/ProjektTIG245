import pandas as pd
from src.mapping.column_mapper import map_columns


def test_mapping_preserves_values_unknown_columns_and_input():
    source = pd.DataFrame([['001', 'raw', 'extra']], columns=['Vernr', 'Mm', 'Other'])
    before = source.copy(deep=True)
    result = map_columns(source)
    assert result.columns.tolist() == ['verification_id', 'vat_code', 'Other']
    assert result.iloc[0].tolist() == ['001', 'raw', 'extra']
    result.iloc[0, 0] = 'edited'
    pd.testing.assert_frame_equal(source, before)


def test_empty_and_duplicate_headers():
    result = map_columns(pd.DataFrame(columns=['Vernr', 'verification_id']))
    assert result.empty
    assert result.columns.tolist() == ['verification_id', 'verification_id']
