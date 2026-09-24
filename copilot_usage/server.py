import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .usage import api_payload, usage_data

WEB = Path(__file__).resolve().parent / "web"
# Explicit because Windows' mimetypes registry can map .js to text/plain, which browsers refuse for modules.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/usage":
            known = parse_qs(url.query).get("v", [""])[0]
            payload = api_payload(known, self.server.budget)
            self.reply(json.dumps(payload, separators=(",", ":")).encode(), "application/json")
        else:
            self.static(url.path)

    def static(self, path):
        file = (WEB / (unquote(path).lstrip("/") or "index.html")).resolve()
        if not file.is_relative_to(WEB) or file.suffix not in CONTENT_TYPES or not file.is_file():
            self.send_error(404)
            return
        self.reply(file.read_bytes(), CONTENT_TYPES[file.suffix])

    def reply(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def serve(port, budget=None):
    print("Indexing session logs...")
    usage_data()
    print(f"Dashboard at http://localhost:{port}  (Ctrl+C to stop)")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.budget = budget
    server.serve_forever()
