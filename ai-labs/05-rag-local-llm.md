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

1. **High-threshold diagnostic:** `python rag.py --threshold 0.99` – inspect the printed context.
   This does not guarantee empty history; a true no-history baseline must explicitly omit it.
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

**Implementation status on 30 October:** RAG now reads the selected embedding profile's threshold
from `thresholds_FROZEN.json` by default. Azure chat completions are supported via
`LLM_PROFILE=azure`. The single incident demo still returns answer text only; timing,
usage capture, pricing and the evaluation matrix remain to be implemented.

This test asks models to propose investigation steps. Tool execution, current-system
verification and a separate investigation-history table are a later agent phase.

### Frozen thresholds and Azure LLM setup

Both threshold JSON files currently contain the same values. RAG defaults to the frozen
file next to `rag.py`, regardless of the working directory. Missing, malformed, duplicate
or invalid thresholds stop the run. To use the working file explicitly:

```bash
EMBED_PROFILE=gemini python rag.py --thresholds-file thresholds.json
```

RAG ignores `SIMILARITY_THRESHOLD` (and prints a note if present). Use the explicit
`--threshold` flag only for deliberate experiments. The standalone search and legacy
evaluation configuration keep their existing environment behavior.

Deploy a chat-completion model in Azure Foundry, then add its **deployment name** to the
Ubuntu VM's environment or local .env:

```bash
export AZURE_OPENAI_LLM_DEPLOYMENT="your-chat-deployment-name"
EMBED_PROFILE=gemini LLM_PROFILE=azure python rag.py
EMBED_PROFILE=azure LLM_PROFILE=azure python rag.py
```

The chat deployment uses the existing AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY.
It must be hosted under that resource. AZURE_OPENAI_EMBED_DEPLOYMENT remains the embedding
deployment. The endpoint may be a resource root or already end in /openai/v1/.
A deployment name is not necessarily identical to the underlying model name.
No API version is required by this v1 client. Incomplete or empty Azure answers raise an
error rather than silently becoming successful evaluation outputs.

## Notes

-
