"""Explainable name resolution with conservative, identity-aware exact priority."""
from collections import Counter
from difflib import SequenceMatcher

from src.models.supplier import SupplierCandidate, SupplierMatch, SupplierMatchStatus as Status
from src.supplier_matching.name_structure import (adjacent_swap, analyze_name_structure,
                                                  distinctive_names_related, one_character_edit,
                                                  structured_names_match)
from src.supplier_matching.normalization import normalize_supplier, split_legal_form
from src.supplier_matching.settings import MatchSettings


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
    if adjacent_swap(a, b):
        # A single adjacent swap (e.g. Sverige/Svergie) is one typo,
        # even when SequenceMatcher's token ratio falls below 0.90.
        return True
    return (one_character_edit(a, b)
            and SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.90)


def select_strong_candidate(candidates: tuple[SupplierCandidate, ...]) -> SupplierCandidate | None:
    """Select an eligible identity; competing strong names block exact priority."""
    if len(candidates) == 1 and candidates[0].strong_eligible:
        return candidates[0]
    exact = [c for c in candidates if c.method == 'exact_normalized']
    # Usable identities retain their strongest eligible alias; unknown rows stay separate.
    # Legacy strong competing names block even with unusable identities. Decision A
    # preserves exact priority over evidence introduced only by structured matching.
    if (len(exact) == 1 and exact[0].strong_eligible
            and not any(c.name_strong and c.method != 'structured_name' for c in candidates
                        if c.supplier.key != exact[0].supplier.key)):
        return exact[0]
    return None


def _selected_key(candidates):
    selected = select_strong_candidate(candidates)
    return selected.supplier.key if selected is not None else None


class SupplierMatcher:
    def __init__(self, suppliers, settings=None):
        self.settings = settings or MatchSettings()
        self.names = [(supplier, name, normalize_supplier(name))
                      for supplier in suppliers for name in supplier.names]
        self._cache = {}

    def _structured_candidate(self, query, supplier, name, normalized, evaluated, *,
                              structural, inspect_competitors, exact_present, query_structure):
        """Supplement legacy evidence without weakening its exact-priority blockers."""
        if evaluated is not None and evaluated[0].name_strong:
            return evaluated
        config = self.settings
        if structural and not exact_present:
            safe = bool(supplier.organization_number)
            reason = ('Exakt samma särskiljande namnled; endast godkända geografiska '
                      'namnled eller utelämnad bolagsform skiljer. Juridisk identitet är inte verifierad.')
            method = 'structured_name'
        elif evaluated is not None:
            return evaluated
        elif inspect_competitors and distinctive_names_related(
                query_structure, analyze_name_structure(normalized, config.geographic_descriptors),
                config.fuzzy_candidate_threshold):
            safe = False
            reason = 'Möjlig strukturell namnkonkurrent; kräver manuell granskning.'
            method = 'structural_alternative'
        else:
            return None
        if not supplier.organization_number:
            reason += (' Organisationsnummer saknas i registret.'
                       if supplier.organization_number_status in (None, 'MISSING') else
                       ' Organisationsnumret i registret är inte ett tekniskt giltigt organisationsnummer.')
        score = (evaluated[0].score if evaluated is not None else
                 round(SequenceMatcher(None, query, normalized, autojunk=False).ratio(), 6))
        return SupplierCandidate(supplier, name, method, score, reason, safe,
                                 method == 'structured_name'), True

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
            relevant = True
            reason = 'Exakt normaliserat namn.'
        elif prefix:
            score = len(query) / len(normalized)
            safe = (len(query) >= config.prefix_min_characters
                    and len(query.split()) >= config.prefix_min_tokens
                    and score >= config.prefix_min_coverage and same_first
                    and query_form is None)
            method = 'prefix' if safe else 'uncertain_prefix'
            relevant = True
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
            # Phase 3D.1: a candidate reached only through full-name similarity is
            # relevant only if its distinctive name is plausibly related; shared
            # legal/geographic words alone are not enough. Strong name evidence is
            # always relevant. Relevance never changes the method, score or strength.
            relevant = (safe or related or query_core == name_core
                        or distinctive_names_related(
                            analyze_name_structure(query, config.geographic_descriptors),
                            analyze_name_structure(normalized, config.geographic_descriptors),
                            config.fuzzy_candidate_threshold))
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
        return SupplierCandidate(supplier, name, method, round(score, 6), reason, safe, name_safe), relevant

    def match(self, supplier_text):
        query = normalize_supplier(supplier_text)
        if not query:
            return SupplierMatch(supplier_text, query, Status.SUPPLIER_NOT_IDENTIFIED,
                                 'none', None, 'Leverantör kunde inte identifieras från underlaget.')
        if query not in self._cache:
            candidates, relevant_keys = {}, set()
            priority = {'exact_normalized': 5, 'prefix': 4, 'fuzzy': 3, 'structured_name': 2,
                        'uncertain_prefix': 1, 'related_name': 0, 'structural_alternative': -1}
            query_structure = analyze_name_structure(query, self.settings.geographic_descriptors)
            structural = [query != normalized and structured_names_match(
                query_structure, analyze_name_structure(normalized, self.settings.geographic_descriptors),
                self.settings.geographic_descriptors) for _, _, normalized in self.names]
            exact_present = any(query == normalized for _, _, normalized in self.names)
            # Inspect low-score plausible competitors only when structured matching
            # is in play. A shared first word alone never supplies strong evidence.
            inspect_competitors = any(structural)
            for (supplier, name, normalized), structure_match in zip(self.names, structural):
                evaluated = self._candidate(query, supplier, name, normalized)
                evaluated = self._structured_candidate(
                    query, supplier, name, normalized, evaluated, structural=structure_match,
                    inspect_competitors=inspect_competitors, exact_present=exact_present,
                    query_structure=query_structure)
                if evaluated is None:
                    continue
                candidate, relevant = evaluated
                if relevant:
                    # An identity is relevant if any of its aliases is.
                    relevant_keys.add(supplier.key)
                previous = candidates.get(supplier.key)
                # Preserve legacy alias priority, including every legacy blocker.
                # New structural aliases use a stable tie-break, independent of row order.
                rank = lambda c: (c.strong_eligible, priority[c.method], c.score,
                                  c.matched_name if c.method in ('structured_name', 'structural_alternative') else '')
                if previous is None or rank(candidate) > rank(previous):
                    candidates[supplier.key] = candidate
            ranked = tuple(sorted(candidates.values(),
                key=lambda c: (-priority[c.method], -c.score, c.supplier.key)))
            relevant = tuple(c for c in ranked if c.supplier.key in relevant_keys)
            # Phase 3D.1 may only remove unrelated evidence, never change the decision:
            # if dropping unrelated identities would alter the selection, keep them all.
            self._cache[query] = (relevant if _selected_key(relevant) == _selected_key(ranked)
                                  else ranked)
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
                if any(c.supplier.key != selected.supplier.key and structured_names_match(
                        analyze_name_structure(query, self.settings.geographic_descriptors),
                        analyze_name_structure(normalize_supplier(c.matched_name), self.settings.geographic_descriptors),
                        self.settings.geographic_descriptors) for c in candidates):
                    reason += (' Ett strukturellt liknande namn kan avse en annan juridisk identitet; '
                               'exakt namnprioritet har bevarats.')
            return SupplierMatch(supplier_text, query, Status.STRONG_MATCH, selected.method, selected.score,
                reason, candidates, selected_supplier_key=selected.supplier.key)
        reason = 'Flera eller osäkra namnmatchningar – kontrollera manuellt. '
        if len(candidates) > 1:
            reason += f'{len(candidates)} möjliga registerkandidater; ingen har valts.'
        else:
            reason += best.reason
        return SupplierMatch(supplier_text, query, Status.AMBIGUOUS_MATCH,
                             best.method, best.score, reason, candidates)
