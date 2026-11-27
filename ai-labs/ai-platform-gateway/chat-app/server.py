"""Homelab Assistant: a minimal chat front end for the LiteLLM gateway.

The app is only a client of the gateway. It knows the gateway URL, its own virtual key and
the model aliases; it never talks to Ollama and never sees the master key.

  GET  /             chat page (static/index.html)
  GET  /api/models   aliases this app's key may use (asked from the gateway)
  POST /api/chat     {model, messages} -> Server-Sent Events: meta, reasoning, delta, done, error
  GET  /healthz      liveness

Nothing is stored server side: the conversation lives in the browser tab. The log line per
request has user, alias, status, tokens and timings, never message text.
Python standard library only.
"""
import http.client
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GATEWAY = urllib.parse.urlsplit(os.environ.get("GATEWAY_URL", "http://litellm-gateway:4000"))
KEY = os.environ.get("CHAT_APP_API_KEY", "")
PORT = int(os.environ.get("CHAT_PORT", "8090"))
MAX_TOKENS = int(os.environ.get("CHAT_MAX_TOKENS", "2048"))
MAX_MESSAGES, MAX_CHARS, MAX_BODY = 24, 24_000, 256_000
STATIC = Path(__file__).resolve().with_name("static")
FILES = {"/": ("index.html", "text/html; charset=utf-8"),
         "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
         "/static/style.css": ("style.css", "text/css; charset=utf-8"),
         "/static/icon.svg": ("icon.svg", "image/svg+xml")}
SYSTEM_PROMPT = ("You are Homelab Assistant. You run on open-weight models on a single home GPU, "
                 "behind an AI gateway. Answer concisely and accurately. Use Markdown for lists, "
                 "tables and code. If you are not sure, say so.")
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                               "script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
_models_cache = {"at": 0.0, "models": []}


def log(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", file=sys.stderr, flush=True)


def gateway(timeout):
    https = GATEWAY.scheme == "https"
    cls = http.client.HTTPSConnection if https else http.client.HTTPConnection
    return cls(GATEWAY.hostname, GATEWAY.port or (443 if https else 80), timeout=timeout)


def allowed_models():
    """Aliases the gateway allows for this key; cached for 60 s."""
    if time.monotonic() - _models_cache["at"] < 60 and _models_cache["models"]:
        return _models_cache["models"]
    conn = gateway(10)
    try:
        conn.request("GET", "/v1/models", headers={"Authorization": f"Bearer {KEY}"})
        response = conn.getresponse()
        body = json.loads(response.read() or b"{}")
    finally:
        conn.close()
    if response.status != 200:
        raise RuntimeError(f"gateway /v1/models HTTP {response.status}")
    _models_cache.update(at=time.monotonic(), models=[m["id"] for m in body.get("data", [])])
    return _models_cache["models"]


def gateway_error(status, raw):
    try:
        error = json.loads(raw).get("error", {})
        message = error.get("message") if isinstance(error, dict) else str(error)
    except ValueError:
        message = raw[:300].decode(errors="replace") if isinstance(raw, bytes) else str(raw)[:300]
    return {"status": status, "message": (message or f"HTTP {status}")[:400]}


class Handler(BaseHTTPRequestHandler):
    server_version = "HomelabChat/1.0"
    sys_version = ""

    def log_message(self, fmt, *args):   # access log without query strings or bodies
        pass

    def _headers(self, status, content_type, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for name, value in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(name, value)
        self.end_headers()

    def _json(self, status, value):
        body = json.dumps(value).encode()
        self._headers(status, "application/json", {"Content-Length": str(len(body)), "Cache-Control": "no-store"})
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in FILES:
            name, content_type = FILES[path]
            body = (STATIC / name).read_bytes()
            self._headers(200, content_type, {"Content-Length": str(len(body)), "Cache-Control": "no-cache"})
            self.wfile.write(body)
        elif path == "/api/models":
            try:
                self._json(200, {"models": allowed_models()})
            except Exception as exc:  # gateway down: show it in the UI
                self._json(502, {"error": f"gateway not reachable: {type(exc).__name__}"})
        elif path == "/healthz":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path != "/api/chat":
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY:
            return self._json(413, {"error": "request too large"})
        try:
            request = json.loads(self.rfile.read(length))
            model = request["model"]
            messages = [{"role": m["role"], "content": m["content"]} for m in request["messages"]
                        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]
        except (ValueError, KeyError, TypeError):
            return self._json(400, {"error": "expected {model, messages:[{role, content}]}"})
        messages = messages[-MAX_MESSAGES:]
        if not messages or messages[-1]["role"] != "user":
            return self._json(400, {"error": "the last message must come from the user"})
        if sum(len(m["content"]) for m in messages) > MAX_CHARS:
            return self._json(413, {"error": f"conversation longer than {MAX_CHARS} characters, start a new chat"})
        try:
            if model not in allowed_models():
                return self._json(403, {"error": f"model '{model}' is not allowed for this app"})
        except Exception as exc:
            return self._json(502, {"error": f"gateway not reachable: {type(exc).__name__}"})
        # Identity: set by `tailscale serve` for requests from the tailnet; local requests have none.
        user = self.headers.get("Tailscale-User-Login") or "local-user"
        self._stream(model, messages, user)

    def _emit(self, event, data):
        self.wfile.write(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
        self.wfile.flush()

    def _stream(self, model, messages, user):
        payload = {"model": model, "stream": True, "stream_options": {"include_usage": True},
                   "max_tokens": MAX_TOKENS, "user": user,
                   "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages}
        started = time.perf_counter()
        first = None
        usage, finish, backend, status = None, None, None, "ok"
        self._headers(200, "text/event-stream; charset=utf-8",
                      {"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
        conn = gateway(310)
        try:
            conn.request("POST", "/v1/chat/completions", body=json.dumps(payload),
                         headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            response = conn.getresponse()
            if response.status != 200:
                status = f"http_{response.status}"
                return self._emit("error", gateway_error(response.status, response.read()))
            self._emit("meta", {"model": model, "user": user,
                                "model_group": response.getheader("x-litellm-model-group"),
                                "attempted_fallbacks": response.getheader("x-litellm-attempted-fallbacks"),
                                "call_id": response.getheader("x-litellm-call-id")})
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("error"):
                    status = "stream_error"
                    return self._emit("error", gateway_error(500, json.dumps(chunk).encode()))
                backend = chunk.get("model") or backend
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    finish = choice.get("finish_reason") or finish
                    for field, event in (("reasoning_content", "reasoning"), ("content", "delta")):
                        if delta.get(field):
                            first = first or time.perf_counter()
                            self._emit(event, {"t": delta[field]})
            elapsed = time.perf_counter() - started
            self._emit("done", {"latency_s": round(elapsed, 2),
                                "first_token_s": round(first - started, 2) if first else None,
                                "usage": usage, "finish_reason": finish, "backend_model": backend})
        except (BrokenPipeError, ConnectionResetError):
            status = "client_aborted"
        except Exception as exc:
            status = type(exc).__name__
            try:
                self._emit("error", {"status": 502, "message": f"gateway error: {type(exc).__name__}"})
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            conn.close()
            tokens = (usage or {}).get("total_tokens")
            log(f"chat user={user} model={model} status={status} tokens={tokens} "
                f"first_token_s={round(first - started, 2) if first else None} "
                f"total_s={round(time.perf_counter() - started, 2)}")


def main():
    if not KEY:
        sys.exit("CHAT_APP_API_KEY is not set (run chat-app/create_key.py)")
    log(f"Homelab Assistant on :{PORT}, gateway {GATEWAY.geturl()}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
