"""Foundry hosted-agent wrapper (architecture A: the whole chain is one tool, code decides the order and the status).

The container serves the Responses protocol on port 8088 (FOUNDRY_PORT_ENV is handled by the library).
Input text:  "C01 2026Q1"   or   {"company_id": "C01", "period": "2026Q1"}
Output text: the JSON that agent.run() returns, unchanged (status, reasons, steps), plus "retrieval_check" (counts
of chunks, chunks of another company and analyst-note chunks; the last two must be 0). No chat model sits between
the caller and agent.run(), so nothing can reword the status or change the order of the steps.

Fail closed: any input that is not exactly a company id and a period, and any unexpected error, is answered with
status "human_review" and a reason. company_id and period are checked with strict patterns BEFORE agent.run(),
because agent.load_statement() builds a file path from them.
"""
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
# C01, or C01_S1 for a company of an attack set (T4). Letters, digits and one underscore only: no path characters.
COMPANY_RE = re.compile(r"C\d{2}(_[A-Z]\d)?")
PERIOD_RE = re.compile(r"\d{4}Q[1-4]")
MAX_INPUT_CHARS = 200
# Trusted document folders inside the deployed package, set at deploy time (never by a request). The production
# agent has only "data"; the T4 test agent also gets the attack sets.
DATA_DIR_NAMES = [n for n in os.environ.get("COVENANT_DATA_DIRS", "data").split(",") if re.fullmatch(r"[a-z][a-z0-9_]*", n)]


def data_dir_for(company_id, names=None, base=BASE):
    """The configured folder that holds this company's documents, or None."""
    for name in DATA_DIR_NAMES if names is None else names:
        if (Path(base) / name / "companies" / company_id).is_dir():
            return Path(base) / name
    return None


def retrieval_check(chunks, company_id):
    """Invariant 4, measured where it runs: every chunk belongs to the company and none is an analyst note."""
    return dict(chunks=len(chunks), foreign_chunks=sum(1 for c in chunks if c["company_id"] != company_id),
                notes_chunks=sum(1 for c in chunks if c["doc_type"] == "notes"))


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def env_check(names=("AZURE_OPENAI_API_KEY", "PGPASSWORD", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_LLM_DEPLOYMENT")):
    """State of the settings the platform should have filled in. Never the value: only set/empty, the length, and
    whether a ${{connections...}} placeholder arrived unresolved."""
    lines = [f"env-check data folders: {DATA_DIR_NAMES}"]
    for name in names:
        value = os.environ.get(name)
        if value is None:
            state = "missing"
        elif not value.strip():
            state = "empty"
        elif "${{" in value:
            state = "UNRESOLVED placeholder"
        else:
            state = f"set, {len(value)} chars" + (", has spaces or quotes" if value != value.strip(" \"'") else "")
        lines.append(f"env-check {name}: {state}")
    return lines


def refuse(reason):
    """Same shape as agent.run() output for a case that was not evaluated."""
    return dict(status="human_review", reasons=[reason], result=None, steps=[])


def parse_request(text):
    """Return (company_id, period, None) or (None, None, reason). Accepts 'C01 2026Q1' or a JSON object."""
    text = (text or "").strip()
    if not text or len(text) > MAX_INPUT_CHARS:
        return None, None, "invalid_request: expected company_id and period"
    if text.startswith("{"):
        try:
            data = json.loads(text)
            company_id, period = data.get("company_id"), data.get("period")
        except (ValueError, AttributeError):
            return None, None, "invalid_request: bad JSON"
    else:
        parts = text.split()
        if len(parts) != 2:
            return None, None, "invalid_request: expected 'C01 2026Q1'"
        company_id, period = parts
    if not (isinstance(company_id, str) and COMPANY_RE.fullmatch(company_id)
            and isinstance(period, str) and PERIOD_RE.fullmatch(period)):
        return None, None, "invalid_request: company_id like C01 and period like 2026Q1"
    return company_id, period, None


def check_covenants(company_id, period):
    """The one tool. Blocking (model and database calls), so the server runs it in a worker thread."""
    import agent
    data_dir = data_dir_for(company_id)
    if data_dir is None:
        return refuse("unknown_case: no documents for this company")
    check = {}

    def retrieve_fn(company, test_period):
        chunks = agent.retrieve(company, test_period)
        check.update(retrieval_check(chunks, company))
        return chunks

    try:
        out = agent.run(company_id, period, retrieve_fn=retrieve_fn, data_dir=data_dir)
        out["retrieval_check"] = check or None   # None: the search did not run or failed (see steps)
        return out
    except FileNotFoundError:
        return refuse("unknown_case: no statement for this company and period")
    except Exception as exc:   # agent.run does not raise for model errors; this is for everything else
        log(f"unexpected {type(exc).__name__}: {str(exc)[:200]}")
        return refuse(f"internal_error: {type(exc).__name__}")


def main():
    from azure.ai.agentserver.responses import (CreateResponse, ResponseContext, ResponsesAgentServerHost,
                                                TextResponse)

    for line in env_check():
        log(line)
    app = ResponsesAgentServerHost()

    @app.response_handler
    async def handler(request: CreateResponse, context: ResponseContext, _cancellation_signal):
        company_id, period, problem = parse_request(await context.get_input_text())
        if problem:
            out = refuse(problem)
        else:
            log(f"request {company_id} {period}")
            out = await asyncio.to_thread(check_covenants, company_id, period)
        return TextResponse(context, request, text=json.dumps(out, ensure_ascii=False))

    app.run()


if __name__ == "__main__":
    main()
