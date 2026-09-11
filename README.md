# ProjektTIG245

## Overview

This project is a prototype for reviewing supplier invoices from Excel files.

The system is intended to:

- read supplier invoice data from Excel files
- standardize and validate the data
- filter out records that should not be reviewed
- group invoice rows into verifications
- detect potential deviations
- explain why a verification was flagged
- create a manual quality-control sample
- export the results
- preserve the original source data

The system is developed as part of the TIG245 project course.

---

## Project status

🚧 Prototype under development.

The system is being implemented step by step according to `PROJECT_SPEC.md`.

Some business rules are still awaiting confirmation from AK.

---

## Documentation

### `AGENTS.md`

Contains instructions for Codex and rules for how code should be implemented.

### `PROJECT_SPEC.md`

Contains the technical specification, data model, detection rules and implementation order.

---

## Project structure

```text
config/settings.yaml     Confirmed settings and unresolved business TODOs
data/input/              Local source invoices (read-only)
data/reference/          Local reference registers (read-only)
data/output/             Generated results
logs/                    Local analysis logs
src/
  models/                Internal row, verification and result models
  ingestion/             Excel, image and reference readers
  mapping/               Standardized column names
  validation/            Data-quality checks
  filtering/             Configured exclusions
  verification/          Grouping rows into verifications
  detection/rules/       Separate detection rules
  sampling/              Manual verification sampling
  output/                Report generation
tests/                   Module and integration tests
```

Only the folder/package scaffold and configuration exist at this stage.
Implementation modules, the pipeline, entry point and UI will be added in the
order specified in section 6.1 of `PROJECT_SPEC.md`. There is no runnable invoice
analysis yet.

## Local setup

Use Python 3.13 for the initial development environment (the version available
during scaffolding; the specification does not mandate a Python version).
From the repository root on macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell, create the environment with `py -3 -m venv .venv`
and activate it with `.venv\Scripts\Activate.ps1`, then run the same pip command.

Initial dependencies are pandas for tabular data, openpyxl for `.xlsx` files,
PyYAML for configuration, and pytest for tests. Versions are not pinned yet;
this scaffold does not provide a locked dependency environment. Image/OCR and
UI dependencies will be selected when their modules are implemented.

Once tests are added, run them from the repository root:

```bash
python -m pytest
```

At this scaffold stage there are no test cases; pytest will report no tests
collected (exit code 5).

## Configuration and pending decisions

`config/settings.yaml` records the confirmed account exclusions (`7698`, `7699`)
and the baseline sampling interval of 20 verifications.
`excluded_verification_types` and `required_fields` are `null`, meaning
**TODO / awaiting business confirmation**, not approved empty lists. Future
consumers must handle unresolved settings explicitly.

The business `required_fields` setting is separate from the five mandatory
row-validation fields already defined in the specification: `verification_id`,
`verification_line_id`, `verification_date`, `amount`, and `account`.

AK must also confirm field meanings, the supplier identifier, reference-register
structures, and attestation rules. Do not infer that `counterparty` identifies
the supplier. The final sampling method remains open to confirmation.

## Data handling

Original invoices and reference data must only be read. All transformations
must operate on working copies, with generated reports written separately to
`data/output/`. The scaffold itself does not enforce filesystem permissions.

Keep real invoices and sensitive registers in the ignored local data folders;
do not commit them elsewhere or force-add them. Data and log folders contain
only tracked `.gitkeep` placeholders. Future committed test fixtures must use
synthetic, non-sensitive data.
