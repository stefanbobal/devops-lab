# T2: retrieval zmluvných článkov, porovnanie 3 embedding modelov

Stav: 2026-11-03 (merania 1 a 2); vyhodnotenie na zamknutej test sade 2026-11-09 je v `STAV_LABU_A_DALSIE_KROKY.md`, sekcia 12e. Meranie 1 (základ, článok = chunk) a meranie 2 (H1: definície po bodoch), sekcia 10.
Všetky firmy a čísla sú vymyslené.
Súvisí s: README (sekcia 2 a test T2), `load_documents.py`, `search.py`, `t2_retrieval.py`,
surové výsledky v `results/t2.json`.

## 1. Čo testujeme a prečo

Agent má kontrolovať úverové podmienky (covenants). Pred výpočtom musí vedieť, **podľa akej
definície a s akým limitom** sa počíta. Tieto informácie sú v zmluve klienta (definícia EBITDA,
definícia čistého dluhu, limit pre daný Den testování, prípadne dodatok alebo waiver).
Do promptu nedávame celú zmluvu, ale nájdené články (RAG).

**Otázka T2:** keď agent položí otázku k zmluve, nájde vyhľadávanie ten článok, ktorý
obsahuje správnu odpoveď? A líši sa to medzi tromi embedding modelmi?

T2 meria iba vyhľadávanie. Nehodnotí LLM ani výpočet stavu (to sú T1 a T3).
Ak sa v T3 pokazí špecifikácia, vďaka T2 vieme, či príčinou nebol chýbajúci článok.

## 2. Čo je v databáze

- **Zdroj:** zmluvy, dodatky, waivery a poznámky analytika 12 vymyslených firiem (`data/companies/`).
  Výkazy sa nenačítavajú, sú vstupom agenta, nie jeho znalosťou.
- **Chunky:** 135 v čase merania 1 (dev sada, delenie po článkoch). Aktuálne má **každá z troch tabuliek 308 chunkov**
  pre 18 firiem (dev aj zamknutá test sada; `load_documents.py` načíta obe, načítanie nie je vyhodnotenie):
  284 článkov zmluvy (vrátane definícií delených po číslovaných bodoch), 4 články dodatkov, 2 waivery a 18 poznámok analytika.
  Zmluvy a dodatky sa delia **po článkoch** (`## Článek N – ...`), článok „Definice a výklad“ po bodoch (meranie 2),
  waiver a poznámky nemajú články, takže je to jeden chunk na dokument. Po pridaní útočných sád (T4) majú tabuľky 2 610 chunkov.
- **Embedovaný text chunku:** hlavička + text článku, napríklad
  `Firma: Vltavská strojírenská a.s. / Dokument: smlouva.md (contract), článek 2 – Definice a výklad / <text>`.
- **Tabuľky:** `covenant_docs_bge`, `covenant_docs_azure`, `covenant_docs_gemini` v kontajneri
  `pgvector-banka` (port 5433). Stĺpce: firma, dokument, typ, článok, strana, text, vektor.
- **Vyhľadávanie:** najprv SQL filter na firmu (povinný), potom zoradenie podľa kosínovej podobnosti
  (`1 - (embedding <=> dotaz)`). Poznámky analytika sa v T2 vynechávajú, nie sú dôkazom limitu ani
  výnimky.

### Testované modely

| Profil | Model | Poskytovateľ | Dimenzia | Poznámka |
| --- | --- | --- | --- | --- |
| `azure` | text-embedding-3-small | Azure OpenAI (Foundry) | 1536 | bez typu úlohy |
| `gemini` | gemini-embedding-001 | Vertex AI (GCP) | 1536 | typ úlohy `RETRIEVAL_DOCUMENT` pre chunky a `RETRIEVAL_QUERY` pre dotazy |
| `bge` | bge-m3 | lokálna Ollama | 1024 | bez typu úlohy a bez prefixu |

## 3. Ako test prebieha

Pre každý z 36 prípadov (12 firiem × 3 štvrťroky) sa položia fixné dotazy:

| Druh | Dotaz | Správny chunk |
| --- | --- | --- |
| `ebitda` | „Jak je ve smlouvě definována EBITDA?“ | článok, ktorý cituje `expected.json` (zvyčajne smlouva čl. 2) |
| `debt` | „Jak je ve smlouvě definován Čistý dluh?“ | tiež zvyčajne smlouva čl. 2 |
| `limit` | „Jaká je nejvyšší přípustná hodnota finančních ukazatelů pro Den testování <dátum>?“ | článok s limitom (smlouva čl. 5 alebo 6; pri C10 Q2 a Q3 dodatok čl. 1) |
| `waiver` | „Prominutí porušení finančního ukazatele pro Den testování <dátum>?“ | waiver dokument; iba 3 prípady majú waiver |

Pre každý dotaz sa vezmú top-3 chunky tej istej firmy.

- **hit@1:** správny chunk je na prvom mieste.
- **hit@3:** správny chunk je medzi prvými tromi.
- **Sweep prahu:** pre prahy 0,30 až 0,85 sa počíta recall (správny chunk zostane nad prahom) a precision
  (aký podiel chunkov nad prahom je správny).

Poznámka k správnosti: „správny“ znamená presne ten dokument a článok, ktorý uvádza `expected.json`,
nie ľubovoľný článok, ktorý by odpoveď tiež obsahoval.

## 4. Výsledky

| Profil | EBITDA hit@1 | Dluh hit@1 | Limit hit@1 | Waiver hit@1 | hit@3 (všetko) |
| --- | --- | --- | --- | --- | --- |
| gemini | 36/36 | 36/36 | 33/36 | 3/3 | 100 % |
| bge | 0/36 | 30/36 | 32/36 | 3/3 | 100 % |
| azure | 0/36 | 3/36 | 35/36 | 3/3 | 100 % |

### Na ktorom mieste je správny článok, keď nie je prvý

- **azure:** EBITDA 33× na 2. mieste a 3× na 3. mieste (C10); dluh 33× na 2. mieste.
- **bge:** EBITDA 36× na 2. mieste; dluh 6× na 2. mieste.
- **gemini:** žiadne chyby pri definíciách; pri limite 3× na 2. mieste (všetky C10).
- **Čo je na prvom mieste namiesto článku 2:** takmer vždy článok 5 alebo 6 („Finanční ukazatele“),
  teda článok, ktorý EBITDA a dluh iba používa v pomere.

### Hodnoty podobnosti správneho chunku (priemer)

| Profil | EBITDA | Dluh | Limit | Waiver |
| --- | --- | --- | --- | --- |
| gemini | 0,72 | 0,71 | 0,71 | 0,76 |
| bge | 0,54 | 0,55 | 0,55 | 0,67 |
| azure | 0,52 | 0,47 | 0,54 | 0,64 |

**Podobnosti rôznych modelov sa nedajú porovnávať.** Gemini dáva všeobecne vyššie čísla.
Vypovedá o tom iba poradie a rozdiel medzi správnym a nesprávnym chunkom.

### Prahy (sweep)

- **gemini:** pri prahu 0,70 je recall 0,95 a precision 0,88. Je to výrazne najlepšie rozdelenie
  správnych a nesprávnych chunkov.
- **bge:** pri 0,50 recall 1,00 a precision 0,56. Pri 0,55 už recall klesá na 0,41.
- **azure:** pri 0,45 recall 0,97 a precision 0,41; pri 0,50 recall 0,63. Rozsah, v ktorom prah funguje, je veľmi úzky.
- Automaticky vybraný „najvyšší prah s plným recall“ (gemini 0,65, bge 0,50, azure 0,40) nie je
  nutne najlepší. Pri gemini sa 0,70 zdalo lepšie, no neskôr sa ukázalo, že 0,65 je bezpečnejšie (sekcia 12).

## 5. Čo z toho vyplýva

1. **Správny článok je v top-3 vždy (100 %) pri všetkých troch modeloch.** Ak agent dostane do
   promptu top-3, retrieval nie je úzke miesto.
2. **Rozdiel je v poradí.** Pri top-1 gemini vyhráva jasne, azure a bge systematicky preferujú
   článok o ukazateľoch pred článkom s definíciami.
3. **Chyba je systematická, nie náhodná.** Je to rovnaký pár článkov vo všetkých firmách. Zodpovedá
   to tomu, že zmluvy sú generované jednou šablónou.
4. **C10 je dobre vidieť na limite.** Dodatok a pôvodná zmluva sú oba v top-3. Ktorý z nich platí,
   rozhoduje `sources.py`, nie retrieval.
5. **Bežný stav `bge` pri limite C05:** na prvom mieste je waiver_2026Q2 aj pri Q1 a Q3, kde ešte
   neplatí. Je to len šum v poradí, validátor vymyslenú alebo neplatnú výnimku neprijme.

## 6. Hypotézy (zatiaľ neoverené)

Toto je namerané, nie vysvetlené. Nasledujúce body sú iba domnienky.

| # | Hypotéza | Ako to overiť |
| --- | --- | --- |
| H1 | Článok 2 obsahuje 6 definícií naraz, preto je jeho vektor „zmiešaný“ a dotaz na jednu definíciu mu nesedí. | Rozdeliť článok 2 po bodoch (2.5 EBITDA, 2.6 Čistý dluh) a znova spustiť T2. Citácia ostane na úrovni článku. **Overené v meraní 2 (sekcia 10): podporené.** |
| H2 | Gemini vyhráva aj vďaka typom úlohy (`RETRIEVAL_QUERY` / `RETRIEVAL_DOCUMENT`), ktoré azure a bge nemajú. | Pustiť gemini s rovnakým typom úlohy pre dotaz aj chunky a pozrieť, či sa výsledok zhorší. |
| H3 | Gemini je väčší model a lepšie rozumie českému právnemu textu než `text-embedding-3-small`. | Priamo sa to v labe overiť nedá. Nepriamo: porovnať s väčším lokálnym modelom (`qwen3-embedding:4b` je v Ollame). |
| H4 | Dotaz „Jak je definována EBITDA?“ je lexikálne bližší článku 5, kde sa EBITDA spomína viackrát, než definícii. | Prepísať dotaz do tvaru definície („EBITDA znamená ...“) a porovnať. |
| H5 | Hlavička `Firma: ... Dokument: ...` je rovnaká vo všetkých chunkoch firmy a znižuje rozlíšenie medzi nimi. | Načítať chunky bez hlavičky a porovnať. |

Ak by H1 platila, malo by sa zlepšiť najmä azure a bge a gemini by sa nemalo zhoršiť.

## 7. Obmedzenia

- **Vzorka je menšia, než vyzerá.** Dotazy na definície sú rovnaké vo všetkých 3 štvrťrokoch firmy,
  takže „36“ je pri EBITDA a dluhu v skutočnosti 12 rôznych situácií. Pri `waiver` je len 3 prípady.
- **Zmluvy sú generované jednou šablónou.** Chyby sa preto opakujú a skutočné zmluvy by boli rôznorodejšie.
- **Malý korpus.** Po filtri na firmu sa vyberá z 10 až 13 chunkov. Rozdiely medzi modelmi by na
  veľkej DB mohli vyzerať inak.
- **Jedna formulácia dotazu na druh.** Výsledok môže závisieť od formulácie (H4).
- **Presné poradie sa môže mierne líšiť pri opakovaní** (volania cloudových modelov nie sú garantované
  deterministické).

## 8. Ako to zopakovať

```bash
cd ~/devops-lab/ai-labs/code_banka
source .venv/bin/activate
bash lab.sh                       # očakávaný výsledok: Lab ready.
docker compose up -d              # ak nebeží pgvector-banka
for p in bge azure gemini; do EMBED_PROFILE=$p python load_documents.py; done
python t2_retrieval.py            # vypíše tabuľku; surové dáta v results/t2.json
```

## 9. Ďalšie kroky

- ~~Overiť H1~~ (hotovo, sekcia 10).
- H2, H4 a H5 už nie sú nutné pre definície (všetky modely majú 36/36). Overovali by sme ich len ak by sa
  retrieval zhoršil na testovacej sade.
- Zapísať prahy do `thresholds.json` pre každý profil zvlášť, kalibrované iba na dev sade (sekcia 11).
- Jednorazovo vyhodnotiť zamknutú testovaciu sadu (`data_test/`, 18 prípadov).
- Pokračovať prompt-mi pre LLM (`rag_prompt.py`) a testom T3.

## 10. Meranie 2: definície rozdelené po bodoch (H1)

Zmena: článok „Definice a výklad“ sa už nechunkuje ako jeden celok, ale po číslovaných bodoch
(2.1 až 2.6 alebo 2.7, každý bod jeden chunk s poľom `clause`). Ostatné články ostali celé.
Zvyšok testu je rovnaký (dev sada, 36 prípadov, rovnaké dotazy). Výsledky: `results/t2_split_defs.json`,
záloha základu: `results/t2_baseline.json`.

Okrem pôvodnej metriky (správny článok) pribudla **striktná** metrika pre EBITDA a dluh: chunk musí byť
v správnom článku **a** obsahovať samotnú definíciu (`„EBITDA“`, resp. `„Čistý dluh“` / `„Dluh“`). Bez nej by
chunk 2.1 (definícia Banky) po rozdelení tiež „trafil článok 2“.

### Výsledky (hit@1, pôvodná metrika; v zátvorke základ z merania 1)

| Profil | EBITDA | Dluh | Limit | Waiver | hit@3 |
| --- | --- | --- | --- | --- | --- |
| gemini | 36/36 (36/36) | 36/36 (36/36) | 33/36 (33/36) | 3/3 (3/3) | 100 % |
| bge | **36/36** (0/36) | **36/36** (30/36) | 32/36 (32/36) | 3/3 (3/3) | 100 % |
| azure | **36/36** (0/36) | **36/36** (3/36) | 35/36 (35/36) | 3/3 (3/3) | 100 % |

Striktná metrika (chunk obsahuje definíciu) vyšla pri EBITDA aj dluhu **36/36 pri hit@1 aj hit@3 pre všetky
tri modely**, takže zlepšenie nie je len tým, že sa trafil článok.

### Odstup správneho chunku od najlepšieho nesprávneho (rozdiel podobností)

Rozdiel medzi najvyššou podobnosťou správneho chunku a najvyššou podobnosťou nesprávneho chunku
(kladný znamená, že správny vyhráva). Podobnosti sa nedajú porovnávať medzi modelmi, rozdiel v rámci modelu áno.

| Profil | EBITDA (min / priemer) | Dluh (min / priemer) | Limit (min / priemer) | Waiver (min / priemer) |
| --- | --- | --- | --- | --- |
| gemini | 0,064 / 0,079 | 0,053 / 0,082 | -0,007 / 0,033 | 0,028 / 0,031 |
| bge | 0,081 / 0,096 | 0,106 / 0,172 | -0,040 / 0,079 | 0,030 / 0,033 |
| azure | 0,091 / 0,133 | 0,157 / 0,192 | -0,033 / 0,054 | 0,076 / 0,078 |

Pri definíciách je odstup vo všetkých prípadoch kladný, teda nie je to tesné víťazstvo. Pri limite sú
záporné minimá (rovnaké prípady C10 a C05 ako v meraní 1).

### Čo sa zmenilo a čo nie

- **H1 je podporená.** Po rozdelení článku sa `azure` a `bge` pri definíciách dostali z 0/36 (EBITDA)
  a 3/36, resp. 30/36 (dluh) na 36/36. `gemini`, ktorý bol dobrý aj predtým, sa nezhoršil.
- **Vedľajší efekt, ktorý sme sa obávali** (malé chunky 2.1 až 2.4 vytlačia iné články z top-3), sa neprejavil:
  hit@3 ostal 100 % a limit ani waiver sa nezhoršili.
- **Limit je nezmenený**: C10 (dodatok a pôvodná zmluva sa striedajú na 1. mieste) a C05 pri `bge` (waiver
  na 1. mieste pri Q1 a Q3, kde ešte neplatí). Nie je to chyba chunkovania, ale nejednoznačnosť, ktorú
  rieši validátor (`sources.py`), nie retrieval.
- **Dôkaz mechanizmu je len nepriamy.** Zlepšenie zodpovedá H1, ale nevylučuje, že pomáha aj to, že chunky sú
  kratšie a bližšie ku krátkym dotazom. H4 a H5 sme nemerali.

### Prahy po zmene (sweep na dev sade)

- **gemini:** pri 0,70 recall 0,97 a precision 0,88; pri 0,75 recall 0,65.
- **bge:** pri 0,50 recall 1,00 a precision 0,56; pri 0,55 recall 0,81 a precision 0,57.
- **azure:** pri 0,45 recall 1,00 a precision 0,48; pri 0,50 recall 0,98 a precision 0,60.
- Prahy sú zapísané v `thresholds.json` (sekcia 12).

### Obmedzenia merania 2

- **Dotazy a chunkovanie sme ladili na tej istej dev sade**, takže 36/36 môže byť čiastočne preučenie na túto
  šablónu. Skutočné overenie prinesie až zamknutá testovacia sada (iná štruktúra, 12 článkov v zmluve).
- Delenie funguje len na články, ktoré sú samé číslované body (`N.M text`), a delí sa podľa názvu článku.
  Pri skutočných zmluvách by to chcelo robustnejšiu detekciu.
- Hit@1 je 36/36 aj preto, že dotazy na definície sú rovnaké vo všetkých 3 štvrťrokoch firmy (efektívna vzorka 12).

## 11. Poradie ďalších krokov (ladenie a test oddelene)

1. Rozhodnúť a zapísať prahy na dev sade (`--write-thresholds`, alebo ručne podľa sweepu).
2. Zamknúť: už nemeniť chunkovanie, texty dotazov ani prahy.
3. Vygenerovať testovaciu sadu (`python generate_data.py --set test`) a načítať ju (`load_documents.py`).
4. Jednorazovo vyhodnotiť: `python t2_retrieval.py --set test --final`. Číslo z nej je výsledok T2.
5. Ak výsledok na test sade bude výrazne horší než na dev sade, je to znamenie preučenia. Treba ho zapísať
   a vrátiť sa k H4, H5 alebo robustnejšiemu delenie chunkov. Po takejto úprave testovacia sada prestáva byť
   „nezávislá“ a treba vygenerovať novú.

## 12. Prahy zapísané a oprava gemini

`thresholds.json` (dev sada, pravidlo: najvyšší prah s recall ≥ 0,95): azure 0,50, bge 0,50, gemini 0,70.
Aplikuje ich `find_relevant` v `search.py`; waiver sa rieši typom dokumentu (`find_waiver`).

Pri teste špecifikácie (T3a, `t3_spec.py`, qwen38 s retrievalom gemini) dostali 4 prípady (C01, C06, C08, C11,
vždy 2. štvrťrok) len 2 chunky: správny chunk s limitom mal skóre 0,695 až 0,700, čiže tesne pod prahom 0,70.
Model správne odmietol hádať (`refused`), v agentovi by išlo o `human_review`. Prah gemini sme preto znížili na
**0,65** (recall 1,00). Poučenie: pri bankovom použití je drahšia chýbajúca pasáž než jeden chunk navyše.

