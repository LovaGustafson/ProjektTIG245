"""Synthetic presence policies exercise mechanics, not actual AK confirmations."""

from dataclasses import asdict

import pandas as pd
import pytest

from src.detection.rules.attestation_check import attestation_check
from src.detection.rules.image_check import image_check
from src.detection.rules.required_fields_check import required_fields_check
from src.detection.rules.supplier_check import supplier_check
from src.models.result import CheckResult, CheckStatus
from src.models.verification import Verification


def verification(*rows):
    return Verification("synthetic-001", pd.DataFrame([
        {"verification_id": "synthetic-001", "verification_line_id": i + 1, **values}
        for i, values in enumerate(rows)
    ], dtype=object))


def required(v, fields=("signature", "attestation"), scope="each_row"):
    return required_fields_check(v, confirmed_required_fields=fields, confirmed_scope=scope)


def image(v, scope="each_row"):
    return image_check(v, image_required_confirmed=True, confirmed_scope=scope)


@pytest.mark.parametrize("status", list(CheckStatus))
def test_shared_result_supports_all_statuses_and_structured_fields(status):
    result = CheckResult("synthetic-001", "test", status, "Synthetic reason", 3)
    fields = asdict(result)
    assert fields["verification_id"] == "synthetic-001"
    assert fields["verification_line_id"] == 3
    assert fields["check_type"] == "test"
    assert fields["status"] == status.value
    assert fields["reason"] == "Synthetic reason"


@pytest.mark.parametrize("reason", ["", "  ", None])
def test_result_requires_explanation(reason):
    with pytest.raises(ValueError, match="reason"):
        CheckResult("synthetic", "test", CheckStatus.FLAGGED, reason)


def test_result_rejects_unknown_status():
    with pytest.raises(ValueError):
        CheckResult("synthetic", "test", "UNKNOWN", "reason")


@pytest.mark.parametrize("rule", [required_fields_check, image_check,
                                  attestation_check, supplier_check])
@pytest.mark.parametrize("values", [{}, {"signature": "S", "attestation": "A",
                                        "image_reference": "synthetic.png"}])
def test_unconfirmed_rules_never_pass_or_flag(rule, values):
    result, = rule(verification(values))
    assert result.status == CheckStatus.NOT_CHECKED
    assert "AK" in result.reason
    assert result.verification_line_id is None


def test_required_information_present():
    results = required(verification({"signature": "S", "attestation": "A"}))
    assert len(results) == 2
    assert all(r.status == CheckStatus.PASS for r in results)
    assert all(r.verification_line_id == 1 for r in results)


@pytest.mark.parametrize("value", [None, pd.NA, pd.NaT, float("nan"), "", " \t"])
def test_required_information_missing(value):
    results = required(verification({"signature": value, "attestation": "A"}))
    assert results[0].status == CheckStatus.FLAGGED
    assert "signature" in results[0].reason
    assert results[1].status == CheckStatus.PASS


def test_missing_required_column_is_missing_information():
    result, = required(verification({}), fields=("signature",))
    assert result.status == CheckStatus.FLAGGED
    assert result.field == "signature"


def test_both_required_fields_and_scope_must_be_confirmed():
    v = verification({})
    result, = required_fields_check(v, confirmed_required_fields=("signature",))
    assert result.status == CheckStatus.NOT_CHECKED
    result, = required_fields_check(v, confirmed_scope="each_row")
    assert result.status == CheckStatus.NOT_CHECKED


def test_empty_confirmed_policy_is_not_a_pass():
    result, = required(verification({}), fields=())
    assert result.status == CheckStatus.NOT_CHECKED


@pytest.mark.parametrize("fields", ["signature", [None], [""], 123])
def test_malformed_policy_returns_error(fields):
    result, = required(verification({}), fields=fields)
    assert result.status == CheckStatus.ERROR


@pytest.mark.parametrize("run", [required, image])
def test_unknown_scope_and_empty_rows_return_error(run):
    assert run(verification({}), scope="unknown")[0].status == CheckStatus.ERROR
    assert run(verification())[0].status == CheckStatus.ERROR


def test_explicit_scope_controls_multiline_presence():
    v = verification({"signature": None}, {"signature": "S"})
    per_row = required(v, fields=("signature",))
    assert [r.status for r in per_row] == [CheckStatus.FLAGGED, CheckStatus.PASS]
    assert [r.verification_line_id for r in per_row] == [1, 2]
    whole, = required(v, fields=("signature",), scope="any_row")
    assert whole.status == CheckStatus.PASS
    assert whole.verification_line_id is None


def test_image_reference_present_does_not_require_file_access():
    result, = image(verification({"image_reference": "/nonexistent/synthetic.png"}))
    assert result.status == CheckStatus.PASS
    assert result.field == "image_reference"
    assert "present" in result.reason


@pytest.mark.parametrize("values", [{}, {"image_reference": None}, {"image_reference": " "}])
def test_image_reference_missing_under_confirmed_requirement(values):
    result, = image(verification(values))
    assert result.status == CheckStatus.FLAGGED
    assert "image_reference" in result.reason


def test_image_requires_both_requirement_and_scope_confirmation():
    v = verification({})
    assert image_check(v, image_required_confirmed=True)[0].status == CheckStatus.NOT_CHECKED
    assert image_check(v, confirmed_scope="any_row")[0].status == CheckStatus.NOT_CHECKED


def test_supplier_does_not_infer_identity_from_candidate_fields():
    result, = supplier_check(verification({"counterparty": "synthetic-supplier",
                                          "supplier_id": "synthetic-id"}))
    assert result.status == CheckStatus.NOT_CHECKED
    assert "supplier identifier" in result.reason
    assert "reference data" in result.reason


def test_attestation_requires_confirmed_rules_and_reference_data():
    result, = attestation_check(verification({"attestation": "synthetic-person"}))
    assert result.status == CheckStatus.NOT_CHECKED
    assert "authorization rules" in result.reason
    assert "reference data" in result.reason


def test_multiple_flag_reasons_survive_across_fields_rows_and_rules():
    v = verification({"signature": None, "attestation": None},
                     {"signature": "S", "attestation": None})
    # Collect independent results here; no Detection Engine is implemented.
    results = (*required(v), *image(v, scope="any_row"))
    flags = [r for r in results if r.status == CheckStatus.FLAGGED]
    assert [(r.check_type, r.field, r.verification_line_id) for r in flags] == [
        ("required_fields_check", "signature", 1),
        ("required_fields_check", "attestation", 1),
        ("required_fields_check", "attestation", 2),
        ("image_check", "image_reference", None),
    ]
    assert all(r.reason for r in flags)


def test_malformed_cell_returns_error_and_later_rows_still_checked():
    v = verification({"image_reference": []}, {"image_reference": "synthetic.png"})
    results = image(v)
    assert [r.status for r in results] == [CheckStatus.ERROR, CheckStatus.PASS]
    assert [r.row_position for r in results] == [0, 1]


def test_duplicate_column_returns_error_without_losing_other_fields():
    v = verification({"signature": "S", "attestation": None})
    v.rows = pd.concat([v.rows, v.rows[["signature"]]], axis=1)
    results = required(v)
    assert [r.status for r in results] == [CheckStatus.ERROR, CheckStatus.FLAGGED]


def test_missing_line_identity_is_error_for_row_scope():
    v = verification({"verification_line_id": None, "image_reference": None})
    result, = image(v)
    assert result.status == CheckStatus.ERROR
    assert result.row_position == 0


def test_any_row_missing_or_uninterpretable_does_not_pass():
    assert image(verification({}), scope="any_row")[0].status == CheckStatus.FLAGGED
    assert image(verification({"image_reference": []}), scope="any_row")[0].status == CheckStatus.ERROR


def test_rules_preserve_input_and_do_not_store_or_overwrite_results():
    v = verification({"signature": None, "attestation": "A", "image_reference": None})
    before = v.rows.copy(deep=True)
    original_results = required(v)
    image(v)
    attestation_check(v)
    supplier_check(v)
    assert required(v) == original_results
    assert v.verification_id == "synthetic-001"
    pd.testing.assert_frame_equal(v.rows, before)
