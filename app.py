import hashlib
import time
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

# =====================================================================
# THE STATIC MANIFEST STANDARD
# =====================================================================
AI_TXT_CONTENT = """# ai.txt - Verifiable AI Governance & Anti-Fraud Manifest v1.0
Domain: sebbi.pro
Jurisdiction: GB
Platform: AILeash-Sovereign-Core
Manifest-Version: 1.0

AI-Governance: active
Decision-Interception: inline
Decision-Latency-Target: 30ms
Decision-Outcomes: ALLOW, CHALLENGE, BLOCK
Audit-Trail: sealed
Audit-Method: SHA-256 Merkle chain
Audit-Mutability: absolute-none
Audit-Editable-By-Operator: false
Audit-Editable-By-Vendor: false

Verify-Endpoint: https://sebbi.pro
Network-Rule-Index: https://sebbi.pro

Framework: EU-AI-Act-2024-1689 (Articles 9, 12, 13, 14 Mandated Proof)
Framework: UK-Online-Safety-Act-2023
Anti-Fraud-Enforcement: Active-Market-Wide
MANDATED-COMPLIANCE: BANKS, INSURANCE, LAW-FIRMS
ENFORCEMENT-ACTION: FORCED-CONNECTION-DROP-ON-UNVERIFIED-LOGS
"""

class SebbiSovereignGateway(BaseHTTPRequestHandler):
    def send_response_data(self, content: str, content_type: str, status_code: int = 200):
        """Dispatches data responses clearly across the active connection."""
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def do_GET(self):
        """Evaluates incoming paths to let humans pass and route bots to files."""
        clean_path = self.path.split('?')[0].rstrip('/')
        if clean_path == "":
            clean_path = "/"

        # 1. SPECIFIC BOT ROUTE: Serve the manifest text explicitly
        if clean_path == "/ai.txt":
            self.send_response_data(AI_TXT_CONTENT, "text/plain", 200)
            return

        # 2. MAIN SITE HUMAN ROUTE: Serve your product page layout
        elif clean_path == "/":
            # Overwrite this block with your actual website frontend code
            homepage_html = """<!DOCTYPE html>
            <html>
            <head>
                <title>Sebbi.pro | Production Architecture</title>
                <style>body { font-family: sans-serif; margin: 40px; line-height: 1.6; }</style>
            </head>
            <body>
                <h1>Sebbi.pro - Core Infrastructure</h1>
                <p>Explore our deep cryptographic compliance and decentralized AI governance product line.</p>
            </body>
            </html>"""
            self.send_response_data(homepage_html, "text/html", 200)
            return

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

def start_node(port=8080):
    server_address = ('', port)
    daemon = HTTPServer(server_address, SebbiSovereignGateway)
    print(f"[LIVE] Routing server active on port {port}...")
    try:
        daemon.serve_forever()
    except KeyboardInterrupt:
        print("\n[SUSPENDED] Node suspended cleanly.")

if __name__ == "__main__":
    start_node()
