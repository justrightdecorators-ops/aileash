"""
AILEASH SERVER
==============
Pure stdlib HTTP server. No FastAPI. No dependencies.
Wraps the AILeash governance engine as a REST API.

Endpoints:
  POST /govern          — score an AI action event
  GET  /health          — liveness check
  GET  /audit           — last 50 audit records
  GET  /user/<user_id>  — user trust state
"""

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from aileash import govern, load_user, DB

PORT = int(os.environ.get("PORT", 8080))


# ======================================================
# RESPONSE HELPERS
# ======================================================

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


# ======================================================
# REQUEST HANDLER
# ======================================================

class AILeashHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Suppress default Apache-style logs; Railway captures stdout
        print(f"[{self.address_string()}] {fmt % args}")

    # --------------------------------------------------
    # OPTIONS (CORS preflight)
    # --------------------------------------------------

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # --------------------------------------------------
    # GET
    # --------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")

        # Health check
        if path == "/health":
            ok(self, {
                "status": "ok",
                "service": "AILeash Governance Engine",
                "version": "1.0.0"
            })
            return

        # Audit log (last 50)
        if path == "/audit":
            conn = sqlite3.connect(DB)
            rows = conn.execute("""
                SELECT ts, user_id, event_json, result_json,
                       prev_hash, audit_hash
                FROM audit_log
                ORDER BY id DESC
                LIMIT 50
            """).fetchall()
            conn.close()

            records = []
            for row in rows:
                records.append({
                    "ts":         row[0],
                    "user_id":    row[1],
                    "event":      json.loads(row[2]),
                    "result":     json.loads(row[3]),
                    "prev_hash":  row[4],
                    "audit_hash": row[5],
                })

            ok(self, {"count": len(records), "records": records})
            return

        # User state
        if path.startswith("/user/"):
            user_id = path[len("/user/"):]
            if not user_id:
                err(self, "Missing user_id")
                return
            state = load_user(user_id)
            ok(self, {"user_id": user_id, **state})
            return

        # Root — API info
        if path in ("", "/"):
            ok(self, {
                "service":   "AILeash Governance API",
                "version":   "1.0.0",
                "endpoints": {
                    "POST /govern":        "Score an AI action event",
                    "GET  /health":        "Liveness check",
                    "GET  /audit":         "Last 50 audit records",
                    "GET  /user/<id>":     "User trust state",
                }
            })
            return

        err(self, "Not found", 404)

    # --------------------------------------------------
    # POST
    # --------------------------------------------------

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")

        if path != "/govern":
            err(self, "Not found", 404)
            return

        # Read body
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            err(self, "Empty request body")
            return

        try:
            body = self.rfile.read(length)
            event = json.loads(body)
        except json.JSONDecodeError:
            err(self, "Invalid JSON")
            return

        # Govern
        try:
            result = govern(event)
            ok(self, result)
        except ValueError as e:
            err(self, str(e))
        except Exception as e:
            err(self, f"Internal error: {e}", 500)


# ======================================================
# ENTRY POINT
# ======================================================

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), AILeashHandler)
    print(f"AILeash Governance API running on port {PORT}")
    print(f"  POST /govern  — score an event")
    print(f"  GET  /health  — liveness")
    print(f"  GET  /audit   — audit chain")
    print(f"  GET  /user/ID — trust state")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
