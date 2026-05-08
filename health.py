"""
Minimal HTTP health check server for Fly.io.
Runs on port 8080 in a separate thread alongside the stdio MCP server.
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")


def check_database():
    if not DATABASE_URL:
        return False
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.close()
        return True
    except Exception:
        return False


class HealthHandler(BaseHTTPRequestHandler):
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

    def log_message(self, format, *args):
        pass


def start_health_server(port=8080):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()
