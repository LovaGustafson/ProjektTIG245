"""Orchestrate existing modules; retain intermediate data and all check results."""
from dataclasses import dataclass
from pathlib import Path

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
from src.sampling.manual_sample import create_manual_sample
from src.output.report_generator import generate_reports
from src.presentation import summary_counts


@dataclass
class PipelineResult:
    standardized_data: pd.DataFrame
    validation: ValidationResult
    filtering: FilterResult
    ungrouped_data: pd.DataFrame
    verifications: list[Verification]
    detection_results: list[DetectionResult]
    manual_sample: list[Verification]
    report_paths: dict[str, Path]
    todos: tuple[str, ...]


def run_pipeline(input_path, *, output_dir, settings_path=DEFAULT_SETTINGS_PATH,
                 sheet_name=0, date_format=None, image_references=None,
                 supplier_register=None, attestation_register=None,
                 rule_options=None, rules=None) -> PipelineResult:
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
    the existing report generator exports only its three supported reports.
    TODO: a persistent report format for all validation/nonflagged results.
    """
    standardized = map_columns(read_excel(input_path, sheet_name=sheet_name))
    validation = validate(standardized, date_format=date_format)
    filtering = filter_rows(standardized, settings_path=settings_path)
    # Route using validator evidence, rather than reimplementing identity checks.
    unusable = {row.row_position for row in validation.rows
                if any(error.field == 'verification_id' for error in row.validation_errors)}
    cleaned = filtering.cleaned_data
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
    results = [run_detection(v, image_results=evidence, supplier_reference=supplier,
                             attestation_reference=attestation,
                             rule_options=rule_options, rules=rules)
               for v, evidence in zip(verifications, images)]
    sample = create_manual_sample(verifications, settings_path=settings_path)
    flagged = [v for v, result in zip(verifications, results) if result.flag_reasons]
    checks = [check for result in results for check in result.checks
              if check.status == CheckStatus.FLAGGED]
    paths = generate_reports(cleaned, flagged_verifications=flagged,
                             flagged_checks=checks, manual_sample=sample, output_dir=output_dir,
                             summary=summary_counts(standardized, validation, results))
    todos = filtering.todos + (
        'TODO / awaiting AK: invalid-identity routing, Bild linkage and business rule confirmation',
        'TODO: persistent export of validation and nonflagged detection results',
    )
    return PipelineResult(standardized, validation, filtering, ungrouped,
                          verifications, results, sample, paths, todos)
