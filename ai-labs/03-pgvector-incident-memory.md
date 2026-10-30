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
source .venv/bin/activate
python load_incidents.py
```

### 4. Inspect the data

```sql
SELECT sid, domain, db_type, title FROM incident_memory_nomic;
SELECT sid, left(embedding::text, 60) FROM incident_memory_nomic;
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

### Recorded environment and expanded dataset

The completed experiment used PostgreSQL 16 with pgvector 0.8.7 in an existing `pgvector`
container created with `docker run`. For that environment, use `docker start pgvector`;
the Compose steps above describe the original setup option.

The original 12-case exercise grew to 200 fictional incidents, INC-0001 through INC-0200:
139 HANA and 61 Oracle. Domains include performance, backup, database, interface, os,
security, jobs and basis. Each profile has its own `incident_memory_<profile>` table.
The stored embedding text includes domain, database, title, evidence and resolution;
text and incident metadata remain available alongside the vector.

| Profile | Dimensions |
| --- | ---: |
| nomic / nomic_prefix | 768 |
| bge | 1024 |
| qwen / qwen_instr | 2560 |
| qwen8 | 4096 |
| gemini / azure | 1536 |

Query vectors must come from the matching profile. Reload documents when changing how their
embedding text is constructed. Keep the model name and embedding text to make regeneration
possible. For example, inspect the BGE table using:

```sql
SELECT count(*) FROM incident_memory_bge;
SELECT embedding_model, vector_dims(embedding), count(*)
FROM incident_memory_bge GROUP BY 1, 2;
```

[Lab 06](06-evaluation.md) evaluates this memory. Separate investigation records and agent
tool execution remain a future phase.

## Notes

-
