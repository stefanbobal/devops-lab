"""Same-origin local dashboard/API. Database credentials stay on the VM."""
import argparse
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote, parse_qs
from db_store import BASE, connect, dataset, save_review

STATIC = {"/": "index.html", "/index.html": "index.html", "/app.mjs": "app.mjs",
          "/data.mjs": "data.mjs", "/styles.css": "styles.css", "/judge_ui.mjs":"judge_ui.mjs"}


class Handler(BaseHTTPRequestHandler):
    server_version = "HomelabLocal/1"

    def respond(self, code, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def local_request(self):
        try:
            host = self.headers.get("Host", "")
            if urlsplit("http://" + host).hostname not in ("127.0.0.1", "localhost", "::1"):
                return False
            origin = self.headers.get("Origin")
            return not origin or origin == "http://" + host
        except ValueError:
            return False

    def do_GET(self):
        if not self.local_request():
            self.respond(403, {"error": "Local same-origin requests only"})
            return
        route = unquote(urlsplit(self.path).path)
        if route in STATIC:
            filename = STATIC[route]
            content_type = "text/javascript; charset=utf-8" if filename.endswith(".mjs") else (mimetypes.guess_type(filename)[0] or "text/plain") + "; charset=utf-8"
            self.respond(200, (BASE / filename).read_bytes(), content_type)
            return
        try:
            if route == "/api/health":
                with connect() as conn:
                    versions = conn.execute("SELECT version FROM llm_eval.schema_version").fetchall()
                    if versions != [(1,)]:
                        raise ValueError("Unsupported schema")
                self.respond(200, {"ok": True, "storage": "postgresql", "reviewer": os.getenv("LAB_REVIEWER", "sapops")})
            elif route == "/api/dataset":
                with connect() as conn:
                    result = dataset(conn, os.getenv("LAB_REVIEWER", "sapops"))
                self.respond(200, result)
            elif route in ('/api/judge/options','/api/judge/batches'):
                from judge_control import options,batches
                with connect() as conn:result=(options if route.endswith('options') else batches)(conn)
                self.respond(200,result)
            elif route=='/api/judge/output':
                from judge_control import job_output
                try:
                    job_id=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
                    with connect() as conn:result=job_output(conn,job_id)
                    self.respond(200,result)
                except ValueError:self.respond(400,{'error':'Neplatná identita posudku.'})
                except LookupError:self.respond(404,{'error':'Posudok neexistuje.'})
            else:
                self.respond(404, {"error": "Not found"})
        except Exception as exc:
            print("DB read failed:", type(exc).__name__, flush=True)
            self.respond(503, {"error": "Database unavailable or schema missing. Run db_import.py and check DB configuration."})

    def do_POST(self):
        if not self.local_request():
            self.respond(403, {"error": "Local same-origin requests only"})
            return
        route=urlsplit(self.path).path
        if route in ('/api/judge/plan','/api/judge/start','/api/judge/stop'):
            self.judge_post(route)
            return
        if route != "/api/reviews":
            self.respond(404, {"error": "Not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.respond(400, {"error": "Expected JSON body up to 64 KiB"})
                return
            raw = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Expected object")
            with connect() as conn:
                result = save_review(conn, raw, os.getenv("LAB_REVIEWER", "sapops"))
            self.respond(200, {"review": result})
        except (ValueError, KeyError, TypeError):
            self.respond(400, {"error": "Invalid review: check run_id, call_id and scores 0–2"})
        except LookupError:
            self.respond(404, {"error": "Call not found"})
        except Exception as exc:
            print("DB write failed:", type(exc).__name__, flush=True)
            self.respond(503, {"error": "Review was not saved. Check database availability."})

    def judge_post(self,route):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=65536 or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                raise ValueError('Očakávaný JSON objekt do 64 KiB.')
            raw=json.loads(self.rfile.read(size).decode('utf-8'))
            if not isinstance(raw,dict):raise ValueError('Očakávaný JSON objekt.')
            from judge_control import plan,start,stop
            with connect() as conn:result={'/api/judge/plan':plan,'/api/judge/start':start,'/api/judge/stop':stop}[route](conn,raw)
            self.respond(200,result)
        except (ValueError,KeyError,TypeError) as exc:
            self.respond(400,{'error':str(exc)[:500] if isinstance(exc,ValueError) else 'Neplatné parametre požiadavky.'})
        except LookupError:self.respond(404,{'error':'Plán neexistuje.'})
        except Exception as exc:
            print('Judge control failed:',type(exc).__name__,flush=True)
            self.respond(503,{'error':'Požiadavku sa nepodarilo spracovať. Skontroluj DB a službu judge.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8008)
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 inside Docker only; publish on host loopback")
    args = parser.parse_args()
    # Load dotenv/reviewer configuration and fail early without exposing DSN.
    try:
        with connect() as conn:
            if conn.execute("SELECT version FROM llm_eval.schema_version").fetchall() != [(1,)]:
                raise ValueError("Unsupported schema")
            from judge_control import init_judge
            init_judge(conn)
    except Exception as exc:
        raise SystemExit("Database not ready (" + type(exc).__name__ + "). Import results first; see DATABASE.md.")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"LLM Homelab + PostgreSQL: http://127.0.0.1:{args.port}", flush=True)
    print("Local single-user API; use SSH forwarding. No public authentication is configured.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
