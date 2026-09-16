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
och granska resultatet i flikarna Granskning, Bortfiltrerade, Kontroller och Export. Det första kalkylbladet används. Appen är
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
- Konton normaliseras endast vid filterjämförelsen (tal, text och omgivande
  blanksteg). Originalvärden behålls; datamodellens validering är oförändrad.
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
`excluded_verification_types` contains the 42 unique MoSCoW exclusions.
`required_fields` remains `null`: **TODO / awaiting business confirmation**.

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

## MoSCoW-filter och export

Sidofältet visar de exkluderade verifikationstyperna. Ta bort en typ från valet
för att återinkludera den, välj andra typer från filen eller återställ standard.
Konto 7698 och 7699 exkluderas alltid. Tomma filtervärden behålls för granskning.
Konto/Vertyp identifieras via kolumnnamn, inklusive omgivande blanksteg, eller
standardiserade namn. Saknade/tvetydiga filterkolumner ger synliga fel; resultatet
är då ofullständigt filtrerat och inga rader försvinner.

Alla rader hamnar i Granskning eller Bortfiltrerade, även ogiltiga rader.
Konto- och typantal kan överlappa; totalantalet räknar varje bortfiltrerad rad
endast en gång. Originalets kolumnnamn och värden används i granskningsvyerna
samt de nya exporterna. Exkluderingsorsaker ligger i en separat tillagd kolumn.

Export erbjuder `granskning.xlsx`, `bortfiltrerade.xlsx` och
`samlad_kontrollfil.xlsx` (Granskning, Bortfiltrerade, Sammanfattning).
Befintliga avvikelse- och stickprovsrapporter finns också kvar. Nedladdningarna
skapas i minnet; ingen källsökväg används som exportmål. Originalets filbytes och
en separat original-DataFrame behålls i sessionen. Filterändringar analyserar
om arbetskopian och uppdaterar också exporterna.

Upphandlingskontroll, attestkontroll och rätt attestant visas som ej tillgängliga.
Inga register eller bedömningar simuleras. TODO: register, leverantörsidentifiering
och attestregler behöver fastställas med AK. Ingen OCR eller systemintegration
ingår. Första kalkylbladet används fortfarande; Excel-format/styling bevaras inte
i exporter. Automatiserad analys omfattar alla kvarvarande verifikationer;
stickprovet görs separat efteråt.

Excel-läsaren söker automatiskt efter tabellrubriken i de första 50 raderna,
innan någon rad tolkas som kolumnnamn. Raden med flest olika träffar bland
Vernr, Vrad, Verdatum, Utfall, Konto, Vertyp, Huvudtext och Radtext väljs
(minst tre träffar; vid lika poäng väljs den första). Även motsvarande
standardiserade fältnamn och omgivande blanksteg accepteras. Metadata ovanför
rubriken räknas inte som fakturarader och används aldrig som filterkonfiguration.
Alla rader under rubriken läses. Helt tomma namnlösa kolumner tas bort;
namnlösa kolumner med data får unika namn, exempelvis `Namnlös kolumn 9`.
Namngivna kolumner behålls även om de saknar värden.

Om ingen tydlig schemamatchning hittas används första raden som tidigare,
för att behålla stöd för generiska rapporter och ofullständiga underlag.
Saknade obligatoriska kolumner rapporteras fortsatt av valideringen och UI:t.
