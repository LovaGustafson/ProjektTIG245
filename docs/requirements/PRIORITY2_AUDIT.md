# Prioritet 2 – audit och bekräftad implementation

Datum: 2026-09-30. Krav: M5/M6 och C1–C3.

Read-only audit genomfördes före implementation mot `manual_sample.py`,
`pipeline.py`, verifieringsbyggaren, leverantörsmodellerna, extraktion,
normalisering, registerläsaren, matchningsmotorn, basfiltren, konfigurationen,
UI/export och relevanta syntetiska tester. Projektets datamappar innehöll inga
kundfiler eller register att verifiera faktiska förekomster mot. Inga verkliga
källvärden lästes eller ändrades.

## Stickprovet före ändringen

- Enheten var en hel verifikation, grupperad på befintlig normalisering av Vernr.
- Alla grupper analyserades först. Position 20, 40, 60 osv. valdes i första-förekomstordning efter basfiltrering.
- Urvalet saknade leverantörsunikhet. Önskat antal motsvarade heltalsdelen av gruppantal / 20.
- Raderna behöll originalvärden och källindex. Vernr/Vrad var inte ensamma källidentiteter.

## Identitet och explicit bekräftelse

Registret grupperar juridiska leverantörer på normaliserat organisationsnummer.
Stark träff har ett entydigt matchat organisationsnummer; osäkra träffar behåller
kandidater utan vald leverantör. Identiteten är radbaserad, så en verifikation kan
innehålla saknad eller flera leverantörsidentiteter.

Användaren bekräftade under arbetet:

> Använd normaliserat namn från Huvudtext när stark träff saknas; verifikationer med saknad eller flera leverantörsidentiteter redovisas utanför stickprovet.

Nyckeln blir därför `org:<organisationsnummer>` vid befintlig STRONG_MATCH, annars
`name:<normaliserat extraherat namn>`. Befintlig extraktion använder texten före
Prelb/Slutk. Normalisering använder Unicode NFKC, skiftläge, blanksteg, interpunktion
och uttryckligen likvärdiga bolagsformer, exempelvis Aktiebolag → AB. Å/Ä/Ö och
skilda bolagsformer förblir skilda. Inga nya fuzzy-regler införs. Motp används inte.
En namnnyckel är inte en verifierad juridisk identitet.

Alla rader måste ha samma nyckel för att gruppen ska kunna väljas. Saknad nyckel
eller flera nycklar ger en dokumenterad orsak utanför stickprovet. En redan vald
nyckel **eller** ett redan valt normaliserat extraherat namn stoppar ett nytt val.
Olika starkt matchade namn med samma organisationsnummer kan därför inte väljas dubbelt.

## Urvalet efter ändringen

Ordinarie positioner och målantal behålls. Varje plats börjar på sin ordinarie
position, eller efter senast prövade kandidat om den redan passerats. Vid
upprepning eller oanvändbar identitet prövas nästa verifikation framåt.
Nästa ordinarie intervallposition flyttas inte. Exempel vid intervall 20:
20 väljs, 40 är en upprepning, 41 väljs, därefter prövas 60.

Det finns ingen randomisering, återgång till tidigare positioner eller utfyllnad
med dubletter. Om sökningen tar slut blir stickprovet mindre, även om andra namn
kan finnas på tidigare oprövade positioner. Mål, faktiskt antal och orsaker visas
i UI, CLI och Excel. Alla beslut och radidentiteter bevaras; exporterade
urvalspositioner kommer från faktiska val och inte längre en modulo-beräkning.
Matchning, flaggning, basfilter, gruppering och källdata är oförändrade.

## Intern/extern: svar A–D

**A. Generell klassificering:** Nej. Det finns inget dokumenterat auktoritativt
intern/extern-fält eller generellt organisationsnummerkriterium i nuvarande schema.
Kontraktskategori/nivåer och Motp ger inte stöd för en sådan slutsats.

**B. Befintlig regel:** `excluded_internal_suppliers` matchar hela uttrycket från
Huvudtext med Unicode-, skiftläges- och blankstegsnormalisering. Den befintliga
bekräftade listan är Försörjningsförvaltning, Fastighetstöd och mall. Det är ett
basfilter, inte en generell klassificerare, och det har inte ändrats.

**C. Poster:** Endast uttryck som exakt träffar dessa tre regler har stöd av det
befintliga basfiltret. Faktiska radförekomster kan inte anges utan godkänt
kundunderlag. Den nya leverantörsvyn har initialt noll extra exkluderingar.

**D. Exemplen:** Apoteket, Securitas och Kantarellen träffar inte regeln.
Försörjningsförvaltningen träffar inte heller Försörjningsförvaltning: ändelsen
`en` tas inte bort. Detta säger inget om deras verkliga organisatoriska status.
Exemplen har inte lagts in som aktiva affärsregler.

## Isolerad mekanism för bekräftade vyregler

`supplier_view_rules: []` är standard. Varje framtida regel behöver `id`,
`match_field`, `value`, `classification`, `reason` och `confirmed`.
Följande är **endast ett syntetiskt konfigurationsexempel**, inte en aktiverad regel:

```yaml
supplier_view_rules:
  - id: synthetic-example
    match_field: supplier_name
    value: "Syntetiskt Exempel AB"
    classification: INTERNAL
    reason: "Ersätt med faktiskt bekräftad avgränsning och motivering."
    confirmed: false
```

`organization_number` är det andra tillåtna matchfältet och kräver stark träff.
Namn matchas exakt efter befintlig extraktion/normalisering; det är inte en
heuristik för att avgöra om företag är interna. Klassificeringar är INTERNAL,
NOT_RELEVANT eller EXTERNAL. Endast bekräftade regler aktiveras. Utan träff är
raden UNCLASSIFIED, inte extern. Motstridiga regler ger CONFLICT och raden visas.

INTERNAL/NOT_RELEVANT påverkar endast leverantörssammanfattningarna och deras
drill-down. Exkluderat antal räknar källrader; regel, värde, orsak och källrader
kan inspekteras. Hela granskningsunderlaget, matchningsevidensen, avtalsöversiktens
totaler och stickprovet behålls. Excelbladet Leverantörsvy dokumenterar besluten.

## Öppet

Q13: exakt bekräftad lista/auktoritativ klassificeringskälla samt om ett framtida
stickprov ska begränsas till externa leverantörer. Ingen sådan urvalsbegränsning
har införts. Vidare bevarande-/godkännandekrav för urvalsunderlag förblir Q2.

## Verifiering

- Hela sviten: `.venv/bin/python -m pytest -q` — **678 passed** (189,22 s).
- `.venv/bin/python -m pip check` — inga brutna beroenden.
- `git diff --check` — inga whitespace-fel.
- Nya tester täcker namnnormalisering, organisationsnummer/alias, determinism,
  framåtersättning över intervallgränser, mindre stickprov, saknad/flera identiteter,
  oförändrade källvärden, uttrycklig klassificering, konflikter/obekräftade regler,
  oförändrad matchning, inspekterbara vyexkluderingar och UI/Excel-evidens.

## Fullständig fillista

- [AGENTS.md](../../AGENTS.md)
- [PROJECT_SPEC.md](../../PROJECT_SPEC.md)
- [README.md](../../README.md)
- [config/settings.yaml](../../config/settings.yaml)
- [docs/requirements/MOSCOW_CURRENT.md](../../docs/requirements/MOSCOW_CURRENT.md)
- [docs/requirements/OPEN_QUESTIONS.md](../../docs/requirements/OPEN_QUESTIONS.md)
- [docs/requirements/PRIORITY2_AUDIT.md](../../docs/requirements/PRIORITY2_AUDIT.md)
- [src/main.py](../../src/main.py)
- [src/output/report_generator.py](../../src/output/report_generator.py)
- [src/pipeline.py](../../src/pipeline.py)
- [src/run_summary.py](../../src/run_summary.py)
- [src/sampling/manual_sample.py](../../src/sampling/manual_sample.py)
- [src/supplier_matching/view_scope.py](../../src/supplier_matching/view_scope.py)
- [src/ui_overview_details.py](../../src/ui_overview_details.py)
- [src/ui_run_summary.py](../../src/ui_run_summary.py)
- [src/ui_supplier_panel.py](../../src/ui_supplier_panel.py)
- [src/ui_support.py](../../src/ui_support.py)
- [streamlit_app.py](../../streamlit_app.py)
- [tests/test_feature_package.py](../../tests/test_feature_package.py)
- [tests/test_pipeline.py](../../tests/test_pipeline.py)
- [tests/test_priority2.py](../../tests/test_priority2.py)
- [tests/test_sampling.py](../../tests/test_sampling.py)
- [tests/test_ui.py](../../tests/test_ui.py)
- [tests/test_ui_filter_panel.py](../../tests/test_ui_filter_panel.py)
- [tests/test_ui_overview_details.py](../../tests/test_ui_overview_details.py)
- [tests/test_ui_run_summary.py](../../tests/test_ui_run_summary.py)
- [tests/test_v01_end_to_end.py](../../tests/test_v01_end_to_end.py)
