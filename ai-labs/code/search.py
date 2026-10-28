"""Lab 04: similarity search = deterministic filters first, then vector similarity."""
import sys

import psycopg
from pgvector.psycopg import register_vector

from config import EMBED_MODEL, PG_DSN, SIMILARITY_THRESHOLD, TABLE
from providers import embed

COLUMNS = ["incident_id", "sid", "domain", "db_type", "incident_date", "title", "evidence",
           "root_cause_status", "resolution", "similarity"]


def find_similar(query, domain=None, db_type=None, limit=3):
    vector = embed(query, "query")
    conn = psycopg.connect(PG_DSN)
    register_vector(conn)

    # <=> is cosine distance in pgvector, so similarity = 1 - distance
    sql = f"""SELECT incident_id, sid, domain, db_type, incident_date, title, evidence,
                    root_cause_status, resolution,
                    1 - (embedding <=> %s) AS similarity
             FROM {TABLE} WHERE true"""
    params = [vector]
    if domain:                      # deterministic filter 1
        sql += " AND domain = %s"
        params.append(domain)
    if db_type:                     # deterministic filter 2
        sql += " AND db_type = %s"
        params.append(db_type)
    sql += " ORDER BY embedding <=> %s LIMIT %s"
    params += [vector, limit]

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(zip(COLUMNS, row)) for row in rows]


if __name__ == "__main__":
    query = sys.argv[1]
    domain = sys.argv[2] if len(sys.argv) > 2 else None
    db_type = sys.argv[3] if len(sys.argv) > 3 else None

    print(f"Model: {EMBED_MODEL} | table: {TABLE} | threshold: {SIMILARITY_THRESHOLD}")
    for r in find_similar(query, domain, db_type):
        mark = "OK" if r["similarity"] >= SIMILARITY_THRESHOLD else "below threshold"
        print(f"{r['similarity']:.2f} [{mark}] {r['incident_id']} {r['sid']} "
              f"{r['domain']}/{r['db_type']} {r['title']} ({r['root_cause_status']})")