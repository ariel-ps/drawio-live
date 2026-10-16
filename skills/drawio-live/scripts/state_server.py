#!/usr/bin/env python3
import http.server
import socketserver
import threading
import json
import os
import re
import time
import uuid

WEBAPP_DIR = os.environ.get("DRAWIO_WEBAPP_DIR")
PORT = int(os.environ.get("DRAWIO_PORT", "8089"))
DIAGRAMS_DIR = os.environ.get("DRAWIO_DIAGRAMS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagrams"))

if not WEBAPP_DIR:
    raise SystemExit("DRAWIO_WEBAPP_DIR must be set to the drawio webapp directory (src/main/webapp)")

os.makedirs(DIAGRAMS_DIR, exist_ok=True)

POLL_TIMEOUT = 20.0
COMMAND_TIMEOUT = 25.0

NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def diagram_path(name):
    if not NAME_RE.match(name or ""):
        return None
    return os.path.join(DIAGRAMS_DIR, name + ".drawio")

_cond = threading.Condition()
_state = {"xml": None}
_queue = []
_results = {}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEBAPP_DIR, **kwargs)

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return json.loads(raw) if raw else {}

    def do_GET(self):
        if self.path.startswith("/d/"):
            name = self.path[len("/d/"):]
            self.send_response(302)
            self.send_header("Location", "/?dev=1&loadDiagram=" + name)
            self.end_headers()
            return

        if self.path.startswith("/api/diagrams/"):
            name = self.path[len("/api/diagrams/"):]
            path = diagram_path(name)
            if path is None:
                self._send_json(400, {"error": "invalid diagram name"})
                return
            if not os.path.isfile(path):
                self._send_json(404, {"error": "no diagram named " + name})
                return
            with open(path, "r") as f:
                body = f.read().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/state":
            with _cond:
                xml = _state["xml"]
            if xml is None:
                self._send_json(404, {"error": "no diagram state pushed yet"})
                return
            body = xml.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/poll":
            deadline = time.time() + POLL_TIMEOUT
            with _cond:
                while not _queue:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        self.send_response(204)
                        self.end_headers()
                        return
                    _cond.wait(timeout=remaining)
                cmd = _queue.pop(0)
            self._send_json(200, cmd)
            return

        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/diagrams/"):
            name = self.path[len("/api/diagrams/"):]
            path = diagram_path(name)
            if path is None:
                self._send_json(400, {"error": "invalid diagram name"})
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            with open(path, "w") as f:
                f.write(body)
            self._send_json(200, {"ok": True, "path": path})
            return

        if self.path == "/api/state":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            with _cond:
                _state["xml"] = body
            self.send_response(204)
            self.end_headers()
            return

        if self.path == "/api/command":
            payload = self._read_json()
            cmd_id = uuid.uuid4().hex
            payload["_requestId"] = cmd_id

            with _cond:
                _queue.append(payload)
                _cond.notify_all()

            deadline = time.time() + COMMAND_TIMEOUT
            with _cond:
                while cmd_id not in _results:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        self._send_json(504, {"ok": False, "error": "timed out waiting for browser"})
                        return
                    _cond.wait(timeout=remaining)
                result = _results.pop(cmd_id)
            self._send_json(200, result)
            return

        if self.path == "/api/result":
            payload = self._read_json()
            cmd_id = payload.get("_requestId")
            with _cond:
                if cmd_id:
                    _results[cmd_id] = payload
                    _cond.notify_all()
            self.send_response(204)
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        if "/api/poll" not in self.path:
            super().log_message(format, *args)


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Serving {WEBAPP_DIR} with full control API on http://127.0.0.1:{PORT}/")
        httpd.serve_forever()
