# Current Customer MoSCoW Requirements

Last updated: 2026-09-23

This document contains the current customer requirements for the TIG245 prototype.

These requirements must be treated as the current customer priority baseline.

Do not invent missing business rules.
Where a requirement is ambiguous, implementation must be based on an explicitly documented rule or marked as requiring clarification.

---

# Must Have

Critical requirements or activities that must be in place for the project to succeed.

## M1 — Correct source/system

Customer requirement:

> Underlaget kommer från rätt källa/system.

Implementation status:

- To be assessed

Clarification required:

- Which source/system is considered authoritative?
- How should the application verify this?

---

## M2 — Complete population

Customer requirement:

> Populationen är komplett.

Implementation status:

- To be assessed

Clarification required:

- What defines a complete population?
- Which records must be present?
- How should completeness be verified?

---

## M3 — Duplicates removed

Customer requirement:

> Dubbletter är borttagna.

Implementation status:

- To be assessed

Clarification required:

- What constitutes a duplicate?
- Which fields determine duplicate identity?
- Should duplicate rows be deleted, excluded from analysis, or retained with a status?
- Traceability to original source data must not be lost.

---

## M4 — Invalid or empty records handled

Customer requirement:

> Felaktiga eller tomma poster är identifierade och hanterade.

Implementation status:

- To be assessed

Clarification required:

- Which fields are mandatory?
- What constitutes an invalid record?
- What does "hanterade" mean: exclude, flag, correct, or report?

---

## M5 — Sampling criteria documented

Customer requirement:

> Urvalskriterier är dokumenterade.

Implementation status:

- To be assessed

Expected principle:

- The system must make the rules used for selecting the review sample transparent and reproducible.

Do not invent sampling rules that are not documented elsewhere in the project.

---

## M6 — Traceability

Customer requirement:

> Det finns spårbarhet mellan källdata och granskningsunderlag.

Implementation status:

- To be assessed

Expected principle:

- A record included in the review material must be traceable back to its source data.

Clarification required:

- Which identifier(s) constitute sufficient traceability?
- How should transformed, filtered, excluded, or sampled records be represented?

---

## M7 — Compliance with VGR AI guidelines

Customer requirement:

> Hålla sig inom VGRs riktlinjer för AI-användande.

Implementation status:

- Requires source documentation / verification

Important:

- Do not assume or invent VGR AI requirements.
- Implementation decisions concerning AI usage must be based on the actual VGR guidelines supplied to the project.

---

# Should Have

Important requirements, but not absolutely critical for the current delivery.

## S1 — Automated data-quality controls

Customer requirement:

> Automatiserade kontroller av datakvalitet.

Customer note:

- Later

Do not prioritize for the current implementation unless explicitly requested.

---

## S2 — Documented work instruction

Customer requirement:

> Dokumenterad arbetsinstruktion.

Implementation status:

- To be assessed

---

## S3 — Peer review of extraction and cleansing

Customer requirement:

> Kollegial kontroll av uttag och rensning.

Customer note:

- Later

Do not prioritize for the current implementation unless explicitly requested.

---

## S4 — Deviation list with comments

Customer requirement:

> Avvikelselista med kommentarer.

Implementation status:

- To be assessed

Clarification required:

- Which deviations should be included?
- Which comments should be generated automatically versus entered manually?
- Required export/output format is not yet specified here.

---

# Could Have

Desirable features that provide additional value but are not necessary for the current core control process.

## C1 — Data visualizations

Customer requirement:

> Visualiseringar av data.

---

## C2 — Automated dashboards

Customer requirement:

> Automatiska dashboards.

---

## C3 — Additional analysis

Customer requirement:

> Ytterligare analyser som ger ökad förståelse.

Important:

- Could Have work must not take priority over incomplete Must Have requirements.

---

# Won't Have This Time

These are consciously excluded from the current delivery.

This does not mean "never"; it means "not now."

## W1 — Fully automated process

Customer requirement:

> Helt automatiserad process. Kontroll av attester, underlag etc.

Do not implement full automation of attest controls, supporting documentation checks, or equivalent processes in the current scope.

---

## W2 — New system solutions

Customer requirement:

> Nya systemlösningar. Kunna göra bättre rapportuttag från Proceedo (Marknadsplatsen).

Do not expand the current scope into replacement systems, integrations, or new reporting solutions for Proceedo unless the project scope is formally changed.

---

## W3 — Advanced analysis functions

Customer requirement:

> Avancerade analysfunktioner som inte krävs för kontrollen.

Do not implement advanced analytical functionality unless it directly supports an approved current requirement.

---

# Priority Rules for Development

When implementing changes:

1. Must Have requirements take priority.
2. Should Have requirements must not delay unresolved Must Have requirements.
3. Could Have functionality must not be implemented at the expense of Must Have functionality.
4. Won't Have This Time functionality is outside the current project scope.
5. Existing functionality must not be interpreted as satisfying a requirement without verification.
6. Do not invent missing business rules.
7. Preserve traceability to original source data.
8. Ambiguous customer requirements must be surfaced rather than silently interpreted.
