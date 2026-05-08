"""
HTTP server for Fly.io deployment.
Handles GET /health (health check) and POST / (JSON-RPC 2.0 over HTTP).
Runs on port 8080.
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")

_jsonrpc_handler = None


def set_jsonrpc_handler(handler):
    global _jsonrpc_handler
    _jsonrpc_handler = handler


def check_database():
    if not DATABASE_URL:
        return False
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.close()
        return True
    except Exception:
        return False


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            body = json.dumps({
                "status": "ok",
                "server": "mtcp-mcp-server",
                "version": "1.0.0",
                "database_connected": check_database()
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error: empty body"}
            }).encode())
            return

        body = self.rfile.read(content_length)
        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error: invalid JSON"}
            }).encode())
            return

        if _jsonrpc_handler is None:
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32603, "message": "Server not ready"}
            }).encode())
            return

        response = _jsonrpc_handler(request)
        if response is None:
            self.send_response(204)
            self.end_headers()
            return

        response_body = json.dumps(response)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(response_body.encode())

    def log_message(self, format, *args):
        pass


def start_http_server(port=8080):
    server = HTTPServer(("0.0.0.0", port), RequestHandler)
    server.serve_forever()
