"""Select a separate manual sample after analysis of all relevant verifications."""

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from src.models.verification import Verification
from src.supplier_matching.extraction import extract_supplier
from src.supplier_matching.normalization import normalize_supplier


DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config/settings.yaml"


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

    @property
    def shortfall_message(self):
        if len(self.sample) == self.target_size:
            return ''
        counts = self.decisions['decision'].value_counts()
        return (f'Stickprovet blev mindre: {len(self.sample)} av önskade {self.target_size} verifikationer. '
                'Inga fler giltiga, unika leverantörer kunde väljas framåt från urvalspositionerna. '
                f'Överhoppade kandidater: {counts.get("DUPLICATE_SUPPLIER", 0)} med redan vald leverantör, '
                f'{counts.get("UNUSABLE_IDENTITY", 0)} med saknad eller flera leverantörsidentiteter. '
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
    No filtering by detection outcome or internal/external classification occurs.
    Empty inputs and inputs shorter than the interval produce an empty sample.
    Selected rows (including mutable object cells) are copied independently.
    Invalid business values are retained without interpretation.

    Supplier uniqueness and the fallback/invalid-identity policy were confirmed
    in the priority-2 request, 2026-09-30. The configured interval remains 20.
    """
    interval = load_sample_interval(settings_path) if interval is None else interval
    if type(interval) is not int or interval <= 0:
        raise ValueError("manual_sample_interval must be a positive integer")

    verifications = list(analyzed_verifications)
    if any(not isinstance(item, Verification) for item in verifications):
        raise TypeError("analyzed_verifications must contain Verification objects, not Excel rows")

    identities = _supplier_identities(verifications, supplier_analysis)
    groups = {p: rows for p, rows in identities.groupby('population_position', sort=False)}
    decisions, names_by_position = [], {}
    for position, verification in enumerate(verifications, 1):
        evidence = groups.get(position, identities.iloc[:0])
        keys = set(evidence.supplier_key.dropna())
        missing = evidence.empty or evidence.supplier_key.isna().any()
        usable = not missing and len(keys) == 1
        reason = ('Leverantörsidentitet saknas på minst en rad.' if missing else
                  'Verifikationen har flera leverantörsnycklar; gemensam identitet är inte säkerställd.' if len(keys) != 1 else
                  'Alla rader har samma leverantörsnyckel.')
        names_by_position[position] = set(evidence.supplier_normalized) - {''}
        decisions.append(dict(population_position=position, verification_id=verification.verification_id,
            supplier_key=next(iter(keys)) if usable else None, identity_usable=bool(usable),
            identity_reason=reason, decision='NOT_CANDIDATE',
            selection_reason='Inte prövad enligt urvalsordningen.', nominal_position=None,
            duplicate_of_population_position=None))
    chosen, seen_keys, seen_names = [], {}, {}
    cursor = 0
    for nominal in range(interval, len(verifications) + 1, interval):
        cursor = max(nominal, cursor + 1)
        while cursor <= len(verifications):
            decision = decisions[cursor - 1]
            decision['nominal_position'] = nominal
            duplicates = [seen_names[name] for name in names_by_position[cursor] if name in seen_names]
            if decision['supplier_key'] in seen_keys:
                duplicates.append(seen_keys[decision['supplier_key']])
            if not decision['identity_usable']:
                decision.update(decision='UNUSABLE_IDENTITY', selection_reason=decision['identity_reason'])
            elif duplicates:
                decision.update(decision='DUPLICATE_SUPPLIER',
                    selection_reason='Leverantörsnyckeln eller det normaliserade namnet finns redan i stickprovet.',
                    duplicate_of_population_position=min(duplicates))
            else:
                decision.update(decision='SELECTED', selection_reason='Första giltiga unika leverantören från denna urvalsposition.')
                chosen.append(cursor)
                seen_keys[decision['supplier_key']] = cursor
                seen_names.update({name: cursor for name in names_by_position[cursor]})
                break
            cursor += 1
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
    decision_table = pd.DataFrame(decisions, columns=[
        'population_position', 'verification_id', 'supplier_key', 'identity_usable', 'identity_reason',
        'decision', 'selection_reason', 'nominal_position', 'duplicate_of_population_position',
    ])
    return SamplingResult(sample, len(verifications) // interval, decision_table, identities)


def create_manual_sample(analyzed_verifications, *, settings_path=DEFAULT_SETTINGS_PATH,
                         interval=None, supplier_analysis=None) -> list[Verification]:
    """Compatibility helper returning the sample; pipeline retains the full audit plan."""
    return plan_manual_sample(analyzed_verifications, settings_path=settings_path,
                              interval=interval, supplier_analysis=supplier_analysis).sample
