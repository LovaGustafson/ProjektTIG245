"""Read source Excel data into an independent in-memory DataFrame."""

from os import PathLike
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook


class ExcelReadError(ValueError):
    """The supplied file could not be parsed as an Excel workbook."""


def read_excel(
    path: str | PathLike[str], *, sheet_name: str | int = 0
) -> pd.DataFrame:
    """Read every row and column of one .xlsx worksheet without writing to disk.

    TODO: confirm the source worksheet and header layout. For now, the first
    worksheet is the default, and the first row contains column names. Select
    another worksheet by name or zero-based index. Sheets are never combined.

    Original headers (including duplicates), blank cells, text identifiers,
    Excel error values and formula expressions are retained. Excel-native
    dates/numbers are decoded by openpyxl; display formatting is not data.
    Formulas are not evaluated. No business validation or transformation runs.

    Returns a new object-typed DataFrame, independent of the source file.
    Missing files, directories and permissions raise their standard OSError
    subclasses. Unsupported extensions or sheet selectors raise ValueError
    (TypeError for invalid selector types). Unreadable workbooks raise
    ExcelReadError with the underlying exception preserved as the cause.
    """
    source = Path(path)
    if source.suffix.lower() != ".xlsx":
        raise ValueError(f"Expected an .xlsx file: {source}")
    if isinstance(sheet_name, bool) or not isinstance(sheet_name, (str, int)):
        raise TypeError("sheet_name must be a worksheet name or zero-based index")

    # A binary read-only handle prevents this module from writing to the source.
    with source.open("rb") as stream:
        workbook = None
        try:
            workbook = load_workbook(stream, read_only=True, data_only=False)
            names = workbook.sheetnames
            if isinstance(sheet_name, int):
                if sheet_name < 0 or sheet_name >= len(names):
                    raise ValueError(f"Worksheet index {sheet_name} does not exist")
                selected = names[sheet_name]
            else:
                selected = sheet_name
                if selected not in names:
                    raise ValueError(f"Worksheet {selected!r} does not exist")

            rows = workbook[selected].iter_rows(values_only=True)
            headers = next(rows, None)
            if headers is None:
                return pd.DataFrame(dtype=object)
            return pd.DataFrame(
                rows, columns=pd.Index(headers, dtype=object), dtype=object
            )
        except OSError:
            raise
        except Exception as exc:
            # Workbook parsing can fail with ZIP, XML or engine-specific errors.
            # Keep this boundary local to ingestion and retain the original cause.
            raise ExcelReadError(
                f"Could not read .xlsx file {source} (sheet {sheet_name!r}): {exc}"
            ) from exc
        finally:
            if workbook is not None:
                workbook.close()
