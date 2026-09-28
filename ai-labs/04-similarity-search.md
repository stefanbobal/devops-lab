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
source venv/bin/activate
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

## Notes

- Chosen threshold:
