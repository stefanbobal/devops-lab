# code_banka: stav labu, všetky doterajšie testy a čo zostáva

Stav k 2026-11-04 (večer). Všetky firmy, zmluvy a čísla sú vymyslené (fiktívna Modrá Banka a.s.).
Účel dokumentu: aby sa dalo zajtra pokračovať (T5) bez spätného čítania konverzácie. Obsahuje setup,
dáta, embeddingy, každý test s číslami, verzie promptov, nájdené chyby, zoznam súborov a presný zoznam toho,
čo chýba na dokončenie celého testu.

Súvisiace dokumenty: `README.md` (zadanie a návrh), `T2_retrieval_embeddings.md` (podrobné meranie
vyhľadávania), `LAB_FINAL_DOCUMENT.md` (pracovný záverečný dokument), `lab_start_README.md` (denný štart).

---

## 0. Rýchly štart na zajtra

```bash
cd ~/devops-lab/ai-labs/code_banka
bash lab.sh                       # očakávaný koniec: "Lab ready."
docker ps | grep pgvector-banka   # musí bežať (port 5433)
ollama stop gemma3:27b            # len ak sa predtým používala gemma (uvoľní GPU)
```

Posledný hotový krok: `agent.py` + `t3_chain.py` (qwen38 35/36, haiku 36/36).
Prvý krok zajtra: T5 (opakovanie 3×), plán v sekcii 12. **Čaká na dve rozhodnutia** (sekcia 12.1):
`--repeats 3` a teplota (predvolená vs. 0).

Pravidlá práce z dnešného dňa (dohodnuté):
- Testy a dlhé príkazy spúšťa používateľ sám. Claude upravuje kód a vysvetľuje výsledky po jednom kroku.
- Každý skript musí vypisovať, čo práve robí (časované `log()`), aby nevyzeral zaseknutý.
- Výsledky nikdy neprepisovať: vždy nová značka `--tag`. (Pri T3a sa raz prepísal `t3_spec_run1.json`.)
- V repe (verejné) nesmú byť zmienky o pohovore ani o konkrétnej firme. Súkromné poznámky držať mimo repa.

---

## 1. Čo lab robí a ako je rozdelená práca

Agent kontroluje úverové podmienky (covenants) firmy: z výkazu a zmluvy určí `breach`, `no_breach` alebo
`human_review`. **Stav určuje overiteľný kód, nie LLM.** LLM číta (výkaz, zmluvu) a prevádza text na
obmedzenú štruktúru (JSON). Python overuje a počíta.

Kroky agenta (`agent.py`, funkcia `run`), každý krok sa zapisuje do `result["steps"]`:

| # | Krok | Kto | Modul |
| --- | --- | --- | --- |
| 1 | `extract`: položky z výkazu (tržby, EBIT, odpisy, dlh, hotovosť…) | LLM | `rag_prompt.build_extract_prompts` |
| 2 | `check_items`: povolené názvy, čísla, **číslo musí byť vytlačené na citovanej strane výkazu** | kód | `agent.check_items` |
| 3 | `retrieve`: úryvky zmluvy z vektorovej DB (firma je povinný filter) | kód + embedding | `search.py` |
| 4 | `spec`: špecifikácia (definícia EBITDA a dluhu, limity, waiver) ako JSON | LLM | `rag_prompt.build_spec_prompts` |
| 5 | `verify`: `validate_spec` + `verify_sources` (každá citácia sa overí v úplných dokumentoch) | kód | `covenants.py`, `sources.py` |
| 6 | `evaluate`: pomery, porovnanie s limitom, waiver, pásmo blízkosti limitu 2 % | kód | `covenants.evaluate` |

Akékoľvek zlyhanie kroku 1 až 5 končí ako `human_review` s dôvodom (`extraction_failed`, `unverified_items`,
`retrieval_failed`, `no_relevant_contract_text`, `spec_failed`, `spec_refused`, `unverified_spec`).
Agent pri chybe modelu nikdy nespadne.

Povolené hodnoty (z `covenants.py`): položky `revenue, ebit, depreciation, restructuring, asset_sale_gain,
interest_expense, bank_loans, bonds, cash, reported_ebitda` (posledná je informatívna, nikdy sa nepoužije);
EBITDA = EBIT + odpisy (zabudovaný základ) + voliteľne `restructuring`/`asset_sale_gain` v `add`/`subtract`;
dluh = `bank_loans` a/alebo `bonds`, voliteľne mínus `cash`; pomery `debt_to_ebitda` (max) a `interest_cover`
(min); pásmo „blízko limitu“ = 2 % → `human_review`.

---

## 2. Setup prostredia

### 2.1 Stroje a služby
- **VM `k8s-lab`** (Ubuntu), tu sa spúšťajú všetky príkazy. Adresár: `~/devops-lab/ai-labs/code_banka`.
- **Ollama na Windows hoste** (GPU). Adresa podľa `lab_start_README.md`: `OLLAMA_HOST=http://192.168.178.25:11434`
  (nastavená vo VM prostredí alebo `.env`). Python klient `ollama` sa pripája rovnako ako `providers.py`.
- **Docker kontajner `pgvector-banka`**: obraz `pgvector/pgvector:pg16`, port **5433** (incidentový lab má vlastný
  `pgvector` na 5432), heslo `lab` (len lokálne), volume `pgdata_banka`. Súbor `docker-compose.yml`.
  DSN: `host=localhost port=5433 user=postgres password=lab dbname=postgres` (`PG_DSN`).
- **Cloud**: Azure OpenAI (embedding + LLM), Vertex AI (Gemini embedding), Anthropic (haiku). Kľúče v `.env`
  (neverzované, je v `.gitignore`): `ANTHROPIC_API_KEY`, `GCP_PROJECT`, `AZURE_OPENAI_ENDPOINT`,
  `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_EMBED_DEPLOYMENT`, `AZURE_OPENAI_LLM_DEPLOYMENT`.

### 2.2 Python
- Virtuálne prostredie `.venv` v `code_banka` (Python 3.14), balíky v `requirements.txt` (pripnuté verzie:
  `anthropic 2.3.0`, `openai 3.40.0`, `ollama 0.6.3`, `google-genai 2.33.0`, `psycopg 3.3.6`,
  `pgvector 0.5.1`, `numpy 2.5.4`, `python-dotenv`, …).
- Aktivácia: `source .venv/bin/activate` (alebo cez `bash lab.sh <skript>`).

### 2.3 Denná kontrola `lab.sh` / `lab_start.py`
`bash lab.sh` aktivuje `.venv`, načíta `.env`, skontroluje Docker (kontajner `pgvector-banka`), spojenie na DB,
rozšírenie `vector` a čítaciu vektorovú operáciu, a vypíše modely z Ollamy. Nič nespúšťa ani nemení.
Koniec: `Lab ready.` Prepínač `--cloud` robí platené sondy (2 embedding + 6 LLM volaní) cez `check_cloud.py`.
`lab.sh <skript.py> ...` pustí skript až po úspešnej kontrole.

### 2.4 Profily modelov (`config.py`)
Embedding (`EMBED_PROFILE`, predvolené `bge`):

| Profil | Model | Poskytovateľ | Dim. | Tabuľka v DB |
| --- | --- | --- | --- | --- |
| `azure` | text-embedding-3-small | Azure OpenAI | 1536 | `covenant_docs_azure` |
| `gemini` | gemini-embedding-001 | Vertex AI (`us-central1`) | 1536 | `covenant_docs_gemini` |
| `bge` | bge-m3 | lokálna Ollama | 1024 | `covenant_docs_bge` |

LLM (`LLM_PROFILE`, predvolené `gemma`): `gemma` (gemma3:27b, Ollama), `qwen36`/`qwen38` (qwen3.6:27b /
qwen3.8:27b, Ollama), `llama` (llama3.1:8b), `azure` (nasadenie z `AZURE_OPENAI_LLM_DEPLOYMENT`),
`claude` (claude-sonnet-5-5), `haiku` (claude-haiku-5-5), `opus` (claude-opus-5-5), `gemini`
(gemini-3.1-flash-lite), `gemini_argon`.
`config.py` číta profily pri importe, preto skripty spúšťajú jeden podproces na profil.
`providers.chat(system, user)` volá model s **predvolenými parametrami** (teplota sa nenastavuje; Anthropic má
`max_tokens=2000`). `providers.embed(text, kind)` pre Gemini používa `RETRIEVAL_DOCUMENT`/`RETRIEVAL_QUERY`,
pre azure a bge bez typu úlohy a bez prefixu.

---

## 3. Dáta

Generuje `generate_data.py` (deterministicky zo seedu, testy `test_generate_data.py`).

| Sada | Priečinok | Seed | Firmy | Prípady | Stavy |
| --- | --- | --- | --- | --- | --- |
| **dev** (ladenie) | `data/` | 20261101 | C01 až C12 | 36 (12 firiem × 3 štvrťroky 2026Q1 až Q3) | no_breach 21, breach 12, human_review 3 |
| **test** (zamknutá) | `data_test/` | 20261201 | C13 až C18 | 18 (6 firiem × 3) | no_breach 9, breach 7, human_review 2 |

Obsah: `companies/<Cxx>/` obsahuje `smlouva.md`, voliteľne `dodatek_1.md`, `waiver_<obdobie>.md`,
`poznamky_analytika.md` a `vykaz_<obdobie>.md`. `expected.json` má pre každý prípad `expected_items`,
`expected_spec` (vrátane citácií), `expected_result` (hodnoty, stav), `expected_status`, `case_type`,
`generic_rule_status` (stav pri všeobecnom pravidle dluh/EBITDA ≤ 4,00 bez zmluvy), `fails_without_contract`,
`injection`. Dokumenty majú značky `[strana N]` (simulácia strán PDF) a články `## Článek N – ...`.
`SUMMARY.md` v každej sade je prehľad prípadov.

Typy prípadov dev: simple 9, custom_definition 6, step_down 3, two_covenants 3, gross_debt 3, amendment 3,
prompt_injection 2 (C11-2026Q2 `override`, C12-2026Q3 `exfiltration`), waiver 1 (C05-2026Q2),
waiver_other_period 1 (C05-2026Q3), waiver_requested_not_granted 1 (C06-2026Q2), missing_item 1 (C09-2026Q2),
near_limit 1 (C09-2026Q3), exact_limit 1 (C11-2026Q3), misleading_management_claim 1 (C12-2026Q2).
Test: custom_definition 3, step_down 3, two_covenants 3, amendment 3, simple 1, waiver_other_period 1, waiver 1,
missing_item 1, near_limit 1, prompt_injection 1 (C18-2026Q3 `override`).
Bez zmluvy (všeobecné pravidlo) by sa pokazilo 12 z 36 dev a 8 z 18 test prípadov.

Poznámka k C05: `waiver_2026Q2.md` existuje pre firmu C05 vo všetkých troch štvrťrokoch, ale platí len pre
Den testování 30. 6. 2026. Očakávaná špecifikácia pre Q1 a Q3 ho obsahuje s obdobím 2026Q2 (nemení stav).
Pri C10 mení dodatok limit až od 30. 6. 2026 (3,00 → 3,75), takže Q1 má limit 3,00 (`smlouva.md`), Q2 a Q3 3,75.

---

## 4. Načítanie dokumentov a chunkovanie (`load_documents.py`)

Príkaz (jedna tabuľka na profil):
```bash
for p in bge azure gemini; do EMBED_PROFILE=$p python load_documents.py; done
```
Skript tabuľku zahodí a vytvorí znova (`DROP TABLE`), načíta **dev aj test** (načítanie nie je vyhodnotenie).
Výkazy sa nenačítavajú (sú vstupom agenta, nie znalosťou). Stĺpce: `company_id, company, document, doc_type,
article, article_title, clause, page, text, embedding_text, embedding_model, embedding`; index
`(company_id, doc_type)`.

Typy dokumentov (`doc_type`): `contract` (smlouva*), `amendment` (dodatek*), `waiver` (waiver*), `notes` (poznamky*).

Pravidlá chunkovania:
- Zmluva a dodatok: **jeden chunk na článok** (`## Článek N – ...`).
- Výnimka (H1, `SPLIT_DEFINITIONS=1`, predvolené): článok „Definice a výklad“ sa delí **po číslovaných
  bodoch** (`2.1 …`, `2.2 …`, každý bod jeden chunk s poľom `clause`). Delí sa len ak je článok celý z číslovaných
  bodov. `SPLIT_DEFINITIONS=0` vráti delenie po článkoch.
- Waiver a poznámky: jeden chunk na dokument (nemajú články).
- Embedovaný text = hlavička + text: `Firma: <názov>\nDokument: <súbor> (<typ>), <kde>\n<text>`.
- Aktuálny obsah **každej** z troch tabuliek: 308 chunkov pre 18 firiem (dev + test): 284 contract, 4 amendment,
  2 waiver, 18 notes. (Staré číslo „135 chunkov“ v `T2_retrieval_embeddings.md` sekcia 2 je z doby pred delením
  a pred načítaním test sady.)

---

## 5. Vyhľadávanie a prahy (`search.py`, `thresholds.json`)

- `search_vector(...)`: SQL `WHERE company_id = %s` je **povinný** (bez neho `ValueError`), voliteľne
  `doc_type = ANY(...)`, zoradenie `ORDER BY embedding <=> dotaz`, podobnosť `1 - (embedding <=> dotaz)`.
- `find_similar`: embedding dotazu + `search_vector` (top-3).
- `find_relevant`: ako `find_similar`, ale **zahodí výsledky pod prahom** daného profilu
  (`load_threshold(PROFILE, thresholds.json)`, žiadny tichý predvolený prah). Typy dokumentov: `contract`,
  `amendment`, `waiver` (poznámky analytika sa nepoužívajú ako dôkaz).
- `has_doc_type(company_id, "waiver")`: **deterministická** kontrola z metadát.
- `find_waiver`: ak firma nemá dokument typu `waiver`, vráti `[]` bez vyhľadávania, inak hľadá len medzi waivermi.
- Prázdny výsledok = „nič nenájdené“ → agent ide na `human_review`.

Zapísané prahy (`thresholds.json`, kalibrované **len na dev**, pravidlo: najvyšší prah s recall ≥ 0,95, potom
ručne upravené pre gemini):

| Profil | Prah | Poznámka |
| --- | --- | --- |
| azure | 0,50 | recall 0,98, precision 0,60 |
| bge | 0,50 | recall 1,00, precision 0,56 |
| gemini | **0,65** | recall 1,00, precision 0,49. Pôvodne 0,70 (recall 0,97, precision 0,88) → 4 chýbajúce limity v T3a, pozri sekciu 8 |

`SIMILARITY_THRESHOLD` v `config.py` sa už nepoužíva (zostatok z incidentového labu).

---

## 6. T2: vyhľadávanie (`t2_retrieval.py`)

**Čo sa meria:** nájde vyhľadávanie správny článok? Pre každý z 36 dev prípadov 3 až 4 fixné dotazy (top-3
chunky tej istej firmy): `ebitda` („Jak je ve smlouvě definována EBITDA?“), `debt` („Jak je ve smlouvě
definován Čistý dluh?“), `limit` („Jaká je nejvyšší přípustná hodnota finančních ukazatelů pro Den testování
<d. m. rrrr>?“), `waiver` („Prominutí porušení finančního ukazatele pro Den testování <d. m. rrrr>“; pri firmách
bez waiveru je to **negatívny dotaz** `no_waiver`). Správny chunk = dokument + článok z `expected_spec` citácie.
Metriky: hit@1, hit@3, strict hit (chunk obsahuje samotnú definíciu `„EBITDA“` / `„Čistý dluh“`), recall /
precision / false-accept pre mriežku prahov 0,30 až 0,85 po 0,05.

Príkazy: `python t2_retrieval.py [profil…] [--tag meno] [--write-thresholds]`;
test sada: `python t2_retrieval.py --set test --final` (jednorazovo; `--write-thresholds` na test sade je zakázané).
Výsledky: `results/t2*.json` (priečinok `results/` je v `.gitignore`).

### Meranie 1 (základ, chunk = celý článok), hit@1

| Profil | EBITDA | Dluh | Limit | Waiver | hit@3 |
| --- | --- | --- | --- | --- | --- |
| gemini | 36/36 | 36/36 | 33/36 | 3/3 | 100 % |
| bge | 0/36 | 30/36 | 32/36 | 3/3 | 100 % |
| azure | 0/36 | 3/36 | 35/36 | 3/3 | 100 % |

Príčina: článok 2 má 6 až 7 definícií naraz → „zmiešaný“ vektor; na prvom mieste bol článok 5/6 (ukazatele).

### Meranie 2 (H1: definície po bodoch), hit@1

| Profil | EBITDA | Dluh | Limit | Waiver | hit@3 |
| --- | --- | --- | --- | --- | --- |
| gemini | 36/36 | 36/36 | 33/36 | 3/3 | 100 % |
| bge | **36/36** | **36/36** | 32/36 | 3/3 | 100 % |
| azure | **36/36** | **36/36** | 35/36 | 3/3 | 100 % |

Strict metrika 36/36 (hit@1 aj hit@3) pre všetky tri. Zmena chunkovania zlepšila viac než akýkoľvek prah.
Zostávajúce „chyby“ pri limite: C10 (dodatok a zmluva sa striedajú na 1. mieste), C05 pri bge (waiver na 1.
mieste pri Q1 a Q3). Správny chunk je vždy v top-3; rozhoduje validátor, nie retrieval.
Minimálny odstup správneho od najlepšieho nesprávneho (definície): kladný všade; pri limite záporný
(gemini −0,007, bge −0,040, azure −0,033).

### Sweep prahov (dev, po meraní 2)
- gemini: 0,65 → recall 1,00 / precision 0,49; 0,70 → 0,97 / 0,88; 0,75 → 0,65 / 1,00.
- bge: 0,50 → 1,00 / 0,56; 0,55 → 0,81 / 0,57; 0,60 → 0,68 / 0,91; 0,65 → 0,59 / 1,00.
- azure: 0,45 → 1,00 / 0,48; 0,50 → 0,98 / 0,60; 0,55 → 0,77 / 0,73; 0,60 → 0,65 / 1,00.

### Negatívny test (waiver u firmy bez waiveru, n = 33)
Najlepší výsledok je vždy článok o **pravidlách** waiverov (nie waiver): gemini a bge čl. 8 „Prominutí a změny“,
azure čl. 7 „Případy porušení“. Najvyššia podobnosť: gemini 0,72 až 0,74 (priemer 0,73), bge 0,60 až 0,64
(0,62), azure 0,54 až 0,61 (0,58). Skutočný waiver: gemini ≈ 0,76, bge 0,66 až 0,68, azure ≈ 0,64. Rozdiel je
0,02 až 0,04. **False-accept pri vybraných prahoch je 1,00** (prah negatívny dotaz nezachytí); zachytenie by
vyžadovalo prah 0,65 (bge, recall 0,59) alebo 0,75 (gemini, recall 0,65). Záver: prah meria tematickú blízkosť,
nie existenciu dokumentu → existencia waiveru sa rieši typom dokumentu (`find_waiver`) a validátorom.

### Čo T2 nemeria
Dotazy na definície sú rovnaké vo všetkých 3 štvrťrokoch (efektívna vzorka ≈ 12). Zmluvy sú z jednej šablóny.
Dotazy aj chunkovanie sme ladili na tej istej dev sade. Nebolo overené H2 (typy úloh Gemini), H3 (veľkosť
modelu), H4 (formulácia dotazu), H5 (hlavička chunku); nie sú potrebné, kým test sada nevyjde výrazne horšie.

---

## 7. Prompty (`rag_prompt.py`) a ich verzie

Staré incidentové funkcie (`SYSTEM_PROMPT`, `format_context`, `build_prompts`) zostali kvôli `rag_test.py`.
Nové: `build_extract_prompts(statement_text)` a `build_spec_prompts(period, test_date, chunks)`.
`format_chunks` zobrazuje metadáta na citovanie: `[Excerpt N] document | type | article | clause | page`.

Dôležité pravidlá promptu špecifikácie: použiť len úryvky; nič nepočítať; článok je len číslo („2“, nie „2.5“);
waiver len ak ho dokument výslovne udeľuje („prominuje“) pre presný Den testování; poznámky analytika ignorovať;
pri chýbajúcej alebo nejasnej hodnote vrátiť `{"error": ...}`; EBITDA vždy začína EBIT + odpisy, **nikdy
neuvádzať odpisy** v `add`/`subtract`; neuvádzať položku, ktorú definícia výslovne nepripočítava
(„nepřipočítávají“); unikátne `id` podmienky; pomery počíta kód a **definícia nákladových úrokov sa nevyžaduje**.

| Verzia | Zmena | Kde sa použila |
| --- | --- | --- |
| P0 | prvá verzia, chunk ukazoval `article: 2/2.5` → model citoval „2/2.5“ | len skúšobný beh (citácia neprešla) |
| P1 | článok a bod zvlášť (`article: 2 \| clause: 2.5`) | T3a `run1` pôvodný (gemma, azure, haiku) |
| P2 | + základ EBITDA (EBIT + odpisy, odpisy nikdy v `add`), pravidlo o záporných formuláciách, unikátne `id` | T3a: qwen38 `run1`, `run2` (gemma, azure, haiku), `retr_*` |
| P3 | + „pomery počíta kód, definícia nákladových úrokov netreba“ | T3a `haiku_fix`, T3 `t3_chain_*`, `agent.py` |

Prompty zatiaľ **nemajú v kóde ani vo výsledkoch zapísanú verziu** (pozri sekciu 14, bod G).

---

## 8. T3a: špecifikácia z nájdeného textu (`t3_spec.py`, dev)

**Čo sa meria:** vyhľadávanie (`EMBED_PROFILE`, predvolené bge) dá LLM úryvky, LLM vráti JSON, kód ho overí
(`validate_spec`, `verify_sources`) a porovná s `expected_spec`. Meria sa len krok 4 + 5; nepočíta sa stav, výkaz
sa nepoužíva. Všetky modely majú rovnaký prompt a rovnaké úryvky; mení sa len model.
Stavy prípadu: `correct`, `verified` (prešlo overením, ale líši sa od očakávanej), `unverified`
(overenie zlyhalo), `invalid_spec`, `bad_json`, `refused`, `llm_error`, `retrieval_error`.

Porovnanie s očakávanou špecifikáciou (po opravách): EBITDA `add`/`subtract`, dluh `include` + `deduct_cash`,
podmienky ako (pomer, limit) **bez id** (id je voľná štítka modelu), waivery len pre testované obdobie a
identifikované pomerom podmienky. Citácie kontroluje `verify_sources`.

Príkaz: `[EMBED_PROFILE=bge] python t3_spec.py <llm_profil…> [--limit N] [--cases a,b] --tag meno`.
Dve fázy (najprv vyhľadávanie pre všetky prípady, potom LLM) kvôli Ollame: striedanie bge-m3 a gemma3:27b pre
každý prípad spôsobilo pád (`llama-server … CUDA error`, kód 0xc0000409).

| Beh (tag) | Model | Retrieval (prah) | Prompt | Správnych / 36 | Poznámka |
| --- | --- | --- | --- | --- | --- |
| run1 (pôvodný) | gemma / azure / haiku | bge | P1 | 12 / 23 / 31 | súbor sa neskôr **prepísal** (zostalo len v konverzácii); chyby hlavne `refused` a `invalid_spec` kvôli odpisom |
| run1 (prepísaný) | qwen38 | bge | P2 | 36 | `results/t3_spec_run1.json` obsahuje len qwen38 |
| run2 | gemma | bge | P2 | 24 (12 `unverified`) | `ebitda.add` obsahuje `restructuring`, kde zmluva hovorí „nepřipočítávají“; C05 Q1 a Q3: waiver z Q2 pripísaný k iným obdobiam (overovač to **zastavil**) |
| run2 | azure | bge | P2 | 36 (vo výpise 35) | 1× „verified“ len pre iné `id` (interest_cover vs. icr), po oprave porovnania 36 |
| run2 | haiku | bge | P2 | 35 + 1 `refused` | C07-2026Q2: chýba definícia nákladových úrokov |
| retr_gemini | qwen38 | gemini (0,70) | P2 | 32 | 4× `refused` (C01, C06, C08, C11, vždy Q2): chunk s limitom mal skóre 0,695 až 0,700 < 0,70 → model dostal 2 chunky |
| retr_azure | qwen38 | azure (0,50) | P2 | 36 | |
| retr_gemini2 | qwen38 | gemini (**0,65**) | P2 | 36 | 4 až 5 chunkov na prípad |
| haiku_fix | haiku | bge | P3 | 36 | veta o pomeroch odstránila posledné odmietnutie |

Zistenia:
1. Väčšina chýb na začiatku bola v prompte a v meraní, nie v modeloch.
2. Gemma (lokálna) zostala na 24/36 (nerozumie záporu „nepřipočítávají“); qwen38 (lokálny), azure a haiku 36/36.
3. Voľba embedding modelu (bge, azure, gemini) nerozhodla, ak je prah bezpečne nízko; rozhodol prah.
4. Overovač zachytil nebezpečnú chybu (waiver pripísaný nesprávnemu obdobiu).
5. Chyba môjho porovnania (trvalo na rovnakom `id`, započítavalo waivery iných období) opravená.
6. Definícia nákladových úrokov v špecifikácii nie je potrebná (kód počíta EBITDA / `interest_expense` z výkazu);
   pôvodné tvrdenie o „diere v retrievale“ bolo mylné, riešením bola veta v prompte (P3).

Obmedzenia: qwen38 a azure neboli spustené s P3; gemma nikdy s P3; porovnanie je na dev sade, ktorú sme ladili.

---

## 9. T3: celý reťazec (`t3_chain.py`, dev)

**Čo sa meria:** celý `agent.run` pre všetkých 36 prípadov proti `expected_status`. Fáza 1: vyhľadávanie pre
všetky prípady (načítaný len bge); fáza 2: agent (načítaný len LLM; vyhľadávanie sa preberá z cache).
Povinný `--tag`, existujúci výsledok sa neprepíše. Výstup `results/t3_chain_<tag>.json` (`summary` + riadky s
krokmi; `spec` a `items` sa ukladajú až od úpravy po behu qwen, takže `t3_chain_qwen_run1.json` ich **nemá**,
`t3_chain_haiku_run1.json` áno).

Príkaz: `LLM_PROFILE=<profil> python t3_chain.py --tag meno [--limit N] [--cases a,b]`.

| Beh | LLM | Retrieval | Prompt | Presný stav | Prehliadnuté porušenia | Falošné poplachy | human_review (očak. 3) | Čas |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen_run1 | qwen3.8:27b | bge | P3 | **35/36** | 0 | 0 | 4 | 418 s (~12 s/prípad) |
| haiku_run1 | claude-haiku-5-5 | bge | P3 | **36/36** | 0 | 0 | 3 | 151 s (~4 s/prípad) |

Matica qwen: breach→breach 12, no_breach→no_breach 20, human_review→human_review 3, no_breach→human_review 1.
Matica haiku: 12 / 21 / 3, bez chýb.

Jediný rozdiel: **C10-2026Q1** (dodatok mení limit až od 30. 6. 2026; správny limit pre Q1 je 3,00). Qwen v tomto
behu použil zlý limit, `verify` ho zastavil („limit or citation does not match the effective rule for
2026Q1“) → `human_review` (bezpečný koniec). V T3a bol ten istý prípad s qwen38 správne → **model nie je stabilný**,
presne to má zmerať T5. Útoky v texte výkazu (C11-2026Q2 `override`, C12-2026Q3 `exfiltration`) prešli oba behy
so správnym stavom. Prípady `human_review` (C09 Q2 chýba odpis, C09 Q3 a C11 Q3 blízko limitu) sedia.

`agent.py` samostatne: `LLM_PROFILE=qwen38 python agent.py C01 2026Q1` → `no_breach`, pomer 3,10 vs. limit
3,75, EBITDA 145 680, dluh 451 608 (zhoda s `expected.json`), ~30 s vrátane načítania modelu.

---

## 10. Testy kódu (jednotkové)

`python -m unittest discover -p "test_*.py"` → posledný beh **97 testov OK** (po `t3_chain` 100). Dôležité:
`test_agent.py` (8 testov, atrapa LLM): perfektný model dá očakávaný stav pre všetkých 36 prípadov; vymyslené
číslo, chýbajúca položka, odmietnutá špecifikácia, zlý JSON, nulový počet úryvkov a waiver pripísaný
nesprávnemu štvrťroku → `human_review`. Ďalej `test_search.py`, `test_rag_prompt.py`, `test_t2_retrieval.py`,
`test_t3_spec.py`, `test_t3_chain.py`, `test_covenants.py`, `test_sources.py`, `test_load_documents.py`,
`test_lab_start.py`, `test_generate_data.py`, `test_rag_benchmark.py`.

---

## 11. Súbory v `code_banka` (čo je čo)

| Súbor | Účel |
| --- | --- |
| `agent.py` | celý agent (`run`), `retrieve`, `check_items`, `load_documents`, `parse_json`, `log` |
| `search.py` | vyhľadávanie, prahy, `find_waiver`, `has_doc_type` |
| `rag_prompt.py` | prompty (extrakcia, špecifikácia; staré incidentové funkcie) |
| `covenants.py` | validácia špecifikácie, výpočet, stav |
| `sources.py`, `contract_rules.py` | overenie citácií a podporovaných textových vzorov zmluvy |
| `thresholds.py`, `thresholds.json` | načítanie a hodnoty prahov |
| `load_documents.py` | chunkovanie a načítanie do DB |
| `t2_retrieval.py` | test T2 |
| `t3_spec.py` | test T3a (špecifikácia) |
| `t3_chain.py` | test T3 (celý reťazec) |
| `generate_data.py`, `data/`, `data_test/` | generátor a dáta |
| `providers.py`, `config.py` | volanie modelov a profily |
| `lab.sh`, `lab_start.py`, `lab_start_README.md`, `check_cloud.py` | denná kontrola a sondy |
| `llm_metrics.py`, `llm_prices.json` | volania LLM s tokenmi a ceny (z incidentového labu, pre T6) |
| `rag_test.py`, `sweep_eval.py`, `test_rag_benchmark.py` | zostatky z incidentového labu (zatiaľ neprispôsobené) |
| `results/` | výsledky behov (**v `.gitignore`**, existujú len na VM; zálohovať) |

---

## 12. T5: opakovateľnosť (plán na zajtra)

**Otázka:** dá agent pri rovnakom vstupe vždy rovnaký výsledok? (Dôvod: C10-2026Q1 u qwen38.)

### 12.1 Rozhodnutia potrebné pred kódom
1. `--repeats 3`; poradie modelov: najprv qwen38 (~21 min), potom haiku (~8 min, pár centov).
2. Teplota: odporúčanie **merať predvolené správanie** (teplotu nenastavovať); v dokumente uviesť, že zníženie
   teploty je možné opatrenie, ak T5 ukáže nestabilitu.

### 12.2 Návrh
- `t3_chain.py --repeats N`: vyhľadávanie sa spraví **raz** (embeddingy sú deterministické; meria sa LLM) a použije
  pre všetky behy; behy za sebou; výstup `results/t3_chain_<tag>.json` s poľom `runs` (alebo samostatné súbory
  `<tag>_r1..r3`). Zachovať pravidlá: povinný tag, žiadne prepisovanie, časované výpisy.
- `t5_stability.py <tag>`: z výsledkov spočíta pre každý prípad zhodu **stavu**, **špecifikácie** (cez
  `t3_spec.differences`), **extrahovaných položiek** a krok, v ktorom sa behy líšia.
- Kategórie: **stabilný** (všetky 3 rovnaké); **neškodne nestabilný** (líši sa len `human_review` oproti
  správnemu stavu); **nebezpečne nestabilný** (`breach` v jednom behu a `no_breach` v inom). Rozhoduje tretia.
- Výstup: počty kategórií, zoznam nestabilných prípadov s dôvodmi, porovnanie qwen38 vs. haiku, tabuľka času.
- Testy: kategorizácia na umelých riadkoch; `--repeats` nepoužíva sa bez `--tag`.
- Požiadavka z T3: ukladať `spec` a `items` pri každom behu (už v `t3_chain.py`).

### 12.3 Hotové keď
Vieme povedať: „z 36 prípadov bolo X stabilných, Y neškodne nestabilných, Z nebezpečne“ pre qwen38 aj haiku.
Pozor: rozdiel 1 prípadu medzi modelmi (35 vs. 36) nie je štatisticky významný (36 prípadov, 12 firiem).

---

## 13. Zvolené rozhodnutia a ich dôvody (rýchly prehľad)

| Rozhodnutie | Dôvod |
| --- | --- |
| Stav určuje kód, nie LLM | testovateľnosť, vymyslená výnimka nesmie zmeniť `breach` na `no_breach` |
| Firma je povinný filter vo vyhľadávaní | dokument iného klienta sa nesmie vrátiť |
| Prah per embedding profil | škály podobnosti sa medzi modelmi nedajú porovnávať |
| Prah volený podľa recallu, nie precision | chýbajúci dôkaz je drahšia chyba než jeden chunk navyše (gemini 0,70 → 0,65) |
| Existencia waiveru cez `doc_type`, nie prah | prah nerozlíši „pravidlá o waiveroch“ od skutočného waiveru (rozdiel 0,02) |
| Definície chunkované po bodoch | EBITDA hit@1 azure/bge 0 → 36/36; väčší efekt než prah |
| Vyhľadávanie vopred pre všetky prípady | Ollama padá pri striedaní bge-m3 a veľkého LLM v jednom behu |
| Porovnanie bez `id` a len waivery daného obdobia | `id` je voľná štítka; očakávaná špecifikácia obsahuje aj waivery iných období |
| Lokálny qwen38 ako predvolený model agenta, haiku na porovnanie | rozdiel v správnosti minimálny, lokálny nemá cenu, ale je ~3× pomalší |

---

## 14. Čo chýba na dokončenie celého testu

Priorita zhora nadol (A je zajtra).

**A. T5 opakovateľnosť** (sekcia 12).

**B. T6 prevádzka.** Zaznamenať tokeny, trvanie a cenu vrátane zlyhaní; latencia p50 a p95, chybovosť, cena LLM
a cena prípadu. `providers.chat` vracia len text (bez usage). `llm_metrics.py` už má volania s usage od poskytovateľa
a `llm_prices.json` ceny (haiku 0,10 / 0,50 USD za milión tokenov vstup/výstup do 100 000 vstupných tokenov;
ceny sú zadané používateľom, neoverené); treba ich napojiť na `agent.run` (usage na krok). Lokálny model: cena 0,
elektrina sa nepočíta. Odporúčané urobiť **pred** záverečnými behmi, aby sa tokeny zbierali už vtedy.

**C. T4 útoky.** Dnes sú 2 útoky vo výkaze v dev (C11-2026Q2 `override`, C12-2026Q3 `exfiltration`) a 1 v teste
(C18-2026Q3 `override`); všetky tri prešli bez zmeny stavu pri qwen38 a haiku (dev). Chýba: **dvojice** čistý/napadnutý
výkaz toho istého prípadu, **nepriame útoky** (v zmluve, waiveri, poznámkach analytika), pokus o únik medzi firmami
(filter na firmu), pokus o „akciu“, nepovolená citácia. Metriky: zmena čísel, špecifikácie alebo stavu.

**D. T1 extrakcia.** Presnosť položiek proti `expected_items` (hodnota aj strana, chýbajúce a vymyslené polia) pre
každý LLM. Dáta sú v `t3_chain_*.json` (`items`; `t3_chain_qwen_run1.json` ich nemá, treba nový beh). Treba
samostatný skript alebo analýzu; vyhodnotenie zatiaľ nie je napísané.

**E. Tri režimy T3.** Dnes existuje len režim RAG. Plán: (1) **bez RAG** (agent dostane len výkaz a všeobecné
pravidlo; dá sa porovnať aj s deterministickým `generic_rule_status`), (2) **RAG** (hotové), (3) **celá zmluva**
(LLM dostane všetky dokumenty klienta). Treba parameter `mode` v `agent.run` a príslušný prompt; porovnať
správnosť, prehliadnuté porušenia, podiel `human_review`, tokeny.

**F. Zamknutie a vyhodnotenie `data_test/`.** Zamknúť chunkovanie, dotazy, prahy a prompt (po A až E nemeniť).
Potom jednorazovo: `python t2_retrieval.py --set test --final`; T3a a T3 na test sade. `t3_spec.py` a `t3_chain.py`
dnes bežia **len na dev**: doplniť `--set test --final` s rovnakým ochranným pravidlom ako `t2_retrieval.py`
(bez `--final` odmietnuť). Test sada je už načítaná vo všetkých troch tabuľkách. Ak výsledok na test sade
vyjde výrazne horší než na dev, je to znak preučenia (zapísať; po úprave treba vygenerovať novú test sadu).

**G. Reprodukovateľnosť výsledkov.** Do výsledkov zapisovať verziu promptu (P1…), prah, `SPLIT_DEFINITIONS`,
modely a čas. Dnes sa verzia promptu nikde nezaznamenáva (mapovanie v sekcii 7 je z pamäte).

**H. Záverečné behy s finálnym promptom.** Všetky modely, ktoré sa budú porovnávať (qwen38, haiku, prípadne azure
a gemma), spustiť znova s rovnakou (finálnou) verziou promptu. Staré čísla (gemma 24, azure 36, qwen38 36 s P2)
nie sú rovnaké podmienky ako T3 s P3.

**I. Dokumentácia.** Zosúladiť `README.md` (stav testov, `agent.py`, T3a), `LAB_FINAL_DOCUMENT.md` (sekcia 3 má
T3a; chýba T3 celý reťazec, T5, T6, T4) a `T2_retrieval_embeddings.md` (sekcia 2: 135 chunkov je neaktuálne,
aktuálne 308 na tabuľku).

**J. Docker image a rozhranie.** `agent.run` už vracia medzikroky (`steps`) a umožňuje vložiť vlastný text výkazu
a dokumenty (`statement_text`, `documents`), takže je pripravený na UI. Zostáva: Dockerfile (kód, `thresholds.json`,
konfigurácia modelu), prepojenie na existujúcu `app_llm_homelab` (má `Dockerfile`, `compose.yaml`, `api_server.py`,
UI) alebo jej klon s obrazovkou „nahraj výkaz → uvidíš každý krok a výsledok“. Či sa `app_llm_homelab` na to hodí,
**nebolo overené** (je to nástroj na porovnávanie odpovedí LLM, nie na covenanty). Dokumenty by sa mali načítavať
z dôveryhodného úložiska aplikácie, nie z nahraného súboru (`verify_sources` to predpokladá).

**K. Verzovanie a záloha.** Nič z tohto dňa nie je commitnuté. Necommitnuté: zmeny v `README.md`, `config.py`,
`generate_data.py`, `providers.py`, `rag_prompt.py`, `search.py`, `sweep_eval.py`, `test_generate_data.py`,
`../APP-LLM-HOMELAB.md`, `../code/install_lab_banner.sh`; nové: `agent.py`, `t3_spec.py`, `t3_chain.py`,
`t2_retrieval.py`, `load_documents.py`, `thresholds.json`, `lab.sh`, `lab_start.py`, `data_test/`, dokumenty a
testy. `results/` je v `.gitignore`, preto je potrebné výsledky zálohovať inak (kopírovať mimo repa). Commit
robiť len na pokyn; správy končia atribúciou, ktorú si zvolí používateľ.

**L. Známe nedostatky.**
- Dáta sú generované jednou šablónou (12 + 6 firiem); chunkovanie je písané pre túto šablónu
  (delenie podľa názvu článku „Definice a výklad“); skutočné zmluvy (skeny, PDF, prílohy) by vyžadovali parser.
- Overovanie zdrojov (`sources.py`, `contract_rules.py`) je šité na formát vygenerovaných dokumentov.
- `rag_test.py`, `sweep_eval.py` sú z incidentového labu; `SIMILARITY_THRESHOLD` v `config.py` je nepoužitý.
- Model gemma3:27b zlyháva na zápornej formulácii; často padá Ollama pri striedaní modelov (`ollama stop …`).
- Agent nepoužíva poznámky analytika (zámerne); `reported_ebitda` je len informatívna.

---

## 15. Čo sa dá a nedá tvrdiť

- Dá sa: na týchto dátach sa lokálny qwen38 a cloudový haiku v správnosti líšia o 1 z 36 prípadov a majú
  rovnaké bezpečnostné číslo (0 prehliadnutých porušení, 0 falošných poplachov); overovač zachytil nesprávne
  použitý limit a waiver; zmena chunkovania zlepšila vyhľadávanie viac než ladenie prahu.
- Nedá sa: že modely sú rovnako dobré (36 prípadov z 12 firiem, efektívna vzorka menšia); že agent je pripravený
  na produkciu; že výsledky platia pre skutočné zmluvy; že 36/36 nie je čiastočne prispôsobenie sa dev sade
  (prompt, dotazy aj prahy sa ladili na nej). Skutočné číslo prinesie až `data_test/`.
