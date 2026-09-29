"""Synthetic integration, export and Streamlit tests; no real invoice data."""
from datetime import date
from io import BytesIO
from pathlib import Path
import json

import pandas as pd
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from src.pipeline import run_pipeline
from src.ui_support import analyze_upload

APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'
MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def workbook(data):
    buffer = BytesIO()
    data.to_excel(buffer, index=False)
    return buffer.getvalue()


def invoices():
    return pd.DataFrame({
        'Vernr': ['001', '001', '002', '003', '004', '005', None],
        'Vrad': [1, 2, 1, 1, 1, 1, None], 'Konto': ['4000'] * 7,
        'Vertyp': ['X', 'X', 'X', 'X', 'FBFM', 'X', 'X'],
        'Huvudtext': ['Telia Sverige A Slutk 1', 'Input interiör Prelb 2',
                     'Helt Främmande Företag AB Slutk 3', 'Ingen markör',
                     'Telia Sverige A Slutk 5', 'Telia Sverige A Prelb 6', None],
        'Motp': [100] * 7,
        'Verdatum': ['2026-09-01', '2026-08-31', '2026-09-01', 'fel',
                    '2026-09-01', '2026-08-01', None],
        'Utfall': [10, 20, 30, 'fel', 50, 60, 'fel'],
    })


def contracts():
    return pd.DataFrame({
        'Leverantör': ['Telia Sverige AB', 'Telia Sverige AB', 'Input interiör AB',
                      'Input interiör Göteborg AB'],
        'Organisationsnummer': ['012345-6789', '0123456789', '2', '3'],
        'Avtals-ID': ['001', '002', '003', '004'],
        'Avtalsnamn': ['=SUM(1,2)', 'Avtal två', 'Avtal tre', 'Avtal fyra'],
        'Startdatum': ['2025-01-01'] * 4, 'Slutdatum': ['2027-12-31'] * 4,
        'Referensnummer': ['R1', 'R2', 'R3', 'R4'], 'Nivå1': ['Kategori'] * 4,
    })


def test_complete_pipeline_preserves_both_original_files_and_filters_before_matching(tmp_path):
    source, registry = tmp_path / 'invoices.xlsx', tmp_path / 'registry.xlsx'
    source.write_bytes(workbook(invoices()))
    registry.write_bytes(workbook(contracts()))
    originals = [(p, p.read_bytes(), p.stat().st_mtime_ns) for p in (source, registry)]
    result = run_pipeline(source, supplier_register=registry, output_dir=tmp_path / 'out')
    assert len(result.filtering.cleaned_data) == 6
    analysis = result.supplier_analysis
    assert analysis.rows['source_row_position'].tolist() == [0, 1, 2, 3, 5, 6]
    assert analysis.rows['supplier_match_status'].tolist() == [
        'STRONG_MATCH', 'AMBIGUOUS_MATCH', 'NO_MATCH', 'SUPPLIER_NOT_IDENTIFIED',
        'STRONG_MATCH', 'SUPPLIER_NOT_IDENTIFIED']
    assert analysis.summary()['Rader med datumvarning'] == 2
    assert analysis.rows['contract_count'].tolist() == [2, 0, 0, 0, 2, 0]
    assert analysis.rows['matched_organization_number'].iloc[0] == '0123456789'
    assert all('FBFM' not in verification.rows['verification_type'].tolist()
               for verification in result.verifications)
    for path, content, mtime in originals:
        assert path.read_bytes() == content and path.stat().st_mtime_ns == mtime
    for name, report in result.report_paths.items():
        with pd.ExcelFile(report) as book:
            assert ('Leverantörsmatchning' in book.sheet_names) == (name != 'excluded_data')
    checks = [check for detection in result.detection_results for check in detection.checks]
    assert all(check.status == 'NOT_CHECKED' for check in checks)
    assert any('Avtalstrohet har inte kontrollerats' in check.reason for check in checks)


def test_export_has_clean_header_matching_candidates_all_contracts_and_literal_formulas():
    review = analyze_upload(workbook(invoices()), registry_content=workbook(contracts()))
    with pd.ExcelFile(BytesIO(review.downloads['samlad_kontrollfil.xlsx'])) as book:
        kept = pd.read_excel(book, sheet_name='Granskning', dtype=object)
        assert kept['Huvudtext'].iloc[0] == 'Telia Sverige A'
        assert review.result.original_data['Huvudtext'].iloc[0] == invoices()['Huvudtext'].iloc[0]
        assert kept['Motp'].tolist() == [100] * 6
        assert kept['supplier_match_status'].iloc[0] == 'STRONG_MATCH'
        assert kept['matched_organization_number'].iloc[0] == '0123456789'
        candidates = pd.read_excel(book, sheet_name='Leverantörskandidater')
        assert len(candidates[candidates.source_row_position == 1]) == 2
        possible = pd.read_excel(book, sheet_name='Möjliga avtal', dtype=object)
        assert possible[possible.source_row_position == 0]['contract_id'].tolist() == ['001', '002']
        assert 'Starka leverantörsträffar' in pd.read_excel(book, sheet_name='Sammanfattning')['Mått'].tolist()
    book = load_workbook(BytesIO(review.downloads['granskning.xlsx']))
    formula_cells = [cell for row in book['Möjliga avtal'] for cell in row if cell.value == '=SUM(1,2)']
    assert formula_cells and all(cell.data_type == 's' for cell in formula_cells)
    book.close()


def test_snapshot_override_changes_warning_but_never_identity_status():
    first = analyze_upload(workbook(invoices()), registry_content=workbook(contracts()))
    later = analyze_upload(workbook(invoices()), registry_content=workbook(contracts()),
                           registry_snapshot_date=date(2026, 9, 2))
    a, b = first.result.supplier_analysis.rows, later.result.supplier_analysis.rows
    assert a['registry_date_warning'].sum() == 2 and b['registry_date_warning'].sum() == 0
    assert a['supplier_match_status'].tolist() == b['supplier_match_status'].tolist()


def test_empty_filtered_result_with_loaded_registry_renders_and_exports():
    review = analyze_upload(workbook(invoices().iloc[[4]]), registry_content=workbook(contracts()))
    assert review.result.supplier_analysis.registry.available
    assert review.result.supplier_analysis.rows.empty
    app = AppTest.from_file(str(APP))
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    assert [b.label.split('**')[1] for b in app.button if b.key and b.key.startswith('supplier_')] == ['0'] * 6
    data = pd.read_excel(BytesIO(review.downloads['granskning.xlsx']))
    assert data.empty and 'supplier_match_status' in data.columns


def test_bad_register_is_explicitly_unavailable_in_ui_and_export():
    review = analyze_upload(workbook(invoices()), registry_content=workbook(pd.DataFrame({'Fel': ['x']})))
    assert not review.result.supplier_analysis.registry.available
    assert review.result.supplier_analysis.rows.empty
    app = AppTest.from_file(str(APP))
    app.session_state['review'] = review
    app.run()
    assert not app.exception
    assert any('kunde inte genomföras' in error.value for error in app.error)
    with pd.ExcelFile(BytesIO(review.downloads['samlad_kontrollfil.xlsx'])) as book:
        info = pd.read_excel(book, sheet_name='Registerinformation')
        assert not info['matching_available'].iloc[0]
        assert 'NO_MATCH' not in pd.read_excel(book, sheet_name='Granskning').to_string()


def test_ui_upload_status_summary_detail_and_refilter_keeps_registry():
    registry_content = workbook(contracts())
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.file_uploader[0].set_value(('invoices.xlsx', workbook(invoices()), MIME)).run()
    app.file_uploader[1].set_value(('registry.xlsx', registry_content, MIME)).run()
    app.button[0].click().run()
    assert not app.exception
    assert [b.label.split('**')[1] for b in app.button if b.key and b.key.startswith('supplier_')] == ['6', '2', '1', '1', '2', '2']
    table = app.tabs[0].dataframe[0]
    assert table.value['Leverantörsträff'].iloc[0] == '🟢 Stark leverantörsträff'
    assert table.value['Leverantörsträff'].iloc[1] == '🟡 Osäker träff – manuell granskning'
    states = app._tree.get_widget_states()
    state = states.widgets.add()
    state.id = table.proto.id
    state.string_value = json.dumps({'selection': {'rows': [0], 'columns': [], 'cells': []}})
    app._run(states)
    assert not app.exception
    assert any('Möjliga avtal' in expander.label for expander in app.expander)
    assert any('äldre än transaktionen' in warning.value for warning in app.warning)
    app.multiselect(key='excluded_types').unselect('FBFM').run()
    assert not app.exception
    review = app.session_state['review']
    assert len(review.result.supplier_analysis.rows) == 7
    assert review.result.supplier_analysis.summary()['Starka leverantörsträffar'] == 3
    assert review.registry_content == registry_content
    app.date_input[0].set_value(date(2026, 9, 2)).run()
    assert not app.metric
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['review'].result.supplier_analysis.summary()['Rader med datumvarning'] == 0
