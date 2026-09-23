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

Status:
- PARTIALLY DEFINED / GOVERNANCE REQUIREMENT

Customer-provided guidance establishes the following principles:

1. VGR-recommended AI services should be used in the first instance:
   - VGR's internal chatbot
   - Copilot within VGR's M365 environment

2. A suitability assessment must be made before generative AI is used for a work task.

3. Secret, sensitive, personal, or sensitive internal information must not be submitted to AI services where such sharing is inappropriate.

4. AI-generated output must always be fact-checked and reviewed by a human.

5. Generative AI must be used as a complement to human work and must not replace human responsibility or judgment.

6. The user remains responsible for AI-assisted output.

7. Use of generative AI in producing material must be disclosed where applicable.

8. Information created using AI remains subject to VGR's normal information-management requirements.

### Development guardrail

External development assistants such as Codex must not be provided with real VGR source data, sensitive information, personal data, or sensitive internal working material unless explicitly approved by VGR.

Codex-assisted development must therefore use synthetic, anonymized, public, or otherwise approved material.

### Application design principle

The TIG245 prototype must not treat AI output as an autonomous business decision.

Human review remains required for:
- flagged deviations
- validation results
- supplier-related conclusions
- review decisions
- exported review material

### Verification status

The repository may implement technical safeguards supporting these principles, but full VGR compliance must not be claimed solely from technical implementation.

Formal compliance/approval remains an organizational governance decision.

Implementation status:

- Requires source documentation / verification

Important:

- Do not assume or invent VGR AI requirements.
- Implementation decisions concerning AI usage must be based on the actual VGR guidelines supplied to the project.

---

# Should Have

Important requirements that provide significant value but are lower priority than the current Must Have baseline.

Should Have requirements are not prohibited. They may be implemented opportunistically when they can be solved safely, with low complexity, and without delaying, weakening, or creating risk for Must Have work.

Codex must not expand a Should Have requirement into a large feature unless explicitly instructed.

## Priority principle for Should Have requirements

Should Have requirements are lower priority than Must Have requirements, but they are not prohibited.

If a Should Have requirement can be implemented safely, with low complexity, and without delaying or creating risk for Must Have work, it may be included opportunistically.

Codex must not expand a Should Have requirement into a large feature without explicit instruction.

---

## S1 — Automated data-quality controls

Customer requirement:

> Automatiserade kontroller av datakvalitet.

Customer note:
- Later

Status:
- PARTIALLY IMPLEMENTED
- LOWER PRIORITY / OPPORTUNISTIC

Interpretation:
- The customer considers this capability useful but not currently critical.
- Existing automated data-quality controls should be preserved.
- Additional controls may be implemented if they are low-risk, clearly beneficial, and do not delay or complicate Must Have work.

Current implementation:
- The prototype already performs several technical data-quality checks.
- Existing validation includes checks for schema, identifiers, dates, amounts, mandatory technical fields, and some duplicate identities.
- Existing automated controls must remain functional unless a confirmed customer requirement explicitly changes them.

Current scope rule:
- Do not prioritize expansion of automated data-quality controls ahead of unresolved Must Have requirements.
- Do not invent new business-specific controls without confirmed customer rules.
- If a simple, well-supported improvement can be made safely while working on related Must Have functionality, it may be included.

Important distinction:
- A technical validation error is not automatically the same as a business deviation.
- Validation results must not automatically be interpreted as failed internal control.
- A warning should not automatically become a business flag unless a confirmed business rule says so.

Acceptance for current phase:
- Existing controls continue to function.
- No regression is introduced.
- New controls are only added when explicitly required or when they clearly support a confirmed Must Have requirement.

---

## S2 — Documented work instruction

Customer requirement:

> Dokumenterad arbetsinstruktion.

Status:
- PARTIALLY IMPLEMENTED
- SHOULD BE COMPLETED WHEN THE CURRENT PROCESS IS STABLE ENOUGH TO DOCUMENT ACCURATELY

Current implementation:
- README and existing project documentation describe technical installation and use of the prototype.
- Parts of the review workflow are already documented.
- The prototype has a defined technical flow from file upload through analysis, review, sampling, and export.

Missing:
- A complete customer-facing work instruction covering the practical review process from received source file to final review material.

The future work instruction should, when the relevant rules are sufficiently confirmed, explain at minimum:

1. How the source file is received.
2. That the current source extract is provided by the customer from Proceedo.
3. That the project team does not have direct access to Proceedo and therefore cannot independently verify source-system completeness.
4. How the received population is checked and reconciled within the prototype.
5. Which confirmed account and Vertyp exclusions are applied.
6. How excluded rows remain traceable and are not silently deleted.
7. How invalid or incomplete records are handled.
8. How possible duplicates are handled once the customer duplicate rule is confirmed.
9. How the review population is created.
10. How every 20th verification is selected.
11. How flagged records are reviewed.
12. How exported review material is generated and used.
13. How traceability back to the supplied source data is maintained.
14. Which steps require human review.
15. How AI-assisted development or analysis must comply with applicable VGR guidelines.

Current scope rule:
- Do not invent procedures for unresolved requirements.
- Open customer decisions must remain clearly marked as open rather than being presented as established working instructions.
- The work instruction should reflect actual implemented behavior, not intended future functionality.

Acceptance for current phase:
- Technical documentation remains accurate.
- The customer-facing work instruction is updated progressively as Must Have rules become confirmed.
- The final instruction must not claim that unresolved controls are already implemented.

---

## S3 — Peer review of extraction and cleansing

Customer requirement:

> Kollegial kontroll av uttag och rensning.

Customer note:
- Later

Status:
- NOT FORMALLY IMPLEMENTED
- LOWER PRIORITY / OPPORTUNISTIC

Interpretation:
- The customer is interested in this capability, but it is not currently a critical delivery requirement.
- A lightweight solution may be considered if it can be implemented without adding unnecessary complexity or delaying Must Have work.

Current state:
- Another person can inspect the review material and exported results.
- This must not be interpreted as a formal peer-review or approval workflow.
- The current prototype does not maintain a formal reviewer record or sign-off state.

Possible lightweight future approaches may include:
- reviewer name or initials,
- review status,
- timestamp for completed review,
- simple review comment,
- export field indicating whether peer review has occurred.

These are possibilities, not confirmed customer requirements.

Open questions:
- Who performs the peer review?
- Which parts of the process require review?
- Does the Proceedo source extraction itself require peer review?
- Does cleansing/filtering require a separate review step?
- Should reviewer identity be stored?
- Should review approval be recorded inside the prototype or outside it?
- Is a lightweight exported review record sufficient, or is an in-application workflow required?

Current scope rule:
- Simple review support may be added opportunistically when it naturally fits related work.
- Do not build a complex reviewer, permissions, approval, or sign-off workflow before the customer clarifies the intended process.
- Do not describe ordinary inspection of the UI or Excel exports as formal peer review.

---

## S4 — Deviation list with comments

Customer requirement:

> Avvikelselista med kommentarer.

Status:
- PARTIALLY IMPLEMENTED

Current implementation:
- The prototype already produces several forms of flagged or explanatory results.
- Detection results can contain reasons for flagged records.
- Validation issues can be surfaced.
- Supplier-related statuses and explanations may also be presented.
- Flagged results can be included in review and export material.
- Invalid or incomplete records should remain available for review rather than being silently removed.

Current limitation:
- There is not yet one unified customer-approved deviation list containing all relevant deviation categories.
- Manual reviewer comments are not currently a confirmed persistent workflow.
- Validation findings, detection flags, supplier statuses, possible duplicates, and exclusions are currently conceptually different result types and must not be merged without preserving their meaning.

Target principle:
- Relevant deviations should be possible to collect into a clearly identifiable review output.
- Each deviation should retain enough information to understand:
  - which source record it concerns,
  - why it was flagged,
  - which rule or check generated it,
  - where it originated in the supplied source data,
  - whether the finding is technical, business-related, supplier-related, or unresolved.

Possible deviation sources include:
- invalid or incomplete records,
- confirmed detection flags,
- possible duplicates once the duplicate rule is confirmed,
- supplier-related findings where applicable,
- other customer-confirmed deviations.

Important distinctions:
- NOT_CHECKED must not be treated as PASS.
- NOT_CHECKED must not automatically be treated as a deviation either.
- A validation warning must not automatically become a business deviation.
- A supplier name match must not automatically be represented as contract compliance.
- An excluded record is not automatically a deviation; confirmed exclusions are a separate category.
- A possible duplicate must remain a possible duplicate until the customer duplicate definition is confirmed.

Comments:
- The customer requirement explicitly mentions comments.
- It is currently not confirmed whether comments should:
  - be entered manually in the prototype,
  - be generated automatically,
  - be stored persistently,
  - or simply be available as an editable/exported field in Excel.

Open question:
- What type of comment workflow does the customer want?

Possible low-complexity approach:
- Add an optional comment column in exported deviation material without introducing a complex in-application comment system.

This should only be treated as a possible implementation approach, not a confirmed requirement.

Acceptance for current phase:
- Existing flagged information remains available.
- Flagged records retain explanatory reasons.
-

# Could Have

Could Have requirements are desirable features that may provide additional value, but they are not necessary for the current core control process.

These requirements must not delay, complicate, or introduce risk to unresolved Must Have work.

Could Have requirements are not prohibited. If a low-risk improvement can be added naturally while working on higher-priority functionality, it may be included when the benefit is clear and the implementation is proportionate.

Codex must not expand a Could Have requirement into a large feature or redesign without explicit instruction.

---

## C1 — Data visualizations

Customer requirement:

> Visualiseringar av data.

Status:
- PARTIALLY IMPLEMENTED
- OPTIONAL / OPPORTUNISTIC

Current implementation:
- The Streamlit interface already provides visual presentation through:
  - KPI cards,
  - status indicators,
  - structured tables,
  - summaries,
  - interactive filtering,
  - supplier-related summaries where applicable.

Interpretation:
- The customer has expressed interest in visualizations, but no specific chart type, metric, dashboard layout, or visualization requirement has been confirmed.
- Existing UI elements may already satisfy part of the intended value.

Possible future improvements may include:
- charts showing included versus excluded records,
- counts of flagged records,
- distribution of validation outcomes,
- sampling summaries,
- supplier-related status distributions,
- other visual summaries that improve understanding of the review population.

Current scope rule:
- Do not create visualizations merely for appearance.
- A visualization should support a real review or decision-support need.
- Do not prioritize visualization work ahead of unresolved Must Have requirements.
- Do not invent business meaning from technical statuses.
- NOT_CHECKED must not be presented visually as PASS.
- Validation warnings, detection flags, supplier statuses, and exclusions must remain conceptually distinct.

Acceptance for current phase:
- Existing visual UI functionality is preserved.
- New visualizations may be added when they provide clear review value and can be implemented safely without affecting core analysis behavior.

---

## C2 — Automated dashboards

Customer requirement:

> Automatiska dashboards.

Status:
- PARTIALLY IMPLEMENTED
- OPTIONAL / OPPORTUNISTIC

Current implementation:
- The Streamlit application already provides dashboard-like analysis views after the user runs an analysis.
- Current functionality includes overview metrics, result summaries, review navigation, and drill-down into different result categories.

Important distinction:
- The current prototype provides a dashboard based on a user-triggered analysis.
- It does not currently provide:
  - scheduled data ingestion,
  - unattended background processing,
  - automatic refresh from Proceedo,
  - continuous monitoring,
  - autonomous reporting.

Interpretation:
- The customer requirement may refer either to richer analysis dashboards or to more automated dashboard operation.
- The exact intended level of automation has not been confirmed.

Current scope rule:
- Existing dashboard functionality should be preserved.
- Additional dashboard components may be added when they improve understanding of existing confirmed analysis results.
- Do not implement scheduled ingestion, Proceedo integration, unattended automation, or background monitoring under this requirement unless scope is explicitly changed.
- Dashboard improvements must not alter the underlying analysis logic.

Possible future improvements:
- clearer overview of source population,
- included and excluded counts,
- number of flagged records,
- sampling information,
- review progress,
- traceability summaries,
- deviation summaries.

Acceptance for current phase:
- Dashboard information must reflect actual analysis results.
- Displayed counts must remain consistent with the underlying data.
- New dashboard elements must not create new business conclusions that are not supported by confirmed rules.

---

## C3 — Additional analyses for increased understanding

Customer requirement:

> Ytterligare analyser som ger ökad förståelse.

Status:
- PARTIALLY IMPLEMENTED
- REQUIRES CASE-BY-CASE ASSESSMENT

Current implementation:
- The prototype already contains analysis beyond basic filtering and validation, including supplier-related matching and register-related information.
- Existing analysis functionality should remain part of the prototype unless explicitly removed from scope.

Interpretation:
- Additional analysis is welcome when it clearly improves understanding of the review material.
- However, "increased understanding" is not itself a sufficient acceptance criterion for building new analysis functionality.

Potential future analysis may be considered when:
- it addresses a real review question,
- the required business rule is known,
- the underlying data supports the analysis,
- the result can be explained and traced back to source data,
- the analysis does not replace required human judgment,
- it does not delay higher-priority requirements.

Current scope rule:
- Do not invent new analytical controls simply because data is available.
- Do not infer compliance, fraud, incorrect attest, procurement violation, or other business conclusions without confirmed rules and evidence.
- New analysis must remain explainable.
- Results must preserve source traceability.
- Existing supplier matching must not be represented as final contract-compliance approval.
- Advanced or speculative analytics that are not required for the control process remain outside the current scope.

Acceptance for current phase:
- Existing approved analysis remains functional.
- New analysis may be introduced opportunistically when its purpose, input, interpretation, and output are clear.
- Every new analysis must distinguish between:
  - observed data,
  - deterministic technical result,
  - warning or indicator,
  - final human review decision.

---

## Priority principle for Could Have requirements

Could Have requirements may be implemented when all of the following are true:

1. The change has a clear user or review benefit.
2. It does not delay unresolved Must Have work.
3. It does not introduce significant technical or business risk.
4. It does not require Codex to invent an unresolved business rule.
5. It preserves source-data traceability.
6. It preserves existing analysis semantics.
7. It does not create autonomous business decisions.
8. The implementation effort is proportionate to the value created.

If these conditions are not met, the functionality should remain deferred.

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
