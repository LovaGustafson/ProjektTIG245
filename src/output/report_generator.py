"""Write already-prepared review results to new Excel workbooks."""

from collections.abc import Iterable, Mapping
from contextlib import ExitStack
from dataclasses import asdict, fields
from decimal import Decimal
from io import BytesIO
from itertools import chain
from pathlib import Path

import pandas as pd

from src.presentation import context_fields, check_message, customer_facing_rows
from src.models.result import CheckResult
from src.models.verification import Verification
from src.supplier_matching.analysis import enrich_rows
from src.supplier_matching.extraction import normalize_header_text
from src.run_summary import SAMPLE_ORDER, SAMPLE_POPULATION, SAMPLE_METHOD, SAMPLE_IDENTITY


ROW_COLUMNS = ["verification_id", "verification_line_id"]
CHECK_COLUMNS = [field.name for field in fields(CheckResult)] + ["verification_date", "header_text", "code", "message"]


def _verification_rows(verifications: Iterable[Verification], supplier_analysis=None) -> pd.DataFrame:
    frames = [verification.rows for verification in verifications]
    rows = pd.concat(frames, sort=False) if frames else pd.DataFrame(columns=ROW_COLUMNS)
    return enrich_rows(rows, supplier_analysis)


def supplier_sheets(analysis, positions=None):
    if analysis is None:
        return {}
    metadata = {'Registerinformation': pd.DataFrame({
        'registry_name': analysis.registry.source_name,
        'registry_source': analysis.registry.source_kind,
        'registry_sha256': analysis.registry.source_sha256,
        'registry_sheet': analysis.registry.data.attrs.get('source_sheet'),
        'registry_header_row': analysis.registry.data.attrs.get('source_header_row'),
        'registry_snapshot_date': analysis.registry.snapshot_date,
        'matching_available': analysis.registry.available,
        'issues': list(analysis.registry.issues) or [''],
    })}
    if not analysis.registry.available:
        return metadata
    def subset(data):
        return data if positions is None else data[data['source_row_position'].isin(positions)]
    return {**metadata, 'Leverantörsmatchning': subset(analysis.rows),
            'Leverantörskandidater': subset(analysis.candidates),
            'Möjliga avtal': subset(analysis.contracts)}


def uncertain_supplier_rows(data, analysis):
    """Retain every non-strong occurrence, including unavailable matching."""
    available = analysis is not None and analysis.registry.available
    if available:
        strong = analysis.rows.loc[analysis.rows['supplier_match_status'] == 'STRONG_MATCH',
                                   'source_row_position']
        data = data.loc[~data.index.isin(strong)]
    result = enrich_rows(data, analysis)
    if not available:
        evidence = {'source_row_position': list(data.index),
                    'header_text_normalized': (data['header_text'].map(normalize_header_text).tolist()
                                               if list(data.columns).count('header_text') == 1 else None),
                    'supplier_match_status': None,
                    'supplier_check_status': 'NOT_CHECKED',
                    'supplier_match_reason': '; '.join(analysis.registry.issues) if analysis else 'Register saknas.'}
        for field, values in evidence.items():
            while field in result.columns:
                field = '_' + field
            result[field] = values
    return result


def audit_sheets(data, *, source_context=None, run_summary=None, sampling_evidence=None, table_name='rows',
                 sampling_result=None, supplier_view=None):
    sheets = {}
    if source_context is not None:
        header = source_context.get('source_header_row')
        sheets['Källspårning'] = pd.DataFrame({
            'export_sheet': [table_name] * len(data),
            'export_row': list(range(2, len(data) + 2)),
            'source_row_position': list(data.index),
            'source_excel_row': [header + 1 + int(p) if header is not None else None for p in data.index],
            **{key: [value] * len(data) for key, value in source_context.items()},
        })
        sheets['Källinformation'] = pd.DataFrame([source_context])
    if run_summary is not None:
        sheets['Körningsöversikt'] = pd.DataFrame(list(run_summary.counts().items()), columns=['Mått', 'Antal'])
        sheets['Exkluderingsregler'] = pd.DataFrame(list(run_summary.exclusion_counts.items()),
                                                columns=['Regel', 'Antal träffade källrader'])
        sheets['Urvalsmetod'] = pd.DataFrame([{
            'Population': SAMPLE_POPULATION, 'Ordning': SAMPLE_ORDER,
            'Metod': SAMPLE_METHOD, 'Leverantörsunikhet': SAMPLE_IDENTITY,
            'Intervall': run_summary.sample_interval,
            'Antal verifikationer i populationen': run_summary.eligible_verifications,
            'Antal valda verifikationer': run_summary.sampled_verifications,
            'Antal valda rader': run_summary.sampled_rows,
            'Önskat antal verifikationer': sampling_result.target_size if sampling_result is not None else None,
            'Förklaring till mindre stickprov': sampling_result.shortfall_message if sampling_result is not None else None,
        }])
    if sampling_evidence is not None:
        sheets['Urvalspositioner'] = sampling_evidence
    if sampling_result is not None:
        sheets['Urvalsbeslut'] = sampling_result.decisions
        sheets['Urvalsidentiteter'] = sampling_result.identity_rows
    if supplier_view is not None:
        sheets['Leverantörsvy'] = supplier_view
    return sheets


def _workbook(sheets: Mapping[str, pd.DataFrame]) -> bytes:
    prepared = {}
    for name, data in sheets.items():
        # Keep decimal precision instead of pandas' float conversion.
        export_data = customer_facing_rows(data).map(
            lambda value: str(value) if isinstance(value, Decimal) else value)
        for value in chain(export_data.columns, export_data.to_numpy().flat):
            if isinstance(value, str) and len(value) > 32767:
                raise ValueError(f"Worksheet {name}: text exceeds Excel's 32767-character cell limit")
        prepared[name] = export_data
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, export_data in prepared.items():
            export_data.to_excel(writer, sheet_name=name, index=False)
            # Source strings are evidence, not executable spreadsheet formulas.
            # Also retain strings such as '#N/A' as literal text on read-back.
            for row in writer.sheets[name].iter_rows():
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.data_type = "s"
    return buffer.getvalue()


def generate_reports(
    cleaned_data: pd.DataFrame, *,
    flagged_verifications: Iterable[Verification],
    flagged_checks: Iterable[CheckResult],
    manual_sample: Iterable[Verification],
    output_dir: str | Path,
    summary: Mapping[str, int] | None = None,
    supplier_analysis=None,
    run_summary=None,
    source_context=None,
    sampling_evidence=None,
    original_data=None,
    filtering=None,
    sampling_result=None,
    supplier_view=None,
    report_names=None,
) -> dict[str, Path]:
    """Export review workbooks and return their paths keyed by report name.

    Inputs must already be cleaned, flagged and sampled by their respective
    modules. Every supplied check is exported once, in order, with no status
    filtering or deduplication. The caller supplies complete verifications for
    those checks. This function does not run detection or choose a sample.

    cleaned_data.xlsx and manual_sample.xlsx contain a 'rows' worksheet.
    flagged_invoices.xlsx contains 'checks' (all CheckResult fields) and 'rows'
    (all rows of the supplied flagged verifications). Separate sheets avoid
    collisions between business columns and check metadata and retain null
    line IDs for verification-level checks. All columns and row order survive;
    index labels/attrs are not inserted into original business columns. Supplied
    source/run context is exported on separate evidence sheets. Uncertain rows
    have a separate report; supplied original/filter data adds excluded rows.
    Empty outputs retain headers where a schema is supplied.

    Excel-native scalar values are supported; Decimal values are explicitly
    stored as exact text, and pandas serializes nested Python objects as text.
    Numbered Slutk markers are removed from header/supplier text on an export
    copy. Other strings, including formula expressions, are exported literally.
    Excel cannot preserve arbitrary Python types/dtypes.

    Workbooks are serialized before any destination is created. Exclusive
    creation refuses every existing path, including symlinks, so source files
    and prior reports cannot be overwritten. On failure, only files created by
    this call are removed. Filesystem and serialization errors propagate.
    """
    flagged_verifications = list(flagged_verifications)
    manual_sample = list(manual_sample)
    flagged_rows = _verification_rows(flagged_verifications, supplier_analysis)
    sample_rows = _verification_rows(manual_sample, supplier_analysis)
    uncertain_rows = uncertain_supplier_rows(cleaned_data, supplier_analysis)
    def audit(data, table_name='rows'):
        return audit_sheets(data, source_context=source_context, run_summary=run_summary,
                            sampling_evidence=sampling_evidence, table_name=table_name,
                            sampling_result=sampling_result, supplier_view=supplier_view)
    checks = []
    for check in flagged_checks:
        record = asdict(check)
        record["status"] = check.status.value
        context = {}
        for verification in flagged_verifications:
            if verification.verification_id == check.verification_id:
                context = context_fields(verification.rows)
                break
        record.update(verification_date=context.get('verification_date'),
                      header_text=context.get('header_text'), code=None,
                      message=check_message(check))
        checks.append(record)
    # Factories preserve the serializer and sheet contents while allowing the UI
    # to prepare only the requested download. CLI callers still create all files.
    workbooks = {
        "cleaned_data": lambda: _workbook({"rows": enrich_rows(cleaned_data, supplier_analysis),
                                    **supplier_sheets(supplier_analysis), **audit(cleaned_data)}),
        "flagged_invoices": lambda: _workbook({
            "checks": pd.DataFrame(checks, columns=CHECK_COLUMNS),
            "rows": flagged_rows,
            **supplier_sheets(supplier_analysis, flagged_rows.index),
            **({"Summary": pd.DataFrame([summary])} if summary is not None else {}),
            **audit(flagged_rows),
        }),
        "manual_sample": lambda: _workbook({"rows": sample_rows,
                                    **supplier_sheets(supplier_analysis, sample_rows.index), **audit(sample_rows)}),
        "uncertain_suppliers": lambda: _workbook({"rows": uncertain_rows,
                                    **supplier_sheets(supplier_analysis, uncertain_rows.index), **audit(uncertain_rows)}),
    }
    if original_data is not None and filtering is not None:
        _, excluded = review_tables(original_data, filtering)
        workbooks['excluded_data'] = lambda: _workbook({'Bortfiltrerade': excluded, **audit(excluded, 'Bortfiltrerade')})
    names = list(workbooks) if report_names is None else list(report_names)
    workbooks = {name: workbooks[name]() for name in names}
    directory = Path(output_dir)
    paths = {name: directory / f"{name}.xlsx" for name in workbooks}
    directory.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        with ExitStack() as stack:
            streams = {}
            for name, path in paths.items():
                streams[name] = stack.enter_context(path.open("xb"))
                created.append(path)
            for name, content in workbooks.items():
                streams[name].write(content)
    except BaseException:
        for path in created:
            path.unlink()
        raise
    return paths


def review_tables(original_data, filtering):
    """Use source headers/values; keep metadata distinct even on name collision."""
    kept = [i for i, reason in enumerate(filtering.reasons) if not reason]
    removed = [i for i, reason in enumerate(filtering.reasons) if reason]
    review = original_data.iloc[kept].copy(deep=True)
    excluded = original_data.iloc[removed].copy(deep=True)
    label = 'Exkluderingsorsak'
    while label in excluded.columns:
        label = '_' + label
    excluded[label] = [filtering.reasons[i] for i in removed]
    return review, excluded


def review_summary(original_data, filtering):
    return {
        'Totalt antal rader': len(original_data),
        'Kvar för granskning': len(filtering.cleaned_data),
        'Exkluderade på grund av konto': filtering.account_count,
        'Exkluderade på grund av verifikationstyp': filtering.verification_type_count,
        'Totalt bortfiltrerade': len(filtering.excluded_data),
    }


def review_workbooks(original_data, filtering, supplier_analysis=None, *, run_summary=None,
                     source_context=None, sampling_evidence=None, sampling_result=None, supplier_view=None,
                     filenames=None):
    review, excluded = review_tables(original_data, filtering)
    review = enrich_rows(review, supplier_analysis)
    counts = review_summary(original_data, filtering)
    if supplier_analysis is not None and supplier_analysis.registry.available:
        counts.update(supplier_analysis.summary())
    if run_summary is not None:
        counts.update(run_summary.counts())
    def audit(data, table_name):
        return audit_sheets(data, source_context=source_context, run_summary=run_summary,
                            sampling_evidence=sampling_evidence, table_name=table_name,
                            sampling_result=sampling_result, supplier_view=supplier_view)
    review_audit = audit(review, 'Granskning')
    excluded_audit = audit(excluded, 'Bortfiltrerade')
    combined_audit = dict(review_audit)
    if source_context is not None:
        combined_audit['Källspårning'] = pd.concat([
            review_audit['Källspårning'], excluded_audit['Källspårning']], ignore_index=True)
    summary = pd.DataFrame(list(counts.items()),
                           columns=['Mått', 'Antal'])
    workbooks = {
        'granskning.xlsx': lambda: _workbook({'Granskning': review, **supplier_sheets(supplier_analysis), **review_audit}),
        'bortfiltrerade.xlsx': lambda: _workbook({'Bortfiltrerade': excluded, **excluded_audit}),
        'samlad_kontrollfil.xlsx': lambda: _workbook({
            'Granskning': review, 'Bortfiltrerade': excluded, 'Sammanfattning': summary,
            **supplier_sheets(supplier_analysis),
            **combined_audit,
        }),
    }
    names = list(workbooks) if filenames is None else list(filenames)
    return {name: workbooks[name]() for name in names}
