"""Phase 1 smoke test: health, model list and one chat completion through the gateway.

Uses only the OpenAI SDK, pointed at the gateway with base_url. The client never sees
Ollama, its address or the backend model name; it only knows the alias.

  ../code/.venv/bin/python smoke_test.py                  # default alias local-fast
  ../code/.venv/bin/python smoke_test.py --model local-quality

Env: LITELLM_BASE_URL (default http://127.0.0.1:4000), LITELLM_API_KEY
(falls back to LITELLM_MASTER_KEY from .env next to this file; the key is never printed).
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
from openai import OpenAI


def log(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", file=sys.stderr, flush=True)


def get_json(url, key=None):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"} if key else {})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read() or b"null")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="local-fast", help="gateway alias")
    args = parser.parse_args()

    load_dotenv(Path(__file__).with_name(".env"))
    base = os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000").rstrip("/")
    key = os.getenv("LITELLM_API_KEY") or os.getenv("LITELLM_MASTER_KEY")
    if not key:
        sys.exit("Set LITELLM_API_KEY (or LITELLM_MASTER_KEY in .env).")

    log(f"step 1/3: GET {base}/health/liveliness (no key needed)")
    status, body = get_json(base + "/health/liveliness")
    log(f"  HTTP {status}: {body}")

    log(f"step 2/3: GET {base}/v1/models (with key)")
    status, body = get_json(base + "/v1/models", key)
    log(f"  HTTP {status}: aliases = {[m['id'] for m in body['data']]}")

    log(f"step 3/3: chat completion via OpenAI SDK, model={args.model} "
        "(first call may load the model into VRAM)")
    client = OpenAI(base_url=base + "/v1", api_key=key, max_retries=0, timeout=300)
    started = time.perf_counter()
    raw = client.chat.completions.with_raw_response.create(
        model=args.model,
        messages=[{"role": "system", "content": "You are a terse SAP Basis assistant."},
                  {"role": "user", "content": "In one sentence: what does a HANA data backup protect?"}],
        # qwen3.6 is a thinking model: reasoning tokens count against max_tokens,
        # so a small limit ends with finish_reason=length and an empty answer.
        max_tokens=1024,
    )
    elapsed = time.perf_counter() - started
    response = raw.parse()
    log(f"  done in {elapsed:.1f}s")
    print(json.dumps({
        "requested_alias": args.model,
        "response_model": response.model,
        "litellm_call_id": raw.headers.get("x-litellm-call-id"),
        "backend_api_base": raw.headers.get("x-litellm-model-api-base"),
        "response_cost_usd": raw.headers.get("x-litellm-response-cost"),
        "finish_reason": response.choices[0].finish_reason,
        "usage": response.usage.model_dump() if response.usage else None,
        "latency_s": round(elapsed, 2),
        "reasoning_chars": len(getattr(response.choices[0].message, "reasoning_content", None) or ""),
        "answer": response.choices[0].message.content,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
