"""Rename source columns only; uncertain field meanings are not interpreted."""

import pandas as pd

COLUMN_MAPPING = dict(zip(
    'Vernr Vrad Verdatum Utfall Konto Ansvar Motp Inv Proj Aktiv Ksansv Mm Pg Vertyp Huvudtext Radtext Bild Sign Att'.split(),
    'verification_id verification_line_id verification_date amount account responsibility counterparty investment project activity cost_responsibility vat_code posting_group verification_type header_text line_text image_reference signature attestation'.split(),
))

# Explicit source aliases, without guessing the meaning of other fields.
COLUMN_ALIASES = {**COLUMN_MAPPING, 'VerDat': 'verification_date',
                  'VerDatum': 'verification_date'}


def map_columns(data: pd.DataFrame) -> pd.DataFrame:
    """Preserve values, unknown columns and duplicate headers for validation.

    TODO: AK must confirm Mm/Pg/Sign/Att/Ksansv/Bild meanings. These are only
    the standardized labels specified in PROJECT_SPEC.md, not interpretations.
    """
    return data.rename(columns=lambda name: COLUMN_ALIASES.get(name.strip(), name.strip())
                       if isinstance(name, str) else name).copy(deep=True)
