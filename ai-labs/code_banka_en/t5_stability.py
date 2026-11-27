"""T5: is the agent repeatable? Compares repeated runs of t3_chain.py on the same cases.

Usage: python t5_stability.py <tag> [<tag> ...]
Reads results/t3_chain_<tag>_r1.json, _r2.json, ... (written by t3_chain.py --repeats N --tag <tag>).
Several tags are compared side by side (e.g. two models). Nothing is written except a printed report.

Per case (all runs of one tag):
  stable             every run gave the same status
  harmless unstable  statuses differ, but never breach vs no_breach (e.g. one run stopped in human_review)
  dangerous unstable one run said breach and another no_breach (the verdict itself flipped)
Besides the status, the extracted items and the specification are compared run to run, so a hidden wobble
(same status, different spec) is visible too. Reproducibility does not equal correctness: the report also
shows how many runs of each case matched expected_status.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

from t3_spec import normalize

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "results"


def load_runs(tag, results_dir=RESULTS):
    pattern = re.compile(rf"t3_chain_{re.escape(tag)}_r(\d+)\.json")   # exact tag: t5_qwen38 must not match t5_qwen38_7r
    found = [(int(m.group(1)), p) for p in results_dir.glob("t3_chain_*.json") if (m := pattern.fullmatch(p.name))]
    return [json.loads(p.read_text("utf-8")) for _, p in sorted(found)]


def category(statuses):
    """statuses: the status of one case in every run."""
    s = set(statuses)
    if len(s) == 1:
        return "stable"
    if {"breach", "no_breach"} <= s:
        return "dangerous"
    return "harmless"


def spec_variants(specs, period):
    """Number of distinct decisive specifications (ignoring free labels and citations); runs without a spec
    count as one separate variant 'none'."""
    seen = set()
    for spec in specs:
        if not spec:
            seen.add("none")
            continue
        try:   # same normalisation as T3a
            seen.add(json.dumps(normalize(spec, period), sort_keys=True))
        except (KeyError, TypeError, ValueError):
            seen.add("invalid")
    return len(seen)


def item_variants(items_list):
    return len({json.dumps(i, sort_keys=True, ensure_ascii=False) for i in items_list})


def analyse(runs):
    """runs: list of loaded result files (each with rows). Returns one dict per case."""
    out = []
    for case_id in [r["case_id"] for r in runs[0]["rows"]]:
        rows = [next(r for r in run["rows"] if r["case_id"] == case_id) for run in runs]
        period = case_id.split("-")[1]
        statuses = [r["got"] for r in rows]
        out.append(dict(
            case_id=case_id, expected=rows[0]["expected"], statuses=statuses, category=category(statuses),
            correct=sum(1 for r in rows if r["got"] == r["expected"]),
            spec_variants=spec_variants([r.get("spec") for r in rows], period),
            item_variants=item_variants([r.get("items") for r in rows]),
            stages=[r["stage"] for r in rows if r["stage"]],
            reasons=sorted({x for r in rows if r["got"] != r["expected"] for x in r["reasons"]})))
    return out


def report(tag, runs):
    cases = analyse(runs)
    n = len(runs)
    cats = Counter(c["category"] for c in cases)
    total_ok = sum(c["correct"] for c in cases)
    print(f"\n=== {tag}: {n} runs x {len(cases)} cases (llm {runs[0]['llm']}) ===")
    print(f"stable {cats['stable']} | harmless unstable {cats['harmless']} | dangerous unstable {cats['dangerous']}")
    print(f"matched expected_status: {total_ok}/{n * len(cases)} case-runs | "
          f"exact in every run: {sum(1 for c in cases if c['correct'] == n)}/{len(cases)}")
    wobble = [c for c in cases if c["category"] == "stable" and (c["spec_variants"] > 1 or c["item_variants"] > 1)]
    print(f"same status but different spec/items between runs: {len(wobble)}")
    times = [sum(r["seconds"] for r in run["rows"]) for run in runs]
    print(f"seconds per run: {', '.join(f'{t:.0f}' for t in times)}")
    for c in cases:
        if c["category"] != "stable" or c["correct"] != n or c in wobble:
            print(f"  {c['case_id']} [{c['category']}] expected {c['expected']}, got {c['statuses']} "
                  f"| spec variants {c['spec_variants']}, item variants {c['item_variants']}")
            for reason in c["reasons"]:
                print(f"      reason: {reason}")
    return cats


def main(argv):
    if not argv:
        raise SystemExit("Give at least one tag, e.g. python t5_stability.py t5_qwen38")
    for tag in argv:
        runs = load_runs(tag)
        if len(runs) < 2:
            print(f"\n=== {tag}: found {len(runs)} run files (results/t3_chain_{tag}_r*.json), need at least 2")
            continue
        report(tag, runs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
