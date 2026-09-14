from dataclasses import replace
from io import BytesIO
import pandas as pd
from src.ui_support import analyze_upload, validation_table, flagged_table
from src.presentation import context_fields, summary_counts
from src.models.result import CheckResult, CheckStatus
from src.ingestion.excel_reader import read_excel
from src.output.report_generator import generate_reports


def upload(data):
    stream = BytesIO()
    data.to_excel(stream, index=False)
    return analyze_upload(stream.getvalue())


def test_schema_and_row_errors_have_swedish_messages_and_real_ids():
    review = upload(pd.DataFrame({'Vernr': ['001'], 'Vrad': [2], 'Utfall': ['bad'], 'Konto': ['4000']}))
    errors = validation_table(review.result)
    schema = errors[errors.scope == 'Fil'].iloc[0]
    assert schema.code == 'missing_column'
    assert schema.message == "Kolumnen 'Verdatum' saknas i den uppladdade filen."
    assert pd.isna(schema.verification_id)
    row = errors[errors.scope == 'Rad'].iloc[0]
    assert row.verification_id == '001'
    assert row.verification_line_id == 2
    assert row.message.endswith('.')


def test_missing_identity_not_invented():
    review = upload(pd.DataFrame({'Vrad': [1], 'Utfall': ['bad']}))
    assert validation_table(review.result).verification_id.isna().all()


def test_context_preserves_conflicting_values_without_aggregation():
    context = context_fields(pd.DataFrame({'header_text': ['A', 'B'], 'amount': [10, 20]}))
    assert context['header_text'] == 'A\nB'
    assert context['amount'] == '10\n20'
    assert context['verification_date'] is None


def test_enriched_report_and_summary_roundtrip(tmp_path):
    review = upload(pd.DataFrame({'Vernr': ['001'], 'Vrad': [1], 'Verdatum': ['2026-09-03'],
                                   'Huvudtext': ['Testfaktura'], 'Utfall': [10], 'Konto': ['4000']}))
    result = review.result
    checks = [CheckResult('001', 'required_fields_check', CheckStatus.FLAGGED,
                          f'Missing required information: {field}', field=field)
              for field in ['signature', 'attestation']]
    result.detection_results[0] = replace(result.detection_results[0], checks=tuple(checks))
    assert flagged_table(result).iloc[0].header_text == 'Testfaktura'
    summary = summary_counts(result.standardized_data, result.validation, result.detection_results)
    paths = generate_reports(result.filtering.cleaned_data, flagged_verifications=result.verifications,
                             flagged_checks=checks, manual_sample=[], output_dir=tmp_path, summary=summary)
    exported = read_excel(paths['flagged_invoices'], sheet_name='checks')
    assert len(exported) == 2
    assert exported.header_text.tolist() == ['Testfaktura'] * 2
    assert exported.verification_date.tolist() == ['2026-09-03'] * 2
    assert exported.code.isna().all()
    assert exported.message.tolist() == ['Obligatorisk information saknas: signature.',
                                          'Obligatorisk information saknas: attestation.']
    totals = read_excel(paths['flagged_invoices'], sheet_name='Summary').iloc[0]
    assert totals.to_dict() == summary


def test_pipeline_summary_matches_ui_metrics():
    review = upload(pd.DataFrame({'Vernr': ['001'], 'Vrad': [1], 'Utfall': ['bad'], 'Konto': ['4000']}))
    summary = pd.read_excel(BytesIO(review.downloads['flagged_invoices.xlsx']), sheet_name='Summary')
    assert summary.iloc[0]['validation_errors'] == len(validation_table(review.result))
    assert summary.iloc[0]['not_checked_results'] == 4
