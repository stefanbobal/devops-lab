"""T1: how accurate is the extraction of items from the statement (step 1 + check_items)?

Usage: python t1_extraction.py <tag> [<tag> ...]
<tag> is a single run (results/t3_chain_<tag>.json) or a repeated one (<tag>_r1.json ...). Reads files only,
calls no model; dev set (data/expected.json) by default, --set test --final for data_test/.

Each of the 10 items of each case-run is compared with expected_items:
  correct   same value (or both missing, as expected for a statement that omits the item)
  missing   expected a value, got none: either the model returned none or check_items rejected the number
  invented  expected no value (the statement does not give it), got a number that passed check_items
  wrong     expected one number, got a different one that passed check_items (found on the cited page, yet
            it belongs to another item): the dangerous kind, it only gets caught later or never
check_items already drops numbers that are not printed on the cited page, so a fabricated number shows up as
"missing" here and as a problem in the check_items step (counted as "rejected").
Page numbers are not saved in the results (only values), so page accuracy is NOT measured here.
"""
import json
import sys
from collections import Counter
from pathlib import Path

from t6_ops import load_files

BASE = Path(__file__).resolve().parent


def classify(expected, got):
    if expected is None:
        return "correct" if got is None else "invented"
    if got is None:
        return "missing"
    return "correct" if got == expected else "wrong"


def analyse(runs, expected_items):
    """expected_items: {case_id: {item: {"value": v, "page": p}}}. Returns counts and the list of errors."""
    counts, per_item, errors = Counter(), {}, []
    rejected = extraction_failed = case_runs = clean = 0
    for run in runs:
        for row in run["rows"]:
            case_runs += 1
            want = {k: v["value"] for k, v in expected_items[row["case_id"]].items()}
            got = row.get("items")
            check = next((s for s in row["steps"] if s["step"] == "check_items"), None)
            if got is None:
                extraction_failed += 1
                got = {}
            rejected += len(check.get("problems", [])) if check else 0
            bad = 0
            for name, value in want.items():
                kind = classify(value, got.get(name))
                counts[kind] += 1
                per_item.setdefault(name, Counter())[kind] += 1
                if kind != "correct":
                    bad += 1
                    errors.append(dict(case_id=row["case_id"], item=name, kind=kind, expected=value,
                                       got=got.get(name)))
            clean += bad == 0
    return dict(case_runs=case_runs, items=sum(counts.values()), counts=dict(counts), per_item=per_item,
                errors=errors, rejected=rejected, extraction_failed=extraction_failed, clean_case_runs=clean)


def report(tag, runs, expected_items):
    a = analyse(runs, expected_items)
    c = a["counts"]
    print(f"\n=== {tag}: {len(runs)} run(s), {a['case_runs']} case-runs, {a['items']} items "
          f"(llm {runs[0]['llm']}) ===")
    print(f"correct {c.get('correct', 0)} | missing {c.get('missing', 0)} | invented {c.get('invented', 0)} "
          f"| wrong {c.get('wrong', 0)}")
    print(f"case-runs with all items right: {a['clean_case_runs']}/{a['case_runs']} | "
          f"numbers rejected by check_items: {a['rejected']} | extraction failed completely: "
          f"{a['extraction_failed']}")
    bad_items = {n: v for n, v in a["per_item"].items() if set(v) - {"correct"}}
    for name, v in sorted(bad_items.items()):
        print(f"  {name:17} " + ", ".join(f"{k} {n}" for k, n in sorted(v.items()) if k != "correct"))
    shown = Counter()
    for e in a["errors"]:   # repeated runs repeat the same error; show each distinct one once with its count
        shown[(e["case_id"], e["item"], e["kind"], e["expected"], e["got"])] += 1
    for (case_id, item, kind, want, got), n in sorted(shown.items(), key=str)[:30]:
        print(f"    {case_id} {item}: {kind}, expected {want}, got {got}  (x{n})")
    return a


def main(argv):
    from dataset import choose_set, strip_set_flags
    set_name, data_dir = choose_set(argv)   # the test set needs --final
    argv = strip_set_flags(argv)
    if not argv:
        raise SystemExit("Give at least one tag, e.g. python t1_extraction.py t5_haiku t5_qwen38")
    cases = json.loads((data_dir / "expected.json").read_text("utf-8"))
    expected_items = {c["case_id"]: c["expected_items"] for c in cases}
    for tag in argv:
        runs = load_files(tag)
        if not runs:
            print(f"\n=== {tag}: no result files found")
        elif not any(r.get("items") is not None for run in runs for r in run["rows"]):
            print(f"\n=== {tag}: files have no saved items (older format), run t3_chain.py again")
        else:
            report(tag, runs, expected_items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
