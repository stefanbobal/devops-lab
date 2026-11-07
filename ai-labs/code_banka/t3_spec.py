"""T3a: can an LLM turn retrieved contract excerpts into a correct, verifiable specification?

Usage: python t3_spec.py [llm_profile ...] [--limit N] [--cases C01-2026Q1,...] [--tag name]
Embedding profile for retrieval: EMBED_PROFILE (default bge), so that only the LLM changes between runs.
Pipeline per dev case: search (find_relevant / find_waiver) -> LLM (build_spec_prompts) -> JSON ->
covenants.validate_spec -> sources.verify_sources -> compare with expected_spec.
Dev set only (data/). The held-out data_test/ is not touched here.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from agent import parse_json

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"


def log(message):
    """Progress goes to stderr (stdout carries the JSON result); always flushed so nothing looks stuck."""
    print(f"[{time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def normalize(spec, period=None):
    """The parts of a specification that decide the result; citations are checked by verify_sources.
    Covenant ids are free labels chosen by the model, so covenants are compared by ratio and limit and a
    waiver is identified by the ratio of its covenant. With a period only waivers for that test period count:
    the expected spec also lists waivers granted for other periods, and they must not change this status."""
    ratio_of = {c["id"]: c["ratio"] for c in spec["covenants"]}
    return {"ebitda": (sorted(spec["ebitda"].get("add", [])), sorted(spec["ebitda"].get("subtract", []))),
            "debt": (sorted(spec["debt"].get("include", [])), spec["debt"].get("deduct_cash")),
            "covenants": sorted((c["ratio"], float(c["limit"])) for c in spec["covenants"]),
            "waivers": sorted((ratio_of.get(w["covenant"]), w["period"]) for w in spec.get("waivers") or []
                              if period is None or w["period"] == period)}


def differences(got, want, period=None):
    a, b = normalize(got, period), normalize(want, period)
    return [k for k in a if a[k] != b[k]]


def load_documents(company_id):
    folder = DATA / "companies" / company_id
    return {p.name: p.read_text("utf-8") for p in folder.glob("*.md") if not p.name.startswith("vykaz")}


_embeddings = {}   # query text -> vector: definition questions are identical for every company


def cached_embed(text, kind="query"):
    if text not in _embeddings:
        from providers import embed
        log(f"    embedding query: {text[:70]}")
        started = time.time()
        _embeddings[text] = embed(text, kind)
        log(f"    embedded in {time.time() - started:.1f}s")
    return _embeddings[text]


def gather_chunks(case):
    import search
    search.embed = cached_embed   # find_similar embeds through this name
    from search import find_relevant, find_waiver
    from t2_retrieval import queries
    chunks, seen = [], set()
    for kind, text, _ in queries(case):
        found = find_waiver(text, case["company_id"]) if kind in ("waiver", "no_waiver") \
            else find_relevant(text, case["company_id"])
        for c in found:
            key = (c["document"], c["article"], c["clause"])
            if key not in seen:
                seen.add(key)
                chunks.append(c)
    return chunks


def run_case(case, chunks):
    from covenants import SpecError, validate_spec
    from providers import chat
    from rag_prompt import build_spec_prompts
    from sources import quarter_end, verify_sources

    out = dict(case_id=case["case_id"], stage=None, problems=[], differences=[], seconds=None)
    out["chunks"] = [f"{c['document']} {c['article']}{'/' + c['clause'] if c['clause'] else ''}" for c in chunks]
    system, user = build_spec_prompts(case["period"], quarter_end(case["period"]).isoformat(), chunks)
    log(f"  {case['case_id']}: {len(chunks)} chunks, calling {os.getenv('LLM_PROFILE')} ...")
    start = time.time()
    try:
        answer = chat(system, user)
    except Exception as exc:   # API / network error is a result, not a crash
        out.update(stage="llm_error", problems=[str(exc)[:200]])
        return out
    out["seconds"] = round(time.time() - start, 1)
    try:
        spec = parse_json(answer)
    except ValueError as exc:
        out.update(stage="bad_json", problems=[str(exc)], answer=answer[:400])
        return out
    if "error" in spec:
        out.update(stage="refused", problems=[str(spec["error"])[:200]])
        return out
    try:
        validate_spec(spec)
    except (SpecError, AttributeError, TypeError, KeyError) as exc:
        out.update(stage="invalid_spec", problems=[str(exc)[:300]], spec=spec)
        return out
    problems = verify_sources(spec, load_documents(case["company_id"]), case["period"])
    diff = differences(spec, case["expected_spec"], case["period"])
    out.update(stage="verified" if not problems else "unverified", problems=problems, differences=diff, spec=spec)
    if not problems and not diff:
        out["stage"] = "correct"
    return out


def worker():
    cases = json.loads((DATA / "expected.json").read_text("utf-8"))
    wanted = os.getenv("T3_CASES")
    if wanted:
        cases = [c for c in cases if c["case_id"] in wanted.split(",")]
    if os.getenv("T3_LIMIT"):
        cases = cases[:int(os.environ["T3_LIMIT"])]
    # Phase 1 loads only the embedding model, phase 2 only the LLM: with local Ollama on one GPU, switching
    # between both for every case is slow and can crash the server.
    from config import EMBED_MODEL, LLM_MODEL
    log(f"LLM {os.getenv('LLM_PROFILE')} ({LLM_MODEL}) | embedding {os.getenv('EMBED_PROFILE')} ({EMBED_MODEL}) | {len(cases)} cases")
    log("phase 1/2: search (embedding model only)")
    retrieved = {}
    for i, case in enumerate(cases, 1):
        log(f"  search {i}/{len(cases)} {case['case_id']}")
        try:
            retrieved[case["case_id"]] = gather_chunks(case)
        except Exception as exc:   # a failing search is a result of this case, not the end of the run
            retrieved[case["case_id"]] = exc
    rows = []
    log("phase 2/2: LLM (the first answer can take a minute while a local model loads)")
    for case in cases:
        chunks = retrieved[case["case_id"]]
        if isinstance(chunks, Exception):
            row = dict(case_id=case["case_id"], stage="retrieval_error", problems=[str(chunks)[:200]],
                       differences=[], seconds=None)
        else:
            row = run_case(case, chunks)
        log(f"  => {row['case_id']:<12} {row['stage']:<12} {row['seconds']}s {row['differences'] or ''} {row['problems'][:1] or ''}")
        rows.append(row)
    print(json.dumps(rows, ensure_ascii=False))


def main(argv):
    if os.getenv("T3_WORKER"):
        return worker()
    opts = {"--limit": "T3_LIMIT", "--cases": "T3_CASES", "--tag": None}
    env_extra, tag, skip = {}, "", set()
    for flag, var in opts.items():
        if flag in argv:
            value = argv[argv.index(flag) + 1]
            skip |= {flag, value}
            if var:
                env_extra[var] = value
            else:
                tag = value
    profiles = [a for a in argv if a not in skip]
    if not profiles:
        raise SystemExit("Give at least one LLM profile, e.g. python t3_spec.py gemma azure haiku")
    results = {}
    for profile in profiles:   # config reads LLM_PROFILE at import, so one process per profile
        log(f"starting LLM profile {profile} (embedding {os.getenv('EMBED_PROFILE', 'bge')}, tag {tag or '-'})")
        proc = subprocess.run([sys.executable, __file__], text=True, stdout=subprocess.PIPE,
                              env={**os.environ, **env_extra, "LLM_PROFILE": profile, "T3_WORKER": "1",
                                   "EMBED_PROFILE": os.getenv("EMBED_PROFILE", "bge")})
        if proc.returncode:
            log(f"{profile}: FAILED (see the error above)")
            continue
        rows = json.loads(proc.stdout.splitlines()[-1])
        results[profile] = rows
        counts = {}
        for r in rows:
            counts[r["stage"]] = counts.get(r["stage"], 0) + 1
        secs = sorted(r["seconds"] for r in rows if r["seconds"])
        median = f" | median {secs[len(secs) // 2]}s per case" if secs else ""
        log(f"{profile}: {len(rows)} cases | " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + median)
    out = BASE / "results" / (f"t3_spec_{tag}.json" if tag else "t3_spec.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"wrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
