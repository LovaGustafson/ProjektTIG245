from datetime import date

import pandas as pd

from src.ingestion.contract_reader import registry_from_frame
from src.supplier_matching.analysis import analyze_suppliers, enrich_rows


def test_row_identity_contracts_date_warning_and_counterparty_is_only_metadata():
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': ['Telia Sverige AB'] * 2, 'organization_number': ['123'] * 2,
        'contract_id': ['001', '002'], 'start_date': ['2025-01-01'] * 2,
        'end_date': ['2027-12-31'] * 2}), snapshot=date(2026, 8, 31))
    data = pd.DataFrame({'header_text': ['Telia Sverige A Slutk 1', 'Saknad Leverantör AB Prelb 2', None],
                         'verification_date': ['2026-09-01', '2026-09-01', 'fel'],
                         'counterparty': [100] * 3}, index=[1, 3, 4])
    before = data.copy(deep=True)
    result = analyze_suppliers(data, registry)
    assert result.rows['supplier_match_status'].tolist() == ['STRONG_MATCH', 'NO_MATCH', 'SUPPLIER_NOT_IDENTIFIED']
    assert result.rows['contract_count'].tolist() == [2, 0, 0]
    assert result.rows['registry_date_warning'].tolist() == [True, True, False]
    assert result.rows['registry_date_check'].iloc[-1] == 'UNKNOWN'
    assert result.contracts['contract_id'].tolist() == ['001', '002']
    assert result.rows['source_row_position'].tolist() == [1, 3, 4]
    assert result.summary()['Rader med datumvarning'] == 2
    pd.testing.assert_frame_equal(data, before)
    enriched = enrich_rows(data, result)
    pd.testing.assert_frame_equal(enriched[data.columns], data)
    changed_counterparty = analyze_suppliers(data.assign(counterparty=[1, 2, 3]), registry)
    pd.testing.assert_frame_equal(result.rows, changed_counterparty.rows)


def test_ambiguous_candidates_no_selected_entity_and_collision_keeps_source():
    registry = registry_from_frame(pd.DataFrame({
        'supplier_name': ['Input interiör AB', 'Input interiör Göteborg AB'],
        'organization_number': ['1', '2']}))
    data = pd.DataFrame({'header_text': ['Input interiör Slutk 1'],
                         'supplier_match_status': ['Originalvärde']})
    result = analyze_suppliers(data, registry)
    assert result.rows['matched_supplier_name'].isna().all()
    assert len(result.candidates) == len(result.contracts) == 2
    enriched = enrich_rows(data, result)
    assert enriched['supplier_match_status'].tolist() == ['Originalvärde']
    assert enriched['_supplier_match_status'].tolist() == ['AMBIGUOUS_MATCH']


def test_unavailable_register_is_not_a_no_match():
    registry = registry_from_frame(pd.DataFrame())
    result = analyze_suppliers(pd.DataFrame({'header_text': ['Telia Sverige AB Slutk 1']}), registry)
    assert result.rows.empty
