# AI Lab 04 – Similarity search with filters and threshold

## Goal

Find similar historical incidents safely: deterministic filters first, then vector similarity,
then a minimum similarity threshold.

## Concepts

- `<=>` in pgvector is cosine distance, so `similarity = 1 - distance`.
- **Deterministic filters** (domain, database type) prevent "Oracle incident → HANA evidence".
- **Top N always returns something.** Without a threshold, irrelevant incidents look relevant.

## Steps and experiments

```bash
cd ~/devops-lab/ai-labs/code
source .venv/bin/activate
```

1. Without filter – does Q11 show up?

   ```bash
   python search.py "Backup failed, backint SSL handshake error"
   ```

2. With filter – Q11 and the Oracle incident disappear:

   ```bash
   python search.py "Backup failed, backint SSL handshake error" backup HANA
   ```

3. Query outside the memory – results should be marked below threshold:

   ```bash
   python search.py "Printer on floor 2 is out of paper"
   ```

4. Paraphrase without shared words:

   ```bash
   python search.py "users complain everything takes forever" performance
   ```

## Tune the threshold

Compare scores of correct and wrong results and set the threshold between them.
No code change needed:

```bash
SIMILARITY_THRESHOLD=0.70 python search.py "Printer on floor 2 is out of paper"
```

### Thresholds selected in the expanded experiment

The 33 tuning questions were evaluated over 0.30–0.85 in steps of 0.05. The chosen threshold
is the middle of the longest contiguous band with the best score; ties use the lower band
or lower middle. The 40 held-out questions did not participate in this selection.

| Profile | Threshold |
| --- | ---: |
| gemini | 0.65 |
| bge | 0.60 |
| azure | 0.40 |
| nomic | 0.60 |
| nomic_prefix | 0.65 |
| qwen | 0.60 |
| qwen8 | 0.55 |
| qwen_instr | 0.40 |

The values are stored in [thresholds.json](code/thresholds.json). `sweep_eval.py` selects
them and `eval_test.py` reads them. As inspected on 30 October, `search.py` and `rag.py`
instead use `SIMILARITY_THRESHOLD` from config/environment (default 0.60); they do not
automatically load the JSON. Until this is wired into the RAG runner, pass the selected
profile and its threshold explicitly, for example:

```bash
EMBED_PROFILE=gemini SIMILARITY_THRESHOLD=0.65 python search.py "Backup failed, backint SSL handshake error" backup HANA
```

`find_similar()` returns up to three candidates before thresholding. The search CLI marks
below-threshold results; `rag.py` excludes them from context. Top-3 retrieval success before
the threshold therefore does not prove that the correct case reaches the LLM.
See [Lab 06](06-evaluation.md) for that distinction and the observed trade-off.

## Notes

- Chosen threshold:
