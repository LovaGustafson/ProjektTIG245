# AGENTS.md

## Project rules

- Read `PROJECT_SPEC.md` before making changes.
- Follow the architecture, data model and implementation order defined in the project specification.
- Work on one task/module at a time.
- Do not modify unrelated files.

## Data safety

- Original invoice files are read-only.
- Never overwrite, modify or delete source data.
- All transformations must be performed on a working copy.
- Do not commit real invoice data or sensitive reference data to GitHub.

## Business rules

- Do not invent business rules.
- If a requirement is unclear or not confirmed by AK, mark it as `TODO` and state the assumption/problem.
- Do not guess the meaning of fields such as `Mm`, `Pg`, `Sign`, `Att`, `Ksansv` or `Bild`.
- Do not assume which field identifies the supplier unless it is confirmed in `PROJECT_SPEC.md`.

## Code structure

- Use the standardized internal field names from `PROJECT_SPEC.md`.
- Keep ingestion, mapping, validation, filtering, detection, sampling and output logic separated.
- A module should have one main responsibility.
- New detection rules should be implemented as separate rules/modules when possible.

## Error handling

- One invalid invoice or row must not crash the full analysis.
- Errors should be handled clearly and logged where appropriate.
- Every flagged invoice must include a clear reason for the flag.

## Testing

- Add or update tests for new functionality.
- Run relevant tests after making changes.
- Do not continue to the next implementation task if the current task is failing.

## When finishing a task

Always report:

1. What files were changed.
2. What functionality was implemented.
3. What tests were run.
4. Any assumptions or unresolved questions.
