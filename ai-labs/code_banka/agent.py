"""The covenant-monitoring agent: statement + contract documents -> breach / no_breach / human_review.

    from agent import run
    result = run("C01", "2026Q1")      # or: python agent.py C01 2026Q1

Steps (every step is recorded in result["steps"] so a UI can show them):
  1 extract   LLM reads the statement into items                       (rag_prompt.build_extract_prompts)
  2 check     Python checks names, numbers, and that every number is printed on the cited page
  3 retrieve  contract chunks from the vector store (company filter is mandatory)   (search.py)
  4 spec      LLM turns the chunks into a structured specification     (rag_prompt.build_spec_prompts)
  5 verify    Python validates the spec and checks each citation against the full documents
  6 evaluate  Python computes the ratios and decides the status        (covenants.evaluate)
The LLM never decides the status. Anything unverified ends as human_review with a reason.
Model: LLM_PROFILE (config.py); embedding and thresholds: EMBED_PROFILE and thresholds.json.
"""
import json
import re
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DOC_PREFIXES = ("smlouva", "dodatek", "waiver", "poznamky")   # vykaz_* is the statement, not a contract document


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def parse_json(text):
    """First JSON object in the answer (models like to wrap it in ```json fences)."""
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in answer")
    return json.loads(text[start:end + 1])


def load_documents(company_id, data_dir=DATA):
    """Full contract documents of one company from the trusted store (never chosen by the LLM)."""
    folder = Path(data_dir) / "companies" / company_id
    return {p.name: p.read_text("utf-8") for p in sorted(folder.glob("*.md")) if p.name.startswith(DOC_PREFIXES)}


def load_statement(company_id, period, data_dir=DATA):
    return (Path(data_dir) / "companies" / company_id / f"vykaz_{period}.md").read_text("utf-8")


def build_queries(period):
    """Fixed questions: both definitions, the limit valid on the test date, and the waiver."""
    from sources import cz_date, quarter_end
    day = cz_date(quarter_end(period))
    return [("ebitda", "Jak je ve smlouvě definována EBITDA?"),
            ("debt", "Jak je ve smlouvě definován Čistý dluh?"),
            ("limit", f"Jaká je nejvyšší přípustná hodnota finančních ukazatelů pro Den testování {day}?"),
            ("waiver", f"Prominutí porušení finančního ukazatele pro Den testování {day}")]


def retrieve(company_id, period):
    """Chunks above the per-profile threshold; the waiver is searched only if the company has a waiver document."""
    from search import find_relevant, find_waiver
    chunks, seen = [], set()
    for kind, text in build_queries(period):
        found = find_waiver(text, company_id) if kind == "waiver" else find_relevant(text, company_id)
        for c in found:
            key = (c["document"], c["article"], c["clause"])
            if key not in seen:
                seen.add(key)
                chunks.append(c)
    return chunks


def check_items(extracted, statement_text):
    """Return (items {name: number or None}, problems). A number must be printed on its cited page."""
    from covenants import ALLOWED_ITEMS
    from sources import pages
    problems, items = [], {}
    raw = extracted.get("items") if isinstance(extracted, dict) else None
    if not isinstance(raw, dict):
        return {}, ["extraction: no items object"]
    page_texts = {n: re.sub(r"(?<=\d)[\s  ](?=\d)", "", t) for n, t in pages(statement_text).items()}
    for name in ALLOWED_ITEMS:
        entry = raw.get(name)
        value = entry.get("value") if isinstance(entry, dict) else None
        if value is None:
            items[name] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"{name}: value {value!r} is not a number")
            items[name] = None
            continue
        page = entry.get("page")
        shown = str(int(abs(value))) if float(value).is_integer() else str(abs(value)).replace(".", ",")
        if page not in page_texts or not re.search(rf"(?<!\d){re.escape(shown)}(?!\d)", page_texts[page]):
            problems.append(f"{name}: value {value} not found on page {page}")
            items[name] = None
            continue
        items[name] = value
    return items, problems


def run(company_id, period, statement_text=None, documents=None, chat=None, retrieve_fn=None, data_dir=DATA):
    """Run all steps. Returns {"status", "reasons", "result", "steps", ...}; never raises for model errors."""
    from covenants import SpecError, evaluate, validate_spec
    from rag_prompt import build_extract_prompts, build_spec_prompts
    from sources import quarter_end, verify_sources
    if chat is None:
        from providers import chat
    retrieve_fn = retrieve_fn or retrieve
    steps = []

    def step(name, started, status, **details):
        steps.append(dict(step=name, status=status, seconds=round(time.time() - started, 1), **details))
        log(f"  {name}: {status} ({steps[-1]['seconds']}s)" + (f" {details['summary']}" if details.get("summary") else ""))

    def finish(status, reasons, result=None, spec=None, items=None):
        log(f"  => {status} {reasons or ''}")
        return dict(company_id=company_id, period=period, status=status, reasons=reasons, result=result,
                    spec=spec, items=items, steps=steps)

    log(f"{company_id} {period}")
    statement_text = statement_text if statement_text is not None else load_statement(company_id, period, data_dir)
    documents = documents if documents is not None else load_documents(company_id, data_dir)

    # 1 extract
    t = time.time()
    system, user = build_extract_prompts(statement_text)
    try:
        extracted = parse_json(chat(system, user))
    except Exception as exc:
        step("extract", t, "failed", summary=str(exc)[:120])
        return finish("human_review", [f"extraction_failed: {str(exc)[:120]}"])
    step("extract", t, "ok")

    # 2 check
    t = time.time()
    items, problems = check_items(extracted, statement_text)
    step("check_items", t, "problems" if problems else "ok", problems=problems, summary="; ".join(problems)[:160])
    if problems:
        return finish("human_review", ["unverified_items: " + "; ".join(problems)], items=items)

    # 3 retrieve
    t = time.time()
    try:
        chunks = retrieve_fn(company_id, period)
    except Exception as exc:
        step("retrieve", t, "failed", summary=str(exc)[:120])
        return finish("human_review", [f"retrieval_failed: {str(exc)[:120]}"], items=items)
    names = [f"{c['document']} {c['article']}{'/' + c['clause'] if c.get('clause') else ''}" for c in chunks]
    step("retrieve", t, "ok", chunks=names, summary=f"{len(chunks)} chunks")
    if not chunks:
        return finish("human_review", ["no_relevant_contract_text"], items=items)

    # 4 spec
    t = time.time()
    system, user = build_spec_prompts(period, quarter_end(period).isoformat(), chunks)
    try:
        spec = parse_json(chat(system, user))
    except Exception as exc:
        step("spec", t, "failed", summary=str(exc)[:120])
        return finish("human_review", [f"spec_failed: {str(exc)[:120]}"], items=items)
    if "error" in spec:
        step("spec", t, "refused", summary=str(spec["error"])[:140])
        return finish("human_review", [f"spec_refused: {str(spec['error'])[:140]}"], items=items)
    step("spec", t, "ok")

    # 5 verify
    t = time.time()
    try:
        validate_spec(spec)
        problems = verify_sources(spec, documents, period)
    except (SpecError, AttributeError, TypeError, KeyError) as exc:
        problems = [f"invalid_spec: {exc}"]
    step("verify", t, "problems" if problems else "ok", problems=problems, summary="; ".join(problems)[:160])
    if problems:
        return finish("human_review", ["unverified_spec: " + "; ".join(problems)], spec=spec, items=items)

    # 6 evaluate
    t = time.time()
    result = evaluate(items, spec, period)
    step("evaluate", t, result["status"], summary="; ".join(result["reasons"])[:160])
    return finish(result["status"], result["reasons"], result=result, spec=spec, items=items)


def main(argv):
    if len(argv) < 2:
        raise SystemExit("Usage: python agent.py <company_id> <period>   e.g. python agent.py C01 2026Q1")
    from config import EMBED_MODEL, LLM_MODEL
    log(f"LLM {LLM_MODEL} | embedding {EMBED_MODEL}")
    out = run(argv[0], argv[1])
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
