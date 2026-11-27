"""Retrieval over contract documents: deterministic SQL filter on company first, then vector similarity."""
import sys
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from config import EMBED_MODEL, PG_DSN, PROFILE, TABLE
from providers import embed
from thresholds import load_threshold

THRESHOLDS_FILE = Path(__file__).parent / "thresholds.json"
EVIDENCE_TYPES = ("contract", "amendment", "waiver")   # analyst notes are never evidence

COLUMNS = ["company_id", "document", "doc_type", "article", "article_title", "clause", "page", "text", "similarity"]


def search_vector(vector, company_id, doc_types=None, limit=3, conn=None):
    """company_id is mandatory: a contract of another client must never be returned."""
    if not company_id:
        raise ValueError("company_id is required")
    own = conn is None
    if own:
        conn = psycopg.connect(PG_DSN)
        register_vector(conn)

    # <=> is cosine distance in pgvector, so similarity = 1 - distance
    sql = f"""SELECT company_id, document, doc_type, article, article_title, clause, page, text,
                    1 - (embedding <=> %s) AS similarity
             FROM {TABLE} WHERE company_id = %s"""
    params = [vector, company_id]
    if doc_types:                   # deterministic filter 2, e.g. exclude analyst notes
        sql += " AND doc_type = ANY(%s)"
        params.append(list(doc_types))
    sql += " ORDER BY embedding <=> %s LIMIT %s"
    params += [vector, limit]

    rows = conn.execute(sql, params).fetchall()
    if own:
        conn.close()
    return [dict(zip(COLUMNS, row)) for row in rows]


def find_similar(query, company_id, doc_types=None, limit=3):
    return search_vector(embed(query, "query"), company_id, doc_types, limit)


def find_relevant(query, company_id, doc_types=EVIDENCE_TYPES, limit=3):
    """Top-k above the per-profile threshold; empty list means "nothing found" -> human review.
    The threshold is only a guard against irrelevant text, not a test that a document exists."""
    threshold = load_threshold(PROFILE, THRESHOLDS_FILE)
    return [r for r in find_similar(query, company_id, doc_types, limit) if r["similarity"] >= threshold]


def has_doc_type(company_id, doc_type, conn=None):
    """Deterministic existence check from metadata (similarity cannot tell "no waiver" from "waiver rules")."""
    if not company_id:
        raise ValueError("company_id is required")
    own = conn is None
    if own:
        conn = psycopg.connect(PG_DSN)
    row = conn.execute(f"SELECT 1 FROM {TABLE} WHERE company_id = %s AND doc_type = %s LIMIT 1",
                       (company_id, doc_type)).fetchone()
    if own:
        conn.close()
    return row is not None


def find_waiver(query, company_id, limit=3):
    """No waiver document for the company -> [] without any similarity search."""
    if not has_doc_type(company_id, "waiver"):
        return []
    return find_relevant(query, company_id, ("waiver",), limit)


if __name__ == "__main__":
    query, company_id = sys.argv[1], sys.argv[2]
    doc_types = sys.argv[3].split(",") if len(sys.argv) > 3 else None

    threshold = load_threshold(PROFILE, THRESHOLDS_FILE)
    print(f"Model: {EMBED_MODEL} | table: {TABLE} | threshold: {threshold}")
    for r in find_similar(query, company_id, doc_types):
        mark = "OK" if r["similarity"] >= threshold else "below threshold"
        print(f"{r['similarity']:.2f} [{mark}] {r['document']} čl. {r['article']}{'/' + r['clause'] if r['clause'] else ''} (s. {r['page']}) {r['article_title']}")
