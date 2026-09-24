"""Select a separate manual sample after analysis of all relevant verifications."""

from collections.abc import Iterable, Mapping
from copy import deepcopy
from pathlib import Path

import pandas as pd
import yaml

from src.models.verification import Verification


DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config/settings.yaml"


def load_sample_interval(settings_path=DEFAULT_SETTINGS_PATH):
    with Path(settings_path).open(encoding="utf-8") as settings_file:
        settings = yaml.safe_load(settings_file)
    interval = settings.get("manual_sample_interval") if isinstance(settings, Mapping) else None
    if type(interval) is not int or interval <= 0:
        raise ValueError("manual_sample_interval must be a positive integer")
    return interval


def create_manual_sample(
    analyzed_verifications: Iterable[Verification], *,
    settings_path: str | Path = DEFAULT_SETTINGS_PATH,
    interval: int | None = None,
) -> list[Verification]:
    """Return copies at positions interval, 2*interval, ... in supplied order.

    The caller must supply every relevant, already-analyzed verification once,
    normally in the builder's first-appearance order. Analysis completion is a
    caller precondition: Verification has no analysis-completion marker.
    src/pipeline.py completes detection for all eligible verifications first.
    The iterable is fully consumed before selecting any verifications.

    No sorting, filtering by detection outcome, or row-level selection occurs.
    Empty inputs and inputs shorter than the interval produce an empty list.
    Selected rows (including mutable object cells) are copied independently.
    Invalid business values are retained without interpretation.

    The confirmed interval is 20, as configured in the repository. See
    PROJECT_SPEC.md, "13. Manual sampling". Customer requirements for selection
    evidence/documentation remain open (OPEN_QUESTIONS.md Q2); the interval is
    not an unresolved decision.
    """
    interval = load_sample_interval(settings_path) if interval is None else interval
    if type(interval) is not int or interval <= 0:
        raise ValueError("manual_sample_interval must be a positive integer")

    verifications = list(analyzed_verifications)
    if any(not isinstance(item, Verification) for item in verifications):
        raise TypeError("analyzed_verifications must contain Verification objects, not Excel rows")

    sample = []
    for verification in verifications[interval - 1::interval]:
        rows = verification.rows.copy(deep=True)
        # pandas does not recursively copy objects stored inside object columns.
        for column_position, dtype in enumerate(rows.dtypes):
            if pd.api.types.is_object_dtype(dtype):
                for row_position in range(len(rows)):
                    rows.iat[row_position, column_position] = deepcopy(
                        rows.iat[row_position, column_position]
                    )
        sample.append(Verification(deepcopy(verification.verification_id), rows))
    return sample
