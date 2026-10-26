# SUDA Fas 3C – Validering av leverantörsidentitet (reviderad plan, version 2)

Gren `feature/suda-identity-validation-fredrik`, HEAD `47d397f`, arbetsträd rent. Endast denna planfil (utanför repot) har skrivits.

Beteckningar: **[BEKRÄFTAT]** läst i kod · **[REPRODUCERAT]** kört i minnet med syntetiska data · **[RISK]** · **[FÖRSLAG]** · **[BESLUT]** kräver mänskligt godkännande.

**Arbetsflöde:** inga automatiska commits, pushar, merges eller PR\:er. Alla Git-operationer kräver uttryckligt mänskligt godkännande. Implementationen lämnas som ändringar i arbetsträdet för granskning.

---

## 0. Svar på granskningens fem punkter

### 0.1 Validering av svenska organisationsnummer: **Invändningen är giltig**

**Bevis:**

- Min version 1 krävde bara 10 siffror, Luhn och en spärr mot nollor. `1212121212` klarar Luhn men har tredje siffran `1`, alltså personnummerform. Den användes som "giltigt" exempel i 3B-fall D ([test_supplier_exact_priority.py:17-18](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/tests/test_supplier_exact_priority.py#L17-L18)) och skulle i v1 ha blivit en användbar organisationsidentitet [REPRODUCERAT: Luhn OK, tredje siffran 1].
- `0000000000` klarar Luhn, men tredje siffran är `0`. Med regeln om tredje siffran blir den separata nollspärren överflödig och tas bort (förenkling).

**Fakta (teknisk struktur, inte affärspolicy):**

- *Svenskt organisationsnummer* (juridisk person): 10 siffror `NNNNNN-NNNN`. Siffra 10 är en Luhn-kontrollsiffra. **Tredje siffran är minst 2** (positionerna 3–4 är ≥ 20), så att numret aldrig kan förväxlas med ett personnummer. Första siffran är en gruppsiffra (t.ex. 5 = aktiebolag, 2 = stat, region eller kommun). Gruppsiffran kontrolleras **inte**: listan över tillåtna värden är inte verifierad i projektet, och att kontrollera den vore en ny regel.
- *Personnummer*: `ÅÅMMDD-NNNC` med Luhn. Tredje siffran (månadens tiotal) är 0 eller 1. `+` används som avgränsare för personer över 100 år. 12-siffrig form `ÅÅÅÅMMDDNNNC`.
- *Samordningsnummer*: som personnummer men dag + 60. Tredje siffran är fortfarande 0 eller 1.
- *Enskild näringsidkare (enskild firma)*: saknar eget organisationsnummer och identifieras med innehavarens **personnummer** (eller samordningsnummer). Den är alltså tekniskt omöjlig att skilja från en privatperson och är dessutom personuppgift.
- *12-siffriga organisationsnummer* (`16` + 10 siffror) förekommer i vissa system.
- En giltig form och kontrollsiffra bevisar **inte** att identiteten är registrerad eller verklig. Det skulle kräva extern verifiering, som inte ingår.

**Rekommenderad korrigering: tekniska statusar**, kontrollerade i ordning efter oförändrad formatering via `organization_key` (mellanslag och `-` tas bort):

| Status                           | Regel                                                                                                                        | Användbar identitet i 3C       |
| :------------------------------- | :--------------------------------------------------------------------------------------------------------------------------- | :----------------------------- |
| `MISSING`                        | NaN/None/bool/blankt                                                                                                         | Nej                            |
| `INVALID_FORMAT`                 | Inte exakt 10 siffror (t.ex. `SAKNAS`, `N/A`, `-`, `+`-form, 12 siffror, utländskt, `'101'`)                                 | Nej                            |
| `INVALID_CHECKSUM`               | 10 siffror, Luhn misslyckas                                                                                                  | Nej                            |
| `NOT_ORGANIZATION_NUMBER_FORMAT` | 10 siffror, Luhn OK, tredje siffran 0/1 (personnummer- eller samordningsnummerform, t.ex. enskild firma, eller `0000000000`) | **Nej, i väntan på beslut D3** |
| `ORGANIZATION_NUMBER_FORMAT`     | 10 siffror, Luhn OK, tredje siffran ≥ 2                                                                                      | **Ja**                         |

- Statusnamnet `NOT_ORGANIZATION_NUMBER_FORMAT` påstår medvetet inte att värdet *är* ett personnummer. Datumdelen valideras inte, eftersom den inte behövs för beslutet.
- Mängden användbara statusar är en konstant i modulen. Ett beslut i D3 blir därmed en ändring på en rad, med tester, utan ny konfiguration.
- **Kvarstående beslut:** D1 (endast svenska nummer), D2 (12-siffrig form), D3 (godta personnummerform för enskild firma), D4 (utländska nummer). Interimsbeteendet ("inte användbart") är det konservativa valet enligt princip 7. Det är **inte** en godkänd affärsregel, och godkännande krävs uttryckligen innan implementationen påbörjas.
- **Utmaning mot granskaren:** att godta personnummerformen vore *inte* "säkrare nuvarande beteende". Dagens kod godtar allt, även `SAKNAS`. Det säkra nuvarande beteendet finns inte, och därför måste valet beslutas.

### 0.2 Invariant för vald leverantör: **Invändningen är giltig, och v1 var ofullständig**

**Bevis [REPRODUCERAT]:** registret `Securitas Svergie AB` (fuzzy, `strong_eligible`) + `Securitas Care AB` (related_name, svag) med frågan `Securitas Sverige AB` ger `AMBIGUOUS_MATCH`. Ett förfalskat resultat `STRONG_MATCH` med `selected_supplier_key` = fuzzykandidaten uppfyller alla villkor i v1-invarianten: den finns, är `strong_eligible`, och ingen annan kandidat är stark. Avtalsperioden skulle då bedömas som PASS för en icke-exakt kandidat bland flera. Orsaken är att matchern ([matcher.py:126-135](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/matcher.py#L126-L135)) bara väljer bland flera kandidater när valet är en **exakt** normaliserad match. Det villkoret saknades i v1.

**Rekommenderad korrigering (minsta säkra, utan duplicerad logik):**

1. Bryt ut valblocket på [matcher.py:124-135](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/matcher.py#L124-L135) till en ren funktion på modulnivå, `select_strong_candidate(candidates) -> SupplierCandidate | None`. Funktionen har exakt samma logik (ensam `strong_eligible`-kandidat, eller unik exakt match utan namnstark konkurrent) och anropas av `SupplierMatcher.match`. Det är en beteendeneutral utbrytning med en enda källa till sanning.
2. I `analyze_suppliers` direkt efter [analysis.py:56](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/analysis.py#L56): räkna fram `expected = select_strong_candidate(result.candidates)` och kräv att `(result.status == STRONG_MATCH) == (expected is not None)` och att `result.selected_supplier_key == (expected.supplier.key if expected else None)`. Vid avvikelse ges `ValueError` med radposition, utan råvärden.
3. Funktionen beror inte på kandidatordningen, så befintligt test [test_supplier_exact_integration.py:82-90](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/tests/test_supplier_exact_integration.py#L82-L90) (omkastad ordning, korrekt nyckel) passerar oförändrat.

Kvarstående gräns: förfalskade *kandidatflaggor* upptäcks inte (de skapas bara av matchern). Det dokumenteras och skyddas inte vidare.

`ValueError` stoppar analysen. Ett avvikande resultat kan bara uppstå genom ett programmeringsfel eller en injicerad matcher, aldrig från data (`pipeline.py:92` injicerar ingen matcher). Enligt AGENTS.md får fel på pipelinenivå stoppa körningen när resultatet annars blir opålitligt. **Beslut D6:** ska detta ingå i 3C (rekommenderas, eftersom princip 4 definieras här) eller i 3D?

### 0.3 Datamodellens konsistens: **Delvis giltig. Modellen förenklas men behåller två fält**

**Bevis [BEKRÄFTAT]:** `Supplier(...)` konstrueras bara på [contract_reader.py:68](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/ingestion/contract_reader.py#L68) (positionsargument, fyra fält). `SupplierCandidate(...)` konstrueras bara på [matcher.py:99](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/matcher.py#L99). Inga tester konstruerar någon av dem direkt. De använder `registry_from_frame` respektive matchern, plus `dataclasses.replace(...)`. Ingen `asdict` används på dessa modeller. Analysen bygger exporten från uttryckligen namngivna fält ([analysis.py:62-78](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/analysis.py#L62-L78)). Likhetsjämförelsen `cached.candidates == result.candidates` ([test_supplier_exact_priority.py:71](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/tests/test_supplier_exact_priority.py#L71)) påverkas inte.

**Rekommendation:**

- `SupplierCandidate.name_strong: bool`, **obligatoriskt** och utan standardvärde, placerat efter `strong_eligible`. Det behövs: utan fältet kan matchern inte låta en konkurrent med ogiltigt nummer blockera. Alternativet att ge `strong_eligible` betydelsen "namnstark" förkastas, eftersom `strong_eligible` exporteras ([analysis.py:21](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/analysis.py#L21)) och dess betydelse i exporten skulle ändras. Obligatoriskt fält gör att ingen framtida konstruktion tyst kan tappa blockeringen. Påverkar inga befintliga konstruktörer.
- `Supplier.organization_number_status: str | None = None`, sista fältet med standardvärde. Konstruktören på rad 68 och `replace()` i tester fungerar oförändrat. Fältet används **bara** för att förklaringen ska vara korrekt: tom `organization_number` med status `MISSING` eller `None` ger befintlig text `Organisationsnummer saknas i registret.`, som UI-mappningen ([ui_supplier_matches.py:51](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/ui_supplier_matches.py#L51)) och testet ([test_ui_supplier_panel.py:144](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/tests/test_ui_supplier_panel.py#L144)) förutsätter. Alla andra statusar ger ny text: `Organisationsnumret i registret är inte ett tekniskt giltigt organisationsnummer.` Fältet styr **inga** beslut. Användbarheten avgörs bara av `organization_number` (sann eller `None`).
- Möjlig förenkling om granskaren föredrar det: utelämna statusfältet och använd en gemensam text. Det avråds från, eftersom "saknas" för ett befintligt men ogiltigt värde är vilseledande. Statusen per rad finns ändå i `registry.issues`.
- Följande ändras **inte**: `SupplierMatch`, exportlistor, `asdict(period)`, UI\:ts `_is_selected_candidate` (en ogiltig kandidat har `organization_number=None` och kan aldrig väljas).

### 0.4 Testbaslinjen: **Invändningen är giltig och klarlagd**

Se §7. Kort: alla 8 fel uppstår bara utan UTF-8-läge. Testerna läser och skriver `config/settings.yaml` med `Path.read_text()`/`write_text()` **utan encoding**, vilket på Windows betyder cp1252. Källkoden läser alltid inställningar med `encoding='utf-8'` (t.ex. [settings.py:30](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/settings.py#L30), [view_scope.py:12](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/view_scope.py#L12), [manual_sample.py:42](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/sampling/manual_sample.py#L42)). Med `PYTHONUTF8=1` blir lokalens kodning UTF-8: 907 passerade, 1 överhoppad, 0 fel. Testfelen är **inte** relaterade till 3C och åtgärdas inte i 3C, men de rapporteras.

Syntetiska nummer som följer den slutliga policyn: hjälparen `org(n) = '559' + f'{n:06d}' + Luhn-siffra` ger tredje siffran 9 och giltig Luhn [REPRODUCERAT: `org(101)=5590001011`, `org(202)=5590002027`, `org(303)=5590003033`, `org(123)=5590001235`, alla Luhn OK]. Hjälparen ska själv testas mot `classify_organization_number` så att policy och fixturer aldrig glider isär.

### 0.5 Arbetsflöde: **Invändningen är giltig och åtgärdad**

Instruktionen om en commit per steg är borttagen. Inga Git-skrivoperationer görs utan uttryckligt godkännande.

---

## 1. Sammanfattning

- **A (bekräftat, bredare än rapporterat):** `organization_key` ([contract_reader.py:17-25](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/ingestion/contract_reader.py#L17-L25)) returnerar valfri text. `Alfa AB/SAKNAS` + `Beta AB/SAKNAS` blir **en** leverantör `org:SAKNAS` som ger STRONG, och Alfa AB\:s avtal bedöms då som identitetsbekräftade [REPRODUCERAT]. Samma sak gäller `-`, `N/A`, `0`.
- **B (felet finns redan i dag):** en namnstark konkurrent med `None` eller blankt nummer blockerar inte exakt prioritering. `Securitas Sverige AB (giltigt)` + `Securitas Svergie AB (None)` ger STRONG [REPRODUCERAT]. Med `SAKNAS` blockerar den bara för att ogiltiga nummer i dag räknas som användbara. Att konvertera till `None` skulle alltså införa revisorns regression.
- **C (bekräftat, ingen produktionsväg):** analysen litar blint på `selected_supplier_key`.
- **Lösning:** teknisk validering med statusar, där bara organisationsnummerformen ger identitet. `name_strong` separerar namnbevis från identitetsanvändbarhet vid blockering. Valet bryts ut till en ren funktion som analysen räknar om och jämför med. Poäng, trösklar, normalisering, datumregler, urvalsalgoritmer och exportkolumner ändras inte.

## 2. Dataflöde och implicit tillit (oförändrad analys från v1)

| Steg                     | Plats                                                                                                                                                                                                                                                                         | Tillit till organisationsnummer          |
| :----------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------- |
| Inläsning/normalisering  | [contract_reader.py:17-25](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/ingestion/contract_reader.py#L17-L25), [:75](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/ingestion/contract_reader.py#L75)                 | Valfri text blir nyckel                  |
| Gruppering               | [contract_reader.py:57-67](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/ingestion/contract_reader.py#L57-L67)                                                                                                                                    | `org:<text>` slår ihop orelaterade rader |
| Kandidat och styrka      | [matcher.py:96-99](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/matcher.py#L96-L99)                                                                                                                                            | Sant värde ⇒ `strong_eligible` möjligt   |
| Konkurrens och val       | [matcher.py:124-142](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/matcher.py#L124-L142)                                                                                                                                        | Blockering bara via `strong_eligible`    |
| Avtalsperiod             | [analysis.py:57-89](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/analysis.py#L57-L89)                                                                                                                                          | Nyckeln kontrolleras inte                |
| Vy-/urvalsklassificering | [view_scope.py:36,58](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/view_scope.py#L36), [classification.py:39-42](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/sampling/classification.py#L39-L42) | Regelvärden valideras inte               |
| Urvalsnyckel             | [manual_sample.py:152-157](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/sampling/manual_sample.py#L152-L157)                                                                                                                                     | `org:<matched>` vid STRONG               |
| UI                       | [ui_supplier_matches.py:58-63](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/ui_supplier_matches.py#L58-L63)                                                                                                                                      | Vald kandidat identifieras via nummer    |
| Export                   | [analysis.py:15-25](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/analysis.py#L15-L25), `report_generator.py:58`                                                                                                                | Tabellerna exporteras oförändrade        |

## 3. Föreslagna ändringar per fil

| Fil                                                                                                                                              | Ändring                                                                                                                                                                                                                                                                                                                                                                                                    |
| :----------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [src/ingestion/contract_reader.py](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/ingestion/contract_reader.py)       | Ny \`classify_organization_number(value) -> (key                                                                                                                                                                                                                                                                                                                                                           |
| [src/models/supplier.py](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/models/supplier.py)                           | \`Supplier.organization_number_status: str                                                                                                                                                                                                                                                                                                                                                                 |
| [src/supplier_matching/matcher.py](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/matcher.py)       | `_candidate`: `name_safe = safe` efter kontrollen av bolagsform (rad 91-95). Statusberoende förklaring på rad 96-98. `select_strong_candidate` bryts ut från rad 124-135, där blockeringen (rad 133) använder `c.name_strong` i stället för `c.strong_eligible`. Rankningen på rad 115 ändras inte (`unknown:`-grupper har ett alias, och för användbara grupper gäller `name_strong == strong_eligible`). |
| [src/supplier_matching/analysis.py](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/analysis.py)     | Omräkning och jämförelse enligt 0.2. Inga ändringar i kolumnlistor.                                                                                                                                                                                                                                                                                                                                        |
| [src/supplier_matching/view_scope.py](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/supplier_matching/view_scope.py) | Rad 36-39: organisationsregler kräver användbar status, annars `ValueError` (befintlig felväg). `comparison_key` = validerad nyckel. Påverkar även urvalsregler via `sampling_rules`. Båda listorna i konfigurationen är tomma i dag.                                                                                                                                                                      |
| [src/ui_supplier_matches.py](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/src/ui_supplier_matches.py)                   | Rad 51: läsbar ersättning för den nya förklaringen.                                                                                                                                                                                                                                                                                                                                                        |
| [PROJECT_SPEC.md](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/PROJECT_SPEC.md)                                         | §12 rad 226 (gruppering), rad 236 (blockering via namnstyrka oberoende av identifierare, val via `select_strong_candidate`), ny punkt om statusar och om att validering ≠ juridisk verifiering, notering om omanalys (som på rad 246/260).                                                                                                                                                                 |
| [docs/requirements/OPEN_QUESTIONS.md](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/docs/requirements/OPEN_QUESTIONS.md) | Ny fråga om policy för organisationsnummer: D1–D4 och D7.                                                                                                                                                                                                                                                                                                                                                  |

Följande ändras **inte**: `manual_sample.py`, `classification.py`, `contract_period.py`, `report_generator.py`, `pipeline.py`, `normalization.py`, `settings.py`, `settings.yaml`.

## 4. Samspel med Fas 3B och risker för befordran till STRONG

- För användbara identiteter gäller `name_strong == strong_eligible`, så alla 3B-utfall mellan giltiga identiteter är identiska (när fixturerna har migrerats till `org(n)`).
- **Avsiktlig skärpning:** en namnstark konkurrent som saknar nummer, har ett ogiltigt nummer eller har personnummerform blockerar nu (STRONG→AMBIGUOUS). Fallet `numberless-nonexact-alternative` (`Bonliva Care AB/None`, related_name) förblir STRONG eftersom konkurrenten inte är namnstark.
- Ingen väg leder till befordran: uppdelning av `org:SAKNAS` ger fler kandidater med bevarad `name_strong`, och exakta delar räknas i `len(exact)`. En ensam kandidat med ogiltigt nummer kan aldrig bli STRONG.

## 5. Avtal, klassificering, urval, dashboard och export

- Avtal: oförändrad `check_contract_period`. Bara identiteten från `select_strong_candidate` får `identity_confirmed=True`. Grupper med ogiltiga nummer får aldrig PASS.
- Urval och klassificering: algoritmerna ändras inte. Rader som tidigare var STRONG via ogiltiga nummer eller B1 får nyckeln `name:`, så urvalet kan ändras **vid omanalys**. Sparade urval matchas inte om. Orelaterade `SAKNAS`-leverantörer blir inte längre falska dubbletter.
- Export: inga nya kolumner. Värdeändring: kandidattabellens `organization_number` blir tom för ogiltiga nummer. Råvärdet finns kvar i avtalsraden och i `registry.data` (**beslut D5**).

## 6. Migrering av testfixturer

1. Ny hjälpare `tests/synthetic_org.py` med `org(n)` enligt 0.4 och ett eget test mot `classify_organization_number`.
2. Mekanisk ersättning där testet avser en giltig identitet: `'101'` → `org(101)`, `'org:101'` → `f'org:{org(101)}'`. Förväntade statusar ändras inte.
3. 3B-fall D (`121212-1212`/`1212121212`): avsikten är att alias med samma organisation, i bindestrecksform och kompakt form, grupperas. Migreras till `org(121)` i båda formerna. Under nuvarande värden skulle fallet bli AMBIGUOUS av en orelaterad orsak (personnummerform). Det dokumenteras.
4. Formateringstester ([test_contract_reader.py:9](vscode-webview://137j0s5nia3qlca1m4srkhpftg09ddesrikho1ahbmotfgd7n9as/tests/test_contract_reader.py#L9)): giltiga `org(n)` i båda formerna.
5. Tester som medvetet använder saknade nummer (`None`, `''`, `' '`, `True`) är oförändrade.
6. Regelvärden (`test_priority2.py:187,232`, `test_sampling_quota.py:133`, `test_supplier_reliability_integration.py:26`, `test_supplier_exact_integration.py:132`) samt direkt konstruerade `matched_organization_number` som jämförs mot regler migreras till `org(n)`.
7. Varje test vars förväntade status måste ändras listas med motivering. Förväntat antal: noll.

## 7. Testbaslinje (före 3C)

Körd med `PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider`. `git status --short` var tom efter varje körning.

| Läge                       | Resultat                                       |
| :------------------------- | :--------------------------------------------- |
| Utan `PYTHONUTF8` (cp1252) | 899 passerade, 8 misslyckade, 1 överhoppad     |
| `PYTHONUTF8=1`             | **907 passerade, 1 överhoppad, 0 misslyckade** |

De 8 felen utan UTF-8-läge:

| #   | Test                                                                                                                                                                   | Symptom                                                             | Orsak                                                                                                       |
| :-- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------ | :---------------------------------------------------------------------------------------------------------- |
| 1   | `test_contract_reader.py::test_excel_metadata_explicit_aliases_and_csv_are_read_only`                                                                                  | CSV-registret blir otillgängligt (rad 48)                           | `csv.write_text(...)` (rad 47) skriver `Leverantör` som cp1252. Läsaren använder `csv_encoding` `utf-8-sig` |
| 2   | `test_feature_package.py::test_default_uploaded_disabled_and_restored_registry_sources`                                                                                | `assert 0 == 1` (rad 169, antal STRONG)                             | Inställningskopian får förvanskade rubrikalias (rad 163-165), så registret matchar inte                     |
| 3   | `test_feature_package.py::test_default_csv_format_is_independent_of_its_display_name`                                                                                  | `assert False` (rad 203, `loaded.available`)                        | Samma inställningskopia via hjälparen `settings()` (rad 41-44)                                              |
| 4   | `test_priority2.py::test_strong_aliases_share_organization_key_and_matching_is_unchanged`                                                                              | Urvalet blir `['2','4','6']` i stället för `['2','5','6']` (rad 91) | Inställningarna skrivs om som cp1252 (rad 86-87), så rubrikalias försvinner och urvalsnycklarna ändras      |
| 5–8 | `test_priority2.py::test_view_classification_…`, `…unconfirmed_rules_…`, `…confirmed_organization_view_rule_…`, `…organization_rule_does_not_use_ambiguous_candidates` | `UnicodeDecodeError` (byte `0xe4`)                                  | `write_rules` (rad 110-113) skriver YAML med `allow_unicode` i cp1252. Källkoden läser UTF-8                |

Inget av felen rör organisationsnummer eller matchningslogik.

Mekanism: hjälparna i testerna (`test_priority2.py:111-113`, `test_feature_package.py:41-44,163-165`) läser UTF-8-filen `config/settings.yaml` som cp1252, vilket ger mojibake i svenska rubrikalias som `Leverantör`. Sedan skrivs den tillbaka som cp1252. Applikationen läser med `encoding='utf-8'`. Följden blir antingen `UnicodeDecodeError` (byte `0xe4` = `ä`), eller att rubrikalias och regelvärden inte känns igen, vilket ger fel antal träffar eller fel urval. 3C rättar inte detta (utanför scope). Efter implementationen körs `PYTHONUTF8=1 python -m pytest -q`, och utan UTF-8 ska exakt samma 8 fel kvarstå och inga fler.

## 8. Nya regressionstester

- **Validering:** statusmatris för `MISSING`/blankt, `SAKNAS`, `N/A`, `-`, `+`-form, 9/11/12 siffror, felaktig kontrollsiffra, `0000000000`, `1212121212` (personnummerform), `org(n)` med och utan bindestreck, float från Excel. Problemmeddelanden innehåller inte råvärdet.
- **Gruppering:** orelaterade `SAKNAS`- och personnummerformsrader blir separata `unknown:`-leverantörer. Flera rader med samma giltiga nummer blir en grupp. Källramen är oförändrad.
- **Blockering:** exakt match plus `Securitas Svergie AB` med `None`/`''`/`SAKNAS`/felaktig kontrollsiffra/personnummerform/`'202'` ger AMBIGUOUS. Samma med prefixkonkurrent. Exakt match med ogiltigt nummer som ensam kandidat ger AMBIGUOUS. 3B-påståendet på rad 52 utökas med `not c.name_strong`.
- **Selektionskonsistens:** förfalskad STRONG på fuzzykandidat bland flera (scenariot i 0.2), nyckel till svag kandidat, nyckel som saknas, nyckel satt vid AMBIGUOUS: alla ger `ValueError`. Testet med omkastade kandidater passerar. `select_strong_candidate` ger samma resultat som matchern för alla `CASES` i båda ordningarna.
- **Avtal:** `SAKNAS`-grupp och ej valda konkurrenter ger bara NOT_CHECKED. PASS endast för vald giltig identitet.
- **Klassificering och urval:** organisationsregel med ogiltigt värde eller personnummerform ger `ValueError`. Två orelaterade `SAKNAS`-leverantörer får olika `name:`-nycklar och blir inte DUPLICATE_SUPPLIER, i både systematiskt och slumpmässigt urval (fast seed).
- **Export och UI:** kolumnlistorna är oförändrade (befintliga påståenden), och förklaringen för ogiltigt nummer i `readable_reason` testas.
- **Skydd för Fas 3B:** hela `CASES` × båda ordningarna, `test_all_orders_keep_candidates_scores_and_selected_identity`, `test_any_strong_eligible_alias_of_competing_identity_blocks_exact_priority`, `test_selected_identity_without_contract_rows_never_borrows_an_alternative_contract` och hela `test_supplier_matching_reliability.py` (poäng och fuzzy-skydd är oförändrade).

## 9. Öppna affärsbeslut (kräver godkännande)

| ID | Fråga                                                                                                                  | Interimsbeteende i planen (inte en godkänd regel) |
| :- | :--------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------ |
| D1 | Innehåller registret bara svenska organisationsnummer?                                                                 | Annat ger `INVALID_FORMAT`                        |
| D2 | Ska den 12-siffriga formen `16NNNNNNNNNN` normaliseras?                                                                | Nej, `INVALID_FORMAT`                             |
| D3 | Ska personnummer- eller samordningsnummerform (enskild firma) godtas som leverantörsidentitet? Det rör även dataskydd. | Inte användbar, AMBIGUOUS, manuell granskning     |
| D4 | Hur hanteras utländska leverantörer?                                                                                   | `INVALID_FORMAT`                                  |
| D5 | Kandidattabellen: tomt fält eller råvärde för ogiltigt nummer?                                                         | Tomt fält, råvärdet finns i avtalsraden           |
| D6 | Invariantskyddet för val: i 3C eller 3D? Stoppa körningen eller degradera?                                             | 3C, `ValueError`                                  |
| D7 | Lokal profilering av det verkliga registret före merge (bara antal per status, inga värden lämnar maskinen, M7)?       | Rekommenderas                                     |

## 10. Ordnad implementationsplan (inga commits)

1. `classify_organization_number` + testhjälparen `org(n)` + statustester.
2. Gruppering och `organization_number_status` + migrering av fixturer + full testkörning för att bekräfta oförändrade statusar.
3. `name_strong` + `select_strong_candidate` (beteendeneutral utbrytning, verifieras med befintliga 3B-tester **innan** blockeringen ändras) + ändrad blockering + B-tester.
4. Invariantskydd i `analyze_suppliers` + C-tester.
5. Validering av regelvärden + migrering och tester för regler.
6. UI-förklaring + test.
7. PROJECT_SPEC + OPEN_QUESTIONS.
8. `PYTHONUTF8=1 python -m pytest -q`, `python -m pip check`, manuell rökprovning i Streamlit med syntetiskt register.

Stoppa om ett test misslyckas utan förklaring. Ändringarna lämnas ocommittade för mänsklig granskning.

## 11. Acceptanskriterier

- Ingen `Supplier.organization_number` utan användbar status. Orelaterade rader med ogiltiga eller saknade nummer grupperas aldrig.
- Ingen STRONG_MATCH utan användbart organisationsnummer. PASS bara för den vald och användbar identitet som `select_strong_candidate` ger.
- En namnstark konkurrent blockerar oavsett nummerstatus.
- Alla 3B-fall mellan giltiga identiteter ger identiska statusar, kandidatordning och poäng.
- Ett inkonsekvent `selected_supplier_key` ger `ValueError`, aldrig PASS.
- Exportkolumner och filnamn är oförändrade. Käll- och registerramar är oförändrade.
- `PYTHONUTF8=1`: alla tester gröna. Utan UTF-8: samma 8 miljöfel och inga nya.

## 12. Risker

| Risk                                                                    | Åtgärd                                                                             |
| :---------------------------------------------------------------------- | :--------------------------------------------------------------------------------- |
| Andelen STRONG sjunker (Excel-nollor, 12-siffrig form, enskilda firmor) | D2/D3/D7, tydliga statusmeddelanden                                                |
| Felmigrerade fixturer                                                   | Mekanisk `org(n)`, hjälparen testas mot policyn, motivering per ändrad förväntan   |
| `ValueError` från en framtida anpassad matcher                          | Avsiktligt, dokumenteras                                                           |
| Personnummer i meddelanden eller loggar                                 | Råvärdet skrivs aldrig ut. Statusnamnet påstår inte att värdet är ett personnummer |
| Formvalidering tolkas som juridisk verifiering                          | Text i spec och UI                                                                 |

## 13. Gränser

Följande ingår inte: extern verifiering av identitet, kontroll av gruppsiffra, datumvalidering av personnummer, ny exportkolumn, ändrade trösklar, poäng eller normalisering, ändrade datum- eller urvalsregler, ny UI-vy, konfigurerbar valideringspolicy, rättning av testernas kodningsfel, Git-operationer.

## 14. Git-status

Före och efter granskningen: `feature/suda-identity-validation-fredrik`, `47d397f`, rent arbetsträd (verifieras igen före överlämning). **Uttryckligt godkännande krävs före implementation**, liksom beslut om minst D1, D3 och D6.