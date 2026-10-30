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
source .venv/bin/activate
python rag.py
```

The first call can take longer while the model loads into GPU memory.

## Experiments

1. **No history:** `SIMILARITY_THRESHOLD=0.99 python rag.py` – how much worse is the answer?
2. **No guardrail:** remove the "CONTEXT ONLY" sentences from `system_prompt`.
   Does the model start claiming the root cause is certainly the certificate?
3. **Different cause:** change the signals to "storage endpoint unreachable, connection timeout".
   Is D15 retrieved instead of Q50?
4. **Different LLM profile:** `LLM_PROFILE=llama python rag.py` and compare.
   Available profiles are defined in `config.py`.

### Status and sequence

The basic RAG demonstration was performed before the expanded retrieval evaluation.
Lab 06 now contains the completed embedding comparison. The next experiment returns to
this RAG pipeline to compare LLMs. Lab numbering describes the learning sequence, not
a requirement to finish every extension before moving to the next lab.

### Planned LLM comparison

**Status: planned; no comparative LLM results recorded yet.**

Compare each candidate LLM with all eight embedding profiles using their own frozen
thresholds from [thresholds.json](code/thresholds.json), established in [Lab 06](06-evaluation.md).
For each question and embedding profile, save the retrieved context and give exactly that
context to every LLM. Keep prompts and scenario inputs fixed. A separate comparison with
one fixed context can isolate LLM behavior from retrieval quality.

The current scenario is a HANA backup failure with `certificate verify failed`.
Assess useful next checks, relevance to the current evidence, source attribution,
and whether the model keeps historical causes as hypotheses requiring current verification.
Extend this to multiple scenarios, including missing history, misleading similar cases and
insufficient evidence, with an agreed rubric before running the comparison.

Record embedding profile, threshold, exact LLM identity and settings, scenario, prompt,
retrieved incident IDs and text, answer, elapsed time, input/output usage and estimated cost.
Measure retrieval and LLM time separately; record model loading, retries and cache effects.
Where available, retain provider usage fields including reasoning/cache categories.
Local inference has no API fee; electricity and hardware are outside that figure.
Repeat each combination 2–3 times where feasible.

**Implementation status on 30 October:** `rag.py` has one fixed incident.
`providers.chat()` returns answer text only; timing, usage capture, pricing and a matrix
runner still need implementation. RAG does not yet read the threshold JSON automatically.
Azure embeddings exist, but Azure LLM support is not implemented in `chat()`.
Candidate API availability and exact deployed model IDs must be checked before the run.

This test asks models to propose investigation steps. Tool execution, current-system
verification and a separate investigation-history table are a later agent phase.

## Notes

-
