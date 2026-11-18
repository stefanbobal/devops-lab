# AI Platform Gateway (LiteLLM Proxy)

One OpenAI-compatible endpoint in front of the local Ollama models. Clients know only
the gateway URL, an API key and a model **alias**. They never see the backend model
name or the Ollama address.

```
 client (OpenAI SDK)                 Ubuntu VM                                  Windows host
 ───────────────────   ┌──────────────────────────────────────────┐   ┌──────────────────────┐
 smoke_test.py ──────► │ litellm-gateway :4000 (127.0.0.1 only)   │──►│ Ollama :11434        │
 rag_test.py (later)   │   aliases: local-fast, local-quality     │   │ llama3.1:8b          │
                       │        │ spend logs, keys (Prisma)       │   │ qwen3.6:27b (RTX4090)│
                       │        ▼                                 │   └──────────────────────┘
                       │ pgvector (PostgreSQL 16)                 │
                       │   DB postgres  → RAG data, llm_eval      │  (untouched)
                       │   DB litellm   → gateway only, own role  │
                       └──────── docker network llm-homelab ──────┘
```

| Alias | Backend | Notes |
|---|---|---|
| `local-fast` | `ollama_chat/llama3.1:8b` | ~6 GB VRAM, short answers |
| `local-quality` | `ollama_chat/qwen3.6:27b` | ~17 GB VRAM, thinking model (`reasoning_content`) |

Both use `num_ctx: 8192`, the same context as the RAG benchmark (`rag_test.py`).

## Setup (once)

Prerequisites: the `pgvector` container and the Docker network `llm-homelab` exist,
and Ollama on Windows listens on `0.0.0.0:11434` (see [../01-local-llm-ollama.md](../01-local-llm-ollama.md)).

1. Secrets: `cp .env.example .env` and replace every `CHANGE_ME` with a random value.
2. A separate database and role for LiteLLM, on the existing PostgreSQL server
   (the password is read from `.env`, never typed or printed):

   ```bash
   set -a; . ./.env; set +a
   docker exec -i pgvector psql -U postgres -v ON_ERROR_STOP=1 -v pw="$LITELLM_DB_PASSWORD" -q <<'SQL'
   CREATE ROLE litellm LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'pw';
   CREATE DATABASE litellm OWNER litellm;
   SQL
   ```

   The role `litellm` owns only the database `litellm`. It cannot read the RAG tables
   (`permission denied for table incident_memory_nomic`).
3. Start: `docker compose up -d`. On first start LiteLLM runs its Prisma migrations in
   the `litellm` database. It takes about 40 s until the container is `healthy`.

## Phase 1: smoke test

```bash
cd ~/devops-lab/ai-labs/ai-platform-gateway
../code/.venv/bin/python smoke_test.py --model local-fast
../code/.venv/bin/python smoke_test.py --model local-quality
```

Steps: `GET /health/liveliness` (no key), `GET /v1/models` (with key), and one chat
completion through the OpenAI SDK with `base_url=http://127.0.0.1:4000/v1`.

Measured on 2026-11-18 (LiteLLM v1.108.11, Ollama 0.40.16):

| Call | Latency | Why |
|---|---|---|
| `local-fast`, first call | 32.2 s | model loaded into VRAM (cold start) |
| `local-fast`, next call | 0.6 s | model already loaded |
| `local-quality`, first call | 16.3 s | 27B model loaded, `llama3.1:8b` evicted |
| `local-fast` after `local-quality` | 4.6 s | `llama3.1:8b` loaded again |

Findings:
- `qwen3.6:27b` thinks before it answers. Reasoning tokens count against `max_tokens`:
  with `max_tokens=100` the answer was empty (`finish_reason=length`). A one-sentence
  answer used 438–530 completion tokens. LiteLLM returns the thinking in a separate
  `reasoning_content` field.
- Ollama ran each model with `context_length 8192` (checked with `/api/ps`), so
  `num_ctx` from `config.yaml` reaches Ollama.
- Gateway container memory: about 730 MiB.

## Security defaults

- Port 4000 is published on `127.0.0.1` only.
- `STORE_MODEL_IN_DB=False`: models come only from `config.yaml`, which is reviewed in git.
- `turn_off_message_logging: true` and `store_prompts_in_spend_logs: false`: the spend
  log keeps metadata (alias, backend model, tokens, time, cost), not the message text.
  Checked: 6 rows in `LiteLLM_SpendLogs`, 0 with messages, 0 with a response.
- Secrets live only in `.env` (gitignored). Checked: none of them appear in `docker logs`.

## Operations

```bash
docker compose ps                      # health
docker compose logs -f litellm         # JSON logs
docker compose restart litellm         # after editing config.yaml
docker compose down                    # stop; never use -v
```
