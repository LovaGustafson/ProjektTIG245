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

## Leverantörsmatchning mot Koncerninköp

Ladda upp både fakturafilen och Koncerninköpsregistret i Streamlits sidofält.
Ange registerutdragets datum (förvalt **2026-08-31**) och starta analysen.
Granskning visar fyra statusar med färgikoner och en sammanfattning per
transaktionsrad. Markera en rad för normalisering, metod, score, motivering,
organisationsnummer, kandidater och möjliga avtal. Filterändringar behåller
det uppladdade registret. Byte av fil eller registerdatum rensar föregående resultat.

CLI stöder också `.csv` för registret:

```bash
python -m src.main data/input/fakturor.xlsx --supplier-register data/reference/koncerninkop.xlsx --registry-snapshot-date 2026-08-31 --output-dir data/output/korning-002
```

Registrets blad, CSV-avgränsare/encoding, rubrikalias och matchningströsklar
ligger i `supplier_matching` i `config/settings.yaml`. UI laddar `.xlsx`;
registerbladet väljs genom konfiguration. CSV använder initialt semikolon och
UTF-8 med eventuell BOM. Excel-läsaren kan hitta registerrubriken inom de första
50 raderna via minst två olika konfigurerade fält. Inga kolumnpositioner gissas.
Leverantörsnamn och organisationsnummer behöver entydiga kolumner; saknade
avtalsdetaljer ger varning. TODO: verifiera exakta rubriker mot den riktiga filen.

Matchningsregler:

- Extrahera endast text före första fristående `Prelb`/`Slutk` (okänsligt för
  stora/små bokstäver). Originalets Huvudtext behålls.
- Normalisera Unicode (NFKC), case, whitespace och skiljetecken. Explicita
  motsvarigheter som Aktiebolag/AB normaliseras, men bolagsformer tas inte bort.
  Svenska diakritiska tecken behålls.
- Prioritera exakt normaliserad träff, därefter prefix, därefter fuzzy.
  Prefix kräver minst **8 tecken**, **2 ord**, **60 % täckning** av det
  normaliserade registernamnet, samma kompletta första namnord och ingen
  redan fullständig bolagsform i kandidattexten före ytterligare namntext.
- Fuzzy använder standardbibliotekets deterministiska `SequenceMatcher`
  (`autojunk=False`). Stark kandidat kräver score **≥ 0,94**, minst två namnord,
  samma antal namnord utan bolagsform och förenlig bolagsform. Score **≥ 0,82**
  ger en kandidat för manuell kontroll. Samma första namnord med minst sex
  tecken eller samma namn utan bolagsform kan också ge en osäker kandidat;
  exempelvis Swedbank Pay/Swedbank och AJ Medical HB/KB.
- En stark träff kräver **en enda rimlig leverantörsidentitet** och ett
  organisationsnummer. Även exakta träffar blir osäkra om en annan rimlig
  juridisk person finns. Saknade organisationsnummer slås aldrig ihop.
  Dessa försiktiga gränser är tekniska prototypval som behöver utvärderas.
- Score är namnlikhet/prefixtäckning, **inte en sannolikhet**. Matchningen
  gör inga besked om upphandling eller avtalstrohet och väljer aldrig ett avtal.
  Organisationsnummer jämförs utan blanksteg/bindestreck; originalvärdet finns
  kvar i avtalsdetaljerna. Ingen kontrollsiffra eller koncernkoppling härleds.
- Alla avtalsrader för varje kandidat visas, även när datum eller kategori
  saknas. `contract_count` räknar registerposter för den starkt matchade
  leverantören; dubbletter av avtalsrader dedupliceras inte utan bekräftade regler.
  Vid osäker match är valt namn/organisationsnummer tomt och avtalsantalet per
  kandidat finns i detaljbladet. Avtalsdatum används inte för att välja avtal.
- Transaktion efter registerdatum får en separat varning. Saknat/ogiltigt
  datum får status UNKNOWN för datumkontrollen; leverantörsstatus påverkas inte.

`src/supplier_matching/` håller extraktion, normalisering, matchning,
datumkontroll och radanalys separerade. `src/ingestion/contract_reader.py`
läser registret, och `src/models/supplier.py` beskriver leverantörsidentiteter
och resultat. `Motp` används aldrig som leverantörsnyckel. En framtida
ID-resolver kan ge samma resultatmodell. Köp–avtalskategori implementeras inte.

Excel-exporterna för granskning, rensat underlag, stickprov och avvikelser
får matchningsfält samt separata blad för **Registerinformation**,
**Leverantörsmatchning**, **Leverantörskandidater** och **Möjliga avtal**.
`source_row_position` kopplar detaljer till den inlästa tabellens radposition
(från 0, inte Excel-radnummer). Originalkolumner skrivs aldrig över; eventuella
namnkrockar ger ett `_`-prefix på det tillagda fältet. Saknat eller oläsbart
register redovisas som otillgänglig matchning, aldrig som NO_MATCH. Loggning
innehåller sammanfattade antal; beslutens fulla förklaringar sparas i resultatet.

Grundfiltret behåller de 42 befintliga Vertyp-koderna, inklusive **FBFM**;
**FBRM** läggs inte till. Konto 7698/7699 fungerar med tal och text.
Tomma rapportrader, upprepade rubriker och tydligt märkta summa-/rapportrader
utan transaktionsuppgifter bevaras i Bortfiltrerade med orsak. Andra ofullständiga
rader behålls för validering. TODO: kontrollera detta mot det verkliga rapportformatet.

De verkliga faktura-/registerfilerna finns inte i projektets datamappar.
Referensvärdena **836 / 825 / 11**, **508 / 4 / 313 / 11** och **139 datumvarningar**
har därför inte verifierats. Testerna använder syntetiska data och omfattar även
trunkeringsexemplen, bolagsformskonflikter, flera juridiska personer, flera avtal,
filernas oförändrade bytes/mtime, Streamlit-raddetaljer och Excel-export.

## Numeriska Excel-identifierare

Validering och verifikationsgruppering använder gemensamma jämförelsenycklar i
`src/mapping/identifiers.py`. `Vernr` och `Konto` accepterar Python-/NumPy-heltal
och ändliga flyttal med exakt heltalsvärde. Exempel: `3934106.0` får intern
nyckel `"3934106"`; `3934106.5`, booleska värden och oändlighet avvisas utan
avrundning. `Vrad` accepterade redan heltaliga tal och har kompletterande
NumPy-regressionstester. Andra fält får inga nya valideringsregler.

Text-ID bevaras exakt. `"00123"` är därför en annan identitet än talet `123`,
medan `3934106`, `3934106.0` och texten `"3934106"` delar intern identitet.
Decimal-/exponentliknande text konverteras inte till tal utan säker uppgift
om ursprunget. Endast jämförelsenyckeln normaliseras; källfiler, DataFrame-värden,
radtyper och exporterade källceller bevaras.

Valideringen återanvänder grundfiltrets identifiering av tomma rapportrader,
summa-/rapportrader och upprepade rubriker. Dessa får `NOT_APPLICABLE` med
förklaring och inga fakturavärdesfel. Saknat Vernr på en faktisk transaktion
är fortsatt ett fel. Testerna omfattar en syntetisk float64-tabell med
4 763 identifierare och två rapportrader samt Excel → UI → export.

## Begränsningar i v0.1

- Avtalstrohet, attestregler och obligatoriska verksamhetsfält inväntar AK.
- Bildläsaren utför inte OCR. Bildkoppling och referensregister konfigureras
  inte via UI:t. Koncerninköp kan laddas upp för namnmatchning enligt ovan.
- Rader utan användbart verifikationsnummer behålls i underlaget men grupperas
  inte som verifikationer. Slutlig hantering kräver verksamhetsbeslut.
- Konton normaliseras vid filterjämförelsen (tal, text och omgivande blanksteg).
  Valideringen accepterar även heltaliga Excel-tal enligt ovan. Originalvärden behålls.
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

AK must also confirm field meanings, the internal supplier ID mapping and
attestation rules. The new name-based prototype uses Huvudtext, never
`counterparty`, for supplier candidates. The final sampling method remains
open to confirmation.

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

Kontroll av avtalstrohet, attestkontroll och rätt attestant är fortsatt ej tillgängliga.
Koncerninköp kan användas för den separata leverantörsmatchningen ovan.
TODO: internt leverantörs-ID och attestregler behöver fastställas med AK. Ingen OCR eller systemintegration
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
