"""Lab 03: create the incident_memory table and load fictional historical incidents from incidents.json."""
import json
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from config import EMBED_DIM, EMBED_MODEL, PG_DSN, TABLE
from providers import embed

INCIDENTS_FILE = Path(__file__).with_name("incidents.json")
INCIDENTS = json.loads(INCIDENTS_FILE.read_text(encoding="utf-8"))


def build_memory_text(domain, db_type, title, evidence, resolution):
    """Compact, normalized text that gets embedded (not raw logs)."""
    return (f"Domain: {domain}\nDatabase: {db_type}\nTitle: {title}\n"
            f"Evidence: {evidence}\nResolution: {resolution}")


print(f"Model: {EMBED_MODEL} ({EMBED_DIM} dims) -> table {TABLE}, {len(INCIDENTS)} incidents")

conn = psycopg.connect(PG_DSN, autocommit=True)
conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
register_vector(conn)

conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
conn.execute(f"""
    CREATE TABLE {TABLE} (
        id serial PRIMARY KEY,
        incident_id text, sid text, domain text, db_type text, incident_date date,
        title text, evidence text, root_cause_status text, resolution text,
        embedding_text text,
        embedding_model text,
        embedding vector({EMBED_DIM})
    )
""")

for inc in INCIDENTS:
    text = build_memory_text(inc["domain"], inc["db_type"], inc["title"],
                             inc["evidence"], inc["resolution"])
    vector = embed(text, "document")
    conn.execute(
        f"""INSERT INTO {TABLE}
           (incident_id, sid, domain, db_type, incident_date, title, evidence,
            root_cause_status, resolution, embedding_text, embedding_model, embedding)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (inc["incident_id"], inc["sid"], inc["domain"], inc["db_type"], inc["incident_date"], inc["title"],
         inc["evidence"], inc["root_cause_status"], inc["resolution"],
         text, EMBED_MODEL, vector),
    )
    print("Stored:", inc["incident_id"], inc["sid"], inc["title"])

print("Done.")