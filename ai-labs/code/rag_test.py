"""Sequential RAG matrix, frozen contexts, per-call usage and resumable result files.

Default is a dry run. --execute starts model calls. See rag_test_README.md.
"""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    temp.replace(path)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def worker(request):
    """Each subprocess imports config after its profile environment is selected."""
    from config import EMBED_MODEL, EMBED_PROVIDER, PROFILE
    if request["operation"] == "retrieve":
        from search import find_similar
        from rag_prompt import format_context
        scenario = request["scenario"]
        started = time.perf_counter()
        rows = find_similar(scenario["incident"], scenario.get("domain"),
                            scenario.get("db_type"), request["top_k"])
        elapsed = time.perf_counter() - started
        history = [r for r in rows if r["similarity"] >= request["threshold"]]
        return dict(status="ok", profile=PROFILE, model=EMBED_MODEL, provider=EMBED_PROVIDER,
                    retrieval_latency_s=elapsed, threshold=request["threshold"],
                    candidates=rows, history=history, context=format_context(history),
                    context_hash=digest(history), created_at=utc_now())
    from llm_metrics import chat_measured
    return chat_measured(request["system"], request["user"], request["max_tokens"], request["timeout"],
                         request.get("ollama_num_ctx", 8192))


def safe_error(exc):
    text = str(exc)
    for key, value in os.environ.items():
        if any(part in key.upper() for part in ("KEY", "SECRET", "TOKEN", "PASSWORD", "DSN")) and len(value) > 5:
            text = text.replace(value, "[REDACTED]")
    return type(exc).__name__ + ": " + text[:1500]


def run_worker(request, embedding, llm, timeout):
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="rag-worker-") as temp:
        source, target = Path(temp) / "request.json", Path(temp) / "response.json"
        write_json(source, request)
        env = {**os.environ, "EMBED_PROFILE": embedding, "LLM_PROFILE": llm}
        try:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                     "--worker", str(source), str(target)], env=env, cwd=BASE,
                                    capture_output=True, text=True, timeout=timeout + 15)
            if target.exists():
                response = read_json(target)
            else:
                response = {"status": "error", "error": f"Worker exit {result.returncode}; no result"}
        except subprocess.TimeoutExpired:
            response = {"status": "timeout", "error": "Worker deadline exceeded; billing may still occur"}
    response["worker_wall_s"] = time.perf_counter() - started
    return response


def selected(text, available):
    values = list(available) if text == "all" else text.split(",")
    if not values or len(set(values)) != len(values) or any(v not in available for v in values):
        raise ValueError(f"Invalid/duplicate profiles {text!r}; choose from {', '.join(available)}")
    return values


def validate_scenarios(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Scenario JSON must contain a nonempty list")
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
            raise ValueError("Each scenario needs a nonempty string id")
        if row["id"] in ids:
            raise ValueError("Duplicate scenario id: " + row["id"])
        ids.add(row["id"])
        if not isinstance(row.get("incident"), str) or not row["incident"].strip():
            raise ValueError("Each scenario needs incident text")
        for key in ("domain", "db_type", "curated_context"):
            if row.get(key) is not None and not isinstance(row[key], str):
                raise ValueError(key + " must be text or null")
    return rows


def export_results(out):
    records = [read_json(path) for path in sorted((out / "calls").glob("*.json"))]
    fields = ["call_id", "scenario_id", "embedding_profile", "llm_profile", "mode", "repeat",
              "status", "model", "resolved_model", "embedding_model", "threshold", "finish_reason", "retrieval_latency_s",
              "llm_latency_s", "worker_wall_s", "pipeline_latency_estimate_s", "input_tokens",
              "output_tokens", "reasoning_tokens", "cached_input_tokens", "cache_creation_tokens",
              "output_tokens_per_wall_second", "load_duration_s", "generation_tokens_per_second", "ollama_num_ctx",
              "estimated_cost_usd", "cost_status", "context_hash", "answer", "error"]
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    groups = {}
    for row in records:
        key = (row["embedding_profile"], row["llm_profile"], row["mode"])
        groups.setdefault(key, []).append(row)
    summaries = []
    for (embedding, llm, mode), rows in groups.items():
        times = sorted(r["llm_latency_s"] for r in rows if r["status"] == "ok" and "llm_latency_s" in r)
        percentile = lambda p: times[max(0, math.ceil(p * len(times)) - 1)] if times else None
        summaries.append(dict(embedding_profile=embedding, llm_profile=llm, mode=mode, calls=len(rows),
            ok=sum(r["status"] == "ok" for r in rows), failures=sum(r["status"] != "ok" for r in rows),
            llm_p50_s=percentile(.5), llm_p95_s=percentile(.95),
            known_llm_cost_usd=sum(r["estimated_cost_usd"] for r in rows if r.get("estimated_cost_usd") is not None),
            unknown_cost_calls=sum(r.get("estimated_cost_usd") is None for r in rows)))
    write_json(out / "summary.json", summaries)
    # A separate review template is never overwritten after human scoring.
    review = out / "quality_review.csv"
    columns = ["call_id", "relevance_0_2", "evidence_0_2", "citations_0_2",
               "uncertainty_0_2", "actionability_0_2", "critical_error", "notes"]
    reviewed = set()
    if review.exists():
        with review.open(newline="", encoding="utf-8") as stream:
            reviewed = {r["call_id"] for r in csv.DictReader(stream)}
    new_file = not review.exists()
    with review.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        if new_file:
            writer.writeheader()
        writer.writerows({"call_id": r["call_id"]} for r in records if r["call_id"] not in reviewed)
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", default="all", help="Comma-separated profiles or all")
    parser.add_argument("--llms", default="all", help="Comma-separated profiles or all")
    parser.add_argument("--scenarios", type=Path, default=BASE / "rag_scenarios.json")
    parser.add_argument("--thresholds-file", type=Path, default=BASE / "thresholds_FROZEN.json")
    parser.add_argument("--prices", type=Path, default=BASE / "llm_prices.json")
    parser.add_argument("--pricing-date", default=datetime.now().date().isoformat(),
                        help="YYYY-MM-DD; override only for a hypothetical pricing scenario")
    parser.add_argument("--modes", default="rag", help="rag,no_history,curated (controls run once per LLM)")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--ollama-num-ctx", type=int, default=8192,
                        help="Explicit Ollama context allocation; verify prompt headroom and GPU residency")
    parser.add_argument("--order", choices=("shuffled", "by-model"), default="shuffled",
                        help="Group shuffled jobs by LLM to reduce local model swaps")
    parser.add_argument("--prepare-contexts", action="store_true",
                        help="With --execute: retrieve/cache all contexts and exit without LLM calls")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-calls", type=int, help="Stop after this many new LLM calls; resume later")
    parser.add_argument("--out", type=Path, default=BASE / "results" / "rag-test")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Enable API calls; otherwise dry run")
    args = parser.parse_args(argv)
    from config import LLMS, MODELS, GCP_PROJECT, VERTEX_LLM_LOCATION, VERTEX_EMBED_LOCATION
    from rag import load_threshold
    from rag_prompt import build_prompts, format_context
    from llm_metrics import estimate_cost, validate_prices
    try:
        embeddings, llms = selected(args.embeddings, MODELS), selected(args.llms, LLMS)
        modes = selected(args.modes, {m: None for m in ("rag", "no_history", "curated")})
        scenarios = validate_scenarios(read_json(args.scenarios))
        if min(args.repeats, args.top_k, args.max_output_tokens) < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("Repeats, top-k, token cap and timeout must be positive")
        if args.max_calls is not None and args.max_calls < 1:
            raise ValueError("max-calls must be positive")
        if args.ollama_num_ctx < 1:
            raise ValueError("ollama-num-ctx must be positive")
        if any(LLMS[p]["provider"] == "ollama" for p in llms) and args.ollama_num_ctx <= args.max_output_tokens:
            raise ValueError("ollama-num-ctx must exceed max-output-tokens; also allow room for input tokens")
        if args.prepare_contexts and "rag" not in modes:
            raise ValueError("prepare-contexts requires rag mode")
        datetime.strptime(args.pricing_date, "%Y-%m-%d")
        if "curated" in modes and any(not s.get("curated_context") for s in scenarios):
            raise ValueError("Every scenario needs curated_context for curated mode")
        thresholds = {p: load_threshold(p, args.thresholds_file) for p in embeddings}
        prices = read_json(args.prices)
        validate_prices(prices)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    jobs = []
    for s in scenarios:
        for mode in modes:
            for embed in embeddings if mode == "rag" else ["none"]:
                for llm in llms:
                    for repetition in range(1, args.repeats + 1):
                        job = dict(scenario_id=s["id"], embedding_profile=embed,
                                   llm_profile=llm, mode=mode, repeat=repetition)
                        job["call_id"] = digest(job)[:24]
                        jobs.append(job)
    random.Random(args.seed).shuffle(jobs)
    if args.order == "by-model":
        jobs.sort(key=lambda job: llms.index(job["llm_profile"]))
    print(f"{len(scenarios)} scenarios; {len(embeddings)} embeddings; {len(llms)} LLMs; {len(jobs)} calls")
    print("Pricing date:", args.pricing_date, "| output:", args.out.resolve())
    print("Cloud cost is an estimate; missing prices/usage remain unknown. Retrieval cost is excluded.")
    if args.prepare_contexts:
        print(f"Prepare-only stage: {len(scenarios) * len(embeddings)} contexts; zero LLM calls")
    if not args.execute:
        print("Dry run: no database or model calls. Add --execute to run.")
        return 0
    versions = {}
    for package in ("openai", "anthropic", "google-genai", "ollama", "psycopg", "pgvector"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not installed"
    manifest = dict(schema_version=2, scenarios=scenarios, thresholds=thresholds,
        embeddings={p: MODELS[p] for p in embeddings}, llms={p: LLMS[p] for p in llms}, prices=prices,
        pricing_date=args.pricing_date, modes=modes, repeats=args.repeats, top_k=args.top_k,
        max_output_tokens=args.max_output_tokens, timeout=args.timeout, seed=args.seed,
        ollama_num_ctx=args.ollama_num_ctx, order=args.order,
        generation_settings="Provider defaults except output cap and explicit Ollama num_ctx; no automatic retries",
        project=GCP_PROJECT, vertex_llm_location=VERTEX_LLM_LOCATION,
        vertex_embed_location=VERTEX_EMBED_LOCATION, azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        python=platform.python_version(), packages=versions,
        sources={f: hashlib.sha256((BASE / f).read_bytes()).hexdigest() for f in
                 ("rag_test.py", "rag_prompt.py", "llm_metrics.py", "rag.py", "search.py", "providers.py", "config.py")})
    fingerprint = digest(manifest)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    # Exclusive lock avoids concurrent runs corrupting or paying for duplicate jobs.
    lock = out / ".running"
    try:
        handle = lock.open("x")
    except FileExistsError:
        parser.error(f"{lock} exists; another run may be active. Remove only after confirming it stopped.")
    try:
        handle.write(str(os.getpid()))
        handle.close()
        manifest_path = out / "manifest.json"
        if manifest_path.exists():
            if not args.resume:
                parser.error("Output already contains a run; use --resume or a new --out directory")
            if read_json(manifest_path)["fingerprint"] != fingerprint:
                parser.error("Resume configuration/code differs; use a new --out directory")
        else:
            if args.resume:
                parser.error("Cannot resume without manifest.json")
            write_json(manifest_path, {"fingerprint": fingerprint, "created_at": utc_now(), **manifest})
        for folder in ("contexts", "calls"):
            (out / folder).mkdir(exist_ok=True)
        by_id = {s["id"]: s for s in scenarios}
        if args.prepare_contexts:
            failures = 0
            # Embedding outer loop minimizes embedding-model swaps on a single GPU.
            for embedding in embeddings:
                for scenario in scenarios:
                    path = out / "contexts" / (digest([scenario["id"], embedding]) + ".json")
                    if path.exists():
                        context = read_json(path)
                    else:
                        context = run_worker(dict(operation="retrieve", scenario=scenario, top_k=args.top_k,
                            threshold=thresholds[embedding]), embedding, llms[0], args.timeout)
                        write_json(path, context)
                    failures += context["status"] != "ok"
                    print(f"Context {scenario['id']}/{embedding}: {context['status']}", flush=True)
            print(f"Prepared contexts; failures={failures}. No LLM calls. Continue with --resume without --prepare-contexts.")
            return 1 if failures else 0
        completed_now = 0
        for job in jobs:
            target = out / "calls" / (job["call_id"] + ".json")
            if target.exists():
                continue  # Includes failed/incomplete calls; no silent paid retries.
            if args.max_calls is not None and completed_now >= args.max_calls:
                break
            scenario = by_id[job["scenario_id"]]
            embedding = job["embedding_profile"]
            if job["mode"] == "rag":
                context_file = out / "contexts" / (digest([scenario["id"], embedding]) + ".json")
                if context_file.exists():
                    context = read_json(context_file)
                else:
                    context = run_worker(dict(operation="retrieve", scenario=scenario, top_k=args.top_k,
                        threshold=thresholds[embedding]), embedding, job["llm_profile"], args.timeout)
                    write_json(context_file, context)
                if context["status"] != "ok":
                    write_json(target, {**job, "status": "retrieval_error", "error": context.get("error"),
                                        "cost_status": "llm_not_called", "estimated_cost_usd": 0.0})
                    continue
            else:
                text = scenario["curated_context"] if job["mode"] == "curated" else format_context([])
                context = dict(context=text, context_hash=digest(text), retrieval_latency_s=0, history=[])
            system, user = build_prompts(scenario["incident"], context["context"])
            # Persist a pending marker BEFORE dispatch. After a crash, never silently repeat
            # a request that may already have been billed by the provider.
            record = {**job, "status": "pending", "started_at": utc_now(),
                      "model": LLMS[job["llm_profile"]]["name"],
                      "provider": LLMS[job["llm_profile"]]["provider"],
                      "embedding_model": MODELS[embedding]["name"] if embedding != "none" else None,
                      "threshold": thresholds.get(embedding),
                      "context_hash": context["context_hash"], "system_prompt": system, "user_prompt": user,
                      "retrieved_ids": [h["incident_id"] for h in context.get("history", [])],
                      "retrieval_latency_s": context["retrieval_latency_s"],
                      "cost_status": "unknown", "estimated_cost_usd": None}
            write_json(target, record)
            result = run_worker(dict(operation="chat", system=system, user=user,
                max_tokens=args.max_output_tokens, timeout=args.timeout, ollama_num_ctx=args.ollama_num_ctx),
                embeddings[0] if embedding == "none" else embedding, job["llm_profile"], args.timeout)
            record.update(result)
            if "input_tokens" in result:
                record.update(estimate_cost(record["provider"], record["model"], result, prices, args.pricing_date))
            if "llm_latency_s" in result:
                record["pipeline_latency_estimate_s"] = context["retrieval_latency_s"] + result["llm_latency_s"]
            record["finished_at"] = utc_now()
            write_json(target, record)
            completed_now += 1
            print(f"{completed_now}: {job['scenario_id']} {embedding}/{job['llm_profile']} "
                  f"{job['mode']} -> {record['status']} | {record.get('llm_latency_s')} s | "
                  f"tokens {record.get('input_tokens')}/{record.get('output_tokens')} | "
                  f"USD {record.get('estimated_cost_usd')}", flush=True)
        records = export_results(out)
        print(f"Saved {len(records)}/{len(jobs)} records to {out}")
        return 1 if any(r["status"] != "ok" for r in records) else 0
    finally:
        handle.close()
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        try:
            response = worker(read_json(sys.argv[2]))
        except (Exception, SystemExit) as exc:
            response = {"status": "error", "error": safe_error(exc)}
        write_json(sys.argv[3], response)
    else:
        raise SystemExit(main())
