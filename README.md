# DevOps & AI Ops Lab

Hands-on learning environment for modern DevOps, platform engineering and AI operations.

## Goal

Build, deploy, automate, monitor and troubleshoot containerized applications using a modern
GitOps / DevOps toolchain, and learn how to run and evaluate AI components (LLMs, embeddings,
vector search) in an operations context.

## Technologies

- Linux
- Docker / containerd
- Kubernetes
- Terraform
- GitHub Actions
- ArgoCD
- Prometheus / Grafana
- GCP / GKE
- Ollama / local LLMs a PostgreSQL + pgvector

## Labs

1. [K3s Basics](labs/01-k3s-basics.md)
2. [Kubernetes Services](labs/02-services.md)
3. [Docker Basics & Custom Image](labs/03-docker-custom-image.md)
4. [Deploy Custom Docker Image to Kubernetes](labs/04-docker-image-to-kubernetes.md)
5. [ConfigMaps & Secrets](labs/05-configmaps-secrets.md)
6. Sealed Secrets / kubeseal
7. Ingress
8. GitHub Actions
9. ArgoCD / GitOps
10. [Prometheus & Grafana](labs/10-prometheus-grafana.md)
11. Terraform
12. GCP / GKE

## AI / AIOps Labs

0. [Roadmap](ai-labs/00-platform-roadmap.md)
1. [Local LLM with Ollama](ai-labs/01-local-llm-ollama.md)
2. [Embeddings](ai-labs/02-embeddings.md)
3. [PostgreSQL + pgvector: Incident Memory](ai-labs/03-pgvector-incident-memory.md)
4. [Similarity Search with Filters and Threshold](ai-labs/04-similarity-search.md)
5. [RAG with a Local LLM](ai-labs/05-rag-local-llm.md)
6. [Evaluating Retrieval](ai-labs/06-evaluation.md)
7. [GPU Fundamentals](ai-labs/07-gpu-fundamentals.md)
8. [Serving with vLLM](ai-labs/08-vllm-serving.md)
9. [LiteLLM Gateway](ai-labs/09-litellm-gateway.md)
10. [Open WebUI](ai-labs/10-open-webui.md)
11. [Observability: Prometheus + Grafana](ai-labs/11-observability.md)
12. [Benchmarking and Model Evaluation](ai-labs/12-benchmarking-evaluation.md)
13. [Platform Operations](ai-labs/13-platform-operations.md)


7. Anomaly Detection (z-score)
8. Multilingual Embeddings

### Experiment status — 30 October 2026

The basic RAG demonstration in Lab 05 was followed by the expanded retrieval evaluation in Lab 06:
200 fictional SAP HANA and Oracle incidents, eight embedding profiles, 33 tuning questions and
40 separate held-out questions. Gemini and Qwen 4B with a query instruction both scored 40/40,
with different amounts of irrelevant context. See [the recorded results](ai-labs/06-evaluation.md#results).

The next step is the [planned LLM comparison](ai-labs/05-rag-local-llm.md#planned-llm-comparison):
each candidate LLM over all eight embedding profiles using their own frozen thresholds.
The basic RAG demonstration is implemented; comparative LLM results are still pending.
Full agent investigations with tools and a linked investigation history are a later phase.

## Environment

- Host: Windows
- Hypervisor: VirtualBox
- Guest OS: Ubuntu Server
- Kubernetes distribution: k3s
- Development environment: VS Code Remote SSH

## Learning approach

The goal of this repository is not only to deploy working solutions, but also to understand how each component works, how to troubleshoot failures, and how the individual DevOps tools fit together.