"""T6: operations. Tokens, latency, errors and cost of the LLM calls, from results written by t3_chain.py.

Usage: python t6_ops.py <tag> [<tag> ...] [--date YYYY-MM-DD]
<tag> is a single run (results/t3_chain_<tag>.json) or a repeated one (<tag>_r1.json, _r2.json, ...).
Reads files only, calls no model. Needs runs made after the usage capture was added (steps carry an "llm" entry);
older files are reported as having no usage data.
Numbers come from the provider's usage report (llm_metrics.normalize_usage), never from text length. Cost is an
estimate from llm_prices.json (user-supplied rates); local Ollama models cost 0 here (no electricity counted).
Failed calls count too: a call whose answer could not be parsed still has tokens and a price.
"""
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

from llm_metrics import estimate_cost, normalize_usage, validate_prices

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "results"
OK_FINISH = {"stop", "end_turn", "STOP", None}   # None: provider did not report a finish reason


def percentile(values, q):
    """Nearest-rank percentile (q in 0..100); None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)]


def load_files(tag, results_dir=RESULTS):
    single = results_dir / f"t3_chain_{tag}.json"
    pattern = re.compile(rf"t3_chain_{re.escape(tag)}_r(\d+)\.json")
    repeated = sorted((int(m.group(1)), p) for p in results_dir.glob("t3_chain_*.json")
                      if (m := pattern.fullmatch(p.name)))
    paths = [p for _, p in repeated] or ([single] if single.exists() else [])
    return [json.loads(p.read_text("utf-8")) for p in paths]


def calls_of(runs, prices, pricing_date):
    """One dict per LLM call: step, latency, tokens, cost, finish status, case id."""
    calls = []
    for run in runs:
        for row in run["rows"]:
            for s in row["steps"]:
                info = s.get("llm")
                if not info:
                    continue
                usage = normalize_usage(info["provider"], info["usage_raw"])
                cost = estimate_cost(info["provider"], info["model"], usage, prices, pricing_date)
                calls.append(dict(case_id=row["case_id"], step=s["step"], latency_s=info["latency_s"],
                                  input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
                                  cost=cost["estimated_cost_usd"], cost_status=cost["cost_status"],
                                  finish_ok=info["finish_reason"] in OK_FINISH,
                                  parse_failed=s["status"] == "failed",
                                  eval_count=info["usage_raw"].get("eval_count"),
                                  eval_duration=info["usage_raw"].get("eval_duration")))
    return calls


def summarize(runs, calls):
    n_cases = sum(len(r["rows"]) for r in runs)
    total_s = sum(c["latency_s"] for c in calls)
    out = dict(runs=len(runs), cases=n_cases, calls=len(calls),
               incomplete_calls=sum(1 for c in calls if not c["finish_ok"]),
               failed_steps=sum(1 for c in calls if c["parse_failed"]),
               input_tokens=sum(c["input_tokens"] or 0 for c in calls),
               output_tokens=sum(c["output_tokens"] or 0 for c in calls),
               missing_usage=sum(1 for c in calls if c["input_tokens"] is None or c["output_tokens"] is None),
               llm_seconds=total_s, steps={})
    costs = [c["cost"] for c in calls]
    out["cost_unknown_calls"] = sum(1 for c in costs if c is None)
    out["cost_usd"] = sum(c for c in costs if c is not None)
    out["cost_statuses"] = sorted({c["cost_status"] for c in calls})
    for step in sorted({c["step"] for c in calls}):
        sc = [c for c in calls if c["step"] == step]
        lat = [c["latency_s"] for c in sc]
        out["steps"][step] = dict(
            calls=len(sc), p50=percentile(lat, 50), p95=percentile(lat, 95), max=max(lat),
            mean_in=sum(c["input_tokens"] or 0 for c in sc) / len(sc),
            mean_out=sum(c["output_tokens"] or 0 for c in sc) / len(sc))
    ev = [(c["eval_count"], c["eval_duration"]) for c in calls if c["eval_count"] and c["eval_duration"]]
    out["tokens_per_second"] = sum(a for a, _ in ev) / (sum(b for _, b in ev) / 1e9) if ev else None
    return out


def report(tag, runs, prices, pricing_date):
    calls = calls_of(runs, prices, pricing_date)
    if not calls:
        print(f"\n=== {tag}: no usage data (runs made before the usage capture was added)")
        return None
    s = summarize(runs, calls)
    print(f"\n=== {tag}: {s['runs']} run(s), {s['cases']} case-runs, {s['calls']} LLM calls "
          f"(llm {runs[0]['llm']}) ===")
    print(f"tokens in {s['input_tokens']:,} | out {s['output_tokens']:,} | per case-run in "
          f"{s['input_tokens'] / s['cases']:.0f}, out {s['output_tokens'] / s['cases']:.0f}")
    print(f"calls without usage: {s['missing_usage']} | incomplete (finish reason not stop): "
          f"{s['incomplete_calls']} | answers the agent could not use: {s['failed_steps']}")
    if s["tokens_per_second"]:
        print(f"generation speed (local): {s['tokens_per_second']:.1f} tokens/s")
    for step, v in s["steps"].items():
        print(f"  {step:8} calls {v['calls']:4} | latency p50 {v['p50']:.1f}s p95 {v['p95']:.1f}s max {v['max']:.1f}s "
              f"| mean tokens in {v['mean_in']:.0f} out {v['mean_out']:.0f}")
    per_case = s["llm_seconds"] / s["cases"]
    print(f"LLM time per case-run: {per_case:.1f}s")
    note = "" if not s["cost_unknown_calls"] else f" (+ {s['cost_unknown_calls']} calls with unknown price)"
    print(f"estimated cost: ${s['cost_usd']:.4f} total, ${s['cost_usd'] / s['cases']:.5f} per case-run{note} "
          f"| status: {', '.join(s['cost_statuses'])}")
    return s


def main(argv):
    pricing_date = date.today().isoformat()
    if "--date" in argv:
        i = argv.index("--date")
        pricing_date = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        raise SystemExit("Give at least one tag, e.g. python t6_ops.py t6_qwen38 t6_haiku")
    prices = json.loads((BASE / "llm_prices.json").read_text("utf-8"))
    validate_prices(prices)
    for tag in argv:
        runs = load_files(tag)
        if not runs:
            print(f"\n=== {tag}: no result files found")
            continue
        report(tag, runs, prices, pricing_date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
