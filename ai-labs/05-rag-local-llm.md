# AI Lab 05 – RAG evaluation: Local LLMs vs. Cloud Models

## Goal

Compare local and cloud LLMs on SAP HANA and Oracle incident triage using historical
cases as context. Evaluate useful next checks, evidence handling, reliability, latency
and cost across the calibrated embedding profiles. History must never become proof
of the current root cause.

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
thresholds from [thresholds_FROZEN.json](code/thresholds_FROZEN.json), established in [Lab 06](06-evaluation.md).
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

### LLM candidates for the comparison

The planned matrix includes the following ten profiles from [config.py](code/config.py).
These are configured candidates; a successful smoke test is required before a profile
is marked available in the run manifest. Missing models must be reported as unavailable,
not silently replaced or counted as quality failures.

| LLM_PROFILE | Model / configured identifier | Execution | Status / verification |
| --- | --- | --- | --- |
| `gemma` | `gemma3:27b` | Local Ollama | Installed tag confirmed; generation and quantization pending |
| `qwen36` | `qwen3.6:27b` | Local Ollama | Installed tag confirmed; generation and quantization pending |
| `qwen38` | `qwen3.8:27b` | Local Ollama | Installed tag confirmed; generation and quantization pending |
| `llama` | `llama3.1:8b` | Local Ollama | Installed tag confirmed; generation and quantization pending |
| `claude` | `claude-sonnet-5-5` by default | Anthropic API | VM smoke test passed; override via CLAUDE_MODEL |
| `haiku` | `claude-haiku-5-5` | Anthropic API | VM smoke test passed |
| `opus` | `claude-opus-5-5` | Anthropic API | VM smoke test passed |
| `gemini` | `gemini-3-flash-preview` by default | Google Vertex AI | VM smoke test passed; override via VERTEX_LLM_MODEL |
| `gemini_argon` | `gemini-4-argon` by default | Google Vertex AI | Direct VM smoke test passed; override via VERTEX_ARGON_MODEL |
| `azure` | GPT-5 Mini, deployment `gpt-5-mini` | Azure OpenAI / Foundry | VM integration smoke test passed |

On 30 October 2026, the VM cloud check passed for two embedding profiles and five LLMs
(Sonnet, Haiku, Opus, Gemini Flash and Azure GPT-5 Mini). A separate direct call with
`gemini-4-argon` and location `global` also returned a nonempty answer.
These are connectivity smoke tests, not RAG quality results. The updated
`check_cloud.py` includes Argon as a sixth cloud LLM (eight checks in total);
the new profile wiring still needs to be exercised after pulling the update.

Flash and Argon use the same Vertex credentials and GCP_PROJECT. Keep
VERTEX_LLM_MODEL set to Flash (or unset for its default); VERTEX_ARGON_MODEL independently
controls Argon. Both use VERTEX_LLM_LOCATION, defaulting to `global`.

```bash
EMBED_PROFILE=gemini LLM_PROFILE=gemini_argon python rag.py
```

Azure GPT-5 Mini deployment was confirmed in Foundry on 30 October 2026:
model version `2025-08-07`, Global Standard, 250,000 TPM and 250 RPM.
The deployment has an automatic version upgrade policy; record its actual version at
experiment time. GPT-6.1 Sol was considered but is not part of this matrix because the
subscription currently has zero quota for it.

Each available LLM will be paired with all eight embedding profiles: `nomic`,
`nomic_prefix`, `bge`, `qwen`, `qwen_instr`, `qwen8`, `gemini`, and `azure`.
Ten available LLMs would give **80 RAG configurations per scenario and repetition**,
plus any no-history and curated-context controls. EMBED_PROFILE and LLM_PROFILE are
independent: `EMBED_PROFILE=gemini LLM_PROFILE=azure` means Gemini retrieval with GPT-5 Mini
answer generation. Embedding rankings do not establish the ranking of LLMs.

Before the benchmark, record resolved API model identifiers, Azure deployment/version,
Ollama tags/digests and quantization, generation/reasoning settings, and availability.
Keep that manifest fixed for the comparison and document any provider-side version changes.
The automatic `rag_test.py` matrix runner is planned and has not been implemented yet.

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
export AZURE_OPENAI_LLM_DEPLOYMENT="gpt-5-mini"
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
