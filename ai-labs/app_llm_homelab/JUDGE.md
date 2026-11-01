# LLM judge: samostatný kontajner a asistované hodnotenie

Judge je dávkový Python worker v image `llm-homelab-judge:local`, služba `judge` v Compose. Dashboard je samostatná služba `app`, existujúci PostgreSQL kontajner `pgvector` ostáva spoločný. Worker číta už importované odpovede; pôvodný RAG test nespúšťa znova. Nemá otvorený port ani nástroje na vykonávanie diagnostických príkazov. Cloudové kľúče dostáva iba worker, nikdy dashboard.

```text
PostgreSQL: calls + scenarios → judge worker → Ollama alebo cloudový poskytovateľ
                                    ↓
                       judge_jobs + judge_evaluations
                                    ↓
                          dashboard → kontrola človekom
                                    ↓ až po Uložiť hodnotenie
                           pôvodná tabuľka reviews
```

**Spúšťanie priamo z aplikácie, lokálne aj cloudové modely:** aktuálny odporúčaný postup je v [JUDGE-UI.md](JUDGE-UI.md). Nižšie uvedené jednorazové CLI príkazy sú alternatíva; zachovávajú lokálny Ollama adaptér. Súbežne ich nepúšťaj s UI dávkou.

## Čo hodnotí

Každý navrhnutý krok má vlastnú krátku citáciu z pôvodnej odpovede a posudok:

| Pole | Význam |
|---|---|
| Technická správnosť | Podložené referenciou / v rozpore s referenciou / technicky neoverené |
| Podklad | Aktuálne údaje / hypotéza z histórie / bez podkladu |
| Priorita | Teraz / neskôr / zbytočné |
| Historická citácia | Sedí / nesedí / bez citácie / neoveriteľná |
| Riziko | Diagnostika / vyžaduje súhlas / neprijateľné |

Kritická chyba je samostatná vlajka; nesmie zaniknúť v priemere skóre:

| Kód | Pevné pravidlo pre `critical_error=true` |
|---|---|
| C1 | Odpoveď cituje historický incident, ktorý nebol dodaný v `retrieved_ids`. |
| C2 | Pri `dev-hana-insufficient` vydá konkrétnu príčinu za istú. |
| C3 | Navrhne zásah zakázaný guidance, napr. mazanie archívnych logov bez overenia. |
| C4 | Historickú príčinu vydá bez aktuálneho dôkazu za potvrdenú aj pre aktuálny incident. |

Každé kritické zistenie musí mať kód, presnú citáciu odpovede a krátke zdôvodnenie. Hodnotiteľ najprv uvedie stručné zdôvodnenia, potom skóre; nevyžadujeme interný myšlienkový postup. Dôkazy sú hlavné kritérium na rozlíšenie faktov a hypotéz; Neistota hodnotí, čo ešte overiť. Viac než tri hlavné investigatívne kroky obmedzí Použiteľnosť najviac na 1. Pri no_history je správne `none`; skutočná citácia historického ID znamená Citácie 0 a C1. Bez obsahu histórie judge neoverí význam citácie; pri dodaných ID môže obsahový súlad zostať nehodnotený. Človek má v aplikácii pôvodný kontext a môže ho overiť.

Výsledkom je stručné odporúčanie `mostly_suitable`, `needs_review` alebo `problematic`, návrh kritickej chyby a voliteľné návrhy piatich existujúcich skóre. Neoveriteľné skóre má hodnotu `null`. Dĺžka a pekné formátovanie nemajú samy osebe zvyšovať skóre. Pri režime bez histórie sa absencia historickej citácie netrestá.

**Dôležité obmedzenie prvej verzie:** `judge_references.json` zatiaľ neobsahuje schválené technické podklady. Technická správnosť preto musí zostať `unverified`. Judge vie posúdiť súlad s incidentom, priority, prácu s dodanou históriou a upozorniť na podozrivé kroky; nemá garantovať správnosť SAP/Oracle príkazov zo svojej pamäte. Toto je pilot asistovaného hodnotenia, nie automaticky overená technická pravda.

Schválené podklady možno pridať do `judge_references.json`: položka potrebuje `id`, `url`, `text` s presným overeným výňatkom a `approved: true`. Do hodnotenia idú iba schválené položky. Tvrdenie `supported`/`incorrect` bez existujúceho ID a doslovného výňatku validátor označí ako `unverified`, odstráni nepodložené referencie a pripojí viditeľné upozornenie; inak platný posudok zachová. Pôvodný výstup zostáva uložený. Samotná existencia citácie stále negarantuje, že ju judge správne interpretoval. Po zmene podkladov znovu zostav image; hash a verzia rozlíšia nový experiment.

Aktuálna rubrika `sap-oracle-general-v3` obsahuje iba tri hodnotiace sekcie: `general`, `critical_error_rules` a `score_anchors`. Nemá `scenarios`, `first_checks`, `later_checks` ani `avoid` a nepredpisuje správny diagnostický postup pre jednotlivé prípady. Rovnaké pravidlá sa použijú na každú odpoveď. Nový scenár nevyžaduje doplniť očakávané riešenie. Identifikátor prípadu slúži iba na aplikáciu výslovne ohraničeného pravidla C2. Pôvodné posudky s rubrikou v2 zostávajú historickými výsledkami podľa vtedajšieho zadania; nie sú novým hodnotením podľa všeobecnej rubriky.

## Nasadenie na Ubuntu VM

Existujúcich 550 odpovedí netreba znovu importovať. V priečinku aplikácie po aktualizácii repozitára:

```bash
cd ~/devops-lab/ai-labs/app_llm_homelab
bash docker_lab.sh build app judge
bash docker_lab.sh up -d app
```

V existujúcom app `.env` skontroluj tieto **verejné** nastavenia. Nie je potrebné meniť funkčné DB heslo ani cloudovú konfiguráciu:

```dotenv
JUDGE_OLLAMA_HOST=http://192.168.178.25:11434
JUDGE_MODEL=gemma3:27b
```

Výpočet beží vo Windows Ollame. Judge kontajner nepotrebuje GPU passthrough. Predvolený model je jeden z už nainštalovaných lokálnych modelov; nie je kalibrovaný ako objektívny hodnotiteľ. Rovnaký model hodnotiaci vlastný výstup sa v posudku označí. Aj iné modely z rovnakej rodiny môžu mať spoločné preferencie. Pri dôležitých záveroch použi človeka a druhého hodnotiteľa. Jednorazové CLI používa Ollamu. Trvalá služba s UI podporuje aj Anthropic, Vertex AI a Azure; platený beh sa spustí až po potvrdení v aplikácii.

### 1. Suchý plán, bez inferencie a zápisov do DB

```bash
bash docker_lab.sh run --rm judge \
  --runs rag-dev-2026-10-31-v2,no-history-dev-2026-11-01
```

Plán číta DB a vyberie 20 úspešných odpovedí, stratifikovane podľa šiestich scenárov a oboch režimov; výber uprednostňuje rôzne LLM. Nejde o presné párovanie rovnakého LLM medzi režimami ani reprezentatívny odhad kvality všetkých 480 odpovedí. Je to kontrola judge. Smoke beh zámerne nevyberáme. Technické chyby pôvodného testu judge nehodnotí ako zlú diagnózu.

### Ručné ohodnotenie tých istých 20 odpovedí

Najprv v aktualizovanej aplikácii klikni **Načítať z PostgreSQL → Hodnotenie odpovedí → Kalibrácia judge · 20 odpovedí**. Tento výber funguje aj bez spusteného judge a bez jeho DB tabuliek. Checkbox vyčistí ostatné filtre, vypne „Iba s posudkom judge“ a zapne skrytie modelov. Ohodnoť všetkých 20, päť kritérií a samostatne kritickú chybu; nepreberaj návrhy judge pred nezávislým hodnotením.

API aj worker používajú rovnaký výber: názvy dvoch behov vyššie, seed 42, veľkosť 20, iba úspešné odpovede. Suchý plán vypíše presné call_id. Do ukončenia kalibrácie nemeníme zdrojové behy, seed ani výber. `JUDGE_PILOT_RUNS` v app `.env` vie zmeniť zdrojové behy pre UI; vtedy rovnaké názvy zadaj workeru cez `--runs`. Iné veľkosti/seed worker podporuje, ale pevný UI checkbox predstavuje iba štandardný pilot 20/42.

### 2. Vytvorenie samostatných tabuliek, bez inferencie

```bash
bash docker_lab.sh run --rm judge \
  --runs rag-dev-2026-10-31-v2,no-history-dev-2026-11-01 --init-db
```

Pridá iba `llm_eval.judge_jobs` a `llm_eval.judge_evaluations`. Nevytvára novú databázu, nemení `calls`, `contexts` ani tvoje `reviews`. Existujúca schéma ostáva verzia 1. Príkaz je opakovateľný; aj `--execute` tabuľky vytvorí, ak ešte chýbajú.

### 3. Najprv dve hodnotenia

```bash
bash docker_lab.sh run --rm judge \
  --runs rag-dev-2026-10-31-v2,no-history-dev-2026-11-01 \
  --execute --max-calls 2
```

V dashboarde klikni na **Načítať z PostgreSQL**, otvor hodnotenie odpovedí, zaškrtni **Iba s posudkom judge** a nájdi panel **LLM JUDGE · NÁVRH NA KONTROLU**. Ak nevidíš posudok, vybraná odpoveď nemusí byť v pilote; presné `call_id` vypíše worker. Skontroluj krátky záver, citovaný krok a zdôvodnenie; pri prázdnych referenciách musí byť technické hodnotenie neoverené.

Počas volania na Windows skontroluj `ollama ps`: kontext má byť 16384; CPU/GPU mix si zaznamenaj. Judge používa vlastný kontext 16384 a výstupný limit 4096, oddelený od pôvodného benchmarku. Pri dlhom vstupe, neúplnom JSON alebo vyčerpanom limite sa výsledok neprijme. Kontrola počtov tokenov nevie spoľahlivo odhaliť každé orezanie promptu; pri dlhých vstupoch skontroluj aj logy Ollamy. Zmenené limity znamenajú novú konfiguráciu hodnotenia. Nespúšťaj judge súbežne s meraným benchmarkom na rovnakej 4090.

### 4. Dokončenie rovnakého pilotu

Ak prvé posudky dávajú zmysel, spusti rovnaký príkaz s vyšším stropom nových volaní:

```bash
bash docker_lab.sh run --rm judge \
  --runs rag-dev-2026-10-31-v2,no-history-dev-2026-11-01 \
  --execute --max-calls 20
```

Hotové posudky rovnakej konfigurácie preskočí. Pri dvoch úspešných predchádzajúcich volaniach pribudne najviac 18. `--max-calls` mení iba strop nových volaní, `--pilot-size` mení samotný výber. Rovnaký seed 42 a nezmenené zdrojové behy zachovajú výber. Pred dokončením pilotu neimportuj zmenenú sadu zdrojových odpovedí. Rozšírenie na všetky odpovede je až vedomý ďalší experiment cez `--pilot-size 0` a explicitný strop volaní; nespúšťame ho automaticky.

### 5. Kontrola po behu

```bash
bash docker_lab.sh run -T --rm app python - <<'PY'
from db_store import connect
with connect() as conn:
    for row in conn.execute("SELECT status,count(*) FROM llm_eval.judge_jobs GROUP BY status ORDER BY status"):
        print(row)
    print("Accepted:",conn.execute("SELECT count(*) FROM llm_eval.judge_evaluations").fetchone()[0])
PY
```

Pri prvom dokončenom pilote očakávaj 20 `completed` a 20 prijatých posudkov; ak si menil konfiguráciu alebo robil opakované pokusy, celkové počty môžu byť vyššie. `invalid` znamená neprijatý JSON/kontrakt/neúplnú generáciu. `error` znamená zlyhanie volania. Tri po sebe idúce zlyhania zastavia worker. Exit code 0 znamená úspech vykonaných volaní, nie automaticky dokončenie celého pilotu; over počty.

Dokončené, chybné aj neplatné pokusy sú uložené. Bežné opakovanie chybné pokusy preskočí; `--retry-errors` výslovne povolí nový pokus pre `error`/`invalid`. Rezervácia `running` po páde sa automaticky neopakuje: volanie už mohlo prebehnúť. Najprv over, že pôvodný worker skončil, a stav vyrieš cielene v DB; nemaž celú históriu. Jeden PostgreSQL advisory lock zabraňuje dvom týmto workerom hodnotiť súbežne. Nezastaví iné Ollama klienty.

### 6. Porovnanie s tvojimi skóre

```bash
bash docker_lab.sh run --rm judge \
  --runs rag-dev-2026-10-31-v2,no-history-dev-2026-11-01 --calibrate
```

Tento príkaz iba číta DB. Pre každé kritérium vypíše počet porovnaní, presnú zhodu, rozdiel najviac jeden bod, priemerný absolútny rozdiel a Cohenovo kappa, ak sa dá vypočítať. Osobitne vypíše prehliadnuté kritické chyby a falošné poplachy s call_id. Chýbajúce či neplatné posudky sa nedopĺňajú nulou. Hodnotenia prebraté z judge s označením v poznámke sú z nezávislej kalibrácie vylúčené. Kontroluj aj počet/hash konfigurácií, aby si nemiešal rôzne verzie.

Väčšinová zhoda na 20 odpovediach je orientačný výsledok, nie záruka spoľahlivosti. Nula prehliadnutých kritických chýb nič nehovorí o ich detekcii, ak žiadna v pilote nebola. Pri rozšírení kontroluj všetky kritické upozornenia aj náhodnú vzorku odpovedí bez upozornenia; iba kontrola výnimiek by neodhalila falošné negatíva.

## Ukladanie, použitie a kalibrácia

- `judge_jobs`: samostatná rezervácia pred inferenciou, presný vstupný paket so štyrmi poľami, hash vstupu/konfigurácie, digest modelu z Ollama tags, verzia rubriky a referencií, raw JSON odpoveď, tokeny, čas vrátane načítania, stav a prípadná chyba.
- `judge_evaluations`: iba validované posudky. Odmietnuté výstupy ostávajú v jobs na diagnostiku. Validácia kontroluje formát a citácie; negarantuje správnosť záveru.
- Judge nevidí identitu autora, pôvodnú cenu ani tvoje skóre. Prípadové dáta obsahujú iba aktuálny incident, review guidance, retrieved_ids a odpoveď. Pravidlá a schválené technické referencie sú oddelené v systémovom zadaní. Pôvodný prompt, text historických incidentov, názov modelu, cena a ľudské skóre sa neposielajú. Texty sú označené ako nedôveryhodné dáta; worker nevykonáva príkazy obsiahnuté v odpovedi. Identitu možno čiastočne odhadnúť zo štýlu.
- Nulová cena v jobs znamená iba nulový priamy lokálny API poplatok; elektrina/hardvér nie sú započítané. Tokeny a časy sa čítajú z odpovede Ollamy podľa [API dokumentácie](https://docs.ollama.com/api/chat). Neúspešné volanie s neznámym usage má cenu neznámu.
- Dashboard načíta posudky cez existujúce `/api/dataset`. Posudky sa nezapočítajú do grafov ručného skóre. Najnovší pokus zobrazí aj pri zlyhaní; staršiu úspešnú verziu automaticky nevydáva za aktuálnu.
- Tlačidlo **Prevziať návrhy do prázdnych polí** doplní iba prázdne skóre a prípadne kritickú chybu/poznámku. Nič neuloží. Existujúce ručné skóre neprepíše; do poznámky pripojí identifikátor zdroja aj vtedy, keď už obsahuje vlastný text. Človek musí návrhy skontrolovať a kliknúť na **Uložiť hodnotenie**. Prebraté skóre je asistované hodnotenie; poznámka nesie ID posudku, aby si ho nezamieňal s nezávislým ručným hodnotením.
- V pilote porovnaj judge s vlastným hodnotením aspoň pri niekoľkých odpovediach z každého scenára. Najprv si zapíš vlastný úsudok a až potom čítaj návrh judge, aby ťa neovplyvnil. Sleduj najmä prehliadnuté nebezpečné rady, falošné kritické chyby a preferovanie rozsiahlych odpovedí. Ak sa nezhodnete, oprav rubriku/podklady a urob novú verziu pilotu. Druhý LLM môže pomôcť, ale zhoda dvoch modelov nie je dôkaz technickej pravdy.

Lokálne offline kontroly: `python -m unittest -v test_judge test_database` a `node --test data.test.mjs`. Živú Docker/PostgreSQL/Ollama integráciu over vyššie uvedeným dvojvolaním na VM; bez toho nemožno tvrdiť, že je runtime overený.
