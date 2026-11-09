"""Add the chunks of the T4 attack sets (A and F) to the vector table in Azure PostgreSQL.

    python load_attacks_azure.py --dry-run          count what would be added, call nothing
    python load_attacks_azure.py [--sets a,f]       embed with the Azure model and insert
    python load_attacks_azure.py --remove           delete the attack rows again (after T4)

Only ADDS rows: the existing dev and test rows are never touched, so the table the deployed agent uses for T3
stays as it was (code_banka/load_documents.py would drop and rebuild the whole table). Attack companies have
ids like C01_S1; the mandatory company filter in search.py keeps them apart from C01. A company that is already
in the table is skipped, so an interrupted run can simply be started again.
Chunking and the embedded text come from load_documents.py, the same code that built the existing rows.
Needs: PGPASSWORD in the shell (the database admin password), your IP allowed on the server firewall, and the
server in .env next to this script (see .env.example). The Azure model endpoint and key are read from
code_banka/.env.
"""
import json
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
LAB = BASE.parent.parent / "code_banka"
ATTACK_ROW = r"^C\d{2}_[A-Z]\d$"   # company ids of attack sets; dev and test companies are C01 ... C18


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def attack_chunks(sets):
    """{company_id: [chunks]} for the chosen sets, chunked exactly like the rows already in the table."""
    from foundry_deploy import ATTACK_SETS
    from load_documents import chunk_document
    by_company = {}
    for key in sets:
        root = ATTACK_SETS[key]
        if not (root / "expected.json").is_file():
            raise SystemExit(f"{root} is missing; build it in code_banka with generate_attacks.py")
        names = {c["company_id"]: c["company"] for c in json.loads((root / "expected.json").read_text("utf-8"))}
        for folder in sorted((root / "companies").iterdir()):
            chunks = []
            for path in sorted(folder.glob("*.md")):
                chunks += chunk_document(folder.name, names[folder.name], path.name, path.read_text("utf-8"))
            by_company[folder.name] = chunks
    return by_company


def main(argv):
    from dotenv import load_dotenv
    load_dotenv(LAB / ".env")                 # Azure model endpoint, key and deployment names
    os.environ["EMBED_PROFILE"] = "azure"     # must be set before config is imported
    from foundry_deploy import PG_HOST, pg_dsn
    os.environ["PG_DSN"] = pg_dsn()           # server and login come from the local .env

    sets = ["a", "f"]
    if "--sets" in argv:
        sets = argv[argv.index("--sets") + 1].split(",")
    dry, remove = "--dry-run" in argv, "--remove" in argv

    from config import EMBED_DIM, EMBED_MODEL, PG_DSN, TABLE
    by_company = attack_chunks(sets)
    total = sum(len(c) for c in by_company.values())
    log(f"sets {sets}: {len(by_company)} companies, {total} chunks | model {EMBED_MODEL} ({EMBED_DIM} dims) | "
        f"table {TABLE} on {PG_HOST.split('.')[0]}")
    if dry and not os.environ.get("PGPASSWORD"):
        log("dry run without PGPASSWORD: the table was not read, nothing was called")
        return 0
    if not os.environ.get("PGPASSWORD"):
        raise SystemExit("Set PGPASSWORD first:  read -s PGPASSWORD; export PGPASSWORD")

    import psycopg
    from pgvector.psycopg import register_vector
    conn = psycopg.connect(PG_DSN, autocommit=True, connect_timeout=15)
    register_vector(conn)

    def count(where="", params=None):
        return conn.execute(f"SELECT count(*), count(DISTINCT company_id) FROM {TABLE} {where}", params).fetchone()

    log(f"table now: {count()[0]} rows, {count()[1]} companies; of them attack rows: "
        f"{count('WHERE company_id ~ %s', (ATTACK_ROW,))[0]}")

    if remove:
        if dry:
            log("dry run: nothing deleted")
            return 0
        deleted = conn.execute(f"DELETE FROM {TABLE} WHERE company_id ~ %s", (ATTACK_ROW,)).rowcount
        log(f"deleted {deleted} attack rows; table now: {count()[0]} rows, {count()[1]} companies")
        return 0

    present = {r[0] for r in conn.execute(f"SELECT DISTINCT company_id FROM {TABLE}").fetchall()}
    todo = {c: chunks for c, chunks in by_company.items() if c not in present}
    todo_chunks = sum(len(c) for c in todo.values())
    log(f"already in the table: {len(by_company) - len(todo)} companies; to add: {len(todo)} companies, {todo_chunks} chunks")
    if dry or not todo:
        log("dry run: nothing embedded, nothing inserted" if dry else "nothing to do")
        return 0

    from load_documents import embedding_text
    from providers import embed
    started, done = time.time(), 0
    for company_id, chunks in todo.items():
        rows = []
        for chunk in chunks:
            text = embedding_text(chunk)
            rows.append((chunk["company_id"], chunk["company"], chunk["document"], chunk["doc_type"], chunk["article"],
                         chunk["article_title"], chunk["clause"], chunk["page"], chunk["text"], text, EMBED_MODEL,
                         embed(text, "document")))
            done += 1
            if done % 25 == 0 or done == todo_chunks:
                log(f"  chunk {done}/{todo_chunks} ({time.time() - started:.0f}s) {company_id}")
        with conn.transaction():   # a company is added completely or not at all, so a restart never leaves half of one
            for row in rows:
                conn.execute(
                    f"""INSERT INTO {TABLE} (company_id, company, document, doc_type, article, article_title,
                                             clause, page, text, embedding_text, embedding_model, embedding)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", row)
    log(f"done in {time.time() - started:.0f}s; table now: {count()[0]} rows, {count()[1]} companies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
