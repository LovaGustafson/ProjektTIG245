"""Engine tests with synthetic checks and existing rules under synthetic policies."""

import pandas as pd
import pytest

from src.detection.detection_engine import run_detection
from src.ingestion.image_reader import ImageReadResult
from src.ingestion.reference_reader import ReferenceReadResult
from src.models.ingestion import ReadStatus
from src.models.result import CheckResult, CheckStatus
from src.models.verification import Verification


@pytest.fixture
def verification():
    return Verification("synthetic-001", pd.DataFrame([{
        "verification_id": "synthetic-001", "verification_line_id": 1,
        "signature": "S", "attestation": "A", "image_reference": "synthetic.png",
        "counterparty": "not-a-confirmed-supplier-id",
    }]))


def registry_for(*statuses):
    return {
        f"rule_{i}": lambda v, context, i=i, status=status: (
            CheckResult(v.verification_id, f"rule_{i}", status, f"Reason {i}"),
        )
        for i, status in enumerate(statuses)
    }


@pytest.mark.parametrize("statuses,summary", [
    ([CheckStatus.PASS] * 4, CheckStatus.PASS),
    ([CheckStatus.PASS, CheckStatus.FLAGGED], CheckStatus.FLAGGED),
    ([CheckStatus.FLAGGED, CheckStatus.ERROR, CheckStatus.NOT_CHECKED], CheckStatus.FLAGGED),
    ([CheckStatus.PASS, CheckStatus.ERROR], CheckStatus.ERROR),
    ([CheckStatus.ERROR, CheckStatus.NOT_CHECKED], CheckStatus.ERROR),
    ([CheckStatus.PASS, CheckStatus.NOT_CHECKED], CheckStatus.NOT_CHECKED),
    ([CheckStatus.NOT_CHECKED] * 4, CheckStatus.NOT_CHECKED),
    ([], CheckStatus.NOT_CHECKED),
])
def test_summary_and_status_preservation(verification, statuses, summary):
    result = run_detection(verification, rules=registry_for(*statuses))
    assert result.verification_id == verification.verification_id
    assert result.status == summary
    assert [check.status for check in result.checks] == statuses
    assert sum(result.counts.values()) == len(statuses)
    for status in CheckStatus:
        assert result.counts[status] == statuses.count(status)


def test_multiple_reasons_and_line_metadata_are_preserved(verification):
    first = CheckResult(verification.verification_id, "first", CheckStatus.FLAGGED,
                        "Missing signature", verification_line_id=1, field="signature", row_position=0)
    second = CheckResult(verification.verification_id, "first", CheckStatus.FLAGGED,
                         "Missing attestation", verification_line_id=1, field="attestation", row_position=0)
    repeated = CheckResult(verification.verification_id, "second", CheckStatus.FLAGGED,
                           "Missing signature", verification_line_id=2)
    result = run_detection(verification, rules={
        "first": lambda v, c: (first, second), "second": lambda v, c: (repeated,),
    })
    assert result.checks == (first, second, repeated)
    assert result.checks[0] is first
    assert result.flag_reasons == ("Missing signature", "Missing attestation", "Missing signature")
    assert result.status == CheckStatus.FLAGGED


def test_raised_exception_does_not_stop_remaining_rules(verification, caplog):
    def broken(v, context):
        raise RuntimeError("synthetic failure")

    rules = {"broken": broken, **registry_for(CheckStatus.PASS, CheckStatus.FLAGGED)}
    result = run_detection(verification, rules=rules)
    assert [c.status for c in result.checks] == [CheckStatus.ERROR, CheckStatus.PASS, CheckStatus.FLAGGED]
    assert result.checks[0].check_type == "broken"
    assert "synthetic failure" in result.checks[0].reason
    assert "broken" in caplog.text
    assert result.status == CheckStatus.FLAGGED


def test_returned_error_does_not_stop_later_rules(verification):
    result = run_detection(verification, rules=registry_for(CheckStatus.ERROR, CheckStatus.PASS))
    assert [c.status for c in result.checks] == [CheckStatus.ERROR, CheckStatus.PASS]


def test_partial_generator_results_survive_failure(verification):
    def partial(v, context):
        yield CheckResult(v.verification_id, "partial", CheckStatus.FLAGGED, "Preserve this reason")
        raise ValueError("failed after first result")

    result = run_detection(verification, rules={"partial": partial, **registry_for(CheckStatus.PASS)})
    assert [c.status for c in result.checks] == [CheckStatus.FLAGGED, CheckStatus.ERROR, CheckStatus.PASS]
    assert result.flag_reasons == ("Preserve this reason",)


@pytest.mark.parametrize("output", [None, (), ["invalid result"]])
def test_malformed_or_empty_output_becomes_error(verification, output):
    result = run_detection(verification, rules={"bad": lambda v, c: output, **registry_for(CheckStatus.PASS)})
    assert [c.status for c in result.checks] == [CheckStatus.ERROR, CheckStatus.PASS]


def test_result_for_another_verification_does_not_flag_current_one(verification):
    wrong = CheckResult("different-id", "wrong", CheckStatus.FLAGGED, "Unrelated reason")
    result = run_detection(verification, rules={"wrong": lambda v, c: (wrong,)})
    assert result.status == CheckStatus.ERROR
    assert result.flag_reasons == ()


def test_disabled_rule_never_runs(verification):
    def disabled(v, context):
        pytest.fail("Disabled rule must not run")

    result = run_detection(verification, rules={"disabled": disabled, **registry_for(CheckStatus.PASS)},
                           enabled_rules=["rule_0"])
    assert result.status == CheckStatus.PASS
    assert result.executed_rules == ("rule_0",)
    assert result.disabled_rules == ("disabled",)


def test_no_enabled_rules_is_not_checked(verification):
    result = run_detection(verification, enabled_rules=[])
    assert result.status == CheckStatus.NOT_CHECKED
    assert result.checks == ()
    assert len(result.disabled_rules) == 4


def test_default_rules_run_without_inventing_confirmation(verification):
    result = run_detection(verification)
    assert result.executed_rules == ("required_fields_check", "image_check", "attestation_check", "supplier_check")
    assert len(result.checks) == 4
    assert all(check.status == CheckStatus.NOT_CHECKED for check in result.checks)
    assert all("AK" in check.reason for check in result.checks)


def test_real_presence_rules_with_explicit_synthetic_policy(verification):
    verification.rows.loc[0, "signature"] = None
    verification.rows.loc[0, "image_reference"] = None
    result = run_detection(verification, rule_options={
        "required_fields_check": {"confirmed_required_fields": ["signature", "attestation"],
                                  "confirmed_scope": "each_row"},
        "image_check": {"image_required_confirmed": True, "confirmed_scope": "any_row"},
    })
    assert result.status == CheckStatus.FLAGGED
    assert result.flag_reasons == ("Missing required information: signature",
                                   "Missing required information: image_reference")
    assert result.counts == {CheckStatus.PASS: 1, CheckStatus.FLAGGED: 2,
                             CheckStatus.ERROR: 0, CheckStatus.NOT_CHECKED: 2}


def test_available_ingestion_results_reach_rules_without_business_interpretation(verification):
    image = ImageReadResult(None, ReadStatus.UNREADABLE, "Synthetic unreadable image")
    supplier = ReferenceReadResult("supplier_procurement", None, ReadStatus.LOADED,
                                   "Synthetic generic table", pd.DataFrame({"counterparty": ["001"]}))
    attestation = ReferenceReadResult("attestation", None, ReadStatus.MISSING_FILE, "Synthetic missing file")

    def inspect_context(v, context):
        assert v is verification
        assert context.image_results == (image,)
        assert context.supplier_reference is supplier
        assert context.attestation_reference is attestation
        return (CheckResult(v.verification_id, "inspect", CheckStatus.NOT_CHECKED, "Synthetic inspection"),)

    result = run_detection(verification, image_results=[image], supplier_reference=supplier,
                           attestation_reference=attestation, rules={"inspect": inspect_context})
    assert result.status == CheckStatus.NOT_CHECKED
    assert result.context.supplier_reference.schema_status == "UNCONFIRMED"
    defaults = run_detection(verification, image_results=[image], supplier_reference=supplier,
                             attestation_reference=attestation)
    assert all(c.status == CheckStatus.NOT_CHECKED for c in defaults.checks)


def test_input_and_previous_run_are_preserved(verification):
    before = verification.rows.copy(deep=True)
    first = run_detection(verification)
    second = run_detection(verification, rules=registry_for(CheckStatus.PASS))
    pd.testing.assert_frame_equal(verification.rows, before)
    assert first.status == CheckStatus.NOT_CHECKED
    assert len(first.checks) == 4
    assert second.status == CheckStatus.PASS


def test_invalid_rule_options_are_isolated_to_that_rule(verification):
    result = run_detection(verification, rule_options={"image_check": {"unknown_option": True}})
    assert result.counts[CheckStatus.ERROR] == 1
    assert result.counts[CheckStatus.NOT_CHECKED] == 3


@pytest.mark.parametrize("kwargs", [{"enabled_rules": ["typo"]},
                                    {"rule_options": {"typo": {}}},
                                    {"enabled_rules": "image_check"}])
def test_invalid_registry_configuration_is_explicit(verification, kwargs):
    with pytest.raises(ValueError):
        run_detection(verification, **kwargs)
