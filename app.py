"""Minimal HTTP frontend for the Monad signed-announcement verifier."""
from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from verifier import VerificationError, load_config, parse_number, verify_announcement

ROOT = Path(__file__).resolve().parent
CONFIG = load_config(Path(os.environ.get("VERIFIER_CONFIG", str(ROOT / "config.json"))))
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "application/javascript; charset=utf-8"),
          "/styles.css": ("styles.css", "text/css; charset=utf-8")}
SLOTS = threading.BoundedSemaphore(2)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; connect-src 'self'; script-src 'self'; style-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "NatsaiVerifier/1.0"

    def _respond(self, status: int, content: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def json_response(self, status: int, body: dict):
        self._respond(status, json.dumps(body).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            return self.json_response(200, {"status": "ok"})
        if path not in STATIC:
            return self.json_response(404, {"error": "Not found."})
        filename, mime = STATIC[path]
        return self._respond(200, (ROOT / "static" / filename).read_bytes(), mime)

    def do_POST(self):
        if self.path != "/api/verify":
            return self.json_response(404, {"error": "Not found."})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.json_response(415, {"error": "Expected application/json."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 1024:
                return self.json_response(413, {"error": "Invalid request size."})
            data = json.loads(self.rfile.read(length))
            number = parse_number(data.get("url") if isinstance(data, dict) else None)
        except (ValueError, json.JSONDecodeError, VerificationError) as exc:
            return self.json_response(400, {"ok": False, "error": str(exc)})
        if not SLOTS.acquire(blocking=False):
            return self.json_response(429, {"ok": False, "error": "Verifier is busy. Please try again shortly."})
        try:
            return self.json_response(200, verify_announcement(number, CONFIG))
        except VerificationError as exc:
            logging.warning("Verification of mf-%d failed: %s", number, exc)
            return self.json_response(422, {"ok": False, "error": str(exc)})
        except Exception:
            logging.exception("Unexpected verification error on mf-%d", number)
            return self.json_response(500, {"ok": False, "error": "Internal verifier error. Check server logs."})
        finally:
            SLOTS.release()

    def log_message(self, fmt: str, *args):
        logging.info("%s %s", self.address_string(), fmt % args)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(f"Natsai Monad Verifier listening on {host}:{port}", flush=True)
    server.serve_forever()
