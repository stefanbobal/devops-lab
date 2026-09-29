# Home AIOps Investigation Agent – Design

Generic design for a home lab. Rebuilds the core ideas of a production AIOps
platform on **fictional systems and data**. No company code, names, hosts or
configurations.

## 1. Goal

Fewer isolated alerts, better incident context, repeatable investigations:

```
OBSERVE -> DETECT -> NORMALIZE -> CORRELATE -> CREATE INCIDENT -> BUILD EVIDENCE
-> INVESTIGATE -> CALL SAFE TOOLS -> REASON -> COMPARE WITH HISTORY
-> SUPPORTED HYPOTHESIS -> RECOMMEND -> LEARN
```

## 2. Principles

- **Monitoring works without AI.** Deterministic rules decide "is CPU > 90 %" or
  "did the backup fail". The LLM only answers "why" and "what next".
- **Alert ≠ incident.** Many raw signals are grouped into one incident that needs
  human action. Everything else is an INFO signal.
- **Topology is a hard boundary.** Each system has a known type, database,
  host and hosting model. Unknown topology = fail closed.
- **The LLM never gets a shell.** It selects a *logical tool*; a gateway validates
  arguments and executes. No free SQL, hosts, paths or playbooks.
- **Read-only investigation.** No autonomous remediation.
- **Aggressive in gathering safe evidence, conservative in claiming root cause.**
- **A failed tool is missing evidence, never "normal".**
- **Negative evidence counts** (e.g. application slow, but load balancer normal).
- **History is context, not proof.**
- **Tool output is untrusted data** (logs and traces can contain prompt injection).

## 3. Home architecture

| Production concept | Home equivalent |
| --- | --- |
| Managed Prometheus / cloud monitoring | Prometheus + node_exporter in the VM |
| Application / database collectors | `fake_app_exporter.py`: simulated app metrics with fault injection |
| Operational database | PostgreSQL (the pgvector container from AI Labs 03–06) |
| Automation platform for diagnostics | Ansible playbooks run locally via `ansible-runner` |
| Corporate LLM gateway | Ollama / LiteLLM (OpenAI-compatible API) |
| Scheduled cloud jobs | docker compose services or k3s CronJobs |
| Chat notifications | Console output or a simple web page |

```
fake_app_exporter + node_exporter ──► Prometheus  (telemetry memory)
                                          │
                                   detector.py ──► PostgreSQL  (incidents, investigations, audit)
                                                        │
                                              investigator.py ◄──► LLM (Ollama / LiteLLM)
                                                        │
                                              tool_gateway.py ──► Ansible playbooks (read-only)
```

Storage rule: **Prometheus keeps the time series, PostgreSQL keeps the story**
(incidents, lifecycle, findings, investigations, tool audit). Never copy all
samples into PostgreSQL.

## 4. Phases

### Phase 1 – Collection

- Prometheus + node_exporter (CPU, memory, filesystem).
- `fake_app_exporter.py` exposes simulated application metrics: response time,
  busy work processes, error dumps, last backup timestamp and status.
- Fault injection scripts: fill a filesystem, CPU hog, failed backup,
  slow response time.

### Phase 2 – Detection and incidents

- `detector.py` reads Prometheus every 1–2 minutes.
- **Hard-state triggers** (no statistics): system down, backup failed,
  filesystem critically full.
- **Anomaly triggers:** baseline (same hour last 7 days), p95, deviation,
  persistence (e.g. 3 samples in a row), trend, hysteresis.
- **Grouping key:** system + domain + time window + signature
  (four backup signals on one system = one incident).
- **Lifecycle:** OPEN → ACTIVE → WORSENING → RECOVERING → RESOLVED.
- **System profile:** environment (DEV/TEST/PROD); DEV never CRITICAL;
  maintenance mode suppresses incidents.

### Phase 3 – Tools and gateway

- Tool registry with 3–4 logical tools implemented as Ansible playbooks:
  `filesystem_usage`, `largest_files`, `top_cpu_processes`, `read_backup_log`.
- Every playbook returns **one structured JSON result**:
  `tool, status, system, summary, hosts[{host, findings, errors, truncated}]`.
  Errors (e.g. permission denied) are separated from data.
- Gateway rules: allowlisted tools and arguments, host and system injected from
  topology (the LLM never invents hosts), timeouts, bounded output,
  audit record for every call (tool, args, status, elapsed, result hash).

### Phase 4 – Investigation loop

```
load evidence
repeat until budget:
    LLM returns ONE JSON action: {tool_request | conclude}
    resolve arguments from topology
    skip duplicates (same tool + args)
    run tool via gateway
    classify outcome: usable | failure class
    one retry for timeout / transient error; exclude broken tools
finalize
```

- **Budgets:** max steps, max tool calls, max tokens, deadline, per-call timeout.
- **Failure classes:** EMPTY_RESULT / PARTIAL_RESULT (usable, negative evidence)
  vs. TIMEOUT, TOOL_ERROR, UNREACHABLE, DUPLICATE (not usable = missing evidence).
- **Finalize:** if the loop ends without a conclusion, make one conclude-only LLM
  call or return INCONCLUSIVE. Never reuse the last tool request reason as the
  hypothesis.
- **Root cause language:** OBSERVATION → TEMPORAL_CORRELATION → HYPOTHESIS →
  SUPPORTED_HYPOTHESIS → CONFIRMED_ROOT_CAUSE, or ROOT_CAUSE_NOT_CONFIRMED.
- **Persistence:** one incident → many investigations → steps
  (evidence, reasoning, tool request, result, conclusion).

### Phase 5 – Evaluation

- Replay set: 10 fault scenarios from Phase 1, each with the expected conclusion.
- Metrics: correct hypothesis, relevant vs. irrelevant tools, number of steps,
  overclaiming (CONFIRMED without evidence), tokens.
- Run the replay set after every prompt, tool or model change.

### Phase 6 – Historical memory

- pgvector as in AI Labs 03–06, one compact record per **validated** investigation.
- Order matters: noise reduction → working investigations → operator feedback →
  clean history → only then vector memory.

## 5. Data model (sketch)

| Table | Purpose |
| --- | --- |
| `system_profile` | system, environment, type, database, host, hosting, mode |
| `incidents` | grouping key, domain, severity, lifecycle status, timestamps |
| `investigations` | incident, status, final hypothesis, root cause level |
| `investigation_steps` | step type, tool, args, outcome, failure class, text |
| `tool_audit` | tool, args, status, elapsed ms, result hash |
| `feedback` | operator verdict, actual root cause, resolution |

## 6. Lessons learned (apply from day one)

- **Verify what the LLM actually receives.** Build a "sent to LLM" view or a
  dry-run script: raw tool result → parsed result → classification → final payload.
- **Read structured results from the right place**, not from human-readable logs.
- **Never truncate the payload blindly.** Give each section a size budget and strip
  debug fields; otherwise later tool results disappear and the model repeats tools.
- **Parse nested results correctly**; an empty parse must be an error, not "OK".
- **Keep stderr separate from data** in every tool.
- **Status and truncation flags must be real**, never hard-coded.
- **Mark failed runs as INVALID** and keep them out of metrics and memory.
- **Reduce noise before adding AI.** Bad alerts in = bad AI out.
- **Fixture-based tests** from real tool output JSON.
- **Working with Copilot:** plan first, one logical change per commit, give evidence
  (payloads, logs) instead of symptoms, trace the data path before fixing,
  tag known-good versions.

## 7. Safety checklist

- [ ] LLM can only select tools from the registry
- [ ] Hosts and systems come from topology, never from the LLM
- [ ] All tools are read-only and time-bounded
- [ ] Every tool call is audited
- [ ] Tool output is delimited and treated as untrusted
- [ ] Failed tools are never treated as normal
- [ ] Unconfirmed hypotheses are never presented as facts

## Notes

-
