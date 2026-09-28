# AI Lab 05 – RAG with a local LLM

## Goal

Give the LLM similar historical incidents as clearly separated context, without letting it
treat history as proof.

## Concepts

- **RAG (Retrieval-Augmented Generation):** retrieve relevant data first, then let the LLM
  work with it.
- **Separation:** CURRENT EVIDENCE and HISTORICAL CONTEXT are separate sections of the prompt.
- **Guardrail in the system prompt:** similarity does not prove the same root cause.

## Steps

```bash
cd ~/devops-lab/ai-labs/code
source venv/bin/activate
python rag.py
```

The first call can take longer while the model loads into GPU memory.

## Experiments

1. **No history:** `SIMILARITY_THRESHOLD=0.99 python rag.py` – how much worse is the answer?
2. **No guardrail:** remove the "CONTEXT ONLY" sentences from `system_prompt`.
   Does the model start claiming the root cause is certainly the certificate?
3. **Different cause:** change the signals to "storage endpoint unreachable, connection timeout".
   Is D15 retrieved instead of Q50?
4. **Smaller model:** `LLM_MODEL=gemma3:12b python rag.py` and compare.

## Notes

-
