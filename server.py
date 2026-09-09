"""Local demonstration server. Bind to localhost; never deploy this dev server publicly."""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from domain import Library, RuleError
from worker import run_shift

ROOT = Path(__file__).resolve().parent


class Demo:
    def __init__(self, directory, model):
        self.directory, self.model = directory, model
        self.library = Library(directory / "library.sqlite3")
        self.library.initialize()
        self.lock = threading.RLock()
        self.job = {"status": "idle", "events": []}

    def state(self):
        with self.lock:
            return {**self.library.snapshot(), "job": json.loads(json.dumps(self.job))}

    def event(self, e):
        with self.lock:
            self.job["events"].append(e)

    def start(self):
        with self.lock:
            if self.job["status"] == "running":
                raise RuleError("A shift is already running.")
            self.job = {"status": "running", "events": [], "model": self.model}

        def work():
            try:
                report = run_shift(self.library, self.directory, self.model, self.event)
                with self.lock:
                    self.job.update({k: v for k, v in report.items() if k != "trace"})
            except Exception as exc:
                with self.lock:
                    self.job.update(status="failed", error_type=type(exc).__name__)
        threading.Thread(target=work, daemon=True).start()
        return {"status": "running"}

    def change(self, action):
        with self.lock:
            if self.job["status"] == "running":
                raise RuleError("Wait for this shift to finish before changing the demo.")
            if action == "reset":
                self.library.reset()
            elif action == "cancel":
                self.library.cancel("R-202")
            self.job = {"status": "idle", "events": []}
            return {"status": "ok"}


def handler(demo):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, data, content_type="application/json; charset=utf-8", download=None):
            payload = json.dumps(data).encode() if content_type.startswith("application/json") else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(payload)

        def valid_host(self):
            return self.headers.get("Host") in (f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}")

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {"error": "This demo is available on localhost only."})
            path = urlparse(self.path).path
            if path == "/api/state":
                return self.send(200, demo.state())
            if path == "/api/desk-pack":
                return self.send(200, demo.library.desk_pack().encode(), "text/markdown; charset=utf-8", "borrowbridge-desk-pack.md")
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8"),
                     "/layout-test": ("layout-test.html", "text/html; charset=utf-8"),
                     "/layout-test.js": ("layout-test.js", "text/javascript; charset=utf-8"),
                     "/layout-test.css": ("layout-test.css", "text/css; charset=utf-8")}
            if path not in files:
                return self.send(404, {"error": "Not found"})
            filename, mime = files[path]
            self.send(200, (ROOT / "static" / filename).read_bytes(), mime)

        def do_POST(self):
            origin = self.headers.get("Origin")
            allowed = {f"http://localhost:{self.server.server_port}", f"http://127.0.0.1:{self.server.server_port}"}
            if not self.valid_host() or origin not in allowed or self.headers.get("X-BorrowBridge") != "local-demo":
                return self.send(403, {"error": "Use the local demo controls."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size != 0:
                    return self.send(400, {"error": "This endpoint accepts no body."})
                path = urlparse(self.path).path
                if path == "/api/run":
                    return self.send(202, demo.start())
                if path in ("/api/reset", "/api/cancel"):
                    return self.send(200, demo.change(path.rsplit("/", 1)[-1]))
                self.send(404, {"error": "Not found"})
            except RuleError as exc:
                self.send(409, {"error": str(exc)})
            except (ValueError, TypeError):
                self.send(400, {"error": "Invalid request"})

    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--model", default="qwen3:8b")
    args = parser.parse_args()
    demo = Demo(ROOT / "private" / "web-demo", args.model)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler(demo))
    print(f"BorrowBridge: http://127.0.0.1:{args.port} (synthetic local demo)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
