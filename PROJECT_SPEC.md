# PROJECT_SPEC.md

## TIG245 — Current Technical Specification

Last updated: 2026-10-21

---

# 1. Document authority

This document describes the current technical behavior and architecture of the TIG245 prototype, including known limitations. Describing existing behavior does not make it a customer-approved business rule.

Current customer scope and priority are defined in:

`docs/requirements/MOSCOW_CURRENT.md`

Repository-wide agent/development rules are defined in:

`AGENTS.md`

If this document conflicts with a current confirmed customer requirement, the current customer requirement takes priority.

Existing code and tests may reveal current implementation behavior, but they do not independently define customer business rules.

Unresolved customer requirements must not be implemented by inference.

Consult [OPEN_QUESTIONS.md](docs/requirements/OPEN_QUESTIONS.md) for unresolved decisions. The authority order is confirmed customer requirements, this technical contract, implementation/tests, then historical material.

Historical implementation plans are not current development instructions.

---

# 2. Current purpose

The prototype supports review of supplier-related accounting / verification data supplied in Excel format.

The system currently focuses on:

- reading supplied Excel data,
- preserving original source values,
- standardizing known columns internally,
- validating technical data quality,
- applying confirmed exclusion/filter rules,
- grouping rows into verifications,
- running currently supported checks,
- performing supplier-name matching against an optional supplier/contract register,
- producing a reproducible systematic or randomized manual sample,
- presenting review results in Streamlit,
- exporting review material.

The prototype must not modify the supplied source file.

Proceedo is the authoritative source system. The customer performs the extraction and supplies the Excel file; the project has no direct Proceedo access. The prototype supports human review, not autonomous transaction approval, compliance decisions or audit conclusions.

---

# 3. Current scope boundaries

The current prototype is a local file-based application.

Current scope does not include:

- production integration with Proceedo or another source system,
- independent verification that AK's extract is complete relative to the source system,
- fully automated audit/control processes,
- completed attestation/compliance approval,
- automatic modification of invoices/source data,
- OCR-based invoice interpretation,
- advanced AI/ML decision logic,
- unattended production operation.

Technical scaffolding or historical documentation for future capabilities does not change these boundaries.

---

# 4. Application entrypoints

The current application has two primary entrypoints.

## CLI

`src/main.py`

Provides command-line execution of the analysis pipeline.

Run `python -m src.main INPUT.xlsx --output-dir NEW_DIRECTORY` from the repository root. `python src/main.py` is also supported. Options include settings, worksheet and local reference-register paths; see `python -m src.main --help`.

## Streamlit UI

`streamlit_app.py`

Provides the interactive prototype used for file upload, analysis, filtering, review and export.

Run `python -m streamlit run streamlit_app.py`. Analysis is user-triggered; changing base verification-type exclusions reruns it. Temporary view filters do not change analysis, sampling or exports. There is no scheduled ingestion or unattended dashboard refresh.

Shared analysis logic should remain outside presentation-specific code.

---

# 5. Current processing pipeline

The current high-level processing flow is:

```text
Supplied Excel file
        ↓
Excel ingestion / header detection
        ↓
Column mapping
        ↓
Validation
        ↓
Filtering / exclusions
        ↓
Retained transaction rows
        ↓
Supplier analysis per retained row, if a supplied register is usable
        ↓
Verification grouping
        ↓
Detection
        ↓
Manual sampling
        ↓
Excel output / Streamlit presentation
```

`src/pipeline.py` orchestrates this flow and returns `PipelineResult`, including original and standardized tables, validation, filtering, ungrouped rows, verifications, detection, sample, supplier/contract-date evidence, `RunSummary`, sampling positions, source-file context and the register snapshot used. It loads explicitly supplied image/reference evidence before detection; loading evidence does not confirm a business rule.

`src/ui_support.py` runs the pipeline on temporary upload copies and supplies the Streamlit review workbooks. The UI defers workbook serialization until download: each run owns a separate snapshot of the completed result and caches only requested report bytes. CLI/default pipeline callers still generate reports immediately. `streamlit_app.py`, `src/presentation.py` and the `src/ui_*.py` modules present these results.

# 6. Ingestion and source preservation

`src/ingestion/excel_reader.py` reads one `.xlsx` worksheet, defaulting to the first. It scans the first 50 rows for the earliest row with the highest number of distinct recognized header fields, requiring at least three for invoice input; otherwise it uses the first row. Metadata above the selected header is not included in the parsed population. Worksheets are not combined.

All rows below that header are read. Named columns and populated unnamed columns survive; only unnamed empty columns are removed. Duplicate named headers, blank cells, text identifiers, formula expressions and Excel errors are retained. Excel-native dates/numbers are decoded; formatting is not preserved and formulas are not evaluated.

Source files are opened read-only. Mapping, filtering and analysis work on copies and must not overwrite source values with comparison keys. `original_data` is the parsed table, not a complete copy of workbook metadata or formatting. The reader retains the selected sheet name and one-based header row in DataFrame attributes. The pipeline records source filename and SHA-256; Streamlit additionally retains the uploaded bytes in session memory.

`src/ingestion/reference_reader.py` reads local Excel/CSV reference tables with technical loading states; successful loading does not prove schema approval or completeness. `src/ingestion/image_reader.py` reads local images/PDFs without OCR. `Bild` linkage is not inferred.

# 7. Standardized fields

`src/mapping/column_mapper.py` trims surrounding header whitespace and maps the following names. Already-standardized names and unknown columns remain available; duplicate headers remain visible to validation. Source cell values are unchanged.

| Source header | Internal field |
| --- | --- |
| `Vernr` | `verification_id` |
| `Vrad` | `verification_line_id` |
| `Verdatum` (also `VerDat`, `VerDatum`) | `verification_date` |
| `Utfall` | `amount` |
| `Konto` | `account` |
| `Ansvar` | `responsibility` |
| `Motp` | `counterparty` |
| `Inv` | `investment` |
| `Proj` | `project` |
| `Aktiv` | `activity` |
| `Ksansv` | `cost_responsibility` |
| `Mm` | `vat_code` |
| `Pg` | `posting_group` |
| `Vertyp` | `verification_type` |
| `Huvudtext` | `header_text` |
| `Radtext` | `line_text` |
| `Bild` | `image_reference` |
| `Sign` | `signature` |
| `Att` | `attestation` |

These are existing technical labels. They do not resolve the business meanings of `Mm`, `Pg`, `Sign`, `Att`, `Ksansv` or `Bild` (Q10). `Motp` is metadata, not supplier identity or source provenance.

# 8. Technical validation and duplicate semantics

`src/validation/validator.py` returns schema errors and positional row metadata without editing or removing rows. Its five mandatory technical fields are `verification_id`, `verification_line_id`, `verification_date`, `amount` and `account`; this is separate from the unresolved business `required_fields` setting.

- Missing/ambiguous required columns and missing/invalid values are reported.
- Identifier/account checks accept nonblank text or finite integral Excel numbers. `src/mapping/identifiers.py` normalizes numeric comparison keys without rounding; text keys retain spelling, whitespace and leading zeros.
- Line IDs must represent finite integers; no positivity/range rule is imposed. Amounts accept finite numeric values, decimal-point text and exponents; locale separators are not inferred.
- Dates accept native dates/datetimes and ISO text, or the caller's explicit format. Numeric date serials are not guessed.
- Recognized structural rows receive `NOT_APPLICABLE` and a reason. Other row results are `VALID` or `INVALID`.
- Repeated normalized `verification_id + verification_line_id` pairs receive `duplicate_identity` errors on every occurrence, including occurrences with other errors. Incomplete/invalid identities are not compared for uniqueness.

This last check is a technical identity collision, not the customer definition of a duplicate. Occurrences are retained. Automatic duplicate removal is prohibited until Q1 is resolved; no survivor rule exists.

Technical validation is not a business deviation or approval. Validation must not silently remove source occurrences. Source formats, mandatory business information and the structural-row boundary remain subject to Q5/Q10.

# 9. Filtering and exclusions

`src/filtering/filter_engine.py` applies account and selected `verification_type` exclusions using standardized fields, never fixed Excel column positions. Confirmed account exclusions are `7698` and `7699`. The standard verification-type set is the 44 values in `config/settings.yaml` under `excluded_verification_types`, including `FBFM`. The 2026-10-12 request adds `LR91S` and `LR95S` to the existing defaults. Both remain selectable for reinclusion through the existing UI. They affect the retained population, grouping and all manual sampling methods through the same filter rules, with preserved source rows and overlapping exclusion reasons.

Account comparisons normalize integral numeric representations and surrounding whitespace. Verification-type comparisons trim surrounding whitespace. Blank filter values do not match these exclusions. Missing/ambiguous filter columns produce explicit messages; other applicable rules can still run, so filtering may be incomplete.

`FilterResult` retains included and excluded tables, original indexes, per-position reasons, per-rule counts and matching positions. Reasons can overlap; the total excluded count counts each occurrence once. Exclusion is separate from validation and detection.

`src/filtering/transaction_rows.py` also recognizes blank report rows, repeated headers, labeled totals/report rows and a footer pattern. Validation and filtering share this recognition. These rows are currently retained as excluded with reasons, not deleted. This documents existing technical classification, not a resolved customer rule for every empty/invalid record (Q5).

The UI can change verification-type selections and rerun analysis; configured account exclusions remain in effect. Approval/evidence for changes to exclusion selections remains Q8. Such changes can alter grouping and the manual sample. Technical configurability alone is not business authorization.

The 2026-09-24 feature-package request additionally confirms exclusion of `Försörjningsförvaltning`, `Fastighetstöd` and `mall`, configured in `excluded_internal_suppliers`. `src/filtering/internal_suppliers.py` compares the extracted supplier expression (or the whole cleaned header when no marker exists), using Unicode NFKC, case folding and whitespace removal. The entire expression must match; there is no substring, fuzzy, legal-form or spelling expansion. Other names remain included. Missing/ambiguous `header_text` produces an explicit incomplete-filtering warning. The reason `Intern leverantör: <expression>` and per-rule positions/counts survive; overlapping rules count once in the excluded population. These exclusions run before matching, grouping and sampling and can change the manual sample.

# 10. Verification grouping and eligibility

`src/verification/verification_builder.py` produces `Verification` objects (`src/models/verification.py`) grouped by the normalized `verification_id` comparison key. Groups follow first appearance in the retained table; rows within each group retain their input order, values and indexes. Rows are neither deduplicated nor aggregated, and line IDs are not sorted.

The pipeline routes retained rows with unusable verification IDs to `ungrouped_data`; they remain in cleaned/review data but are not detection or sampling units. A missing/ambiguous verification-ID column prevents grouping. Invalid amounts, dates, line IDs and technical duplicate-identity errors alone do not remove otherwise groupable rows.

The builder itself retains null keys if called directly; the pipeline performs the routing described above. Grouping by a business key does not prove source identity or settle customer duplicate semantics. Final disposition of ungrouped records remains Q5.

# 11. Detection

`src/detection/detection_engine.py` runs the enabled rules for each grouped verification. `src/models/result.py` defines `CheckResult` with verification ID, check type, status, reason and optional line ID, field and row position. Every result requires a nonblank reason.

| Status | Meaning |
| --- | --- |
| `PASS` | The implemented check passed within its configured scope. |
| `FLAGGED` | The check returned a finding with an explanatory reason. |
| `ERROR` | The check could not complete reliably. |
| `NOT_CHECKED` | The control was not assessed, for example because its prerequisites/rules are unconfirmed. |

`NOT_CHECKED` is not `PASS`, and neither technical success nor an absence of flags is final business approval. The technical summary precedence is `FLAGGED > ERROR > NOT_CHECKED > PASS`; no results means `NOT_CHECKED`. Disabled rules are recorded separately and do not contribute a status. Individual results must remain available to explain the summary.

The default rules in `src/detection/rules/` are `required_fields_check.py`, `image_check.py`, `attestation_check.py` and `supplier_check.py`. Unconfirmed presence policies return `NOT_CHECKED`; explicitly supplied confirmed policies can check required-field/image-reference presence. Image-reference PASS does not establish that a document exists or is sufficient. Attestation and procurement compliance remain unassessed. Existing scaffolding is not permission to implement Won't Have controls.

Rule exceptions, malformed results and empty rule output become `ERROR`; prior results survive and later rules continue. Validation findings are not automatically converted to detection flags.

# 12. Supplier matching

`src/ingestion/contract_reader.py` loads the optional Koncerninköp register using configured header aliases. Supplier-name and organization-number columns must be present and unambiguous. Missing contract-detail columns produce warnings. Names alone do not merge legal entities; only technically usable organization numbers group register rows, while missing or unusable numbers retain separate identities (see [Organization-number validation and supplier identity](#organization-number-validation-and-supplier-identity-phase-3c)). Contract rows are not deduplicated.

`src/supplier_matching/` separates extraction, normalization, matching, date warnings, settings and row analysis; `src/models/supplier.py` defines their result models.

- Extraction uses only text before the first `Prelb`/`Slutk` marker in `header_text`/`Huvudtext`, case-insensitively. `Slutk123` and `Slutk 123` are both recognized; existing standalone markers remain supported. Missing markers/candidates remain unidentified. `normalize_header_text` separately removes numbered Slutk occurrences and collapses whitespace on a comparison copy, exported as `header_text_normalized`. Original Huvudtext is preserved. `Motp` is never a matching key.
- Comparison normalization preserves original text and Swedish diacritics; it normalizes Unicode, case, whitespace, punctuation and explicit equivalent legal-form names without treating distinct legal forms as equivalent.
- Matching ranks exact normalized names, eligible prefixes and deterministic fuzzy candidates. Current technical defaults are prefix length 8, two tokens and 60% coverage; fuzzy strong/candidate thresholds are 0.94/0.82. Additional token and legal-form safeguards apply in `matcher.py`. These are prototype settings, not customer compliance thresholds or probabilities.
- The controlled supplier-reliability implementation approved on 2026-10-14 adds a **strong fuzzy eligibility guard per register alias, before representative selection within an organization** (S4/C3, M6 evidence). The existing full-name `SequenceMatcher(..., autojunk=False)` score, discovery threshold, normalization, legal-form checks, exact/prefix behavior and multiple-identity ambiguity remain unchanged. The guard can only downgrade eligibility; it cannot promote a candidate or remove one from manual review.
- Strong fuzzy eligibility still requires the configured raw-score threshold, at least two core name tokens, equal core token counts and no unconfirmed explicit legal form. After the existing legal-form split, identical tokens are cancelled across all positions using their occurrence counts. No unmatched tokens passes the added guard. Otherwise exactly one unmatched pair is allowed: both tokens must have at least six characters, with one insertion/deletion/substitution and token `SequenceMatcher` similarity of at least 0.90. **One adjacent character transposition is an explicit exception to the token-score threshold**, still requiring both tokens to have at least six characters. Multiple unmatched pairs, two ordinary edits and nonadjacent swaps fail. No token is discarded for being geographic or generic, and the first token has no special role in this added guard. (The separate Phase 3D.1 candidate-relevance check below uses configured geographic descriptors only to decide whether a weak fuzzy candidate is discovered; it never affects this strength guard.)
- These are conservative technical pilot criteria, not identity probabilities or universal spelling rules. `ATEA Stockholm Sverige AB` / `Telia Stockholm Sverige AB` retains raw score `0.941176` and its candidate but becomes `AMBIGUOUS_MATCH`. `Securitas Svergie AB` / `Securitas Sverige AB` remains strong via the adjacent-swap exception. Plausible short typos such as `Acem` / `Acme`, substitutions below 0.90 (including a single substitution in a nine-character token), and several genuine typos require review. A failed guard records: `Leverantörsnamnen är delvis lika, men särskiljande namnled skiljer sig åt.` Existing UI and exports carry this reason and the raw score. Selecting a different eligible alias can change the representative name and its reported score, without changing any pair's score formula.
- `STRONG_MATCH` selects one eligible registered supplier identity with an organization number. The existing single-candidate decision remains supported. The controlled Phase 3B rule approved on 2026-10-16 also permits one unique `exact_normalized` identity despite weaker alternatives: exactly one identity must have an exact normalized alias, that identity must be strong-eligible under the organization-number rules, and no competing identity may have strong name evidence. Since Phase 3C, a competitor's strong name blocks even when its organization number is missing or unusable. Additional exact identities (including exact records without usable organization numbers) and competing strong fuzzy/prefix identities retain `AMBIGUOUS_MATCH`, with no selected identity. A score of 1.0 alone does not select an identity. Other states remain `NO_MATCH` and `SUPPLIER_NOT_IDENTIFIED`.
- Candidate discovery, raw scores, ranking, register grouping, aliases and all Phase 2 fuzzy safeguards are unchanged by exact prioritization. Candidate representatives retain any strong-eligible alias before the final decision, so a competing alias with strong name evidence blocks promotion regardless of registry order. Every alternative remains in candidate and contract evidence. `SupplierMatch.selected_supplier_key` records the explicit selected identity only for strong decisions; consumers must not infer it from score or candidate order. Existing row-level `matched_supplier_name`, `matched_organization_number` and `contract_count` describe that selected identity; export columns are unchanged.
- Missing, unreadable or unusable registers produce unavailable matching, never fabricated `NO_MATCH`. All retained rows can receive supplier analysis when the register is usable, including ungrouped rows.
- Candidate evidence includes possible contract rows; no contract is automatically selected. Identity matching does not establish procurement compliance, contract applicability or transaction approval. The verification-level supplier compliance check remains `NOT_CHECKED`.
- The review UI prioritizes the source supplier name, register supplier name, friendly match result, unchanged score (0–1) and a readable explanation. Its source-row list still shows the first existing ranked candidate, marked `(kandidat)`, for ambiguous matches in `Leverantör i avtalsregistret`; all candidates appear separately in the overview's candidate table and row details. Missing candidates and unextracted names are explicit; no score is invented. `Visa tekniska matchningsdetaljer` preserves the original row/candidate reasons, methods, status codes, normalized source name, candidate counts, register organization numbers and source positions. Explanations distinguish row ambiguity from candidate similarity, including missing and technically unusable register organization numbers. This presentation neither selects a supplier nor verifies legal identity or purchase-to-contract applicability; backend results and export structures remain unchanged.
- For a strong exact decision with weaker alternatives, the selected candidate displays `Stark namnmatchning`; unselected identities display `Alternativ kandidat – inte vald` with their own candidate reason and unchanged score. Identity comparison uses the recorded selected organization number, never the display order or supplier name. The row explanation records exact prioritization and retained alternatives. Technical candidate comparisons still attach the source row's `supplier_match_status`, explicitly described as row-level evidence rather than a candidate's selection status.
- Transactions after the registry snapshot receive a separate freshness warning. Missing/invalid transaction dates or missing snapshot dates yield `UNKNOWN` for the date check and do not change supplier identity status.

Row evidence joins through retained source indexes, not verification or supplier identity. Q10 covers unresolved field/control meanings; M7/Q9 governs any future AI use.

Downstream rules are unchanged by the fuzzy guard. A downgraded row has no selected organization/name, retains all candidate/contract evidence, and its contract periods are `NOT_CHECKED`. Organization-based classification no longer applies to that row; exact confirmed source-name rules still can. Sampling uses its existing normalized-name fallback instead of an organization key, so uniqueness, mixed-identity usability, classification/quota decisions and sample membership may change **on reanalysis**, even with the same seed. A saved analysis/selection and its export snapshot are not retroactively rematched or rewritten; a new analysis is needed to apply the safeguard. Synthetic integration tests cover both sampling methods, saved plans, all existing workbook filenames, source provenance and the UI explanation. Contract-policy questions in Q12 remain unresolved.

## Organization-number validation and supplier identity (Phase 3C)

Phase 3C adds technical validation of register organization numbers and restricts which register values can act as a supplier identity. Name normalization, candidate discovery, raw scores, ranking, the fuzzy guard, contract-period rules, sampling algorithms and export columns are unchanged. The policy below is the **interim technical policy approved for the Phase 3C implementation**. It is not a confirmed customer business rule; [Q14](docs/requirements/OPEN_QUESTIONS.md#q14--organization-number-policy-and-identifier-exposure) records the open decisions D1–D7.

**Technical validation.** `classify_organization_number` in `src/ingestion/contract_reader.py` formats a value with the unchanged `organization_key` (spaces and hyphens removed; integer-valued Excel numbers become digits) and returns the formatted key and one status:

| Status | Rule | Usable identity |
| :-- | :-- | :-- |
| `MISSING` | Missing, blank or boolean value | No |
| `INVALID_FORMAT` | Not exactly ten digits after formatting, for example `SAKNAS`, `N/A`, `-`, the `+` separator, 9/11/12 digits including `16`-prefixed forms, and foreign identifiers | No (D1, D2, D4) |
| `INVALID_CHECKSUM` | Ten digits, Luhn check digit fails | No |
| `NOT_ORGANIZATION_NUMBER_FORMAT` | Ten digits, Luhn passes, third digit 0 or 1: personal or coordination number form (including sole traders) or `0000000000` | No (D3) |
| `ORGANIZATION_NUMBER_FORMAT` | Ten digits, Luhn passes, third digit at least 2 | **Yes** |

`USABLE_ORGANIZATION_NUMBER_STATUSES` contains only `ORGANIZATION_NUMBER_FORMAT`. The group digit and any date part are not checked. The status name `NOT_ORGANIZATION_NUMBER_FORMAT` deliberately does not assert that a value is a personal identity number.

**Technical validation is not legal identity verification.** A usable status only means that the value has the structure of a Swedish organization number. It does not establish that the organization is registered or active, that it is the legal entity named in the register, or that it is the supplier on the invoice. No external register is consulted. UI, exports and reports must not present a usable status as verified legal identity, and supplier matching still does not establish procurement or contract compliance.

**Safe identity grouping.** `registry_from_frame` groups register rows as `org:<key>` only when the status is usable. Every other row becomes its own `unknown:<register row position>` identity, so unrelated rows sharing a placeholder such as `SAKNAS` or a personal-number form are never merged. For these identities `Supplier.organization_number` is `None`, and `Supplier.organization_number_status` keeps the status for explanations only; it controls no decision. `registry.issues` records each affected register row: missing numbers keep the existing message, and other statuses record `organisationsnumret är inte tekniskt användbart (<STATUS>)`. Issue texts name the status, never the value. The register source frame and the contract rows keep the original value unchanged (D5).

**Name evidence and identity eligibility.** `SupplierCandidate.name_strong` records whether the name evidence alone is strong after the existing legal-form checks and fuzzy guard. `strong_eligible` additionally requires a usable organization number and keeps its exported meaning; `name_strong` is not exported. For identities with usable numbers both flags are equal.

**Strong competing supplier protection.** `select_strong_candidate` in `src/supplier_matching/matcher.py` is the single selection function used by the matcher. It selects a sole strong-eligible candidate, or the unique `exact_normalized` identity when that identity is strong-eligible and no other identity has `name_strong`. Consequences:

- A competitor with a strong name blocks exact priority even when its number is missing or unusable. This is a deliberate tightening of Phase 3B, where only strong-eligible competitors blocked. Weak competitors still do not block.
- A candidate whose number is missing or unusable can never be selected, even as the only candidate. The row becomes `AMBIGUOUS_MATCH` with the candidate, score and contract evidence retained for manual review.
- Candidate reasons state `Organisationsnummer saknas i registret.` for missing numbers and `Organisationsnumret i registret är inte ett tekniskt giltigt organisationsnummer.` for other unusable statuses. Neither contains the register value.

**`selected_supplier_key` consistency invariant.** `analyze_suppliers` recomputes `select_strong_candidate` on each match result's candidates. It requires `STRONG_MATCH` exactly when a candidate is selected, and `selected_supplier_key` equal to that candidate's key. Any mismatch raises `ValueError` naming only the source row position. The analysis stops: the CLI exits with an error message and the Streamlit analysis fails. A mismatch can arise only from a programming error or an injected matcher, never from input data. Limitation: the candidate flags themselves come from the matcher and are trusted; forged flags are not detected (D6).

**Classification rule validation.** `validate_classification_rules` in `src/supplier_matching/view_scope.py` serves `supplier_view_rules`, `sampling_supplier_rules` and explicit rules passed to `plan_manual_sample` and `plan_random_sample`. An `organization_number` rule value must have a usable status; otherwise `ValueError` names the rule ID and status, never the value, and one invalid rule rejects the whole list. The `comparison_key` is the compact ten-digit key and the configured value is preserved. Supplier-name rules and the existing shape checks are unchanged. Both production rule lists are empty, so no current configuration is affected.

**User-facing explanations.** The review UI translates the unusable-number reason into: `Organisationsnumret i avtalsregistret är inte ett giltigt svenskt organisationsnummer, vilket hindrar en stark namnmatchning. Numret kan vara felskrivet, ofullständigt eller ha ett annat format.` The missing-number explanation is unchanged. Both the candidate table and the source-row review table use this translation. Candidate and row-level organization-number fields are empty for unusable numbers, so the candidate panel and its technical details do not show the value. The row-detail contract expander (`Möjliga avtal`) still shows the original register value (D5).

**Effects on contracts, sampling and exports.**

- Contract periods: `check_contract_period` is unchanged. Only the selected identity is identity-confirmed, and identities with unusable numbers are never selected, so their contracts are always `NOT_CHECKED`, never `PASS` or `FLAGGED`.
- Sampling and classification: algorithms are unchanged. Rows that were previously strong only through an unusable number become ambiguous and use the existing `name:` fallback key. Unrelated suppliers that shared a placeholder no longer share an `org:` key or become false `DUPLICATE_SUPPLIER` decisions, and organization-based classification no longer applies to them. Strong/ambiguous counts, classification, quota decisions and sample membership may therefore change **on reanalysis**, even with the same seed. Saved analyses, selections and export snapshots are not rematched.
- Exports: no columns are added or removed. `Leverantörskandidater.organization_number` and `Leverantörsmatchning.matched_organization_number` are empty for unusable numbers. The `Möjliga avtal` sheet keeps the original register value, including personal-number forms (D5).

**Preservation of Phase 3B safeguards.** For identities with usable numbers `name_strong == strong_eligible`, so all Phase 3B decisions between valid identities are unchanged, as are scores, ranking and the fuzzy guard. Regression coverage includes the Phase 3B exact-priority cases in both register orders, the selection function across all candidate permutations, and the full supplier-reliability suite. Test fixtures use synthetic Luhn-valid numbers from `tests/synthetic_org.py`; their migration changed no expected match status.

## Supplier-name structure and candidate relevance (Phase 3D.1)

Phase 3D.1 separates the structure of supplier names to judge whether a candidate is relevant at all. It adds no strong-match rule: methods, raw scores, name strength, strong eligibility, `select_strong_candidate`, organization-number validation, grouping, contract isolation, sampling and export schemas are unchanged.

**Name structure.** `src/supplier_matching/name_structure.py` analyzes a normalized comparison copy (original names and `normalize_supplier` output are never altered). `split_legal_form` separates a trailing legal form, so AB, HB and KB stay distinct and only the existing Aktiebolag(et)→AB equivalence applies. Every later word that is a configured geographic descriptor, a one-typo variant of one (one edit or adjacent swap, at least six characters), or a truncation of one in the final position (at least four characters) is a descriptor. The first word is always distinctive, so a leading geographic word ("Sverige Trafik AB") is kept. Everything else is the distinctive name, including additional words such as Technology, Supply or Bygg.

**Descriptors.** `supplier_matching.geographic_descriptors` in configuration (default `["Sverige"]`, the descriptor named by the stakeholder) is validated as single words that are not legal forms. Cities, regions and other words are not descriptors unless explicitly added after confirmation.

**Candidate relevance.** Candidate discovery, alias consolidation per identity and ranking are unchanged. A candidate reached only through the full-name similarity threshold (no shared first word of the related-name length, no equal core, not name-strong) is marked relevant only when its distinctive name is plausibly related to the query's. The relation is symmetric and deliberately generous: equal, one edit or adjacent swap apart, at or above the existing candidate threshold in either comparison direction, equal after folding diacritics (Åkeriet/Akeriet), sharing the shorter distinctive name word for word from its first word, or an abbreviation, truncation, compound or initials of it (space-free forms equal or one a prefix of the other, or words aligned one by one as prefixes: "Alfa B"/"Alfa Bygg", "Nordv"/"Nordverk", "Alfa Bygg"/"Alfa Byggservice", "A.B.C"/"ABC"). An identity is relevant if any of its aliases is. Exact, prefix and name-strong candidates are always relevant. Shared legal or geographic words alone therefore do not make a candidate relevant (for example "Atea Sverige AB" vs "Tele2 Sverige AB", fuzzy 0.8387). Discovery or relevance is never identity confirmation.

**Decision preservation.** Relevance filtering may only remove unrelated evidence; it must never independently create a `STRONG_MATCH`. The matcher decides with `select_strong_candidate` on the complete, unfiltered candidate set. It returns the relevant subset only when the same function selects the identical identity (or none) on that subset; otherwise it returns the complete set, including unrelated candidates. The returned candidates therefore always reproduce the returned decision, and the `selected_supplier_key` consistency check in `analysis.py` is unchanged. Exact matches drop unrelated alternatives; a sole strong-named identity that was blocked by an unrelated candidate stays `AMBIGUOUS_MATCH` with all its original evidence.

**Consequences on reanalysis.** Rows whose candidates were all unrelated move from `AMBIGUOUS_MATCH` to `NO_MATCH`; they remain in the exported non-strong rows. Unrelated alternatives of an exact match disappear from candidate and contract evidence (they were never assessed). No row becomes `STRONG_MATCH` and no selected identity changes, so contract assessment, sampling keys and organization classification are unaffected. Saved analyses and exports are not rematched. The existing expectation "ATEA Sverige AB" vs "Telia Sverige AB" changed deliberately from `AMBIGUOUS_MATCH` to `NO_MATCH`. Phase 3D.1 authorizes no new strong-match rule; distinctive-name promotion (for example a missing geographic word or legal form) is deferred to Phase 3D.2 and [Q15](docs/requirements/OPEN_QUESTIONS.md#q15--supplier-name-structure-policy-phase-3d).

## Safe structured supplier matching (Phase 3D.2)

The Phase 3D.2 implementation request confirms a limited extension within M6/S4/C3,
with exact-priority decision A and safe-prefix decision B. This section extends
the earlier phase contracts above; it does not change their historical scope.

**New name evidence.** `structured_names_match` compares normalized copies using
the existing name structure. Nonempty distinctive token sequences must be exactly
equal, in order and including multiplicity and diacritics; a legal designation
alone cannot supply distinctive evidence. Only exact configured
geographic descriptors may differ; the approved vocabulary remains `Sverige`.
Either side may omit a trailing legal form; explicit forms on both sides must
agree after existing equivalent-form normalization. Explicit AB/HB/KB conflicts,
extra distinctive words, spelling edits and diacritic folding do not supply new
strong evidence. Descriptor typo/truncation recognition remains useful for
relevance but cannot independently justify a new structural promotion. Existing
safe prefixes (including truncated distinctive components) and the legacy fuzzy
guard remain supported; this phase does not remove their established eligibility.

**Discovery and competition.** When at least one nonidentical alias satisfies the
structured comparison, the matcher also discovers plausible distinctive-name
alternatives below the old full-name score threshold, using the existing symmetric
relevance relation. Such `structural_alternative` candidates cannot be selected;
they can block a nonexact selection. No shared-first-word test alone supplies
strong evidence. `structured_name` candidates require a usable register identity,
and are selectable only as the sole candidate identity under the centralized
`select_strong_candidate`. Missing/invalid-number competitors remain separate
identities and can still block. Aliases sharing a valid organization number are
one identity with every contract occurrence retained. New structural alias ties
are resolved deterministically; legacy strong aliases outrank new evidence.

**Exact priority (decision A).** If any exact-normalized alias exists, structural
promotion is suppressed and all existing name-strength/blocking evidence is
preserved. Newly discovered alternatives remain visible with their contracts.
The selection function also excludes structural-only strength from exact-priority
blocking. Thus `Bonliva AB` can still select the exact identity despite a different
identity named `Bonliva Sverige AB`; existing exact collisions and strong legacy
prefix/fuzzy competitors still block, including competitors with unusable numbers.
The existing row-reason field records the potential different-legal-identity
conflict when a returned representative is structurally equivalent. No dedicated
conflict status, counter or UI workflow is introduced. Absence of that diagnostic
is not proof of absence of conflicting register aliases (Q15).

**Preservation and consequences.** Phase 3D.1's decision-preserving relevance
filter and Phase 3C's selected-key consistency check still use the same selection
function. Relevance removal alone cannot create a strong decision. No global
threshold, source value, register grouping, invoice-side organization number,
output column or saved analysis is changed. Existing score formulas are retained:
a newly discovered pair reports the normalized full-name SequenceMatcher score;
an upgraded existing candidate retains its prior score, including prefix coverage.
These scores are not legal-identity probabilities. A structurally justified strong
match can therefore have a score below the fuzzy thresholds.

On reanalysis, approved descriptor/legal-form omissions can move `NO_MATCH` or
`AMBIGUOUS_MATCH` to `STRONG_MATCH`; additional plausible identities can instead
retain or introduce ambiguity. Only selected suppliers' contract periods may be
assessed. Organization sampling keys, uniqueness, classification, quotas and
uncertain-export membership can consequently change. Sampling algorithms,
contract applicability/compliance limits, export schemas, source provenance and
saved analyses/export snapshots retain their existing contracts. Name matching
does not verify legal identity, even with one technically usable register identity.
Q14's interim organization-number policy and Q12's date-policy questions remain.

## Register source selection

`src/ingestion/registry_source.py` isolates source selection from identity matching. `supplier_matching.default_registry_path` selects a local default file (relative paths resolve against the project root); an optional `default_registry_name` controls its label. The configured path is `data/reference/koncerninkop.xlsx`. No real register is distributed in Git; the file must exist locally before default matching is available. UI uploads replace the default. The final upload cleanup removes the dedicated remove/restore buttons and their enable/version state; the native uploader still supports replacement and clearing. Without an upload, normal configured-default selection applies. Missing defaults remain unavailable. CLI supports `--supplier-register` and `--no-default-registry`; shared source-selection modes remain unchanged.

An immutable `RegistrySource` retains the exact bytes, source kind/name, snapshot date and SHA-256 for the run. UI refiltering reuses these bytes even if the local default file subsequently changes. Source/register changes clear stale results. Missing, disabled or unreadable sources remain unavailable; they do not trigger a substitute register or fabricated negative matches. Register date is explicit configuration/UI input, not inferred from filenames. Export metadata also records the parsed register sheet and header row when available.

The upload UI labels the existing single-file invoice uploader `Här laddar du upp
fakturaunderlaget` and the register uploader `Här laddar du upp koncernavtalsregistret`.
The visible format guidance is `I detta verktyg används Excel-filer (.xlsx)`; the
invoice help retains first-worksheet/all-row processing information. A Swedish
`Max <configured server.maxUploadSize> MB per fil` caption accompanies each native
uploader. Streamlit 1.63 has no public option to hide its native size/type text.
CSS scoped to the `invoice_upload_panel` and `registry_upload_panel` containers
hides only `stFileUploaderDropzoneInstructions`, which in that version contains
the size/type metadata. Labels, input controls, upload buttons and drag feedback
remain intact; the Swedish format/size guidance remains accessible. This internal
test ID needs checking on Streamlit upgrades. No JavaScript is injected.

The UI uses existing register validation, cached per session and source/configuration,
before displaying an active filename or extraction-date control. A missing default
shows only an instruction to upload a register; an unusable register gets a readable
replacement instruction. Unavailable registers have no date field. The
unverified prototype snapshot date `2026-08-31` has been removed from configuration;
the default is null. An explicitly configured known date applies to the default
register only. Each uploaded replacement requests its own date, initially blank;
user-entered dates are retained per source within the session. A blank date remains
unknown in the explicit source snapshot rather than falling back to another
register's configured date. The UI explains that the existing freshness check is
`UNKNOWN` without a date; analysis may still proceed. Changing the date clears the
current UI result, while prior analysis/export snapshots remain unchanged. Date
warning outcomes can change on reanalysis because the input date changes; supplier
matching, contract-period rules, sampling, classification and export calculations
are unchanged. Register extraction dates never substitute for contract dates.

## Contract-period evidence

The 2026-09-24 request authorizes date comparisons, separately from purchase-to-contract applicability. `src/supplier_matching/contract_period.py` compares each register contract of a strongly identified supplier with each retained row's verification date. Multiple contracts are preserved and checked separately; none is selected as the purchase's governing contract. Ambiguous candidates remain `NOT_CHECKED`.

Phase 3B restricts the identity-confirmed input to contracts whose supplier key equals the explicitly selected `SupplierMatch.selected_supplier_key`. Unselected identities' contracts remain `NOT_CHECKED`, including those with otherwise valid or expired dates; their reason records that the candidate was not selected. In contract evidence, `supplier_match_status` is `STRONG_MATCH` only for the selected identity and `AMBIGUOUS_MATCH` for unselected identities, even if the source-row match is strong. All original contract rows/dates and source links remain available. Missing selected contracts or dates cannot borrow an alternative identity's contract. Existing date/boundary/extension rules are unchanged: selected contracts may still be `FLAGGED` or `NOT_CHECKED`. Backend, saved analysis, UI and workbook exports consume the same prepared results.

Exact priority can change source-level strong/uncertain counts, organization-based classification and sampling keys on a new analysis. Sampling algorithms, classification rules, quotas and export schemas remain unchanged. Saved selections and lazy export snapshots are not rematched; even an explicitly regenerated random sample uses its saved analysis. Reanalysis is required to apply a new matching decision. Regression expectations for unique exact identities plus only weak alternatives have been updated deliberately; exact collisions and independently strong competing identities retain conservative tests.

The contract reader preserves `start_date`, `end_date` and `final_end_date` (including the alias `Sista slutdatum`). Evidence includes original dates, parsed verification date, evaluated period, end-date basis, boundary-policy setting, rule identifier, reason and the existing `PASS`/`FLAGGED`/`NOT_CHECKED` status vocabulary. `PASS` means within that register period only; `FLAGGED` means before or after it. These results do not change supplier confidence or manufacture procurement-compliance/detection conclusions. Summary counts explicitly use **contract comparisons**, not invoices or unique contracts.

Pending Q12, `contract_period.end_date_field` and `inclusive_boundaries` remain null. An ordinary end date with no final date, or two agreeing end dates, supports checks strictly before/inside/after the period. Conflicting end dates, a final date without an ordinary end date, boundary-day transactions, missing/unreadable dates or reversed periods yield `NOT_CHECKED` with a reason. No extension priority or inclusive-day rule is guessed. Configurable end-field/boundary policies are implementation capabilities, not approval to select a business rule. Snapshot freshness remains a separate warning.

# 13. Manual sampling

The 2026-09-30 priority-2 request adds **one selected verification per supplier** to the nominal every-20th method. `src/sampling/manual_sample.py` retains `manual_sample_interval: 20`, the builder's first-appearance order, complete groups and analysis before sampling. Target size is floor(grouped population / interval); nominal positions remain 20, 40, 60, etc. Each slot scans forward from its nominal position or after the last examined candidate, whichever is later, until a usable unique supplier is found. This systematic method has no randomization, wraparound, revisiting passed positions or duplicate backfilling. The sample can therefore be smaller even when earlier, unvisited positions contain other suppliers. The 2026-10-12 product decision explicitly preserves this method and its population-dependent target as the default.

Per source row, an existing `STRONG_MATCH` supplies `org:<matched_organization_number>`; since Phase 3C this is always a technically usable organization number. Otherwise the user's explicit fallback confirmation permits `name:<normalize_supplier(extract_supplier(header_text))>`, including ambiguous/no-match/unavailable register cases. This reuses existing Unicode, case, whitespace, punctuation and equivalent legal-form normalization, never Motp, fuzzy regrouping or candidate selection. A name key is not proof of legal identity. Every row in a verification must have a key and the group must contain exactly one distinct key; missing or multiple identities remain outside the sample with reasons. Different strong aliases sharing an organization number share one key. Both a previously selected key and a previously selected normalized extracted name prevent reselection. Ambiguous supplier-match statuses themselves remain unchanged.

`plan_manual_sample` returns the copied sample, target size, one decision per population verification and identity evidence per source occurrence. Decisions distinguish selected, repeated supplier, unusable identity and not examined according to the order; they retain nominal/actual positions and the previously selected position for duplicates. `create_manual_sample` remains a list-returning convenience wrapper. `PipelineResult.sampling_result` preserves the plan, and `sampling_evidence` now comes from actual selections, including replacements, rather than a modulo calculation. UI, CLI and export explain shortfalls. No source occurrence is deleted or modified; missing/multiple supplier identities remain in the complete review population. Sampling stays independent of flags and of supplier-view classification. For systematic sampling, fewer than 20 groups still gives an empty sample. Q2 remains open for further retention/approval requirements.

The separately confirmed randomized method, `plan_random_sample`, has a fixed
target of 20, even for populations below/above 400. It gives every verification in
the full grouped population a random priority with a local `random.Random(seed)`
and `shuffle`; it never draws from the systematic sample. Candidates are examined
without replacement in that order using the shared, unchanged identity/uniqueness
checks, until 20 are selected or the population is exhausted. Random priority is
uniform across verifications; supplier uniqueness constrains final inclusion
probabilities, as do the confirmed sampling classifications/quota below. No risk,
flag, supplier ranking or view classification weights the draw. Insufficient
eligible unique suppliers or final quota removals yield a smaller sample and an
explicit shortfall with recorded rejection reasons. Empty populations yield an
empty sample with target 20. Selected complete
groups are copied and returned in population order; `draw_position` in decisions
preserves the random order. Systematic decisions retain their existing meaning.

Both plans record method, interval (systematic only), UTC generation timestamp,
identity evidence and an SHA-256 of the ordered population identity evidence.
Randomized additionally records its non-negative integer seed. The source-file
hash remains separate: the identity fingerprint does not authenticate the source
or establish completeness. The same seed, classification rules and ordered population/identity evidence
reproduce selections with the recorded generator implementation. New seeds use
local `secrets.randbits(128)`; explicit regeneration ensures a seed different from
the previous draw. New draws can select the same members, especially when all
possible unique suppliers already fit in the sample.

## Confirmed internal quota (Del 1, 2026-10-13)

Both methods share `src/sampling/classification.py`. The separate
`sampling_supplier_rules` configuration list is **empty**, as explicitly requested;
no example identities are activated. Future entries require confirmed exact names
or organization numbers, with the same explicit rule fields/normalization as view
rules, but only `INTERNAL`/`EXTERNAL` classifications. Only confirmed rules apply.
Names use existing extracted/normalized identity evidence; organization rules
require an existing strong-match organization identity, and their configured
values must be technically usable organization numbers (Phase 3C) or loading fails. No substring/fuzzy rule,
Motp inference or new supplier matching is introduced. View rules never substitute
for these sampling rules. Base exclusions are unchanged.

Each source occurrence records its matching rule IDs, classification and reasons.
Within a verification: internal + unclassified is internal; external + unclassified
is unclassified; internal + external or any conflicting source classification is
conflict. All-external groups are external; no rule is unclassified, never external.
Existing missing/multiple identity checks and supplier uniqueness still apply.
Examined conflicts receive `CLASSIFICATION_CONFLICT` and remain outside the sample.

At most floor(target / 20) internal verifications may be accepted during the
existing forward/random selection sequence; excess internal candidates receive
`INTERNAL_QUOTA` and examination continues in the same sequence. After selection,
remove latest selected internal verifications, in reverse selection order, until
internal count <= floor(actual remaining size / 20). Recompute the denominator
after every removal, recording `INTERNAL_QUOTA_REMOVED` and the reason. There is
no redraw, revisiting, quota-slot reservation or backfill after removal. Duplicate
decisions remain explained even when the earlier selected supplier is removed.
Targets, nominal positions, random generator/seed and source ordering are unchanged.

`SamplingResult` retains the rule snapshot, source classifications and their
fingerprint. Method switching/regeneration uses that snapshot; exports serialize
the active plan, never draw another sample. UI/export report actual/target counts,
selected internal/external/unclassified counts, examined quota/conflict rejections
and final quota removals, with shortfall reasons. Not-examined cases retain their
classification evidence without being counted as rejection decisions. Both surfaces
warn that unclassified suppliers can contain internal suppliers and the cap cannot
guarantee actual internal share. With zero active internal rules this is stated explicitly.

The main navigation has `Analys och granskning` and `Manuellt urval`. The first
contains the existing review, excluded, controls and export tabs. The manual
sample is rendered once with its existing session state. Its tab offers `Var 20:e (stegvis)` (default) and
`Slumpmässig`, with population, usable-identity, target and actual
counts. `Generera nytt slumpmässigt urval` explicitly replaces the random plan.
`UploadResult.sampling_plans` is local to one completed analysis/session;
`select_sample_method` reuses a saved plan when switching methods and replaces
the active `PipelineResult` sampling fields, sampling summary and deferred export
snapshot together. It does not rerun analysis. Ordinary reruns, charts, navigation
and table filters cannot regenerate a sample. Refiltering creates a new analysis
and fresh plans/seed while retaining the chosen method; a new upload/analysis
starts with systematic. Temporary table filters remain presentation-only and
exports contain the complete active sample shown in the verification summary.

## Supplier-view population (separate from sampling)

No general internal/external signal is documented in the current input or register schema. `src/supplier_matching/view_scope.py` therefore applies only explicit `supplier_view_rules` entries in configuration. The default list is empty. Each entry supplies a unique `id`, `match_field` (`organization_number` or `supplier_name`), string `value`, `classification` (`INTERNAL`, `NOT_RELEVANT`, `EXTERNAL`), `reason` and boolean `confirmed`. Only confirmed entries apply. Organization rules require an existing strong match, and their values must be technically usable organization numbers or loading raises `ValueError` (Phase 3C); exact name rules use existing Huvudtext extraction and supplier normalization. No substrings, candidate guesses or Motp classification are used.

Each retained source row receives classification evidence, rule IDs, fields, configured values and reasons. No matching rule means `UNCLASSIFIED`, not external; conflicting classifications mean `CONFLICT` and remain visible. INTERNAL/NOT_RELEVANT hide rows only in the supplier-status overview, supplier cards and their drill-downs. Excluded counts, reasons and source rows are inspectable in a collapsed view; the complete review table, all supplier evidence/exports, contract-overview totals, base filtering and sampling remain intact. This classification is independent of the three existing confirmed base exclusions and the separate sampling quota rules. Sampling permits unclassified suppliers; Q13 retains the unresolved exact classification identities.

# 14. Exports and review UI

`src/output/report_generator.py` writes the following pipeline/CLI workbooks to a separate output directory, refusing to overwrite existing files:

| Workbook | Current contents |
| --- | --- |
| `cleaned_data.xlsx` | `rows`: all retained standardized rows, including ungrouped/invalid rows. |
| `flagged_invoices.xlsx` | `checks`: FLAGGED results supplied by the pipeline; `rows`: their retained verification rows; `Summary`: analysis counts. |
| `manual_sample.xlsx` | `rows`: retained rows of selected verifications. |
| `uncertain_suppliers.xlsx` | `rows`: every retained occurrence without `STRONG_MATCH`, including ambiguous, unmatched, unidentified and unavailable matching. Unavailable rows have no fabricated match status and explicitly carry `supplier_check_status: NOT_CHECKED`. |
| `excluded_data.xlsx` | `Bortfiltrerade`: original excluded rows and all exclusion reasons. |

Streamlit also prepares `granskning.xlsx` (`Granskning`), `bortfiltrerade.xlsx` (`Bortfiltrerade`) and `samlad_kontrollfil.xlsx` (both tables plus `Sammanfattning`). These tables retain source headers; excluded rows receive an extra reason column. Customer-facing copies remove numbered Slutk markers from Huvudtext as described below. The UI offers these three downloads plus the flagged, sample and uncertain-supplier workbooks. All use the same workbook serializer. The UI generates only the requested workbook on download, using its run's result snapshot without rereading source files/configuration or repeating analysis. Temporary export files are removed after their bytes are collected. New analyses, including refiltering, create a new snapshot/cache; caches are not shared between runs or sessions.

The confirmed 2026-09-29 presentation rule hides numbered `Slutk` markers in `Huvudtext`/`header_text` and extracted `supplier_text_raw` in all UI tables/details and Excel reports, including excluded rows, verification context and manual samples. `src/presentation.py` applies the existing `normalize_header_text` only to values containing a numbered marker, on presentation copies. `Prelb`, standalone `Slutk`, `Slutkund AB` and `Slutk123abc` remain unchanged. Original headers remain in the source file/upload bytes and internal original, standardized, filtered, grouped and sampled tables; matching evidence and source-occurrence linkage remain intact. This does not change supplier extraction/matching, filtering, grouping, ordering or sampling.

When supplier matching is available, review/cleaned/flagged/sample exports add matching fields and the sheets `Registerinformation`, `Leverantörsmatchning`, `Leverantörskandidater` and `Möjliga avtal`. Added fields avoid original-column collisions with `_` prefixes. An unusable supplied register yields availability/issue metadata instead of match results. Excluded exports are not supplier-enriched. `Möjliga avtal` carries the original register organization-number value, which can be an unusable identifier such as a personal-number form; this is open decision D5 in [Q14](docs/requirements/OPEN_QUESTIONS.md#q14--organization-number-policy-and-identifier-exposure).

Pipeline/UI workbooks add `Källspårning`, `Källinformation`, `Körningsöversikt`, `Exkluderingsregler`, `Urvalsmetod` and `Urvalspositioner`. Each export row maps to its exact source occurrence via export sheet/row, parsed source position, source Excel row, worksheet, filename and SHA-256. Combined workbooks distinguish included and excluded export sheets. Matching/contract evidence is subset to each report's population; complete-run summary and sampling evidence remain explicitly run-level context. Register metadata records the source name/kind/hash/date.

The priority-2 update additionally exports run-level `Urvalsbeslut`, `Urvalsidentiteter` and `Leverantörsvy`. `Urvalsmetod` includes the supplier-uniqueness method, target size and any shortfall explanation; `Urvalspositioner` contains only actual selections with row-level identity evidence. The supplier-view sheet records classifications without removing source rows or altering matching evidence in exports. Whole-run matching counts remain in RunSummary; supplier-status charts/cards use the explicit view subset and display its excluded count separately.

The 2026-10-12 sampling update adds the active method, UTC generation timestamp,
seed (randomized only, exported as literal text to preserve all digits), generator
and Python version, population identity fingerprint and usable-identity count to
`Urvalsmetod`. Population/target/actual counts, limitations, per-verification
decisions and source-row linkage follow the active plan in every workbook.
Randomized has no interval; systematic exports retain the configured interval.
Method changes or explicit regeneration create a new deferred export snapshot;
previous download bytes cannot leak into the active sample's reports.

The Del 1 quota update adds `Urvalsklassificering` (source-level evidence) and
`Urvalsklassificeringsregler` (the rule snapshot, including an empty table when no
rules exist). Existing workbook sheets and source values are retained.
`Urvalsbeslut` adds verification classification/reason; `Urvalsmetod` adds selected
classification counts, quota/conflict rejections, final removals, the actual-size
quota, active internal-rule count, limitations and classification fingerprint.

`src/run_summary.py` derives actual pipeline counts for UI and export: input/included/excluded/ungrouped rows, eligible/sample verifications, sampled rows, per-rule exclusions, flagged verifications and their rows, matching availability/confidence, detection statuses and contract-period statuses. Units remain explicit; overlapping exclusions and multiple contract comparisons are not summed as unique invoices. No reviewer completion or persistent sign-off state is invented.

The visual overview in `src/ui_run_summary.py` precedes the detail views. It presents compact KPIs and horizontal charts for retained/excluded source rows, recorded exclusion-rule hits, existing supplier-match statuses, contract-period statuses and selected/remaining eligible verifications. Population, exclusion, flagged-verification, contract and sampling counts come directly from `RunSummary`; supplier-status counts come from `SupplierAnalysis.rows`. Unavailable matching is displayed as unavailable, without fabricated match statuses. Zero-result categories have explicit empty states. Contract-period statuses remain distinct, and no review-completion progress is inferred. Existing source-row drill-downs, validation, flag/error explanations and exports remain available under Details and review. Temporary view filters do not change dashboard counts or the sample.

The 2026-10-02 UI clarification removes `Detektionskontroller`, its chart and status drill-downs, the `Ej kontrollerade` card and unassessed control rows from the interface. A single information box reads: `Attestkontroll ej genomförd – kräver attestregister eller motsvarande behörighetsunderlag som inte finns tillgängligt i prototypen.` Actual flagged findings and technical errors remain inspectable under `Flaggningar och tekniska fel`; analyzed/flagged/validation counts remain unchanged. Detection results and `RunSummary.check_status_counts` remain intact in memory and existing exports. Supplier matching, contract-period evidence (including `NOT_CHECKED`), sampling, filtering and all other counts are unchanged.

The 2026-09-29 transparency update adds initially collapsed category expanders beneath these summaries, including the entire exclusion-reasons section. `src/ui_overview_details.py` builds read-only detail tables from existing results: exact backend reasons and counts at the corresponding unit, supplier candidates, contract dates/status/reasons, verification groups and source rows with occurrence/Excel-row linkage. Its detection-evidence helper is retained but no longer rendered after the 2026-10-02 clarification. Detection row positions are resolved through the corresponding verification's retained indexes; results without a row position retain group context, without inferring linkage from Vernr/Vrad. Unusable positions remain explicit without an invented row link. Source values and existing numbered-Slutk presentation behavior remain unchanged.

The 2026-10-06 UI update retains the original graphical overview: horizontal bar charts, metric cards and existing category expanders. The subsequent interactive-dashboard request adds real Vega-Lite single-category selection to all five existing charts, without replacing charts with buttons. Clicking a bar or its count opens the corresponding existing category expander and displays a Swedish selection message and `Rensa diagramval`. The stable `Status` field connects population indexes, recorded exclusion-rule positions, view-scoped supplier statuses, full-run contract comparisons and selected/remaining verification groups to the existing helpers in `src/ui_overview_details.py`. Contract drilldowns count comparisons; sample drilldowns count groups, with their source rows shown separately. No population is reconstructed or deduplicated for navigation. Empty categories retain their empty detail state; entirely empty charts retain their existing information messages.

`src/ui_chart_selection.py` isolates chart navigation. The `category` point selection explicitly projects `Status`, disables multi-selection and binds once to the named bar layer to avoid duplicate Vega signals in the layered chart. Native selection events trigger a Streamlit rerun. Each chart has a namespaced widget key with a reset revision; reset remounts the widget rather than assigning its read-only selection state. Independent chart selections persist across unrelated reruns. A different completed `PipelineResult` resets every chart, including after base refiltering or register changes; `Till översikt` also resets them. Selection never reruns analysis or alters temporary table filters, matching, sample membership, counts or exports.

The sidebar title is `Exkluderingsregler`. Manual-sample verification summaries also show all distinct supplier names already recorded in sampling identity evidence, linked by source position, with explicit multiple-name/missing-name labels. No matching, population, sampling or export-content rules change. Refiltering still rereads the working source/register copies and recomputes analysis; it no longer waits for serialization of eight unrequested workbooks.

The overview explains the audited units: the sample population is `len(verifications)` after routing unusable IDs and grouping; strong supplier hits count retained rows with `STRONG_MATCH`, including any ungrouped rows. These are intentionally different units, not alternative counts of the same population. Contract counts remain comparisons: a row without a candidate has no contract comparison and is explained under supplier matching, not given a fabricated `NOT_CHECKED` contract result. `NOT_CHECKED` contract comparisons remain separate from dates actually outside a period and do not imply missing or invalid contracts. No filtering, matching, date policy, detection, grouping, sampling, summary calculation or export behavior changes in this update.

Apart from the header/supplier presentation rule above, strings, including formula expressions, are exported literally. Decimal values are written as exact text; Excel styling and arbitrary Python types are not preserved. Unsupported values or cell-size limits can stop export without changing the source.

Known evidence limitations:

- Detailed validation remains available in the UI. All detection results remain in memory, while only flagged findings and technical errors are shown in the UI; the checks export is not a complete record of `ERROR`, `NOT_CHECKED` or `PASS` results. Summary counts are not their explanations.
- No formal reviewer identity/sign-off or persistent comment workflow is implemented (Q6/Q7).

# 15. Source-occurrence traceability: requirement and current limits

M6 requires linkage to the exact source occurrence, including repeated or missing business identifiers. `Vernr`/`Vrad` and supplier metadata alone are not sufficient provenance.

The current Excel reader creates unique zero-based table indexes. Mapping, filtering, grouping and sampling retain them. Validation positions refer to the original parsed table; supplier `source_row_position` uses retained indexes. UI row details use positional linkage. These indexes must not be discarded or recreated without an explicit replacement.

Current limitations mean full M6 completion must not be claimed:

- Detection `row_position` in per-row presence checks is local to the verification, whereas validation positions are relative to the parsed source table.
- Detailed validation and all nonflagged detection findings are not yet persisted; the run evidence does not replace them.

Source tables remain unchanged; separate provenance sheets now carry exact occurrence/Excel-row linkage in pipeline/UI exports even without a register and for excluded rows. The source hash identifies the supplied bytes, not authenticity or completeness relative to Proceedo.

Q3 concerns the required traceability information and presentation. These limitations are deferred technical work, not permission to weaken source preservation or invent business identity rules.
