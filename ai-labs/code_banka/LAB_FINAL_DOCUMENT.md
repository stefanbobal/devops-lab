# code_banka: záverečný dokument (pracovná verzia)

Priebežne dopĺňaný dokument. Každá sekcia sa pridáva po dokončení kroku labu, na záver sa upraví do jedného celku.
Podrobné merania sú v samostatných súboroch (`T2_retrieval_embeddings.md`, `STAV_LABU_A_DALSIE_KROKY.md`). Všetky firmy a čísla sú vymyslené.

## 1. Zámer labu

Agent má kontrolovať úverové podmienky (covenants) z výkazov firmy. **Výsledný stav určuje overiteľný kód, nie LLM.**
LLM vyťahuje údaje, číta zmluvu a píše vysvetlenie. Pozri README.

## 2. RAG nad zmluvami (stav: retrieval odmeraný, T2)

Zdroj merania: `T2_retrieval_embeddings.md`.

- Zmluvy sa delia na chunky, každý sa premení na vektor a uloží do tabuľky pre daný embedding model
  (Azure `text-embedding-3-small`, Gemini `gemini-embedding-001`, lokálny `bge-m3`).
- Vyhľadávanie: najprv SQL filter na firmu (povinný), potom kosínová podobnosť, vráti sa top-3.
- Správny článok je v top-3 pri všetkých troch modeloch vždy. Rozdiel je v hit@1.

### 2.1 Chunkovanie

**Čo to je:** rozdelenie dlhého dokumentu na menšie kúsky, z ktorých každý má vlastný vektor.
Jeden chunk má byť o jednej veci, inak je jeho vektor rozmazaný.

**Čo sme zistili:** článok 2 obsahoval 6 definícií. Pri azure a bge vyhrával článok 5 (kde sa EBITDA spomína často).
Po rozdelení po bodoch (2.1 až 2.6) sa azure a bge pri EBITDA a dluhu zlepšili z 0/36 (a 3/36, 30/36) na 36/36,
bez zmeny modelu. Poučenie: pred ladením prahu a pred výmenou modelu skontroluj chunkovanie.

**Ako sa to robí v prevádzke:** začať jednoduchým pravidlom (pevná dĺžka s prekryvom), pri dokumentoch s
článkami deliť podľa štruktúry, ku každému chunku pridať hlavičku (kontext) a metadáta, varianty porovnať
na vyhodnocovacej sade, chunkovanie verzovať (po zmene nový index). Pokročilé techniky: sémantické,
hierarchické (parent-child), kontextové chunkovanie, špeciálne spracovanie tabuliek.

**Obmedzenie nášho riešenia:** delenie je napísané pre šablónu vygenerovaných zmlúv (podľa názvu článku).
Skutočné zmluvy (skeny, PDF, prílohy) by potrebovali parser dokumentov a ladenie na veľkej vzorke.

### 2.2 Prah podobnosti (similarity threshold)

**Čo to je:** hranica skóre, pod ktorou sa výsledok vyhľadávania zahodí. Vyhľadávanie vždy vráti top-k,
aj keď nič relevantné neexistuje. Prah rieši, kedy systém povie „nič som nenašiel“ a prípad ide človeku
(`human_review`) namiesto hádania.

**Kde sa aplikuje:** nie v databáze. Databáza vráti top-k so skóre, prah aplikuje náš kód po vrátení.
Ak je nad prahom menej než k výsledkov, agent dostane menej chunkov; ak nič, ide na `human_review`.

**Päť vecí na zapamätanie:**
1. Skóre nie je porovnateľné medzi modelmi (Gemini dáva správnym chunkom okolo 0,7, azure a bge okolo 0,5),
   preto má prah každý embedding model zvlášť.
2. Prah závisí od dát a chunkovania, ladí sa až po ustálení chunkovania.
3. Je to kompromis dvoch chýb: nízky prah prepustí nerelevantné (riziko halucinácie), vysoký zahodí správne
   (zbytočné odovzdanie človeku). U nás je bezpečnejšie priznať „neviem“.
4. Meria sa recall (koľko správnych ostane nad čiarou) a precision (koľko toho, čo ostane, je správne).
   Pri top-3 s jedným správnym je strop precision okolo 0,33, nízka precision nie je sama o sebe chyba.
5. Ladenie a test sa nerobia na tých istých dátach: prah sa ladí na ladiacej sade (dev), výsledok sa overí
   jednorazovo na zamknutej testovacej sade (`data_test/`, 18 prípadov).

**Čo sme zistili my:** negatívny test (waiver u firmy, ktorá ho nemá) ukázal, že vyhľadávač vráti článok o pravidlách
waiverov so skóre 0,72 až 0,74 (gemini), zatiaľ čo skutočný waiver má 0,76. Medzera je len 0,02. Prah, ktorý by to
oddelil, by zahodil väčšinu správnych chunkov pre iné otázky. Prah nevie rozlíšiť „téma sedí“ od „toto je ten
dokument“. **Existencia dokumentu sa preto rieši deterministicky** (typ dokumentu v metadátach, overenie v
`sources.py`), prah je len poistka proti úplne nerelevantnému textu.

**Ako sme prah vyberali (postup):**
1. Označená dev sada: pre každú otázku vieme, ktorý chunk je správny (gold). Navyše 33 negatívnych otázok
   (waiver u firmy, ktorá ho nemá), kde správna odpoveď neexistuje.
2. Mriežka prahov 0,30 až 0,85 po 0,05. Pre každý prah: recall, precision, false-accept
   (podiel negatívnych otázok, kde najlepší chunk ostal nad prahom).
3. Pravidlo: najvyšší prah s recall ≥ 0,95. Dôvod: chýbajúci správny chunk končí na `human_review` (bezpečná
   chyba), prepustený cudzí chunk musí ešte zastaviť validátor.
4. Prahy sú v `thresholds.json` pre každý profil zvlášť a aplikuje ich `find_relevant` v `search.py`.

| Profil | Prah | Recall | Precision | Skóre „článku o waiveroch“ (negatívne dotazy) | Skutočný waiver |
| --- | --- | --- | --- | --- | --- |
| gemini | 0,65 | 1,00 | 0,49 | 0,72 až 0,74 | 0,76 |
| bge | 0,50 | 1,00 | 0,56 | 0,60 až 0,64 | 0,66 až 0,68 |
| azure | 0,50 | 0,98 | 0,60 | 0,54 až 0,61 | 0,64 |

False-accept je pri vybraných prahoch 1,00 vo všetkých profiloch, teda prah negatívny waiver nezachytí. Na
zachytenie by bol potrebný prah 0,65 (bge), pri ktorom recall padne na 0,59, alebo 0,75 (gemini), recall 0,65.
Gemini sme najprv nastavili na 0,70 (precision 0,88, recall 0,97), no pri behu agenta (T3a, qwen38 s gemini
retrievalom) padli pod prah správne chunky s limitom v štyroch prípadoch (skóre 0,695 až 0,700), model dostal len
2 chunky a správne odmietol hádať (4 z 36 `refused`). Prah sme preto znížili na 0,65 (recall 1,00). Poučenie:
chýbajúci dôkaz je drahšia chyba než jeden zbytočný chunk navyše, takže prah sa volí podľa recallu, nie podľa
precision.

**Implementácia waiveru:** `find_waiver` najprv skontroluje v metadátach (`has_doc_type`), či firma má dokument
typu `waiver`. Ak nie, vráti prázdny výsledok bez vyhľadávania. Prah sa na túto otázku nepoužíva.

**Alternatívy:** reranker (cross-encoder, presnejší než porovnanie vektorov, ale pomalší), hybridné vyhľadávanie
(vektor + BM25, lepšie na presné výrazy ako „prominuje“), relatívny prah (odstup od prvého výsledku), prah podľa typu
otázky, LLM ako posudzovateľ relevantnosti, metadátové filtre, prepísanie dotazu.

**Úskalia:** cosine skóre nie je pravdepodobnosť (0,7 neznamená 70 % istotu). Prah sa po zmene modelu, chunkovania
alebo typu dokumentov musí rekalibrovať. V prevádzke sa sleduje podiel prázdnych výsledkov a vzorka sa kontroluje
ručne.

**Obmedzenia merania:** dáta sú generované a malé (12 firiem, dotazy na definície sa opakujú, efektívna vzorka je
okolo 12 situácií). Čísla ilustrujú metódu, nie záruku pre skutočnú banku.

### 2.3 Kto zodpovedá za chunkovanie

| Čo | Kto |
| --- | --- |
| Návrh vhodných chunkov | AI/data inžinier s doménovým expertom (právnik, úverový analytik) |
| Vyhodnotenie (testovacia sada, metriky) | AI inžinier, často spolu so správcom platformy |
| Prevádzka indexovacej úlohy (načítanie, plánovanie, opakovanie pri chybe) | správca platformy |
| Verzie a zmeny (nový index, záloha, prepnutie, aby sa nemiešali staré a nové chunky) | správca platformy |
| Monitoring (aktuálnosť indexu, počet chunkov, pokrytie firiem, kvalita) | správca platformy |
| Prístup a bezpečnosť (filtre podľa klienta, citlivé údaje) | správca platformy s bezpečnosťou |
| Cena (opätovné embedovanie pri zmene) | správca platformy |

## 3. Zmluvná špecifikácia z nájdeného textu (T3a, dev sada)

**Čo sa merá:** vyhľadávanie (bge, azure alebo gemini) dá LLM úryvky zmluvy, LLM vráti JSON so špecifikáciou
(definícia EBITDA a dluhu, limity, waiver). Kód ju overí (`validate_spec`, `verify_sources`) a porovná s očakávanou.
Všetky modely majú rovnaký prompt a rovnaké úryvky. Skript `t3_spec.py`, výsledky `results/t3_spec_*.json`.

| Beh | Model | Retrieval | Správnych z 36 | Poznámka |
| --- | --- | --- | --- | --- |
| run1 | haiku / azure / gemma | bge | 31 / 23 / 12 | pôvodný prompt |
| run2 | azure / haiku / gemma | bge | 36 / 35 / 24 | prompt s vysvetleným základom EBITDA |
| | qwen38 | bge | 36 | |
| | qwen38 | azure | 36 | |
| | qwen38 | gemini, prah 0,70 | 32 | 4× chýbal limit (skóre 0,695 až 0,700) |
| | qwen38 | gemini, prah 0,65 | 36 | |
| haiku_fix | haiku | bge | 36 | prompt s vetou o pomeroch |

**Čo sme zistili:**
1. Veľká časť chýb na začiatku bola v prompte, nie v modeloch. Model nevedel, že EBITDA vždy začína EBIT plus
   odpisy a že pomery počíta kód. Po doplnení sa azure a haiku dostali na 35 až 36 z 36.
2. Gemma (lokálna) zostala na 24 z 36: číta „nepřipočítávají“ ako pridanie. Qwen38 (lokálny) dal 36 z 36.
3. Voľba embedding modelu nerozhodla, ak sú prahy bezpečne nízko. Gemini s prahom 0,70 zahodil správny chunk
   s limitom, model správne odmietol hádať (v agentovi by išlo na `human_review`).
4. Overovač zachytil gemmu, ktorá pripísala waiver z 2. štvrťroka aj ku štvrťrokom 1 a 3. Bez overenia by
   `breach` mohol zmeniť na `no_breach`.
5. Chyby v našom meraní: porovnanie pôvodne trvalo na rovnakom id podmienky a započítavalo waivery z iných období.

**Obmedzenia:** prompt a porovnanie sme ladili na tej istej dev sade (12 firiem, 36 prípadov), takže 36/36 čiastočne
meria prispôsobenie sa týmto dátam. Skutočné overenie prinesie až `data_test/`. Modely neboli všetky spustené
s úplne rovnakou verziou promptu (qwen38 a azure bez poslednej vety o pomeroch); pred záverečným číslom ich treba
spustiť znova s finálnym promptom.

## 4. Agent a jeho reťazec (hotové)

**Agent a testy sú dve rôzne veci.** Agent (`agent.py`, `agent.run(company, period, mode)`) je kód, ktorý dostane výkaz firmy a
vráti stav, dôvody a všetky medzikroky. Testy merajú jeho kroky a pomáhajú vybrať model; v prevádzke sa nespúšťajú.

| Krok | Kto | Modul | Test |
| --- | --- | --- | --- |
| 1 `extract`: položky z výkazu | LLM | `rag_prompt.py` | T1 |
| 2 `check_items`: číslo musí byť na citovanej strane | kód | `agent.py` | T1 |
| 3 `retrieve`: úryvky zo zmluvy | kód + embedding | `search.py` | T2 |
| 4 `spec`: špecifikácia ako JSON | LLM | `rag_prompt.py` | T3a |
| 5 `verify`: validácia a overenie citácií | kód | `covenants.py`, `sources.py`, `contract_rules.py` | T3a, T3 |
| 6 `evaluate`: pomery, limit, waiver, pásmo 2 % | kód | `covenants.py` | T3 |

Kto čo robí je dôležité: **LLM nikdy nerozhoduje o stave.** Pri akomkoľvek zlyhaní krokov 1 až 5 je výsledok `human_review` s dôvodom.

## 5. Celý reťazec (T3)

Dev sada, 36 prípadov, prompt P3: haiku 36/36, qwen3.8 35/36 a po opakovaní 36/36, Azure 36/36; 0 prehliadnutých porušení a 0 falošných poplachov.
Jediná odchýlka (qwen3.8, C10-2026Q1, neskôr C03-2026Q1 v režime `full`) je chybná citácia zastavená overovačom → bezpečný `human_review`.

### Tri režimy práce so zmluvou (krok E)

| Režim | Správne | Prehliadnuté porušenia | Poznámka |
| --- | --- | --- | --- |
| `rag` | 36/36 (haiku, qwen3.8) | 0 | základ |
| `full` | 36/36 (haiku), 35/36 (qwen3.8) | 0 | nie lepší, ≈ 1,75× tokenov v kroku špecifikácie |
| `generic` (bez zmluvy) | 24/36 | **7** (+ 4 falošné poplachy) | zmluva je nutná |
| `no_context` | 3/36 | 0 | všetkých 36× odmietnutie, nič sa nevymyslelo |

## 6. Opakovateľnosť, prevádzka a extrakcia (T5, T6, T1)

- **T5:** qwen3.8 359/360 správnych behov (10 opakovaní); haiku 108/108. Nikdy sa neprehodilo `breach` ↔ `no_breach`.
  Jediná nestabilita bola citácia jedného prípadu.
- **T6 (36 prípadov):** haiku 93 377 / 31 448 tokenov, ≈ 4,3 s a $0,0007 na prípad; qwen3.8 ≈ 12,6 s (134 tokenov/s), bez poplatku;
  Azure 63 681 / 55 845 tokenov, 13,3 s. Žiadne neúplné ani nepoužiteľné odpovede.
- **T1:** 5 400 položiek na dev a 360 na teste, 0 chýb (výkazy z jednej šablóny, bez skenov; presnosť strán sa nemerala).

## 7. Útoky (T4)

12 druhov útokov (výkaz S1 až S7, zmluva C1 a X2, waiver C2, poznámky N1, únik medzi firmami X1) v troch rodinách; **0 úspešných zo 378 prípadov**.
Hlavné zistenie: **model sa dá oklamať, obranu drží kód.** Lokálny model raz napísal do špecifikácie limit 6,0 z vloženej vety; stav sa nezmenil
iba preto, že prísny parser článku s limitmi (`contract_rules.py`) zmluvu s cudzou vetou zamietol. Parser sa preto nezmierňuje; cena je,
že každý útok na finančný článok končí ako `human_review`.

## 8. Zamknutá testovacia sada (F) a finálny prompt (H)

Jednorazovo, bez zmeny promptu, prahu a chunkovania. Test (18 prípadov, 6 firiem): haiku 18/18, qwen3.8 18/18, Azure 16/18 (dva bezpečné `human_review`:
útok zastavený filtrom obsahu Azure a nejednoznačný waiver „Čistý dluh“ vs. „Dluh“). T2 hit@3 100 %, vzory chýb rovnaké ako na dev, preučenie sa nepreukázalo.
Obmedzenia: 18 prípadov z tej istej šablóny, jeden beh na model, firmy C13 až C16 sa predtým použili na útoky, takže sada nie je celkom nedotknutá.
Každý výsledok má `meta` s verziou a hashom promptu (`run_meta.py`).

## 9. Zostáva a obmedzenia

- Presun do Azure AI Foundry (hosted agent, vektorová databáza v Azure): `FOUNDRY_PORT.md`.
- OpenTelemetry, YAML konfigurácia agenta, GitHub Actions s regresnou sadou, Docker image a rozhranie (voliteľné).
- Obmedzenia: vygenerované dáta z jednej šablóny, jeden beh na model a režim, prompt a prahy ladené na dev sade, chunkovanie a overovanie šité na formát
  vygenerovaných zmlúv (skutočné zmluvy by potrebovali parsovanie PDF, detekciu štruktúry a odkazov).
