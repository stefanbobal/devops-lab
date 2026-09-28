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
