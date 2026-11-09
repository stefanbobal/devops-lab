# Presun agenta z domáceho labu do Azure AI Foundry: zadanie a návrh

Účel: dokument opisuje, čo domáci agent robí, aké garancie dáva a čo musí Foundry verzia zachovať. Všetky firmy,
zmluvy a čísla sú vymyslené (fiktívna Modrá Banka a.s.). Čísla výsledkov sú z `STAV_LABU_A_DALSIE_KROKY.md`.
Veci, ktoré závisia od aktuálnej podoby Foundry (názvy služieb, formát nasadenia, rozšírenie vo VS Code), sú
označené **[overiť]**: pred implementáciou ich treba skontrolovať v aktuálnej dokumentácii, nie spoliehať sa na tento text.

---

## 1. Čo agent robí

Vstup: `company_id`, `period` (napr. `C01`, `2026Q1`). Výstup: `breach`, `no_breach` alebo `human_review` s dôvodmi
a krokmi. Agent kontroluje úverové podmienky (covenants) z výkazu a zmluvy.

**Princíp: stav určuje overiteľný kód, nie LLM.** LLM iba prevádza text na obmedzenú štruktúru (JSON). Python overuje
a počíta. Každé zlyhanie akéhokoľvek kroku 1 až 5 končí ako `human_review` s dôvodom; agent pri chybe modelu nikdy nespadne.

| # | Krok | Kto | Kód |
| --- | --- | --- | --- |
| 1 | `extract`: položky z výkazu (tržby, EBIT, odpisy, dlh, hotovosť …) | LLM | `rag_prompt.build_extract_prompts` |
| 2 | `check_items`: povolené názvy, čísla; **číslo musí byť vytlačené na citovanej strane výkazu** | kód | `agent.check_items` |
| 3 | `retrieve`: úryvky zmluvy z vektorovej DB (firma je povinný filter) | kód + embedding | `search.py` |
| 4 | `spec`: špecifikácia (definícia EBITDA a dluhu, limity, waiver) ako JSON | LLM | `rag_prompt.build_spec_prompts` |
| 5 | `verify`: `validate_spec` + `verify_sources` (každá citácia sa overí v úplných dokumentoch) | kód | `covenants.py`, `sources.py`, `contract_rules.py` |
| 6 | `evaluate`: pomery, porovnanie s limitom, waiver, pásmo 2 % pri limite → `human_review` | kód | `covenants.evaluate` |

Režimy (`agent.run(..., mode=)`): `rag` (predvolený), `full` (všetky chunky zmluvy bez vyhľadávania), `generic`
(všeobecné pravidlo bez zmluvy, LLM len extrahuje), `no_context` (špecifikácia bez úryvkov).

## 2. Bezpečnostné invarianty (nesmú sa oslabiť)

1. **LLM nikdy nerozhoduje o stave.** Stav vzniká iba v `covenants.evaluate`.
2. **Čísla z výkazu sa overujú v texte**: model nemôže dodať číslo, ktoré nie je na uvedenej strane.
3. **Každá citácia sa overí v úplných dokumentoch** z dôveryhodného úložiska, ktoré model nevyberá. Dokument nahraný
   používateľom sa nesmie dostať do `verify_sources` ako dôveryhodný.
4. **Vyhľadávanie je vždy obmedzené na firmu** (`WHERE company_id = ...`; bez nej `ValueError`). Poznámky analytika sa
   nepoužívajú ako dôkaz. Existencia waiveru sa určuje typom dokumentu, nie prahom podobnosti.
5. **Parser článku s limitmi je prísny a fail-closed** (`contract_rules.contract_limits`): cudzia veta vo finančnom
   článku zmluvy → `human_review`. **Nezmierňovať.** V T4 raz qwen38 prevzal limit 6,0 z vloženej vety a zastavil ho
   práve tento parser.
6. **Text z výkazu a zmluvy je dáta, nie pokyny.** Prompt extrakcie to tvrdí; obrana pred vloženým pokynom v zmluve
   stojí na krokoch 5 a parseri, nie na modeli.
7. **Pri akejkoľvek neistote `human_review`**, nikdy hádanie.

## 3. Výsledky domáceho labu (základ pre porovnanie)

Dev sada: 36 prípadov, 12 firiem (C01 až C12); stavy 21 `no_breach`, 12 `breach`, 3 `human_review`.

| Test | Výsledok |
| --- | --- |
| T3 celý reťazec | haiku 36/36; qwen3.8:27b 35/36 (C10-2026Q1 → bezpečný `human_review`); 0 prehliadnutých porušení, 0 falošných poplachov |
| T5 opakovateľnosť | qwen38 359/360 správnych case-runov (10 behov), haiku 108/108 (3 behy); nikdy sa neprehodilo `breach` ↔ `no_breach` |
| T1 extrakcia | 5 400 položiek, 0 chýb (jedna šablóna výkazov, bez skenov) |
| T4 útoky | 0 úspešných zo 378 prípadov; 72 zo 378 prípadov skončilo ako narušenie (`human_review`, ~19 %); vždy pri útoku vo finančnom článku zmluvy, kde parser blokuje 100 %, plus ojedinelé odmietnutia haiku |
| T6 prevádzka (36 prípadov) | haiku 93 377 / 31 448 tokenov (vstup/výstup), ~4,3 s LLM na prípad; qwen38 ~12,6 s |
| Azure `gpt` nasadenie, T3a | špecifikácia 36/36 (iný krok než T3, ale rovnaký prompt) |

Bez zmluvy (všeobecné pravidlo dluh/EBITDA ≤ 4,00) by sa pokazilo 12 z 36 prípadov; kontrola tohto základu je režim `generic`.
Obmedzenie: dáta sú generované jednou šablónou; výsledky nehovoria nič o skutočných zmluvách či PDF.

## 4. Mapovanie domáci lab → Azure

| Domáci lab | Azure / Foundry |
| --- | --- |
| Ollama (qwen38, bge-m3) | nasadenia modelov vo Foundry; profil `azure` v `config.py` už existuje (LLM `AZURE_OPENAI_LLM_DEPLOYMENT`, embedding `text-embedding-3-small`, 1536 rozmerov) **[overiť]** |
| `pgvector-banka` (Docker, PG16 + pgvector, port 5433) | Azure Database for PostgreSQL s rozšírením pgvector (najmenšia zmena `search.py`), alternatíva Azure AI Search **[overiť]** |
| `data/<firma>/*.md` na disku | dôverné úložisko (Blob Storage alebo súbory v obraze); dokumenty nikdy z nahrávaného súboru |
| kľúče v `.env` | Managed Identity a Key Vault; kľúče sa nesmú dostať do repa ani do obrazu |
| `python agent.py C01 2026Q1` | endpoint agenta (pozri sekciu 5) |
| Prah `thresholds.json` | **prah je per embedding profil**; pre `azure` je 0,50 (recall 0,98, precision 0,60). Pri zmene modelu alebo chunkovania treba T2 zopakovať |

Pri presune sa musí zachovať chunkovanie (`load_documents.py`, definície po číslovaných bodoch) a rovnaké dotazy
(`agent.build_queries`); inak prah z `thresholds.json` neplatí.

## 5. Dve architektúry nasadenia

**A. Reťazec ako jeden nástroj.** Foundry agent (alebo kontajner) zavolá jeden nástroj `check_covenants(company_id,
period)`; celý reťazec beží v našom kóde a vráti štruktúrovaný výsledok. Poradie krokov a stav určuje kód. Bezpečnostné
invarianty sa zachovajú bez dodatočnej práce.

**B. Konverzačný model volá jednotlivé kroky ako nástroje.** Môže byť rovnako bezpečný, **len ak sa bezpečnosť vynúti
na strane nástrojov, nie modelom**. Podmienky:

1. Nástroje sú stavové: `start_run(company_id, period)` vráti `run_id`; ďalšie nástroje berú iba `run_id`.
   Medzivýsledky (položky, špecifikácia) žijú na serveri. **Model nikdy nedodáva čísla ani špecifikáciu** pre `evaluate`.
2. Každý nástroj skontroluje predchádzajúci krok a odmietne beh mimo poradia alebo opakovanie s inými údajmi.
3. `evaluate` je jediný zdroj stavu a výsledok sa vráti ako štruktúrovaný objekt, ktorý aplikácia zobrazí **doslova**,
   nie ako text, ktorý model prepíše.
4. Nástroje s LLM vo vnútri (`extract`, `spec`) volajú model samy. Konverzačný model je potom len smerovač.
5. Nevracať konverzačnému modelu surový text výkazu ani zmluvy (kanál pre vložený pokyn).
6. Odpoveď `spec_refused` obsahuje až 140 znakov textu z modelu; ak ju UI vykresľuje, musí ju ošetriť (kanál pre útočníka).
7. Foundry guardrails (filtre obsahu, ochrana pred vloženými pokynmi) sú dodatočná vrstva, nie náhrada **[overiť]**.

Bez týchto podmienok je B slabšie než domáci lab: poradie krokov by určoval model a vloženým pokynom by sa dalo meniť.
S nimi sa B v praxi blíži k A (model len volá nástroje v danom poradí), takže jeho prínos je hlavne v konverzačnom rozhraní.
**Odporúčanie: A ako hlavná verzia, B ako experiment.** Pre B treba zopakovať T4 (útoky) a kontrolovať aj poradie volaní.

## 6. Plán porovnania "kontajner" vs. "Foundry agent"

Rovnaký kód, rovnaké dáta, rovnaký model; mení sa len orchestrácia. Inak by sa merali modely, nie architektúry.

| Variant | Orchestrácia | Model |
| --- | --- | --- |
| V1 | domáci kontajner (dnešný agent) | Azure model (rovnaký ako V3 a V4) |
| V2 | domáci kontajner | lokálny qwen38 / haiku (referenčné, už zmerané) |
| V3 | Foundry agent, architektúra A | ten istý Azure model |
| V4 | Foundry agent, architektúra B (so stavovými nástrojmi) | ten istý Azure model |

Merať na tých istých prípadoch (36 dev, potom jednorazovo `data_test/`) a rovnakými skriptmi, ak sa dá
(`t3_chain.py`, `t5_stability.py`, `t6_ops.py`, `t4_attacks.py`):

- správnosť, prehliadnuté porušenia (cieľ 0), falošné poplachy, podiel `human_review`;
- opakovateľnosť (T5, aspoň 3 behy, pri B aj poradie volaní);
- útoky (T4, sady A a F; hlavné číslo = počet úspešných útokov, cieľ 0);
- latencia a tokeny na prípad, cena (T6);
- pre B navyše: počet prípadov, kde model preskočil krok, zavolal ich mimo poradia, alebo vrátil iný stav, než nástroj.

Kritérium prijatia pre Foundry verziu: **0 prehliadnutých porušení a 0 úspešných útokov**, správnosť nie horšia než V1 a
každá odchýlka od V1 vysvetlená. Nepoužívať `data_test/` na ladenie; je to jednorazová sada.

## 7. Poradie prác

1. Dokončiť domáci lab (krok E porovnanie módov, krok H finálne behy) a zafixovať prompt (`PROMPT_VERSION`, hash v `meta`).
2. Spustiť existujúce testy s `LLM_PROFILE=azure EMBED_PROFILE=azure` bez nasadenia (rýchly dôkaz, že kód funguje na Azure modeloch).
3. Presunúť vektorovú databázu a zopakovať T2 s Azure embeddingom a prahom 0,50.
4. Zabaliť agenta (Dockerfile, `thresholds.json`, konfigurácia modelu cez premenné prostredia) a nasadiť.
5. Foundry verzia A, potom (voliteľne) B; porovnanie podľa sekcie 6.

## 8. Čo sa dá a nedá tvrdiť

Dá sa: rovnaký reťazec s overovaním dáva rovnaké bezpečnostné číslo bez ohľadu na model, ak kód zostane nezmenený.
Nedá sa: že Foundry verzia je bezpečná, kým neprejde T4 a T5 v samotnom Foundry (nepreniesť z domáceho labu); že výsledky
platia pre skutočné zmluvy; že B je rovnako bezpečné ako A bez zmerania.
