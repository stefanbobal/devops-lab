# code_banka: agent na sledovanie úverových podmienok (covenant monitoring)

Domáci lab. **Všetky firmy, zmluvy, výkazy a čísla sú vymyslené.**
Žiadne skutočné klientske dáta ani firemný kód.

**Stav (2026-11-09):** agent, testy T1 až T6, tri režimy práce so zmluvou, útoky, opakovanie, vyhodnotenie
zamknutej testovacej sady aj beh na Azure modeli sú hotové. Podrobný stav, čísla a zistenia sú v
`STAV_LABU_A_DALSIE_KROKY.md`, prehľad v `LAB_FINAL_DOCUMENT.md`, plán presunu do Azure AI Foundry v `FOUNDRY_PORT.md`.
Texty nižšie opisujú pôvodné zadanie a návrh; kde sa realita líši, je to poznačené.

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

Dáta sú rozdelené na dve sady:

- **dev** (`data/`, 12 firiem, 36 prípadov): na nej sa ladí chunkovanie, dotazy a prahy;
- **test** (`data_test/`, 6 firiem C13–C18, 18 prípadov): zamknutá, vyhodnocuje sa jednorazovo na konci.
  Má inú štruktúru zmlúv (zamiešané poradie článkov, 12 článkov) a iné kombinácie, no rovnaké znenie viet,
  aby ju zvládol striktný overovač (`contract_rules.py`). Tuning na nej nie je dovolený.

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
python generate_data.py            # dev sada: prepíše data/ (seed 20261101)
python generate_data.py --set test # zamknutá testovacia sada: prepíše data_test/ (seed 20261201)
```

- `data/companies/<Cxx>/`: `smlouva.md`, voliteľne `dodatek_1.md` a `waiver_<obdobie>.md`,
  `poznamky_analytika.md`, `vykaz_2026Q1–Q3.md` (strany označené `[strana N]`);
- `data/expected.json`: správne položky so stranami, zmluvná špecifikácia s citáciami, výsledok,
  stav podľa všeobecného pravidla a príznak `fails_without_contract`;
- `data/scenarios.json`: formát pre `rag_test.py` (`incident` = výkaz, `curated_context` = všetky dokumenty klienta);
- `data/generic_rule.md`: všeobecné pravidlo pre režim bez zmluvy;
- `data/SUMMARY.md`: prehľad 36 prípadov (12 firiem × 3 štvrťroky); `data_test/` má vlastné rovnaké súbory.

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

## 2. Načítanie do vektorovej DB (`load_documents.py`, hotové)

- Zmluvy a dodatky sa delia **po článkoch**; článok „Definice a výklad“ sa delí ešte **po číslovaných bodoch**
  (2.1 až 2.6), lebo jeden chunk s 6 definíciami zhoršoval retrieval (pozri `T2_retrieval_embeddings.md`).
  Prepínač `SPLIT_DEFINITIONS=0` vráti chunkovanie po článkoch. Waiver a poznámky sú jeden chunk na dokument.
  Výkazy sa nenačítavajú, sú vstupom agenta.
- Metadáta: firma, dokument, typ dokumentu, článok, bod (`clause`), strana. Platnosť od–do sa v DB neukladá,
  overuje ju `sources.py` z plného textu.
- Tabuľky `covenant_docs_<profil>`; vlastný kontajner `pgvector-banka` na porte 5433.
- Pevný SQL filter podľa firmy (povinný) a voliteľne typu dokumentu, až potom vektorové vyhľadávanie (`search.py`).
- **3 embedding profily:** `azure` (`text-embedding-3-small`, 1536), `gemini` (`gemini-embedding-001`, 1536,
  Vertex) a `bge` (`bge-m3`, 1024, lokálna Ollama).
- Načítanie dev aj testovacej sady do rovnakých tabuliek (firmy majú rôzne ID). Načítanie nie je vyhodnotenie.
- Thresholdy: kalibrácia iba na dev sade (`t2_retrieval.py`); `sweep_eval.py` je ešte z incidentového labu.

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

**Implementácia (`agent.py`):** kroky 1 až 7 sú hotové (v kóde sú to kroky `extract`, `check_items`, `retrieve`, `spec`,
`verify`, `evaluate`). Krok 8 (vysvetlenie LLM) a krok 9 (akcia) sa **neimplementovali**: agent vracia stav, dôvody a všetky
medzikroky, čo stačí na testovanie. Parameter `mode` volí zdroj zmluvného textu: `rag`, `full`, `generic`, `no_context`.

## 4. Testy

| # | Test | Metrika | Skript | Stav |
| --- | --- | --- | --- | --- |
| T1 | vyťahovanie položiek z výkazu | podiel správnych polí (správne / chýba / vymyslené / zlé číslo) | `t1_extraction.py` | hotové (dev aj test) |
| T2 | vyhľadávanie | správny článok v top-k, pre každý embedding profil | `t2_retrieval.py` | hotové (dev aj test) |
| T3a | zmluvná špecifikácia z nájdeného textu | správnosť špecifikácie a citácií | `t3_spec.py` | hotové (dev aj test) |
| T3 | celý reťazec, stav proti `expected.json` | správny stav, prehliadnuté porušenia, podiel `human_review` | `t3_chain.py` | hotové (dev aj test) |
| T4 | útoky v dokumentoch | zmenil sa stav, čísla alebo špecifikácia? | `t4_attacks.py` | hotové |
| T5 | opakovanie | stabilita stavu a špecifikácie | `t3_chain.py --repeats`, `t5_stability.py` | hotové |
| T6 | prevádzka | tokeny, latencia, cena | `t6_ops.py` | hotové |

Režimy práce so zmluvou (T3, `t3_chain.py --mode`):

| Režim | Čo model dostane | Poznámka |
| --- | --- | --- |
| `rag` | úryvky z vektorového vyhľadávania | normálny agent |
| `full` | všetky chunky zmluvy, dodatku a waiveru firmy, bez vyhľadávania | bez poznámok analytika |
| `generic` | žiadna zmluva; všeobecné pravidlo dluh/EBITDA ≤ 4,00 | deterministický základ, LLM len extrahuje výkaz |
| `no_context` | špecifikácia bez úryvkov | ukáže, či model odmietne alebo vymýšľa |

Keďže stav počíta kód, každú chybu stavu sa dá priradiť konkrétnemu kroku:
zlá položka (T1), nenájdený článok (T2) alebo zlá špecifikácia (T3). `covenants.py` má vlastné
unit testy so známymi vstupmi a výsledkami (celkom 169 jednotkových testov).

**Prehliadnuté porušenie** (agent povie `no_breach`, správne je `breach`) sa vykazuje zvlášť.
Pre banku je to najhoršia chyba, horšia než falošný poplach.

Modely: lokálne (qwen3.8:27b, gemma3:27b), cloudové (claude-haiku-5-5, Azure OpenAI).
Testovacia sada `data_test/` je zamknutá: skripty ju odmietnu bez `--final`.

## 5. Prevádzka a platforma

Hotové:
- Každý krok agenta sa zapisuje do výsledku (stav, čas, tokeny a latencia z údajov poskytovateľa).
- Každý výsledkový súbor má záznam `meta`: verzia a hash promptu, modely, prah, stav vektorovej tabuľky a git commit (`run_meta.py`).
- Výsledky sa nikdy neprepisujú (povinná značka `--tag`).

Zostáva (nezačaté): OpenTelemetry trace s exportom do Application Insights, konfigurácia agenta vo verzovanom YAML,
GitHub Actions s regresnou evaluáciou pri každej zmene, nasadenie do Azure AI Foundry (`FOUNDRY_PORT.md`).

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

- `rag_prompt.py`: pôvodné incidentové funkcie zostali kvôli `rag_test.py`; prompty tohto labu (extrakcia, špecifikácia, verzia P3) sú doplnené;
- `sweep_eval.py`: stále načítava testy z `eval.py`, ktorý tu neexistuje (nahrádza ho `t2_retrieval.py`);
- `rag_test.py`: predvolené `rag_scenarios.json` a `thresholds_FROZEN.json` tu neexistujú.

`search.py` je už prepísaný (filter podľa firmy a typu dokumentu). Z `../code` sú navyše skopírované `lab.sh`,
`lab_start.py`, `lab_start_README.md` a `test_lab_start.py`; kontrolujú kontajner `pgvector-banka` (port 5433).

`requirements.txt` pochádza zo spoločného motora: `openai` sa používa pre Azure OpenAI a Foundry,
`ollama` pre lokálne modely; `anthropic` a `google-genai` slúžia profilom Claude a Gemini
z incidentového labu, ktoré tento lab zatiaľ nepoužíva.

Zmeny oproti originálu:

- embedding profily zúžené na 3 (`azure`, `gemini`, `bge`);
- tabuľky `covenant_docs_<profil>`, nie `incident_memory_<profil>`, aby sa nedotkli incidentového labu;
- vlastná DB: kontajner `pgvector-banka` na porte **5433**, `PG_DSN` zodpovedá heslu z `docker-compose.yml`;
- `load_threshold` presunutý z `rag.py` do `thresholds.py` (incidentové demo `rag.py` sa nekopíruje);
- testy si vytvárajú vlastný dočasný súbor s thresholdmi.

Zámerne **neprevzaté**: incidenty, scenáre, testovacie otázky, thresholdy a výsledky.

## TODO

Hotové: dáta a generátor (dev, zamknutá test sada, útoky), chunkovanie a vektorová databáza, `search.py` s prahmi,
`covenants.py`, `sources.py`, `contract_rules.py`, prompty, `agent.py` (štyri režimy), testy T1 až T6, vyhodnotenie zamknutej
sady, záznam reprodukovateľnosti, beh na Azure modeli.

- [ ] hosted agent v Azure AI Foundry, vektorová databáza v Azure (`FOUNDRY_PORT.md`)
- [ ] OpenTelemetry, YAML konfigurácia agenta, GitHub Actions s regresnou sadou
- [ ] Docker image a rozhranie (voliteľné)
- [ ] ceny Azure modelov v `llm_prices.json` (T6 ich zatiaľ nepočíta)
- [ ] vysvetlenie výsledku (krok 8) a akcia (krok 9), ak budú potrebné
- [ ] `rag_test.py`, `sweep_eval.py` prispôsobiť alebo odstrániť (zostatky z incidentového labu)

## Spustenie

```bash
cd ~/devops-lab/ai-labs/code_banka
source .venv/bin/activate     # samostatný venv tohto labu
docker compose up -d          # vlastná DB na porte 5433
docker exec pgvector-banka psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector"   # raz
bash lab.sh                   # kontrola labu; očakávaný výsledok: Lab ready.
python generate_data.py       # na VM, nie vo OneDrive na Windows
python generate_data.py --set test
for p in bge azure gemini; do EMBED_PROFILE=$p python load_documents.py; done

LLM_PROFILE=qwen38 python agent.py C01 2026Q1                  # jeden prípad
LLM_PROFILE=haiku python t3_chain.py --tag moj_beh             # T3, všetkých 36 prípadov
LLM_PROFILE=haiku python t3_chain.py --mode generic --tag g1   # iný režim
python t2_retrieval.py --tag moj_beh                           # T2
python t6_ops.py moj_beh                                       # tokeny a cena z hotového behu
python -m unittest discover -p "test_*.py"                     # 169 jednotkových testov
```

Zamknutá testovacia sada sa spúšťa jednorazovo a len s `--set test --final` (napr. `python t3_chain.py --set test --final --tag f_x`).
Výsledky sú v `results/` (v `.gitignore`, treba ich zálohovať mimo repa). Podrobný postup a zoznam všetkých behov:
`STAV_LABU_A_DALSIE_KROKY.md`.

API kľúče a prípadné prepísania nastavení (napr. `PG_DSN`, `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_LLM_DEPLOYMENT`) patria do súboru `.env` v tomto priečinku.
`config.py` ho načíta cez python-dotenv; `.env` je v `.gitignore` a necommituje sa.
