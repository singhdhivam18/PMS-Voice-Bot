"""
A dependency-free health check endpoint.
Kept intentionally tiny (no Flask) to avoid extra image weight.
"""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger("publisher.health")

_status = {"ok": True, "last_run": None, "last_error": None}


def set_status(ok: bool, last_run: str = None, last_error: str = None):
    _status["ok"] = ok
    if last_run is not None:
        _status["last_run"] = last_run
    _status["last_error"] = last_error


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            code = 200 if _status["ok"] else 503
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_status).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # silence default request logging; we use our own logger


def start_health_server(port: int):
    server = HTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health check server listening on :%s/health", port)
    return server
