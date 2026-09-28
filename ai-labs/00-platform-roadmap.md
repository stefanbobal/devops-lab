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
