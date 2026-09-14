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

## Installera och köra lokalt

v0.1 har ett körbart tekniskt flöde och ett svenskt Streamlit-gränssnitt.
Verksamhetskontroller som väntar på AK:s bekräftelse förblir `NOT_CHECKED`.
Detta är inte ett godkännande av fakturorna.

Använd Python 3.13 (testad version). Kör från projektets rot på macOS/Linux:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Öppna http://127.0.0.1:8501. Ladda upp en `.xlsx`-fil, välj **Starta analys**
och ladda ner de tre rapporterna. Det första kalkylbladet används. Appen är
bunden till den lokala datorn och användningstelemetri är avstängd.
Arbetsfiler tas bort efter körningen; resultat och nedladdningar behålls i
sessionens minne. Byte av uppladdad fil rensar tidigare resultat.

På Windows PowerShell: skapa miljön med `py -3.13 -m venv .venv` och aktivera
med `.venv\Scripts\Activate.ps1`. Kör sedan samma pip- och Streamlit-kommandon.

Kommandoradsalternativ:

```bash
python -m src.main data/input/fakturor.xlsx --output-dir data/output/korning-001
python -m src.main --help
```

Använd en ny rapportkatalog för varje körning. Befintliga rapportfiler skrivs
aldrig över. Sökvägen till indata ska avse din lokala fil; ingen exempelfaktura
med verkliga uppgifter ingår i Git.

Testa installationen:

```bash
python -m pip check
python -m pytest -q
```

Beroenden finns i `requirements.txt`. Minimikrav anges där API-användningen
kräver det; miljön är inte fullständigt versionslåst.

## Begränsningar i v0.1

- Leverantörs- och attestregler samt obligatoriska verksamhetsfält inväntar AK.
- Bildläsaren utför inte OCR. Bildkoppling och referensregister konfigureras
  inte via UI:t; laddade register innebär inte att verksamhetsregler bekräftats.
- Rader utan användbart verifikationsnummer behålls i underlaget men grupperas
  inte som verifikationer. Slutlig hantering kräver verksamhetsbeslut.
- Konton matchas exakt som text. Numeriska konton markeras av valideringen;
  de normaliseras inte automatiskt.
- Valideringsdetaljer och samtliga kontrollresultat finns i UI/minnesresultatet;
  Excel innehåller underlag, flaggningar, stickprov och sammanfattning.
- `code` i flaggrapporten är tomt: `check_type` identifierar kontrollen men är
  inte en orsakskod. Samma kontroll kan ge flera olika orsaker.
- Egna framtida kontrolltexter behöver översättningar; originalorsaken bevaras.
  Streamlits inbyggda filväljare kan innehålla engelska standardtexter.
- Excel begränsar cellstorlek och datatyper. Decimalvärden exporteras som exakt
  text; format som Excel inte stöder kan stoppa exporten utan att ändra källan.

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
`data/output/`. Existing destination files are never overwritten.

Keep real invoices and sensitive registers in the ignored local data folders;
do not commit them elsewhere or force-add them. Data and log folders contain
only tracked `.gitkeep` placeholders. Future committed test fixtures must use
synthetic, non-sensitive data.
