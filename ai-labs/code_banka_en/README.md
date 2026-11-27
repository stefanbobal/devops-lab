# code_banka: loan covenant monitoring agent

Home lab. **All companies, contracts, statements and numbers are made up.**
No real client data and no company code.

**Status (2026-11-09):** the agent, tests T1 to T6, three ways of working with the contract, attacks, repetition,
the evaluation of the locked test set and a run on an Azure model are all done. Detailed status, numbers and findings are in
`LAB_STATUS_AND_NEXT_STEPS.md`, an overview in `LAB_FINAL_DOCUMENT.md`, and the plan for moving to Azure AI Foundry in `FOUNDRY_PORT.md`.
The text below describes the original brief and design; where reality differs, it is noted.

## Use case

A bank finances companies. The loan agreement contains conditions (covenants), for example
"net debt / EBITDA ≤ 4.0". Every quarter the company sends financial statements, which today
an analyst retypes and checks by hand. The agent prepares this check and hands the analyst
only the cases that need attention.

## Architecture

- **Agent = our own Python code in a Docker image.** Calculations, checks, routing and evaluation
  live in our code, so results are comparable across models.
- **Models from Azure AI Foundry** (e.g. `gpt-5-mini` and one larger model), or alternatively **local Ollama**.
  Only the LLM profile changes; the rest of the pipeline stays the same.
- This matches the "own agent platform + models from Foundry" model.
- Foundry Agent Service is an optional bonus at the end, not the basis of the test.
- **The final status is decided by verifiable code, not by the LLM.** The LLM extracts data, turns contract text
  into a structured specification with citations, and writes the explanation. Computing the ratio, comparing it
  with the limit and the `breach` / `no_breach` / `human_review` status are decided by Python, which can be tested.
- Routing to a human is decided by **rules in code**, not by the confidence the LLM reports about itself.

## 1. Test data (`data/`)

Actual state: **12 made-up companies** (the plan was 10–12). For each one:

- **loan agreement** (10 articles): definitions (EBITDA, net debt), covenants with limits,
  for some a limit that changes over time (step-down), reporting obligation, procedure on breach;
- **3 quarterly statements** (2026Q1–Q3) as Markdown tables (the plan was 2–4; PDF is a later extension);
- depending on the scenario an **amendment**, a **waiver letter**, and always **analyst notes**.

The data is split into two sets:

- **dev** (`data/`, 12 companies, 36 cases): used to tune chunking, queries and thresholds;
- **test** (`data_test/`, 6 companies C13–C18, 18 cases): locked, evaluated once at the end.
  It has a different contract structure (shuffled article order, 12 articles) and different combinations, but the same sentence wording,
  so that the strict verifier (`contract_rules.py`) can handle it. Tuning on it is not allowed.

`data/expected.json`: for every test case the correctly extracted values, the computed ratio,
the contract specification, the final status (`breach` / `no_breach` / `human_review`) and the cited articles.

Case types (actually 36; the plan was 30–40; exact breakdown in `data/SUMMARY.md`):

| Type | What it tests |
| --- | --- |
| simple OK / simple breach | the basics |
| custom EBITDA definition in the contract | whether the agent fails without RAG |
| limit changed over time | picking the right period |
| waiver granted by the bank | a breach that is not acted on |
| value exactly at the limit | comparison precision |
| missing or unreadable number | must go to a human |
| prompt injection in the statement | security |

About half of the cases must be built so that they go wrong without the contract.
Otherwise the comparison with and without RAG shows nothing.

### Generated data

```bash
python generate_data.py            # dev set: overwrites data/ (seed 20261101)
python generate_data.py --set test # locked test set: overwrites data_test/ (seed 20261201)
```

- `data/companies/<Cxx>/`: `smlouva.md` (contract), optionally `dodatek_1.md` (amendment) and `waiver_<period>.md`,
  `poznamky_analytika.md` (analyst notes), `vykaz_2026Q1–Q3.md` (statements; pages marked `[strana N]`);
- `data/expected.json`: correct items with pages, contract specification with citations, result,
  status under the generic rule and the `fails_without_contract` flag;
- `data/scenarios.json`: the format for `rag_test.py` (`incident` = statement, `curated_context` = all of the client's documents);
- `data/generic_rule.md`: the generic rule for the no-contract mode;
- `data/SUMMARY.md`: overview of the 36 cases (12 companies × 3 quarters); `data_test/` has its own set of the same files.

Status: 21 `no_breach`, 12 `breach`, 3 `human_review`. In 12 cases the generic rule
(`data/generic_rule.md`) gives a different status than the contract. This is a **comparison of two deterministic rules**,
not a measured LLM failure; the real behaviour of models without the contract is shown only by test T3.
The share is not artificially inflated to make RAG look better.
In addition, C10-2026Q2 fails if RAG finds the contract but not the amendment. C04 has a misleading
client claim in the analyst notes, C06 a waiver request that has not been granted yet.
Numbers and expected results are computed by code; `test_generate_data.py` checks determinism,
agreement with `covenants.py`, and that the cited article lies on the cited page. Never edit
the documents by hand, only through the generator. The generator deletes only a folder it created itself
(marker `.generated-by-generate_data`); it will not delete someone else's non-empty folder or a folder with code.

## 2. Loading into the vector DB (`load_documents.py`, done)

- Contracts and amendments are split **by article**; the "Definice a výklad" (definitions) article is further split **by numbered clause**
  (2.1 to 2.6), because one chunk with 6 definitions made retrieval worse (see `T2_retrieval_embeddings.md`).
  The `SPLIT_DEFINITIONS=0` switch restores article-level chunking. Waivers and notes are one chunk per document.
  Statements are not loaded; they are the agent's input.
- Metadata: company, document, document type, article, clause (`clause`), page. Validity from–to is not stored in the DB;
  `sources.py` checks it from the full text.
- Tables `covenant_docs_<profile>`; a dedicated `pgvector-banka` container on port 5433.
- A fixed SQL filter by company (mandatory) and optionally by document type, and only then vector search (`search.py`).
- **3 embedding profiles:** `azure` (`text-embedding-3-small`, 1536), `gemini` (`gemini-embedding-001`, 1536,
  Vertex) and `bge` (`bge-m3`, 1024, local Ollama).
- The dev and test sets are loaded into the same tables (the companies have different IDs). Loading is not evaluation.
- Thresholds: calibrated on the dev set only (`t2_retrieval.py`); `sweep_eval.py` is still from the incident lab.

## 3. Agent steps

First work out **what** to compute and **under which definition**, and only then compute it.

1. **Extract items from the statement (LLM):** JSON with the individual items (revenue, operating profit,
   depreciation, one-off costs, debt, cash…) and the page where each was found.
   **Not the company's ready-made EBITDA**, because the contract definition may be different.
2. **Check the items (Python):** schema, totals, missing fields.
3. **Search the contract (RAG):** definition of EBITDA and net debt, the limit valid for the period,
   waivers, analyst notes.
4. **Contract specification (LLM → JSON):** a structured rule built from the retrieved text, for example
   `{"ratio": "net_debt/ebitda", "ebitda_adds_back": ["one_off_restructuring"], "limit": 4.5,
   "valid_from": "2026-01-01", "valid_to": "2026-12-31", "waiver": null, "citations": [{"article": "7.2", "page": 4}]}`.
   Values are chosen only from a fixed list of allowed items.
5. **Verify the specification (Python):**
   - `covenants.validate_spec`: items only from the allowed list and without duplicates, the limit is a finite
     positive number, no two covenants with the same id, every waiver has a citation and a valid period;
   - `sources.verify_sources`: the cited document exists, the cited article lies on the cited page,
     both the EBITDA and the debt definition match a supported text pattern (`contract_rules.py`),
     the limit belongs to a specific covenant and to the tested period, including a supplied effective amendment.
     The specification must contain every contract covenant exactly once. A waiver must cite a document that explicitly grants it
     ("prominuje", i.e. waives) for the given Deň testování (test date); analyst notes are not evidence of a waiver or a limit.
   Anything unverified → `human_review`. A made-up waiver therefore cannot turn `breach` into `no_breach`.
   The text checks are tailored to the format of the generated documents; real documents would need
   more robust verification (e.g. a structured waiver register).
   The call `verify_sources(spec, documents, period)` needs the tested period.
   The validator receives the complete source documents of one company, not just the excerpts the LLM picked;
   the list of documents must be assembled by the application from a trusted store. An omitted amendment
   cannot be detected just from its absence in this list. Unknown definitions, clauses,
   a missing period, or several amendments without supported precedence rules lead to `human_review`.
6. **Calculation and status (Python, `covenants.py`):** build EBITDA according to the specification, compute the ratio,
   compare with the limit, apply a waiver → `breach` / `no_breach`.
7. **Rules for `human_review` (Python):** an item is missing or is not a finite non-negative number
   (only EBIT may be negative), the specification or the sources failed verification,
   an unreadable document, a result in the band close to the limit, a conflict between articles.
8. **Explanation (LLM):** a clear justification with citations. It does not change the status; code checks
   that the explanation states the same status and only citations from the specification.
9. **Action:** a task for the analyst. In the lab simulated by writing to a table; the agent has no other tools
   or permissions (least privilege).

**Implementation (`agent.py`):** steps 1 to 7 are done (in code they are the steps `extract`, `check_items`, `retrieve`, `spec`,
`verify`, `evaluate`). Step 8 (LLM explanation) and step 9 (action) were **not implemented**: the agent returns the status, the reasons and all
intermediate steps, which is enough for testing. The `mode` parameter selects the source of contract text: `rag`, `full`, `generic`, `no_context`.

## 4. Tests

| # | Test | Metric | Script | Status |
| --- | --- | --- | --- | --- |
| T1 | extracting items from the statement | share of correct fields (correct / missing / invented / wrong number) | `t1_extraction.py` | done (dev and test) |
| T2 | retrieval | correct article in top-k, for each embedding profile | `t2_retrieval.py` | done (dev and test) |
| T3a | contract specification from retrieved text | correctness of the specification and citations | `t3_spec.py` | done (dev and test) |
| T3 | the whole chain, status against `expected.json` | correct status, missed breaches, share of `human_review` | `t3_chain.py` | done (dev and test) |
| T4 | attacks in documents | did the status, numbers or specification change? | `t4_attacks.py` | done |
| T5 | repetition | stability of status and specification | `t3_chain.py --repeats`, `t5_stability.py` | done |
| T6 | operations | tokens, latency, cost | `t6_ops.py` | done |

Ways of working with the contract (T3, `t3_chain.py --mode`):

| Mode | What the model gets | Note |
| --- | --- | --- |
| `rag` | excerpts from vector search | the normal agent |
| `full` | all chunks of the company's contract, amendment and waiver, no search | without analyst notes |
| `generic` | no contract; the generic rule debt/EBITDA ≤ 4.00 | deterministic baseline, the LLM only extracts the statement |
| `no_context` | specification without excerpts | shows whether the model refuses or makes things up |

Because the status is computed by code, every status error can be attributed to a specific step:
a wrong item (T1), an article not found (T2) or a wrong specification (T3). `covenants.py` has its own
unit tests with known inputs and outputs (169 unit tests in total).

**A missed breach** (the agent says `no_breach`, the correct answer is `breach`) is reported separately.
For a bank it is the worst error, worse than a false alarm.

Models: local (qwen3.8:27b, gemma3:27b), cloud (claude-haiku-5-5, Azure OpenAI).
The test set `data_test/` is locked: the scripts refuse it without `--final`.

## 5. Operations and platform

Done:
- Every agent step is written into the result (status, time, tokens and latency from the provider's data).
- Every result file has a `meta` record: prompt version and hash, models, threshold, vector table state and git commit (`run_meta.py`).
- Results are never overwritten (mandatory `--tag`).

Remaining (not started): OpenTelemetry traces exported to Application Insights, agent configuration in versioned YAML,
GitHub Actions with a regression evaluation on every change, deployment to Azure AI Foundry (`FOUNDRY_PORT.md`).

## 6. Presenting the results

- one results table (3 modes × models);
- 2–3 failures taken apart: what happened, why, and what changed;
- a short live demo of one run with its trace.

## Order of work

1 (data) → 3 (agent) → T3 (the core of the story) → T1, T2, T4–T6 → 5 (operations) → 6.

## What was taken from `../code`

Usable without changing content (shared engine): `config.py`, `providers.py`, `llm_metrics.py`,
`rag_test.py`, `test_rag_benchmark.py`, `check_cloud.py`, `llm_prices.json`, `requirements.txt`,
`docker-compose.yml`.

Taken **only as a skeleton, still incident-oriented and in need of a rewrite** (see TODO):

- `rag_prompt.py`: the original incident functions remain because of `rag_test.py`; this lab's prompts (extraction, specification, version P3) were added;
- `sweep_eval.py`: still loads tests from `eval.py`, which does not exist here (replaced by `t2_retrieval.py`);
- `rag_test.py`: the default `rag_scenarios.json` and `thresholds_FROZEN.json` do not exist here.

`search.py` has already been rewritten (filter by company and document type). In addition, `lab.sh`,
`lab_start.py`, `lab_start_README.md` and `test_lab_start.py` were copied from `../code`; they check the `pgvector-banka` container (port 5433).

`requirements.txt` comes from the shared engine: `openai` is used for Azure OpenAI and Foundry,
`ollama` for local models; `anthropic` and `google-genai` serve the Claude and Gemini profiles
from the incident lab, which this lab does not use yet.

Changes compared with the original:

- embedding profiles narrowed to 3 (`azure`, `gemini`, `bge`);
- tables `covenant_docs_<profile>`, not `incident_memory_<profile>`, so they do not touch the incident lab;
- own DB: the `pgvector-banka` container on port **5433**, `PG_DSN` matches the password from `docker-compose.yml`;
- `load_threshold` moved from `rag.py` to `thresholds.py` (the incident demo `rag.py` is not copied);
- the tests create their own temporary thresholds file.

Deliberately **not taken**: incidents, scenarios, test questions, thresholds and results.

## TODO

Done: data and generator (dev, locked test set, attacks), chunking and the vector database, `search.py` with thresholds,
`covenants.py`, `sources.py`, `contract_rules.py`, prompts, `agent.py` (four modes), tests T1 to T6, evaluation of the locked
set, reproducibility record, run on an Azure model.

- [ ] hosted agent in Azure AI Foundry, vector database in Azure (`FOUNDRY_PORT.md`)
- [ ] OpenTelemetry, YAML agent configuration, GitHub Actions with a regression set
- [ ] Docker image and a UI (optional)
- [ ] Azure model prices in `llm_prices.json` (T6 does not compute them yet)
- [ ] result explanation (step 8) and action (step 9), if needed
- [ ] adapt or remove `rag_test.py`, `sweep_eval.py` (leftovers from the incident lab)

## Running

```bash
cd ~/devops-lab/ai-labs/code_banka_en
source .venv/bin/activate     # this lab's own venv
docker compose up -d          # own DB on port 5433
docker exec pgvector-banka psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector"   # once
bash lab.sh                   # lab check; expected result: Lab ready.
python generate_data.py       # on the VM, not in OneDrive on Windows
python generate_data.py --set test
for p in bge azure gemini; do EMBED_PROFILE=$p python load_documents.py; done

LLM_PROFILE=qwen38 python agent.py C01 2026Q1                  # one case
LLM_PROFILE=haiku python t3_chain.py --tag my_run              # T3, all 36 cases
LLM_PROFILE=haiku python t3_chain.py --mode generic --tag g1   # another mode
python t2_retrieval.py --tag my_run                            # T2
python t6_ops.py my_run                                        # tokens and cost from a finished run
python -m unittest discover -p "test_*.py"                     # 169 unit tests
```

The locked test set is run once and only with `--set test --final` (e.g. `python t3_chain.py --set test --final --tag f_x`).
Results are in `results/` (in `.gitignore`; back them up outside the repo). Detailed procedure and a list of all runs:
`LAB_STATUS_AND_NEXT_STEPS.md`.

API keys and any setting overrides (e.g. `PG_DSN`, `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_LLM_DEPLOYMENT`) belong in a `.env` file in this folder.
`config.py` loads it via python-dotenv; `.env` is in `.gitignore` and is not committed.
