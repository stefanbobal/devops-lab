# AI Lab 02 – Embeddings

## Goal

Understand how text becomes a vector and how "similar meaning" is measured.

## Concepts

- **Embedding:** a list of numbers (here 768) that represents the meaning of a text.
- **Cosine similarity:** how close two vectors point in the same direction.
  1 = same meaning, close to 0 = unrelated.
- Sentences with similar meaning get similar vectors even if they share almost no words.

## Steps

```bash
cd ~/devops-lab/ai-labs/code
source venv/bin/activate
python embeddings_test.py
```

## What to observe

- "slow" vs. "high response times" should score higher than "slow" vs. "backup failed".
- The coffee machine should be far from everything.
- The Slovak sentence is probably weakly linked to the English ones: `nomic-embed-text`
  is trained mainly on English. Language support matters when choosing a model for production.
- Scores do not use the full 0–1 range, typically 0.4–0.9. A similarity threshold must be
  tuned by experiment.

## Experiment

Add your own sentences (no company data) and see what the model considers similar.

## Notes

-
