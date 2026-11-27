# Moving the agent from the home lab to Azure AI Foundry: brief and design

Purpose: this document describes what the home agent does, which guarantees it gives, and what the Foundry version must preserve. All companies,
contracts and numbers are made up (the fictional Modrá Banka a.s.). Result numbers come from `LAB_STATUS_AND_NEXT_STEPS.md`.
Things that depend on the current shape of Foundry (service names, deployment format, the VS Code extension) are
marked **[verify]**: check them against the current documentation before implementing; do not rely on this text.

---

## 1. What the agent does

Input: `company_id`, `period` (e.g. `C01`, `2026Q1`). Output: `breach`, `no_breach` or `human_review` with reasons
and steps. The agent checks loan covenants from the statement and the contract.

**Principle: the status is decided by verifiable code, not by the LLM.** The LLM only turns text into a constrained structure (JSON). Python verifies
and computes. Any failure in any of steps 1 to 5 ends as `human_review` with a reason; the agent never crashes on a model error.

| # | Step | Who | Code |
| --- | --- | --- | --- |
| 1 | `extract`: items from the statement (revenue, EBIT, depreciation, debt, cash …) | LLM | `rag_prompt.build_extract_prompts` |
| 2 | `check_items`: allowed names, numbers; **the number must be printed on the cited page of the statement** | code | `agent.check_items` |
| 3 | `retrieve`: contract excerpts from the vector DB (company is a mandatory filter) | code + embedding | `search.py` |
| 4 | `spec`: specification (EBITDA and debt definition, limits, waiver) as JSON | LLM | `rag_prompt.build_spec_prompts` |
| 5 | `verify`: `validate_spec` + `verify_sources` (every citation is checked in the complete documents) | code | `covenants.py`, `sources.py`, `contract_rules.py` |
| 6 | `evaluate`: ratios, comparison with the limit, waiver, a 2 % band at the limit → `human_review` | code | `covenants.evaluate` |

Modes (`agent.run(..., mode=)`): `rag` (default), `full` (all contract chunks, no search), `generic`
(generic rule without a contract, the LLM only extracts), `no_context` (specification without excerpts).

## 2. Security invariants (must not be weakened)

1. **The LLM never decides the status.** The status is produced only in `covenants.evaluate`.
2. **Numbers from the statement are verified in the text**: the model cannot supply a number that is not on the stated page.
3. **Every citation is verified in the complete documents** from a trusted store that the model does not choose. A document uploaded
   by a user must never reach `verify_sources` as trusted.
4. **Search is always restricted to the company** (`WHERE company_id = ...`; without it, `ValueError`). Analyst notes are
   not used as evidence. Whether a waiver exists is decided by document type, not by a similarity threshold.
5. **The parser for the article with limits is strict and fail-closed** (`contract_rules.contract_limits`): a foreign sentence in the financial
   article of the contract → `human_review`. **Do not relax it.** In T4, qwen38 once took over a limit of 6.0 from an injected sentence, and it was
   exactly this parser that stopped it.
6. **Text from the statement and the contract is data, not instructions.** The extraction prompt says so; the defence against an injected instruction in the contract
   rests on step 5 and the parser, not on the model.
7. **On any uncertainty, `human_review`**, never guessing.

## 3. Home lab results (baseline for comparison)

Dev set: 36 cases, 12 companies (C01 to C12); statuses 21 `no_breach`, 12 `breach`, 3 `human_review`.

| Test | Result |
| --- | --- |
| T3 whole chain | haiku 36/36; qwen3.8:27b 35/36 (C10-2026Q1 → safe `human_review`); 0 missed breaches, 0 false alarms |
| T5 repeatability | qwen38 359/360 correct case-runs (10 runs), haiku 108/108 (3 runs); never flipped `breach` ↔ `no_breach` |
| T1 extraction | 5,400 items, 0 errors (one statement template, no scans) |
| T4 attacks | 0 successful out of 378 cases; 72 of 378 cases ended as disrupted (`human_review`, ~19 %); always for an attack in the contract's financial article, where the parser blocks 100 %, plus occasional haiku refusals |
| T6 operations (36 cases) | haiku 93,377 / 31,448 tokens (input/output), ~4.3 s of LLM per case; qwen38 ~12.6 s |
| Azure `gpt` deployment, T3a | specification 36/36 (a different step than T3, but the same prompt) |

Without the contract (generic rule debt/EBITDA ≤ 4.00), 12 of 36 cases would go wrong; the check of this baseline is the `generic` mode.
Limitation: the data is generated from a single template; the results say nothing about real contracts or PDFs.

## 4. Mapping home lab → Azure

| Home lab | Azure / Foundry |
| --- | --- |
| Ollama (qwen38, bge-m3) | model deployments in Foundry; the `azure` profile already exists in `config.py` (LLM `AZURE_OPENAI_LLM_DEPLOYMENT`, embedding `text-embedding-3-small`, 1536 dimensions) **[verify]** |
| `pgvector-banka` (Docker, PG16 + pgvector, port 5433) | Azure Database for PostgreSQL with the pgvector extension (smallest change to `search.py`), alternatively Azure AI Search **[verify]** |
| `data/<company>/*.md` on disk | a trusted store (Blob Storage or files in the image); documents never from an uploaded file |
| keys in `.env` | Managed Identity and Key Vault; keys must never get into the repo or the image |
| `python agent.py C01 2026Q1` | an agent endpoint (see section 5) |
| Threshold `thresholds.json` | **the threshold is per embedding profile**; for `azure` it is 0.50 (recall 0.98, precision 0.60). When the model or chunking changes, T2 must be repeated |

The move must keep the chunking (`load_documents.py`, definitions split by numbered clause) and the same queries
(`agent.build_queries`); otherwise the threshold in `thresholds.json` does not apply.

## 5. Two deployment architectures

**A. The chain as a single tool.** The Foundry agent (or container) calls one tool `check_covenants(company_id,
period)`; the whole chain runs in our code and returns a structured result. The order of steps and the status are decided by code. The security
invariants are preserved with no extra work.

**B. A conversational model calls the individual steps as tools.** It can be just as safe **only if safety is enforced
on the tool side, not by the model**. Conditions:

1. The tools are stateful: `start_run(company_id, period)` returns a `run_id`; the other tools take only the `run_id`.
   Intermediate results (items, specification) live on the server. **The model never supplies numbers or a specification** to `evaluate`.
2. Each tool checks the previous step and refuses a run out of order or a repeat with different data.
3. `evaluate` is the only source of the status, and the result is returned as a structured object that the application displays **verbatim**,
   not as text that the model rewrites.
4. Tools with an LLM inside (`extract`, `spec`) call the model themselves. The conversational model is then just a router.
5. Do not return the raw text of the statement or the contract to the conversational model (a channel for injected instructions).
6. The `spec_refused` response contains up to 140 characters of model text; if the UI renders it, it must sanitise it (a channel for an attacker).
7. Foundry guardrails (content filters, protection against injected instructions) are an additional layer, not a replacement **[verify]**.

Without these conditions, B is weaker than the home lab: the order of steps would be decided by the model, and an injected instruction could change it.
With them, B in practice comes close to A (the model just calls the tools in the given order), so its value is mainly the conversational interface.
**Recommendation: A as the main version, B as an experiment.** For B, T4 (attacks) must be repeated and the order of calls must be checked too.

## 6. Comparison plan: "container" vs. "Foundry agent"

Same code, same data, same model; only the orchestration changes. Otherwise we would be measuring models, not architectures.

| Variant | Orchestration | Model |
| --- | --- | --- |
| V1 | home container (today's agent) | Azure model (the same as V3 and V4) |
| V2 | home container | local qwen38 / haiku (reference, already measured) |
| V3 | Foundry agent, architecture A | the same Azure model |
| V4 | Foundry agent, architecture B (with stateful tools) | the same Azure model |

Measure on the same cases (36 dev, then once on `data_test/`) and with the same scripts where possible
(`t3_chain.py`, `t5_stability.py`, `t6_ops.py`, `t4_attacks.py`):

- accuracy, missed breaches (target 0), false alarms, share of `human_review`;
- repeatability (T5, at least 3 runs, for B also the order of calls);
- attacks (T4, sets A and F; headline number = count of successful attacks, target 0);
- latency and tokens per case, cost (T6);
- for B additionally: number of cases where the model skipped a step, called steps out of order, or returned a different status than the tool.

Acceptance criterion for the Foundry version: **0 missed breaches and 0 successful attacks**, accuracy no worse than V1, and
every deviation from V1 explained. Do not use `data_test/` for tuning; it is a one-time set.

## 7. Order of work

1. Finish the home lab (step E mode comparison, step H final runs) and freeze the prompt (`PROMPT_VERSION`, hash in `meta`).
2. Run the existing tests with `LLM_PROFILE=azure EMBED_PROFILE=azure` without deploying (a quick proof that the code works on Azure models).
3. Move the vector database and repeat T2 with the Azure embedding and a threshold of 0.50.
4. Package the agent (Dockerfile, `thresholds.json`, model configuration through environment variables) and deploy it.
5. Foundry version A, then (optionally) B; comparison according to section 6.

## 8. What can and cannot be claimed

Can: the same chain with verification gives the same security number regardless of the model, as long as the code stays unchanged.
Cannot: that the Foundry version is safe until it passes T4 and T5 in Foundry itself (do not carry this over from the home lab); that the results
apply to real contracts; that B is as safe as A without measuring it.
