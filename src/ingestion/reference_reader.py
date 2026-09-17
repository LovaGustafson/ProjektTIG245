"""Load local reference tables generically; never interpret register business rules."""

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

from src.ingestion._local_file import local_path
from src.ingestion.excel_reader import read_excel
from src.models.ingestion import ReadStatus


RegisterType = Literal["supplier_procurement", "attestation"]


@dataclass(frozen=True, eq=False)
class ReferenceReadResult:
    register_type: RegisterType
    path: Path | None
    status: ReadStatus
    reason: str
    data: pd.DataFrame | None = field(default=None, repr=False)
    observed_columns: tuple[object, ...] = ()
    schema_status: str = "UNCONFIRMED"
    todos: tuple[str, ...] = ()


def _read_csv(path: Path, delimiter: str, encoding: str) -> pd.DataFrame:
    """Preserve text, duplicate/blank headers, and blank records without inference."""
    with path.open("r", encoding=encoding, newline="") as stream:
        records = csv.reader(stream, delimiter=delimiter, strict=True)
        headers = next(records, None)
        if not headers:
            raise ValueError("CSV has no header record")
        rows = []
        for record in records:
            # Preserve an empty physical record as an empty table row.
            if not record:
                record = [""] * len(headers)
            if len(record) != len(headers):
                raise ValueError(f"Malformed CSV near line {records.line_num}: "
                                 f"expected {len(headers)} cells, found {len(record)}")
            rows.append(record)
    return pd.DataFrame(rows, columns=pd.Index(headers, dtype=object), dtype=object)


def read_reference(
    reference: object, *, register_type: RegisterType,
    sheet_name: str | int = 0, delimiter: str = ",", encoding: str = "utf-8-sig",
    header_aliases=None, header_minimum_fields=3,
) -> ReferenceReadResult:
    """Load an .xlsx worksheet or CSV as an independent, uninterpreted table.

    Assumptions/TODO: confirm register layouts with AK. The first record is the
    header. Excel defaults to worksheet 0, with explicit name/index selection;
    sheet_name does not apply to CSV. CSV defaults to comma and UTF-8 (optional
    BOM), with explicit delimiter/encoding overrides. No format sniffing occurs.
    Inconsistent CSV widths and broken quoting are file-format errors, not
    business-schema validation. Empty/header-only Excel sheets and header-only
    CSVs are loaded without inventing required columns or row counts.

    LOADED only means file ingestion succeeded. schema_status stays UNCONFIRMED
    even when familiar column names are observed. This never confirms supplier
    identity, register completeness, authorization, or matching rules.
    """
    if register_type not in ("supplier_procurement", "attestation"):
        raise ValueError("register_type must be supplier_procurement or attestation")
    todos = ("TODO / awaiting AK: confirm required columns, header layout and register schema",)
    if register_type == "supplier_procurement":
        todos += ("TODO / awaiting AK: supplier identifier and procurement matching rules; "
                  "counterparty is not assumed to identify the supplier",)
    else:
        todos += ("TODO / awaiting AK: Sign/Att meanings, attestation flow and authorization rules",)

    def result(path, status, reason, data=None):
        return ReferenceReadResult(register_type, path, status, reason, data,
                                   tuple(data.columns) if data is not None else (), todos=todos)

    try:
        path = local_path(reference)
    except (TypeError, ValueError) as exc:
        return result(None, ReadStatus.UNSUPPORTED, str(exc))
    if path is None:
        return result(None, ReadStatus.MISSING_REFERENCE, "No reference-register path supplied")
    if path.suffix.lower() not in (".xlsx", ".csv"):
        return result(path, ReadStatus.UNSUPPORTED, "Only .xlsx and .csv reference files are supported")
    try:
        if path.suffix.lower() == ".xlsx":
            data = read_excel(path, sheet_name=sheet_name, header_aliases=header_aliases,
                              header_minimum_fields=header_minimum_fields)
        else:
            data = _read_csv(path, delimiter, encoding)
    except FileNotFoundError:
        return result(path, ReadStatus.MISSING_FILE, f"Reference file not found: {path}")
    except (OSError, ValueError, TypeError, LookupError, csv.Error) as exc:
        return result(path, ReadStatus.UNREADABLE,
                      f"Cannot load reference file ({type(exc).__name__}): {exc}")
    return result(path, ReadStatus.LOADED,
                  "Reference table loaded generically; schema remains unconfirmed by AK", data)


def read_supplier_register(reference: object, **read_options) -> ReferenceReadResult:
    """Load a supplier/procurement register; options are those of read_reference."""
    return read_reference(reference, register_type="supplier_procurement", **read_options)


def read_attestation_register(reference: object, **read_options) -> ReferenceReadResult:
    """Load an attestation register; options are those of read_reference."""
    return read_reference(reference, register_type="attestation", **read_options)
