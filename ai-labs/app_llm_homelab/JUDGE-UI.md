# LLM sudca priamo z aplikácie

Stav: 1. november 2026. Záložka **LLM sudca** umožňuje vybrať lokálny aj cloudový model, pripraviť náhľad a výslovne spustiť hodnotenie. API aplikácie zapisuje úlohu do PostgreSQL; samostatný kontajner `judge` ju spracuje. Aplikácia nepotrebuje Docker socket ani cloudové kľúče. Žiadne hodnotenie sa nespustí samotným otvorením stránky alebo štartom kontajnerov.

## 1. Aktualizácia na Ubuntu VM

```bash
cd ~/devops-lab
git pull --ff-only
cd ai-labs/app_llm_homelab
bash docker_lab.sh build app judge
bash docker_lab.sh up -d app judge
bash docker_lab.sh ps
```

Týmto sa zostavia dva image. Build context je teraz rodičovský priečinok `ai-labs`, s Dockerfile v `app_llm_homelab`. Compose to nastavuje automaticky. `ai-labs/.dockerignore` povoľuje aplikačné zdroje a dve čisté benchmarkové závislosti (`llm_metrics.py`, `llm_prices.json`); `.env`, výsledky, cache a testy sa do image neposielajú. Prípadný priamy build používaj z `ai-labs` cez `docker build -f app_llm_homelab/Dockerfile ... .`.

App a worker pri štarte pridajú potrebné judge tabuľky. Existujúcich 550 odpovedí netreba znovu importovať. Pôvodné výsledky ani ručné hodnotenia sa nemenia. Worker čaká na úlohy aj bez otvoreného prehliadača a po reštarte kontajnera sa znovu pripojí na front.

## 2. Kde worker vezme modely a poverenia

Lokálne modely načíta z Windows Ollamy podľa `JUDGE_OLLAMA_HOST` v app `.env`; predvolene `http://192.168.178.25:11434`. Zjavné embedding modely sa z výberu vynechajú. Samotný zoznam modelov je neplatený metadátový dotaz, nevyvoláva generovanie.

Cloudové premenné worker štandardne načíta cez Compose z existujúceho `../code/.env`. Aplikácia tento súbor nedostáva. Ak sú poverenia zatiaľ iba exportované v termináli VM, do kontajnera sa týmto automaticky neprenesú: ulož ich do existujúcej funkčnej dotenv konfigurácie alebo nastav v app `.env` cestu `JUDGE_CLOUD_ENV_FILE` na vlastný dotenv súbor. Názvy premenných nemeníme a hodnoty nevypisujeme do UI ani logov.

| Poskytovateľ | Potrebné vo worker kontajneri |
|---|---|
| Anthropic | `ANTHROPIC_API_KEY`; voliteľne `CLAUDE_MODEL` pre Sonnet |
| Azure | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_LLM_DEPLOYMENT` |
| Vertex AI | `GCP_PROJECT`, čitateľné Google ADC/service-account poverenie; voliteľne `VERTEX_LLM_MODEL`, `VERTEX_ARGON_MODEL`, `VERTEX_LLM_LOCATION` |

Modely v cloudovom výbere zodpovedajú laboratóriu: Claude Sonnet/Haiku/Opus, Gemini Flash-Lite/Argon a nakonfigurovaný Azure LLM deployment. Mená z konfigurácie nemeníme na domnelé novšie modely. Stav **konfigurácia prítomná** nie je overenie účtu, platnosti kľúča, dostupnosti modelu ani kvóty; prvé dve výslovne spustené hodnotenia sú runtime kontrola.

Google ADC zo štandardného VM priečinka `${HOME}/.config/gcloud` sa montuje iba na čítanie do `/gcp`. Predvolená hodnota vo workeri je `GOOGLE_APPLICATION_CREDENTIALS=/gcp/application_default_credentials.json`. Ak používaš iný priečinok/súbor, nastav v app `.env`:

```dotenv
# Verejné cesty, nie samotný obsah poverenia:
GCP_ADC_DIR=/home/sapops/.config/gcloud
JUDGE_GOOGLE_CREDENTIALS=/gcp/application_default_credentials.json
# Voliteľne iný existujúci dotenv súbor s cloudovou konfiguráciou:
# JUDGE_CLOUD_ENV_FILE=../code/.env
```

Pri service-account JSON nastav `GCP_ADC_DIR` na jeho adresár a `JUDGE_GOOGLE_CREDENTIALS` na názov súboru pod `/gcp`. Súbor musí byť čitateľný pre UID používateľa spúšťajúceho `docker_lab.sh`; helper posiela do kontajnera tvoje aktuálne UID/GID. Po zmene premenných či mountov obnov worker cez `bash docker_lab.sh up -d --force-recreate judge`; rob to medzi hodnoteniami. Potom v UI klikni na **Obnoviť dostupnosť**.

Compose používa voliteľný `env_file` (`required: false`, Compose 2.24+; v našom VM bol balík 2.40.3). Chýbajúca cloudová konfigurácia zneprístupní cloudové možnosti; lokálny judge môže pracovať ďalej. [Dokumentácia Docker Compose](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/).

## 3. Postup v prehliadači

1. Obnov stránku aplikácie a klikni **Načítať z PostgreSQL**.
2. Otvor **LLM sudca**. Skontroluj **Worker online**. Ak je offline, skontroluj `bash docker_lab.sh logs --tail 50 judge` a obnov dostupnosť.
3. Vyber model sudcu a zdrojové behy. Predvolene sú vybrané hlavný RAG a no-history beh; smoke vynechávame.
4. Pre prvé spustenie nechaj **veľkosť výberu 20**, **najviac nových volaní 2** a **seed 42**. Predvolené filtre zodpovedajú kalibračnému výberu v aplikácii.
5. Klikni **Pripraviť náhľad bez volaní LLM**. Uloží sa návrh s presnými vybranými odpoveďami a konfiguráciou; generovanie sa ešte nespúšťa.
6. Skontroluj model, počty, prípadné hodnotenie vlastných odpovedí a cenu. Pri cloude potvrď platené odoslanie poskytovateľovi a klikni **Spustiť … volaní**.
7. Sleduj priebeh. Po skončení klikni **Načítať posudky do aplikácie**. Otvorí sa hodnotenie odpovedí s filtrom **Iba s posudkom judge**. Posudky majú vlastný panel, pôvodné ručné skóre ostáva oddelené.

Ak prvé dve hodnotenia dávajú zmysel, nastav strop nových volaní na 20 a priprav nový náhľad pri rovnakých ostatných parametroch. Hotové posudky rovnakej konfigurácie sa preskočia; pri dvoch hotových ostáva najviac 18 nových volaní. Zmena modelu, rubriky, dátumu cenníka, kontextu či výstupného limitu znamená inú konfiguráciu a môže vytvoriť nové posudky. UI preto vždy ukazuje náhľad počtu nových volaní.

## 4. Parametre a ich význam

| Parameter | Význam |
|---|---|
| Model sudcu | Jeden konkrétny model/deployment pre celý beh. Lokálne modely majú zaznamenaný digest z Ollamy. |
| Zdrojové behy | Už importované odpovede v DB; pôvodný benchmark sa neopakuje. |
| Veľkosť výberu | Seedovaný výber vyvažovaný podľa scenára/režimu a modelov; 0 = všetky úspešné odpovede z vybraného rozsahu. |
| Najviac nových volaní | Strop generovaní pre toto spustenie, nezávislý od veľkosti výberu. |
| Výstupný limit | Billed output limit podľa API vrátane reasoning, kde ho poskytovateľ započítava. Nedostatok priestoru môže spôsobiť neúplný/neplatný JSON. |
| Timeout | Čas pre jedno volanie; zastavenie v UI už odoslané volanie nepreruší. |
| Rozpočet USD | Kontrola plánovacích odhadov pred ďalšími cloudovými volaniami a známych nákladov po nich; nie garantovaný limit účtu. Pri lokálnom modeli je pole vypnuté. |
| Dátum cenníka | Vyberie platnosť sadzieb zo zdieľaného `code/llm_prices.json`. Predvolený dátum je deň v Europe/Prague. |
| Seed | Stabilizuje výber a posiela sa Ollame; cloudové odpovede nezaručuje deterministické. |
| Kontext Ollamy | Explicitné `num_ctx`; vypnuté pri cloude. Musí pokryť prompt aj generovanie. |
| Limit chýb za sebou | Po toľkých error/invalid za sebou sa beh zastaví. |
| Scenáre, hodnotené modely, režimy | Voliteľné filtre pred výberom. Prázdny výber = všetky; pri viacnásobnom výbere používaj Ctrl/Cmd. Toto sú modely pôvodných odpovedí, nie model sudcu. |
| Opakovať error/invalid | Výslovne povolí nový pokus pre chybný posudok. `running` ani `completed` sa automaticky neopakujú. |
| Povoliť neznámu cenu | Umožní beh aj bez spoľahlivého cenového odhadu; neznáme náklady sa nesčítajú ako nula. |

Cloud používa nastavenie sampling poskytovateľa, Ollama temperature 0. Univerzálny thinking prepínač neposielame neoverene všetkým modelom. Rubrika, schválené referencie a JSON kontrakt sú verzované súbory; z UI nemožno poslať ľubovoľnú cestu, príkaz, serverový URL ani cloudový kľúč.

## 5. Čo presne znamená cena

Jednotkové ceny preberáme z benchmarkového cenníka; sú to používateľom dodané odhady, nie nezávisle overené kontraktné ceny. Argon pred 1.12.2026 zostáva `estimated_future_rate` podľa predchádzajúcej dohody. Rozličné modely a deploymenty musia mať vlastný presný kľúč cenníka.

Pred volaním nemáme skutočné token usage. Náhľad počíta **plánovací scenár**, ktorý predpokladá počet vstupných tokenov rovný počtu UTF-8 bajtov systémového zadania a prípadových dát a plný výstupný limit. Je to zreteľne označený orientačný odhad, nie meranie ani matematicky garantovaná horná hranica faktúry. Pri cached/creation tokenoch a poskytovateľskom spracovaní sa môže líšiť. Presné modelové tokenizery tento náhľad nepoužíva.

Po volaní ukladáme poskytovateľom vykázané input/output/cached/reasoning tokeny a podľa nich odhad ceny. Azure reasoning sa nepričíta druhýkrát k completion tokens; Vertex thoughts sa započítajú k viditeľnému výstupu. Neznáma cache cena zostáva neznáma. Sieťovo zlyhané volanie mohlo byť spoplatnené bez dostupných usage údajov. Pri neznámej cene worker predvolene zastaví pred ďalším volaním. Nula pri Ollame znamená iba nulový priamy API poplatok; GPU a elektrina nie sú ocenené.

Automatické SDK opakovania sú vypnuté; pri chybe nevzniká tiché ďalšie platené generovanie. Adaptéry vychádzajú z fungujúceho benchmarku a oficiálnych SDK: [OpenAI Python](https://developers.openai.com/api/reference/python), [Anthropic Python](https://github.com/anthropics/anthropic-sdk-python), [Google Gen AI Python](https://googleapis.github.io/python-genai/), [Ollama API](https://docs.ollama.com/api/chat).

## 6. Priebeh, zastavenie a reštart

Úloha prechádza `draft → queued → running → completed/failed/cancelled`. `completed` znamená ukončenie daného spustenia do jeho stropu nových volaní, nie nutne všetky odpovede z celého datasetu. Položky mimo stropu alebo po zastavení majú `not_run`. `invalid` posudky neprešli kontraktom; `error` je zlyhanie volania. V histórii sa zobrazia počty, náklady a posledné volania s konkrétnymi chybami.

**Zastaviť po aktuálnom volaní** nastaví požiadavku v DB. Už odoslané cloudové volanie môže byť účtované a lokálna inferencia sa dokončí. Nezabíjame kontajner ani nepredstierame okamžité zrušenie poskytovateľskej operácie. Opakované kliknutie na spustenie tej istej úlohy je idempotentné.

Po páde workeru sa predchádzajúce `running` dávky označia ako prerušené. Rozpracované `judge_jobs.running` ostanú zachované a automaticky sa neopakujú. Po kontrole možno vytvoriť nový náhľad: dokončené/neisté volania sa preskočia. Dvojica PostgreSQL advisory lockov chráni pred dvoma service workermi a pred súbehom s CLI judge; iných Ollama klientov nezamyká.

Worker publikuje heartbeat každých 10 sekúnd a inventár modelov približne každú minútu. UI obnovuje iba stavové DB dotazy každé 4 sekundy, pokiaľ je záložka otvorená a stránka viditeľná; toto nie sú modelové volania.

## 7. Databáza a API

| Objekt | Úloha |
|---|---|
| `judge_jobs`, `judge_evaluations` | Pôvodné pokusy a validované posudky jednotlivých odpovedí. |
| `judge_batches` | Nastavenia, zamrznutý konfiguračný/cenový snapshot, náhľad a stav spustenia. |
| `judge_batch_items` | Presné vybrané odpovede, časti vstupu a priebeh každej položky; odkaz na samostatný job. |
| `judge_worker_state` | Verejný inventár bez kľúčov a heartbeat workeru. |

Nové routes: GET `/api/judge/options`, GET `/api/judge/batches`; POST `/api/judge/plan`, `/api/judge/start`, `/api/judge/stop`. POST vyžaduje lokálny same-origin Host/Origin a JSON do 64 KiB. Modely sú povolené len z inventára workeru, nastavenia majú pevné hranice a cloudové spustenie vyžaduje výslovné potvrdenie. HTTP server nevykonáva shell príkazy ani nesprístupňuje Docker socket. Prístup zostáva cez localhost/SSH tunel, bez verejného nasadenia a bez novej autentifikácie.

Judge zostáva pomocný hodnotiteľ: nemení ručné skóre automaticky. Bez schválených technických referencií necháva technickú správnosť neoverenú. Pri vstupe obmedzenom na incident/guidance/ID/odpoveď neoverí obsah historickej citácie, iba prítomnosť ID a argumentáciu odpovede. Kritické pravidlá C1–C4 a rozlíšenie dôkazov/neistoty sú v [JUDGE.md](JUDGE.md).

## 8. Overenie implementácie

Offline kontroly:

```bash
python -m unittest -v test_judge_control test_judge test_database
node --test data.test.mjs
# Voliteľne s dostupným Playwright a Edge/Chromium:
node test_judge_ui.cjs
```

Unit testy používajú simulované DB/provider objekty; browser test simuluje HTTP odpovede. Overujú náhľad bez inferencie, cloudové potvrdenie, zastavenie, ochranu pred duplicitným spustením, nezmenené ručné skóre, účtovanie tokenov a mobilný layout. Nie je to živý Docker/PostgreSQL/cloud integračný test. Runtime kontrolu na VM vykonaj prvými dvoma výslovne spustenými hodnoteniami; počas implementácie sa žiadne platené volania nespúšťali.

## Oprava validácie technických tvrdení

Validátor `judge-validation-v3` zachová inak platný posudok, ak sudca označí technickú správnosť ako supported/incorrect bez skutočnej schválenej referencie. Toto pole zníži na unverified, odstráni nepodloženú referenciu a uloží viditeľné validation_warnings a presný záznam úpravy. Pôvodný raw_output ostáva nezmenený. Ide o označenie neistoty, nie o potvrdenie správnosti príkazu. Kritické zistenia, kontrola doslovných citácií odpovede a ostatné štrukturálne kontroly ostávajú zachované. Nepodložené pozitívne celkové odporúčanie sa zmení na needs_review.

Staré invalid pokusy ostávajú v histórii. Po aktualizácii oboch image priprav nový náhľad a spusti opäť najviac 2 volania. Nová verzia validátora/kontraktu je súčasťou auditu konfigurácie, takže pôvodné dva chybné pokusy neblokujú nový pokus a netreba ich mazať. Náhľady vytvorené pred aktualizáciou sa nevykonajú s inými pravidlami; treba ich pripraviť nanovo.

## Typovaný výstup sudcu a rozbalené panely

Verzia `judge-validation-v4` posiela do Ollamy celú typovanú JSON schému namiesto samotného `format: json`. Pole critical_error je v schéme boolean, všetky skóre a kritické zistenia sú povinné polia. Bez schválených referencií je technická klasifikácia obmedzená na unverified. Aj prompt vysvetľuje rozdiel medzi skutočnou hodnotou a popisom typu. Kontroly zmyslu, doslovných citácií a C1–C4 ostávajú vo validátore; neznámu hodnotu kritickej chyby nekonvertujeme na false. Typovaný formát rieši štruktúru, nie vecnú správnosť posudku. [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

Priebeh neprekresľuje nezmenenú históriu. Pri zmenách zachová otvorenie aj zatvorenie panelov podľa stabilnej identity dávky/volania. Pri každom poslednom volaní možno rozbaliť Pôvodný výstup sudcu a načítať uložený raw_output cez lokálny GET /api/judge/output?id=UUID. Tento krok iba číta už uložený text, nespúšťa LLM; text sa vkladá bezpečne ako text a zostáva načítaný aj pri ďalšej obnove. Funguje aj pre staré invalid pokusy.

## Platné posudky a história pokusov pri konkrétnej odpovedi

Tlačidlo Načítať posudky do aplikácie iba číta uložené výsledky z PostgreSQL, neimportuje ich znovu a nespúšťa model. Filter Iba odpovede s platným posudkom judge vyberá iba odpovede, pri ktorých existuje completed pokus s použiteľným posudkom. Samotný invalid/error/running pokus na zaradenie nestačí.

Pri odpovedi sa predvolene zobrazí jej najnovší platný posudok, nie automaticky prvý alebo posledný ľubovoľný pokus. Výber Posudok pre túto odpoveď LLM ukazuje model sudcu, dátum/čas v Europe/Prague, stav a ID jednotlivých pokusov. Ak je platný posudok starší než posledný neúspešný pokus, rozhranie to výslovne oznámi. Neplatné pokusy ostávajú dostupné na kontrolu, ale ich skóre nemožno prevziať. Prevzatie návrhov vždy používa práve vybraný platný posudok. Prepnutie histórie nemení neuložené ručné skóre.

Platný posudok inej odpovede ani iného behu sa nepriraďuje automaticky: rovnaký názov scenára nestačí. Identitou je konkrétna odpoveď podľa run_id a call_id. Ak odpoveď nemá platný pokus, UI to uvedie a nedosadí hodnotenie z inej odpovede. Staré chybné pokusy netreba mazať.

## Všeobecná rubrika bez predpísaných scenárových riešení

Od `sap-oracle-general-v3` sa do systémového zadania sudcu posielajú z rubriky výlučne sekcie general, critical_error_rules a score_anchors. Sekcia scenarios a jej first_checks/later_checks/avoid boli odstránené zo súboru aj z generovania zadania. Všeobecné pravidlá sa skutočne vkladajú do promptu, nie iba ukladajú do konfigurácie. Judge nedostáva predpísaný postup investigácie pre konkrétny incident a nový scenár nevyžaduje vlastný kľúč odpovedí.

Prípadové dáta ostávajú aktuálny incident, reviewer guidance, dodané ID a odpoveď. Identifikátor prípadu slúži na rozsah explicitného pravidla C2, nie ako zdroj riešenia. Jazyk a obsah troch používateľom určených sekcií zostali zachované. Systémová správa zabezpečuje úlohu hodnotiteľa, nedôveryhodnosť dát a typovaný formát, neobsahuje ďalší skrytý diagnostický kľúč.

Nová verzia a zmenené zadanie vstupujú do hash konfigurácie. Existujúce posudky v2 sa neprepisujú ani automaticky neprehodnocujú. Hodnotenia podľa v2 a v3 treba interpretovať oddelene. Nový náhľad po zostavení oboch image použije všeobecnú rubriku; staré náhľady sú blokované kontrolou zmeneného systémového zadania pred novým volaním.
