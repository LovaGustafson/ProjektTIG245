"""Manual sampling tests use only synthetic verifications and configuration."""

import pandas as pd
import pytest

from src.models.verification import Verification
from src.sampling.manual_sample import create_manual_sample


def verifications(count):
    return [Verification(str(i), pd.DataFrame({
        "verification_id": [str(i)] * (i % 3 + 1),
        "verification_line_id": range(1, i % 3 + 2),
        "amount": ["invalid synthetic amount"] * (i % 3 + 1),
        "header_text": [f"Syntetisk leverantör {i} AB Prelb 1"] * (i % 3 + 1),
    })) for i in range(1, count + 1)]


def settings(tmp_path, interval):
    path = tmp_path / "settings.yaml"
    path.write_text(f"manual_sample_interval: {interval}\n", encoding="utf-8")
    return path


def test_repository_baseline_interval():
    result = create_manual_sample(verifications(65))
    assert [v.verification_id for v in result] == ["20", "40", "60"]


def test_sampling_selects_complete_verifications():
    source = verifications(40)
    result = create_manual_sample(source)
    for selected, original in zip(result, [source[19], source[39]]):
        pd.testing.assert_frame_equal(selected.rows, original.rows)
    assert len(result) == 2


@pytest.mark.parametrize("count", [0, 1, 19])
def test_empty_and_smaller_datasets(count):
    assert create_manual_sample(verifications(count)) == []


@pytest.mark.parametrize("interval", [1, 3, 7])
def test_configurable_interval(tmp_path, interval):
    result = create_manual_sample(verifications(15), settings_path=settings(tmp_path, interval))
    assert [v.verification_id for v in result] == [str(i) for i in range(interval, 16, interval)]


def test_input_unchanged_and_sample_independent(tmp_path):
    source = verifications(2)
    source[1].rows["notes"] = [{"values": ["synthetic"]} for _ in range(len(source[1].rows))]
    source[1].rows.index.name = "source_row"
    before = source[1].rows.copy(deep=True)
    result = create_manual_sample(source, settings_path=settings(tmp_path, 2))
    assert len(source) == 2
    assert result is not source
    assert result[0] is not source[1]
    pd.testing.assert_frame_equal(source[1].rows, before)
    result[0].verification_id = "edited"
    result[0].rows.loc[0, "amount"] = "edited"
    result[0].rows.iloc[0]["notes"]["values"].append("edited")
    assert source[1].verification_id == "2"
    assert source[1].rows.iloc[0]["notes"] == {"values": ["synthetic"]}
    pd.testing.assert_frame_equal(source[1].rows, before)


def test_preserves_supplied_order_and_consumes_all_input(tmp_path):
    source = verifications(5)[::-1]
    visited = []

    def analyzed_input():
        for verification in source:
            visited.append(verification.verification_id)
            yield verification

    result = create_manual_sample(analyzed_input(), settings_path=settings(tmp_path, 2))
    assert visited == ["5", "4", "3", "2", "1"]
    assert [v.verification_id for v in result] == ["4", "2"]


@pytest.mark.parametrize("interval", [0, -1, "true", "null", "2.5", "'3'"])
def test_invalid_configuration(tmp_path, interval):
    with pytest.raises(ValueError, match="positive integer"):
        create_manual_sample([], settings_path=settings(tmp_path, interval))


def test_missing_interval(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="manual_sample_interval"):
        create_manual_sample([], settings_path=path)


def test_excel_rows_are_not_accepted():
    with pytest.raises(TypeError, match="Verification objects"):
        create_manual_sample([{"verification_id": "1"}])
