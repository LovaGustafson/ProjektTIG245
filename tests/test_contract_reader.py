import pandas as pd

from src.ingestion.contract_reader import registry_from_frame, read_contract_registry
from src.supplier_matching.settings import load_matching_settings


def test_groups_organization_numbers_retains_all_contracts_and_source():
    data = pd.DataFrame({'supplier_name': ['Telia Sverige AB'] * 3,
                         'organization_number': ['012345-6789', '0123456789', '1123456789'],
                         'contract_id': ['001', '002', '003']})
    before = data.copy(deep=True)
    registry = registry_from_frame(data)
    assert len(registry.suppliers) == 2
    assert len(registry.suppliers[0].contracts) == 2
    assert registry.suppliers[0].contracts[0]['organization_number'] == '012345-6789'
    pd.testing.assert_frame_equal(data, before)


def test_missing_names_and_ids_do_not_crash_or_merge_unknown_entities():
    data = pd.DataFrame({'supplier_name': [None, 'Bolaget AB', 'Bolaget AB'],
                         'organization_number': ['1', None, None]})
    registry = registry_from_frame(data)
    assert registry.available and len(registry.suppliers) == 2
    assert sum('Registerrad' in issue for issue in registry.issues) == 3
    assert not registry_from_frame(data.drop(columns='supplier_name')).available
    assert not registry_from_frame(pd.DataFrame([['X', 'Y', '1']], columns=[
        'supplier_name', 'supplier_name', 'organization_number'])).available


def test_excel_metadata_explicit_aliases_and_csv_are_read_only(tmp_path):
    from openpyxl import Workbook
    path = tmp_path / 'contracts.xlsx'
    book = Workbook()
    sheet = book.active
    sheet.append(['Koncerninköp, registerutdrag'])
    sheet.append(['Leverantör', 'Organisationsnummer', 'Avtals-ID', 'Nivå1'])
    sheet.append(['Företaget AB', '0123456789', '001', 'Kategori'])
    book.save(path)
    book.close()
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    registry = read_contract_registry(path, config=load_matching_settings())
    assert registry.available
    assert registry.suppliers[0].organization_number == '0123456789'
    assert registry.suppliers[0].contracts[0]['level_1'] == 'Kategori'
    assert path.read_bytes() == before and path.stat().st_mtime_ns == mtime
    csv = tmp_path / 'contracts.csv'
    csv.write_text('Leverantör;Organisationsnummer;Avtals-ID\nFöretaget AB;0123456789;001\n')
    assert read_contract_registry(csv, config=load_matching_settings()).available
    assert not read_contract_registry(tmp_path / 'missing.xlsx', config={}).available
