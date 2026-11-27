"""Create the virtual key of the chat app and store it in chat-app/.env (never printed).

The chat app is just another client of the gateway: it gets its own key, limited to the
local aliases and to a request rate, and never sees the master key.

  ../code/.venv/bin/python chat-app/create_key.py            # create once
  ../code/.venv/bin/python chat-app/create_key.py --rotate   # delete the old key, create a new one

Uses LITELLM_MASTER_KEY from ../.env (admin action) and the gateway on 127.0.0.1:4000.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALIAS = "chat-app"
MODELS = ["local-fast", "local-quality", "local-gemma"]


def log(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", file=sys.stderr, flush=True)


def load_env(path):
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def call(base, master, path, payload):
    request = urllib.request.Request(base + path, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {master}",
                                              "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rotate", action="store_true", help="delete the existing chat-app key first")
    args = parser.parse_args()

    target = HERE / ".env"
    if target.exists() and not args.rotate:
        sys.exit(f"{target} exists; use --rotate to replace the key")
    master = load_env(HERE.parent / ".env")["LITELLM_MASTER_KEY"]
    base = os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000").rstrip("/")

    if args.rotate:
        log(f"step 1/3: delete keys with alias '{ALIAS}'")
        status, body = call(base, master, "/key/delete", {"key_aliases": [ALIAS]})
        log(f"  HTTP {status}: deleted {len(body.get('deleted_keys', []))} key(s)")
    else:
        log("step 1/3: no existing key file, nothing to delete")

    log(f"step 2/3: POST /key/generate alias={ALIAS} models={MODELS} rpm_limit=30")
    status, body = call(base, master, "/key/generate", {
        "key_alias": ALIAS,
        "models": MODELS,
        "rpm_limit": 30,
        "metadata": {"owner": "homelab-chat", "purpose": "chat front end, local models only"},
    })
    if status != 200 or "key" not in body:
        sys.exit(f"key generation failed: HTTP {status} {body.get('error', body)}")
    key = body["key"]
    log(f"  HTTP {status}: key {key[:5]}…{key[-4:]} created (models {body.get('models')})")

    log(f"step 3/3: write {target} (mode 600)")
    old_umask = os.umask(0o077)
    try:
        target.write_text("# Virtual key of the chat app (created by create_key.py). Never commit.\n"
                          f"CHAT_APP_API_KEY={key}\n")
    finally:
        os.umask(old_umask)
    log("done; restart the chat container: docker compose up -d chat")


if __name__ == "__main__":
    main()
