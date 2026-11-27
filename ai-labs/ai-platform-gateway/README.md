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

## Phase 2: model routing

| Alias | Backend | Fallback |
|---|---|---|
| `local-fast` | `ollama_chat/llama3.1:8b` | – |
| `local-quality` | `ollama_chat/qwen3.6:27b` | → `local-fast` |
| `local-gemma` | `ollama_chat/gemma3:27b` | – |
| `cloud-quality` | commented out in `config.yaml` (lab stays local and free) | – |

```bash
../code/.venv/bin/python routing_demo.py aliases    # same code, three aliases, load times
../code/.venv/bin/python routing_demo.py errors     # unknown alias

# fallback: point only local-quality at a dead port inside the container, then restore
LOCAL_QUALITY_API_BASE=http://127.0.0.1:9 docker compose up -d
../code/.venv/bin/python routing_demo.py fallback
docker compose up -d
```

`mock_testing_fallbacks` cannot be used for this: since v1.85.0 the proxy strips it from
requests. The demo therefore breaks a real backend.

### Results (2026-11-18)

**Same client code, same schema.** One function `ask(client, alias)`; only the alias string
changes. Every response has the same top-level fields
(`choices, created, id, model, object, usage`) and `model` is the alias, not the backend.
Only the thinking model adds `message.reasoning_content`.

**Model switching.** Ollama keeps one model in VRAM at a time, so every alias switch evicts
the previous model:

| # | Alias | Latency | VRAM after |
|---|---|---|---|
| 1 | local-fast | 3.31 s (load) | llama3.1:8b 6.0 GB |
| 2 | local-fast | 0.23 s | llama3.1:8b 6.0 GB |
| 3 | local-quality | 14.71 s (load) | qwen3.6:27b 17.2 GB |
| 4 | local-quality | 9.39 s | qwen3.6:27b 17.2 GB |
| 5 | local-gemma | 21.50 s (load) | gemma3:27b 17.5 GB |
| 6 | local-gemma | 0.54 s | gemma3:27b 17.5 GB |
| 7 | local-fast | 4.32 s (load) | llama3.1:8b 6.0 GB |
| 8 | local-fast | 0.37 s | llama3.1:8b 6.0 GB |

The warm `local-quality` call still takes 9 s: it produced 824 completion tokens, most of
them reasoning. With the thinking model, latency comes from generated tokens, not from loading.

**Unknown alias** → HTTP 400, `openai.BadRequestError`, type `invalid_request_error`:
`Invalid model name passed in model=gpt-unknown. Call /v1/models to view available models for your key.`

**Fallback** (local-quality backend down):

| Request | Result |
|---|---|
| normal | answer in 1.57 s; headers `x-litellm-model-group: local-fast`, `x-litellm-attempted-fallbacks: 1` |
| `disable_fallbacks: true` | HTTP 500, `openai.InternalServerError`, `litellm.APIConnectionError: Ollama_chatException - Cannot connect to host REDACTED:9` |

Findings:
- A fallback silently changes the quality: the client asked for the 27B model and got the 8B
  answer with HTTP 200. Only the response headers show it. A client that cares (or an
  evaluation) must read `x-litellm-attempted-fallbacks`.
- After a fallback, `response.model` is the backend name `ollama_chat/llama3.1:8b`, not
  an alias. In the normal case the backend name is hidden.
- In the error, LiteLLM masks the backend host (`REDACTED`) but the provider type is visible.
- `num_retries: 0`: with a dead backend, retrying the same deployment only adds latency.

## API docs in dark mode (cosmetic)

`/docs` is the stock Swagger UI of LiteLLM. `docs-theme/saitron-dark.css` restyles it in a calm
"modern dark" look: one hue for all surfaces, colour only for the HTTP method (left edge + label),
Inter for text, monospace for paths and JSON. No change to the API.

```bash
./docs-theme/build.sh       # stock CSS from the pinned image + theme -> docs-theme/swagger-ui.css (gitignored)
docker compose up -d        # the file is mounted read-only over the stock swagger-ui.css
```

Run `build.sh` before the first `docker compose up` (otherwise Docker creates an empty directory
at the mount path) and again after a LiteLLM upgrade. Browser: Ctrl+F5 to skip the cached CSS.

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
