"""XLSX presentation omits internal fields without changing synthetic analyses."""
from copy import deepcopy
from datetime import date
from io import BytesIO

import pandas as pd
import pytest

from src.output.report_generator import XLSX_EXCLUDED_COLUMNS, _workbook
from src.pipeline import export_pipeline_result
from src.ui_support import analyze_upload, select_sample_method
from tests.synthetic_org import org
from tests.test_feature_package import invoices, registry, settings, workbook
from tests.test_ui_ux import assert_same_analysis


DOWNLOADS = {
    'cleaned_data.xlsx', 'flagged_invoices.xlsx', 'manual_sample.xlsx',
    'uncertain_suppliers.xlsx', 'excluded_data.xlsx', 'granskning.xlsx',
    'bortfiltrerade.xlsx', 'samlad_kontrollfil.xlsx',
}
USEFUL_MATCH_COLUMNS = {
    'supplier_match_status', 'supplier_match_score', 'supplier_match_reason',
    'matched_supplier_name', 'matched_organization_number', 'source_row_position',
}


def read_sheets(content):
    sheets = pd.read_excel(BytesIO(content), sheet_name=None, dtype=object)
    for name, data in sheets.items():
        assert not XLSX_EXCLUDED_COLUMNS.intersection(data.columns), name
    return sheets


def synthetic_sources(mode):
    data = invoices(43)
    data.loc[0, 'Konto'] = '7698'
    data.loc[1, 'Huvudtext'] = 'Okänd Testverksamhet AB Slutk1'
    contracts = registry()
    if mode == 'ambiguous':
        data.loc[2, 'Huvudtext'] = 'Input interiör Slutk2'
        alternatives = pd.concat([
            registry('Input interiör AB'), registry('Input interiör Göteborg AB'),
        ], ignore_index=True)
        alternatives['Organisationsnummer'] = [org(2), org(3)]
        contracts = pd.concat([contracts, alternatives], ignore_index=True)
    return data, None if mode == 'unavailable' else workbook(contracts)


def expected_positions(result):
    kept = result.filtering.cleaned_data.index.tolist()
    excluded = result.filtering.excluded_data.index.tolist()
    sample = [p for verification in result.manual_sample for p in verification.rows.index]
    flagged = [p for verification, detection in zip(result.verifications, result.detection_results)
               if detection.flag_reasons for p in verification.rows.index]
    strong = result.supplier_analysis.rows.loc[
        result.supplier_analysis.rows.supplier_match_status.eq('STRONG_MATCH'),
        'source_row_position',
    ]
    uncertain = [p for p in kept if p not in set(strong)]
    return {
        'cleaned_data.xlsx': kept, 'flagged_invoices.xlsx': flagged,
        'manual_sample.xlsx': sample, 'uncertain_suppliers.xlsx': uncertain,
        'excluded_data.xlsx': excluded, 'granskning.xlsx': kept,
        'bortfiltrerade.xlsx': excluded, 'samlad_kontrollfil.xlsx': kept + excluded,
    }


@pytest.mark.parametrize('deferred', [False, True])
@pytest.mark.parametrize('mode', ['matching', 'ambiguous', 'unavailable'])
def test_all_ui_xlsx_downloads_omit_only_internal_columns(tmp_path, deferred, mode):
    data, contracts = synthetic_sources(mode)
    content = workbook(data)
    review = analyze_upload(content, registry_content=contracts,
        registry_mode='disabled' if mode == 'unavailable' else 'uploaded',
        registry_snapshot_date=date(2026, 6, 1), source_name='synthetic.xlsx',
        settings_path=settings(tmp_path), defer_downloads=deferred)
    before = deepcopy(review.result)
    assert set(review.downloads) == DOWNLOADS
    positions = expected_positions(before)

    for filename in sorted(DOWNLOADS):
        sheets = read_sheets(review.downloads[filename])
        assert sheets['Källspårning'].source_row_position.tolist() == positions[filename]
        assert len(sheets['Källspårning']) == len(positions[filename])
        assert sheets['Urvalsbeslut'].decision.tolist() == before.sampling_result.decisions.decision.tolist()
        assert sheets['Urvalsklassificering'].classification.tolist() == before.sampling_result.classification_rows.classification.tolist()
        if mode != 'unavailable' and 'Leverantörsmatchning' in sheets:
            matches = sheets['Leverantörsmatchning']
            assert USEFUL_MATCH_COLUMNS.issubset(matches.columns)
            assert {'method', 'score', 'reason'}.issubset(sheets['Leverantörskandidater'].columns)
            assert {'contract_period_status', 'contract_period_reason'}.issubset(sheets['Möjliga avtal'].columns)
        if filename == 'granskning.xlsx':
            assert sheets['Granskning'].Vernr.tolist() == data.Vernr.iloc[1:].tolist()
            assert sheets['Granskning'].Utfall.tolist() == [100] * 42
            if mode != 'unavailable':
                assert USEFUL_MATCH_COLUMNS.issubset(sheets['Granskning'].columns)
                actual = sheets['Leverantörsmatchning'].set_index('source_row_position')
                original = before.supplier_analysis.rows.set_index('source_row_position')
                for field in ('supplier_match_status', 'supplier_match_score', 'supplier_match_reason'):
                    assert actual.loc[3, field] == original.loc[3, field]
                assert sheets['Möjliga avtal'].contract_period_status.tolist() == before.supplier_analysis.contracts.contract_period_status.tolist()

    assert XLSX_EXCLUDED_COLUMNS.issubset(review.result.supplier_analysis.rows.columns)
    if mode != 'unavailable':
        assert review.result.supplier_analysis.rows.registry_date_warning.all()
        assert set(review.result.supplier_analysis.rows.registry_date_check) == {'AFTER_SNAPSHOT'}
        assert review.result.supplier_analysis.rows.set_index('source_row_position').loc[3, 'supplier_match_status'] == 'STRONG_MATCH'
        if mode == 'ambiguous':
            assert review.result.supplier_analysis.rows.set_index('source_row_position').loc[2, 'supplier_match_status'] == 'AMBIGUOUS_MATCH'
    assert_same_analysis(before, review.result)
    pd.testing.assert_frame_equal(before.sampling_result.classification_rows,
                                  review.result.sampling_result.classification_rows)
    assert review.source_content == content


@pytest.mark.parametrize('method', ['systematic', 'randomized'])
def test_cli_xlsx_exports_preserve_active_sample_and_internal_evidence(tmp_path, method):
    data, contracts = synthetic_sources('ambiguous')
    review = analyze_upload(workbook(data), registry_content=contracts,
        registry_snapshot_date=date(2026, 6, 1), settings_path=settings(tmp_path),
        defer_downloads=True)
    review = select_sample_method(review, method)
    before = deepcopy(review.result)
    positions = expected_positions(before)
    paths = export_pipeline_result(review.result, output_dir=tmp_path / 'reports')
    assert set(paths) == {'cleaned_data', 'flagged_invoices', 'manual_sample',
                          'uncertain_suppliers', 'excluded_data'}
    for path in paths.values():
        sheets = read_sheets(path.read_bytes())
        assert sheets['Källspårning'].source_row_position.tolist() == positions[path.name]
        assert sheets['Urvalsbeslut'].decision.tolist() == before.sampling_result.decisions.decision.tolist()
    assert_same_analysis(before, review.result)
    assert XLSX_EXCLUDED_COLUMNS.issubset(review.result.supplier_analysis.rows.columns)


@pytest.mark.parametrize('empty', [False, True])
def test_shared_serializer_keeps_other_columns_values_and_order(empty):
    source = pd.DataFrame({
        'label': ['second', 'first'], 'candidate_count': [2, 1], 'contract_count': [3, 4],
        'registry_snapshot_date': [date(2026, 6, 1)] * 2,
        'registry_date_warning': [True, False], 'registry_date_check': ['AFTER_SNAPSHOT', 'UNKNOWN'],
        'registry_date_message': ['warning', 'unknown'], 'supplier_match_method': ['exact', 'fuzzy'],
        'candidate_count_note': ['keep second', 'keep first'],
        '_candidate_count': ['original second', 'original first'],
        'supplier_match_status': ['STRONG_MATCH', 'AMBIGUOUS_MATCH'],
        'supplier_match_score': [100, 92], 'supplier_match_reason': ['exact name', 'manual review'],
        'source_row_position': [11, 7],
    })
    # Duplicate headers must not allow another occurrence of a hidden column through.
    source = pd.concat([source, source[['candidate_count']]], axis=1)
    if empty:
        source = source.iloc[:0]
    before = source.copy(deep=True)
    retained = ['label', 'candidate_count_note', '_candidate_count', 'supplier_match_status',
                'supplier_match_score', 'supplier_match_reason', 'source_row_position']
    sheets = read_sheets(_workbook({
        'Granskning': source, 'Registerinformation': source, 'Urvalspositioner': source,
    }))
    for data in sheets.values():
        assert data.columns.tolist() == retained
        pd.testing.assert_frame_equal(data, source[retained], check_dtype=False)
    pd.testing.assert_frame_equal(source, before)


def test_source_header_collisions_cannot_expose_generated_hidden_aliases(tmp_path):
    data, contracts = synthetic_sources('matching')
    for field in XLSX_EXCLUDED_COLUMNS:
        data[field] = 'original ' + field
    data['_candidate_count'] = 'genuine prefixed source value'
    content = workbook(data)
    review = analyze_upload(content, registry_content=contracts,
        settings_path=settings(tmp_path), defer_downloads=True)
    before = deepcopy(review.result)
    generated_aliases = {'_' + field for field in XLSX_EXCLUDED_COLUMNS if field != 'candidate_count'}
    for filename in sorted(DOWNLOADS):
        sheets = read_sheets(review.downloads[filename])
        for sheet in sheets.values():
            assert not generated_aliases.intersection(sheet.columns)
            assert '__candidate_count' not in sheet.columns
        if filename in ('granskning.xlsx', 'cleaned_data.xlsx', 'manual_sample.xlsx'):
            rows = sheets['Granskning' if filename == 'granskning.xlsx' else 'rows']
            assert rows['_candidate_count'].tolist() == ['genuine prefixed source value'] * len(rows)
    for field in XLSX_EXCLUDED_COLUMNS:
        assert review.result.original_data[field].tolist() == ['original ' + field] * len(data)
    assert_same_analysis(before, review.result)
    assert review.source_content == content
