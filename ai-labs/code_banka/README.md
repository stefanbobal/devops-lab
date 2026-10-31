# code_banka: agent na sledovanie úverových podmienok (covenant monitoring)

Domáci lab na pohovor. **Všetky firmy, zmluvy, výkazy a čísla sú vymyslené.**
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

10–12 vymyslených firiem. Pre každú:

- **úverová zmluva** (~10 článkov): definície (EBITDA, čistý dlh), podmienky s limitmi,
  limit meniaci sa v čase (step-down), povinnosť reportovať, postup pri porušení;
- **2–4 štvrťročné výkazy**: najprv Markdown tabuľky, neskôr PDF;
- voliteľne **list s výnimkou (waiver)** a **poznámky analytika**.

`data/expected.json`: pre každý testovací prípad správne vytiahnuté hodnoty, vypočítaný pomer,
zmluvná špecifikácia, výsledný stav (`breach` / `no_breach` / `human_review`) a citované články.

Typy prípadov (spolu 30–40):

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

## 2. Načítanie do vektorovej DB (`load_documents.py`)

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
5. **Overenie špecifikácie (Python):** citované články sú v nájdenom texte, položky sú z povoleného
   zoznamu, obdobie sedí na výkaz, limit je kladné číslo, žiadne dva články si neodporujú.
6. **Výpočet a stav (Python, `covenants.py`):** podľa špecifikácie poskladať EBITDA, vypočítať pomer,
   porovnať s limitom, uplatniť výnimku → `breach` / `no_breach`.
7. **Pravidlá pre `human_review` (Python):** chýba položka, špecifikácia neprešla overením,
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

## 6. Výstup na pohovor

- jedna tabuľka výsledkov (3 režimy × modely);
- 2–3 rozobrané zlyhania: čo sa stalo, prečo a čo sa zmenilo;
- krátke živé demo jedného behu s traceom.

## Poradie práce

1 (dáta) → 3 (agent) → T3 (jadro príbehu) → T1, T2, T4–T6 → 5 (prevádzka) → 6.

## Čo je prevzaté z `../code`

Motor bez dát: `config.py`, `providers.py`, `llm_metrics.py`, `rag_test.py`,
`test_rag_benchmark.py`, `search.py`, `rag_prompt.py`, `sweep_eval.py`,
`check_cloud.py`, `llm_prices.json`, `requirements.txt`, `docker-compose.yml`.

Zmeny oproti originálu:

- tabuľky `covenant_docs_<profil>`, nie `incident_memory_<profil>`, aby sa nedotkli incidentového labu;
- vlastná DB: kontajner `pgvector-banka` na porte **5433**, `PG_DSN` zodpovedá heslu z `docker-compose.yml`;
- `load_threshold` presunutý z `rag.py` do `thresholds.py` (incidentové demo `rag.py` sa nekopíruje);
- testy si vytvárajú vlastný dočasný súbor s thresholdmi.

Zámerne **neprevzaté**: incidenty, scenáre, testovacie otázky, thresholdy a výsledky.

## TODO

- [ ] `data/`: firmy, zmluvy, výkazy, výnimky, poznámky a `expected.json`
- [ ] `load_documents.py`: chunking po článkoch s metadátami
- [ ] `search.py`: stĺpce a filtre pre dokumenty (firma, typ dokumentu, obdobie) namiesto domain/db_type
- [ ] schéma zmluvnej špecifikácie a zoznam povolených položiek; validátor špecifikácie
- [ ] `covenants.py` + testy: výpočet podľa špecifikácie, porovnanie s limitom, výnimky, pravidlá pre `human_review`
- [ ] `rag_prompt.py`: prompty pre vyťahovanie položiek, zmluvnú špecifikáciu a vysvetlenie; štruktúrovaný JSON výstup
- [ ] scenáre pre runner (`incident` → text výkazu, `curated_context` → celá zmluva)
- [ ] automatické hodnotenie T1–T4 voči `expected.json` (runner zatiaľ hodnotí iba ručne)
- [ ] kalibrácia thresholdov
- [ ] OpenTelemetry, YAML konfigurácia agenta, GitHub Actions
- [ ] Foundry: deploymenty modelov, ceny v `llm_prices.json`

## Spustenie (zatiaľ iba motor)

```bash
cd ~/devops-lab/ai-labs/code_banka
docker compose up -d          # vlastná DB na porte 5433
python -m unittest -v test_rag_benchmark
```
