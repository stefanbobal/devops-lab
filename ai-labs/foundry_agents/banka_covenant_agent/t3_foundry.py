"""T3 against the deployed Foundry agent: every dev case, compared with expected_status.

Usage: python t3_foundry.py --tag name [--limit N] [--cases C01-2026Q1,...] [--agent covenant-agent-code]
                            [--compare ../../code_banka/results/t3_chain_h_azure_dev.json]
Same key numbers as code_banka/t3_chain.py: missed breaches (expected breach, got no_breach), false alarms,
human_review share, and which step stopped each case. The chain runs inside Foundry; this script only sends
"<company_id> <period>" and reads the JSON the agent returns. A tag is required and an existing result file is
never overwritten. A call that fails (HTTP error, answer that is not the agent's JSON) is recorded as got "error":
it is neither a correct answer nor a human_review.
--compare prints the cases whose status differs from an earlier t3_chain result file (the home-lab run).
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

import foundry_deploy

BASE = Path(__file__).resolve().parent


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def plain(value):
    """SDK model objects -> plain dicts and lists that json can write."""
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def summarize(rows):
    """rows: dicts with expected, got, stage (step that ended in human_review, or None), values_ok."""
    n = len(rows)
    exact = sum(1 for r in rows if r["got"] == r["expected"])
    return dict(
        cases=n, exact=exact,
        missed_breach=[r["case_id"] for r in rows if r["expected"] == "breach" and r["got"] == "no_breach"],
        false_alarm=[r["case_id"] for r in rows if r["expected"] == "no_breach" and r["got"] == "breach"],
        errors=[r["case_id"] for r in rows if r["got"] == "error"],
        review_expected=sum(1 for r in rows if r["expected"] == "human_review"),
        review_got=sum(1 for r in rows if r["got"] == "human_review"),
        stopped_at=dict(Counter(r["stage"] for r in rows if r["stage"])),
        matrix={f"{e} -> {g}": c for (e, g), c in sorted(Counter((r["expected"], r["got"]) for r in rows).items())},
    )


def first_stop(out):
    """Name of the first step that did not end well (the cause of a human_review), else None."""
    for s in out.get("steps") or []:
        if s["status"] in ("failed", "problems", "refused"):
            return s["step"]
    return None


def call_agent(openai_client, company_id, period):
    """One request = one new session in Foundry. Returns (agent output dict, None) or (None, error text)."""
    try:
        response = openai_client.responses.create(input=f"{company_id} {period}")
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:200]}"
    try:
        out = json.loads(response.output_text)
    except ValueError:
        return None, f"answer is not JSON: {response.output_text[:120]!r}"
    if not isinstance(out, dict) or "status" not in out:
        return None, "answer has no status"
    return out, None


def main(argv):
    opts = {a: argv[i + 1] for i, a in enumerate(argv)
            if a in ("--limit", "--cases", "--tag", "--agent", "--compare") and i + 1 < len(argv)}
    if "--tag" not in opts:
        raise SystemExit("Give a tag, e.g. python t3_foundry.py --tag foundry_run1 (existing results are never overwritten)")
    out_file = BASE / "results" / f"t3_foundry_{opts['--tag']}.json"
    if out_file.exists():
        raise SystemExit(f"{out_file.name} already exists, choose another tag")
    agent_name = opts.get("--agent", foundry_deploy.CODE_AGENT_NAME)
    baseline = None
    if "--compare" in opts:
        baseline = {r["case_id"]: r["got"] for r in json.loads(Path(opts["--compare"]).read_text("utf-8"))["rows"]}

    cases = json.loads((BASE / "data" / "expected.json").read_text("utf-8"))
    if "--cases" in opts:
        cases = [c for c in cases if c["case_id"] in opts["--cases"].split(",")]
    if "--limit" in opts:
        cases = cases[:int(opts["--limit"])]

    project = foundry_deploy.client()
    versions = [dict(v) for v in project.agents.list_versions(agent_name=agent_name)]
    active = [v["version"] for v in versions if v.get("status") == "active"]
    if not active:
        raise SystemExit(f"{agent_name} has no active version; deploy it first")
    version = max(active, key=int)
    definition = plain(next(v for v in versions if v["version"] == version).get("definition")) or {}
    env = definition.get("environment_variables") or {}
    # built and serialized before the run, so a problem with the record stops the script now, not after all cases
    meta = dict(time=time.strftime("%Y-%m-%d %H:%M:%S"), orchestration="foundry_hosted_agent", agent=agent_name,
                agent_version=version, llm=env.get("AZURE_OPENAI_LLM_DEPLOYMENT"),
                embedding=env.get("AZURE_OPENAI_EMBED_DEPLOYMENT"), mode="rag", dataset="dev",
                code_configuration=definition.get("code_configuration"),
                image=(definition.get("container_configuration") or {}).get("image"))
    json.dumps(meta)
    out_file.parent.mkdir(exist_ok=True)
    log(f"T3 Foundry | agent {agent_name} version {version} | LLM {env.get('AZURE_OPENAI_LLM_DEPLOYMENT')} | "
        f"embedding {env.get('AZURE_OPENAI_EMBED_DEPLOYMENT')} | {len(cases)} cases | tag {opts['--tag']}")
    openai_client = project.get_openai_client(agent_name=agent_name)

    rows, started = [], time.time()
    for i, case in enumerate(cases, 1):
        t = time.time()
        out, error = call_agent(openai_client, case["company_id"], case["period"])
        if error:
            row = dict(got="error", stage=None, reasons=[error], values_ok=False, spec=None, items=None, steps=[])
        else:
            want = case["expected_result"].get("values")
            result = out.get("result")
            row = dict(got=out["status"], stage=first_stop(out), reasons=out.get("reasons"),
                       values_ok=result is not None and want is not None and result.get("values") == want,
                       spec=out.get("spec"), items=out.get("items"), steps=out.get("steps"))
        row = dict(case_id=case["case_id"], case_type=case["case_type"], expected=case["expected_status"],
                   seconds=round(time.time() - t, 1), **row)
        rows.append(row)
        mark = "ok " if row["got"] == row["expected"] else "DIFF"
        note = f" ({row['stage']}: {str(row['reasons'])[:110]})" if row["got"] != row["expected"] else ""
        log(f"  [{mark}] {i}/{len(cases)} {case['case_id']} expected {row['expected']}, got {row['got']} "
            f"in {row['seconds']}s{note}")

    summary = summarize(rows)
    out_file.write_text(json.dumps(dict(meta=meta, summary=summary, rows=rows), ensure_ascii=False, indent=1,
                                   default=str),   # an unexpected type must not lose a finished run
                        encoding="utf-8")
    log(f"done in {time.time() - started:.0f}s | exact {summary['exact']}/{summary['cases']} | "
        f"human_review got {summary['review_got']} (expected {summary['review_expected']})")
    log(f"missed breaches: {summary['missed_breach'] or 'none'} | false alarms: {summary['false_alarm'] or 'none'} | "
        f"errors: {summary['errors'] or 'none'}")
    log(f"matrix: {summary['matrix']}")
    if summary["stopped_at"]:
        log(f"human_review caused by step: {summary['stopped_at']}")
    if baseline is not None:
        diffs = [(r["case_id"], baseline.get(r["case_id"]), r["got"]) for r in rows
                 if r["case_id"] in baseline and baseline[r["case_id"]] != r["got"]]
        log(f"compared with {Path(opts['--compare']).name}: {len(diffs)} case(s) differ")
        for case_id, before, now in diffs:
            log(f"  {case_id}: home lab {before}, Foundry {now}")
    log(f"wrote results/{out_file.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
