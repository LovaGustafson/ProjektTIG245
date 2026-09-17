"""Explainable name resolution. Several plausible legal entities never auto-select."""
from difflib import SequenceMatcher

from src.models.supplier import SupplierCandidate, SupplierMatch, SupplierMatchStatus as Status
from src.supplier_matching.normalization import normalize_supplier, split_legal_form
from src.supplier_matching.settings import MatchSettings


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
        else:
            return None
        if conflict:
            safe = False
            reason += f' Olika bolagsformer: {query_form.upper()} / {name_form.upper()}.'
        elif explicit_form_uncertain:
            reason += ' Bolagsformen kan inte bekräftas.'
        if not supplier.organization_number:
            safe = False
            reason += ' Organisationsnummer saknas i registret.'
        return SupplierCandidate(supplier, name, method, round(score, 6), reason, safe)

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
        if len(candidates) == 1 and best.strong_eligible:
            return SupplierMatch(supplier_text, query, Status.STRONG_MATCH, best.method, best.score,
                'Stark leverantörsträff i Koncerninköpsregistret. ' + best.reason, candidates)
        reason = 'Flera eller osäkra leverantörsträffar – kontrollera manuellt. '
        if len(candidates) > 1:
            reason += f'{len(candidates)} möjliga leverantörsidentiteter; ingen har valts.'
        else:
            reason += best.reason
        return SupplierMatch(supplier_text, query, Status.AMBIGUOUS_MATCH,
                             best.method, best.score, reason, candidates)
