"""Exact sampling classifications and quota evidence, separate from view exclusions."""
import pandas as pd
import yaml

from src.supplier_matching.view_scope import validate_classification_rules

CLASSIFICATION_LABELS = {'INTERNAL': 'Bekräftat intern', 'EXTERNAL': 'Bekräftat extern',
                         'UNCLASSIFIED': 'Oklassificerad', 'CONFLICT': 'Klassificeringskonflikt'}
QUOTA_EXPLANATION = (
    'Högst 5 % av det faktiska stickprovet får vara bekräftat interna verifikationer '
    '(avrundat nedåt; inga interna under 20 valda). Oklassificerade är inte bekräftat externa. '
    'Den faktiska interna andelen kan vara högre eftersom oklassificerade leverantörer kan vara interna.'
)
NO_INTERNAL_RULES = ('Inga interna klassificeringsregler är aktiva. 5 %-begränsningen kan därför '
                     'inte garantera den faktiska andelen interna leverantörer.')
RULE_COLUMNS = ['id', 'match_field', 'value', 'classification', 'reason', 'confirmed', 'comparison_key']


def sampling_rules(rules):
    validated = validate_classification_rules(list(rules))
    if any(rule['classification'] not in ('INTERNAL', 'EXTERNAL') for rule in validated):
        raise ValueError('Sampling rules support INTERNAL or EXTERNAL classifications only')
    return validated


def load_sampling_rules(settings_path):
    with open(settings_path, encoding='utf-8') as stream:
        config = yaml.safe_load(stream) or {}
    rules = config.get('sampling_supplier_rules', [])
    if not isinstance(rules, list):
        raise ValueError('sampling_supplier_rules must be a list')
    return sampling_rules(rules)


def classify_identities(identities, rules):
    """Use existing extracted names/strong organization numbers, never candidate guesses."""
    records = []
    for row in identities.to_dict('records'):
        hits = [rule for rule in rules if rule['confirmed'] and rule['comparison_key'] == (
            row['matched_organization_number'] if rule['match_field'] == 'organization_number'
            and row['identity_basis'] == 'STRONG_MATCH_ORG' else
            row['supplier_normalized'] if rule['match_field'] == 'supplier_name' else None)]
        classes = {rule['classification'] for rule in hits}
        classification = (next(iter(classes)) if len(classes) == 1 else
                          'CONFLICT' if classes else 'UNCLASSIFIED')
        records.append({**row, 'classification': classification,
            'rule_ids': '; '.join(rule['id'] for rule in hits),
            'classification_reason': ('Motstridiga bekräftade klassificeringsregler. ' if len(classes) > 1 else '') +
                ('; '.join(rule['reason'] for rule in hits) or 'Ingen bekräftad klassificeringsregel träffade.')})
    return pd.DataFrame(records, columns=[*identities.columns, 'classification', 'rule_ids', 'classification_reason'])


def verification_classification(rows):
    classes = set(rows['classification'])
    if 'CONFLICT' in classes or {'INTERNAL', 'EXTERNAL'} <= classes:
        return 'CONFLICT', 'Motstridiga bekräftade klassificeringar; verifikationen får inte ingå i stickprovet.'
    if 'INTERNAL' in classes:
        return 'INTERNAL', 'Bekräftat intern; eventuella oklassificerade rader ändrar inte klassificeringen.'
    if classes == {'EXTERNAL'}:
        return 'EXTERNAL', 'Samtliga rader är bekräftat externa.'
    return 'UNCLASSIFIED', 'Minst en rad saknar bekräftad klassificering; verifikationen räknas inte som extern.'


def enforce_final_quota(chosen, decisions):
    """Remove latest selected internal occurrences until the final denominator is safe."""
    internal = [p for p in chosen if decisions[p - 1]['supplier_classification'] == 'INTERNAL']
    removed = set()
    while len(internal) > (len(chosen) - len(removed)) // 20:
        position = internal.pop()
        removed.add(position)
        before = len(chosen) - len(removed) + 1
        decisions[position - 1].update(decision='INTERNAL_QUOTA_REMOVED', selection_reason=(
            f'Borttagen vid slutkontroll av internkvoten: {before} valda tillät högst {before // 20} interna. '
            'Senast valda interna tas bort först. Ingen ny dragning eller återgång görs.'))
    for decision in decisions:
        if decision['decision'] == 'DUPLICATE_SUPPLIER' and decision['duplicate_of_population_position'] in removed:
            decision['selection_reason'] = ('Leverantören hade redan valts vid prövningen. Det tidigare valet '
                'togs senare bort vid slutkontroll av internkvoten; kandidaten prövas inte igen.')
    return [position for position in chosen if position not in removed]
