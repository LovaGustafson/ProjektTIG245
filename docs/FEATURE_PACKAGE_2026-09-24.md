# Funktionspaket 2026-09-24 — genomförande och verifiering

## Påverkan och återanvändning

Paketet berör M2/M4/M5/M6, S4 och C1–C3. Befintlig verifikationsgruppering,
var-20:e-urval, leverantörsmatchning, kontrollstatusmodell och Excel-serializer
återanvänds. Nya interna exkluderingar påverkar populationen före gruppering och
kan därför ändra stickprovet. Verifikation är den etablerade urvalsenheten;
enskilda transaktionsrader behandlas inte som separata fakturor.

## Implementerat

- UI visar urvalspopulation, intervall, antal valda verifikationer och rader.
  `manual_sample.xlsx` är separat export. Population, första-förekomstordning
  och valda positioner dokumenteras i exporten. 100 valbara verifikationer ger fem val.
- `Slutk123` och `Slutk 123` känns igen. En explicit funktion rensar numrerade
  markörer och whitespace på en jämförelsekopia; originaltexten bevaras.
- Försörjningsförvaltning, Fastighetstöd och mall exkluderas genom exakt
  uttrycksmatchning med case-/whitespace-normalisering. Orsak, regelträffar och
  exkluderade källrader behålls, även när flera regler träffar samma rad.
- Varje avtalsrad för en säkert identifierad leverantör jämförs separat med
  verifikationsdatum. Ursprungliga datum, använd period, regel och motivering
  finns i UI/export. Periodkontroller ändrar inte leverantörsidentitet eller
  fastställer vilket avtal köpet omfattas av. De redovisas separat från den
  befintliga detektionsmotorns flaggade verifikationer.
- `uncertain_suppliers.xlsx` innehåller samtliga kvarvarande källförekomster
  utan stark leverantörsträff. Otillgänglig matchning redovisas som ej genomförd,
  utan fabricerade `NO_MATCH`-resultat. Även ogiltiga/ej grupperbara rader bevaras.
- Standardregister, uppladdad ersättare, avaktivering och återställning hanteras
  utanför matchningsmotorn. UI visar registerkälla och exporter innehåller dess
  namn, hash och utdragsdatum. Omfiltrering återanvänder körningens registerbytes.
- En gemensam körningssammanfattning ger faktiska populations-, exkluderings-,
  kontroll-, leverantörs-, avtalsperiods- och urvalsantal. Ingen påhittad
  granskningsprogress eller signering införs.
- Separata spårbarhetsblad kopplar exportblad/rad till källfilens namn/hash,
  kalkylblad och Excel-rad, även för exkluderade rader och utan register.
  CLI får också `excluded_data.xlsx` med exkluderingsorsaker.

## Verifiering

- Före ändringarna: **585 tester godkända**.
- Efter ändringarna: `.venv/bin/python -m pytest -q` — **633 godkända**.
- `.venv/bin/python -m pip check` — inga trasiga beroenden.
- `git diff --check` — godkänd.
- Dokumentlänkar kontrollerade.

Tester använder syntetiska data och omfattar datum före/under/efter period,
saknade och tvetydiga datum, flera avtal, osäker identitet, registerbyte och
återställning, reproducerbart urval, UI-räkning, Excel-återläsning och exakta
källkopplingar med upprepade/saknade affärsidentifierare. Originalvärden och
källfiler kontrolleras för oförändrat innehåll.

## Kvarstående frågor och saknad data

1. [Q12 — avtalsdatum](requirements/OPEN_QUESTIONS.md#q12--contract-period-date-rules):
   prioritet mellan slutdatum och sista slutdatum, eventuell reservregel när
   ett datum saknas och giltighet på start-/slutdagen behöver bekräftas.
   Berörda oklara fall får `NOT_CHECKED`; inga regler väljs genom antagande.
2. Den faktiska koncerninköpsfilen/sökvägen saknas. Stödet är implementerat och
   testat med syntetiska register, men ett verkligt standardregister kan inte
   aktiveras eller dess schema verifieras utan filen. Konfigurera
   `supplier_matching.default_registry_path`; förvald lokal sökväg är
   `data/reference/koncerninkop.xlsx`. Ingen registerfil läggs i Git.

Befintliga frågor om dubbletter, källsystemets fullständighet och övriga
verksamhetskontroller är oförändrade. Fullständig export av alla validerings-
och icke-flaggade detektionsfynd samt förening av kontrollernas olika
positionssystem återstår; paketet gör inte anspråk på fullständig M6-uppfyllelse.

## Samtliga ändrade eller tillagda filer

| Område | Filer |
| --- | --- |
| Instruktioner och teknisk dokumentation | [AGENTS.md](../AGENTS.md), [PROJECT_SPEC.md](../PROJECT_SPEC.md), [README.md](../README.md) |
| Krav och redovisning | [MOSCOW_CURRENT.md](requirements/MOSCOW_CURRENT.md), [OPEN_QUESTIONS.md](requirements/OPEN_QUESTIONS.md), [denna redovisning](FEATURE_PACKAGE_2026-09-24.md) |
| Konfiguration | [config/settings.yaml](../config/settings.yaml) |
| Filtrering | [filter_engine.py](../src/filtering/filter_engine.py), [internal_suppliers.py](../src/filtering/internal_suppliers.py) |
| Inläsning och registerkälla | [contract_reader.py](../src/ingestion/contract_reader.py), [excel_reader.py](../src/ingestion/excel_reader.py), [registry_source.py](../src/ingestion/registry_source.py) |
| Leverantörsmodell | [models/supplier.py](../src/models/supplier.py) |
| Leverantörs- och avtalsanalys | [analysis.py](../src/supplier_matching/analysis.py), [contract_period.py](../src/supplier_matching/contract_period.py), [date_warning.py](../src/supplier_matching/date_warning.py), [extraction.py](../src/supplier_matching/extraction.py) |
| Pipeline och körningssammanfattning | [pipeline.py](../src/pipeline.py), [run_summary.py](../src/run_summary.py), [main.py](../src/main.py) |
| Stickprov och export | [manual_sample.py](../src/sampling/manual_sample.py), [report_generator.py](../src/output/report_generator.py) |
| UI | [streamlit_app.py](../streamlit_app.py), [ui_support.py](../src/ui_support.py), [ui_supplier_panel.py](../src/ui_supplier_panel.py), [ui_run_summary.py](../src/ui_run_summary.py) |
| Nya acceptans- och regeltester | [test_feature_package.py](../tests/test_feature_package.py), [test_contract_period.py](../tests/test_contract_period.py) |
| Uppdaterade regressionstester | [test_filtering.py](../tests/test_filtering.py), [test_moscow.py](../tests/test_moscow.py), [test_report_generator.py](../tests/test_report_generator.py), [test_supplier_integration.py](../tests/test_supplier_integration.py), [test_ui.py](../tests/test_ui.py), [test_v01_end_to_end.py](../tests/test_v01_end_to_end.py) |
