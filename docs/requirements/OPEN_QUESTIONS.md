# Open Customer Questions

Current scope and confirmed facts are defined in [MOSCOW_CURRENT.md](MOSCOW_CURRENT.md); current technical behavior is described in [PROJECT_SPEC.md](../../PROJECT_SPEC.md). The questions below are unresolved, not implementation authorization. Proceedo is the confirmed source system. Systematic sampling retains interval 20; the 2026-10-12 product decision additionally confirms randomized sampling with a fixed target of 20.

## Q1 — Duplicate definition

Related requirement: M3

Status: Open
Target discussion: next customer meeting

Questions:

- What constitutes a duplicate?
- Is duplicate identity based on Vernr, Vernr + Vrad, identical rows, invoice identity, or another rule?
- Should duplicates be removed, excluded, flagged, or retained?
- If removed, which occurrence survives?
- What is the duplicate scope, can repeated Vernr values represent legitimate records, and how must handling affect validation, filtering, grouping, sampling and exports while preserving occurrences?

Until resolved:
No automatic duplicate removal is permitted.

## Q2 — Sampling evidence

Related requirement: M5 (also S2)

Status: Open

- What evidence must document selection of every 20th eligible verification: eligible population, ordering, applied exclusions, interval, selected positions or other information?
- Where should that evidence appear, and what must a reviewer retain to reproduce or verify the sample?

The 2026-09-24 feature package records population, ordering, exclusions, interval and selected source positions in UI/export. The explicit 2026-09-30 priority-2 request adds supplier uniqueness, forward replacements, target/actual counts, per-verification decisions and per-row identity evidence. The user confirmed normalized extracted names as fallback and keeping missing/multiple identities outside the sample. Customer requirements for further evidence, retention and approval remain open. The interval is already confirmed; this question alone does not authorize changing the selection method.

The 2026-10-12 request and explicit product decision authorize a separate randomized
method with target 20 while preserving systematic target floor(population / 20).
The different sizes are accepted. Seed, timestamp, method, population/identity
evidence, target/actual counts and shortfall reasons are included in the existing
exports. Further retention/approval requirements remain open; they do not block
these explicitly confirmed sampling changes.

## Q3 — Source-occurrence traceability

Related requirement: M6

Status: Open

- Which source-file, worksheet and occurrence information must accompany review material and each export?
- How should included, excluded, invalid, ungrouped and sampled occurrences and their findings be linked and presented to reviewers?

Source/export sheet-row linkage, source-file name/hash and worksheet/header metadata are now implemented for pipeline/UI row exports, including exclusions. Further customer presentation/retention expectations and complete validation/detection-finding export remain open. Existing limitations do not weaken the preservation requirement.

## Q4 — Source and extract assurance

Related requirements: M1, M2 (also S2)

Status: Open

- What evidence establishes the supplied file's origin from Proceedo, and who supplies and reviews it?
- What period, selection and record scope define the required extract population, and what independent evidence reconciles it to Proceedo?
- Who is responsible for source-system completeness, and what reconciliation evidence must the prototype present for the received population?

The prototype has no direct Proceedo access; reading all parsed rows is not independent verification of the customer's extraction.

## Q5 — Structural rows and invalid-record handling

Related requirements: M2, M4, M6

Status: Open

- What distinguishes structural report rows from empty, incomplete or invalid review records in the supplied formats?
- Which existing blank/header/total/footer classifications reflect the intended customer boundary?
- What final review/disposition is required for invalid or ungrouped records, including records without a usable verification ID, and how should this affect sampling eligibility?

Preserve current occurrences and explanations; do not infer permission to remove or correct records.

## Q6 — Peer review and sign-off

Related requirement: S3 (also S2)

Status: Open

- Who reviews extraction and cleansing/filtering, and which steps require separate review?
- What reviewer identity, status, timestamp or sign-off evidence is required?
- Should that evidence be recorded in the prototype, an export or an external process?

Ordinary inspection of an export is not an implemented formal sign-off workflow.

## Q7 — Deviation comments and review output

Related requirement: S4

Status: Open

- Which findings belong in the customer deviation output, with technical, supplier, exclusion and business-review meanings kept distinct?
- What should comments document, and should they be reviewer-entered, generated explanations or both?
- Should comments be entered/persisted in the prototype, provided as editable export fields or maintained outside it?

## Q8 — Changes to exclusion selections

Related requirements: M2, M4, M5 (also S2, S3)

Status: Open

- What approval and supporting evidence are required when changing the standard verification-type exclusions or selecting additional types?
- Who may make such changes, and what selection history or run-specific configuration must accompany the review material and resulting sample?

Confirmed account exclusions remain unchanged. The 2026-10-12 request explicitly adds LR91S and LR95S to the existing standard verification-type set, with reinclusion through the existing UI. The 2026-09-24 request separately authorizes exact internal-supplier exclusions for Försörjningsförvaltning, Fastighetstöd and mall. Approval/evidence for other selection changes remains open; UI/configuration capabilities alone do not authorize new business exclusions.

## Q9 — External AI/Codex governance

Related requirement: M7

Status: Open

- Which supplied VGR guidance/version and organizational decision establish the applicable AI-use requirements?
- Which project data/material and external development-assistant uses are explicitly approved, by whom, and where is approval evidenced?
- What suitability, information-security and privacy assessment and approval would be required before any future AI integration using real VGR data?

M7's existing development guardrail remains in force; technical safeguards alone do not establish full VGR compliance.

## Q10 — Field meanings and business controls

Related requirements: M4, S1, S4; W1/W3 scope boundaries

Status: Open

- What are the business meanings and accepted indicator values for `Mm`, `Pg`, `Sign`, `Att`, `Ksansv` and `Bild`, including source date/number formats and any line-ID constraints?
- Which business information is mandatory, at what scope, and what evidence or reference linkage is required for a control?
- What, if any, confirmed supplier-ID mapping, purchase-to-contract scope or attestation rules/registers would support a separately authorized control?

Existing internal field labels and provisional UI presence interpretations do not answer these questions. Confirmed rules/data alone do not authorize Won't Have functionality; an explicit scope change is also required.

## Q11 — Optional dashboard and analysis needs

Related requirements: C1, C2, C3

Status: Partly specified by the 2026-09-24 feature package / further needs open

- Which review questions, metrics or visualizations would provide additional value beyond the current views?
- What does the customer mean by automated dashboards, and which improvements can be considered within the current user-triggered workflow?
- For any proposed additional analysis, what are its purpose, supported interpretation, required evidence and acceptance criteria?

These questions do not prioritize optional work over Must Haves or authorize scheduled ingestion, Proceedo integration, speculative controls or autonomous decisions.

The requested user-triggered overview now includes received/included/excluded counts and reasons, flagged verifications, supplier confidence/availability, separate contract-period comparisons, sample counts and source traceability. Formal review progress remains unavailable because no reviewer-state workflow exists.

## Q12 — Contract-period date rules

Related requirements: S4, C3; M6 evidence; W1/W3 boundaries

Status: Open — requested during implementation of the 2026-09-24 feature package

- When `Slutdatum` and `Sista slutdatum` both exist or differ, which determines the applicable end of the period? Does `Sista slutdatum` describe an exercised extension or only a possible extension?
- If one end-date field is missing, may the other be used, and under what conditions?
- Are the start day and end day included in the valid period?

The implementation evaluates unambiguous ordinary periods strictly before/inside/after their bounds. Conflicting end dates, final-date-only records and unconfirmed boundary-day cases remain `NOT_CHECKED` with preserved date evidence. Configuration options do not confirm a rule. Every candidate contract remains visible; no purchase-to-contract applicability or compliance conclusion is inferred.

Deployment input still needed: the local source path for the default Koncerninköp register. No real register file was available in the repository data folders during implementation; the default path is configurable and missing files remain explicitly unavailable.

## Q13 — Supplier-view classification and external-only sampling

Del 1 update, 2026-10-13: the approved, implemented cap is floor(actual sample
size / 20) confirmed internal verifications for both methods, including zero
below 20. Use the target-size cap during selection and remove latest selected
internal verifications as necessary against actual size, without backfilling or
redrawing. External and unclassified suppliers remain eligible. Internal +
unclassified means internal; external + unclassified means unclassified;
internal + external or conflicting source rules means conflict and exclusion.
UI/export preserve classification and decision evidence, counts and limitations.
The latest user decision leaves the separate `sampling_supplier_rules` empty.
No example name or organization number is authorized for activation. The quota
is tested using synthetic rules and will apply when exact identities are confirmed.
There is no complete approved external list. Unclassified is never external,
and actual internal share may exceed 5%; the UI/export explicitly explain the
absence of active internal rules. Existing base exclusions remain unchanged.

Related requirements: M5, M6, C1–C3

Status: Sampling policy resolved; exact classification identities remain open.

- Which exact supplier organization numbers or extracted names are confirmed as internal, external or irrelevant to the supplier-matching view? Supply a reason for each entry. Apoteket, Securitas, Försörjningsförvaltningen and Kantarellen are examples, not an approved list.
- External-only sampling is not required: confirmed external and unclassified suppliers are eligible under the approved quota policy. View classification remains separate from sampling classification.
- Would a future authoritative internal/external field or register be supplied, and what does it mean? No such field is currently documented. Motp is not supplier identity or a classification signal.

The implemented `supplier_view_rules` list is empty by default. Only explicitly
confirmed entries apply; unclassified and conflicting cases remain visible.
Existing exact base exclusions for Försörjningsförvaltning, Fastighetstöd and mall
remain unchanged and separate. The additional trailing `en` is not an authorized alias.
See [priority-2 audit](PRIORITY2_AUDIT.md) for evidence and boundaries.

## Q14 — Organization-number policy and identifier exposure

Related requirements: M6, S4, C1–C3; M7 data guardrail; W1 boundaries

Status: Open. An interim technical policy is implemented in Phase 3C (uncommitted on branch `feature/suda-identity-validation-fredrik`). **D5 must be reviewed before the pull request is opened.**

Phase 3C treats a register organization number as a usable supplier identity only when it is ten digits, passes the Luhn check and has a third digit of at least 2. Everything else stays a separate identity that cannot be strongly matched and requires manual review. See the [Phase 3C section of PROJECT_SPEC.md](../../PROJECT_SPEC.md#organization-number-validation-and-supplier-identity-phase-3c). This is technical structure validation only. It does not verify that an organization is registered, active or the invoiced supplier, and it is not a customer-approved business rule.

| ID | Question | Interim behavior implemented (not an approved rule) |
| :-- | :-- | :-- |
| D1 | Does the Koncerninköp register contain only Swedish organization numbers? | Any other value is `INVALID_FORMAT` and cannot be selected. |
| D2 | Should the 12-digit form `16NNNNNNNNNN` be normalized to ten digits? | No normalization; `INVALID_FORMAT`. |
| D3 | Should personal or coordination number forms, for example sole traders, be accepted as supplier identity? This also concerns data protection. | Not usable (`NOT_ORGANIZATION_NUMBER_FORMAT`); `AMBIGUOUS_MATCH` and manual review. |
| D4 | How should foreign suppliers be identified? | Foreign identifiers are `INVALID_FORMAT`; matching falls back to manual review and the UI calls them not a valid Swedish organization number. |
| D5 | May raw unusable identifiers, including personal-number forms, appear in contract data, the UI and Excel exports? | Candidate and row-level organization-number fields are empty for unusable values. The original value is retained in contract rows, shown in the row-detail contract expander and exported in the `Möjliga avtal` sheet. |
| D6 | Should the `selected_supplier_key` consistency check stop the analysis or degrade the row? | Implemented in Phase 3C as `ValueError`, which stops the analysis. It cannot be triggered by input data. |
| D7 | Should the real register be profiled locally before merge, counting values per status without any value leaving the machine (M7)? | Recommended; not performed. |

**D5 requires review before the pull request.** Unusable identifiers are kept unchanged in contract evidence to preserve source traceability. Some of these values can have personal identity number form, for example sole traders, and therefore may be personal data. They are visible in the review UI's contract details and written to the `Möjliga avtal` export sheet. Before the pull request, the project must decide whether this exposure is acceptable or whether those values should be masked, omitted or handled separately, and how any change preserves traceability to the register row. No masking is implemented, and none should be added without that decision.

Limitations of the interim policy:

- Sole traders, foreign suppliers and 12-digit identifiers can never become `STRONG_MATCH`. This increases manual review and can change sampling keys and contract-period checks on reanalysis.
- A usable status is not legal identity verification. No external register is consulted.
- The group digit and date parts are not validated.
- The consistency check trusts candidate flags produced by the matcher; forged flags are not detected.
- Saved analyses, selections and export snapshots are not rematched; a new analysis is required to apply the policy.

Until resolved: keep the conservative interim behavior, do not treat a usable status as proof of legal identity, and do not change the exposure of raw identifiers without a D5 decision.
