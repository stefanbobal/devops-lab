# Docker image: dashboard + API + PostgreSQL import

Toto je odporúčaný spôsob nasadenia. **Jeden image obsahuje HTML/CSS/JavaScript aj
Python API.** Používa existujúci kontajner pgvector, nevytvára druhú databázu.
Image sa vytvorí lokálne na Ubuntu; zatiaľ ho nepublikujeme do registry.

**LLM sudca:** druhý image/služba `judge` teraz beží ako trvalý worker frontu. Z aplikácie vieš vybrať lokálny aj cloudový model a spustiť posudky; štart kontajnera sám žiadne hodnotenie nespúšťa. Postup a cloudové poverenia sú v [JUDGE-UI.md](JUDGE-UI.md). Build context sa presunul do `ai-labs`; Compose ho nastaví automaticky.

## 1. Jednorazové nastavenie

Po dokončení oboch benchmarkov v Ubuntu:

```bash
cd ~/devops-lab
git pull --ff-only
cd ai-labs/app_llm_homelab
cp -n .env.example .env
nano .env
```

V app `.env` nastav **existujúce** meno DB, používateľa a heslo, ktoré už fungujú v labe.
Príklad tvaru pripojenia (heslo nahraď vlastným, nevypisuj ho do zdieľaných logov):

```dotenv
LLM_EVAL_PG_DSN=host=pgvector port=5432 dbname=postgres user=postgres password=YOUR_EXISTING_PASSWORD
LAB_REVIEWER=sapops
LLM_RESULTS_DIR=../code/results
```

Host musí byť **pgvector**: localhost v app kontajneri označuje app kontajner, nie DB.
Ak heslo obsahuje medzery/špeciálne znaky, použi správne citovaný libpq DSN alebo
percent-encoded PostgreSQL URI. .env sa necommitne a nebalí do image.
Do app kontajnera sa posiela iba DB pripojenie a meno hodnotiteľa, nie cloudové API kľúče.

## 2. Vytvor image

```bash
bash docker_lab.sh build
```

Helper overí bežiaci kontajner `pgvector`, vytvorí sieť `llm-homelab`, ak chýba,
a pripojí k nej existujúci pgvector. Jeho pôvodnú sieť/volume nemení ani ho nereštartuje.
App kontajner pripojí do tej istej siete. Kontajner používa UID/GID aktuálneho používateľa,
aby dokázal čítať jeho výsledky; nevyžaduje chmod 777. Docker príkazy spúšťaj ako sapops,
ktorý už má právo používať Docker. Tento krok vyžaduje prístup k registru a PyPI pri build-e.

## 3. Over výsledky bez zápisu

```bash
bash docker_lab.sh run --rm app python db_import.py --results /results
```

`/results` je read-only mount pôvodného `ai-labs/code/results`.
Vypíšu sa behy a počty; databáza sa pri dry run neotvára.
Pred importom over názvy hlavných behov, napríklad RAG 480 volaní a no-history 60.
Smoke behy sa importujú tiež ako samostatné behy, ak sú pod týmto priečinkom.
Len jeden beh importuješ napríklad cez `--results /results/rag-dev-2026-10-31-v2`.

## 4. Naimportuj do databázy

```bash
bash docker_lab.sh run --rm app python db_import.py --results /results --execute
```

Vytvorí schému `llm_eval` a tabuľky runs/scenarios/contexts/calls/reviews.
DB účet potrebuje právo vytvoriť schému. Incidentové tabuľky sa nemenia.
Import je transakčný a opakovateľný bez duplikátov. Rovnaký dokončený výsledok sa
neprepíše iným obsahom; pri konflikte import zlyhá a vráti transakciu späť.
Existujúce DB hodnotenia sa neprepíšu starším CSV. Celý postup a pravidlá importu
sú v [DATABASE.md](DATABASE.md).

Kontrola uložených stavov priamo v DB cez ten istý image:

```bash
bash docker_lab.sh run --rm -T app python - <<'PY'
from db_store import connect
with connect() as conn:
    for row in conn.execute('''
        SELECT r.name,c.status,count(*)
        FROM llm_eval.runs r JOIN llm_eval.calls c ON c.run_id=r.id
        GROUP BY r.id,r.name,c.status ORDER BY r.name,c.status
    '''):
        print(*row)
PY
```

Pre hlavný RAG beh očakávame **476 ok + 4 error** podľa pôvodného testu.
No-history skontroluj podľa jeho skutočného dokončeného výstupu.

## 5. Spusti aplikáciu

Zastav pôvodný statický/Python server na porte 8008 cez Ctrl+C v jeho termináli,
ak ešte beží. Potom:

```bash
bash docker_lab.sh up -d
bash docker_lab.sh ps
bash docker_lab.sh logs --tail 50 app
curl --fail http://127.0.0.1:8008/api/health
```

Očakávaj kontajner Up/healthy a JSON `ok: true`. Ak DB/schéma nie je dostupná,
API sa nespustí; pozri logs. Pri chýbajúcej schéme najprv vykonaj import.
Logy neobsahujú zámerne celé DSN/heslo. `docker compose config` môže rozbaliť
hodnoty prostredia — jeho výstup nezdieľaj bez redakcie.

Vo Windows otvor SSH tunel (ak ho už máš, nemusíš ďalší):

```powershell
ssh -L 8008:127.0.0.1:8008 sapops@k8s-lab
```

V prehliadači otvor **http://127.0.0.1:8008** a klikni **Načítať z PostgreSQL**.
Výsledky netreba kopírovať do Windowsu. Skóre sa v tomto režime ukladá do DB.
Over uloženie jedného hodnotenia: ulož, obnov stránku, znova načítaj DB a prezri rovnakú odpoveď.

## Prevádzka

```bash
# Po pridaní ďalších výsledkov zopakuj import; existujúce volania sa nezdvojnásobia.
bash docker_lab.sh run --rm app python db_import.py --results /results --execute

# Po aktualizácii aplikácie:
bash docker_lab.sh build
bash docker_lab.sh up -d

# Zastavenie iba app služby, nie pgvector:
bash docker_lab.sh down
```

Dáta sú v existujúcom PostgreSQL volume a v pôvodných JSON/CSV, nie vo vrstve app image.
App má read-only filesystem, read-only results mount a hostiteľský port viazaný len na
127.0.0.1. V kontajneri API počúva na 0.0.0.0, aby fungovalo publikovanie portu;
neznamená to verejné vystavenie VM. Ide o lokálnu aplikáciu bez verejnej autentifikácie.
Compose nemá závislosť, ktorá by vytvárala alebo mazala existujúci pgvector volume.

## Overenie pri príprave

Offline testy importéra a UI sú súčasťou projektu. Živý build/DB import je potrebné
vykonať vyššie uvedenými príkazmi na VM s Dockerom; príprava kódu sama neznamená,
že výsledky už boli naimportované do tvojej DB.
