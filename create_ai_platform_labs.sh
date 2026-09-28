#!/usr/bin/env bash
# Adds AI Platform labs 07-13 to ai-labs/.
# Run from the repository root:  bash create_ai_platform_labs.sh
set -euo pipefail

if [ ! -d ai-labs ]; then
  echo "ai-labs/ not found. Run create_ai_labs.sh first, from the repository root."
  exit 1
fi

for f in ai-labs/07-*.md ai-labs/08-*.md ai-labs/09-*.md ai-labs/10-*.md \
         ai-labs/11-*.md ai-labs/12-*.md ai-labs/13-*.md; do
  if [ -e "$f" ]; then
    echo "$f already exists - nothing was changed."
    exit 1
  fi
done

cat > ai-labs/00-platform-roadmap.md << 'EOF'
# AI Platform Homelab – Roadmap (Labs 07–13)

## Goal

Build a small copy of an internal company LLM platform at home: models served on my own
GPU, one gateway with API keys, a web UI for users, monitoring, benchmarks and documentation.

## Target architecture

```
                         Ubuntu VM (k8s-lab)
Users ──► Open WebUI ──► LiteLLM gateway ─────────────┐
                             (API keys, quotas,        │
                              routing, usage)          │
                                                       ▼
Prometheus + Grafana ◄── metrics ──────────  Windows host, RTX 4090
(dashboards, alerts)                         vLLM (Docker/WSL2) + Ollama
```

## Labs

| Lab | Topic | Skill it proves |
| --- | --- | --- |
| 07 | GPU fundamentals and nvidia-smi | GPU operations basics |
| 08 | Serving with vLLM | Production model serving |
| 09 | LiteLLM gateway | API keys, routing, quotas, usage reporting |
| 10 | Open WebUI | Self-service front end for users |
| 11 | Observability: Prometheus + Grafana | Monitoring and alerting for GPU and inference |
| 12 | Benchmarking and model evaluation | Choosing models with data, not opinions |
| 13 | Platform operations | Runbooks, onboarding guide, priorities |

## How these labs are written

Each lab defines the goal, concepts and a clear "Done when" checklist.
Detailed step-by-step instructions are written when I start the lab, because the
tools and recommended models in this area change every few months.

## Prerequisites

- AI Labs 01–06 completed
- Python line from the study guide completed
- DevOps labs: Docker basics
EOF

cat > ai-labs/07-gpu-fundamentals.md << 'EOF'
# AI Lab 07 – GPU fundamentals and nvidia-smi

## Goal

Understand what happens on the GPU when a model runs, and read the numbers that matter.

## Concepts

- **VRAM:** GPU memory. It holds the model weights plus the working memory for requests.
- **KV cache:** the working memory for the conversation context. Longer context and more
  parallel users = more KV cache = more VRAM.
- **Utilization, temperature, power draw:** the basic health signals of a GPU.
- **Driver and CUDA version:** the software layer between the model server and the GPU.

## What you will do

- Read `nvidia-smi` output field by field while idle, while a model is loaded and during generation.
- Load models of different sizes in Ollama and watch VRAM usage change.
- Increase the context length and observe the effect on VRAM.
- Record a simple table: model, size, VRAM used, tokens per second.

## Done when

- [ ] I can explain every field in `nvidia-smi` output
- [ ] I can explain why a 27B model uses more VRAM than its file size
- [ ] My measurement table is in the Notes section

## Notes

-
EOF

cat > ai-labs/08-vllm-serving.md << 'EOF'
# AI Lab 08 – Serving models with vLLM

## Goal

Run a model with vLLM, a production-grade inference server, and compare it with Ollama.

## Concepts

- **Inference server:** a service that loads a model and answers requests over HTTP.
- **OpenAI-compatible API:** most tools speak this API, so one server works with many clients.
- **Batching:** serving many users at once efficiently. This is where vLLM beats Ollama.
- **Model formats and quantization for vLLM:** why vLLM uses different model files than Ollama.

## What you will do

- Run vLLM in Docker on the Windows host with GPU access (Docker Desktop + WSL2 backend).
  VirtualBox cannot access the GPU, so vLLM runs on the host, like Ollama.
- Serve one model that fits into 24 GB VRAM.
- Call it from the VM with `curl` and from Python.
- Send 10 requests in parallel to Ollama and to vLLM and compare total time.

## Done when

- [ ] vLLM answers requests from the VM
- [ ] I can explain the difference between Ollama and vLLM in two sentences
- [ ] Parallel request comparison is in the Notes section

## Notes

-
EOF

cat > ai-labs/09-litellm-gateway.md << 'EOF'
# AI Lab 09 – LiteLLM gateway

## Goal

Put one gateway in front of all models, so users get one endpoint and one API key,
and I control access, routing and usage.

## Concepts

- **Gateway:** a single entry point that forwards requests to the right model backend.
- **Virtual API keys:** one key per team or user, revocable, with limits.
- **Routing and fallback:** send a request to vLLM, fall back to Ollama if vLLM is down.
- **Usage reporting:** who used which model, how many tokens, when.

## What you will do

- Run LiteLLM in Docker in the VM, with its PostgreSQL database.
- Register both backends: vLLM and Ollama.
- Create API keys for two fictional teams ("sap-ops", "dev") with different limits.
- Stop vLLM and verify the fallback works.
- Produce a usage report per team.

## Done when

- [ ] Both teams can call models only with their own key
- [ ] A team hitting its limit gets a clear error
- [ ] Fallback works when one backend is down
- [ ] I can show token usage per team

## Notes

-
EOF

cat > ai-labs/10-open-webui.md << 'EOF'
# AI Lab 10 – Open WebUI

## Goal

Give users a ChatGPT-like web interface on top of the platform, without direct access to backends.

## Concepts

- **Front end vs. gateway:** the UI talks only to LiteLLM, never directly to vLLM or Ollama.
- **Users and roles:** admin vs. regular user.
- **Self-service:** users should not need me to start using the platform.

## What you will do

- Run Open WebUI in Docker in the VM, connected to LiteLLM.
- Create an admin and two regular users.
- Decide which models regular users can see.
- Upload a fictional runbook and ask questions about it (built-in RAG).

## Done when

- [ ] Users log in and chat without knowing where the model runs
- [ ] Model visibility is controlled by the admin
- [ ] Requests from Open WebUI appear in the LiteLLM usage report

## Notes

-
EOF

cat > ai-labs/11-observability.md << 'EOF'
# AI Lab 11 – Observability: Prometheus + Grafana

## Goal

See the health of the platform on one dashboard and get alerted before users notice problems.
Builds on DevOps lab 10 (Prometheus & Grafana).

## Concepts

- **GPU metrics:** utilization, VRAM, temperature, power.
- **Inference metrics:** requests per second, time to first token (TTFT), tokens per second,
  queue length, error rate.
- **Percentiles again:** p50 vs. p95 latency (study guide, week 2).
- **Good alerts:** actionable, few false positives (study guide, week 3 – alert fatigue).

## What you will do

- Scrape vLLM and LiteLLM metrics with Prometheus.
- Export GPU metrics from the Windows host.
- Build one Grafana dashboard: GPU, latency percentiles, throughput, errors, usage per team.
- Define 3 alerts, for example: GPU temperature too high, p95 latency too high, backend down.
- Trigger each alert on purpose.

## Done when

- [ ] One dashboard shows GPU and inference health
- [ ] Every alert fired once in a controlled test
- [ ] Each alert has a one-line "what to do" description

## Notes

-
EOF

cat > ai-labs/12-benchmarking-evaluation.md << 'EOF'
# AI Lab 12 – Benchmarking and model evaluation

## Goal

Recommend which model to run based on measurements: speed on my hardware and answer quality
on my own tasks.

## Concepts

- **Performance:** TTFT, tokens per second, throughput under parallel load.
- **Quality:** a small test set of realistic tasks with expected answers (Lab 06 approach).
- **Trade-offs:** bigger model = better answers but slower and fewer parallel users.

## What you will do

- Pick 2–3 current open-weight models that fit into 24 GB VRAM.
- Measure performance with 1, 5 and 10 parallel users.
- Build a quality test set of 15–20 SAP-operations-style tasks (fictional data only).
- Score the answers and write a one-page recommendation.

## Done when

- [ ] Performance table for all models
- [ ] Quality scores for all models
- [ ] One-page recommendation: which model, for what, and why

## Notes

-
EOF

cat > ai-labs/13-platform-operations.md << 'EOF'
# AI Lab 13 – Platform operations

## Goal

Run the homelab like a real internal service: documented, repeatable, with clear rules.

## Concepts

- **Onboarding guide:** a new developer gets a key and makes the first call in 10 minutes, alone.
- **Runbooks:** model upgrade, backend down, GPU overheating, key revocation.
- **Priorities and queueing:** interactive users vs. overnight batch jobs.
- **Infrastructure as Code:** the whole platform can be rebuilt from the repository.

## What you will do

- Write the onboarding guide and test it on the fictional "dev" team.
- Write four runbooks.
- Define a priority policy: who goes first, what runs overnight.
- Make the platform reproducible with docker compose files and an Ansible playbook.
- Perform one model upgrade following your own runbook.

## Done when

- [ ] Onboarding guide works without my help
- [ ] Four runbooks exist and one was used for a real upgrade
- [ ] The platform can be rebuilt from the repository

## Notes

-
EOF

echo
echo "Created:"
ls -1 ai-labs/00-platform-roadmap.md ai-labs/0[7-9]-*.md ai-labs/1[0-3]-*.md
echo
echo "Next: add the new labs to README.md, then git add / commit."
