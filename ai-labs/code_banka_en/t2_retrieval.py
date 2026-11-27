"""T2: does retrieval put the cited contract article into top-k? Run per embedding profile.

Usage: python t2_retrieval.py [profile ...] [--write-thresholds]
       python t2_retrieval.py --tag split_defs     (results/t2_split_defs.json instead of t2.json)
       python t2_retrieval.py --set test --final [profile ...]   (held-out set, run once at the end)
For every case in data/expected.json the agent needs up to four things; each is one fixed query:
EBITDA definition, net debt definition, the limit valid on the test date, and (only if the case has
one) the waiver. The gold chunk is the document and article that expected_spec cites.
Analyst notes are excluded from search: they are never evidence of a limit or waiver.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from sources import cz_date, quarter_end

BASE = Path(__file__).resolve().parent
KS = (1, 3)
RECALL_TARGET = 0.95   # the chosen threshold must keep at least this share of the correct chunks
GRID = [round(0.30 + 0.05 * i, 2) for i in range(12)]
DOC_TYPES = ("contract", "amendment", "waiver")
DATA_DIRS = {"dev": "data", "test": "data_test"}
# Strict check for definitions: the chunk must contain the defining sentence, not only sit in the right article.
MARKERS = {"ebitda": ("„EBITDA“",), "debt": ("„Čistý dluh“", "„Dluh“")}


def queries(case):
    day = cz_date(quarter_end(case["period"]))
    spec = case["expected_spec"]
    out = [("ebitda", "Jak je ve smlouvě definována EBITDA?", [spec["ebitda"]["citation"]]),
           ("debt", "Jak je ve smlouvě definován Čistý dluh?", [spec["debt"]["citation"]]),
           ("limit", f"Jaká je nejvyšší přípustná hodnota finančních ukazatelů pro Den testování {day}?",
            [c["citation"] for c in spec["covenants"]])]
    waiver_query = f"Prominutí porušení finančního ukazatele pro Den testování {day}"
    if spec["waivers"]:
        out.append(("waiver", waiver_query, [w["citation"] for w in spec["waivers"]]))
    else:   # negative query: no waiver exists, so nothing found should count as relevant
        out.append(("no_waiver", waiver_query, []))
    return out


def run_profile(data_set):
    import psycopg
    from pgvector.psycopg import register_vector

    from config import PG_DSN, PROFILE
    from providers import embed
    from search import search_vector

    cases = json.loads((BASE / DATA_DIRS[data_set] / "expected.json").read_text("utf-8"))
    conn = psycopg.connect(PG_DSN)
    register_vector(conn)
    cache, rows = {}, []
    for case in cases:
        for kind, text, cites in queries(case):
            if text not in cache:
                cache[text] = embed(text, "query")
            gold = {(c["document"], c["article"]) for c in cites}
            hits = search_vector(cache[text], case["company_id"], DOC_TYPES, 3, conn)
            keys = [(h["document"], h["article"]) for h in hits]
            rank = next((i + 1 for i, k in enumerate(keys) if k in gold), None)
            marks = MARKERS.get(kind)
            strict = next((i + 1 for i, (h, k) in enumerate(zip(hits, keys))
                           if k in gold and (not marks or any(m in h["text"] for m in marks))), None)
            rows.append(dict(case_id=case["case_id"], case_type=case["case_type"], kind=kind, rank=rank, strict_rank=strict,
                             gold=sorted(map(str, gold)), top=[f"{d} čl. {a}" for d, a in keys],
                             sims=[round(h["similarity"], 3) for h in hits],
                             gold_sim=next((round(h["similarity"], 3) for h, k in zip(hits, keys) if k in gold), None),
                             is_gold=[k in gold for k in keys]))
    return dict(profile=PROFILE, rows=rows)


def summarize(result):
    rows, lines = result["rows"], []
    for kind in ("ebitda", "debt", "limit", "waiver"):
        sub = [r for r in rows if r["kind"] == kind]
        if sub:
            cells = "  ".join(f"hit@{k} {sum(1 for r in sub if r['rank'] and r['rank'] <= k)}/{len(sub)}" for k in KS)
            if kind in MARKERS:
                cells += "  | strict " + "  ".join(
                    f"hit@{k} {sum(1 for r in sub if r['strict_rank'] and r['strict_rank'] <= k)}/{len(sub)}" for k in KS)
            lines.append(f"  {kind:7} {cells}")
    neg = [r["sims"][0] for r in rows if r["kind"] == "no_waiver"]
    if neg:
        lines.append(f"  no_waiver best similarity (nothing correct exists): "
                     f"min {min(neg):.2f}  mean {sum(neg) / len(neg):.2f}  max {max(neg):.2f}  (n={len(neg)})")
    return lines


def thresholds_sweep(rows):
    """Per threshold: recall of the correct chunk, precision of what stays above it, and the
    false-accept rate: share of negative queries whose best chunk is still above the threshold."""
    positive = [r for r in rows if r["kind"] != "no_waiver"]
    negative = [r for r in rows if r["kind"] == "no_waiver"]
    sweep = []
    for t in GRID:
        kept = sum(1 for r in positive for s in r["sims"] if s >= t)
        found = sum(1 for r in positive if r["gold_sim"] is not None and r["gold_sim"] >= t)
        good = sum(1 for r in positive for s, g in zip(r["sims"], r["is_gold"]) if g and s >= t)
        accepted = sum(1 for r in negative if r["sims"][0] >= t)
        sweep.append(dict(threshold=t, recall=found / len(positive) if positive else 0.0,
                          precision=good / kept if kept else 0.0,
                          false_accept=accepted / len(negative) if negative else None))
    return sweep


def choose_threshold(sweep):
    """Highest grid threshold that still reaches the recall target (false accepts only fall as it rises)."""
    ok = [s for s in sweep if s["recall"] >= RECALL_TARGET]
    return max(ok, key=lambda s: s["threshold"]) if ok else None


def main(argv):
    from config import MODELS
    write = "--write-thresholds" in argv
    data_set = "test" if "--set" in argv and argv[argv.index("--set") + 1] == "test" else "dev"
    if data_set == "test" and "--final" not in argv:
        raise SystemExit("The test set is held out: tuning on it is not allowed. Add --final to evaluate once.")
    if data_set == "test" and write:
        raise SystemExit("Thresholds are calibrated on the dev set only.")
    tag = argv[argv.index("--tag") + 1] if "--tag" in argv else ""
    skip = ({"test", "dev"} if "--set" in argv else set()) | ({tag} if tag else set())
    profiles = [a for a in argv if not a.startswith("--") and a not in skip] or list(MODELS)
    if os.getenv("T2_WORKER"):
        result = run_profile(os.environ["T2_SET"])
        result["sweep"] = thresholds_sweep(result["rows"])
        print(json.dumps(result, ensure_ascii=False))
        return 0
    results, chosen = {}, []
    for profile in profiles:   # one process per profile: config reads EMBED_PROFILE at import
        proc = subprocess.run([sys.executable, __file__, profile], capture_output=True, text=True,
                              env={**os.environ, "EMBED_PROFILE": profile, "T2_WORKER": "1",
                                  "T2_SET": data_set})
        if proc.returncode:
            print(f"{profile}: FAILED\n{proc.stderr[-500:]}")
            continue
        results[profile] = json.loads(proc.stdout.splitlines()[-1])
        res = results[profile]
        print(profile)
        print("\n".join(summarize(res)))
        print("  threshold  recall  precision  false-accept")
        for row in res["sweep"]:
            if 0.40 <= row["threshold"] <= 0.80:
                fa = "-" if row["false_accept"] is None else f"{row['false_accept']:.2f}"
                print(f"  {row['threshold']:<9}  {row['recall']:.2f}    {row['precision']:.2f}       {fa}")
        best = choose_threshold(res["sweep"])
        if best is None:
            print(f"  no threshold reaches recall {RECALL_TARGET}")
            continue
        fa = "-" if best["false_accept"] is None else f"{best['false_accept']:.2f}"
        print(f"  proposed threshold (highest with recall >= {RECALL_TARGET}): {best['threshold']} "
              f"(precision {best['precision']:.2f}, false-accept {fa})")
        chosen.append(dict(model=profile, threshold=best["threshold"]))
        for r in res["rows"]:   # definitions repeat identically in all 3 quarters; show only limit/waiver misses
            if r["kind"] in ("limit", "waiver") and (not r["rank"] or r["rank"] > 1):
                print(f"    MISS@1 {r['case_id']} {r['kind']}: rank {r['rank']}, top {r['top'][0]} {r['sims'][0]}, gold {r['gold']}")
    name = "t2" if data_set == "dev" else "t2_test"
    out = BASE / "results" / (f"{name}_{tag}.json" if tag else f"{name}.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    if write and len(chosen) == len(profiles):
        (BASE / "thresholds.json").write_text(json.dumps(chosen, indent=2) + "\n", encoding="utf-8")
        print("wrote thresholds.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
