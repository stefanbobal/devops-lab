# code_banka: final document (working version)

A document filled in as the lab progresses. Each section is added after a lab step is finished; at the end it will be edited into one whole.
Detailed measurements are in separate files (`T2_retrieval_embeddings.md`, `LAB_STATUS_AND_NEXT_STEPS.md`). All companies and numbers are made up.

## 1. Purpose of the lab

The agent checks loan covenants from a company's statements. **The final status is decided by verifiable code, not by the LLM.**
The LLM extracts data, reads the contract and writes the explanation. See the README.

## 2. RAG over contracts (status: retrieval measured, T2)

Source of the measurement: `T2_retrieval_embeddings.md`.

- Contracts are split into chunks; each is turned into a vector and stored in a table for the given embedding model
  (Azure `text-embedding-3-small`, Gemini `gemini-embedding-001`, local `bge-m3`).
- Search: first an SQL filter on the company (mandatory), then cosine similarity; the top 3 are returned.
- The correct article is always in the top 3 for all three models. The difference is in hit@1.

### 2.1 Chunking

**What it is:** splitting a long document into smaller pieces, each with its own vector.
One chunk should be about one thing; otherwise its vector is blurred.

**What we found:** article 2 contained 6 definitions. For azure and bge, article 5 won (where EBITDA is mentioned often).
After splitting by clause (2.1 to 2.6), azure and bge improved on EBITDA and debt from 0/36 (and 3/36, 30/36) to 36/36,
without changing the model. Lesson: check the chunking before tuning the threshold and before swapping the model.

**How it is done in production:** start with a simple rule (fixed length with overlap); for documents with
articles, split by structure; add a header (context) and metadata to each chunk; compare variants
on an evaluation set; version the chunking (a new index after a change). Advanced techniques: semantic,
hierarchical (parent-child), contextual chunking, special handling of tables.

**Limitation of our solution:** the splitting is written for the template of the generated contracts (by article title).
Real contracts (scans, PDFs, annexes) would need a document parser and tuning on a large sample.

### 2.2 Similarity threshold

**What it is:** a score boundary below which a search result is discarded. Search always returns top-k,
even when nothing relevant exists. The threshold decides when the system says "I found nothing" and the case goes to a human
(`human_review`) instead of guessing.

**Where it is applied:** not in the database. The database returns top-k with scores; our code applies the threshold afterwards.
If fewer than k results are above the threshold, the agent gets fewer chunks; if none, it goes to `human_review`.

**Five things to remember:**
1. Scores are not comparable across models (Gemini gives correct chunks around 0.7, azure and bge around 0.5),
   so each embedding model has its own threshold.
2. The threshold depends on the data and chunking; it is tuned only once the chunking has settled.
3. It is a trade-off between two errors: a low threshold lets irrelevant text through (risk of hallucination), a high one discards correct text
   (unnecessary hand-off to a human). For us it is safer to admit "I don't know".
4. You measure recall (how many correct ones stay above the line) and precision (how much of what stays is correct).
   With top-3 and one correct chunk the precision ceiling is about 0.33, so low precision is not an error in itself.
5. Tuning and testing are not done on the same data: the threshold is tuned on the tuning set (dev), and the result is checked
   once on the locked test set (`data_test/`, 18 cases).

**What we found:** a negative test (a waiver for a company that has none) showed that search returns the article about waiver
rules with a score of 0.72 to 0.74 (gemini), while the real waiver scores 0.76. The gap is only 0.02. A threshold that would
separate them would discard most correct chunks for other questions. A threshold cannot tell "the topic matches" from "this is the
document". **The existence of a document is therefore handled deterministically** (document type in metadata, verification in
`sources.py`); the threshold is only a safeguard against completely irrelevant text.

**How we chose the threshold (procedure):**
1. A labelled dev set: for each question we know which chunk is correct (gold). In addition, 33 negative questions
   (a waiver for a company that has none), where no correct answer exists.
2. A grid of thresholds from 0.30 to 0.85 in steps of 0.05. For each threshold: recall, precision, false-accept
   (the share of negative questions where the best chunk stayed above the threshold).
3. Rule: the highest threshold with recall ≥ 0.95. Reason: a missing correct chunk ends in `human_review` (a safe
   error), while a foreign chunk that gets through still has to be stopped by the validator.
4. The thresholds are in `thresholds.json`, separately for each profile, and are applied by `find_relevant` in `search.py`.

| Profile | Threshold | Recall | Precision | Score of the "article about waivers" (negative queries) | Real waiver |
| --- | --- | --- | --- | --- | --- |
| gemini | 0.65 | 1.00 | 0.49 | 0.72 to 0.74 | 0.76 |
| bge | 0.50 | 1.00 | 0.56 | 0.60 to 0.64 | 0.66 to 0.68 |
| azure | 0.50 | 0.98 | 0.60 | 0.54 to 0.61 | 0.64 |

False-accept is 1.00 at the chosen thresholds in all profiles, so the threshold does not catch a negative waiver. Catching it
would need a threshold of 0.65 (bge), where recall drops to 0.59, or 0.75 (gemini), recall 0.65.
We first set Gemini to 0.70 (precision 0.88, recall 0.97), but in the agent run (T3a, qwen38 with gemini
retrieval) the correct chunks with the limit fell below the threshold in four cases (score 0.695 to 0.700); the model got only
2 chunks and correctly refused to guess (4 of 36 `refused`). We therefore lowered the threshold to 0.65 (recall 1.00). Lesson:
missing evidence is a more expensive error than one unnecessary extra chunk, so the threshold is chosen by recall, not by
precision.

**Waiver implementation:** `find_waiver` first checks in the metadata (`has_doc_type`) whether the company has a document
of type `waiver`. If not, it returns an empty result without searching. The threshold is not used for this question.

**Alternatives:** a reranker (cross-encoder, more accurate than comparing vectors but slower), hybrid search
(vector + BM25, better for exact terms like "prominuje" (waives)), a relative threshold (distance from the first result), a threshold per question
type, an LLM as relevance judge, metadata filters, query rewriting.

**Pitfalls:** a cosine score is not a probability (0.7 does not mean 70 % confidence). After a change of model, chunking
or document type, the threshold must be recalibrated. In production, track the share of empty results and check a sample
by hand.

**Measurement limitations:** the data is generated and small (12 companies, the definition queries repeat, the effective sample is
about 12 situations). The numbers illustrate the method, not a guarantee for a real bank.

### 2.3 Who is responsible for chunking

| What | Who |
| --- | --- |
| Designing suitable chunks | AI/data engineer with a domain expert (lawyer, credit analyst) |
| Evaluation (test set, metrics) | AI engineer, often together with the platform owner |
| Running the indexing job (loading, scheduling, retry on failure) | platform owner |
| Versions and changes (new index, backup, switch-over so old and new chunks do not mix) | platform owner |
| Monitoring (index freshness, chunk count, company coverage, quality) | platform owner |
| Access and security (per-client filters, sensitive data) | platform owner with security |
| Cost (re-embedding after a change) | platform owner |

## 3. Contract specification from retrieved text (T3a, dev set)

**What is measured:** search (bge, azure or gemini) gives the LLM contract excerpts; the LLM returns a JSON specification
(EBITDA and debt definition, limits, waiver). Code verifies it (`validate_spec`, `verify_sources`) and compares it with the expected one.
All models get the same prompt and the same excerpts. Script `t3_spec.py`, results `results/t3_spec_*.json`.

| Run | Model | Retrieval | Correct out of 36 | Note |
| --- | --- | --- | --- | --- |
| run1 | haiku / azure / gemma | bge | 31 / 23 / 12 | original prompt |
| run2 | azure / haiku / gemma | bge | 36 / 35 / 24 | prompt with the EBITDA base explained |
| | qwen38 | bge | 36 | |
| | qwen38 | azure | 36 | |
| | qwen38 | gemini, threshold 0.70 | 32 | limit missing 4× (score 0.695 to 0.700) |
| | qwen38 | gemini, threshold 0.65 | 36 | |
| haiku_fix | haiku | bge | 36 | prompt with the sentence about ratios |

**What we found:**
1. A large part of the early errors was in the prompt, not in the models. The model did not know that EBITDA always starts as EBIT plus
   depreciation and that ratios are computed by code. Once that was added, azure and haiku reached 35 to 36 out of 36.
2. Gemma (local) stayed at 24 out of 36: it reads "nepřipočítávají" ("are not added back") as an addition. Qwen38 (local) got 36 out of 36.
3. The choice of embedding model did not matter as long as the thresholds are safely low. Gemini with a 0.70 threshold discarded the correct chunk
   with the limit; the model correctly refused to guess (in the agent it would go to `human_review`).
4. The verifier caught gemma attributing the Q2 waiver to Q1 and Q3 as well. Without verification it could have
   turned `breach` into `no_breach`.
5. Errors in our measurement: the comparison originally insisted on the same covenant id and counted waivers from other periods.

**Limitations:** the prompt and the comparison were tuned on the same dev set (12 companies, 36 cases), so 36/36 partly
measures adaptation to this data. The real check comes only with `data_test/`. Not all models were run
with exactly the same prompt version (qwen38 and azure without the last sentence about ratios); before the final number they need to be
run again with the final prompt.

## 4. The agent and its chain (done)

**The agent and the tests are two different things.** The agent (`agent.py`, `agent.run(company, period, mode)`) is code that receives a company's statement and
returns the status, the reasons and all intermediate steps. The tests measure its steps and help choose a model; they are not run in production.

| Step | Who | Module | Test |
| --- | --- | --- | --- |
| 1 `extract`: items from the statement | LLM | `rag_prompt.py` | T1 |
| 2 `check_items`: the number must be on the cited page | code | `agent.py` | T1 |
| 3 `retrieve`: contract excerpts | code + embedding | `search.py` | T2 |
| 4 `spec`: specification as JSON | LLM | `rag_prompt.py` | T3a |
| 5 `verify`: validation and citation checks | code | `covenants.py`, `sources.py`, `contract_rules.py` | T3a, T3 |
| 6 `evaluate`: ratios, limit, waiver, 2 % band | code | `covenants.py` | T3 |

Who does what matters: **the LLM never decides the status.** On any failure in steps 1 to 5 the result is `human_review` with a reason.

## 5. The whole chain (T3)

Dev set, 36 cases, prompt P3: haiku 36/36, qwen3.8 35/36 and 36/36 on repeat, Azure 36/36; 0 missed breaches and 0 false alarms.
The only deviation (qwen3.8, C10-2026Q1, later C03-2026Q1 in `full` mode) is a wrong citation stopped by the verifier → a safe `human_review`.

### Three ways of working with the contract (step E)

| Mode | Correct | Missed breaches | Note |
| --- | --- | --- | --- |
| `rag` | 36/36 (haiku, qwen3.8) | 0 | baseline |
| `full` | 36/36 (haiku), 35/36 (qwen3.8) | 0 | not better, ≈ 1.75× the tokens in the specification step |
| `generic` (no contract) | 24/36 | **7** (+ 4 false alarms) | the contract is necessary |
| `no_context` | 3/36 | 0 | refused all 36×, nothing was made up |

## 6. Repeatability, operations and extraction (T5, T6, T1)

- **T5:** qwen3.8 359/360 correct runs (10 repetitions); haiku 108/108. Never flipped `breach` ↔ `no_breach`.
  The only instability was the citation of one case.
- **T6 (36 cases):** haiku 93,377 / 31,448 tokens, ≈ 4.3 s and $0.0007 per case; qwen3.8 ≈ 12.6 s (134 tokens/s), no fee;
  Azure 63,681 / 55,845 tokens, 13.3 s. No incomplete or unusable responses.
- **T1:** 5,400 items on dev and 360 on test, 0 errors (statements from one template, no scans; page accuracy was not measured).

## 7. Attacks (T4)

12 kinds of attacks (statement S1 to S7, contract C1 and X2, waiver C2, notes N1, cross-company leak X1) in three families; **0 successful out of 378 cases**.
Main finding: **the model can be fooled; the code holds the defence.** The local model once wrote a limit of 6.0 from an injected sentence into the specification; the status did not change
only because the strict parser of the article with limits (`contract_rules.py`) rejected the contract with the foreign sentence. That is why the parser is not relaxed; the price is
that every attack on the financial article ends as `human_review`.

## 8. Locked test set (F) and final prompt (H)

Run once, without changing the prompt, threshold or chunking. Test (18 cases, 6 companies): haiku 18/18, qwen3.8 18/18, Azure 16/18 (two safe `human_review`:
an attack stopped by the Azure content filter, and an ambiguous waiver "Čistý dluh" (net debt) vs. "Dluh" (debt)). T2 hit@3 100 %, error patterns the same as on dev, no overfitting shown.
Limitations: 18 cases from the same template, one run per model, companies C13 to C16 were previously used for attacks, so the set is not entirely untouched.
Every result has `meta` with the prompt version and hash (`run_meta.py`).

## 9. Remaining work and limitations

- Move to Azure AI Foundry (hosted agent, vector database in Azure): `FOUNDRY_PORT.md`.
- OpenTelemetry, YAML agent configuration, GitHub Actions with a regression set, Docker image and a UI (optional).
- Limitations: generated data from one template, one run per model and mode, prompt and thresholds tuned on the dev set, chunking and verification tailored to the format
  of the generated contracts (real contracts would need PDF parsing, detection of structure and cross-references).
