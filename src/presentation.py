"""Shared Swedish presentation of existing evidence; no business decisions."""
import pandas as pd
from src.mapping.column_mapper import COLUMN_MAPPING

SOURCE_NAMES = {internal: source for source, internal in COLUMN_MAPPING.items()}


def validation_message(error):
    name = SOURCE_NAMES.get(error.field, error.field)
    templates = {
        'missing_column': f"Kolumnen '{name}' saknas i den uppladdade filen.",
        'duplicate_column': f"Kolumnen '{name}' förekommer flera gånger i den uppladdade filen.",
        'missing_value': f"Värdet i '{name}' saknas på raden.",
        'invalid_value': f"Värdet i '{name}' har inte ett giltigt format enligt valideringen.",
        'duplicate_identity': 'Kombinationen av verifikationsnummer och radnummer förekommer flera gånger.',
    }
    return templates.get(error.code, f"Ett valideringsfel har rapporterats för '{name}'.")


def cell(data, position, field):
    if list(data.columns).count(field) != 1:
        return None
    value = data.iloc[position][field]
    return None if pd.api.types.is_scalar(value) and pd.isna(value) else value


def validation_records(data, validation):
    schema = validation.schema_errors
    records = []
    for error in schema:
        records.append(dict(scope='Fil', row_position=None, verification_id=None,
                            verification_line_id=None, field=error.field, code=error.code,
                            message=validation_message(error)))
    for row in validation.rows:
        for error in row.validation_errors:
            if error in schema:
                continue
            records.append(dict(scope='Rad', row_position=row.row_position,
                verification_id=cell(data, row.row_position, 'verification_id'),
                verification_line_id=cell(data, row.row_position, 'verification_line_id'),
                field=error.field, code=error.code, message=validation_message(error)))
    return records


def summary_counts(data, validation, results):
    return dict(analyzed_verifications=len(results),
                flagged_verifications=sum(bool(r.flag_reasons) for r in results),
                validation_errors=len(validation_records(data, validation)),
                not_checked_results=sum(c.status == 'NOT_CHECKED' for r in results for c in r.checks))


def context_fields(rows):
    """Keep all distinct supplied values, without choosing a canonical header/date.

    Multiple values are displayed on separate lines; missing fields stay blank.
    Complete original rows remain available separately.
    """
    output = {}
    for field in ('verification_date', 'header_text', 'amount', 'account'):
        values = []
        for position in range(len(rows)):
            value = cell(rows, position, field)
            if value is not None and str(value) not in [str(v) for v in values]:
                values.append(value)
        output[field] = values[0] if len(values) == 1 else '\n'.join(map(str, values)) if values else None
    return output


def check_message(check):
    """Translate known rule text without changing the original reason or status.

    TODO: custom rules need a translation catalog; unknown reasons are retained.
    CheckResult has no machine-readable reason code, so exports leave code blank.
    """
    reason = check.reason
    if reason.startswith('TODO / awaiting AK confirmation:'):
        details = {
            'required_fields_check': 'obligatoriska uppgifter och kontrollens omfattning',
            'image_check': 'bildreferensens betydelse, krav och kontrollens omfattning',
            'supplier_check': 'leverantörsidentifiering, registerstruktur och referensdata; motpart antas inte vara leverantör',
            'attestation_check': 'betydelsen av Sign/Att, attestflöde, behörighetsregler och referensdata',
        }
        return f"Kontrollen väntar på AK:s bekräftelse av {details.get(check.check_type, 'kontrollens förutsättningar')}."
    if reason.startswith('Missing required information: '):
        return f"Obligatorisk information saknas: {reason.split(': ', 1)[1]}."
    replacements = {
        'Cannot check presence: no row data available': 'Närvaro kan inte kontrolleras eftersom raddata saknas.',
        'Unsupported presence scope': 'Kontrollens omfattning stöds inte.',
        'No required information checks configured': 'Inga kontroller av obligatorisk information har konfigurerats.',
        'Required fields must be a sequence of nonblank field names': 'Obligatoriska fält måste anges som en lista med ifyllda fältnamn.',
        'Cannot attribute row check: missing or ambiguous verification_line_id': 'Radkontrollen kan inte kopplas till ett entydigt radnummer.',
        'Cannot attribute row check: missing verification_line_id': 'Radkontrollen saknar radnummer.',
    }
    if reason in replacements:
        return replacements[reason]
    if reason.startswith('Ambiguous duplicate column: '):
        return f"Kolumnen '{check.field}' förekommer flera gånger och är tvetydig."
    for suffix, translation in [(': information present on at least one row', 'Information finns på minst en rad'),
                                (': information present on row', 'Information finns på raden'),
                                (': presence could not be determined', 'Det gick inte att avgöra om information finns')]:
        if reason.endswith(suffix):
            return f'{translation}: {check.field}.'
    if reason.startswith('Rule ') and ' failed (' in reason:
        return f'Kontrollen {check.check_type} kunde inte genomföras på grund av ett tekniskt fel.'
    return reason
