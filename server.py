import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from aileash import govern, load_user, DB

PORT = int(os.environ.get("PORT", 8080))

def ok(handler, data, status=200):
    body = json.dumps(data, indent=2).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)

def err(handler, message, status=400):
    ok(handler, {"error": message}, status)

class AILeashHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")
    
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        if path == "/health":
            ok(self, {"status": "ok", "service": "AILeash Governance Engine", "version": "1.0.0"})
        elif path == "/audit":
            conn = sqlite3.connect(DB)
            rows = conn.execute("SELECT ts, user_id, event_json, result_json, prev_hash, audit_hash FROM audit_log ORDER BY id DESC LIMIT 50").fetchall()
            conn.close()
            records = [{"ts": r[0], "user_id": r[1], "event": json.loads(r[2]), "result": json.loads(r[3]), "prev_hash": r[4], "audit_hash": r[5]} for r in rows]
            ok(self, {"count": len(records), "records": records})
        elif path.startswith("/user/"):
            user_id = path[len("/user/"):]
            ok(self, {"user_id": user_id, **load_user(user_id)})
        elif path in ("", "/"):
            ok(self, {"service": "AILeash Governance API", "version": "1.0.0", "endpoints": {"POST /govern": "Score an AI action event", "GET /health": "Liveness check", "GET /audit": "Last 50 audit records", "GET /user/<id>": "User trust state"}})
        else:
            err(self, "Not found", 404)
    
    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        if path != "/govern":
            err(self, "Not found", 404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            err(self, "Empty request body")
            return
        try:
            event = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            err(self, "Invalid JSON")
            return
        try:
            ok(self, govern(event))
        except ValueError as e:
            err(self, str(e))
        except Exception as e:
            err(self, f"Internal error: {e}", 500)

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), AILeashHandler)
    print(f"AILeash running on port {PORT}")
    server.serve_forever()
