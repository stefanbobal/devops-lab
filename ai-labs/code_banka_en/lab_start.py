"""Read-only lab readiness checks. --cloud adds paid check_cloud.py probes."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def check_venv():
    expected = (BASE / ".venv").resolve()
    if sys.prefix == sys.base_prefix or Path(sys.prefix).resolve() != expected:
        raise RuntimeError("Activate " + str(BASE / ".venv/bin/activate"))
    return sys.executable


def check_docker():
    result = subprocess.run(["docker", "ps", "--format", "{{json .}}"],
                            capture_output=True, text=True, timeout=15, check=True)
    containers = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    expected = os.getenv("LAB_DB_CONTAINER", "pgvector-banka").strip()
    if expected:
        matches = [c for c in containers if c.get("Names") == expected]
        if not matches:
            raise RuntimeError("Configured LAB_DB_CONTAINER is not running")
    else:
        matches = [c for c in containers if any(word in
                   (c.get("Image", "") + " " + c.get("Names", "")).lower()
                   for word in ("postgres", "pgvector"))]
    if not matches:
        raise RuntimeError("No running PostgreSQL/pgvector container detected; set LAB_DB_CONTAINER for a custom name")
    for c in matches:
        if "unhealthy" in c.get("Status", "").lower() or "health: starting" in c.get("Status", "").lower():
            raise RuntimeError("Database container health is not ready")
    return ", ".join(c["Names"] + ": " + c.get("Status", "running") for c in matches)


def check_database():
    import psycopg
    from config import PG_DSN
    with psycopg.connect(PG_DSN, connect_timeout=10) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET statement_timeout = '10s'")
        row = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
        if not row:
            raise RuntimeError("Connected database does not have the vector extension installed")
        conn.execute("SELECT '[1,2,3]'::vector <=> '[1,2,3]'::vector").fetchone()
    return "Configured PG_DSN reachable; pgvector " + str(row[0]) + "; vector operation OK"


def check_ollama():
    import ollama
    response = ollama.Client(timeout=10).list()
    data = response.model_dump(mode="json")
    models = data.get("models", [])
    if not models:
        raise RuntimeError("Ollama responds but has no installed models")
    return f"Configured Ollama endpoint responds; {len(models)} models listed"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud", action="store_true", help="Also run eight paid cloud probes")
    args = parser.parse_args(argv)
    # Check interpreter before importing project dependencies.
    try:
        print("OK venv:", check_venv(), flush=True)
        from dotenv import load_dotenv
        load_dotenv(BASE / ".env")
    except Exception as exc:
        print("FAIL environment:", type(exc).__name__, "- activate the lab venv and install its dependencies")
        return 1
    failed = False
    for label, check in (("Docker", check_docker), ("PostgreSQL/pgvector", check_database), ("Ollama", check_ollama)):
        try:
            print("OK", label + ":", check(), flush=True)
        except (Exception, SystemExit) as exc:
            # Do not print raw SDK/DSN errors that could contain credentials.
            print("FAIL", label + ":", type(exc).__name__, "- see lab_start_README.md", flush=True)
            failed = True
    if failed:
        print("Lab not ready. No cloud probes started.")
        return 1
    if args.cloud:
        print("Starting paid cloud probes...", flush=True)
        try:
            result = subprocess.run([sys.executable, str(BASE / "check_cloud.py")], cwd=BASE, timeout=1500)
        except (OSError, subprocess.TimeoutExpired):
            print("FAIL cloud probe process")
            return 1
        if result.returncode:
            return 1
    print("Lab ready.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
