"""Phase 2: model routing through the gateway.

  aliases   same client code for every alias; same response schema; model load times
  errors    what the client gets for an unknown alias
  fallback  local-quality backend down -> answer from local-fast; and the error without fallback
            (run while the gateway is started with LOCAL_QUALITY_API_BASE=http://127.0.0.1:9)

  ../code/.venv/bin/python routing_demo.py aliases
  ../code/.venv/bin/python routing_demo.py errors
  ../code/.venv/bin/python routing_demo.py fallback

Progress goes to stderr, the JSON summary to stdout. Keys are never printed.
The Ollama /api/ps call is the operator view (what is in VRAM); clients never call Ollama.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import APIStatusError, APIConnectionError, OpenAI

PROMPT = [{"role": "system", "content": "You are a terse SAP Basis assistant."},
          {"role": "user", "content": "In one sentence: what does a HANA log backup protect?"}]
HEADERS = ("x-litellm-model-group", "x-litellm-model-api-base", "x-litellm-attempted-fallbacks",
           "x-litellm-attempted-retries", "x-litellm-call-id")


def log(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", file=sys.stderr, flush=True)


def loaded_models():
    base = os.getenv("OLLAMA_API_BASE", "http://192.168.178.25:11434").rstrip("/")
    with urllib.request.urlopen(base + "/api/ps", timeout=5) as response:
        models = json.load(response)["models"]
    return [f"{m['name']} {m['size_vram'] / 1e9:.1f}GB" for m in models]


def ask(client, alias, **extra):
    """The only client code. Switching models = changing the alias string."""
    started = time.perf_counter()
    raw = client.chat.completions.with_raw_response.create(
        model=alias, messages=PROMPT, max_tokens=1024, extra_body=extra or None)
    response = raw.parse()
    message = response.choices[0].message
    return {
        "alias": alias,
        "latency_s": round(time.perf_counter() - started, 2),
        "response_model": response.model,
        "object": response.object,
        "top_level_fields": sorted(k for k, v in response.model_dump().items() if v is not None),
        "finish_reason": response.choices[0].finish_reason,
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "reasoning_chars": len(getattr(message, "reasoning_content", None) or ""),
        "answer": (message.content or "").strip()[:160],
        "headers": {h: raw.headers.get(h) for h in HEADERS if raw.headers.get(h) is not None},
    }


def client_error(exc):
    if isinstance(exc, APIStatusError):
        body = exc.body if isinstance(exc.body, dict) else {}
        error = body.get("error", body) if isinstance(body, dict) else {}
        return {"http_status": exc.status_code, "sdk_exception": type(exc).__name__,
                "error_type": error.get("type"), "error_code": error.get("code"),
                "message": str(error.get("message", exc))[:300]}
    return {"sdk_exception": type(exc).__name__, "message": str(exc)[:300]}


def part_aliases(client):
    sequence = ["local-fast", "local-fast", "local-quality", "local-quality",
                "local-gemma", "local-gemma", "local-fast", "local-fast"]
    results = []
    log(f"VRAM before: {loaded_models() or 'empty'}")
    for i, alias in enumerate(sequence, 1):
        log(f"call {i}/{len(sequence)}: {alias} (a first call after a switch may load the model)")
        result = ask(client, alias)
        result["vram_after"] = loaded_models()
        log(f"  {result['latency_s']}s, {result['completion_tokens']} tokens, "
            f"finish={result['finish_reason']}, VRAM: {result['vram_after']}")
        results.append(result)
    fields = {tuple(r["top_level_fields"]) for r in results}
    log(f"same top-level response fields for all aliases: {len(fields) == 1} {sorted(fields)[0]}")
    return {"calls": results, "same_schema": len(fields) == 1}


def part_errors(client):
    log("unknown alias 'gpt-unknown' (not in config.yaml)")
    try:
        ask(client, "gpt-unknown")
        return {"unknown_alias": "unexpected success"}
    except (APIStatusError, APIConnectionError) as exc:
        error = client_error(exc)
        log(f"  client got: {error}")
        return {"unknown_alias": error}


def part_fallback(client):
    out = {}
    log("local-quality with fallbacks enabled (its backend should be down for this demo)")
    try:
        out["with_fallback"] = ask(client, "local-quality")
        log(f"  answered by {out['with_fallback']['headers']}")
    except (APIStatusError, APIConnectionError) as exc:
        out["with_fallback"] = client_error(exc)
        log(f"  client got: {out['with_fallback']}")
    log("local-quality with disable_fallbacks=true (what the client would see without a fallback)")
    try:
        out["without_fallback"] = ask(client, "local-quality", disable_fallbacks=True)
        log("  answered: the local-quality backend is up, start the gateway in broken mode first")
    except (APIStatusError, APIConnectionError) as exc:
        out["without_fallback"] = client_error(exc)
        log(f"  client got: {out['without_fallback']}")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("part", choices=("aliases", "errors", "fallback"))
    args = parser.parse_args()
    load_dotenv(Path(__file__).with_name(".env"))
    base = os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000").rstrip("/")
    key = os.getenv("LITELLM_API_KEY") or os.getenv("LITELLM_MASTER_KEY")
    client = OpenAI(base_url=base + "/v1", api_key=key, max_retries=0, timeout=300)
    log(f"part '{args.part}' against {base}")
    result = {"aliases": part_aliases, "errors": part_errors, "fallback": part_fallback}[args.part](client)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
