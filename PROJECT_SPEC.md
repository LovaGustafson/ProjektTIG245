# PROJECT_SPEC.md

## TIG245 — Current Technical Specification

Last updated: 2026-09-24

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
- producing a deterministic manual sample,
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

`src/ui_support.py` runs the pipeline on temporary upload copies, collects report bytes, and adds the Streamlit review workbooks. `streamlit_app.py`, `src/presentation.py` and the `src/ui_*.py` modules present these results.

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

`src/filtering/filter_engine.py` applies account and selected `verification_type` exclusions using standardized fields, never fixed Excel column positions. Confirmed account exclusions are `7698` and `7699`. The existing standard verification-type set is the 42 values in `config/settings.yaml` under `excluded_verification_types`, including `FBFM`; this document does not redefine that set.

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

`src/ingestion/contract_reader.py` loads the optional Koncerninköp register using configured header aliases. Supplier-name and organization-number columns must be present and unambiguous. Missing contract-detail columns produce warnings. Names alone do not merge legal entities; organization numbers group register rows, while missing numbers retain separate identities. Contract rows are not deduplicated.

`src/supplier_matching/` separates extraction, normalization, matching, date warnings, settings and row analysis; `src/models/supplier.py` defines their result models.

- Extraction uses only text before the first `Prelb`/`Slutk` marker in `header_text`/`Huvudtext`, case-insensitively. `Slutk123` and `Slutk 123` are both recognized; existing standalone markers remain supported. Missing markers/candidates remain unidentified. `normalize_header_text` separately removes numbered Slutk occurrences and collapses whitespace on a comparison copy, exported as `header_text_normalized`. Original Huvudtext is preserved. `Motp` is never a matching key.
- Comparison normalization preserves original text and Swedish diacritics; it normalizes Unicode, case, whitespace, punctuation and explicit equivalent legal-form names without treating distinct legal forms as equivalent.
- Matching ranks exact normalized names, eligible prefixes and deterministic fuzzy candidates. Current technical defaults are prefix length 8, two tokens and 60% coverage; fuzzy strong/candidate thresholds are 0.94/0.82. Additional token and legal-form safeguards apply in `matcher.py`. These are prototype settings, not customer compliance thresholds or probabilities.
- `STRONG_MATCH` requires one plausible eligible supplier identity with an organization number. Multiple or uncertain candidates remain `AMBIGUOUS_MATCH` for manual review, with no chosen supplier. Other states are `NO_MATCH` and `SUPPLIER_NOT_IDENTIFIED`.
- Missing, unreadable or unusable registers produce unavailable matching, never fabricated `NO_MATCH`. All retained rows can receive supplier analysis when the register is usable, including ungrouped rows.
- Candidate evidence includes possible contract rows; no contract is automatically selected. Identity matching does not establish procurement compliance, contract applicability or transaction approval. The verification-level supplier compliance check remains `NOT_CHECKED`.
- Transactions after the registry snapshot receive a separate freshness warning. Missing/invalid transaction dates or missing snapshot dates yield `UNKNOWN` for the date check and do not change supplier identity status.

Row evidence joins through retained source indexes, not verification or supplier identity. Q10 covers unresolved field/control meanings; M7/Q9 governs any future AI use.

## Register source selection

`src/ingestion/registry_source.py` isolates source selection from identity matching. `supplier_matching.default_registry_path` selects a local default file (relative paths resolve against the project root); an optional `default_registry_name` controls its label. The configured path is `data/reference/koncerninkop.xlsx`. No real register is distributed in Git; the file must exist locally before default matching is available. UI uploads replace the default, removal disables register use, and restoring the default clears the uploaded selection. CLI supports `--supplier-register` and `--no-default-registry`.

An immutable `RegistrySource` retains the exact bytes, source kind/name, snapshot date and SHA-256 for the run. UI refiltering reuses these bytes even if the local default file subsequently changes. Source/register changes clear stale results. Missing, disabled or unreadable sources remain unavailable; they do not trigger a substitute register or fabricated negative matches. Register date is explicit configuration/UI input, not inferred from filenames. Export metadata also records the parsed register sheet and header row when available.

## Contract-period evidence

The 2026-09-24 request authorizes date comparisons, separately from purchase-to-contract applicability. `src/supplier_matching/contract_period.py` compares each register contract of a strongly identified supplier with each retained row's verification date. Multiple contracts are preserved and checked separately; none is selected as the purchase's governing contract. Ambiguous candidates remain `NOT_CHECKED`.

The contract reader preserves `start_date`, `end_date` and `final_end_date` (including the alias `Sista slutdatum`). Evidence includes original dates, parsed verification date, evaluated period, end-date basis, boundary-policy setting, rule identifier, reason and the existing `PASS`/`FLAGGED`/`NOT_CHECKED` status vocabulary. `PASS` means within that register period only; `FLAGGED` means before or after it. These results do not change supplier confidence or manufacture procurement-compliance/detection conclusions. Summary counts explicitly use **contract comparisons**, not invoices or unique contracts.

Pending Q12, `contract_period.end_date_field` and `inclusive_boundaries` remain null. An ordinary end date with no final date, or two agreeing end dates, supports checks strictly before/inside/after the period. Conflicting end dates, a final date without an ordinary end date, boundary-day transactions, missing/unreadable dates or reversed periods yield `NOT_CHECKED` with a reason. No extension priority or inclusive-day rule is guessed. Configurable end-field/boundary policies are implementation capabilities, not approval to select a business rule. Snapshot freshness remains a separate warning.

# 13. Manual sampling

The confirmed rule is **every 20th eligible verification**. `src/sampling/manual_sample.py` uses `manual_sample_interval: 20` in repository configuration and selects positions 20, 40, 60, etc. in the builder's first-appearance order after filtering/grouping and analysis of every eligible verification.

Sampling is separate from detection, independent of flags, and selects complete retained verification groups rather than raw Excel rows. Fewer than 20 eligible verifications gives an empty sample. Copies retain source indexes. Changes to base exclusions, grouping or source order can change selection; temporary UI view filters do not.

The helper supports other configured intervals technically; that does not authorize changing the confirmed customer interval. The pipeline loads the interval once and records population count, ordering, selected verification positions and all selected source positions. UI shows eligible verification count, `1 av 20`, selected verification count and selected row count. Q2 remains open for customer retention/approval requirements beyond the implemented evidence.

# 14. Exports and review UI

`src/output/report_generator.py` writes the following pipeline/CLI workbooks to a separate output directory, refusing to overwrite existing files:

| Workbook | Current contents |
| --- | --- |
| `cleaned_data.xlsx` | `rows`: all retained standardized rows, including ungrouped/invalid rows. |
| `flagged_invoices.xlsx` | `checks`: FLAGGED results supplied by the pipeline; `rows`: their retained verification rows; `Summary`: analysis counts. |
| `manual_sample.xlsx` | `rows`: retained rows of selected verifications. |
| `uncertain_suppliers.xlsx` | `rows`: every retained occurrence without `STRONG_MATCH`, including ambiguous, unmatched, unidentified and unavailable matching. Unavailable rows have no fabricated match status and explicitly carry `supplier_check_status: NOT_CHECKED`. |
| `excluded_data.xlsx` | `Bortfiltrerade`: original excluded rows and all exclusion reasons. |

Streamlit also prepares `granskning.xlsx` (`Granskning`), `bortfiltrerade.xlsx` (`Bortfiltrerade`) and `samlad_kontrollfil.xlsx` (both tables plus `Sammanfattning`). These tables retain original source headers/values; excluded rows receive an extra reason column. The UI offers these three downloads plus the flagged, sample and uncertain-supplier workbooks. All use the same workbook serializer. Temporary pipeline files are removed after their bytes are collected.

When supplier matching is available, review/cleaned/flagged/sample exports add matching fields and the sheets `Registerinformation`, `Leverantörsmatchning`, `Leverantörskandidater` and `Möjliga avtal`. Added fields avoid original-column collisions with `_` prefixes. An unusable supplied register yields availability/issue metadata instead of match results. Excluded exports are not supplier-enriched.

Pipeline/UI workbooks add `Källspårning`, `Källinformation`, `Körningsöversikt`, `Exkluderingsregler`, `Urvalsmetod` and `Urvalspositioner`. Each export row maps to its exact source occurrence via export sheet/row, parsed source position, source Excel row, worksheet, filename and SHA-256. Combined workbooks distinguish included and excluded export sheets. Matching/contract evidence is subset to each report's population; complete-run summary and sampling evidence remain explicitly run-level context. Register metadata records the source name/kind/hash/date.

`src/run_summary.py` derives actual pipeline counts for UI and export: input/included/excluded/ungrouped rows, eligible/sample verifications, sampled rows, per-rule exclusions, flagged verifications and their rows, matching availability/confidence, detection statuses and contract-period statuses. Units remain explicit; overlapping exclusions and multiple contract comparisons are not summed as unique invoices. No reviewer completion or persistent sign-off state is invented.

Strings, including formula expressions, are exported literally. Decimal values are written as exact text; Excel styling and arbitrary Python types are not preserved. Unsupported values or cell-size limits can stop export without changing the source.

Known evidence limitations:

- Detailed validation and nonflagged detection results remain in memory/UI; the checks export is not a complete record of `ERROR`, `NOT_CHECKED` or `PASS` results. Summary counts are not their explanations.
- No formal reviewer identity/sign-off or persistent comment workflow is implemented (Q6/Q7).

# 15. Source-occurrence traceability: requirement and current limits

M6 requires linkage to the exact source occurrence, including repeated or missing business identifiers. `Vernr`/`Vrad` and supplier metadata alone are not sufficient provenance.

The current Excel reader creates unique zero-based table indexes. Mapping, filtering, grouping and sampling retain them. Validation positions refer to the original parsed table; supplier `source_row_position` uses retained indexes. UI row details use positional linkage. These indexes must not be discarded or recreated without an explicit replacement.

Current limitations mean full M6 completion must not be claimed:

- Detection `row_position` in per-row presence checks is local to the verification, whereas validation positions are relative to the parsed source table.
- Detailed validation and all nonflagged detection findings are not yet persisted; the run evidence does not replace them.

Source tables remain unchanged; separate provenance sheets now carry exact occurrence/Excel-row linkage in pipeline/UI exports even without a register and for excluded rows. The source hash identifies the supplied bytes, not authenticity or completeness relative to Proceedo.

Q3 concerns the required traceability information and presentation. These limitations are deferred technical work, not permission to weaken source preservation or invent business identity rules.
