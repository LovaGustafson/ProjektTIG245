"""Orchestrate independent rules and summarize their results for one verification."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING

from src.detection.rules.attestation_check import attestation_check
from src.detection.rules.image_check import image_check
from src.detection.rules.required_fields_check import required_fields_check
from src.detection.rules.supplier_check import supplier_check
from src.models.result import CheckResult, CheckStatus
from src.models.verification import Verification

if TYPE_CHECKING:
    from src.ingestion.image_reader import ImageReadResult
    from src.ingestion.reference_reader import ReferenceReadResult


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectionContext:
    """Already-loaded evidence and explicit options; rules must treat these as read-only."""

    image_results: tuple[ImageReadResult, ...] = ()
    supplier_reference: ReferenceReadResult | None = None
    attestation_reference: ReferenceReadResult | None = None
    rule_options: Mapping[str, Mapping[str, object]] = field(default_factory=dict)


@dataclass(frozen=True)
class DetectionResult:
    verification_id: object
    checks: tuple[CheckResult, ...]
    context: DetectionContext
    executed_rules: tuple[str, ...]
    disabled_rules: tuple[str, ...]

    @property
    def status(self) -> CheckStatus:
        """Technical summary: FLAGGED > ERROR > NOT_CHECKED > PASS.

        With no results the summary is NOT_CHECKED. This convention prevents
        incomplete execution from implying PASS; no business risk score is used.
        """
        statuses = {check.status for check in self.checks}
        if not statuses:
            return CheckStatus.NOT_CHECKED
        for status in (CheckStatus.FLAGGED, CheckStatus.ERROR, CheckStatus.NOT_CHECKED):
            if status in statuses:
                return status
        return CheckStatus.PASS

    @property
    def flag_reasons(self) -> tuple[str, ...]:
        """Keep every flagged reason in execution order, including repeated text."""
        return tuple(check.reason for check in self.checks if check.status == CheckStatus.FLAGGED)

    @property
    def counts(self) -> dict[CheckStatus, int]:
        """Counts of check results, not counts of rules or invoice rows."""
        return {status: sum(check.status == status for check in self.checks)
                for status in CheckStatus}


Rule = Callable[[Verification, DetectionContext], Iterable[CheckResult]]


def _default_rules() -> dict[str, Rule]:
    # Only adapt call signatures here; applicability and checks stay in rules.
    return {
        rule.__name__: (
            lambda verification, context, rule=rule:
            rule(verification, **context.rule_options.get(rule.__name__, {}))
        )
        for rule in (required_fields_check, image_check, attestation_check, supplier_check)
    }


def run_detection(
    verification: Verification, *,
    image_results: Sequence[ImageReadResult] = (),
    supplier_reference: ReferenceReadResult | None = None,
    attestation_reference: ReferenceReadResult | None = None,
    rule_options: Mapping[str, Mapping[str, object]] | None = None,
    enabled_rules: Sequence[str] | None = None,
    rules: Mapping[str, Rule] | None = None,
) -> DetectionResult:
    """Run enabled rules once in registry order and preserve all their results.

    By default all four existing rules run with their unresolved-policy defaults.
    rule_options forwards keyword arguments by rule name; passing confirmation
    options has exactly the meaning documented by that rule. Nothing is inferred
    from register columns, ingestion success, or the presence of counterparty.

    enabled_rules=None selects all rules; an empty sequence selects none.
    Disabled names are recorded separately, not counted as applicable checks.
    Unknown enabled/option names are configuration errors and raise ValueError.
    A custom rules registry replaces the defaults and receives the full context,
    allowing future rules to consume evidence without adding logic to the engine.

    Existing rules do not yet consume ingestion results. They remain available
    in the result context; TODO: extend individual rules after AK confirms how
    to use image content and reference schemas. This engine never reads files.

    Raised exceptions, malformed outputs and empty rule outputs become ERROR
    results. Results yielded before a failure survive, and later rules still run.
    A result for another verification is rejected as an execution error so it
    cannot affect this verification's summary. Input business data is not edited.
    """
    registry = _default_rules() if rules is None else dict(rules)
    options = dict(rule_options) if rule_options is not None else {}
    if isinstance(enabled_rules, str):
        raise ValueError("enabled_rules must be a sequence of rule names, not a string")
    enabled = set(registry) if enabled_rules is None else set(enabled_rules)
    unknown = (enabled | set(options)) - set(registry)
    if unknown:
        raise ValueError(f"Unknown detection rule names: {sorted(unknown)}")
    context = DetectionContext(tuple(image_results), supplier_reference, attestation_reference, options)
    checks = []
    executed = []
    disabled = []
    for name, rule in registry.items():
        if name not in enabled:
            disabled.append(name)
            continue
        executed.append(name)
        start = len(checks)
        try:
            for check in rule(verification, context):
                if not isinstance(check, CheckResult):
                    raise TypeError("Rule must return an iterable of CheckResult objects")
                if check.verification_id != verification.verification_id:
                    raise ValueError("Rule returned a result for another verification")
                checks.append(check)
            if len(checks) == start:
                raise ValueError("Rule returned no results; use NOT_CHECKED for inapplicable checks")
        except Exception as exc:
            checks.append(CheckResult(
                verification.verification_id, name, CheckStatus.ERROR,
                f"Rule {name} failed ({type(exc).__name__}): {exc}",
            ))
            logger.warning("Detection rule %s failed (%s)", name, type(exc).__name__)
    return DetectionResult(verification.verification_id, tuple(checks), context,
                           tuple(executed), tuple(disabled))
