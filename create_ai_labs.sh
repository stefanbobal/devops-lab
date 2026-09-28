#!/usr/bin/env bash
# Creates ai-labs/ in the devops-lab repository.
# Run from the repository root:  bash create_ai_labs.sh
set -euo pipefail

if [ ! -d .git ]; then
  echo "Run this script from the repository root (~/devops-lab)."
  exit 1
fi

if [ -e ai-labs ]; then
  echo "ai-labs/ already exists - nothing was changed."
  exit 1
fi

mkdir -p ai-labs/code

# ---------------------------------------------------------------------------
# .gitignore
# ---------------------------------------------------------------------------
touch .gitignore
for pattern in "venv/" "__pycache__/" ".env"; do
  grep -qxF "$pattern" .gitignore || echo "$pattern" >> .gitignore
done

# ---------------------------------------------------------------------------
# Code
# ---------------------------------------------------------------------------
cat > ai-labs/code/requirements.txt << 'EOF'
ollama
psycopg[binary]
pgvector
numpy
EOF

cat > ai-labs/code/docker-compose.yml << 'EOF'
services:
  pgvector:
    image: pgvector/pgvector:pg16
    container_name: pgvector
    environment:
      POSTGRES_PASSWORD: lab   # local lab only, never use real credentials here
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
EOF

cat > ai-labs/code/config.py << 'EOF'
"""Shared settings for all AI labs. Override any value with an environment variable."""
import os

PG_DSN = os.getenv("PG_DSN", "host=localhost user=postgres password=lab dbname=postgres")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
LLM_MODEL = os.getenv("LLM_MODEL", "gemma3:27b")
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.60"))
EOF

cat > ai-labs/code/embeddings_test.py << 'EOF'
"""Lab 02: compare the meaning of sentences using embeddings."""
import numpy as np
import ollama

from config import EMBED_MODEL

sentences = [
    "SAP system is very slow for users",
    "High dialog response times on application server",
    "HANA data backup failed",
    "Backint returned SSL handshake error during backup",
    "Coffee machine on the third floor is broken",
    "SAP systém je veľmi pomalý",
]

response = ollama.embed(model=EMBED_MODEL, input=sentences)
vectors = np.array(response["embeddings"])
print("Vector dimension:", vectors.shape[1])

# cosine similarity: 1 = same meaning, close to 0 = unrelated
vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
similarity = vectors @ vectors.T

for i in range(len(sentences)):
    for j in range(i + 1, len(sentences)):
        print(f"{similarity[i, j]:.2f}  {sentences[i]}  <->  {sentences[j]}")
EOF

cat > ai-labs/code/load_incidents.py << 'EOF'
"""Lab 03: create the incident_memory table and load fictional historical incidents."""
import numpy as np
import ollama
import psycopg
from pgvector.psycopg import register_vector

from config import EMBED_DIM, EMBED_MODEL, PG_DSN

# (sid, domain, db_type, date, title, evidence, root_cause_status, resolution)
INCIDENTS = [
    ("Q50", "backup", "HANA", "2026-09-10", "HANA Backup Failure",
     "Data backup failed. Backint returned SSL handshake error. backup.log shows failed external backup call.",
     "CONFIRMED", "Renewed expired client certificate for backint agent."),
    ("D15", "backup", "HANA", "2026-08-22", "HANA Backup Failure",
     "Log backups piling up. Backint could not reach backup target. Network timeout to storage endpoint.",
     "CONFIRMED", "Storage team restored backup target availability."),
    ("P20", "backup", "HANA", "2026-07-14", "HANA log backup overdue",
     "Log backup interval exceeded. Log volume filling up. Backint process hung.",
     "NOT_CONFIRMED", "Restarted backint agent, backups resumed."),
    ("P11", "backup", "Oracle", "2026-06-03", "Oracle RMAN backup failed",
     "RMAN job ended with error. Archive log destination full.",
     "CONFIRMED", "Cleaned archive log destination and added space."),
    ("P30", "performance", "HANA", "2026-09-02", "High dialog response time",
     "Dialog response time above 2 seconds. Most work processes busy. Expensive SQL from a custom report.",
     "CONFIRMED", "Stopped long-running custom report and optimized its SQL."),
    ("Q30", "performance", "HANA", "2026-08-11", "SAP system slow for users",
     "Users report slowness. High CPU on HANA host. Delta merge running during business hours.",
     "NOT_CONFIRMED", "Rescheduled delta merge outside business hours."),
    ("P40", "performance", "Oracle", "2026-07-31", "Long running batch jobs",
     "Month-end batch jobs running twice as long. Database wait events on I/O.",
     "CONFIRMED", "Infrastructure team fixed storage I/O bottleneck."),
    ("P50", "database", "HANA", "2026-08-28", "HANA memory allocation limit reached",
     "Column store unloads. Out of memory dumps. Large table fully loaded into memory.",
     "CONFIRMED", "Partitioned the large table and raised allocation limit."),
    ("D50", "database", "HANA", "2026-06-19", "HANA indexserver restart",
     "Indexserver crashed and restarted. Crash dump matches a known bug in the revision.",
     "CONFIRMED", "Applied HANA revision update recommended by SAP Note."),
    ("Q11", "interface", "HANA", "2026-09-15", "RFC connection failure",
     "RFC destination to external system failing. Certificate in STRUST expired, SSL handshake fails.",
     "CONFIRMED", "Imported new certificate in STRUST."),
    ("P60", "interface", "HANA", "2026-05-27", "IDoc processing stuck",
     "IDocs in status 64 not processed. Background job for RBDAPP01 not scheduled.",
     "CONFIRMED", "Rescheduled IDoc processing job."),
    ("D20", "os", "HANA", "2026-08-05", "Filesystem /usr/sap almost full",
     "Filesystem usage at 95 percent. Old trace files and work directory logs accumulated.",
     "CONFIRMED", "Cleaned old traces and set up housekeeping."),
]


def build_memory_text(domain, db_type, title, evidence, resolution):
    """Compact, normalized text that gets embedded (not raw logs)."""
    return (f"Domain: {domain}\nDatabase: {db_type}\nTitle: {title}\n"
            f"Evidence: {evidence}\nResolution: {resolution}")


conn = psycopg.connect(PG_DSN, autocommit=True)
conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
register_vector(conn)

conn.execute("DROP TABLE IF EXISTS incident_memory")
conn.execute(f"""
    CREATE TABLE incident_memory (
        id serial PRIMARY KEY,
        sid text, domain text, db_type text, incident_date date,
        title text, evidence text, root_cause_status text, resolution text,
        embedding_text text,
        embedding_model text,
        embedding vector({EMBED_DIM})
    )
""")

for sid, domain, db_type, date, title, evidence, status, resolution in INCIDENTS:
    text = build_memory_text(domain, db_type, title, evidence, resolution)
    vector = ollama.embed(model=EMBED_MODEL, input=text)["embeddings"][0]
    conn.execute(
        """INSERT INTO incident_memory
           (sid, domain, db_type, incident_date, title, evidence,
            root_cause_status, resolution, embedding_text, embedding_model, embedding)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (sid, domain, db_type, date, title, evidence, status, resolution,
         text, EMBED_MODEL, np.array(vector)),
    )
    print("Stored:", sid, title)

print("Done.")
EOF

cat > ai-labs/code/search.py << 'EOF'
"""Lab 04: similarity search = deterministic filters first, then vector similarity."""
import sys

import numpy as np
import ollama
import psycopg
from pgvector.psycopg import register_vector

from config import EMBED_MODEL, PG_DSN, SIMILARITY_THRESHOLD

COLUMNS = ["sid", "domain", "db_type", "incident_date", "title", "evidence",
           "root_cause_status", "resolution", "similarity"]


def find_similar(query, domain=None, db_type=None, limit=3):
    vector = np.array(ollama.embed(model=EMBED_MODEL, input=query)["embeddings"][0])
    conn = psycopg.connect(PG_DSN)
    register_vector(conn)

    # <=> is cosine distance in pgvector, so similarity = 1 - distance
    sql = """SELECT sid, domain, db_type, incident_date, title, evidence,
                    root_cause_status, resolution,
                    1 - (embedding <=> %s) AS similarity
             FROM incident_memory WHERE true"""
    params = [vector]
    if domain:                      # deterministic filter 1
        sql += " AND domain = %s"
        params.append(domain)
    if db_type:                     # deterministic filter 2
        sql += " AND db_type = %s"
        params.append(db_type)
    sql += " ORDER BY embedding <=> %s LIMIT %s"
    params += [vector, limit]

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(zip(COLUMNS, row)) for row in rows]


if __name__ == "__main__":
    query = sys.argv[1]
    domain = sys.argv[2] if len(sys.argv) > 2 else None
    db_type = sys.argv[3] if len(sys.argv) > 3 else None

    for r in find_similar(query, domain, db_type):
        mark = "OK" if r["similarity"] >= SIMILARITY_THRESHOLD else "below threshold"
        print(f"{r['similarity']:.2f} [{mark}] {r['sid']} "
              f"{r['domain']}/{r['db_type']} {r['title']} ({r['root_cause_status']})")
EOF

cat > ai-labs/code/rag.py << 'EOF'
"""Lab 05: RAG - historical incidents as CONTEXT for a local LLM, never as proof."""
import ollama

from config import LLM_MODEL, SIMILARITY_THRESHOLD
from search import find_similar

current_incident = """SID: D60
Domain: backup
Database: HANA
Title: HANA Backup Failure
Signals: data backup failed at 02:00, backint exit code non-zero,
backint.log contains 'SSL routines: certificate verify failed'"""

candidates = find_similar(current_incident, "backup", "HANA")
history = [c for c in candidates if c["similarity"] >= SIMILARITY_THRESHOLD]

if history:
    context = "\n\n".join(
        f"Similar incident #{i + 1}: {h['sid']} ({h['incident_date']}), "
        f"similarity {h['similarity']:.2f}\n"
        f"Title: {h['title']}\nEvidence: {h['evidence']}\n"
        f"Root cause status: {h['root_cause_status']}\nResolution: {h['resolution']}"
        for i, h in enumerate(history)
    )
else:
    context = "No sufficiently similar historical incidents found."

system_prompt = """You are an SAP operations investigation assistant.
Historical incidents are CONTEXT ONLY. Similarity does NOT prove the same root cause.
Use history to decide what to check next, never as proof."""

user_prompt = f"""CURRENT EVIDENCE
{current_incident}

HISTORICAL CONTEXT
{context}

Task: propose the 3 most useful next investigation steps for the CURRENT incident.
For each step, say which historical case inspired it.
State clearly what must still be verified on the current system."""

response = ollama.chat(model=LLM_MODEL, messages=[
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt},
])

print("--- HISTORICAL CONTEXT ---")
print(context)
print("\n--- MODEL ANSWER ---")
print(response["message"]["content"])
EOF

cat > ai-labs/code/eval.py << 'EOF'
"""Lab 06: measure retrieval quality on a small test set."""
from config import SIMILARITY_THRESHOLD
from search import find_similar

# (query, domain, db_type, expected SID or None if nothing should be found)
TESTS = [
    ("backint cannot verify SSL certificate", "backup", "HANA", "Q50"),
    ("backup target storage not reachable, timeout", "backup", "HANA", "D15"),
    ("log backups are late and log volume grows", "backup", "HANA", "P20"),
    ("archive log area full, RMAN failed", "backup", "Oracle", "P11"),
    ("custom report runs heavy SQL, dialog is slow", "performance", "HANA", "P30"),
    ("indexserver crashed unexpectedly", "database", "HANA", "D50"),
    ("RFC call fails because certificate expired", "interface", "HANA", "Q11"),
    ("disk almost full on /usr/sap", "os", "HANA", "D20"),
    ("Printer on floor 2 is out of paper", None, None, None),
    ("network switch firmware upgrade planned", None, None, None),
]

correct = 0
for query, domain, db_type, expected in TESTS:
    above = [r for r in find_similar(query, domain, db_type)
             if r["similarity"] >= SIMILARITY_THRESHOLD]
    found = above[0]["sid"] if above else None
    ok = found == expected
    correct += ok
    print(f"{'OK  ' if ok else 'FAIL'}  expected={expected}  found={found}  | {query}")

print(f"\nScore: {correct}/{len(TESTS)} at threshold {SIMILARITY_THRESHOLD}")
EOF

# ---------------------------------------------------------------------------
# Labs
# ---------------------------------------------------------------------------
cat > ai-labs/01-local-llm-ollama.md << 'EOF'
# AI Lab 01 – Local LLM with Ollama (hybrid setup)

## Goal

Run a local LLM on the Windows host GPU and call it from the Ubuntu VM over the network.

## Architecture

```
Ubuntu VM (192.168.178.110)                 Windows host (192.168.178.25)
Python scripts, Docker, PostgreSQL  ──────►  Ollama :11434  ──►  RTX 4090 (24 GB VRAM)
```

VirtualBox cannot pass the GPU into the VM, so the model runs on Windows and the VM uses it
as a network service. This is the same pattern as a model endpoint in production:
the model is a separate service, the application calls it over HTTP.

## Concepts

- **Model size vs. VRAM:** a model has billions of parameters, each stored as a number.
- **Quantization:** storing parameters with lower precision. A 70B model needs ~140 GB in FP16,
  ~70 GB in 8-bit and ~35–40 GB in 4-bit. `gemma3:27b` in Ollama is 4-bit (~17 GB) and fits
  into 24 GB VRAM; a 70B model does not.
- **Embedding model:** a small model that turns text into a vector (used from Lab 02 on).

## Steps

### 1. Install Ollama on Windows

Download from ollama.com and install. Verify in PowerShell:

```powershell
ollama --version
```

### 2. Pull models (Windows)

```powershell
ollama pull gemma3:27b
ollama pull nomic-embed-text
```

### 3. Test locally (Windows)

```powershell
ollama run gemma3:27b
```

Ask a question, exit with `/bye`. In a second window run `ollama ps`:
the PROCESSOR column must show **100% GPU**.

### 4. Expose Ollama to the network (Windows)

Option A: Ollama app → Settings → **Expose Ollama to the network**.

Option B:

```powershell
setx OLLAMA_HOST 0.0.0.0
Get-Process *ollama* | Stop-Process -Force
# start Ollama again from the Start menu
```

Verify in a **new** PowerShell window:

```powershell
netstat -an | findstr 11434
```

Expected: `0.0.0.0:11434 ... LISTENING`.

### 5. Firewall (Windows, PowerShell as administrator)

```powershell
New-NetFirewallRule -DisplayName "Ollama" -Direction Inbound -LocalPort 11434 -Protocol TCP -Action Allow -Profile Private
Get-NetConnectionProfile
```

`NetworkCategory` of the Ethernet adapter must be `Private`.

### 6. Test from the VM

```bash
curl http://192.168.178.25:11434
```

Expected: `Ollama is running`.

### 7. Persist OLLAMA_HOST in the VM

The `ollama` Python library reads this variable, so no script needs the IP hard-coded.

```bash
echo 'export OLLAMA_HOST=http://192.168.178.25:11434' >> ~/.bashrc
source ~/.bashrc
```

### 8. Python environment (VM)

```bash
cd ~/devops-lab/ai-labs/code
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `netstat` shows `127.0.0.1:11434` | Ollama did not pick up `OLLAMA_HOST` | Kill all Ollama processes, start again |
| `curl` hangs / timeout | Windows firewall, network profile `Public` | `Set-NetConnectionProfile -InterfaceAlias "Ethernet" -NetworkCategory Private` |
| `curl` connection refused | Ollama not listening on the network | See step 4 |
| Worked yesterday, not today | Windows got a new IP from DHCP | Fritz!Box: always assign the same IPv4 address |
| `ollama ps` shows CPU | Model too big for VRAM | Use a smaller model |

## Experiment

Pull `gemma3:12b` and compare speed and answer quality with `gemma3:27b` on the same question.

## Notes

-
EOF

cat > ai-labs/02-embeddings.md << 'EOF'
# AI Lab 02 – Embeddings

## Goal

Understand how text becomes a vector and how "similar meaning" is measured.

## Concepts

- **Embedding:** a list of numbers (here 768) that represents the meaning of a text.
- **Cosine similarity:** how close two vectors point in the same direction.
  1 = same meaning, close to 0 = unrelated.
- Sentences with similar meaning get similar vectors even if they share almost no words.

## Steps

```bash
cd ~/devops-lab/ai-labs/code
source venv/bin/activate
python embeddings_test.py
```

## What to observe

- "slow" vs. "high response times" should score higher than "slow" vs. "backup failed".
- The coffee machine should be far from everything.
- The Slovak sentence is probably weakly linked to the English ones: `nomic-embed-text`
  is trained mainly on English. Language support matters when choosing a model for production.
- Scores do not use the full 0–1 range, typically 0.4–0.9. A similarity threshold must be
  tuned by experiment.

## Experiment

Add your own sentences (no company data) and see what the model considers similar.

## Notes

-
EOF

cat > ai-labs/03-pgvector-incident-memory.md << 'EOF'
# AI Lab 03 – PostgreSQL + pgvector: incident memory

## Goal

Store historical incidents with their embeddings in PostgreSQL using the pgvector extension.

## Concepts

- **No separate vector database:** pgvector adds a `vector` column type and similarity
  operators to regular PostgreSQL. Same design choice as SAITron.
- **What to embed:** a compact, normalized summary per incident, not raw logs.
  See `build_memory_text()` in `load_incidents.py`.
- **Store the model name** with each vector, so vectors can be regenerated if the model changes.

## Steps

### 1. Start PostgreSQL with pgvector

The image already contains PostgreSQL 16 and pgvector, no separate installation needed.

```bash
cd ~/devops-lab/ai-labs/code
docker compose up -d
docker compose ps
```

If `docker compose` is missing: `sudo apt install docker-compose-v2`.

### 2. Verify the extension

```bash
docker exec -it pgvector psql -U postgres
```

```sql
CREATE EXTENSION IF NOT EXISTS vector;
SELECT extversion FROM pg_extension WHERE extname = 'vector';
\q
```

### 3. Load incidents

```bash
source venv/bin/activate
python load_incidents.py
```

### 4. Inspect the data

```sql
SELECT sid, domain, db_type, title FROM incident_memory;
SELECT sid, left(embedding::text, 60) FROM incident_memory;
```

A vector really is just a long list of numbers.

## What to observe

Q11 (RFC + expired certificate) is semantically close to Q50 (backup + SSL) but belongs to
another domain. Lab 04 shows why deterministic filters matter.

## Cleanup

```bash
docker compose down        # stop, keep data
docker compose down -v     # stop and delete data
```

## Notes

-
EOF

cat > ai-labs/04-similarity-search.md << 'EOF'
# AI Lab 04 – Similarity search with filters and threshold

## Goal

Find similar historical incidents safely: deterministic filters first, then vector similarity,
then a minimum similarity threshold.

## Concepts

- `<=>` in pgvector is cosine distance, so `similarity = 1 - distance`.
- **Deterministic filters** (domain, database type) prevent "Oracle incident → HANA evidence".
- **Top N always returns something.** Without a threshold, irrelevant incidents look relevant.

## Steps and experiments

```bash
cd ~/devops-lab/ai-labs/code
source venv/bin/activate
```

1. Without filter – does Q11 show up?

   ```bash
   python search.py "Backup failed, backint SSL handshake error"
   ```

2. With filter – Q11 and the Oracle incident disappear:

   ```bash
   python search.py "Backup failed, backint SSL handshake error" backup HANA
   ```

3. Query outside the memory – results should be marked below threshold:

   ```bash
   python search.py "Printer on floor 2 is out of paper"
   ```

4. Paraphrase without shared words:

   ```bash
   python search.py "users complain everything takes forever" performance
   ```

## Tune the threshold

Compare scores of correct and wrong results and set the threshold between them.
No code change needed:

```bash
SIMILARITY_THRESHOLD=0.70 python search.py "Printer on floor 2 is out of paper"
```

## Notes

- Chosen threshold:
EOF

cat > ai-labs/05-rag-local-llm.md << 'EOF'
# AI Lab 05 – RAG with a local LLM

## Goal

Give the LLM similar historical incidents as clearly separated context, without letting it
treat history as proof.

## Concepts

- **RAG (Retrieval-Augmented Generation):** retrieve relevant data first, then let the LLM
  work with it.
- **Separation:** CURRENT EVIDENCE and HISTORICAL CONTEXT are separate sections of the prompt.
- **Guardrail in the system prompt:** similarity does not prove the same root cause.

## Steps

```bash
cd ~/devops-lab/ai-labs/code
source venv/bin/activate
python rag.py
```

The first call can take longer while the model loads into GPU memory.

## Experiments

1. **No history:** `SIMILARITY_THRESHOLD=0.99 python rag.py` – how much worse is the answer?
2. **No guardrail:** remove the "CONTEXT ONLY" sentences from `system_prompt`.
   Does the model start claiming the root cause is certainly the certificate?
3. **Different cause:** change the signals to "storage endpoint unreachable, connection timeout".
   Is D15 retrieved instead of Q50?
4. **Smaller model:** `LLM_MODEL=gemma3:12b python rag.py` and compare.

## Notes

-
EOF

cat > ai-labs/06-evaluation.md << 'EOF'
# AI Lab 06 – Evaluating retrieval

## Goal

Measure retrieval quality on a test set instead of relying on "it seems to work".

## Concepts

- Each test has a query and the incident that should be found. Two tests should find nothing.
- **Threshold too low:** irrelevant incidents are returned (false positives).
- **Threshold too high:** correct incidents are missed (false negatives).
- The same trade-off as precision vs. recall.

## Steps

```bash
cd ~/devops-lab/ai-labs/code
source venv/bin/activate
SIMILARITY_THRESHOLD=0.50 python eval.py
SIMILARITY_THRESHOLD=0.60 python eval.py
SIMILARITY_THRESHOLD=0.70 python eval.py
```

## Results

| Threshold | Score | Notes |
| --- | --- | --- |
| 0.50 |  |  |
| 0.60 |  |  |
| 0.70 |  |  |

## Extensions

- **Multilingual embeddings:** `ollama pull bge-m3` (1024 dimensions), then
  `EMBED_MODEL=bge-m3 EMBED_DIM=1024 python load_incidents.py` and test Slovak queries
  with the same variables.
- Add your own paraphrases to `TESTS` and find where search fails.

## Notes

-
EOF

echo
echo "Created:"
find ai-labs -type f | sort
echo
echo "Next: add the AI Labs section to README.md, then git add / commit."
