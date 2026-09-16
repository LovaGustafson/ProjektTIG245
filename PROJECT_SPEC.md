# Aktuell avgränsning – MoSCoW, september 2026

Detta tillägg preciserar prototypens nuvarande version och har företräde framför
äldre framtidsbeskrivningar nedan:

- De 42 unika standardexkluderingarna för Vertyp finns i `config/settings.yaml`.
  Användaren kan återinkludera dem och exkludera andra förekommande typer i UI.
- Konto 7698/7699 exkluderas genom normaliserad jämförelse av tal/text.
- Kolumnnamn, aldrig Excel-positioner, styr mappning och filtrering.
  Konto och Vertyp behövs för fullständig filtrering; saknade kolumner visas som fel.
- Alla rader bevaras i Granskning eller Bortfiltrerade med samtliga filterorsaker.
  Originaldata och källfil ändras aldrig. Tomma filtervärden exkluderas inte.
- Alla kvarvarande verifikationer analyseras före separat manuellt stickprov.
- UI har Granskning, Bortfiltrerade, Kontroller och Export samt filter och radmått.
- Nya Excel-nedladdningar innehåller granskning, bortfiltrerade och sammanfattning.
- Upphandlings- och attestregister saknas. Kontrollerna, inklusive rätt attestant,
  är ej tillgängliga och ger inga simulerade godkännanden eller underkännanden.
- TODO / AK: leverantörsidentifiering, registerstruktur, attestregler och tidigare
  obesvarade fältbetydelser. OCR och produktionsintegration ingår inte.

# Steg 1


## Problem scope

Systemet ska behandla leverantörsfakturor i form av Excel-filer, analysera
fakturorna och granska för potentiella avvikelser utan att förändra originaldatan. Systemet
ska även kunna läsa av bilder för att ge en helhet.

# Steg 2


# 02 – Datamodell

## Syfte

Syftet med datamodellen är att standardisera kolumnerna från den ursprungliga Excel-filen
till ett enhetligt internt format.

Systemet ska alltid arbeta mot de standardiserade fältnamnen, oavsett hur den ursprungliga
datakällan är strukturerad.

Flöde:

```text
Original Excel
→ Kolumnmappning
→ Validering
→ Standardiserad datamodell
→ Avvikelseanalys
```

## Identitet

**Vernr → `verification_id`**
Datatyp: `string`
Obligatorisk: Ja
Beskrivning: Unikt verifikationsnummer.

**Vrad → `verification_line_id`**
Datatyp: `integer`
Obligatorisk: Ja
Beskrivning: Radnummer inom verifikationen.

## Transaktion

**Verdatum → `verification_date`**
Datatyp: `date`
Obligatorisk: Ja
Beskrivning: Datum för verifikationen.

**Utfall → `amount`**
Datatyp: `decimal`
Obligatorisk: Ja

Beskrivning: Bokfört belopp på raden.

## Kontering

**Konto → `account`**
Datatyp: `string`
Obligatorisk: Ja
Beskrivning: Bokföringskonto.

**Ansvar → `responsibility`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Ansvarsenhet eller organisatorisk ansvarskod.

**Motp → `counterparty`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Motpart.

**Inv → `investment`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Investeringskod eller investeringsreferens.

**Proj → `project`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Projektkod.

**Aktiv → `activity`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Aktivitetskod.

**Ksansv → `cost_responsibility`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Kostnadsansvar.

**Mm → `vat_code`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Moms-/momskod.
Status: Behöver verifieras mot datakällan.

**Pg → `posting_group`**
Datatyp: `string`
Obligatorisk: Nej

Beskrivning: Konterings-/bokföringsgrupp.
Status: Behöver verifieras mot datakällan.

## Klassificering

**Vertyp → `verification_type`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Typ av verifikation.

## Text

**Huvudtext → `header_text`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Övergripande text för verifikationen.

**Radtext → `line_text`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Beskrivande text för aktuell rad.

## Övrigt

**Bild → `image_reference`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Referens eller länk till associerad bild eller dokument.

## Kontroll

**Sign → `signature`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Signatur eller identifiering av signerande person/system.
Status: Behöver verifieras mot datakällan.

**Att → `attestation`**
Datatyp: `string`
Obligatorisk: Nej
Beskrivning: Information om attest/godkännande.
Status: Behöver verifieras mot datakällan.

## Primärnyckel

En unik verifikationsrad identifieras genom kombinationen:

`verification_id + verification_line_id`

Exempel:

`105432 + 3`

Denna kombination ska vara unik i datasetet.

## Regler för saknade värden

Följande fält betraktas som obligatoriska:

- `verification_id`
- `verification_line_id`
- `verification_date`
- `amount`
- `account`

Om något obligatoriskt fält saknas ska raden markeras som ogiltig eller ofullständig.

Systemet ska inte krascha på grund av saknade värden.

Frivilliga fält får innehålla `null`.

## Grundläggande validering

Systemet ska minst kontrollera:

- att `verification_id` finns
- att `verification_line_id` är giltigt
- att `verification_date` kan tolkas som datum
- att `amount` kan tolkas som numeriskt värde
- att `account` finns
- att kombinationen av `verification_id` och `verification_line_id` inte förekommer dubbelt

## Öppna frågor

Följande originalfält behöver verifieras mot datakällans dokumentation:

- `Mm`
- `Pg`
- `Sign`
- `Att`

Vid behov även:

- `Ksansv`
- `Bild`

# 3. Detection Strategy

## 3.1 Filtrering

Agenten ska rensa bort:

- Konto 7698 och 7699
- de Vertyp-värden i kolumn J som AK vill exkludera


## 3.2 Verifikationer

Agenten ska förstå att en verifikation kan ha flera rader:

- Vernr = verifikation
- Vrad = rad i verifikationen

Kontroll ska ske på rätt nivå.


## 3.3 Obligatoriska delar

Agenten ska kontrollera att nödvändiga delar finns, exempelvis:

- Bild
- Sign
- Att

Exakt vad som är obligatoriskt behöver AK bekräfta.


## 3.4 Attestkontroll

Agenten ska kontrollera:

- om attestgången är korrekt
- om rätt person har signerat/attesterat

Det kräver jämförelse mot ett attestregister.


## 3.5 Leverantörskontroll

Leverantörer som inte finns i upphandlingen ska flaggas.

Det kräver ett upphandlings-/leverantörsregister.

## 3.6 Manuellt stickprov

Agenten granskar 100 % av fakturorna.

Efteråt tas ungefär var 20:e faktura ut för manuell kontroll av att agenten gjort rätt.


## 3.7 Resultat

Agenten ska kunna skapa:

- rensat underlag
- flaggade fakturor
- manuellt stickprov

Den ska också ange varför en faktura flaggats.

# 04 – Systemarkitektur

## Syfte

Syftet med systemarkitekturen är att beskriva hur prototypens olika delar samverkar från
inläsning av leverantörsfakturor till färdigt granskningsresultat.

Systemet ska:

- behandla leverantörsfakturor från Excel-filer
- kunna läsa tillhörande fakturabilder
- standardisera och validera data
- filtrera bort poster som inte ska granskas
- analysera verifikationer och deras rader
- kontrollera attest och leverantörer mot referensregister
- flagga potentiella avvikelser
- förklara varför en faktura har flaggats
- skapa ett manuellt stickprov
- aldrig förändra originaldatan

All bearbetning ska ske på en kopia av den data som lästs in.


## 4.1 Övergripande arkitektur

Systemet delas upp i separata komponenter med tydliga ansvarsområden.

```text
           ┌──────────────────────┐
           │ Original Excel │
           │ Leverantörsfakturor │

          └──────────┬───────────┘
                  │
                  ▼
          ┌──────────────────────┐
          │ Excel Reader │
          │    Inläsning       │
          └──────────┬───────────┘
                  │
                  ▼
          ┌──────────────────────┐
          │ Column Mapper           │
          │ Standardisering       │
          └──────────┬───────────┘
                  │
                  ▼
          ┌──────────────────────┐
          │    Validator      │
          │ Datakvalitetskontroll│
          └──────────┬───────────┘
                  │
                  ▼
          ┌──────────────────────┐
          │    Filter Engine │
          │ Exkludering av data │
          └──────────┬───────────┘
                  │
                  ▼
          ┌──────────────────────┐
          │ Verification Builder │
          │ Grupperar Vernr/Vrad │
          └──────────┬───────────┘
                  │
      ┌───────────────┴───────────────┐
      │                      │
      ▼                        ▼
┌────────────────────┐                    ┌────────────────────┐
│ Image Reader │              │ Reference Data │
│ Faktura / dokument │          │           │
│             │        │ Attestregister │
└─────────┬──────────┘                    │ Leverantörsregister│
      │               └─────────┬──────────┘
      │                      │
      └──────────────┬────────────────┘
                ▼
         ┌──────────────────────┐
         │ Detection Engine │
         │                │
         │ Obligatoriska delar │

         │ Attestkontroll     │
         │ Leverantörskontroll │
         │ Övriga avvikelser │
         └──────────┬───────────┘
                 │
                 ▼
         ┌──────────────────────┐
         │ Risk Result        │
         │                │
         │ Flagga            │
         │ Orsak            │
         │ Kontrollresultat │
         └──────────┬───────────┘
                 │
          ┌─────────┴───────────┐
          │               │
          ▼                ▼
    ┌──────────────────┐ ┌──────────────────┐
    │ Resultat / Export│ │ Manual Sampling │
    │            │ │            │
    │ Rensat underlag │ │ Ca var 20:e    │
    │ Flaggade fakturor│ │ faktura     │
    └──────────────────┘ └──────────────────┘
```

## 4.2 Input Layer

Input-lagret ansvarar endast för att läsa in data.

Systemet ska kunna ta emot:

1. leverantörsfakturor i Excel-format
2. fakturabilder eller dokument som hänvisas till genom image_reference
3. attestregister
4. upphandlings-/leverantörsregister

Originalfilerna ska endast läsas.

Systemet får inte skriva över eller förändra originalfilerna.


## 4.3 Excel Reader

Excel Reader ansvarar för att läsa den ursprungliga Excel-filen.

Komponenten ska:

- läsa samtliga relevanta rader
- läsa samtliga relevanta kolumner

- bevara originalvärden
- lämna informationen vidare till Column Mapper

Excel Reader ska inte själv göra någon avvikelsebedömning.


## 4.4 Column Mapper

Column Mapper översätter originalkolumnerna till den standardiserade datamodellen från
steg 2.

Exempel:

Vernr   → verification_id
Vrad    → verification_line_id
Verdatum → verification_date
Utfall  → amount
Konto    → account
Bild    → image_reference
Sign    → signature
Att    → attestation

Efter detta steg ska övriga delar av systemet endast använda de standardiserade
fältnamnen.


## 4.5 Validator

Validator kontrollerar att informationen kan användas av systemet.

Minimikontroller:

- verification_id finns
- verification_line_id är giltigt
- verification_date kan tolkas som datum
- amount är numeriskt
- account finns
- kombinationen verification_id + verification_line_id är unik

Felaktiga eller ofullständiga rader ska markeras.

Systemet ska inte krascha på grund av ett enskilt felaktigt värde.


## 4.6 Filter Engine

Filter Engine tar bort sådant som enligt Detection Strategy inte ska ingå i granskningen.

Initiala regler:

- exkludera account = 7698
- exkludera account = 7699
- exkludera de verification_type som AK beslutar inte ska granskas

Filtreringen ska ske på systemets arbetskopia.

Originalfilen ska förbli oförändrad.


## 4.7 Verification Builder

En verifikation kan innehålla flera rader.

Systemet ska därför bygga upp en verifikation genom:

```text
verification_id
    │
    ├── verification_line_id 1
    ├── verification_line_id 2
    ├── verification_line_id 3
    └── ...
```

verification_id identifierar hela verifikationen.

verification_line_id identifierar en specifik rad inom verifikationen.

Kontroller ska kunna göras både:

- på radnivå
- på verifikationsnivå

Detta är viktigt eftersom vissa avvikelser gäller en enskild konteringsrad medan exempelvis
bild, signering och attest kan behöva bedömas för hela verifikationen.


## 4.8 Image Reader

Image Reader ansvarar för att läsa den fakturabild eller det dokument som kopplas till
verifikationen via:

image_reference

Komponenten ska kunna extrahera relevant information från bilden så att bildinformationen
kan användas tillsammans med Excel-datan.

Syftet är att systemet ska kunna skapa en mer komplett bild av fakturan än genom enbart
Excel-informationen.

Bildinformationen ska inte ersätta originaldata utan användas som kompletterande underlag.

## 4.9 Reference Data

Systemet behöver referensdata för vissa kontroller.

### Attestregister


Används för att kontrollera:

- vem som får attestera
- om rätt person har attesterat
- om attestgången följer definierade regler

### Upphandlings-/leverantörsregister


Används för att kontrollera:

- om leverantören är godkänd
- om leverantören finns inom relevant upphandling

Leverantörer som inte finns i registret ska kunna flaggas.


## 4.10 Detection Engine

Detection Engine är systemets huvudsakliga granskningskomponent.

Den tar emot:

- standardiserad Excel-data
- grupperade verifikationer
- information från fakturabilder
- attestregister
- upphandlings-/leverantörsregister

Detection Engine ska genomföra de kontroller som definierats i steg 3.

### Kontroll A – obligatoriska delar


Kontrollera exempelvis förekomst av:

- image_reference
- signature
- attestation

Exakt vilka delar som är obligatoriska fastställs efter bekräftelse från AK.

### Kontroll B – attest


Jämför:

```text
Fakturans attestinformation
       ↓
   Attestregister
       ↓
   Godkänd / Avvikelse
```

### Kontroll C – leverantör


Jämför leverantören eller motparten mot upphandlings-/leverantörsregistret.

```text
Leverantör
   ↓
Upphandlingsregister
   ↓
Finns → OK
Finns inte → FLAGGA
```

### Kontroll D – övriga avvikelser


Arkitekturen ska göra det möjligt att lägga till ytterligare kontrollregler senare utan att övriga
delar av systemet behöver byggas om.

Varje kontrollregel bör därför implementeras som en separat regel eller modul.


## 4.11 Resultatmodell

Varje genomförd kontroll ska skapa ett tydligt resultat.

Exempel:

verification_id: 105432

status: FLAGGED

reason:
"Leverantören saknas i upphandlingsregistret."

check:
supplier_check

En faktura ska kunna ha flera flaggningsorsaker.

Exempel:

Verification 105432

FLAGGED

Reasons:
- Leverantören saknas i upphandlingsregistret
- Attestanten saknar behörighet
- Fakturabild saknas

Systemet ska alltså inte enbart ange att något är fel.

Det ska även förklara varför fakturan har flaggats.


## 4.12 Manual Sampling

Efter att samtliga fakturor har analyserats ska systemet skapa ett separat manuellt stickprov.

Utgångspunkt:

100 % analyseras automatiskt
        ↓
ca var 20:e faktura
        ↓
manuell kontroll

Stickprovet används för att kontrollera att agentens granskning fungerar som avsett.

Stickprovet ska sparas separat från de fakturor som flaggats automatiskt.


## 4.13 Output Layer

Systemet ska kunna skapa minst tre resultat.

1. Rensat underlag

Data efter definierad filtrering.

Exempelvis utan:

- konto 7698
- konto 7699
- exkluderade verifikationstyper

2. Flaggade fakturor

Lista över potentiella avvikelser.

För varje flaggad verifikation ska minst följande finnas:

verification_id
status
reason

check_type

Vid behov även berörd:

verification_line_id

3. Manuellt stickprov

Separat lista över de fakturor som ska granskas manuellt.


## 4.14 Princip för originaldata

En central arkitekturprincip är:

```text
Originaldata
   │
   │ READ ONLY
   ▼
Arbetskopia
   │
   ├── standardisering
   ├── filtrering
   ├── analys
   └── resultat
```

Originaldata får aldrig förändras.

Alla transformationer och analyser ska göras på data som systemet har läst in till sin egen
arbetsyta.


## 4.15 Modulprincip

Varje huvudfunktion ska hållas separat.

En möjlig framtida kodstruktur är:

```text
src/
│
├── ingestion/
│ ├── excel_reader.py
│ ├── image_reader.py
│ └── reference_reader.py
│
├── mapping/
│ └── column_mapper.py
│
├── validation/
│ └── validator.py

│
├── filtering/
│ └── filter_engine.py
│
├── verification/
│ └── verification_builder.py
│
├── detection/
│ ├── required_fields_check.py
│ ├── attestation_check.py
│ ├── supplier_check.py
│ └── detection_engine.py
│
├── sampling/
│ └── manual_sample.py
│
└── output/
  └── report_generator.py
```

Detta gör att varje del kan utvecklas och testas separat.


## 4.16 Arkitekturprinciper

Systemet ska följa följande grundprinciper:

1. Originaldata är read-only
2. Standardiserade fältnamn används internt
3. Verifikation och verifikationsrad behandlas som olika nivåer
4. Kontrollregler hålls separerade från datainläsning
5. Referensregister hålls separerade från fakturadatan
6. Varje flaggning ska vara förklarbar
7. En felaktig rad får inte krascha hela analysen
8. Nya kontrollregler ska kunna läggas till senare
9. Automatisk granskning och manuellt stickprov hålls separerade
10. Systemet ska kunna kombinera Excel-data och bildinformation


### Då har ni en tydlig kedja

**Steg 1** säger *vad systemet ska lösa.*
**Steg 2** säger *hur datan ska se ut.*
**Steg 3** säger *vad systemet ska kontrollera.*
**Steg 4** säger *hur systemets komponenter ska byggas för att utföra det.*

Det här är tillräckligt detaljerat för arkitektursteget utan att ni börjar bestämma själva
Python-implementationen för tidigt. Nästa naturliga steg är sedan **Steg 5 –
kod-/repositorystruktur och modulernas exakta ansvar**, där vi gör underlaget ännu mer
Codex-redo.

# 05 – Kodstruktur och modulansvar

## Syfte

Syftet med steg 5 är att översätta systemarkitekturen från steg 4 till en konkret
Python-/repositorystruktur.

Varje modul ska ha ett tydligt ansvar.

Grundprincipen är:

En modul = ett huvudsakligt ansvar

Ingen modul ska både läsa data, förändra data, göra avvikelsebedömningar och skapa
rapporter.

Det gör systemet enklare att:

- utveckla
- testa
- felsöka
- förändra
- bygga ut med nya kontrollregler


## 5.1 Repositorystruktur

Föreslagen struktur:

```text
invoice-audit-agent/
│
├── README.md
├── requirements.txt
├── .gitignore
│
├── config/
│ └── settings.yaml
│
├── data/
│ ├── input/
│ ├── reference/
│ └── output/
│
├── src/
│ │
│ ├── main.py

│ ├── pipeline.py
│ │
│ ├── models/
│ │ ├── invoice_row.py
│ │ ├── verification.py
│ │ └── result.py
│ │
│ ├── ingestion/
│ │ ├── excel_reader.py
│ │ ├── image_reader.py
│ │ └── reference_reader.py
│ │
│ ├── mapping/
│ │ └── column_mapper.py
│ │
│ ├── validation/
│ │ └── validator.py
│ │
│ ├── filtering/
│ │ └── filter_engine.py
│ │
│ ├── verification/
│ │ └── verification_builder.py
│ │
│ ├── detection/
│ │ ├── detection_engine.py
│ │ └── rules/
│ │     ├── required_fields_check.py
│ │     ├── attestation_check.py
│ │     ├── supplier_check.py
│ │     └── image_check.py
│ │
│ ├── sampling/
│ │ └── manual_sample.py
│ │
│ └── output/
│    └── report_generator.py
│
└── tests/
  ├── test_mapping.py
  ├── test_validation.py
  ├── test_filtering.py
  ├── test_verification_builder.py
  ├── test_detection.py
  └── test_sampling.py
```

## 5.2 config/settings.yaml

Regler som kan ändras ska inte hårdkodas inne i Python-filerna.

Exempel:

```yaml
excluded_accounts:
  - "7698"
  - "7699"

excluded_verification_types:
  - "EXEMPEL_1"
  - "EXEMPEL_2"

required_fields:
  - image_reference
  - signature
  - attestation

manual_sample_interval: 20
```

När AK senare meddelar vilka Vertyp som ska exkluderas ska dessa alltså kunna läggas
till här.

På samma sätt ska det gå att ändra vad som räknas som obligatoriskt utan att behöva skriva
om Detection Engine.


## 5.3 Datamodeller

Systemet bör ha interna modeller som representerar det data som bearbetas.


### `invoice_row.py`

Representerar en standardiserad Excel-rad.

Exempel:

InvoiceRow

verification_id
verification_line_id
verification_date
amount

account

responsibility
counterparty
investment
project
activity
cost_responsibility
vat_code
posting_group

verification_type

header_text
line_text

image_reference
signature
attestation

Modellen följer alltså datamodellen från steg 2.


### `verification.py`

Representerar hela verifikationen.

Verification

verification_id

rows:
  InvoiceRow
  InvoiceRow
  InvoiceRow
  ...

image_data

checks

Exempel:

Verification 105432

├── Row 1
├── Row 2

├── Row 3
├── Image
└── Check results

Detta gör det möjligt att utföra kontroller på både:

radnivå

och:

verifikationsnivå


### `result.py`

Representerar resultatet från en kontroll.

Exempel:

CheckResult

verification_id
verification_line_id
check_type
status
reason

Exempel:

verification_id: 105432
verification_line_id: null

check_type: supplier_check

status: FLAGGED

reason:
"Leverantören saknas i upphandlingsregistret."

verification_line_id = null betyder att kontrollen gäller hela verifikationen.


## 5.4 Ingestion

### `excel_reader.py`


Ansvar:

```text
Excel-fil
   ↓
Läs data
   ↓
Arbetskopia
```

Modulen ska:

- öppna Excel-filen
- läsa relevanta kolumner
- läsa relevanta rader
- bevara originalvärden
- returnera data till nästa modul

Den ska inte:

- filtrera
- bedöma avvikelser
- ändra originalfilen

Princip:

read_excel(path)

returnerar exempelvis:

raw_dataframe

Originalfilen förblir oförändrad.


### `image_reader.py`

Ansvar:

```text
image_reference
     ↓
hitta dokument
     ↓
läsa dokument
     ↓
extrahera relevant information
```

Image Reader ska endast extrahera information.

Den ska inte själv avgöra om fakturan är felaktig.

Exempel:

Fakturabild

Leverantör: Företag AB
Belopp: 45 000
Fakturanummer: 123456
Datum: 2026-09-03

Informationen skickas sedan vidare till Detection Engine.


### `reference_reader.py`

Ansvarar för extern referensdata.

Exempel:

Attestregister

Leverantörsregister
Upphandlingsregister

Modulen ska läsa registren och skapa strukturer som övriga systemet kan använda.


## 5.5 Column Mapper

### `column_mapper.py`

Ansvar:

```text
Originalkolumn
    ↓
Standardiserat namn
```

Exempel:

```python
COLUMN_MAPPING = {
  "Vernr": "verification_id",
  "Vrad": "verification_line_id",
  "Verdatum": "verification_date",
  "Utfall": "amount",
  "Konto": "account",
  "Vertyp": "verification_type",

    "Bild": "image_reference",
    "Sign": "signature",
    "Att": "attestation"
}
```

Systemets övriga moduler ska aldrig behöva veta att fältet ursprungligen hette Vernr.

Efter detta steg används endast:

verification_id


## 5.6 Validator

### `validator.py`

Validatorn kontrollerar datakvaliteten.

Exempel:

```text
Rad
↓
Validator
↓
VALID / INVALID
```

Kontroller:

verification_id finns

verification_line_id är giltigt

verification_date är datum

amount är numeriskt

account finns

verification_id +
verification_line_id
är unik

En felaktig rad ska exempelvis kunna få:

validation_status: INVALID

validation_errors:
- Missing account
- Invalid amount

Men analysen av resterande dataset ska fortsätta.


## 5.7 Filter Engine

### `filter_engine.py`

Filter Engine ska läsa regler från settings.yaml.

Exempel:

```text
account 7698
    ↓
EXCLUDED

account 7699
    ↓
EXCLUDED
```

Samma princip används för verification_type.

verification_type
     ↓
finns i excluded_verification_types?
     │
    ┌─┴─┐
   JA NEJ
   │ │
 REMOVE KEEP

Viktigt:

Originaldata
  ↓
oförändrad

Arbetskopia
    ↓
filtreras

## 5.8 Verification Builder

### `verification_builder.py`

Verification Builder grupperar rader utifrån:

verification_id

Exempel:

Excel

105432 | 1
105432 | 2
105432 | 3
105433 | 1
105434 | 1
105434 | 2

blir:

Verification 105432
├── row 1
├── row 2
└── row 3

Verification 105433
└── row 1

Verification 105434
├── row 1
└── row 2

Detection Engine ska därefter i första hand arbeta med:

Verification

och inte direkt mot råa Excel-rader.


## 5.9 Detection Rules

Varje kontroll bör vara separat.

Detta är en viktig del av arkitekturen.

Detection Engine
│
├── Required Fields Check
├── Image Check
├── Attestation Check
├── Supplier Check
└── framtida regler


### `required_fields_check.py`

Kontrollerar exempelvis:

image_reference
signature
attestation

Exempel:

Bild saknas

→ FLAGGED

reason:
"Fakturabild saknas."


### `attestation_check.py`

Input:

Verification
+
Attestregister


Kontrollen kan exempelvis vara:

Attestant
  ↓
Finns personen i registret?
  ↓
Har personen rätt behörighet?
  ↓
Är attestgången korrekt?

Resultat:

PASS

eller:

FLAGGED

"Attestanten saknar behörighet för aktuell faktura."


### `supplier_check.py`

Input:

Verification
+
Leverantörs-/upphandlingsregister

Princip:

Leverantör
   ↓
Finns i upphandlingsregister?
   │
┌──┴──┐
JA NEJ
│    │
PASS FLAGGED

Exempel:

reason:
"Leverantören saknas i upphandlingsregistret."

#### Viktig punkt att lösa med AK


Här finns just nu en lucka i datamodellen:

Vilket fält identifierar leverantören?

Ni har bland annat:

counterparty

men det måste bekräftas att detta faktiskt är rätt värde för leverantörskontrollen.

Annars behöver datamodellen kompletteras med exempelvis:

supplier_id
supplier_name
organization_number

Det här bör inte Codex gissa.


## 5.10 Detection Engine

### `detection_engine.py`

Detection Engine styr vilka kontroller som ska köras.

Princip:

```text
for verification in verifications:

  required_fields_check()

  image_check()

  attestation_check()

  supplier_check()

  samla resultat
```

Varje kontroll returnerar ett standardiserat resultat.

Exempel:

Verification 105432

supplier_check
→ FLAGGED

attestation_check
→ FLAGGED

image_check
→ PASS

Slutresultat:

Verification 105432

STATUS: FLAGGED

Reasons:

- Leverantören saknas i upphandlingsregistret
- Attestanten saknar behörighet

Det gör att en faktura kan ha flera avvikelser samtidigt.


## 5.11 Manual Sampling

### `manual_sample.py`

Agenten ska först analysera:

100 % av fakturorna

Stickprovet sker efter analysen.

```text
Alla analyserade verifikationer
        ↓
     ca var 20:e
        ↓
    manuellt stickprov
```

Urvalet ska göras på verifikationsnivå, inte var 20:e Excel-rad.

Det är viktigt eftersom:

1 faktura/verifikation

kan bestå av:

flera Vrad

Exempel:

Verification 1
Verification 2
...
Verification 20 ← SAMPLE
...
Verification 40 ← SAMPLE
...
Verification 60 ← SAMPLE

Exakt metod för stickprovet kan justeras senare om AK vill ha slumpmässigt stickprov i
stället.

## 5.12 Report Generator

### `report_generator.py`

Report Generator ska skapa tre separata outputs.

```text
output/
│
├── cleaned_data.xlsx
├── flagged_invoices.xlsx
└── manual_sample.xlsx
```

### `cleaned_data.xlsx`


Innehåller data efter filtrering.

Exempelvis utan:

account 7698
account 7699
exkluderade verification_type

### `flagged_invoices.xlsx`


Exempel:

| verification_id | line | status | check_type | reason |
|---|---:|---|---|---|
| 105432 |  | FLAGGED | supplier_check | Leverantören saknas i registret |
| 105432 |  | FLAGGED | attestation_check | Attestanten saknar behörighet |
| 105487 | 2 | FLAGGED | required_fields | Obligatorisk information saknas |


### `manual_sample.xlsx`


Separat lista över fakturorna som ska kontrolleras manuellt.


## 5.13 Pipeline


### `pipeline.py`

Pipeline ska koppla ihop modulerna.

```text
1. Läs Excel
     ↓
2. Skapa arbetskopia
     ↓
3. Standardisera kolumner
     ↓
4. Validera
     ↓
5. Filtrera
     ↓
6. Bygg verifikationer
     ↓
7. Läs bilder
     ↓
8. Läs referensregister
     ↓
9. Kör Detection Engine
     ↓
10. Samla resultat
     ↓
11. Skapa manuellt stickprov
     ↓
12. Exportera resultat
```

pipeline.py ska huvudsakligen orkestrera processen.

Den ska inte innehålla själva logiken för exempelvis attestkontrollen.


## 5.14 Main

### `main.py`

main.py blir systemets startpunkt.

I prototypen skulle användaren exempelvis kunna köra:

```bash
python src/main.py
```

Programmet kan då:

```text
Välj Excel-fil
    ↓
Kör granskning
    ↓
Resultat sparas i data/output/
```

Senare kan detta ersättas av ett grafiskt gränssnitt utan att analyslogiken behöver byggas
om.


## 5.15 Felhantering och loggning

Systemet ska inte avbryta hela analysen på grund av en enskild faktura.

Exempel:

Bild 105432 går inte att läsa

ska ge:

WARNING

verification_id: 105432
reason:
"Image could not be read."

och därefter:

fortsätt med 105433

Detta bör även loggas separat.

Exempel:

```text
logs/
└── audit.log
```


## 5.16 Tester

Varje modul ska kunna testas separat.

Exempel:

### `test_mapping.py`


Vernr
↓
verification_id
### `test_filtering.py`


account = 7698
↓
EXCLUDED
### `test_verification_builder.py`


Vernr 100 + Vrad 1
Vernr 100 + Vrad 2

↓

1 Verification
2 Rows
### `test_supplier_check.py`


Leverantör finns i register
→ PASS

Leverantör saknas
→ FLAGGED
### `test_sampling.py`


40 verifikationer
→ ungefär 2 i stickprovet


## 5.17 Definition of Done för första prototypen

Den första tekniska versionen kan betraktas som fungerande när följande kedja fungerar
från början till slut:

```text
Excel
 ↓
Inläsning
 ↓
Mapping
 ↓
Validation
 ↓
Filtering
 ↓
Verification Builder
 ↓
Detection
 ↓
Results
 ↓
Manual Sample
 ↓
Excel-export
```

Och när systemet kan visa exempelvis:

Verification 105432

FLAGGED

Reason:
Leverantören saknas i upphandlingsregistret.

utan att originalfilen har modifierats.


# 06 – Implementation Plan

## Syfte

Syftet är att beskriva i vilken ordning prototypen ska implementeras och testas. Systemet
byggs modulärt enligt arkitekturen i steg 4 och kodstrukturen i steg 5.

Varje del ska implementeras och testas innan nästa påbörjas.

Implementera → Testa → Verifiera → Nästa steg


## 6.1 Implementationsordning

| Steg | Komponent | Huvuduppgift |
|---:|---|---|
| 1 | Projektstruktur & konfiguration | Skapa repository, mappar och settings.yaml |
| 2 | Excel Reader | Läsa Excel utan att förändra originalfilen |
| 3 | Column Mapper | Standardisera kolumnnamn enligt datamodellen |
| 4 | Validator | Kontrollera obligatoriska fält, datatyper och unika rader |
| 5 | Filter Engine | Exkludera konto 7698, 7699 och beslutade verification_type |
| 6 | Verification Builder | Gruppera Vernr och Vrad till verifikationer |
| 7 | Detection Rules | Kontrollera obligatoriska delar, attest och leverantörer |
| 8 | Image & Reference Reader | Läsa fakturabilder och externa register |
| 9 | Detection Engine | Köra och sammanställa samtliga kontrollregler |
| 10 | Manual Sampling | Välja cirka var 20:e verifikation för manuell kontroll |
| 11 | Report Generator | Skapa rensat underlag, flaggade fakturor och stickprov |
| 12 | Pipeline & Main | Koppla samman systemet till ett komplett flöde |
| 13 | Integrationstest | Testa hela lösningen med representativ testdata |


## 6.2 Implementationsprinciper

Vid implementation ska följande principer följas:

- Originaldata ska alltid vara read-only.
- Moduler ska ha ett tydligt och avgränsat ansvar.
- Regler som kan ändras ska ligga i konfiguration och inte hårdkodas.
- Ett fel i en faktura ska inte stoppa hela analysen.
- Varje flaggning ska ange vad som upptäckts och varför.
- Nya kontrollregler ska kunna läggas till utan större förändringar i övriga systemet.
- Varje modul ska testas innan den integreras i den fullständiga lösningen.


## 6.3 Testning under implementation

Testdata ska innehålla både normala och avvikande fall, exempelvis:

- konto 7698 eller 7699
- saknad bild, signatur eller attest
- ogiltigt belopp eller datum
- flera Vrad för samma Vernr
- dubbla verifikationsrader
- leverantör som finns respektive saknas i register
- korrekt respektive felaktig attest

Efter integration ska hela flödet testas:

```text
Excel
→ Mapping
→ Validation
→ Filtering
→ Verification Builder
→ Detection
→ Sampling
→ Export
```

## 6.4 Frågor som måste bekräftas av AK

Följande ska inte bestämmas av systemet eller Codex utan verksamhetsbekräftelse:

- vilka Vertyp som ska exkluderas
- vilka fält som är obligatoriska
- betydelsen av Mm, Pg, Sign, Att, Ksansv och Bild
- vilket fält som identifierar leverantören
- strukturen på leverantörs- och attestregister
- reglerna för korrekt attestgång

Tills detta är fastställt markeras funktionerna som TODO / awaiting business confirmation.


## 6.5 Definition of Done

Prototypen betraktas som tekniskt fungerande när den kan:

1. läsa en Excel-fil utan att ändra originalet,
2. standardisera, validera och filtrera data,
3. gruppera rader till rätt verifikation,
4. genomföra definierade kontroller,
5. förklara varför en verifikation flaggats,
6. skapa ett manuellt stickprov,
7. exportera rensat underlag, flaggade fakturor och stickprov.


# 07 – Teststrategi

## Syfte

Säkerställa att varje del av systemet fungerar korrekt och att agenten inte förändrar
originaldata eller flaggar fakturor utan tydlig anledning.


## 7.1 Vad ska testas?

Systemet ska minst testas för:

- korrekt inläsning av Excel
- korrekt kolumnmappning
- validering av obligatoriska fält
- filtrering av konto 7698 och 7699
- filtrering av exkluderade verification_type
- korrekt gruppering av Vernr och Vrad
- attestkontroll
- leverantörskontroll
- bildhantering
- skapande av flaggningsorsaker
- manuellt stickprov
- att originalfilen aldrig ändras


## 7.2 Testnivåer

### Unit tests


Varje modul testas separat.

Exempel:

validator → hanterar saknat account
filter_engine → tar bort konto 7698
supplier_check → flaggar okänd leverantör

### Integration tests


Kontrollera att flera moduler fungerar tillsammans.

```text
Excel
→ Mapping
→ Validation
→ Filtering
→ Detection
→ Resultat
```

### End-to-end test


En komplett testfil körs genom hela systemet.

Förväntat resultat jämförs med faktiskt resultat.


## 7.3 Testdata

Skapa en mindre testfil med både normala och avvikande fakturor.

Exempel:

Normal faktura
Saknad attest
Ej godkänd leverantör
Konto 7698
Saknad bild
Felaktigt belopp
Dubbel verification_id + verification_line_id

Testdata ska inte innehålla känslig verklig information.


## 7.4 Godkänt resultat

Prototypen är tekniskt godkänd när:

- kända testfall ger förväntat resultat
- filtreringen fungerar korrekt
- avvikelser får en tydlig orsak
- felaktig data inte kraschar systemet
- originaldata förblir oförändrad
- samtliga fakturor kan analyseras


## 7.5 Manuell kontroll

Efter automatisk analys används ungefär var 20:e faktura som manuellt kontrollurval.

Syftet är att jämföra:

```text
Agentens bedömning
    ↕
Mänsklig bedömning
```

Skillnader dokumenteras och används för att förbättra reglerna.


Det där **räcker för steg 7**. Jag hade inte gjort det längre.

Den fortsatta kedjan kan också komprimeras rejält:

**6. Data Flow & Interfaces** → kollegan
**7. Teststrategi** → detta
**8. MVP & UI** → vad användaren faktiskt ska kunna göra
**9. Codex Implementation Plan** → ordningen Codex ska bygga modulerna
**10. Definition of Done** → när prototypen räknas som färdig

Så ni är faktiskt **ganska nära att sluta dokumentera och börja bygga**. Jag skulle inte låta
detta bli ett 70-sidigt designspec-dokument.

Absolut — vi håller 8:an kompakt. Den här kan ni i princip klistra in direkt som
08_mvp_ui.md.


# 08 – MVP & användargränssnitt

## Syfte

MVP:n ska vara en enkel lokal prototyp som visar att systemet kan läsa in
leverantörsfakturor, genomföra definierade kontroller och presentera ett tydligt
granskningsresultat.

Målet är funktionalitet före avancerad design.

## 8.1 Användarflöde

```text
Välj Excel-fil
     ↓
Läs in data
     ↓
Validera och filtrera
     ↓
Analysera fakturor
     ↓
Visa resultat
     ↓
Exportera resultat
```

## 8.2 Funktioner i MVP

Användaren ska kunna:

- ladda upp/välja en Excel-fil
- starta analysen
- se hur många fakturor som analyserats
- se hur många som flaggats
- se varför en faktura har flaggats
- se eventuella datafel
- exportera rensat underlag
- exportera flaggade fakturor
- exportera manuellt stickprov

Originalfilen får aldrig förändras.


## 8.3 Enkel UI


Gränssnittet kan exempelvis visa:

```text
------------------------------------
 Leverantörsfakturagranskning
------------------------------------

[ Välj Excel-fil ]

[ Starta analys ]

Analyserade: 1 240
Flaggade: 38
Datafel:   4

------------------------------------
Vernr | Status | Orsak
------------------------------------
1054 | FLAGGAD | Saknad attest
1082 | FLAGGAD | Leverantör ej godkänd
------------------------------------

[ Exportera resultat ]
```

## 8.4 Fakturadetaljer

När en flaggad faktura väljs bör användaren kunna se:

- verification_id
- relevanta verifikationsrader
- belopp
- konto
- textinformation
- bildinformation om sådan finns
- genomförda kontroller
- flaggningsorsak

En faktura kan ha flera flaggningsorsaker.


## 8.5 Teknik

För prototypen kan ett enkelt lokalt Python-gränssnitt användas, exempelvis Streamlit.

Systemet ska i första versionen kunna köras lokalt utan integration med organisationens
ekonomisystem.


## 8.6 Utanför MVP


Följande behöver inte ingå i första versionen:

- direkt integration med ekonomisystem
- automatisk ändring av fakturor
- automatisk betalningsblockering
- avancerad användarhantering
- produktionsdrift
- fullständig AI/ML-modell

Dessa kan betraktas som möjlig framtida vidareutveckling.


**Steg 8 svarar alltså på:** *Vad är den minsta fungerande prototypen som vi faktiskt ska
bygga och demonstrera?*

Sedan är **9:an Codex Implementation Plan**, och den kan också hållas väldigt kort —
egentligen bara byggordning + vad Codex får/inte får göra.
