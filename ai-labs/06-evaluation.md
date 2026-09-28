# AI Lab 06 – Evaluating retrieval

## Goal

Measure retrieval quality on a test set instead of relying on "it seems to work".

## Concepts

- Each test has a query and the incident that should be found. Two tests should find nothing.
- **Threshold too low:** irrelevant incidents are returned (false positives).
- **Threshold too high:** correct incidents are missed (false negatives).
- The same trade-off as precision vs. recall.

## Steps

```bash
cd ~/devops-lab/ai-labs/code
source venv/bin/activate
SIMILARITY_THRESHOLD=0.50 python eval.py
SIMILARITY_THRESHOLD=0.60 python eval.py
SIMILARITY_THRESHOLD=0.70 python eval.py
```

## Results

| Threshold | Score | Notes |
| --- | --- | --- |
| 0.50 |  |  |
| 0.60 |  |  |
| 0.70 |  |  |

## Extensions

- **Multilingual embeddings:** `ollama pull bge-m3` (1024 dimensions), then
  `EMBED_MODEL=bge-m3 EMBED_DIM=1024 python load_incidents.py` and test Slovak queries
  with the same variables.
- Add your own paraphrases to `TESTS` and find where search fails.

## Notes

-
