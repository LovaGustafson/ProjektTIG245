# AGENTS.md

## Purpose

This file defines repository-wide working rules for Codex and other coding agents working on TIG245.

It does not define customer business requirements in detail.

Current customer scope and priority are defined in:

`docs/requirements/MOSCOW_CURRENT.md`

Current technical behavior for confirmed requirements is defined in:

`PROJECT_SPEC.md`

---

## Instruction hierarchy

For changes that affect application behavior, customer requirements, data handling, validation, filtering, detection, supplier matching, sampling, traceability, exports or UI semantics:

1. Read the relevant requirement in `docs/requirements/MOSCOW_CURRENT.md` and related unresolved decisions in `docs/requirements/OPEN_QUESTIONS.md`.
2. Read the relevant section of `PROJECT_SPEC.md`.
3. Inspect the existing implementation and relevant tests before changing behavior.

Do not require unrelated documentation to be read for trivial changes such as spelling corrections or isolated documentation formatting.

If information conflicts:

1. Current confirmed customer requirements and scope take priority.
2. `PROJECT_SPEC.md` defines the technical implementation of confirmed requirements.
3. Existing code and tests document current technical behavior but do not override current customer requirements.
4. Historical plans, examples, comments and TODOs do not authorize new functionality.

Do not invent a missing rule in order to resolve a conflict.

Surface the conflict or unresolved question instead.

---

## Task discipline

- Work on one coherent task at a time.
- Modify only the implementation, tests, configuration and documentation necessary for that task.
- Do not refactor unrelated code while implementing a requested change.
- Understand the relevant current behavior before replacing it.
- Do not treat historical implementation plans as a required build order.
- Current customer priorities determine development priority.
- Must Have requirements take priority over Should Have and Could Have work unless explicitly instructed otherwise.
- Do not implement Won't Have functionality unless the project scope is explicitly changed.

Before implementing a customer requirement, identify:

- the relevant requirement ID,
- the confirmed rule being implemented,
- the relevant technical contract,
- any unresolved business decisions that affect the task.

If the business rule is unresolved, do not implement guessed behavior.

---

## Data safety

- Original invoice and source files are read-only.
- Never overwrite, modify or delete source data.
- All transformations must be performed on an internal working copy.
- Do not silently replace original cell values with normalized values.
- Do not commit real invoice data or sensitive reference data to GitHub.
- Use synthetic test data unless explicitly authorized otherwise.

Source occurrences must not silently disappear from the processing chain.

If rows are:

- excluded,
- invalid,
- structurally not applicable,
- ungrouped,
- sampled,
- or otherwise separated,

the reason and relationship to the supplied source material must remain explainable.

---

## Traceability

Protect source-level traceability through:

- ingestion,
- mapping,
- validation,
- filtering,
- verification grouping,
- supplier analysis,
- detection,
- sampling,
- output and export.

Do not assume that any of the following alone are sufficient source provenance:

- `Vernr`,
- `Vrad`,
- `verification_id`,
- `verification_line_id`.

This is especially important where:

- identifiers are duplicated,
- identifiers are missing,
- identifiers are invalid,
- several source occurrences may share the same business identity.

Where source-row identity already exists, do not remove it without an explicitly confirmed replacement.

Do not use `Motp` / `counterparty` as:

- source provenance,
- supplier identity,
- or a substitute for source-row linkage.

---

## Business rules

- Do not invent business rules.
- If a requirement is unclear or awaiting AK confirmation, consult `docs/requirements/OPEN_QUESTIONS.md`, preserve safe current behavior and report the missing decision.
- Adding a TODO does not authorize implementing an assumption.
- Do not guess the meaning of fields such as `Mm`, `Pg`, `Sign`, `Att`, `Ksansv` or `Bild`.
- Do not infer source-system completeness from successfully reading an input file.
- Do not automatically remove possible duplicates until the customer duplicate definition and required disposition are confirmed.
- Do not interpret technical validation failures as customer-approved business deviations unless explicitly defined.
- Do not interpret supplier name matching as procurement or contract compliance.
- Do not claim VGR AI compliance without the applicable VGR guidance and an explicit assessment.
- Follow M7's data guardrail for external AI-assisted development; local storage or read-only access does not establish approval to share project data with an external service.
- Do not promote technical defaults or prototype thresholds into business rules without confirmation.

When a business decision is missing, report what information is required instead of selecting a plausible rule.

---

## Population and source responsibility

AK currently supplies the Excel verification list extracted from Proceedo, the authoritative source system.

The project team does not currently have direct access to the underlying source system.

Therefore:

- the application may verify processing and preservation of the supplied population,
- the application must not claim that the supplied extract is complete relative to the source system unless independent evidence exists,
- successfully reading all supplied rows is not proof of source-system completeness,
- source authenticity and source-system completeness must remain distinct from technical file validation.

---

## Duplicate handling

Possible duplicate identification and duplicate removal are separate behaviors.

The current customer definition of a duplicate is unresolved.

Until the customer duplicate definition is confirmed:

- do not automatically delete duplicate source occurrences,
- do not introduce generic deduplication such as `drop_duplicates()` as a business rule,
- preserve source occurrences,
- preserve provenance,
- keep duplicate identification separate from duplicate disposition,
- report the unresolved business rule.

Any future duplicate-handling change must explicitly define:

- duplicate identity,
- duplicate scope,
- whether multiple rows with the same `Vernr` are legitimate,
- required disposition,
- survivor rule if applicable,
- traceability behavior,
- effect on validation,
- effect on filtering,
- effect on verification grouping,
- effect on sampling,
- effect on export.

---

## Validation, filtering, detection and supplier matching

Keep these concepts separate.

### Validation

Validation answers whether supplied data is structurally or technically usable.

A validation error is not automatically a business deviation.

### Filtering / exclusion

Filtering answers whether a source occurrence is excluded by a confirmed selection rule.

Excluded rows must remain accounted for and explainable.

### Detection

Detection represents the result of an approved control.

Current standardized detection states may include:

- `PASS`
- `FLAGGED`
- `ERROR`
- `NOT_CHECKED`

Unconfirmed or unavailable business controls must not return fabricated PASS or FLAGGED results.

### Supplier matching

Supplier matching describes supplier-identity confidence only.

Supplier matching does not establish:

- procurement compliance,
- contract applicability,
- contract compliance,
- approval of a purchase.

Do not merge these four concepts into one status system or present one as proof of another.

---

## Supplier matching rules

The [Supplier matching section](PROJECT_SPEC.md#12-supplier-matching) defines the current technical contract for supplier analysis, subject to confirmed customer requirements.

Key invariants:

- `Motp` / `counterparty` is metadata, never supplier identity.
- Supplier-name extraction uses the confirmed `header_text` / `Huvudtext` rules.
- Supplier matching and contract compliance are separate concepts.
- Missing or unreadable supplier registers must not fabricate `NO_MATCH`.
- Ambiguous supplier identity must remain ambiguous and require manual review where applicable.
- Source-row linkage uses source-row provenance, not supplier metadata or verification number.
- Original supplier text and source values remain unchanged.
- Registry-date warnings remain separate from supplier-name matching.

Do not extend supplier matching into procurement/compliance approval unless current confirmed requirements explicitly authorize it.

---

## Filtering rules

Current confirmed base filtering includes:

- account `7698`,
- account `7699`,
- configured excluded `verification_type` values.

The feature-package request of 2026-09-24 also confirms exclusions for the exact
internal supplier expressions `Försörjningsförvaltning`, `Fastighetstöd` and `mall`,
with case/whitespace normalization and preserved exclusion evidence. See
PROJECT_SPEC.md section 9. Do not expand these into substring or fuzzy exclusions.

Filtering uses standardized field names, not fixed Excel column positions.

Do not reintroduce historical assumptions such as "Vertyp is column J".

The configured verification-type exclusions are maintained in repository configuration.

Configuration values must not automatically be treated as customer-approved business rules if their confirmation status is unclear.

---

## Code structure

Use the [standardized internal fields](PROJECT_SPEC.md#7-standardized-fields) defined in `PROJECT_SPEC.md`.

Keep major responsibilities separated, including:

- ingestion,
- mapping,
- validation,
- filtering,
- verification grouping,
- detection,
- supplier matching,
- sampling,
- output,
- UI and presentation.

A module should have one primary responsibility.

New detection rules should be implemented separately where practical.

Do not move business decisions into UI code.

Do not introduce a new architectural abstraction solely because a historical design document once proposed it.

Prefer the architecture that actually exists unless a current task intentionally changes it.

Do not create historical planned modules merely to make the repository match an outdated architecture diagram.

---

## Sampling

Sampling is separate from automated analysis.

Current principles include:

- analysis occurs before manual sampling,
- sampling occurs at verification level rather than raw Excel-row level,
- selection must not depend on whether a verification was flagged,
- every 20th eligible verification is selected in the current first-appearance order, using the configured interval of 20.

Do not change the sampling method solely because the customer-facing evidence/documentation requirements remain unresolved (OPEN_QUESTIONS.md Q2).

If a change affects:

- filtering,
- eligible verifications,
- grouping,
- ordering,
- sampling interval,

explicitly assess whether the manual sample also changes.

---

## Error handling

- One invalid invoice or row must not crash the full analysis where safe continuation is possible.
- Errors should be surfaced clearly and logged where appropriate.
- Recoverable errors should preserve as much evidence as possible.
- Every flagged detection result must include a clear reason.
- Missing external or reference data must not be converted into a false business conclusion.
- Unreadable optional registers must produce an unavailable state rather than fabricated negative matches.
- Pipeline-level failures may stop processing where continuing would make the overall result unreliable.

---

## Testing

- Add or update tests for changed functionality.
- Use synthetic data.
- Run relevant targeted tests after making changes.
- Run broader regression tests when a change affects shared pipeline behavior.
- Do not continue a multi-phase implementation while introduced failures remain unexplained.
- Distinguish newly introduced failures from pre-existing or environment-specific failures.
- Do not change tests merely to make an incorrect implementation pass.
- Existing tests describe current technical behavior but do not create missing customer requirements.

Current documented commands include:

```bash
python -m pytest -q
python -m pip check
python -m streamlit run streamlit_app.py
```
