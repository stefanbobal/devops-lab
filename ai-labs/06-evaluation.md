# AI Lab 06 – Evaluating retrieval

## Goal

Measure how well incident retrieval works on domain-specific data. The original threshold
exercise grew into an eight-profile experiment on 200 fictional SAP HANA and Oracle incidents,
completed on 28 October 2026. This measures retrieval; LLM answer evaluation is the
[planned next experiment in Lab 05](05-rag-local-llm.md#planned-llm-comparison).

## Concepts

- Tune thresholds on one question set and evaluate on another.
- Each question specifies expected incident IDs, domain/database filters, and a category.
  No-answer questions expect no result above the threshold.
- A low threshold admits irrelevant context; a high threshold can discard correct cases.
- Similarity scores and suitable thresholds differ between embedding profiles.
- Historical cases are context for investigation, never proof of the current root cause.

### Dataset and profiles

The corpus contains 200 fictional incidents (139 HANA, 61 Oracle), stored separately for
each profile in PostgreSQL with pgvector. Ollama ran on Windows with an RTX 4090 (24 GB);
Python ran in an Ubuntu VM. Gemini used Vertex AI and Azure used text-embedding-3-small.

| Profile | Model / input variant | Dimensions |
| --- | --- | ---: |
| nomic | nomic-embed-text v1.5, no prefixes | 768 |
| nomic_prefix | nomic-embed-text, document/query prefixes | 768 |
| bge | bge-m3 | 1024 |
| qwen | qwen3-embedding:4b, no instruction | 2560 |
| qwen_instr | qwen3-embedding:4b, query instruction | 2560 |
| qwen8 | qwen3-embedding:8b, no instruction | 4096 |
| gemini | gemini-embedding-001, retrieval task types | 1536 |
| azure | text-embedding-3-small | 1536 |

## Steps

1. Load the same incident corpus for each profile, preserving model and embedding text.
2. Use the 33 questions in `eval.py` for tuning only.
3. `sweep_eval.py` retrieves the top result once per question/profile and evaluates thresholds
   0.30–0.85 in 0.05 steps against those scores.
4. Choose the middle of the longest contiguous best-scoring band. Use the lower band or
   lower middle when tied. Save the result in `thresholds.json`.
5. Freeze thresholds and the 40-question held-out set before evaluating.
6. `eval_test.py` evaluates the held-out questions once per profile and records results.

The held-out set contains 14 normal queries, eight paraphrases, six traps, six Slovak queries
and six no-answer queries: 34 answerable questions plus six that should return nothing.
Domain and database filters apply where specified; two questions have no filters.

Commands below describe the original workflow, not a request to overwrite frozen results:

```bash
cd ~/devops-lab/ai-labs/code
source .venv/bin/activate
python sweep_eval.py
python eval_test.py
```

The experiment record preserves `thresholds_FROZEN.json`, `test_questions_FROZEN.py`
and `results_FROZEN.csv`. The evaluator guards against evaluating an already recorded
profile again and writes results after the run completes. Reproduction must preserve the
original artifacts; further tuning requires a new evaluation protocol.

## Results

Recorded results from 28 October 2026, transcribed from the complete experiment record.
No new model runs were performed for this documentation update.

### Threshold selection

| Profile | Tuning score /33 | Threshold | Best band |
| --- | ---: | ---: | --- |
| gemini | 33 | 0.65 | 0.65 |
| bge | 32 | 0.60 | 0.60 |
| azure | 32 | 0.40 | 0.40 |
| nomic | 31 | 0.60 | 0.60–0.65 |
| nomic_prefix | 31 | 0.65 | 0.65 |
| qwen | 29 | 0.60 | 0.60 |
| qwen8 | 29 | 0.55 | 0.55 |
| qwen_instr | 29 | 0.40 | 0.35–0.45 |

### Held-out results

| Profile | Overall /40 | Rank-1 /34 | Top-3 /34 | No-answer accepted /6 | Irrelevant context total | Gap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gemini | 40 | 34 | 34 | 0 | 38 | +0.1275 |
| qwen_instr | 40 | 34 | 34 | 0 | 59 | +0.0978 |
| bge | 37 | 33 | 34 | 0 | 16 | +0.0400 |
| qwen | 37 | 34 | 34 | 0 | 24 | +0.0155 |
| azure | 36 | 32 | 34 | 0 | 44 | −0.0720 |
| qwen8 | 36 | 31 | 34 | 0 | 50 | +0.0834 |
| nomic | 34 | 30 | 33 | 1 | 40 | −0.0748 |
| nomic_prefix | 32 | 28 | 32 | 0 | 38 | −0.0752 |

### Metric definitions

- **Overall:** correct highest-ranked accepted incident for answerable queries, or no accepted
  incident for no-answer queries.
- **Rank-1 / Top-3:** correct first result / at least one correct result in the first three,
  both measured before thresholding.
- **No-answer accepted:** a no-answer query for which at least one candidate passed the threshold.
- **Irrelevant context:** candidates above threshold outside the expected answer set, summed
  over the 34 answerable queries. Other reasonable cases may be counted as irrelevant.
- **Gap:** the lowest best-correct score across answerable queries minus the highest no-answer
  score. Correct candidates are considered within the first three; read this metric with Top-3.

### What the results mean for RAG

Gemini and instructed Qwen tied on overall score, while admitting 38 and 59 irrelevant
candidates respectively. BGE admitted 16, but its threshold rejected two correct top-ranked
answers. Qwen without instruction rejected three such answers.

These totals are across 34 questions: Gemini averaged about 1.1 irrelevant cases per query,
instructed Qwen 1.7 and BGE 0.5. They are not dozens of cases in a single prompt.

Top-3 success does not guarantee the correct incident survives the threshold. Overall minus
correctly rejected no-answer queries counts only correct first accepted results, so it gives
a lower bound on correct context availability; a correct second or third accepted case may
also reach the LLM. The next evaluation should directly measure recall after thresholding.

Nomic prefixes did not improve this dataset (34 → 32 overall). Qwen's instruction improved
the gap (0.0155 → 0.0978) and overall (37 → 40), while the lower selected threshold admitted
more irrelevant context (24 → 59). This does not isolate an instruction-only causal effect.

## Extensions

- Run the planned LLM × embedding matrix using these fixed per-profile thresholds.
- Measure correct-context availability after thresholding and grade partial relevance.
- Add harder similar-looking cases with different causes and more realistic no-answer queries.
- Evaluate hybrid retrieval and re-ranking in a separate experiment.
- Validate on approved real incident data before selecting a production configuration.

## Notes

All data is fictional and AI-assisted. Forty questions are a small sample; a one-question
difference changes overall accuracy by 2.5 percentage points. The held-out traps were easy:
every profile answered all six correctly. The two question sets have different composition,
so their scores should not be treated as directly comparable measures of improvement.

Single-value best bands indicate sensitivity on the tested grid, not proof that only one
exact real-valued threshold works. Public benchmarks help choose candidates, but do not
replace evaluation on the intended domain. These results demonstrate a method and do not
establish a universal model ranking or LLM answer quality.
