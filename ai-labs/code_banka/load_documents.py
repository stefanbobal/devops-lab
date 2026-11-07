"""Lab 03: chunk the contract documents by article and load them into covenant_docs_<profile>.

Usage: python load_documents.py            (EMBED_PROFILE selects the model and the table)
Loads data/ (dev) and, if it exists, data_test/ (held out): loading is not evaluating.
Statements (vykaz_*) are not loaded: they are the input of the agent, not its knowledge base.
"""
import json
import os
import re
from pathlib import Path

from sources import PAGE_RE, pages

DATA_DIRS = {"dev": Path(__file__).with_name("data"), "test": Path(__file__).with_name("data_test")}
DATA = DATA_DIRS["dev"]
ARTICLE_RE = re.compile(r"^## Článek (\d+) – (.*)$", re.MULTILINE)
SPLIT_TITLES = ("Definice a výklad",)   # H1: one chunk per numbered clause instead of one per article
SPLIT_DEFINITIONS = os.getenv("SPLIT_DEFINITIONS", "1") == "1"
CLAUSE_RE = re.compile(r"^\d+\.\d+ ")
DOC_TYPES = (("smlouva", "contract"), ("dodatek", "amendment"), ("waiver", "waiver"),
             ("poznamky", "notes"))


def doc_type(name):
    for prefix, kind in DOC_TYPES:
        if name.startswith(prefix):
            return kind
    return None   # vykaz_* and anything unknown is not loaded


def split_clauses(body):
    """Numbered clauses of an article, or None if the article is not made of numbered clauses only."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if len(parts) < 2 or not all(CLAUSE_RE.match(p) for p in parts):
        return None
    return parts


def chunk_document(company_id, company, name, text, split_definitions=SPLIT_DEFINITIONS):
    """One chunk per article (contract, amendment); one chunk per document for waivers and notes.
    With split_definitions the definitions article is split per numbered clause."""
    kind = doc_type(name)
    if kind is None:
        return []
    base = dict(company_id=company_id, company=company, document=name, doc_type=kind)
    chunks = []
    for page, content in pages(text).items():
        headings = list(ARTICLE_RE.finditer(content))
        for i, m in enumerate(headings):
            end = headings[i + 1].start() if i + 1 < len(headings) else len(content)
            article = dict(base, article=m.group(1), article_title=m.group(2).strip(), page=page, clause=None)
            body = content[m.end():end].strip()
            clauses = split_clauses(body) if split_definitions and article["article_title"] in SPLIT_TITLES else None
            if clauses:
                chunks += [dict(article, clause=c.split(" ", 1)[0], text=c) for c in clauses]
            else:
                chunks.append(dict(article, text=body))
    if not chunks:   # no article structure: whole document is one chunk
        body = PAGE_RE.sub("", text).strip()
        chunks.append(dict(base, article=None, article_title=None, clause=None, page=1, text=body))
    return chunks


def embedding_text(chunk):
    """Compact text that gets embedded: context header + the article text."""
    where = f"článek {chunk['article']} – {chunk['article_title']}" if chunk["article"] else "celý dokument"
    if chunk["clause"]:
        where += f", bod {chunk['clause']}"
    return f"Firma: {chunk['company']}\nDokument: {chunk['document']} ({chunk['doc_type']}), {where}\n{chunk['text']}"


def load_chunks():
    """Chunks of every existing set. Company ids differ between sets, so the SQL filter keeps them apart."""
    chunks = []
    for root in DATA_DIRS.values():
        if not (root / "expected.json").is_file():
            continue
        companies = {c["company_id"]: c["company"] for c in json.loads((root / "expected.json").read_text("utf-8"))}
        for folder in sorted((root / "companies").iterdir()):
            for path in sorted(folder.glob("*.md")):
                chunks += chunk_document(folder.name, companies[folder.name], path.name,
                                         path.read_text("utf-8"))
    return chunks


def main():
    import psycopg
    from pgvector.psycopg import register_vector

    from config import EMBED_DIM, EMBED_MODEL, PG_DSN, TABLE
    from providers import embed

    chunks = load_chunks()
    print(f"Model: {EMBED_MODEL} ({EMBED_DIM} dims) -> table {TABLE}, {len(chunks)} chunks "
          f"(split definitions: {SPLIT_DEFINITIONS})")
    conn = psycopg.connect(PG_DSN, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
    conn.execute(f"""
        CREATE TABLE {TABLE} (
            id serial PRIMARY KEY,
            company_id text, company text, document text, doc_type text,
            article text, article_title text, clause text, page int, text text,
            embedding_text text, embedding_model text, embedding vector({EMBED_DIM})
        )
    """)
    conn.execute(f"CREATE INDEX ON {TABLE} (company_id, doc_type)")
    for chunk in chunks:
        text = embedding_text(chunk)
        conn.execute(
            f"""INSERT INTO {TABLE} (company_id, company, document, doc_type, article, article_title,
                                     clause, page, text, embedding_text, embedding_model, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (chunk["company_id"], chunk["company"], chunk["document"], chunk["doc_type"],
             chunk["article"], chunk["article_title"], chunk["clause"], chunk["page"], chunk["text"],
             text, EMBED_MODEL, embed(text, "document")),
        )
    print("Done.")


if __name__ == "__main__":
    main()
