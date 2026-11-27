"""Reproducibility record (step G): what exactly produced a result file.

run_metadata() is stored under "meta" in every result file of t3_chain, t3_spec and t4_attacks.
Nothing here changes behaviour; it only describes the run.

- prompt_version: the label from rag_prompt.PROMPT_VERSION (a person must bump it when a prompt changes).
- prompt_hashes: sha256 of the prompts rendered with fixed dummy input. They change whenever the prompt text or
  template changes, even if nobody bumped the label, so a forgotten bump is visible.
- split_definitions: read from the vector table (are there chunks with a clause number?), not from the
  environment, because the table was loaded earlier and the variable may differ from what was loaded.
"""
import hashlib
import subprocess
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _hash(*parts):
    return hashlib.sha256("\n--\n".join(parts).encode("utf-8")).hexdigest()[:16]


def prompt_hashes():
    from rag_prompt import build_extract_prompts, build_spec_prompts
    return dict(spec=_hash(*build_spec_prompts("PERIOD", "DATE", [])),
                extract=_hash(*build_extract_prompts("STATEMENT")))


def table_state():
    """Chunk counts of the vector table and whether definitions are split by clause. None if the DB is unreachable."""
    try:
        import psycopg
        from config import PG_DSN, TABLE
        with psycopg.connect(PG_DSN, connect_timeout=5) as conn:
            total, with_clause = conn.execute(
                f"SELECT count(*), count(clause) FROM {TABLE}").fetchone()   # TABLE comes from config, not input
        return dict(chunks=total, chunks_with_clause=with_clause, split_definitions=with_clause > 0)
    except Exception as exc:   # a missing DB must not stop a run; the gap is recorded instead
        return dict(error=str(exc)[:150])


def git_commit():
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BASE, capture_output=True,
                             text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=BASE, capture_output=True,
                               text=True, timeout=5).stdout.strip()
        return sha + ("+uncommitted" if dirty else "") if sha else None
    except Exception:
        return None


def run_metadata():
    from config import EMBED_MODEL, LLM_MODEL, LLM_PROFILE, PROFILE
    from rag_prompt import PROMPT_VERSION
    from search import THRESHOLDS_FILE
    from thresholds import load_threshold
    return dict(
        time=time.strftime("%Y-%m-%d %H:%M:%S"),
        prompt_version=PROMPT_VERSION, prompt_hashes=prompt_hashes(),
        llm_profile=LLM_PROFILE, llm=LLM_MODEL,
        embed_profile=PROFILE, embedding=EMBED_MODEL, threshold=load_threshold(PROFILE, THRESHOLDS_FILE),
        vector_table=table_state(), git=git_commit())
