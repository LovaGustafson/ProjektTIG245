"""Select a separate manual sample after analysis of all relevant verifications."""

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from secrets import randbits

import pandas as pd
import yaml

from src.models.verification import Verification
from src.sampling.classification import (
    load_sampling_rules, sampling_rules, classify_identities, verification_classification,
    enforce_final_quota, QUOTA_EXPLANATION, NO_INTERNAL_RULES,
)
from src.supplier_matching.extraction import extract_supplier
from src.supplier_matching.normalization import normalize_supplier


DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config/settings.yaml"
SAMPLING_METHODS = {'systematic': 'Var 20:e (stegvis)', 'randomized': 'Slumpmässig'}
RANDOM_SAMPLE_SIZE = 20


def sampling_timestamp():
    return datetime.now(timezone.utc).isoformat()


def new_sample_seed(previous=None):
    seed = randbits(128)
    while seed == previous:
        seed = randbits(128)
    return seed


def load_sample_interval(settings_path=DEFAULT_SETTINGS_PATH):
    with Path(settings_path).open(encoding="utf-8") as settings_file:
        settings = yaml.safe_load(settings_file)
    interval = settings.get("manual_sample_interval") if isinstance(settings, Mapping) else None
    if type(interval) is not int or interval <= 0:
        raise ValueError("manual_sample_interval must be a positive integer")
    return interval


@dataclass
class SamplingResult:
    sample: list[Verification]
    target_size: int
    decisions: pd.DataFrame
    identity_rows: pd.DataFrame
    method: str = 'systematic'
    interval: int | None = None
    seed: int | None = None
    generated_at: str = field(default_factory=lambda: sampling_timestamp())
    classification_rows: pd.DataFrame = field(default_factory=pd.DataFrame)
    classification_rules: tuple = ()

    @property
    def classification_fingerprint(self):
        payload = (json.dumps(self.classification_rules, sort_keys=True, ensure_ascii=False)
                   + self.classification_rows.to_json(orient='split', force_ascii=False))
        return sha256(payload.encode('utf-8')).hexdigest()

    @property
    def internal_rules_active(self):
        return sum(rule['confirmed'] and rule['classification'] == 'INTERNAL' for rule in self.classification_rules)

    @property
    def classification_counts(self):
        selected = self.decisions.loc[self.decisions.decision.eq('SELECTED'), 'supplier_classification']
        return {status: int(selected.eq(status).sum()) for status in ('INTERNAL', 'EXTERNAL', 'UNCLASSIFIED')}

    @property
    def quota_rejections(self):
        return int(self.decisions.decision.isin(['INTERNAL_QUOTA', 'INTERNAL_QUOTA_REMOVED']).sum())

    @property
    def conflict_rejections(self):
        return int(self.decisions.decision.eq('CLASSIFICATION_CONFLICT').sum())

    @property
    def quota_metadata(self):
        counts = self.classification_counts
        return {
            'Antal bekräftat interna': counts['INTERNAL'],
            'Antal bekräftat externa': counts['EXTERNAL'],
            'Antal oklassificerade': counts['UNCLASSIFIED'],
            'Antal bortval på grund av kvotbegränsning': self.quota_rejections,
            'Antal bortval på grund av klassificeringskonflikter': self.conflict_rejections,
            'Varav borttagna vid slutkontroll av internkvot': int(self.decisions.decision.eq('INTERNAL_QUOTA_REMOVED').sum()),
            'Tillåtet antal interna i faktiskt stickprov': len(self.sample) // 20,
            'Aktiva interna klassificeringsregler': self.internal_rules_active,
            'Internkvot och begränsning': QUOTA_EXPLANATION,
            'Klassificeringsregelstatus': ('Bekräftade interna klassificeringsregler används.'
                                         if self.internal_rules_active else NO_INTERNAL_RULES),
            'Klassificeringsunderlag SHA-256': self.classification_fingerprint,
        }

    @property
    def population_fingerprint(self):
        """Identify the ordered selection evidence; source bytes have their own hash."""
        return sha256(self.identity_rows.to_json(orient='split', force_ascii=False).encode('utf-8')).hexdigest()

    @property
    def selected_identity_rows(self):
        selected = self.decisions.loc[self.decisions['decision'] == 'SELECTED', 'population_position']
        return self.identity_rows.loc[self.identity_rows['population_position'].isin(selected)].copy(deep=True)

    @property
    def shortfall_message(self):
        if len(self.sample) == self.target_size:
            return ''
        counts = self.decisions['decision'].value_counts()
        if self.quota_rejections or self.conflict_rejections:
            return (f'Stickprovet blev mindre: {len(self.sample)} av önskade {self.target_size} verifikationer. '
                    f'{self.quota_rejections} bortval på grund av internkvoten, varav '
                    f'{counts.get("INTERNAL_QUOTA_REMOVED", 0)} vid slutkontroll mot faktiskt antal. '
                    f'{self.conflict_rejections} bortval på grund av klassificeringskonflikter. '
                    f'{counts.get("DUPLICATE_SUPPLIER", 0)} med redan vald leverantör och '
                    f'{counts.get("UNUSABLE_IDENTITY", 0)} med saknad eller flera leverantörsnycklar. '
                    'Ingen ny dragning eller återgång görs för att fylla borttagna platser. '
                    'Se urvalsbesluten för prövade och ej prövade verifikationer.')
        if self.method == 'randomized':
            return (f'Stickprovet blev mindre: {len(self.sample)} av önskade {self.target_size} verifikationer. '
                    f'Hela populationen om {len(self.decisions)} verifikationer har prövats i slumpordning. '
                    'Inga fler giltiga, unika leverantörer kunde väljas. '
                    f'{counts.get("DUPLICATE_SUPPLIER", 0)} kandidater har redan vald leverantör och '
                    f'{counts.get("UNUSABLE_IDENTITY", 0)} har saknad eller flera leverantörsnycklar. '
                    'Återstående platser fylls inte med dubletter. Se urvalsbesluten för orsaker och källrader.')
        return (f'Stickprovet blev mindre: {len(self.sample)} av önskade {self.target_size} verifikationer. '
                'Inga fler giltiga, unika leverantörer kunde väljas framåt från urvalspositionerna. '
                f'Överhoppade kandidater: {counts.get("DUPLICATE_SUPPLIER", 0)} med redan vald leverantör, '
                f'{counts.get("UNUSABLE_IDENTITY", 0)} med saknad eller flera leverantörsnycklar. '
                'Återstående platser fylls inte med dubletter. Se urvalsbesluten för orsaker och källrader.')


def _supplier_identities(verifications, analysis):
    matches = (analysis.rows.set_index('source_row_position')
               if analysis is not None and analysis.registry.available else pd.DataFrame())
    records = []
    for position, verification in enumerate(verifications, 1):
        rows = verification.rows
        for source_position, row in rows.iterrows():
            raw = extract_supplier(row['header_text']) if list(rows.columns).count('header_text') == 1 else None
            normalized = normalize_supplier(raw)
            match = matches.loc[source_position] if source_position in matches.index else None
            strong = match is not None and match['supplier_match_status'] == 'STRONG_MATCH'
            org = match['matched_organization_number'] if strong else None
            key = 'org:' + str(org) if strong and pd.notna(org) and str(org).strip() else (
                'name:' + normalized if normalized else None)
            basis = 'STRONG_MATCH_ORG' if key and key.startswith('org:') else (
                'NORMALIZED_HEADER_NAME' if key else 'UNAVAILABLE')
            records.append(dict(population_position=position, verification_id=verification.verification_id,
                source_row_position=source_position, supplier_text_raw=raw, supplier_normalized=normalized,
                supplier_key=key, identity_basis=basis,
                supplier_match_status=match['supplier_match_status'] if match is not None else None,
                matched_organization_number=org,
                identity_reason={'STRONG_MATCH_ORG': 'Organisationsnummer från befintlig stark leverantörsträff.',
                    'NORMALIZED_HEADER_NAME': 'Exakt normaliserat namn extraherat ur Huvudtext; juridisk identitet är inte bekräftad.',
                    'UNAVAILABLE': 'Inget användbart leverantörsnamn kunde extraheras ur Huvudtext.'}[basis]))
    return pd.DataFrame(records, columns=[
        'population_position', 'verification_id', 'source_row_position', 'supplier_text_raw',
        'supplier_normalized', 'supplier_key', 'identity_basis', 'supplier_match_status',
        'matched_organization_number', 'identity_reason',
    ])


def plan_manual_sample(
    analyzed_verifications: Iterable[Verification], *,
    settings_path: str | Path = DEFAULT_SETTINGS_PATH,
    interval: int | None = None,
    supplier_analysis=None,
    classification_rules=None,
) -> SamplingResult:
    """Try interval, 2*interval, ...; replace ineligible candidates by scanning forward.

    The caller must supply every relevant, already-analyzed verification once,
    normally in the builder's first-appearance order. Analysis completion is a
    caller precondition: Verification has no analysis-completion marker.
    src/pipeline.py completes detection for all eligible verifications first.
    The iterable is fully consumed before selecting any verifications.

    The target is floor(population / interval). Each slot starts at its original
    interval position or after the last examined candidate, whichever is later.
    There is no wraparound, reordering, randomization or duplicate backfilling.
    Strong matches use existing organization numbers; other rows use the exact
    existing normalization of the supplier extracted from Huvudtext. Every row
    of a verification must have one and the same key. Missing/multiple identities
    remain outside the sample with evidence. Never use Motp or pick a candidate.
    Both a repeated key and a repeated normalized name prevent reselection.
    Detection outcomes and supplier-view classification do not affect selection.
    Separate confirmed sampling classifications enforce the internal quota.
    Empty inputs and inputs shorter than the interval produce an empty sample.
    Selected rows (including mutable object cells) are copied independently.
    Invalid business values are retained without interpretation.

    Supplier uniqueness and the fallback/invalid-identity policy were confirmed
    in the priority-2 request, 2026-09-30. The configured interval remains 20.
    """
    interval = load_sample_interval(settings_path) if interval is None else interval
    if type(interval) is not int or interval <= 0:
        raise ValueError("manual_sample_interval must be a positive integer")

    rules = load_sampling_rules(settings_path) if classification_rules is None else sampling_rules(classification_rules)
    verifications, identities, decisions, names_by_position, classified = _prepare_candidates(
        analyzed_verifications, supplier_analysis, rules)
    chosen, seen_keys, seen_names = [], {}, {}
    target = len(verifications) // interval
    internal_count = 0
    cursor = 0
    for nominal in range(interval, len(verifications) + 1, interval):
        cursor = max(nominal, cursor + 1)
        while cursor <= len(verifications):
            decision = decisions[cursor - 1]
            decision['nominal_position'] = nominal
            if _select_candidate(decision, names_by_position[cursor], seen_keys, seen_names,
                                 'Första giltiga unika leverantören från denna urvalsposition.',
                                 internal_count=internal_count, internal_limit=target // 20):
                chosen.append(cursor)
                internal_count += decision['supplier_classification'] == 'INTERNAL'
                break
            cursor += 1
    chosen = enforce_final_quota(chosen, decisions)
    return SamplingResult(_copy_sample(verifications, chosen), target,
                          _decision_table(decisions), identities, interval=interval,
                          classification_rows=classified, classification_rules=rules)


def plan_random_sample(analyzed_verifications: Iterable[Verification], *,
                       seed: int | None = None, supplier_analysis=None,
                       settings_path=DEFAULT_SETTINGS_PATH, classification_rules=None) -> SamplingResult:
    """Uniformly shuffle the full population, then accept up to 20 unique suppliers.

    Every verification receives an equally random priority, independently of
    flags, matching confidence, supplier-view classification and interval slots.
    Supplier uniqueness and the confirmed classification/quota rules constrain
    final inclusion probabilities. Missing/multiple identities are unusable
    under the same rules as systematic sampling.
    The generator is local: no global RNG state is read or changed. The same seed
    and ordered population/identity evidence with the same classification rules
    reproduce the selected occurrences.
    Display/export retain population order; draw_position records random priority.
    """
    seed = new_sample_seed() if seed is None else seed
    if type(seed) is not int or seed < 0:
        raise ValueError('sampling seed must be a non-negative integer')
    rules = load_sampling_rules(settings_path) if classification_rules is None else sampling_rules(classification_rules)
    verifications, identities, decisions, names_by_position, classified = _prepare_candidates(
        analyzed_verifications, supplier_analysis, rules)
    order = list(range(1, len(verifications) + 1))
    Random(seed).shuffle(order)
    for draw_position, position in enumerate(order, 1):
        decisions[position - 1]['draw_position'] = draw_position
        decisions[position - 1]['selection_reason'] = 'Urvalsmålet uppnåddes innan kandidaten prövades.'
    chosen, seen_keys, seen_names = [], {}, {}
    internal_count = 0
    for position in order:
        if _select_candidate(decisions[position - 1], names_by_position[position], seen_keys, seen_names,
                             'Vald från hela populationen i seedstyrd slumpordning; unik leverantör.',
                             internal_count=internal_count, internal_limit=RANDOM_SAMPLE_SIZE // 20):
            chosen.append(position)
            internal_count += decisions[position - 1]['supplier_classification'] == 'INTERNAL'
            if len(chosen) == RANDOM_SAMPLE_SIZE:
                break
    chosen = enforce_final_quota(chosen, decisions)
    return SamplingResult(_copy_sample(verifications, sorted(chosen)), RANDOM_SAMPLE_SIZE,
                          _decision_table(decisions, randomized=True), identities,
                          method='randomized', seed=seed, classification_rows=classified, classification_rules=rules)


def _prepare_candidates(analyzed_verifications, supplier_analysis, rules):
    """Shared, unchanged identity rules for both selection methods."""
    verifications = list(analyzed_verifications)
    if any(not isinstance(item, Verification) for item in verifications):
        raise TypeError("analyzed_verifications must contain Verification objects, not Excel rows")
    identities = _supplier_identities(verifications, supplier_analysis)
    classified = classify_identities(identities, rules)
    groups = {p: rows for p, rows in classified.groupby('population_position', sort=False)}
    decisions, names_by_position = [], {}
    for position, verification in enumerate(verifications, 1):
        evidence = groups.get(position, classified.iloc[:0])
        keys = set(evidence.supplier_key.dropna())
        missing = evidence.empty or evidence.supplier_key.isna().any()
        usable = not missing and len(keys) == 1
        reason = ('Leverantörsnyckel saknas på minst en rad.' if missing else
                  'Verifikationen har flera leverantörsnycklar; en gemensam nyckel kan inte fastställas.' if len(keys) != 1 else
                  'Alla rader har samma leverantörsnyckel.')
        classification, class_reason = verification_classification(evidence)
        names_by_position[position] = set(evidence.supplier_normalized) - {''}
        decisions.append(dict(population_position=position, verification_id=verification.verification_id,
            supplier_key=next(iter(keys)) if usable else None, identity_usable=bool(usable),
            identity_reason=reason, supplier_classification=classification, classification_reason=class_reason,
            decision='NOT_CANDIDATE',
            selection_reason='Inte prövad enligt urvalsordningen.', nominal_position=None,
            duplicate_of_population_position=None))
    return verifications, identities, decisions, names_by_position, classified


def _select_candidate(decision, names, seen_keys, seen_names, selected_reason, *, internal_count, internal_limit):
    duplicates = [seen_names[name] for name in names if name in seen_names]
    if decision['supplier_key'] in seen_keys:
        duplicates.append(seen_keys[decision['supplier_key']])
    if decision['supplier_classification'] == 'CONFLICT':
        decision.update(decision='CLASSIFICATION_CONFLICT', selection_reason=decision['classification_reason'])
    elif not decision['identity_usable']:
        decision.update(decision='UNUSABLE_IDENTITY', selection_reason=decision['identity_reason'])
    elif duplicates:
        decision.update(decision='DUPLICATE_SUPPLIER',
            selection_reason='Leverantörsnyckeln eller det normaliserade namnet finns redan i stickprovet.',
            duplicate_of_population_position=min(duplicates))
    elif decision['supplier_classification'] == 'INTERNAL' and internal_count >= internal_limit:
        decision.update(decision='INTERNAL_QUOTA', selection_reason=(
            f'Internkvoten utifrån målantalet tillåter högst {internal_limit} interna; kandidaten hoppas över.'))
    else:
        decision.update(decision='SELECTED', selection_reason=selected_reason)
        position = decision['population_position']
        seen_keys[decision['supplier_key']] = position
        seen_names.update({name: position for name in names})
        return True
    return False


def _copy_sample(verifications, chosen):
    sample = []
    for position in chosen:
        verification = verifications[position - 1]
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


def _decision_table(decisions, *, randomized=False):
    return pd.DataFrame(decisions, columns=[
        'population_position', 'verification_id', 'supplier_key', 'identity_usable', 'identity_reason',
        'decision', 'selection_reason', 'nominal_position', 'duplicate_of_population_position',
        'supplier_classification', 'classification_reason',
    ] + (['draw_position'] if randomized else []))


def create_manual_sample(analyzed_verifications, *, settings_path=DEFAULT_SETTINGS_PATH,
                         interval=None, supplier_analysis=None) -> list[Verification]:
    """Compatibility helper returning the sample; pipeline retains the full audit plan."""
    return plan_manual_sample(analyzed_verifications, settings_path=settings_path,
                              interval=interval, supplier_analysis=supplier_analysis).sample
