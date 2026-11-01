"""PostgreSQL storage for evaluation artifacts; no model/API calls."""
import csv
import hashlib
import json
import os
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCORES = ("relevance_0_2", "evidence_0_2", "citations_0_2", "uncertainty_0_2", "actionability_0_2")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))


def settings():
    from dotenv import load_dotenv
    load_dotenv(BASE / "../code/.env")
    load_dotenv(BASE / ".env")
    dsn = os.getenv("LLM_EVAL_PG_DSN") or os.getenv("PG_DSN")
    if not dsn:
        raise ValueError("Set PG_DSN or LLM_EVAL_PG_DSN in the environment or existing code/.env")
    return dsn


def connect():
    import psycopg
    return psycopg.connect(settings(), connect_timeout=10,
                          options="-c statement_timeout=30000 -c lock_timeout=10000")


def init_schema(conn):
    conn.execute("SELECT pg_advisory_xact_lock(7150261101)")
    conn.execute((BASE / "schema.sql").read_text(encoding="utf-8"))
    versions = conn.execute("SELECT version FROM llm_eval.schema_version").fetchall()
    if versions != [(1,)]:
        raise ValueError("Unsupported llm_eval schema version")


def run_identity(manifest):
    fingerprint, created = manifest.get("fingerprint"), manifest.get("created_at")
    if not isinstance(fingerprint, str) or not fingerprint or not isinstance(created, str) or not created:
        raise ValueError("Manifest needs fingerprint and created_at")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, canonical([fingerprint, created])))


def validate_review(raw):
    if not isinstance(raw, dict):
        raise ValueError("Review must be an object")
    result = {}
    for field in SCORES:
        value = raw.get(field)
        if value is None or value == "":
            result[field] = ""
        elif isinstance(value, bool) or str(value) not in ("0", "1", "2"):
            raise ValueError("Scores must be 0, 1, 2 or blank")
        else:
            result[field] = int(value)
    critical = raw.get("critical_error") or ""
    if critical not in ("", "yes", "no"):
        raise ValueError("critical_error must be yes, no or blank")
    notes = raw.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 20000:
        raise ValueError("Notes must be text, at most 20000 characters")
    return {**result, "critical_error": critical, "notes": notes}


def collect_runs(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("Results directory does not exist")
    collected, warnings = [], []
    def checked(path):
        if not path.resolve().is_relative_to(root):
            raise ValueError("Artifact points outside selected results directory")
        return path
    for path in sorted(root.rglob("manifest.json")):
        directory = checked(path).parent
        manifest = read_json(checked(path))
        run_id = run_identity(manifest)
        scenarios = manifest.get("scenarios")
        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError("Manifest scenarios must be a nonempty list")
        scenario_ids = {s["id"] for s in scenarios}
        if len(scenario_ids) != len(scenarios):
            raise ValueError("Duplicate scenario IDs")
        contexts = {p.stem: read_json(checked(p)) for p in sorted((directory / "contexts").glob("*.json"))}
        calls = []
        for p in sorted((directory / "calls").glob("*.json")):
            call = read_json(checked(p))
            for field in ("call_id", "scenario_id", "llm_profile", "embedding_profile", "mode", "status"):
                if not isinstance(call.get(field), str) or not call[field]:
                    raise ValueError("Call needs nonempty " + field)
            if call["scenario_id"] not in scenario_ids:
                raise ValueError("Call references unknown scenario")
            canonical(call)
            calls.append(call)
        if len({c["call_id"] for c in calls}) != len(calls):
            raise ValueError("Duplicate call_id inside run")
        if not calls:
            warnings.append(directory.name + ": no calls yet; skipped")
            continue
        reviews = []
        review_path = directory / "quality_review.csv"
        if review_path.exists():
            with checked(review_path).open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    review = validate_review(row)
                    if any(v != "" for v in review.values()):
                        if row.get("call_id") not in {c["call_id"] for c in calls}:
                            raise ValueError("Review references unknown call_id")
                        reviews.append((row["call_id"], review))
        collected.append(dict(id=run_id, name=directory.name, manifest=manifest,
                              scenarios=scenarios, contexts=contexts, calls=calls, reviews=reviews))
    if not collected:
        raise ValueError("No importable runs with manifest.json and calls/*.json found")
    return collected, warnings


def context_key(call, contexts):
    if call["mode"] != "rag":
        return None
    # Same key as rag_test.digest([scenario_id, embedding_profile]).
    key = hashlib.sha256(canonical([call["scenario_id"], call["embedding_profile"]]).encode()).hexdigest()
    return key if key in contexts else None


def should_update(existing, incoming):
    if existing == incoming:
        return False
    if existing.get("status") != "pending":
        raise ValueError("Completed artifact changed; keep corrective attempts in a separate run")
    identity = ("call_id", "scenario_id", "llm_profile", "embedding_profile", "mode")
    if any(existing.get(k) != incoming.get(k) for k in identity):
        raise ValueError("Pending call identity changed")
    return True


def import_runs(conn, runs, reviewer="sapops"):
    from psycopg.types.json import Jsonb
    counts = dict(runs=0, inserted_calls=0, updated_pending_calls=0, unchanged_calls=0, imported_reviews=0)
    for run in runs:
        rid, manifest = run["id"], run["manifest"]
        existing = conn.execute("SELECT manifest FROM llm_eval.runs WHERE id=%s", (rid,)).fetchone()
        if existing and existing[0] != manifest:
            raise ValueError("Existing run manifest differs; import aborted")
        conn.execute("""INSERT INTO llm_eval.runs(id,fingerprint,created_at,name,manifest)
                     VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                     (rid, manifest["fingerprint"], manifest["created_at"], run["name"], Jsonb(manifest)))
        for scenario in run["scenarios"]:
            conn.execute("INSERT INTO llm_eval.scenarios VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                         (rid, scenario["id"], Jsonb(scenario)))
        for key, data in run["contexts"].items():
            old = conn.execute("SELECT data FROM llm_eval.contexts WHERE run_id=%s AND context_key=%s", (rid,key)).fetchone()
            if old and old[0] != data:
                raise ValueError("Existing retrieval context changed; import aborted")
            conn.execute("INSERT INTO llm_eval.contexts VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (rid,key,Jsonb(data)))
        for call in run["calls"]:
            cid = call["call_id"]
            old = conn.execute("SELECT data FROM llm_eval.calls WHERE run_id=%s AND call_id=%s", (rid,cid)).fetchone()
            update = should_update(old[0], call) if old else False
            key = context_key(call, run["contexts"])
            if not old:
                conn.execute("""INSERT INTO llm_eval.calls
                    (run_id,call_id,scenario_id,context_key,llm_profile,embedding_profile,mode,status,data)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (rid,cid,call["scenario_id"],key,call["llm_profile"],call["embedding_profile"],call["mode"],call["status"],Jsonb(call)))
                counts["inserted_calls"] += 1
            elif update:
                conn.execute("UPDATE llm_eval.calls SET status=%s,data=%s,context_key=%s WHERE run_id=%s AND call_id=%s",
                             (call["status"],Jsonb(call),key,rid,cid))
                counts["updated_pending_calls"] += 1
            else:
                counts["unchanged_calls"] += 1
        for cid, review in run["reviews"]:
            cur = conn.execute("""INSERT INTO llm_eval.reviews(run_id,call_id,reviewer,data)
                VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""", (rid,cid,reviewer,Jsonb(review)))
            counts["imported_reviews"] += cur.rowcount
        counts["runs"] += 1
    return counts


def dataset(conn, reviewer="sapops"):
    files = []
    pilot_rows=[]
    pilot_names=os.getenv('JUDGE_PILOT_RUNS','rag-dev-2026-10-31-v2,no-history-dev-2026-11-01').split(',')
    for rid, name, manifest in conn.execute("SELECT id,name,manifest FROM llm_eval.runs ORDER BY imported_at,id"):
        prefix = "database/" + str(rid)
        manifest = {**manifest, "_database_id": str(rid), "_database_name": name}
        files.append(dict(path=prefix+"/manifest.json", text=canonical(manifest)))
        for cid, call in conn.execute("SELECT call_id,data FROM llm_eval.calls WHERE run_id=%s ORDER BY call_id", (rid,)):
            if name in pilot_names:
                pilot_rows.append(dict(run_id=str(rid),run_name=name,call_id=cid,call=call))
            # IDs in virtual paths are encoded to avoid interpreting embedded separators.
            files.append(dict(path=prefix+"/calls/"+hashlib.sha256(cid.encode()).hexdigest()+".json", text=canonical(call)))
        for key, context in conn.execute("SELECT context_key,data FROM llm_eval.contexts WHERE run_id=%s", (rid,)):
            files.append(dict(path=prefix+"/contexts/"+hashlib.sha256(key.encode()).hexdigest()+".json", text=canonical(context)))
        reviews = [{"call_id": cid, **data} for cid, data in conn.execute(
            "SELECT call_id,data FROM llm_eval.reviews WHERE run_id=%s AND reviewer=%s", (rid,reviewer))]
        if reviews:
            import io
            buf = io.StringIO(newline="")
            writer = csv.DictWriter(buf, fieldnames=["call_id",*SCORES,"critical_error","notes"])
            writer.writeheader()
            writer.writerows(reviews)
            files.append(dict(path=prefix+"/quality_review.csv", text=buf.getvalue()))
    judges=[]
    # Additive rollout: an existing dashboard works before judge tables are created.
    if conn.execute("SELECT to_regclass('llm_eval.judge_jobs')").fetchone()[0] is not None:
        for rid,cid,jid,state,config,usage,elapsed,cost,error,created,result,inputs in conn.execute('''
            SELECT j.run_id,j.call_id,j.id,j.status,j.config,j.usage,j.elapsed_s,
                   j.estimated_cost_usd,j.error,j.created_at,e.data,j.input_data
            FROM llm_eval.judge_jobs j LEFT JOIN llm_eval.judge_evaluations e ON e.job_id=j.id
            ORDER BY j.created_at DESC,j.id'''):
            judges.append(dict(run_id=str(rid),call_id=cid,job_id=str(jid),status=state,
                config={k:config.get(k) for k in ('provider','model','model_digest','rubrics_version','references_version')},
                usage=usage,elapsed_s=elapsed,estimated_cost_usd=cost,error=error,
                created_at=created.isoformat(),result=result,
                references=config.get('approved_references',[])))
    from judge_core import sample_rows, digest
    selected=sample_rows(sorted(pilot_rows,key=lambda r:(r['run_name'],r['call_id'])),20,42)
    selection=[dict(run_id=r['run_id'],call_id=r['call_id']) for r in selected]
    return {"files": files, "reviewer": reviewer, "judge_evaluations":judges,
            "judge_pilot":{"size":20,"seed":42,"runs":pilot_names,"selection":selection,"selection_hash":digest(selection)}}


def save_review(conn, raw, reviewer="sapops"):
    from psycopg.types.json import Jsonb
    rid = str(uuid.UUID(raw["run_id"]))
    cid = raw["call_id"]
    if not isinstance(cid,str) or not cid or len(cid)>500:
        raise ValueError("Invalid call_id")
    data = validate_review(raw)
    if not conn.execute("SELECT 1 FROM llm_eval.calls WHERE run_id=%s AND call_id=%s", (rid,cid)).fetchone():
        raise LookupError("Call not found")
    conn.execute("""INSERT INTO llm_eval.reviews(run_id,call_id,reviewer,data)
        VALUES (%s,%s,%s,%s) ON CONFLICT (run_id,call_id,reviewer)
        DO UPDATE SET data=EXCLUDED.data,updated_at=now()""", (rid,cid,reviewer,Jsonb(data)))
    return {"call_id": cid, **data}
