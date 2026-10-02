"""Explicit, confirmed presentation classifications; never matching or base filtering."""
import pandas as pd
import yaml

from src.ingestion.contract_reader import organization_key
from src.supplier_matching.analysis import SupplierAnalysis
from src.supplier_matching.extraction import extract_supplier
from src.supplier_matching.normalization import normalize_supplier


def load_view_rules(settings_path):
    with open(settings_path, encoding='utf-8') as stream:
        config = yaml.safe_load(stream) or {}
    rules = config.get('supplier_view_rules', [])
    if not isinstance(rules, list):
        raise ValueError('supplier_view_rules must be a list')
    validated, ids = [], set()
    for rule in rules:
        if (not isinstance(rule, dict) or
                any(not isinstance(rule.get(field), str) or not rule[field].strip()
                    for field in ('id', 'match_field', 'value', 'classification', 'reason')) or
                type(rule.get('confirmed')) is not bool):
            raise ValueError('Each supplier view rule needs id, match_field, value, classification, reason and confirmed')
        if rule['id'] in ids:
            raise ValueError('Supplier view rule IDs must be unique')
        ids.add(rule['id'])
        if rule['match_field'] not in ('organization_number', 'supplier_name'):
            raise ValueError('View rules support organization_number or supplier_name, never counterparty')
        if rule['classification'] not in ('INTERNAL', 'NOT_RELEVANT', 'EXTERNAL'):
            raise ValueError('Invalid supplier view classification')
        normalize = organization_key if rule['match_field'] == 'organization_number' else normalize_supplier
        key = normalize(rule['value'])
        if not key:
            raise ValueError('Supplier view rule must have a usable exact comparison key')
        validated.append({**rule, 'comparison_key': key})
    return tuple(validated)


def classify_supplier_view(data, analysis, rules):
    """Unclassified/conflicting rows stay visible. Configured names match exactly.

    Organization rules require an existing STRONG_MATCH. Name rules use only
    the existing Huvudtext extraction and normalization, without fuzzy inference.
    Rule confirmation is explicit configuration evidence, not inferred from a name.
    """
    matches = (analysis.rows.set_index('source_row_position')
               if analysis is not None and analysis.registry.available else pd.DataFrame())
    records = []
    for position, row in data.iterrows():
        raw = extract_supplier(row['header_text']) if list(data.columns).count('header_text') == 1 else None
        name = normalize_supplier(raw)
        match = matches.loc[position] if position in matches.index else None
        org = (match['matched_organization_number'] if match is not None and
               match['supplier_match_status'] == 'STRONG_MATCH' else None)
        hits = [rule for rule in rules if rule['confirmed'] and rule['comparison_key'] ==
                (org if rule['match_field'] == 'organization_number' else name)]
        classifications = {rule['classification'] for rule in hits}
        classification = (next(iter(classifications)) if len(classifications) == 1 else
                          'CONFLICT' if classifications else 'UNCLASSIFIED')
        records.append(dict(source_row_position=position, supplier_text_raw=raw, supplier_normalized=name,
            organization_number=org, classification=classification,
            excluded_from_view=classification in ('INTERNAL', 'NOT_RELEVANT'),
            rule_ids='; '.join(rule['id'] for rule in hits),
            match_fields='; '.join(rule['match_field'] for rule in hits),
            configured_values='; '.join(rule['value'] for rule in hits),
            reason=('Motstridiga bekräftade vyregler; raden visas för granskning. ' if classification == 'CONFLICT' else '') +
                   ('; '.join(rule['reason'] for rule in hits) if hits else 'Ingen bekräftad klassificeringsregel träffade.')))
    return pd.DataFrame(records, columns=[
        'source_row_position', 'supplier_text_raw', 'supplier_normalized', 'organization_number',
        'classification', 'excluded_from_view', 'rule_ids', 'match_fields', 'configured_values', 'reason',
    ])


def visible_supplier_analysis(analysis, classification):
    """A scoped presentation copy. The full analysis and all exports remain intact."""
    if analysis is None or classification is None or classification.empty:
        return analysis
    excluded = classification.loc[classification['excluded_from_view'], 'source_row_position']
    def visible(table):
        return table.loc[~table['source_row_position'].isin(excluded)].copy(deep=True)
    return SupplierAnalysis(analysis.registry, visible(analysis.rows),
                            visible(analysis.candidates), visible(analysis.contracts))
