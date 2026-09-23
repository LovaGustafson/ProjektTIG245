# PROJECT_SPEC.md

## TIG245 — Current Technical Specification

Last updated: 2026-09-23

---

# 1. Document authority

This document defines the current technical behavior and architecture of the TIG245 prototype.

Current customer scope and priority are defined in:

`docs/requirements/MOSCOW_CURRENT.md`

Repository-wide agent/development rules are defined in:

`AGENTS.md`

If this document conflicts with a current confirmed customer requirement, the current customer requirement takes priority.

Existing code and tests may reveal current implementation behavior, but they do not independently define customer business rules.

Unresolved customer requirements must not be implemented by inference.

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

## Streamlit UI

`streamlit_app.py`

Provides the interactive prototype used for file upload, analysis, filtering, review and export.

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
Supplier analysis per retained row, when register is available
        ↓
Verification grouping
        ↓
Detection
        ↓
Manual sampling
        ↓
Streamlit presentation / Excel output
```
