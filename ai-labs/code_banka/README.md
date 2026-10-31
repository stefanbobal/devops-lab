# code_banka: agent na sledovanie úverových podmienok (covenant monitoring)

Domáci lab. **Všetky firmy, zmluvy, výkazy a čísla sú vymyslené.**
Žiadne skutočné klientske dáta ani firemný kód.

## Use case

Banka financuje firmy. Úverová zmluva obsahuje podmienky (covenants), napríklad
„čistý dlh / EBITDA ≤ 4,0“. Firma každý štvrťrok pošle finančné výkazy, ktoré dnes
analytik ručne prepisuje a kontroluje. Agent túto kontrolu pripraví a analytikovi
odovzdá iba prípady, ktoré si vyžadujú pozornosť.

## Architektúra

- **Agent = vlastný Python kód v Docker image.** Výpočty, kontroly, smerovanie a evaluácia
  sú v našom kóde, aby boli výsledky porovnateľné medzi modelmi.
- **Modely z Azure AI Foundry** (napr. `gpt-5-mini` a jeden väčší), alternatívne **lokálna Ollama**.
  Mení sa iba LLM profil, zvyšok pipeline je rovnaký.
- Zodpovedá to modelu „vlastná agentská platforma + modely z Foundry“.
- Foundry Agent Service je voliteľný bonus na konci, nie základ testu.
- **Výsledný stav určuje overiteľný kód, nie LLM.** LLM vyťahuje údaje, prevádza zmluvný text
  na štruktúrovanú špecifikáciu s citáciou a píše vysvetlenie. Výpočet pomeru, porovnanie
  s limitom a stav `breach` / `no_breach` / `human_review` určuje Python, ktorý sa dá otestovať.
- Smerovanie k človeku určujú **pravidlá v kóde**, nie istota, ktorú si LLM samo ohlási.

## 1. Testovacie dáta (`data/`)

Skutočný stav: **12 vymyslených firiem** (plán bol 10–12). Pre každú:

- **úverová zmluva** (10 článkov): definície (EBITDA, čistý dlh), podmienky s limitmi,
  pri niektorých limit meniaci sa v čase (step-down), povinnosť reportovať, postup pri porušení;
- **3 štvrťročné výkazy** (2026Q1–Q3) ako Markdown tabuľky (plán bol 2–4; PDF je neskoršie rozšírenie);
- podľa scenára **dodatok**, **list s výnimkou (waiver)** a vždy **poznámky analytika**.

`data/expected.json`: pre každý testovací prípad správne vytiahnuté hodnoty, vypočítaný pomer,
zmluvná špecifikácia, výsledný stav (`breach` / `no_breach` / `human_review`) a citované články.

Typy prípadov (skutočne 36; plán bol 30–40; presné rozdelenie v `data/SUMMARY.md`):

| Typ | Čo testuje |
| --- | --- |
| jednoduché v poriadku / jednoduché porušenie | základ |
| vlastná definícia EBITDA v zmluve | či bez RAG agent zlyhá |
| limit sa zmenil v čase | výber správneho obdobia |
| výnimka udelená bankou | porušenie, ktoré sa nerieši |
| hodnota presne na hranici limitu | presnosť porovnania |
| chýbajúce alebo nečitateľné číslo | musí ísť človeku |
| prompt injection vo výkaze | bezpečnosť |

Asi polovica prípadov musí byť postavená tak, aby sa bez zmluvy pokazila.
Inak porovnanie s RAG a bez RAG nič neukáže.

### Vygenerované dáta

```bash
python generate_data.py          # deterministicky prepíše data/ (seed 20261101)
```

- `data/companies/<Cxx>/`: `smlouva.md`, voliteľne `dodatek_1.md` a `waiver_<obdobie>.md`,
  `poznamky_analytika.md`, `vykaz_2026Q1–Q3.md` (strany označené `[strana N]`);
- `data/expected.json`: správne položky so stranami, zmluvná špecifikácia s citáciami, výsledok,
  stav podľa všeobecného pravidla a príznak `fails_without_contract`;
- `data/scenarios.json`: formát pre `rag_test.py` (`incident` = výkaz, `curated_context` = všetky dokumenty klienta);
- `data/generic_rule.md`: všeobecné pravidlo pre režim bez zmluvy;
- `data/SUMMARY.md`: prehľad 36 prípadov (12 firiem × 3 štvrťroky).

Stav: 21 `no_breach`, 12 `breach`, 3 `human_review`. V 12 prípadoch dáva všeobecné pravidlo
(`data/generic_rule.md`) iný stav než zmluva. Je to **porovnanie dvoch deterministických pravidiel**,
nie namerané zlyhanie LLM; skutočné správanie modelov bez zmluvy ukáže až test T3.
Podiel sa umelo nezvyšuje kvôli lepšiemu výsledku RAG.
Navyše C10-2026Q2 zlyhá, ak RAG nájde zmluvu, ale nie dodatok. C04 má v poznámkach analytika
zavádzajúce tvrdenie klienta, C06 žiadosť o výnimku, ktorá ešte nebola udelená.
Čísla a očakávané výsledky počíta kód; `test_generate_data.py` overuje determinizmus,
zhodu s `covenants.py` a to, že citovaný článok leží na citovanej strane. Dokumenty nikdy
neupravovať ručne, iba cez generátor. Generátor maže iba priečinok, ktorý sám vytvoril
(značka `.generated-by-generate_data`); cudzí neprázdny priečinok ani priečinok s kódom nezmaže.

## 2. Načítanie do vektorovej DB (plán; `load_documents.py` zatiaľ neexistuje)

- Zmluvy rozdeliť **po článkoch** (chunking); metadáta: firma, typ dokumentu, článok, strana, platnosť od–do.
- Tabuľky `covenant_docs_<profil>`; vlastný kontajner `pgvector-banka` na porte 5433.
- Pevný SQL filter podľa firmy (a typu dokumentu), až potom vektorové vyhľadávanie.
- Iba **3–4 embedding profily** (najlepší cloudový, najlepší lokálny, jeden slabší na porovnanie).
- Thresholdy **znova nakalibrovať** na týchto dokumentoch (`sweep_eval.py`, prepísať na nové testy).

## 3. Kroky agenta

Najprv sa zistí, **čo** a **podľa akej definície** sa má počítať, až potom sa počíta.

1. **Vytiahnutie položiek z výkazu (LLM):** JSON s jednotlivými položkami (tržby, prevádzkový zisk,
   odpisy, jednorazové náklady, dlh, hotovosť…) a stranou, kde boli nájdené.
   **Nie hotová EBITDA firmy**, pretože zmluvná definícia môže byť iná.
2. **Kontrola položiek (Python):** schéma, súčty, chýbajúce polia.
3. **Vyhľadanie v zmluve (RAG):** definícia EBITDA a čistého dlhu, limit platný pre dané obdobie,
   výnimky (waivers), poznámky analytika.
4. **Zmluvná špecifikácia (LLM → JSON):** z nájdeného textu štruktúrovaný predpis, napríklad
   `{"ratio": "net_debt/ebitda", "ebitda_adds_back": ["one_off_restructuring"], "limit": 4.5,
   "valid_from": "2026-01-01", "valid_to": "2026-12-31", "waiver": null, "citations": [{"article": "7.2", "page": 4}]}`.
   Hodnoty sa vyberajú iba z pevného zoznamu povolených položiek.
5. **Overenie špecifikácie (Python):**
   - `covenants.validate_spec`: položky iba z povoleného zoznamu a bez duplicít, limit je konečné
     kladné číslo, žiadne dva ukazovatele s rovnakým id, každá výnimka má citáciu a platné obdobie;
   - `sources.verify_sources`: citovaný dokument existuje, citovaný článok leží na citovanej strane,
     definícia EBITDA aj dlhu zodpovedá podporovanému textovému vzoru (`contract_rules.py`),
     limit patrí konkrétnemu ukazovateľu a testovanému obdobiu vrátane dodaného účinného dodatku.
     Špecifikácia musí obsahovať všetky zmluvné ukazovatele práve raz. Výnimka cituje dokument, ktorý ju výslovne udeľuje
     („prominuje“) pre daný Deň testování; poznámky analytika nie sú dôkaz výnimky ani limitu.
   Čokoľvek neoverené → `human_review`. Vymyslená výnimka tak nemôže zmeniť `breach` na `no_breach`.
   Textové kontroly sú šité na formát vygenerovaných dokumentov; skutočné dokumenty by potrebovali
   robustnejšie overenie (napr. štruktúrovaný register výnimiek).
   Volanie `verify_sources(spec, documents, period)` potrebuje testované obdobie.
   Validátor dostáva úplné zdrojové dokumenty jednej firmy, nie iba úryvky vybrané LLM;
   zoznam dokumentov musí zostaviť aplikácia z dôveryhodného úložiska. Vynechaný dodatok
   nemožno odhaliť iba z jeho neprítomnosti v tomto zozname. Neznáme definície, klauzuly,
   chýbajúce obdobie alebo viac dodatkov bez podporovaných pravidiel priority vedú na `human_review`.
6. **Výpočet a stav (Python, `covenants.py`):** podľa špecifikácie poskladať EBITDA, vypočítať pomer,
   porovnať s limitom, uplatniť výnimku → `breach` / `no_breach`.
7. **Pravidlá pre `human_review` (Python):** chýba položka alebo nie je konečné nezáporné číslo
   (záporný môže byť iba EBIT), špecifikácia alebo zdroje neprešli overením,
   nečitateľný dokument, výsledok v pásme blízko limitu, rozpor medzi článkami.
8. **Vysvetlenie (LLM):** zrozumiteľné zdôvodnenie s citáciami. Stav nemení; kód overí,
   že vysvetlenie uvádza rovnaký stav a iba citácie zo špecifikácie.
9. **Akcia:** úloha pre analytika. V labe simulovaná zápisom do tabuľky; agent nemá iné nástroje
   ani oprávnenia (least privilege).

## 4. Testy

| # | Test | Metrika |
| --- | --- | --- |
| T1 | vyťahovanie položiek z výkazu | podiel presne správnych polí, pre každý LLM |
| T2 | retrieval | správny článok v top-k, pre každý embedding profil |
| T3 | zmluvná špecifikácia a výsledný stav v 3 režimoch | správnosť špecifikácie (definícia, limit, výnimka), správnosť citácie, výsledný stav, podiel `human_review` |
| T4 | prompt injection | zmenila sa špecifikácia alebo stav, prípadne nastala nežiadaná akcia? |
| T5 | opakovanie 3× | konzistentnosť odpovedí (nedeterminizmus) |
| T6 | prevádzka | tokeny, cena a latencia na jeden beh |

Režimy pre T3 (mapa na existujúci runner):

| Režim | Čo agent dostane | `rag_test.py --modes` |
| --- | --- | --- |
| bez RAG | výkaz a všeobecné pravidlo | `no_history` |
| RAG | výkaz a nájdené články, výnimky, poznámky | `rag` |
| celá zmluva | výkaz a všetky dokumenty klienta | `curated` |

Keďže stav počíta kód, každú chybu stavu sa dá priradiť konkrétnemu kroku:
zlá položka (T1), nenájdený článok (T2) alebo zlá špecifikácia (T3). `covenants.py` má vlastné
unit testy so známymi vstupmi a výsledkami.

**Prehliadnuté porušenie** (agent povie `no_breach`, správne je `breach`) vykazovať zvlášť.
Pre banku je to najhoršia chyba, horšia než falošný poplach.

Modely: 1–2 z Foundry a 1–2 lokálne, aby matica ostala zvládnuteľná.

## 5. Prevádzka a platforma

- OpenTelemetry trace pre každý krok agenta; voliteľne export do Application Insights a KQL dotaz.
- Konfigurácia agenta vo verzovanom YAML: verzia promptu, model, threshold, prah istoty.
- GitHub Actions: `python -m unittest` a malá regresná evaluácia pri každej zmene.

## 6. Prezentácia výsledkov

- jedna tabuľka výsledkov (3 režimy × modely);
- 2–3 rozobrané zlyhania: čo sa stalo, prečo a čo sa zmenilo;
- krátke živé demo jedného behu s traceom.

## Poradie práce

1 (dáta) → 3 (agent) → T3 (jadro príbehu) → T1, T2, T4–T6 → 5 (prevádzka) → 6.

## Čo je prevzaté z `../code`

Použiteľné bez zmeny obsahu (spoločný motor): `config.py`, `providers.py`, `llm_metrics.py`,
`rag_test.py`, `test_rag_benchmark.py`, `check_cloud.py`, `llm_prices.json`, `requirements.txt`,
`docker-compose.yml`.

Prevzaté **iba ako kostra, stále incidentové a treba ich prepísať** (pozri TODO):

- `search.py`: stále stĺpce a filtre incidentov (`incident_id`, `sid`, `domain`, `db_type`);
- `rag_prompt.py`: stále prompt „SAP operations investigation assistant“;
- `sweep_eval.py`: stále načítava testy z `eval.py`, ktorý tu neexistuje.

`requirements.txt` pochádza zo spoločného motora: `openai` sa používa pre Azure OpenAI a Foundry,
`ollama` pre lokálne modely; `anthropic` a `google-genai` slúžia profilom Claude a Gemini
z incidentového labu, ktoré tento lab zatiaľ nepoužíva.

Zmeny oproti originálu:

- tabuľky `covenant_docs_<profil>`, nie `incident_memory_<profil>`, aby sa nedotkli incidentového labu;
- vlastná DB: kontajner `pgvector-banka` na porte **5433**, `PG_DSN` zodpovedá heslu z `docker-compose.yml`;
- `load_threshold` presunutý z `rag.py` do `thresholds.py` (incidentové demo `rag.py` sa nekopíruje);
- testy si vytvárajú vlastný dočasný súbor s thresholdmi.

Zámerne **neprevzaté**: incidenty, scenáre, testovacie otázky, thresholdy a výsledky.

## TODO

- [x] `data/`: firmy, zmluvy, výkazy, výnimky, poznámky a `expected.json` (`generate_data.py`)
- [ ] `load_documents.py`: chunking po článkoch s metadátami
- [ ] `search.py`: stĺpce a filtre pre dokumenty (firma, typ dokumentu, obdobie) namiesto domain/db_type
- [x] schéma zmluvnej špecifikácie a zoznam povolených položiek; validátor špecifikácie (`covenants.py`)
- [x] `covenants.py` + testy: výpočet podľa špecifikácie, porovnanie s limitom, výnimky, pravidlá pre `human_review`
- [x] `sources.py` + testy: overenie citácií, limitov a výnimok voči dokumentom (`evaluate_with_sources`)
- [ ] `rag_prompt.py`: prompty pre vyťahovanie položiek, zmluvnú špecifikáciu a vysvetlenie; štruktúrovaný JSON výstup
- [x] scenáre pre runner (`data/scenarios.json`: `incident` → text výkazu, `curated_context` → všetky dokumenty klienta)
- [ ] automatické hodnotenie T1–T4 voči `expected.json` (runner zatiaľ hodnotí iba ručne)
- [ ] kalibrácia thresholdov
- [ ] OpenTelemetry, YAML konfigurácia agenta, GitHub Actions
- [ ] Foundry: deploymenty modelov, ceny v `llm_prices.json`

## Spustenie (zatiaľ iba dáta, výpočet a offline testy)

```bash
cd ~/devops-lab/ai-labs/code_banka
docker compose up -d          # vlastná DB na porte 5433
python generate_data.py       # na VM, nie vo OneDrive na Windows
python -m unittest discover -v -p "test_*.py"
```

Vyhľadávanie nad zmluvami a kroky s LLM sa zatiaľ spustiť nedajú: chýba `load_documents.py`
a `search.py` s `rag_prompt.py` sú ešte incidentové.

API kľúče a prípadné prepísania nastavení (napr. `PG_DSN`, `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_LLM_DEPLOYMENT`) patria do súboru `.env` v tomto priečinku.
`config.py` ho načíta cez python-dotenv; `.env` je v `.gitignore` a necommituje sa.
