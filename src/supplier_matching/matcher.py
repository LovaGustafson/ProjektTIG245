"""Explainable name resolution with conservative, identity-aware exact priority."""
from collections import Counter
from difflib import SequenceMatcher

from src.models.supplier import SupplierCandidate, SupplierMatch, SupplierMatchStatus as Status
from src.supplier_matching.normalization import normalize_supplier, split_legal_form
from src.supplier_matching.settings import MatchSettings


def _one_character_edit(left, right):
    """One insertion, deletion or substitution; transpositions are checked separately."""
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right):
        left, right = right, left
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return (left[index + 1:] == right[index + 1:] if len(left) == len(right)
                    else left[index:] == right[index + 1:])
    return len(right) == len(left) + 1


def _fuzzy_tokens_compatible(words, other_words):
    """Conservative pilot guard, independent of token position and raw name score."""
    left, right = Counter(words), Counter(other_words)
    unmatched_left, unmatched_right = list((left - right).elements()), list((right - left).elements())
    if not unmatched_left and not unmatched_right:
        return True
    if len(unmatched_left) != 1 or len(unmatched_right) != 1:
        return False
    a, b = unmatched_left[0], unmatched_right[0]
    if min(len(a), len(b)) < 6:
        return False
    if len(a) == len(b):
        differences = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(differences) == 2:
            i, j = differences
            if j == i + 1 and a[i] == b[j] and a[j] == b[i]:
                # A single adjacent swap (e.g. Sverige/Svergie) is one typo,
                # even when SequenceMatcher's token ratio falls below 0.90.
                return True
    return (_one_character_edit(a, b)
            and SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.90)


def select_strong_candidate(candidates: tuple[SupplierCandidate, ...]) -> SupplierCandidate | None:
    """Select an eligible identity; competing strong names block exact priority."""
    if len(candidates) == 1 and candidates[0].strong_eligible:
        return candidates[0]
    exact = [c for c in candidates if c.method == 'exact_normalized']
    # Usable identities retain their strongest eligible alias; unknown rows stay separate.
    # A strong competing name blocks even when its identity cannot itself be selected.
    if (len(exact) == 1 and exact[0].strong_eligible
            and not any(c.name_strong for c in candidates
                        if c.supplier.key != exact[0].supplier.key)):
        return exact[0]
    return None


class SupplierMatcher:
    def __init__(self, suppliers, settings=None):
        self.settings = settings or MatchSettings()
        self.names = [(supplier, name, normalize_supplier(name))
                      for supplier in suppliers for name in supplier.names]
        self._cache = {}

    def _candidate(self, query, supplier, name, normalized):
        config = self.settings
        query_core, query_form = split_legal_form(query)
        name_core, name_form = split_legal_form(normalized)
        score = SequenceMatcher(None, query, normalized, autojunk=False).ratio()
        conflict = bool(query_form and name_form and query_form != name_form)
        explicit_form_uncertain = bool(query_form and query_form != name_form)
        words, other_words = query_core.split(), name_core.split()
        same_first = bool(words and other_words and words[0] == other_words[0])
        related = same_first and len(words[0]) >= config.related_first_token_min_characters
        prefix = normalized.startswith(query)
        if query == normalized:
            method, score, safe = 'exact_normalized', 1.0, True
            reason = 'Exakt normaliserat namn.'
        elif prefix:
            score = len(query) / len(normalized)
            safe = (len(query) >= config.prefix_min_characters
                    and len(query.split()) >= config.prefix_min_tokens
                    and score >= config.prefix_min_coverage and same_first
                    and query_form is None)
            method = 'prefix' if safe else 'uncertain_prefix'
            reason = 'Namnet är ett prefix av registernamnet.'
            if not safe:
                reason += ' Prefixet uppfyller inte säkerhetskraven.'
                if query_form:
                    reason += ' Namnet innehåller redan en fullständig bolagsform före ytterligare namntext.'
        elif score >= config.fuzzy_candidate_threshold or related or query_core == name_core:
            method = 'fuzzy' if score >= config.fuzzy_candidate_threshold else 'related_name'
            # Added/removed name tokens can denote a different subsidiary or service.
            safe = (score >= config.fuzzy_strong_threshold and len(words) >= 2
                    and len(words) == len(other_words) and not explicit_form_uncertain)
            reason = ('Hög teckenlikhet med samma antal namnord.' if safe else
                      'Liknande namn, men otillräcklig säkerhet eller avvikande namnord.')
            if safe and not _fuzzy_tokens_compatible(words, other_words):
                safe = False
                reason = 'Leverantörsnamnen är delvis lika, men särskiljande namnled skiljer sig åt.'
        else:
            return None
        if conflict:
            safe = False
            reason += f' Olika bolagsformer: {query_form.upper()} / {name_form.upper()}.'
        elif explicit_form_uncertain:
            reason += ' Bolagsformen kan inte bekräftas.'
        name_safe = safe
        if not supplier.organization_number:
            safe = False
            if supplier.organization_number_status in (None, 'MISSING'):
                reason += ' Organisationsnummer saknas i registret.'
            else:
                reason += ' Organisationsnumret i registret är inte ett tekniskt giltigt organisationsnummer.'
        return SupplierCandidate(supplier, name, method, round(score, 6), reason, safe, name_safe)

    def match(self, supplier_text):
        query = normalize_supplier(supplier_text)
        if not query:
            return SupplierMatch(supplier_text, query, Status.SUPPLIER_NOT_IDENTIFIED,
                                 'none', None, 'Leverantör kunde inte identifieras från underlaget.')
        if query not in self._cache:
            candidates = {}
            priority = {'exact_normalized': 4, 'prefix': 3, 'fuzzy': 2,
                        'uncertain_prefix': 1, 'related_name': 0}
            for supplier, name, normalized in self.names:
                candidate = self._candidate(query, supplier, name, normalized)
                if candidate is None:
                    continue
                previous = candidates.get(supplier.key)
                rank = lambda c: (c.strong_eligible, priority[c.method], c.score)
                if previous is None or rank(candidate) > rank(previous):
                    candidates[supplier.key] = candidate
            self._cache[query] = tuple(sorted(candidates.values(),
                key=lambda c: (-priority[c.method], -c.score, c.supplier.key)))
        candidates = self._cache[query]
        if not candidates:
            return SupplierMatch(supplier_text, query, Status.NO_MATCH, 'none', None,
                'Ingen leverantörsmatch hittades i aktuell Koncerninköpslista.')
        best = candidates[0]
        selected = select_strong_candidate(candidates)
        if selected is not None:
            reason = 'Stark namnmatchning i avtalsregistret. ' + selected.reason
            if len(candidates) > 1:
                reason += (f' En entydig exakt namnmatchning har valts; {len(candidates) - 1} '
                           'svagare alternativa kandidater bevaras för granskning och har inte valts.')
            return SupplierMatch(supplier_text, query, Status.STRONG_MATCH, selected.method, selected.score,
                reason, candidates, selected_supplier_key=selected.supplier.key)
        reason = 'Flera eller osäkra namnmatchningar – kontrollera manuellt. '
        if len(candidates) > 1:
            reason += f'{len(candidates)} möjliga registerkandidater; ingen har valts.'
        else:
            reason += best.reason
        return SupplierMatch(supplier_text, query, Status.AMBIGUOUS_MATCH,
                             best.method, best.score, reason, candidates)
