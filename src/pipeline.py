"""Orchestrate existing modules; retain intermediate data and all check results."""
from dataclasses import dataclass, fields
from pathlib import Path
from hashlib import sha256

import pandas as pd

from src.ingestion.excel_reader import read_excel
from src.ingestion.image_reader import read_image
from src.ingestion.reference_reader import read_supplier_register, read_attestation_register
from src.mapping.column_mapper import map_columns
from src.validation.validator import validate, ValidationResult
from src.filtering.filter_engine import filter_rows, FilterResult, DEFAULT_SETTINGS_PATH
from src.verification.verification_builder import build_verifications
from src.detection.detection_engine import run_detection, DetectionResult
from src.models.result import CheckStatus
from src.models.verification import Verification
from src.sampling.manual_sample import plan_manual_sample, load_sample_interval, SamplingResult
from src.output.report_generator import generate_reports
from src.presentation import summary_counts
from src.ingestion.registry_source import resolve_registry_source, load_contract_source, RegistrySource
from src.supplier_matching.analysis import SupplierAnalysis, analyze_suppliers
from src.supplier_matching.settings import load_matching_settings, MatchSettings
from src.supplier_matching.contract_period import ContractDatePolicy
from src.run_summary import RunSummary, summarize_run
from src.supplier_matching.view_scope import load_view_rules, classify_supplier_view


@dataclass
class PipelineResult:
    original_data: pd.DataFrame
    standardized_data: pd.DataFrame
    validation: ValidationResult
    filtering: FilterResult
    ungrouped_data: pd.DataFrame
    verifications: list[Verification]
    detection_results: list[DetectionResult]
    manual_sample: list[Verification]
    report_paths: dict[str, Path]
    todos: tuple[str, ...]
    supplier_analysis: SupplierAnalysis | None = None
    summary: RunSummary | None = None
    source_context: dict | None = None
    sampling_evidence: pd.DataFrame | None = None
    registry_source: RegistrySource | None = None
    sampling_result: SamplingResult | None = None
    supplier_view: pd.DataFrame | None = None


def run_pipeline(input_path, *, output_dir, settings_path=DEFAULT_SETTINGS_PATH,
                 sheet_name=0, date_format=None, image_references=None,
                 supplier_register=None, attestation_register=None,
                 rule_options=None, rules=None, excluded_verification_types=None,
                 registry_snapshot_date=None, registry_source=None,
                 use_default_registry=True, source_name=None, export_reports=True) -> PipelineResult:
    """Run analysis of every grouped verification before selecting the sample.

    Validation metadata refers to standardized_data positions before filtering.
    Invalid amounts/dates/line IDs do not discard a verification's rows.
    Validator-reported invalid verification IDs cannot identify a verification;
    their rows remain in ungrouped_data and cleaned output, not a null-ID group.
    TODO / awaiting AK: final routing policy for invalid identities.

    Image paths must be explicitly supplied as {verification_id: [paths]}.
    Bild linkage is not inferred. Readers retain their default local-file and
    register format conventions. Unconfirmed rules retain engine defaults;
    required_fields in YAML does not imply confirmation of business scope.
    All detection results and validation errors are retained in PipelineResult;
    the report generator exports review, flagged, sample, uncertain-supplier and
    excluded workbooks with source/run evidence. Supplier identity and contract
    periods have separate sheets when a register is usable. Name matching is
    row-level and runs on cleaned rows even if they cannot form a verification.
    TODO: a persistent report format for all validation/nonflagged checks.
    """
    original = read_excel(input_path, sheet_name=sheet_name)
    standardized = map_columns(original)
    validation = validate(standardized, date_format=date_format)
    filtering = filter_rows(standardized, settings_path=settings_path,
                            excluded_verification_types=excluded_verification_types)
    # Route using validator evidence, rather than reimplementing identity checks.
    unusable = {row.row_position for row in validation.rows
                if any(error.field == 'verification_id' for error in row.validation_errors)}
    cleaned = filtering.cleaned_data
    config = load_matching_settings(settings_path)
    registry_source = registry_source or resolve_registry_source(
        settings_path=settings_path, path=supplier_register,
        mode='default' if use_default_registry or supplier_register is not None else 'disabled',
        registry_snapshot_date=registry_snapshot_date)
    registry = load_contract_source(registry_source, config=config)
    matching = MatchSettings(**{f.name: config[f.name] for f in fields(MatchSettings) if f.name in config})
    contract_policy = ContractDatePolicy(**(config.get('contract_period') or {}))
    supplier_analysis = analyze_suppliers(cleaned, registry, settings=matching, date_format=date_format,
                                         contract_policy=contract_policy)
    supplier_view = classify_supplier_view(cleaned, supplier_analysis, load_view_rules(settings_path))
    eligible = cleaned.loc[~cleaned.index.isin(unusable)]
    ungrouped = cleaned.loc[cleaned.index.isin(unusable)].copy(deep=True)
    if list(eligible.columns).count('verification_id') == 1:
        verifications = build_verifications(eligible)
    else:
        verifications = []
        ungrouped = cleaned.copy(deep=True)
    supplier = read_supplier_register(supplier_register)
    attestation = read_attestation_register(attestation_register)
    images = [tuple(read_image(path) for path in (image_references or {}).get(v.verification_id, ()))
              for v in verifications]
    if rules is None and supplier_analysis is not None and supplier_analysis.registry.available:
        rule_options = {**(rule_options or {})}
        rule_options['supplier_check'] = {**rule_options.get('supplier_check', {}),
                                          'identity_matching_available': True}
    results = [run_detection(v, image_results=evidence, supplier_reference=supplier,
                             attestation_reference=attestation,
                             rule_options=rule_options, rules=rules)
               for v, evidence in zip(verifications, images)]
    interval = load_sample_interval(settings_path)
    sampling_result = plan_manual_sample(verifications, interval=interval, supplier_analysis=supplier_analysis)
    sample = sampling_result.sample
    run_summary = summarize_run(original, filtering, ungrouped, verifications, results,
                                sample, supplier_analysis, interval)
    source_context = {'source_name': source_name or Path(input_path).name,
                      'source_sha256': sha256(Path(input_path).read_bytes()).hexdigest(),
                      'source_sheet': original.attrs.get('source_sheet'),
                      'source_header_row': original.attrs.get('source_header_row')}
    selected_positions = sampling_result.decisions.loc[
        sampling_result.decisions['decision'] == 'SELECTED', 'population_position']
    sampling_evidence = sampling_result.identity_rows.loc[
        sampling_result.identity_rows['population_position'].isin(selected_positions)].copy(deep=True)
    todos = filtering.todos + (
        'TODO / awaiting AK: invalid-identity routing, Bild linkage and business rule confirmation',
        'TODO: persistent export of validation and nonflagged detection results',
    )
    if supplier_analysis is not None:
        todos += supplier_analysis.registry.issues
    result = PipelineResult(original, standardized, validation, filtering, ungrouped,
                          verifications, results, sample, {}, todos, supplier_analysis,
                          run_summary, source_context, sampling_evidence, registry_source,
                          sampling_result, supplier_view)
    if export_reports:
        result.report_paths = export_pipeline_result(result, output_dir=output_dir)
    return result


def export_pipeline_result(result, *, output_dir, report_names=None):
    """Serialize existing evidence without rerunning any part of the analysis."""
    flagged = [v for v, detection in zip(result.verifications, result.detection_results) if detection.flag_reasons]
    checks = [check for detection in result.detection_results for check in detection.checks
              if check.status == CheckStatus.FLAGGED]
    return generate_reports(result.filtering.cleaned_data, flagged_verifications=flagged,
        flagged_checks=checks, manual_sample=result.manual_sample, output_dir=output_dir,
        summary=summary_counts(result.standardized_data, result.validation, result.detection_results),
        supplier_analysis=result.supplier_analysis, run_summary=result.summary,
        source_context=result.source_context, sampling_evidence=result.sampling_evidence,
        sampling_result=result.sampling_result, supplier_view=result.supplier_view,
        original_data=result.original_data, filtering=result.filtering, report_names=report_names)
