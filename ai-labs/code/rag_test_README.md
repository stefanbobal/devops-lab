# RAG matrix evaluation

`rag_test.py` runs every selected LLM against every selected embedding profile,
using `thresholds_FROZEN.json`. The default is **dry run**, with no model or database calls.
The six bundled scenarios are development examples, **not a held-out benchmark**.
The proposed 12-development/48-held-out evaluation dataset still needs to be curated.

## Start on the Ubuntu VM

```bash
cd ~/devops-lab/ai-labs/code
source .venv/bin/activate
git pull --ff-only
# Update .env too if it still overrides the old Flash identifier.
export VERTEX_LLM_MODEL=gemini-3.1-flash-lite
export VERTEX_LLM_LOCATION=global
python -m unittest -v test_rag_benchmark
python rag_test.py

# Small end-to-end probe: at most two LLM calls, plus retrieval for those scenarios.
python rag_test.py --embeddings gemini --llms gemini,azure \
  --max-calls 2 --out results/rag-smoke --execute

# Resume the same configuration; completed or failed requests are not repeated.
python rag_test.py --embeddings gemini --llms gemini,azure \
  --out results/rag-smoke --execute --resume
```

The SDKs already used by `providers.py` are required. The measured Vertex adapter also
requires `google-genai` with `HttpOptions.retry_options`/`HttpRetryOptions` support.
Missing packages or unavailable models are recorded as errors, never silently replaced.
Flash-Lite replaces Flash in the `gemini` LLM profile; this new identifier still needs
a real VM smoke test. The `gemini` **embedding** profile remains `gemini-embedding-001`.

Full default development matrix: **6 scenarios × 8 embeddings × 10 LLMs = 480 LLM calls**.
It retrieves only **48 contexts**, reusing each context across LLMs and repetitions.
Add `--execute --out results/rag-dev` to run it. API usage is billable.
Use `--repeats 3` for three independent generations, or `--llms`/`--embeddings`
with comma-separated profile names to select a subset.

## What gets measured

| Field | Meaning |
| --- | --- |
| `input_tokens`, `output_tokens` | Actual provider usage counts, not character-based estimates |
| `reasoning_tokens` | Separate reasoning count where reported; output includes billable reasoning |
| `cached_input_tokens`, `cache_creation_tokens` | Cache usage when returned by the API |
| `usage_raw` | Original usage metadata, retained in each call JSON |
| `retrieval_latency_s` | Query embedding plus database search; measured once per frozen context |
| `llm_latency_s` | Non-streaming call wall time, including SDK/client setup, network and model execution |
| `worker_wall_s` | Worker startup/imports plus the operation; available for errors and timeouts too |
| `pipeline_latency_estimate_s` | Retrieval measurement + LLM measurement; reconstructed, not a new end-to-end observation |
| `output_tokens_per_wall_second` | Output count divided by LLM call time; includes reasoning where counted |
| `load_duration_s`, `generation_tokens_per_second` | Ollama model loading and engine generation throughput |
| `estimated_cost_usd`, `cost_status` | LLM API cost estimate and whether it is known |

This is **not streaming**: time to first token is not measured. Cloud generation-only
speed is not exposed here. Ollama reports generation duration separately in nanoseconds,
which the adapter converts to seconds. Cold/warm/cache effects remain in the observations;
inspect load/cache fields rather than assuming every call is warm.

Azure completion tokens already include reasoning: do not add reasoning a second time.
Vertex output accounting adds candidate and thought tokens. Anthropic total input sums
uncached input, cache reads and cache creation. Provider defaults for temperature/reasoning
are retained; a common output cap of 4096 is requested (provider cap semantics differ).
Use `--max-output-tokens` to change it. Truncation, refusal, empty content and other
non-success finish reasons are saved as `incomplete`, with their usage retained.

## Pricing and limits

`llm_prices.json` contains the user's supplied **USD per million tokens** rates.
These are estimates, not verified contract prices or invoices. Azure pricing can differ
from standard OpenAI rates. Exact `provider:model` keys prevent accidentally using the
wrong price when a model/deployment is overridden. Add a matching key for renamed Azure
deployments. The manifest snapshots the full rate table used by the run.

Without caching, cost = input_tokens × input_rate / 1,000,000 + output_tokens × output_rate / 1,000,000.
For Haiku the entire call switches to the upper tier when total input exceeds 100,000 tokens.
Optional `cached_input_per_million` and `cache_creation_per_million` rates price those
categories separately; a nonzero cache count without its rate produces **unknown cost**,
not a guessed zero. Mixed cache-write TTL prices are not supported by this simple rate table.
Local API fee is zero; local electricity and hardware are not priced.

The Argon rates ($4 input / $20 output) start **2026-12-01**. Runs priced before that date
show `price_outside_effective_dates`. A separate run with `--pricing-date 2026-12-01`
is a hypothetical future-price calculation, not today's bill. Effective dates for the
other user-provided rates begin on 2026-10-30, when the table was supplied.

Query embedding cost, original corpus embedding, database/storage, tax and network fees
are **excluded**. No total pipeline dollar cost is claimed. Missing API usage and failed
or timed-out requests may still incur charges; reconcile with provider billing.
`--max-calls` caps new LLM requests, not dollars or retrieval requests. There is no hard
spend cap. `--timeout` defaults to 180 seconds per operation; killing a local worker does
not guarantee that the remote provider stopped processing/billing the request.

## Files and resuming

- `manifest.json`: model configuration, SDK versions, code hashes, thresholds, scenarios,
  prices, seed and generation settings. No API keys are included.
- `contexts/*.json`: retrieved candidates, similarities, selected history and exact context.
- `calls/*.json`: full prompts, answers, status, token counts, timings and cost per call.
- `results.csv`: spreadsheet-friendly export, with multiline answers quoted correctly.
- `summary.json`: counts, successful-call p50/p95 latency by LLM/embedding/mode, sum of
  known LLM costs and count of calls whose costs are unknown. Quantiles use nearest rank.
- `quality_review.csv`: blank human-scoring sheet; existing scores survive resume.

Requests are sequential in a seeded shuffled order. Profiles run in isolated subprocesses
so module-level configuration cannot leak from one model to the next. A context is retrieved
only once per scenario/embedding and saved. Resume validates the manifest fingerprint;
changed settings, prices, scenarios, code or SDK versions require a new output directory.
Do not change the corpus during a run. Resuming reuses saved contexts, while contexts not
yet fetched still come from the live database. The database itself is not snapshotted.

Automatic SDK retries are disabled for measured LLM calls. Completed, incomplete, failed
and pending records are all skipped on resume. A pending record means execution was
interrupted and the charge/result is uncertain. To deliberately retry failed work, use a
new output directory and a narrowed scenario/profile selection; retain both runs for costs.
The `.running` lock prevents simultaneous writers. After a hard crash, remove it only
after checking that the prior process has stopped. JSON results are persisted per call;
CSV/summary exports refresh at the end of a normal invocation, including a resumed one.

## Scenario format and quality evaluation

Pass `--scenarios my_scenarios.json` with a nonempty JSON list:

```json
[
  {
    "id": "unique-scenario-id",
    "incident": "Current evidence, including what is not yet known",
    "domain": "backup",
    "db_type": "HANA",
    "review_guidance": "Expected checks, forbidden assumptions and critical errors",
    "curated_context": "Optional manually selected reference history"
  }
]
```

`domain` and `db_type` are optional deterministic filters; use actual values from the
database or null. `review_guidance` is retained for reviewers and **never sent to the LLM**.
Use `--modes rag,no_history` to compare retrieval against no history. `curated` mode requires
`curated_context` in every scenario. Controls run once per scenario/LLM/repetition, rather
than once for each embedding profile. Thus the default six-scenario matrix plus no-history
controls has 540 calls per repetition.

The runner does not equate a successful API response with a correct investigation.
Review each answer against current evidence and the saved history. Score 0 (wrong/missing),
1 (partly useful) or 2 (correct/useful) for relevance, evidence handling, citation correctness,
uncertainty and actionability. Mark `critical_error` for unsupported certainty or unsafe
destructive recommendations. Review blinded model identities where possible. Human scores
are not yet aggregated automatically. Do not select the best RAG on latency or cost alone.

Before a portfolio-grade evaluation, freeze a separate held-out scenario set and rubric,
record exact Ollama digests/quantization, run multiple repetitions and verify cloud model
versions. This runner records returned model identifiers but does not pin provider versions.

## Offline verification and API references

```bash
python -m unittest -v test_rag_benchmark
```

Tests use simulated API responses and validate pricing tiers/dates, token normalization,
incomplete responses, shared contexts, dry runs and resume behavior. They do not establish
live SDK compatibility or service availability; the Ubuntu smoke run does that.

- [Ollama chat metrics](https://docs.ollama.com/api/chat)
- [Vertex response usage](https://cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/GenerateContentResponse)
- [Google Gen AI SDK retry options](https://googleapis.github.io/python-genai/genai.html)
- [Anthropic cache token accounting](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Azure chat reference](https://learn.microsoft.com/en-in/azure/foundry/openai/latest?view=foundry-classic)
