# T2: retrieval of contract articles, comparison of 3 embedding models

Status: 2026-11-03 (measurements 1 and 2); the evaluation on the locked test set on 2026-11-09 is in `LAB_STATUS_AND_NEXT_STEPS.md`, section 12e. Measurement 1 (baseline, article = chunk) and measurement 2 (H1: definitions split by clause), section 10.
All companies and numbers are made up.
Related: README (section 2 and test T2), `load_documents.py`, `search.py`, `t2_retrieval.py`,
raw results in `results/t2.json`.

## 1. What we test and why

The agent checks loan covenants. Before computing anything it must know **under which
definition and with which limit** to compute. This information is in the client's contract (EBITDA definition,
net debt definition, the limit for the given Den testování (test date), possibly an amendment or a waiver).
We do not put the whole contract into the prompt, only the retrieved articles (RAG).

**The T2 question:** when the agent asks a question about the contract, does search find the article that
contains the correct answer? And does that differ between the three embedding models?

T2 measures only retrieval. It does not evaluate the LLM or the status calculation (those are T1 and T3).
If the specification goes wrong in T3, T2 tells us whether a missing article was the cause.

## 2. What is in the database

- **Source:** contracts, amendments, waivers and analyst notes of 12 made-up companies (`data/companies/`).
  Statements are not loaded; they are the agent's input, not its knowledge.
- **Chunks:** 135 at the time of measurement 1 (dev set, split by article). Currently **each of the three tables has 308 chunks**
  for 18 companies (dev and locked test set; `load_documents.py` loads both, and loading is not evaluation):
  284 contract articles (including definitions split by numbered clause), 4 amendment articles, 2 waivers and 18 analyst notes.
  Contracts and amendments are split **by article** (`## Článek N – ...`), the "Definice a výklad" (definitions) article by clause (measurement 2);
  waivers and notes have no articles, so they are one chunk per document. After adding the attack sets (T4) the tables have 2,610 chunks.
- **Embedded chunk text:** header + article text, for example
  `Firma: Vltavská strojírenská a.s. / Dokument: smlouva.md (contract), článek 2 – Definice a výklad / <text>`.
- **Tables:** `covenant_docs_bge`, `covenant_docs_azure`, `covenant_docs_gemini` in the
  `pgvector-banka` container (port 5433). Columns: company, document, type, article, page, text, vector.
- **Search:** first an SQL filter on the company (mandatory), then ordering by cosine similarity
  (`1 - (embedding <=> query)`). Analyst notes are left out in T2; they are not evidence of a limit or
  a waiver.

### Models tested

| Profile | Model | Provider | Dimension | Note |
| --- | --- | --- | --- | --- |
| `azure` | text-embedding-3-small | Azure OpenAI (Foundry) | 1536 | no task type |
| `gemini` | gemini-embedding-001 | Vertex AI (GCP) | 1536 | task type `RETRIEVAL_DOCUMENT` for chunks and `RETRIEVAL_QUERY` for queries |
| `bge` | bge-m3 | local Ollama | 1024 | no task type and no prefix |

## 3. How the test runs

For each of the 36 cases (12 companies × 3 quarters), fixed queries are asked (in Czech, like the documents):

| Kind | Query | Correct chunk |
| --- | --- | --- |
| `ebitda` | "Jak je ve smlouvě definována EBITDA?" (How is EBITDA defined in the contract?) | the article cited by `expected.json` (usually contract art. 2) |
| `debt` | "Jak je ve smlouvě definován Čistý dluh?" (How is net debt defined in the contract?) | also usually contract art. 2 |
| `limit` | "Jaká je nejvyšší přípustná hodnota finančních ukazatelů pro Den testování <date>?" (What is the maximum permitted value of the financial covenants for test date <date>?) | the article with the limit (contract art. 5 or 6; for C10 Q2 and Q3 amendment art. 1) |
| `waiver` | "Prominutí porušení finančního ukazatele pro Den testování <date>?" (Waiver of a covenant breach for test date <date>?) | the waiver document; only 3 cases have a waiver |

For each query, the top 3 chunks of the same company are taken.

- **hit@1:** the correct chunk is in first place.
- **hit@3:** the correct chunk is among the first three.
- **Threshold sweep:** for thresholds 0.30 to 0.85, compute recall (the correct chunk stays above the threshold) and precision
  (what share of the chunks above the threshold is correct).

Note on correctness: "correct" means exactly the document and article listed in `expected.json`,
not any article that might also contain the answer.

## 4. Results

| Profile | EBITDA hit@1 | Debt hit@1 | Limit hit@1 | Waiver hit@1 | hit@3 (all) |
| --- | --- | --- | --- | --- | --- |
| gemini | 36/36 | 36/36 | 33/36 | 3/3 | 100 % |
| bge | 0/36 | 30/36 | 32/36 | 3/3 | 100 % |
| azure | 0/36 | 3/36 | 35/36 | 3/3 | 100 % |

### Where the correct article ranks when it is not first

- **azure:** EBITDA 33× in 2nd place and 3× in 3rd place (C10); debt 33× in 2nd place.
- **bge:** EBITDA 36× in 2nd place; debt 6× in 2nd place.
- **gemini:** no errors on definitions; on the limit 3× in 2nd place (all C10).
- **What is in first place instead of article 2:** almost always article 5 or 6 ("Finanční ukazatele", financial covenants),
  i.e. the article that only uses EBITDA and debt in the ratio.

### Similarity of the correct chunk (average)

| Profile | EBITDA | Debt | Limit | Waiver |
| --- | --- | --- | --- | --- |
| gemini | 0.72 | 0.71 | 0.71 | 0.76 |
| bge | 0.54 | 0.55 | 0.55 | 0.67 |
| azure | 0.52 | 0.47 | 0.54 | 0.64 |

**Similarities of different models cannot be compared.** Gemini gives generally higher numbers.
Only the ranking and the gap between the correct and the wrong chunk are meaningful.

### Thresholds (sweep)

- **gemini:** at a threshold of 0.70, recall 0.95 and precision 0.88. This is by far the best separation
  of correct and wrong chunks.
- **bge:** at 0.50 recall 1.00 and precision 0.56. At 0.55 recall already drops to 0.41.
- **azure:** at 0.45 recall 0.97 and precision 0.41; at 0.50 recall 0.63. The range in which the threshold works is very narrow.
- The automatically chosen "highest threshold with full recall" (gemini 0.65, bge 0.50, azure 0.40) is not
  necessarily the best. For gemini 0.70 seemed better, but it later turned out that 0.65 is safer (section 12).

## 5. What follows from this

1. **The correct article is always in the top 3 (100 %) for all three models.** If the agent gets the
   top 3 in its prompt, retrieval is not the bottleneck.
2. **The difference is in the ranking.** At top-1 gemini clearly wins; azure and bge systematically prefer
   the covenant article over the article with the definitions.
3. **The error is systematic, not random.** It is the same pair of articles in all companies. This fits
   the fact that the contracts are generated from one template.
4. **C10 shows up clearly on the limit.** The amendment and the original contract are both in the top 3. Which one applies
   is decided by `sources.py`, not by retrieval.
5. **Usual `bge` behaviour on the C05 limit:** waiver_2026Q2 is in first place even for Q1 and Q3, where it does not
   apply yet. It is just noise in the ranking; the validator will not accept a made-up or invalid waiver.

## 6. Hypotheses (not yet verified)

This is measured, not explained. The following points are only conjectures.

| # | Hypothesis | How to verify it |
| --- | --- | --- |
| H1 | Article 2 contains 6 definitions at once, so its vector is "mixed" and a query about one definition does not match it. | Split article 2 by clause (2.5 EBITDA, 2.6 Čistý dluh) and rerun T2. The citation stays at article level. **Verified in measurement 2 (section 10): supported.** |
| H2 | Gemini also wins thanks to the task types (`RETRIEVAL_QUERY` / `RETRIEVAL_DOCUMENT`), which azure and bge lack. | Run gemini with the same task type for queries and chunks and see whether the result gets worse. |
| H3 | Gemini is a larger model and understands Czech legal text better than `text-embedding-3-small`. | Cannot be verified directly in the lab. Indirectly: compare with a larger local model (`qwen3-embedding:4b` is in Ollama). |
| H4 | The query "Jak je definována EBITDA?" is lexically closer to article 5, where EBITDA is mentioned several times, than to the definition. | Rewrite the query in the form of a definition ("EBITDA znamená ..." / "EBITDA means ...") and compare. |
| H5 | The `Firma: ... Dokument: ...` header is the same in all of a company's chunks and reduces the distinction between them. | Load the chunks without the header and compare. |

If H1 holds, azure and bge in particular should improve, and gemini should not get worse.

## 7. Limitations

- **The sample is smaller than it looks.** The definition queries are the same in all 3 quarters of a company,
  so "36" for EBITDA and debt is really 12 different situations. For `waiver` there are only 3 cases.
- **The contracts are generated from one template.** The errors therefore repeat, and real contracts would be more varied.
- **Small corpus.** After the company filter, the choice is among 10 to 13 chunks. Differences between models could
  look different on a large DB.
- **One query wording per kind.** The result may depend on the wording (H4).
- **The exact ranking may differ slightly on a repeat** (calls to cloud models are not guaranteed to be
  deterministic).

## 8. How to reproduce it

```bash
cd ~/devops-lab/ai-labs/code_banka_en
source .venv/bin/activate
bash lab.sh                       # expected result: Lab ready.
docker compose up -d              # if pgvector-banka is not running
for p in bge azure gemini; do EMBED_PROFILE=$p python load_documents.py; done
python t2_retrieval.py            # prints the table; raw data in results/t2.json
```

## 9. Next steps

- ~~Verify H1~~ (done, section 10).
- H2, H4 and H5 are no longer needed for the definitions (all models get 36/36). We would verify them only if
  retrieval got worse on the test set.
- Write the thresholds into `thresholds.json` separately for each profile, calibrated on the dev set only (section 11).
- Evaluate the locked test set once (`data_test/`, 18 cases).
- Continue with the LLM prompts (`rag_prompt.py`) and test T3.

## 10. Measurement 2: definitions split by clause (H1)

Change: the "Definice a výklad" (definitions) article is no longer chunked as one whole, but by numbered clause
(2.1 to 2.6 or 2.7, each clause one chunk with a `clause` field). The other articles stayed whole.
The rest of the test is the same (dev set, 36 cases, same queries). Results: `results/t2_split_defs.json`,
baseline backup: `results/t2_baseline.json`.

In addition to the original metric (correct article), a **strict** metric was added for EBITDA and debt: the chunk must be
in the correct article **and** contain the definition itself (`„EBITDA“`, or `„Čistý dluh“` / `„Dluh“`). Without it,
chunk 2.1 (the definition of the Bank) would also "hit article 2" after the split.

### Results (hit@1, original metric; baseline from measurement 1 in brackets)

| Profile | EBITDA | Debt | Limit | Waiver | hit@3 |
| --- | --- | --- | --- | --- | --- |
| gemini | 36/36 (36/36) | 36/36 (36/36) | 33/36 (33/36) | 3/3 (3/3) | 100 % |
| bge | **36/36** (0/36) | **36/36** (30/36) | 32/36 (32/36) | 3/3 (3/3) | 100 % |
| azure | **36/36** (0/36) | **36/36** (3/36) | 35/36 (35/36) | 3/3 (3/3) | 100 % |

The strict metric (the chunk contains the definition) came out at **36/36 for both hit@1 and hit@3 for all
three models** for EBITDA and debt, so the improvement is not just a matter of hitting the article.

### Margin of the correct chunk over the best wrong one (similarity difference)

The difference between the highest similarity of the correct chunk and the highest similarity of a wrong chunk
(positive means the correct one wins). Similarities cannot be compared across models, but differences within a model can.

| Profile | EBITDA (min / mean) | Debt (min / mean) | Limit (min / mean) | Waiver (min / mean) |
| --- | --- | --- | --- | --- |
| gemini | 0.064 / 0.079 | 0.053 / 0.082 | -0.007 / 0.033 | 0.028 / 0.031 |
| bge | 0.081 / 0.096 | 0.106 / 0.172 | -0.040 / 0.079 | 0.030 / 0.033 |
| azure | 0.091 / 0.133 | 0.157 / 0.192 | -0.033 / 0.054 | 0.076 / 0.078 |

For the definitions the margin is positive in every case, so these are not narrow wins. For the limit there are
negative minima (the same C10 and C05 cases as in measurement 1).

### What changed and what did not

- **H1 is supported.** After splitting the article, `azure` and `bge` went on the definitions from 0/36 (EBITDA)
  and 3/36 and 30/36 respectively (debt) to 36/36. `gemini`, which was good before, did not get worse.
- **The side effect we feared** (the small chunks 2.1 to 2.4 pushing other articles out of the top 3) did not appear:
  hit@3 stayed at 100 % and neither the limit nor the waiver got worse.
- **The limit is unchanged**: C10 (the amendment and the original contract alternate in 1st place) and C05 with `bge` (the waiver
  in 1st place for Q1 and Q3, where it does not apply yet). This is not a chunking error but an ambiguity that is
  resolved by the validator (`sources.py`), not by retrieval.
- **The evidence for the mechanism is only indirect.** The improvement fits H1, but does not rule out that it also helps that the chunks are
  shorter and closer to the short queries. We did not measure H4 and H5.

### Thresholds after the change (sweep on the dev set)

- **gemini:** at 0.70 recall 0.97 and precision 0.88; at 0.75 recall 0.65.
- **bge:** at 0.50 recall 1.00 and precision 0.56; at 0.55 recall 0.81 and precision 0.57.
- **azure:** at 0.45 recall 1.00 and precision 0.48; at 0.50 recall 0.98 and precision 0.60.
- The thresholds are written in `thresholds.json` (section 12).

### Limitations of measurement 2

- **We tuned the queries and the chunking on the same dev set**, so 36/36 may partly be overfitting to this
  template. The real check comes only with the locked test set (different structure, 12 articles in the contract).
- The split only works on articles that consist solely of numbered clauses (`N.M text`), and it is chosen by article title.
  Real contracts would need more robust detection.
- Hit@1 is 36/36 partly because the definition queries are the same in all 3 quarters of a company (effective sample 12).

## 11. Order of the next steps (tuning and testing kept separate)

1. Decide and write the thresholds on the dev set (`--write-thresholds`, or by hand from the sweep).
2. Lock: no more changes to chunking, query texts or thresholds.
3. Generate the test set (`python generate_data.py --set test`) and load it (`load_documents.py`).
4. Evaluate once: `python t2_retrieval.py --set test --final`. The number from it is the T2 result.
5. If the result on the test set is clearly worse than on the dev set, that is a sign of overfitting. Record it
   and go back to H4, H5 or more robust chunk splitting. After such a change the test set is no longer
   "independent" and a new one must be generated.

## 12. Thresholds written and the gemini fix

`thresholds.json` (dev set, rule: the highest threshold with recall ≥ 0.95): azure 0.50, bge 0.50, gemini 0.70.
They are applied by `find_relevant` in `search.py`; the waiver is handled by document type (`find_waiver`).

In the specification test (T3a, `t3_spec.py`, qwen38 with gemini retrieval), 4 cases (C01, C06, C08, C11,
always the 2nd quarter) got only 2 chunks: the correct chunk with the limit scored 0.695 to 0.700, i.e. just below the 0.70 threshold.
The model correctly refused to guess (`refused`); in the agent this would be `human_review`. We therefore lowered the gemini threshold to
**0.65** (recall 1.00). Lesson: in a banking use case, a missing passage is more expensive than one extra chunk.
