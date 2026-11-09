"""T3: the whole agent on every dev case, compared with expected_status.

Usage: python t3_chain.py [--limit N] [--cases C01-2026Q1,...] [--repeats N] [--mode rag|full|generic|no_context] [--set dev|test --final] --tag name
--mode (step E): rag = vector search (default), full = all contract chunks of the company, generic = built-in
general rule without a contract, no_context = spec prompt without excerpts (see agent.MODES).
--repeats N runs the agent N times on the same cached search results and writes <tag>_r1 ... <tag>_rN.
LLM: LLM_PROFILE (default gemma), embedding: EMBED_PROFILE (default bge). A tag is required and an existing
result file is never overwritten. Dev set by default (data/); --set test --final evaluates the held-out data_test/ (refused without --final).
Phase 1 searches for all cases (only the embedding model is loaded), phase 2 runs the agent (only the LLM).
Key numbers: missed breaches (expected breach, got no_breach), false alarms, human_review share, and
which step stopped each case.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

import agent
from agent import log
from dataset import choose_set
from run_meta import run_metadata

BASE = Path(__file__).resolve().parent


def summarize(rows):
    """rows: dicts with expected, got, stage (step that ended in human_review, or None), values_ok."""
    n = len(rows)
    exact = sum(1 for r in rows if r["got"] == r["expected"])
    return dict(
        cases=n, exact=exact,
        missed_breach=[r["case_id"] for r in rows if r["expected"] == "breach" and r["got"] == "no_breach"],
        false_alarm=[r["case_id"] for r in rows if r["expected"] == "no_breach" and r["got"] == "breach"],
        review_expected=sum(1 for r in rows if r["expected"] == "human_review"),
        review_got=sum(1 for r in rows if r["got"] == "human_review"),
        stopped_at=dict(Counter(r["stage"] for r in rows if r["stage"])),
        matrix={f"{e} -> {g}": c for (e, g), c in sorted(Counter((r["expected"], r["got"]) for r in rows).items())},
    )


def first_stop(out):
    """Name of the first step that did not end well (the cause of a human_review), else None."""
    for s in out["steps"]:
        if s["status"] in ("failed", "problems", "refused"):
            return s["step"]
    return None


def main(argv):
    set_name, data_dir = choose_set(argv)
    opts = {a: argv[i + 1] for i, a in enumerate(argv)
            if a in ("--limit", "--cases", "--tag", "--repeats", "--mode") and i + 1 < len(argv)}
    if "--tag" not in opts:
        raise SystemExit("Give a tag, e.g. python t3_chain.py --tag qwen_run1 (existing results are never overwritten)")
    mode = opts.get("--mode", "rag")
    if mode not in agent.MODES:
        raise SystemExit(f"--mode must be one of {agent.MODES}")
    repeats = int(opts.get("--repeats", 1))
    if repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    # one run -> t3_chain_<tag>.json; several runs -> t3_chain_<tag>_r1.json ... _rN.json
    names = [opts["--tag"]] if "--repeats" not in opts else [f"{opts['--tag']}_r{i}" for i in range(1, repeats + 1)]
    out_files = [BASE / "results" / f"t3_chain_{n}.json" for n in names]
    existing = [f.name for f in out_files if f.exists()]
    if existing:
        raise SystemExit(f"{', '.join(existing)} already exists, choose another tag")
    from config import EMBED_MODEL, LLM_MODEL
    cases = json.loads((data_dir / "expected.json").read_text("utf-8"))
    if "--cases" in opts:
        cases = [c for c in cases if c["case_id"] in opts["--cases"].split(",")]
    if "--limit" in opts:
        cases = cases[:int(opts["--limit"])]
    log(f"T3 chain | LLM {LLM_MODEL} | embedding {EMBED_MODEL} | {len(cases)} cases | tag {opts['--tag']} | mode {mode} | set {set_name}")

    log("phase 1/2: search (embedding model only)" + ("" if mode == "rag" else f" - skipped in mode {mode}"))
    chunks = {}
    for i, case in enumerate(cases if mode == "rag" else [], 1):
        log(f"  search {i}/{len(cases)} {case['case_id']}")
        try:
            chunks[case["case_id"]] = agent.retrieve(case["company_id"], case["period"])
        except Exception as exc:   # becomes a human_review of this case inside the agent
            chunks[case["case_id"]] = exc

    def cached(case_id):
        def retrieve_fn(company_id, period):
            if isinstance(chunks[case_id], Exception):
                raise chunks[case_id]
            return chunks[case_id]
        return retrieve_fn

    log("phase 2/2: agent (the first answer can take a minute while a local model loads)")
    for run_no, out_file in enumerate(out_files, 1):
        log(f"--- run {run_no}/{len(out_files)} -> {out_file.name}")
        rows, started = [], time.time()
        for case in cases:
            t = time.time()
            out = agent.run(case["company_id"], case["period"], mode=mode, data_dir=data_dir,
                            retrieve_fn=cached(case["case_id"]) if mode == "rag" else None)
            want = case["expected_result"].get("values")
            values_ok = out["result"] is not None and want is not None and out["result"].get("values") == want
            rows.append(dict(case_id=case["case_id"], case_type=case["case_type"], expected=case["expected_status"],
                             got=out["status"], stage=first_stop(out), reasons=out["reasons"], values_ok=values_ok,
                             seconds=round(time.time() - t, 1), spec=out["spec"], items=out["items"],
                             steps=out["steps"]))
            mark = "ok " if rows[-1]["got"] == rows[-1]["expected"] else "DIFF"
            log(f"  [{mark}] {case['case_id']} expected {rows[-1]['expected']}, got {rows[-1]['got']}")

        summary = summarize(rows)
        out_file.parent.mkdir(exist_ok=True)
        out_file.write_text(json.dumps(dict(llm=LLM_MODEL, embedding=EMBED_MODEL, meta=dict(run_metadata(), mode=mode, dataset=set_name),
                                            summary=summary, rows=rows),
                                       ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"done in {time.time() - started:.0f}s | exact {summary['exact']}/{summary['cases']} | "
            f"human_review got {summary['review_got']} (expected {summary['review_expected']})")
        log(f"missed breaches: {summary['missed_breach'] or 'none'} | false alarms: {summary['false_alarm'] or 'none'}")
        log(f"matrix: {summary['matrix']}")
        if summary["stopped_at"]:
            log(f"human_review caused by step: {summary['stopped_at']}")
        log(f"wrote {out_file.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
