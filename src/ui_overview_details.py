"""Read-only drill-down tables linked through existing source-occurrence evidence."""
from dataclasses import asdict
from numbers import Integral

import pandas as pd
from src.supplier_matching.view_scope import visible_supplier_analysis


def source_rows(result, positions):
    """Retain source headers/values, adding collision-safe provenance and reasons.

    Pipeline indexes identify parsed source occurrences, even for repeated or
    missing business IDs. No selection rule or normalization is rerun here.
    """
    positions = list(positions)
    rows = result.original_data.loc[positions].copy(deep=True)
    context = result.source_context or {}
    header = context.get('source_header_row')
    evidence = {
        'source_row_position': positions,
        'source_excel_row': [header + 1 + int(p) if header is not None else None for p in positions],
        'source_sheet': [context.get('source_sheet')] * len(positions),
        'exclusion_reason': [result.filtering.reasons[int(p)] for p in positions],
    }
    # Keep source columns unchanged, as in existing row enrichment/export code.
    for field, values in reversed(list(evidence.items())):
        name = field
        while name in rows.columns:
            name = '_' + name
        rows.insert(0, name, values)
    return rows


def reason_counts(evidence, fields):
    """Count exact backend reasons at the evidence's own unit, including null fields."""
    return evidence.groupby(fields, dropna=False, sort=False).size().reset_index(name='Antal')


def detection_details(result, status):
    """One table row per check, plus the distinct source occurrences it refers to.

    Detection positions are local to a verification, never source positions.
    Missing positions show group context; line IDs alone cannot identify rows.
    Invalid positions remain visible without an invented source-row link.
    """
    checks, positions = [], set()
    for verification, detection in zip(result.verifications, result.detection_results):
        for check in detection.checks:
            if check.status != status:
                continue
            local = check.row_position
            if local is None:
                linked = list(verification.rows.index)
                scope = 'Verifikationskontext – ingen enskild källrad angiven'
            elif isinstance(local, Integral) and not isinstance(local, bool) and 0 <= local < len(verification.rows):
                linked = [verification.rows.index[local]]
                scope = 'Enskild källrad via position inom verifikationen'
            else:
                linked = []
                scope = 'Radpositionen kan inte kopplas till en källrad'
            checks.append({**asdict(check), 'source_row_positions': linked, 'source_link': scope})
            positions.update(linked)
    evidence = pd.DataFrame(checks, columns=[
        'verification_id', 'check_type', 'status', 'reason', 'verification_line_id',
        'field', 'row_position', 'source_row_positions', 'source_link',
    ])
    return evidence, source_rows(result, sorted(positions))


def supplier_details(result, status):
    """Subset each evidence table by retained source position, never supplier/verification ID."""
    analysis = visible_supplier_analysis(result.supplier_analysis, result.supplier_view)
    matches = analysis.rows.loc[analysis.rows['supplier_match_status'] == status].copy(deep=True)
    positions = matches['source_row_position'].tolist()
    candidates = analysis.candidates.loc[analysis.candidates['source_row_position'].isin(positions)].copy(deep=True)
    contracts = analysis.contracts.loc[analysis.contracts['source_row_position'].isin(positions)].copy(deep=True)
    return matches, candidates, contracts, source_rows(result, positions)


def contract_details(result, status):
    analysis = result.supplier_analysis
    contracts = analysis.contracts.loc[analysis.contracts['contract_period_status'] == status].copy(deep=True)
    positions = contracts['source_row_position'].tolist()
    # A source occurrence is displayed once here, even if it has several comparisons.
    rows = source_rows(result, result.filtering.cleaned_data.index[
        result.filtering.cleaned_data.index.isin(positions)])
    return contracts, rows


def exclusion_details(result, rule):
    kind, _, expression = rule.partition(': ')
    positions = result.filtering.rule_details[kind][expression]
    return source_rows(result, result.original_data.iloc[positions].index)


def verification_details(result, population='all'):
    """Use existing groups and sample membership, preserving population order."""
    sampled_positions = {p for v in result.manual_sample for p in v.rows.index}
    flagged_positions = {p for v, d in zip(result.verifications, result.detection_results)
                         if d.flag_reasons for p in v.rows.index}
    groups, positions = [], []
    for number, verification in enumerate(result.verifications, 1):
        linked = list(verification.rows.index)
        selected = any(p in sampled_positions for p in linked)
        if population == 'selected' and not selected:
            continue
        if population == 'remaining' and selected:
            continue
        if population == 'flagged' and not any(p in flagged_positions for p in linked):
            continue
        groups.append({'population_position': number, 'verification_id': verification.verification_id,
                       'row_count': len(linked), 'source_row_positions': linked})
        positions.extend(linked)
    return pd.DataFrame(groups, columns=[
        'population_position', 'verification_id', 'row_count', 'source_row_positions',
    ]), source_rows(result, positions)
