# Runbook: RAG / LLM test — sobota 31. októbra 2026

**Prostredie:** Ubuntu VM `sapops@k8s-lab`, repozitár `~/devops-lab`,
Python venv `~/devops-lab/ai-labs/code/.venv`.
Príkazy sú pre **Bash na Ubuntu**, okrem osobitne označenej kontroly Windows GPU.

**Revízia 31.10.:** explicitné Ollama num_ctx, príprava kontextov pred LLM a poradie podľa modelu.
Staré behy majú iný manifest/kód; pokračuj v nich iba so starou verziou. Pre túto revíziu sú priečinky označené v2.

**Cieľ dňa:** overiť celý tok a porovnať modely na **6 vývojových scenároch**.
Finálnych 24 návrhov zatiaľ nepoužívať na ladenie.
Úspešný technický beh neznamená správnu investigáciu — tú hodnotíme ručne.

## 0. Rozsah, očakávané počty a pravidlá

| Fáza | Retrieval | LLM volania |
| --- | ---: | ---: |
| Kontrola DB a zoznamu Ollama | 0 | 0 |
| Kontrola retrieval všetkých profilov na jednom vývojovom scenári | 8 | 0 |
| Smoke test jedného scenára, Gemini embedding, všetky LLM | 1 | 10 |
| Vývojový RAG test: 6 × 8 × 10, jedno opakovanie | 48 | 480 |
| Voliteľná kontrola bez histórie: 6 × 10 | 0 | 60 |
| Neskorší finálny test: 24 × 8 × 10 | 192 | 1 920 |

Počty platia pri dostupnosti všetkých profilov a bez chýb.
Query embeddingy a cloudové LLM volania sú spoplatnené. Retrieval probe a smoke test sú
osobitné behy; ich kontexty sa do hlavného testu neprenášajú.

- Nevytvárať znovu embeddingy 200 incidentov a nemenit ich tabuľky počas testu.
- Neobnovovať/ladiť thresholdy; používať `thresholds_FROZEN.json`.
- Nespúšťať súbežne iné GPU benchmarky. Zaznamenať hardvér a zaťaženie.
- Po začatí jedného behu nemeniť kód, balíky, prompty, ceny ani scenáre.
- Cloudové limity/ceny sú odhady; `--max-calls` nie je dolárový budget.
- `rag.py` je iba samostatná ukážka; na maticu používame `rag_test.py`.
- Pokračovať na ďalšiu fázu až po splnení jej kontroly.

## 1. Pripojenie, kód a venv

Na Ubuntu:

```bash
cd ~/devops-lab
git status --short
git branch --show-current
git remote get-url origin
```

**Kontrola:** správny repozitár `stefanbobal/devops-lab`, vetva `master`.
Ak sú rozpracované zmeny, najprv ich preskúmať; nepoužívať `reset --hard`.

```bash
git pull --ff-only
cd ~/devops-lab/ai-labs/code
source .venv/bin/activate
python --version
python -c 'import sys; print(sys.executable)'
python rag_test.py --help
```

**Kontrola:** Python patrí do tejto `.venv`; CLI obsahuje `--scenarios`,
`--max-calls`, `--resume`, `--execute`, `--pricing-date`.

Pre dlhý beh je vhodný `tmux`, ak je na VM dostupný:

```bash
command -v tmux
```

Ak je dostupný, otvor `tmux new -s rag-20261031` a v jeho okne znova vykonaj
`cd ~/devops-lab/ai-labs/code` a `source .venv/bin/activate`.
Všetky ďalšie kroky vykonávaj v tom istom okne. Odpojenie: Ctrl+B, potom D.
Návrat: `tmux attach -t rag-20261031`.
Bez tmux nechaj SSH reláciu otvorenú; odpojenie môže prerušiť beh.

## 2. Konfigurácia — bez vypisovania tajných kľúčov

Nastav iba verejné identifikátory; existujúce kľúče, GCP projekt, DB a OLLAMA_HOST
ponechaj z funkčnej konfigurácie. Nesourceuj naslepo celý `.env` ako shell skript;
`config.py` ho načíta cez python-dotenv.

```bash
export EMBED_PROFILE=nomic
export LLM_PROFILE=gemma
export VERTEX_LLM_MODEL=gemini-3.1-flash-lite
export VERTEX_ARGON_MODEL=gemini-4-argon
export VERTEX_LLM_LOCATION=global
export AZURE_OPENAI_LLM_DEPLOYMENT=gpt-5-mini
export PYTHONUNBUFFERED=1
set -o pipefail
mkdir -p results/preflight-2026-10-31-v2
```

Exporty platia pre aktuálny terminál a majú prednosť pred `.env`.
Flash-Lite je nové LLM, Gemini embedding zostáva `gemini-embedding-001`.
Ak máš zámerne iný názov Azure deploymentu, použi jeho skutočný názov a uprav
príslušný kľúč cenníka pred začatím testu.

```bash
python - <<'PY'
import os
from config import LLMS, MODELS, GCP_PROJECT, VERTEX_LLM_LOCATION
for key in ("ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"):
    assert os.getenv(key, "").strip(), f"Missing: {key}"
endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
assert not endpoint.endswith(("/responses", "/chat/completions")), "Use resource root or /openai/v1/"
print("Required cloud settings: present (values hidden)")
print("GCP project:", GCP_PROJECT, "| LLM location:", VERTEX_LLM_LOCATION)
for profile, spec in LLMS.items():
    print("LLM", profile, spec["provider"], spec["name"])
for profile, spec in MODELS.items():
    print("EMBED", profile, spec["provider"], spec["name"], spec["dim"])
assert len(LLMS) == 10 and len(MODELS) == 8
assert LLMS["gemini"]["name"] == "gemini-3.1-flash-lite"
assert LLMS["gemini_argon"]["name"] == "gemini-4-argon"
print("Configuration OK")
PY
```

**Kontrola:** 10 LLM profilov, 8 embedding profilov; žiadny vypísaný API kľúč.
Samotná prítomnosť konfigurácie nepotvrdzuje funkčné prihlásenie — to overia volania nižšie.

## 3. Offline kontroly a záznam verzií

```bash
python -m pip check
python -m unittest -v test_rag_benchmark
```

**Kontrola:** bez konfliktov balíkov, **20 testov, OK** podľa tejto verzie kódu.
Testy používajú simulované odpovede; nevolajú cloud ani databázu.

```bash
python - <<'PY'
import importlib
from google.genai import types
for module in ("numpy", "dotenv", "psycopg", "pgvector.psycopg", "ollama", "anthropic", "openai", "google.genai"):
    importlib.import_module(module)
types.HttpOptions(timeout=180000, retry_options=types.HttpRetryOptions(attempts=1))
print("Imports and Vertex retry options OK")
PY
git rev-parse HEAD > results/preflight-2026-10-31-v2/git-head.txt
git status --short > results/preflight-2026-10-31-v2/git-status.txt
python -m pip freeze > results/preflight-2026-10-31-v2/packages.txt
sha256sum config.py providers.py search.py rag.py rag_prompt.py rag_test.py llm_metrics.py rag_scenarios.json thresholds_FROZEN.json llm_prices.json > results/preflight-2026-10-31-v2/input-sha256.txt
```

**Pri chybe:** zastaviť. Opraviť len konkrétny chýbajúci/nekompatibilný balík v tejto venv,
potom kontroly zopakovať. Pri chýbajúcom `HttpRetryOptions` aktualizovať `google-genai`
pred začatím behov a zaznamenať novú verziu. Nerobiť plošný upgrade počas benchmarku.

### Thresholdy a scenáre

```bash
python - <<'PY'
import json
from pathlib import Path
from config import MODELS
from rag import load_threshold
from rag_test import validate_scenarios
from llm_metrics import validate_prices
expected = {"nomic": .60, "nomic_prefix": .65, "bge": .60, "qwen": .60,
            "qwen_instr": .40, "qwen8": .55, "gemini": .65, "azure": .40}
for p in MODELS:
    value = load_threshold(p, Path("thresholds_FROZEN.json"))
    assert value == expected[p], (p, value)
    print(p, value)
scenarios = validate_scenarios(json.loads(Path("rag_scenarios.json").read_text()))
assert len(scenarios) == 6
validate_prices(json.loads(Path("llm_prices.json").read_text()))
for s in scenarios:
    assert s.get("review_guidance")
    print(s["id"], "domain=", s.get("domain"), "db_type=", s.get("db_type"))
print("6 development scenarios; thresholds and prices structurally valid")
PY
```

Nesúlad thresholdu neopraviť podľa tejto tabuľky naslepo; najprv zistiť, prečo sa líši
schválený frozen súbor. Validácia cien neoveruje pravdivosť dodávateľského cenníka.

## 4. Databáza: osem tabuliek, rozmery, rovnakých 200 incidentov

Nasledujúci blok robí iba SELECT. Používa existujúci `PG_DSN` z configu;
heslo nevypisuje. Nemá vytvárať ani meniť tabuľky.

```bash
python - <<'PY'
import json
from pathlib import Path
import psycopg
from psycopg import sql
from config import MODELS, PG_DSN
baseline = None
report = {}
required = {"incident_id", "sid", "domain", "db_type", "incident_date", "title",
            "evidence", "root_cause_status", "resolution", "embedding"}
with psycopg.connect(PG_DSN, connect_timeout=10) as conn:
    conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET statement_timeout = '30s'")
    for profile, spec in MODELS.items():
        table = sql.Identifier("incident_memory_" + profile)
        cursor = conn.execute(sql.SQL("SELECT * FROM {} LIMIT 0").format(table))
        columns = {c.name for c in cursor.description}
        assert required <= columns, (profile, "missing columns", required - columns)
        rows = conn.execute(sql.SQL(
            "SELECT incident_id, vector_dims(embedding) FROM {}").format(table)).fetchall()
        ids = {str(r[0]) for r in rows}
        dims = sorted({r[1] for r in rows if r[1] is not None})
        assert len(rows) == 200 and len(ids) == 200, (profile, len(rows), len(ids))
        assert all(r[1] == spec["dim"] for r in rows), (profile, dims)
        if baseline is None:
            baseline = ids
        assert ids == baseline, (profile, "different incident IDs")
        filters = conn.execute(sql.SQL(
            "SELECT domain, db_type, count(*) FROM {} GROUP BY domain, db_type ORDER BY domain, db_type"
        ).format(table)).fetchall()
        report[profile] = {"rows": len(rows), "dims": dims, "filters": filters,
                           "incident_ids": sorted(ids)}
        print(profile, "rows=", len(rows), "dims=", dims, "filters=", filters)
Path("results/preflight-2026-10-31-v2/database-check.json").write_text(
    json.dumps(report, indent=2, default=str))
print("Database structure, row counts, dimensions and IDs OK")
PY
```

**Kontrola:** každá tabuľka 200 unikátnych incidentov a rozmery podľa configu.
Vypísané filtre musia obsahovať hodnoty používané scenármi (napríklad `backup`, `HANA`).
Táto kontrola nepotvrdzuje pravdivosť obsahu ani pôvod embeddingov.
Ak narazíš na chybu názvu tabuľky, dimenzie či stĺpca, neopravuj ju obídením kontroly;
najprv zosúlaď databázu s pôvodným embedding experimentom.

Polia `evidence` a `resolution` sú obsah syntetických dát, nie dôkaz, že už prebehla
skutočná investigácia. Ich význam skontrolujeme vo vzorke v kroku 6.

## 5. Ollama na správnom hoste a GPU

Kontrolu rob **z Ubuntu**, aby si overil rovnakú cestu, ktorú používa runner.
`ollama list` na Windows samo osebe nepotvrdzuje dostupnosť modelov z VM.
Skript načíta existujúci `OLLAMA_HOST`; ak chýba, klient používa svoj predvolený localhost.

```bash
python - <<'PY'
import json
from pathlib import Path
import config
import ollama
client = ollama.Client(timeout=30)
listing = client.list().model_dump(mode="json")
models = listing.get("models", [])
installed = {(m.get("model") or m.get("name")): m for m in models}
normalize = lambda name: name if ":" in name else name + ":latest"
wanted = {s["name"] for s in list(config.LLMS.values()) + list(config.MODELS.values())
          if s["provider"] == "ollama"}
details = {}
for name in sorted(wanted):
    canonical = normalize(name)
    assert canonical in installed, f"Model not found on VM's Ollama endpoint: {name}"
    info = client.show(name).model_dump(mode="json")
    details[name] = {"listed": installed[canonical], "details": info.get("details"),
                     "parameters": info.get("parameters"), "model_info": info.get("model_info")}
    print(name, installed[canonical].get("digest"), info.get("details"))
Path("results/preflight-2026-10-31-v2/ollama-models.json").write_text(
    json.dumps(details, indent=2, default=str))
print("Required local models present")
PY
```

**Kontrola:** dostupné štyri lokálne LLM a embedding modely; uložený digest a kvantizácia.
Samotný zoznam ešte neoveruje GPU inference.

Na **Windows hoste s RTX 4090**, v PowerShelli, pred testom a počas lokálneho volania:

```powershell
nvidia-smi
ollama ps
```

Zaznamenať GPU, VRAM a spôsob spracovania. Ak Ollama používa CPU alebo CPU/GPU mix,
výsledok tak označiť; neprezentovať ho ako čisté GPU meranie.
Nespúšťať zbytočne druhý model mimo benchmarku.

### Kontext, thinking a timeout pred hlavným behom

- Meraný adaptér teraz explicitne posiela `num_ctx=8192`; nespolieha sa na serverový default.
  Aktuálne defaulty Ollamy sa môžu líšiť podľa verzie a VRAM. Overiť `CONTEXT` v `ollama ps`
  počas volania, nie odhadovať hodnotu.
- Kontext musí pokryť vstupný prompt aj generovanie. Podmienka `num_ctx > output cap`
  je iba základná kontrola, nie presný tokenizer ani záruka proti orezaniu.
  Skontrolovať `input_tokens`, veľkosť promptu a logy servera.
- Väčší kontext zvyšuje pamäťové nároky. Pre porovnanie označené ako čisto GPU
  vyžadovať `100% GPU`; ak je CPU/GPU mix, zaznamenať ho a podľa potreby
  upraviť experiment pred hlavným behom.
- Pri Qwen prezrieť `output_tokens`, `finish_reason` a skutočný text odpovede.
  Limit takmer vyčerpaný a neúplná/prázdna odpoveď sú dôvod na diagnostiku thinking budgetu,
  nie dôkaz slabého modelu. Nenastavovať neoverený think parameter univerzálne.
- Ak smoke ukáže nedostatočný output cap, zvoľ pre nový porovnateľný beh napríklad
  `--max-output-tokens 8192 --ollama-num-ctx 16384`; znovu over GPU/VRAM.
  Potrebný kontext závisí aj od reálneho vstupu.
- Timeout 300 s je počiatočné nastavenie. Pri CPU offloade alebo dlhej generácii nemusí stačiť.
  Zmenu urob pred hlavným behom, zopakuj smoke a používaj ju konzistentne.
- Túto explicitnú konfiguráciu používa `rag_test.py`; jednoduchý `rag.py` a
  `check_cloud.py` naďalej používajú pôvodný jednoduchý provider.

Oficiálne podklady: [Ollama context length](https://docs.ollama.com/context-length),
[Ollama chat options a timing](https://docs.ollama.com/api/chat).

## 6. Retrieval probe: jeden vývojový scenár cez všetkých 8 profilov

**Toto už volá embedding modely**, vrátane cloudových; nevolá žiadny LLM.
Súčasne vytvorí jedno-scenárový súbor pre ďalší smoke test.

```bash
python - <<'PY'
from pathlib import Path
from config import MODELS
from rag import load_threshold
from rag_test import read_json, write_json, run_worker
out = Path("results/preflight-2026-10-31-v2")
scenario = read_json("rag_scenarios.json")[0]
write_json(out / "smoke-scenario.json", [scenario])
failed = []
for profile in MODELS:
    threshold = load_threshold(profile, "thresholds_FROZEN.json")
    result = run_worker({"operation": "retrieve", "scenario": scenario,
                         "top_k": 3, "threshold": threshold},
                        profile, "gemma", 300)
    write_json(out / ("retrieval-" + profile + ".json"), result)
    print("\nPROFILE:", profile, "| STATUS:", result["status"], "| THRESHOLD:", threshold)
    if result["status"] != "ok":
        failed.append(profile)
        print(result.get("error"))
        continue
    for row in result["candidates"]:
        print(row["incident_id"], round(row["similarity"], 4), row["title"])
    print("SELECTED:", [r["incident_id"] for r in result["history"]])
    print(result["context"])
assert not failed, f"Retrieval failures: {failed}"
print("\nAll 8 retrieval probes completed")
PY
```

**Kontrola:**
- 8 výsledkov so statusom `ok`.
- Načítaná história má zmysel; skontrolovať jej skutočný text.
- Žiadny vybraný výsledok nesmie byť pod thresholdom.
- Prázdna história nie je technická chyba. Treba rozlíšiť threshold/filter od chyby DB.
- Ak `resolution` neobsahuje použiteľné informácie, nepovažovať ju za hotovú investigáciu.
- Na kvalitu retrievalu nestačí status `ok`; ručne posúdiť vhodnosť ID a textov.
- Finálny draft 24 scenárov v tejto fáze nepoužívať.

## 7. Smoke test: všetkých 10 LLM cez meraný adaptér

Tento krok je dôležitejší než samotný pozdrav cez `check_cloud.py`:
používa presne ten meraný adaptér, aký použije hlavný test.

```bash
python rag_test.py \
  --scenarios results/preflight-2026-10-31-v2/smoke-scenario.json \
  --embeddings gemini --llms all --modes rag --repeats 1 \
  --top-k 3 --max-output-tokens 4096 --ollama-num-ctx 8192 --order by-model --timeout 300 --seed 42 \
  --pricing-date 2026-10-31 --out results/rag-smoke-2026-10-31-v2
```

**Očakávané:** `1 scenarios; 1 embeddings; 10 LLMs; 10 calls` a `Dry run`.

Až potom reálny beh:

```bash
python rag_test.py \
  --scenarios results/preflight-2026-10-31-v2/smoke-scenario.json \
  --embeddings gemini --llms all --modes rag --repeats 1 \
  --top-k 3 --max-output-tokens 4096 --ollama-num-ctx 8192 --order by-model --timeout 300 --seed 42 \
  --pricing-date 2026-10-31 --out results/rag-smoke-2026-10-31-v2 --execute \
  2>&1 | tee results/preflight-2026-10-31-v2/smoke-console.log
rag_rc=${PIPESTATUS[0]}
printf 'Smoke exit code: %s\n' "$rag_rc"
```

Kontrola výsledkov:

```bash
python - <<'PY'
from pathlib import Path
from collections import Counter
from rag_test import read_json
out = Path("results/rag-smoke-2026-10-31-v2")
rows = [read_json(p) for p in sorted((out / "calls").glob("*.json"))]
print("Rows:", len(rows), "Statuses:", Counter(r["status"] for r in rows))
for r in rows:
    print(r["llm_profile"], r["status"], "tokens:", r.get("input_tokens"),
          r.get("output_tokens"), "seconds:", r.get("llm_latency_s"),
          "USD:", r.get("estimated_cost_usd"), r.get("cost_status"), r.get("error", ""))
assert len(rows) == 10
assert all(r["status"] == "ok" and r.get("answer", "").strip() for r in rows)
assert all(r.get("input_tokens") is not None and r.get("output_tokens") is not None for r in rows)
assert len({r["user_prompt"] for r in rows}) == 1
assert len({r["system_prompt"] for r in rows}) == 1
assert all("review_guidance" not in r["user_prompt"] for r in rows)
print("10 complete answers, token usage and identical prompts verified")
PY
```

**Nepokračovať na 480 volaní**, ak niektorý model vracia chybu/neúplnú odpoveď.
`check_cloud.py` je voliteľná dodatočná diagnostika (`python check_cloud.py`,
očakáva 8 passed, 0 failed), ale stojí ďalšie API volania a nepoužíva meraný adaptér.

Cenu `None` preskúmať podľa `cost_status`; nie je automaticky chybou odpovede.
Napríklad cache hit bez nastavenej cache ceny má neznámu cenu.

## 8. Hlavný vývojový beh — najprv 20, potom zvyšok

Použijeme tie isté parametre pri spustení aj pokračovaní.
Nasledujúce premenné nastav v aktuálnom Bash okne:

```bash
export RUN=results/rag-dev-2026-10-31-v2
RAG_ARGS=(
  --scenarios rag_scenarios.json
  --thresholds-file thresholds_FROZEN.json
  --prices llm_prices.json
  --embeddings all --llms all
  --modes rag --repeats 1
  --top-k 3 --max-output-tokens 4096
  --ollama-num-ctx 8192 --order by-model
  --timeout 300 --seed 42
  --pricing-date 2026-10-31
  --out "$RUN"
)
python rag_test.py "${RAG_ARGS[@]}"
```

**Očakávané:** `6 scenarios; 8 embeddings; 10 LLMs; 480 calls`, dry run.
Ak priečinok už obsahuje manifest, nezačínaj doň nový beh; použi resume iba pre
identickú konfiguráciu, inak nový názov priečinka.

Najprv priprav všetkých 48 kontextov. Táto fáza vykonáva iba retrieval,
po embedding profiloch; nevykoná žiadne LLM volanie. Vytvorí manifest a contexts,
ale ešte nie výsledkové CSV.

```bash
python rag_test.py "${RAG_ARGS[@]}" --execute --prepare-contexts \
  2>&1 | tee results/preflight-2026-10-31-v2/prepare-contexts.log
rag_rc=${PIPESTATUS[0]}
printf 'Prepare exit code: %s\n' "$rag_rc"
```

**Kontrola:** 48 kontextov a `failures=0`. Pri chybe nepokračovať.
Prerušenú prípravu možno dokončiť tým istým príkazom s `--resume`;
už uložené chybné kontexty sa však automaticky neopakujú.

Na Windows hoste skontroluj `ollama ps`. Ak zostali rezidentné embedding modely,
ukonči ich pred LLM fázou; rob to iba vtedy, keď ich nepoužíva iný proces.
Nasledujúce príkazy uvoľnia rezidentné modely, nevymažú ich súbory:

```powershell
ollama ps
ollama stop nomic-embed-text
ollama stop bge-m3
ollama stop qwen3-embedding:4b
ollama stop qwen3-embedding:8b
ollama ps
```

Niektoré už nemusia bežať. Na hoste počas testu nespúšťaj ďalšie modely.
Lokalita Ollamy zostáva tá, ktorú má VM nastavenú cez OLLAMA_HOST.

Potom spusti prvých najviac 20 nových LLM volaní. Použi už `--resume`,
pretože prípravná fáza vytvorila manifest:

```bash
python rag_test.py "${RAG_ARGS[@]}" --execute --resume --max-calls 20 \
  2>&1 | tee results/preflight-2026-10-31-v2/dev-first20.log
rag_rc=${PIPESTATUS[0]}
printf 'First batch exit code: %s\n' "$rag_rc"
```

Pozri výsledky podľa kroku 9. Ak sú v poriadku, pokračuj:

```bash
python rag_test.py "${RAG_ARGS[@]}" --execute --resume \
  2>&1 | tee results/preflight-2026-10-31-v2/dev-resume.log
rag_rc=${PIPESTATUS[0]}
printf 'Resume exit code: %s\n' "$rag_rc"
```

Pri bezchybnom prvom bloku sa doplní 460 LLM odpovedí, nie ďalších 480.
Pri chybách retrievalu môže existovať viac než 20 záznamov: `--max-calls`
limituje nové LLM volania, nie záznamy retrieval_error.

**Kontrola ukončenia:** 480 záznamov, ideálne všetky `ok`, 48 uložených retrieval kontextov.
Exit code 0 po prvých 20 volaniach neznamená dokončenú celú maticu.
V tomto runbooku používame `--order by-model`: najprv sa premiešajú scenáre
podľa seedu a potom sa zoskupia podľa LLM. Po príprave kontextov sa už embeddingy
medzi LLM volania nevkladajú. Prvé volanie každého modelu, vypršanie keep-alive,
resume alebo iná GPU záťaž stále môžu spôsobiť cold load.
Poradie po modeloch môže priniesť časový bias; zaznamenať ho a nevyhlasovať celý beh
za čisto warm meranie. `load_duration_s` a engine throughput posudzovať osobitne.

## 9. Kontrola výsledkov, promptov a ceny

Tento blok možno použiť po prvých 20 volaniach aj po dokončení.
Premenná RUN musí ukazovať na správny beh.

```bash
python - <<'PY'
import os
from collections import Counter, defaultdict
from pathlib import Path
from rag_test import read_json
out = Path(os.environ["RUN"])
manifest = read_json(out / "manifest.json")
rows = [read_json(p) for p in (out / "calls").glob("*.json")]
contexts = [read_json(p) for p in (out / "contexts").glob("*.json")]
print("Records:", len(rows), "/ 480")
print("Statuses:", dict(Counter(r["status"] for r in rows)))
print("Contexts:", len(contexts), "/ 48")
print("Cost statuses:", dict(Counter(r.get("cost_status", "unknown") for r in rows)))
known = sum(r["estimated_cost_usd"] for r in rows if r.get("estimated_cost_usd") is not None)
unknown = sum(r.get("estimated_cost_usd") is None for r in rows)
print("Sum of known LLM estimates, USD:", round(known, 6))
print("Unknown-cost records:", unknown)
groups = defaultdict(set)
for r in rows:
    if "user_prompt" in r:
        groups[(r["scenario_id"], r["embedding_profile"], r["mode"])].add(
            (r["system_prompt"], r["user_prompt"]))
    if r["status"] != "ok":
        print("CHECK:", r["call_id"], r["llm_profile"], r["status"], r.get("error"), r.get("finish_reason"))
assert all(len(prompts) == 1 for prompts in groups.values()), "Prompt mismatch"
for context in contexts:
    if context["status"] == "ok":
        assert all(h["similarity"] >= context["threshold"] for h in context["history"])
print("Prompt equality and retrieved thresholds OK")
if len(rows) == 480 and all(r["status"] == "ok" for r in rows):
    print("COMPLETE: 480/480 successful responses")
else:
    print("NOT fully complete/successful: inspect counts and errors")
PY
```

Čo cenu znamená:
- `estimated`: odhad podľa uložených sadzieb; nie faktúra.
- `estimated_future_rate`: Argon používa na tvoju žiadosť $4/$20 podľa sadzieb od 1.12.;
  nezahŕňa promo kredity.
- `local_api_fee_only`: nulový priamy API poplatok; elektrina/GPU nie sú zadarmo.
- `missing_or_invalid_cached_input_per_million`: cache tokeny majú neznámu sadzbu.
- `unknown`/chýbajúce usage pri timeout: náklad môže existovať, hoci ho nepoznáme.
- `llm_not_called`: zlyhal retrieval, LLM nebol volaný; embedding náklad nie je započítaný.

Súčet známych cien nie je úplná faktúra. Nezahŕňa retrieval, preflight a smoke
mimo tohto priečinka, neznáme náklady, elektrinu ani infraštruktúru.
Ceny počas behu nemenit — manifest by už nezodpovedal.

Latencia:
- `llm_latency_s`: celé ne-streamované volanie vrátane inicializácie klienta a siete.
- `retrieval_latency_s`: embedding dotazu + DB vyhľadanie, uložené raz a zdieľané.
- `pipeline_latency_estimate_s`: ich súčet, nie osobitne meraný nový end-to-end request.
- `summary.json`: p50/p95 iba úspešných volaní v danej skupine.
- Na šiestich scenároch je p95 len orientačné; TTFT nemeriame.

## 10. Priprav podklady na ručné hodnotenie

Tento export zjednotí incident, guidance a odpoveď do jedného CSV.
Guidance sa pridáva až teraz, nie do promptu poslaného LLM.
Súbor neobsahuje automatické skóre.

```bash
python - <<'PY'
import csv
import os
from pathlib import Path
from rag_test import read_json
out = Path(os.environ["RUN"])
manifest = read_json(out / "manifest.json")
scenarios = {s["id"]: s for s in manifest["scenarios"]}
fields = ["call_id", "scenario_id", "incident", "review_guidance", "embedding_profile",
          "llm_profile", "status", "retrieved_ids", "user_prompt", "answer"]
with (out / "review_packet.csv").open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    for path in sorted((out / "calls").glob("*.json")):
        row = read_json(path)
        scenario = scenarios[row["scenario_id"]]
        writer.writerow({
            "call_id": row["call_id"], "scenario_id": row["scenario_id"],
            "incident": scenario["incident"], "review_guidance": scenario.get("review_guidance", ""),
            "embedding_profile": row["embedding_profile"], "llm_profile": row["llm_profile"],
            "status": row["status"], "retrieved_ids": ", ".join(row.get("retrieved_ids", [])),
            "user_prompt": row.get("user_prompt", ""), "answer": row.get("answer", "")
        })
print(out / "review_packet.csv")
print("Score in:", out / "quality_review.csv")
PY
```

Otvor `review_packet.csv` a `quality_review.csv`, spájaj ich podľa `call_id`.
Nepočítať riadky CSV cez `wc -l`: odpovede obsahujú nové riadky.

Každú úplnú odpoveď hodnotiť 0–2:

| Pole | 0 | 1 | 2 |
| --- | --- | --- | --- |
| relevance_0_2 | nesúvisiace kroky | časť krokov vhodná | kroky sedia na aktuálne signály |
| evidence_0_2 | vymyslené/nesprávne dôkazy | čiastočne podložené | dôsledne oddeľuje fakty od hypotéz |
| citations_0_2 | falošné historické zdroje | nejasné priradenie | správne ID alebo jasne uvedený aktuálny dôkaz |
| uncertainty_0_2 | nepodložená istota | neistota neúplná | jasné hranice poznania a čo overiť |
| actionability_0_2 | nepoužiteľné/rizikové | príliš všeobecné | konkrétne a primerané ďalšie kontroly |

`critical_error`: zapisuj `yes` alebo `no`; do `notes` daj stručné zdôvodnenie.
Nevyplnené skóre neznamená nulu. Pri technickej chybe ho nechaj prázdne a označ
technickú chybu; nepovažuj ju za nesprávnu diagnostiku.
Odmietnutie nebezpečného pokynu s citovaním jeho textu nie je automaticky zlyhanie.
Nehodnotiť štylistickú uhladenosť namiesto správnosti.

Ak sa dá, pri hodnotení skry `llm_profile` a cenu, aby neovplyvnili úsudok.
Pravidlá použi rovnako pre všetky modely. Iný správny postup než guidance je prípustný.
Skóre runner zatiaľ automaticky neagreguje; nesľubuje automatický rebríček kvality.

## 11. Obnovenie a riešenie problémov

### Bežné pokračovanie

Znova nastav exporty z kroku 2 a RAG_ARGS/RUN z kroku 8, aktivuj tú istú venv.
Nepúšťaj medzi tým git pull ani pip upgrade.

```bash
python rag_test.py "${RAG_ARGS[@]}" --execute --resume
```

Rovnaké `--pricing-date 2026-10-31` ponechaj aj pri pokračovaní po polnoci.
Záznamy `ok`, `error`, `incomplete`, `timeout`, `pending` aj `retrieval_error`
sa **neopakujú**. Resume doplní len chýbajúce kombinácie.

### Prerušenie

Na plánovanú prestávku použi `--max-calls` a nechaj blok dobehnúť.
Ctrl+C môže nechať `pending` a vzdialená služba mohla request účtovať.
Pred novým behom over, že nezostal bežať worker:

```bash
pgrep -af 'rag_test.py'
```

Ak po páde zostal `.running`, najprv preskúmaj PID a aktívne procesy.
V tmux sa najprv vráť do pôvodnej relácie; nespúšťaj duplicitný proces.
Lock odstraňuj až po potvrdení, že pôvodný proces ani workery už nebežia.
Nemaž `calls/*.json`, aby si vynútil opakovanie.

### Obnova CSV po prerušení — bez API volaní

```bash
python - <<'PY'
import os
from pathlib import Path
from rag_test import export_results
out = Path(os.environ["RUN"])
assert (out / "manifest.json").exists()
assert not (out / ".running").exists(), "Do not export while the writer is running"
rows = export_results(out)
print("Exported records:", len(rows))
PY
```

### Najčastejšie chyby

| Problém | Postup |
| --- | --- |
| `Resume configuration/code differs` | Porovnať manifest s parametrami, dátumom, modelmi, balíkmi a kódom. Obnoviť pôvodné prostredie alebo nový priečinok; nikdy neprepisovať manifest. |
| `401/403` | Overiť platnosť kľúča/ADC a oprávnenia pre skutočný projekt/deployment. Nevypisovať tokeny do logu. |
| `404/model not found` | Overiť presný model, Azure deployment a Vertex location. Model nenahrádzať potichu pod rovnakým názvom experimentu. |
| `429` | Zastaviť ďalšie bloky, skontrolovať kvótu a čas obnovy. Chybné záznamy resume neopakuje. |
| `incomplete`, `length`, `MAX_TOKENS`, `max_tokens` | Pozrieť odpoveď a reasoning usage. Ak je cap malý, upraviť ho pre nový vývojový beh všetkých porovnávaných modelov. |
| Timeout pri lokálnom modeli | Overiť GPU/VRAM, host a cold load. Zmenu timeoutu robiť v novom behu, lebo patrí do manifestu. |
| Chyba HttpRetryOptions | Opraviť verziu google-genai pred novým behom, zopakovať smoke. |
| Žiadna relevantná história | Skontrolovať kandidátov, filtre a frozen threshold. Nie je to automaticky API chyba. |
| Cena None | Pozrieť cost_status a raw usage; neinterpretovať ako $0. |
| Chybný retrieval uložený v contexts | Resume ho znova nepokúsi. Po oprave vytvoriť nový, jasne označený beh. |

Opravný beh môže mať zúžené `--llms`/`--embeddings` a samostatný súbor scenárov.
Zachovaj pôvodné výsledky aj ich náklady; neopravuj ich prepísaním úspešnými odpoveďami.

## 12. Voliteľné kontroly a finálna sada

### Samostatná čisto lokálna vetva: 144 volaní bez API poplatkov

Ak chceš iba túto vetvu, vykonaj krok 1 a offline unit testy z kroku 3.
**Vynechaj cloudové kontroly kľúčov v kroku 2, cloudové importy a kroky 6–8 plného behu.**
Cloudové kľúče nie sú pre tento výber potrebné. Potrebuješ však funkčný PG_DSN,
OLLAMA_HOST, numpy, python-dotenv, psycopg, pgvector a ollama v existujúcej venv.
Kontrolu lokálnych modelov a GPU z kroku 5 zachovaj.

Over šesť lokálnych tabuliek bez cloudových volaní:

```bash
python - <<'PY'
import psycopg
from psycopg import sql
from config import MODELS, PG_DSN
profiles = ["nomic", "nomic_prefix", "bge", "qwen", "qwen_instr", "qwen8"]
baseline = None
with psycopg.connect(PG_DSN, connect_timeout=10) as conn:
    conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET statement_timeout = '30s'")
    for p in profiles:
        rows = conn.execute(sql.SQL(
            "SELECT incident_id, vector_dims(embedding) FROM {}"
        ).format(sql.Identifier("incident_memory_" + p))).fetchall()
        ids = {str(r[0]) for r in rows}
        assert len(rows) == len(ids) == 200, p
        assert all(r[1] == MODELS[p]["dim"] for r in rows), p
        if baseline is None:
            baseline = ids
        assert ids == baseline, p
        print(p, "OK", len(rows), MODELS[p]["dim"])
PY
```

Priprav parametre. Rovnakú konfiguráciu použi pri príprave, spustení a resume:

```bash
set -o pipefail
export RUN=results/rag-local-2026-10-31-v2
LOCAL_ARGS=(
  --scenarios rag_scenarios.json
  --embeddings nomic,nomic_prefix,bge,qwen,qwen_instr,qwen8
  --llms gemma,qwen36,qwen38,llama
  --modes rag --repeats 1 --top-k 3
  --max-output-tokens 4096 --ollama-num-ctx 8192
  --timeout 300 --order by-model --seed 42
  --pricing-date 2026-10-31 --out "$RUN"
)
python rag_test.py "${LOCAL_ARGS[@]}"
```

**Kontrola:** 6 scenárov × 6 embedding profilov × 4 LLM = **144 LLM volaní**.
Najprv retrieval a kontrola `failures=0`:

```bash
python rag_test.py "${LOCAL_ARGS[@]}" --execute --prepare-contexts
```

Po pripravení 36 kontextov uvoľni rezidentné embeddingy na hoste podľa kroku 8.
Spusti postupne krátke bloky a kontroluj GPU, výstupné tokeny a status.
Zoskupené poradie znamená, že prvý blok nemusí obsahovať všetky štyri LLM:

```bash
python rag_test.py "${LOCAL_ARGS[@]}" --execute --resume --max-calls 4
```

Keď sú výsledky v poriadku, doplň zvyšok:

```bash
python rag_test.py "${LOCAL_ARGS[@]}" --execute --resume
```

```bash
python - <<'PY'
import os
from pathlib import Path
from collections import Counter
from rag_test import read_json
out = Path(os.environ["RUN"])
rows = [read_json(p) for p in (out / "calls").glob("*.json")]
print("Records", len(rows), "/ 144", Counter(r["status"] for r in rows))
print("Contexts", len(list((out / "contexts").glob("*.json"))), "/ 36")
assert len(rows) == 144
assert all(r["status"] == "ok" for r in rows)
print("Local matrix complete")
PY
```

Export z kroku 10 funguje aj pre tento RUN. Počty 480/48 z kroku 9 a cloudové
smoke priečinky z archivácie pre túto vetvu nepoužívaj.
Archivácia iba lokálneho behu:

```bash
tar -czf "results/rag-local-session-2026-10-31-$(date +%H%M%S).tar.gz" "$RUN"
```

API poplatok je nulový; GPU, elektrina a čas majú stále náklady.

### Ďalšie kontroly plnej matice


**Bez histórie:** až keď je RAG beh funkčný; samostatných 60 LLM volaní:

```bash
python rag_test.py --scenarios rag_scenarios.json --embeddings all --llms all \
  --modes no_history --repeats 1 --max-output-tokens 4096 --ollama-num-ctx 8192 --order by-model --timeout 300 \
  --pricing-date 2026-10-31 --out results/rag-no-history-2026-10-31-v2 --execute
```

No-history neposiela query embeddingy ani nečíta DB. Porovnáva iba schopnosť pracovať
s aktuálnymi signálmi. `curated` režim zatiaľ neštartovať — nemáme doplnené curated_context.

**24 finálnych kandidátov:** najprv len skontrolovať zoznam a guidance.
Neposielať ich LLM počas ladenia promptu. Po manuálnej kontrole corpus coverage,
relevantných historických ID a rubriky vytvor prijatú verziu
`rag_scenarios_final.json`. Až vtedy použi `--scenarios rag_scenarios_final.json`.
Názov "final" sám osebe nezaručuje nezávislosť; rozhoduje nepoužitie pri ladení.

V aktuálnom drafte sú referenčné ID `null` = zatiaľ neskontrolované.
Nezamieňať to s prázdnym zoznamom = overene žiadna relevantná história.
Prompt-injection prípady testujú len generovanú odpoveď, nie reálne tool calling.

## 13. Archivácia a záver dňa

Po dokončení exportov a hodnotenia, v Ubuntu:

```bash
git rev-parse HEAD > results/preflight-2026-10-31-v2/git-head-end.txt
sha256sum config.py providers.py search.py rag.py rag_prompt.py rag_test.py llm_metrics.py rag_scenarios.json thresholds_FROZEN.json llm_prices.json > results/preflight-2026-10-31-v2/input-sha256-end.txt
diff -u results/preflight-2026-10-31-v2/input-sha256.txt results/preflight-2026-10-31-v2/input-sha256-end.txt
tar -czf "results/rag-session-2026-10-31-v2-$(date +%H%M%S).tar.gz" \
  results/preflight-2026-10-31-v2 "$RUN" results/rag-smoke-2026-10-31-v2
```

**Kontrola:** diff bez zmien, archív existuje. Voliteľný no-history priečinok archivovať
tiež, ak bol spustený. Archív obsahuje incidentové texty a odpovede; neobsahuje zámerne
`.env` ani API kľúče. Výsledky zostávajú lokálne a sú v gitignore.

Na konci zaznamenať:
- commit, modelové identifikátory/digesty, GPU a parametre;
- počet plánovaných, úspešných, neúplných a chybných volaní;
- známe odhadované náklady a počet neznámych;
- latencie s informáciou o cold loads;
- stav ručného hodnotenia a príklady dobrých/chybných krokov;
- zmeny promptu navrhnuté z vývojovej sady;
- či je finálna sada už skontrolovaná a zmrazená.

**Tvrdenie po tomto dni:** výsledok na šiestich vývojových scenároch,
nie všeobecné prvenstvo modelu ani úspešne vykonaná agentová investigácia.

## Overenie tohto runbooku

Postup bol pripravený podľa aktuálneho rozhrania skriptov na GitHube 30.10.2026.
Python bloky sú syntakticky kontrolované; reálne DB/API/GPU kroky sa musia overiť na VM.
Žiadne platené benchmark volania neboli pri príprave runbooku vykonané.
