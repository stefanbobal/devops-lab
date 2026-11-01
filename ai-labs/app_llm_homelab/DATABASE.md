# PostgreSQL režim: import výsledkov a trvalé hodnotenie

**Pre zabalenie celej aplikácie do Docker image použi [DOCKER.md](DOCKER.md).**
Nasledujúce príkazy sú alternatíva pri priamom spustení cez existujúcu venv.

Schéma **llm_eval** v existujúcom PostgreSQL. Incidentové tabuľky ani vektory sa nemenia.
Import číta pôvodné manifest.json, calls/*.json, contexts/*.json a vyplnené quality_review.csv.
Results.csv neimportujeme druhýkrát: je exportom tých istých calls JSON. Pri CSV-only
behu najprv použi súborový režim aplikácie; DB import vyžaduje plné artefakty.
Pôvodné súbory sa neprepisujú a zostávajú auditným zdrojom.

## 1. Aktualizuj projekt po dokončení benchmarku

Na Ubuntu VM, v novom termináli:

```bash
cd ~/devops-lab
git pull --ff-only
cd ai-labs/code
source .venv/bin/activate
cd ../app_llm_homelab
```

Použije sa existujúci psycopg a python-dotenv z labovej venv. Nie je potrebný FastAPI,
Node ani ďalší LLM/provider SDK pre backend. PG_DSN sa načíta z existujúceho code/.env
alebo prostredia; nie je potrebné heslo kopírovať do JavaScriptu.
Voliteľný LLM_EVAL_PG_DSN má prednosť. Kód nemá zabudované predvolené heslo.
App .env slúži len na doplnenie ešte nenastavených premenných; exporty majú prednosť.
LAB_REVIEWER určuje meno hodnotiteľa, predvolene sapops.

## 2. Najprv over import bez zápisu

```bash
python db_import.py --results ../code/results
```

Vypíše nájdené behy, počty volaní, kontextov a deterministické DB ID.
Tento príkaz sa ešte nepripája k DB. Priečinky bez calls sa preskočia.
Ak chceš len dva konkrétne behy, importuj ich samostatnými príkazmi so zodpovedajúcou
cestou; import celej results zložky zahŕňa aj smoke a ďalšie nájdené behy.
V aplikácii ich potom filtruj podľa behu, aby neovplyvnili hlavné výsledky.

## 3. Vykonaj import

```bash
python db_import.py --results ../code/results --execute
```

Databázový účet musí mať právo vytvoriť schému v danej databáze a tabuľky v nej.
Pri chybe oprávnení sa import ukončí; nevypne ochrany ani nemení existujúce incidentové dáta.
Všetky zmeny importu sú v jednej transakcii. Pri konflikte sa transakcia vráti späť.
Migráciu/import serializuje transakčný advisory lock.

Opakovaný rovnaký príkaz nevytvorí duplicitné volania. Pri ďalšom importe očakávaj
inserted_calls=0 a unchanged_calls podľa pôvodného počtu. Stav pending môže prejsť na
výsledný stav, ale zmena už dokončenej odpovede, manifestu alebo kontextu import zastaví.
Opravné pokusy uchovávaj ako samostatný beh. Štyri pôvodné chyby Argonu sa importujú
ako chyby; neprepisujeme ich úspešnými odpoveďami z iného pokusu.

Vyplnené CSV hodnotenia sa importujú pod LAB_REVIEWER len vtedy, ak pre príslušné
volanie/hodnotiteľa ešte nie sú v DB. Opakovaný import neprepíše skóre z aplikácie.
Hodnotenia uložené iba v localStorage najprv exportuj do quality_review.csv pri správnom
behu a potom importuj. Prenos lokálnych skóre do DB nie je automatický.

## 4. Over počty priamo v PostgreSQL

```bash
python - <<'PY'
from db_store import connect
with connect() as conn:
    for row in conn.execute('''
        SELECT r.name, c.status, count(*)
        FROM llm_eval.runs r JOIN llm_eval.calls c ON c.run_id=r.id
        GROUP BY r.id,r.name,c.status ORDER BY r.name,c.status
    '''):
        print(*row)
    for table in ('runs','scenarios','contexts','calls','reviews'):
        from psycopg import sql
        count = conn.execute(sql.SQL('SELECT count(*) FROM llm_eval.{}').format(sql.Identifier(table))).fetchone()[0]
        print(table, count)
PY
```

Pri tvojom hlavnom vývojovom behu očakávame **476 ok + 4 error**.
No-history beh má očakávaných 60 záznamov; jeho úspešnosť treba overiť zo skutočných dát.
Smoke je samostatný beh. Celkový počet v DB závisí od importovaných priečinkov.

## 5. Spusti aplikáciu s API

Zastav pôvodný statický server na porte 8008 cez Ctrl+C v jeho termináli, ak ešte beží.
Z aktívnej labovej venv v priečinku app_llm_homelab spusti:

```bash
python api_server.py --port 8008
```

Vo Windows PowerShelli otvor alebo ponechaj SSH tunel:

```powershell
ssh -L 8008:127.0.0.1:8008 sapops@k8s-lab
```

Otvor http://127.0.0.1:8008 a klikni **Načítať z PostgreSQL**.
Výsledky číta backend priamo z DB vo VM; netreba scp ani výber Windows priečinka.
Po načítaní vidíš názvy importovaných behov a označenie PostgreSQL.
Tlačidlo Uložiť hodnotenie zapisuje do DB a po obnovení/novom načítaní sa skóre vráti.
Ak API zápis zlyhá, aplikácia nesmie oznámiť úspešné uloženie.
V databázovom režime skóre z localStorage neprepisuje skóre z PostgreSQL.
Súborový režim a demo sú naďalej dostupné; režim ukladania je viditeľne označený.

## Dáta a API

| Tabuľka | Úloha |
| --- | --- |
| runs | fingerprint + created_at, manifest a názov behu |
| scenarios | incident a guidance pre konkrétny beh |
| contexts | retrieval záznam raz, kľúč podľa pôvodného súboru |
| calls | unikátne run_id + call_id, stav a úplný JSON výsledku |
| reviews | skóre a poznámky podľa behu/volania/hodnotiteľa |

JSONB zachováva raw usage, prompty a pôvodné metriky. Relačné kľúče viažu scénar a
kontext k volaniu; ak kontext v zdrojovom priečinku chýba, väzba zostane NULL, neháda sa.
Výsledné náklady sa znovu neprepočítavajú iným cenníkom pri importe.
Chýbajúca cena je stále neznáma; lokálny nulový API poplatok sa nemení na cenu elektriny.

- GET /api/health: dostupnosť DB a schémy.
- GET /api/dataset: importované behy pre dashboard a hodnotenia aktuálneho hodnotiteľa.
- POST /api/reviews: kontrolovaný zápis skóre 0–2, kritickej chyby a poznámky.

Backend počúva iba na 127.0.0.1; prístup cez SSH tunel. Heslo zostáva na serveri.
Ide o lokálnu jedno-používateľskú aplikáciu: LAB_REVIEWER je meno, nie autentifikácia.
API nevystavuj priamo na verejný internet. Backend odmieta cudzie Origin/Host a
neposkytuje ľubovoľné súbory, SQL endpoint, mazanie dát ani nástroje vykonávajúce akcie.
Plný dataset sa načíta naraz; stránkovanie pri veľkých datasetoch je ďalšie rozšírenie.

## Testy a záloha

```bash
python -m unittest -v test_database
node --test data.test.mjs
```

Python testy sú offline; živý PostgreSQL overia import a SELECT kontrola vyššie.
Pred dôležitými zmenami zálohuj existujúcu DB bežným pg_dump postupom a uchovaj pôvodné
výsledkové priečinky. Do GitHubu necommituj .env ani svoje výsledky/DB dumpy.
