# PROJECT_SPEC.md

## 1. Project goal

Build a local prototype that reviews supplier invoices from Excel files and identifies potential deviations.

The system must:

- read supplier invoice data from Excel
- optionally use associated invoice images/documents
- standardize and validate the data
- filter out records that should not be reviewed
- analyze all relevant invoices
- flag potential deviations
- explain why an invoice was flagged
- create a manual sample for quality control
- export results
- never modify the original source files

All processing must be performed on a working copy.

---

## 2. Internal data model

The system must use standardized internal field names.

| Original | Internal |
|---|---|
| Vernr | `verification_id` |
| Vrad | `verification_line_id` |
| Verdatum | `verification_date` |
| Utfall | `amount` |
| Konto | `account` |
| Ansvar | `responsibility` |
| Motp | `counterparty` |
| Inv | `investment` |
| Proj | `project` |
| Aktiv | `activity` |
| Ksansv | `cost_responsibility` |
| Mm | `vat_code` |
| Pg | `posting_group` |
| Vertyp | `verification_type` |
| Huvudtext | `header_text` |
| Radtext | `line_text` |
| Bild | `image_reference` |
| Sign | `signature` |
| Att | `attestation` |

A unique row is identified by:

`verification_id + verification_line_id`

Required technical fields:

- `verification_id`
- `verification_line_id`
- `verification_date`
- `amount`
- `account`

---

## 3. Validation

The system must validate that:

- `verification_id` exists
- `verification_line_id` is valid
- `verification_date` can be interpreted as a date
- `amount` is numeric
- `account` exists
- `verification_id + verification_line_id` is unique

Invalid rows must be marked clearly.

One invalid row must not crash the entire analysis.

---

## 4. Filtering

The system must initially exclude:

- account `7698`
- account `7699`
- verification types confirmed by AK as excluded

Excluded verification types must be configurable and must not be hardcoded unless confirmed.

Filtering must only affect the working copy.

---

## 5. Verification structure

A verification can contain multiple rows.

Example:

```text
verification_id 1001
├── verification_line_id 1
├── verification_line_id 2
└── verification_line_id 3
