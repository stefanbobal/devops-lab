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
