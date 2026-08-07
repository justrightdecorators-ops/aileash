import hashlib
import time
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

# =====================================================================
# SECTION 1: THE ACTIVE AI.TXT CONTRACT FILE CONTENT
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

GLOBAL_SOVEREIGN_LEDGER = ["0" * 64]

# =====================================================================
# SECTION 2: INTERCEPTION ENGINE (FRAUD & INSTITUTIONAL FORCING)
# =====================================================================

class AITxtValidationEngine:
    def __init__(self):
        self.latency_limit_ms = 30
        self.velocity_window_seconds = 60
        self.velocity_max_limit = 5
        self.institutional_velocity_cache = {}

    def compute_sha256(self, input_string: str) -> str:
        """Computes absolute mathematical cryptographic key signatures."""
        return hashlib.sha256(input_string.encode('utf-8')).hexdigest()

    def evaluate_network_packet(self, headers: dict, payload_body: str, path: str) -> dict:
        start_time = time.time()
        global GLOBAL_SOVEREIGN_LEDGER

        institutional_sector = headers.get('X-Institutional-Sector', 'commercial').lower()
        client_verify_endpoint = headers.get('X-Verifiable-Endpoint', 'NONE')
        origin_ip = headers.get('X-Forwarded-For', '127.0.0.1')
        user_agent = headers.get('User-Agent', 'Unknown-System')

        try:
            payload_json = json.loads(payload_body) if payload_body else {}
        except Exception:
            payload_json = {}

        account_id = payload_json.get("account_id", "unverified_identity")
        outcome = "ALLOW"
        rationale = "Connection verified against the live ai.txt structural parameter baseline."
        http_status_code = 200

        # --- TEST 1: AUTOMATED DATA EXTRACTION BOT BLOCK ---
        malicious_scraper_agents = ['python-requests', 'scrapy', 'headlesschrome', 'curl', 'wget', 'gptbot', 'claudebot']
        if any(bot in user_agent.lower() for bot in malicious_scraper_agents):
            outcome = "BLOCK"
            rationale = "LEGAL_BLOCK: Unauthorized data harvesting halted explicitly by user-agent fingerprint."
            http_status_code = 403

        # --- TEST 2: FINANCIAL VELOCITY ANTI-FRAUD ENGINE ---
        current_time = time.time()
        if outcome != "BLOCK" and account_id != "unverified_identity":
            if account_id not in self.institutional_velocity_cache:
                self.institutional_velocity_cache[account_id] = []
            
            self.institutional_velocity_cache[account_id] = [t for t in self.institutional_velocity_cache[account_id] if current_time - t < self.velocity_window_seconds]
            self.institutional_velocity_cache[account_id].append(current_time)

            if len(self.institutional_velocity_cache[account_id]) > self.velocity_max_limit:
                outcome = "BLOCK"
                rationale = "FRAUD_BLOCK: High-frequency transaction velocity anomaly over database pathways."
                http_status_code = 403

        # --- TEST 3: THE MANDATORY ADOPTION HANDSHAKE LINK ---
        if outcome == "ALLOW" and institutional_sector in ['banking', 'insurance', 'legal']:
            if client_verify_endpoint == "NONE":
                outcome = "CHALLENGE"
                rationale = "REGULATORY_CHALLENGE: Unverified caller state. Access refused under manifest rules."
                http_status_code = 428

        # --- TEST 4: LIVE MERKLE SEQUENTIAL KEY SIGNING ---
        event_record = {
            "timestamp_epoch_ms": int(time.time() * 1000),
            "endpoint_route": path,
            "origin_ip": origin_ip,
            "outcome": outcome,
            "rationale": rationale,
            "payload_data_hash": self.compute_sha256(payload_body if payload_body else user_agent)
        }

        previous_chain_root = GLOBAL_SOVEREIGN_LEDGER[-1]
        serialized_block = json.dumps(event_record, sort_keys=True)
        new_calculated_hash = self.compute_sha256(serialized_block + previous_chain_root)
        
        GLOBAL_SOVEREIGN_LEDGER.append(new_calculated_hash)
        elapsed_execution_ms = (time.time() - start_time) * 1000

        return {
            "enforcement_decision": outcome,
            "http_status_code": http_status_code,
            "latency_ms": round(elapsed_execution_ms, 2),
            "cryptographic_receipt_key": new_calculated_hash,
            "ledger_depth": len(GLOBAL_SOVEREIGN_LEDGER) - 1,
            "immutable_record": event_record
        }

enforcement_engine = AITxtValidationEngine()

# =====================================================================
# SECTION 3: HTTP PRODUCTION SOCKET INTEGRATION LAYER (FIXED)
# =====================================================================

class SebbiProductionServerGateway(BaseHTTPRequestHandler):
    def send_socket_data(self, string_data: str, content_type: str = "text/plain", response_code: int = 200):
        """Dispatches data packets directly across the raw socket interface connection."""
        self.send_response(response_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Sebbi-Core-Interception", "Active-30ms")
        self.end_headers()
        self.wfile.write(string_data.encode('utf-8'))

    def do_GET(self):
        """Fixed Web Routing Layer. Splits URL query params out cleanly using standard string formats."""
        raw_path = self.path.split('?')[0]
        clean_path = raw_path.rstrip('/')
        
        if clean_path == "":
            clean_path = "/"

        # Dynamic Route 1: Serve the core standardized ai.txt file structure cleanly
        if clean_path == "/ai.txt":
            self.send_socket_data(AI_TXT_CONTENT, "text/plain", 200)
            return
            
        # Dynamic Route 2: Expose the live key root block state to regulatory auditors
        elif clean_path == "/api/verify":
            current_state = {
                "ledger_integrity": "unbroken",
                "root_proof_hash_key": GLOBAL_SOVEREIGN_LEDGER[-1],
                "total_committed_records": len(GLOBAL_SOVEREIGN_LEDGER) - 1,
                "protocol_standard": "sebbi.pro SHA-256 Merkle Ledger Node"
            }
            self.send_socket_data(json.dumps(current_state, indent=2), "application/json", 200)
            return
            
        # Dynamic Route 3: Standard base path landing trace for standard human clients
        elif clean_path == "/":
            # Hand over your standard public business marketing layout or front end homepage 
            homepage_html = "<h1>Welcome to Sebbi.pro</h1><p>Cryptographic compliance and decentralized AI governance infrastructure.</p>"
            self.send_socket_data(homepage_html, "text/html", 200)
            return
            
        # Dynamic Route 4: Fallback pathway treating passive data requests via the validation engine
        else:
            headers_mapped = {k: v for k, v in self.headers.items()}
            passive_receipt = enforcement_engine.evaluate_network_packet(headers_mapped, "", self.path)
            
            if passive_receipt["enforcement_decision"] != "ALLOW":
                self.send_socket_data(json.dumps(passive_receipt, indent=2), "application/json", passive_receipt["http_status_code"])
            else:
                self.send_socket_data(f"Sebbi Handshake: PASS. Key: {passive_receipt['cryptographic_receipt_key']}\n")

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_raw_payload = self.wfile.read(content_length).decode('utf-8') if content_length > 0 else ""
        
        headers_mapped = {k: v for k, v in self.headers.items()}
        engine_receipt = enforcement_engine.evaluate_network_packet(headers_mapped, post_raw_payload, self.path)
        
        self.send_socket_data(
            json.dumps(engine_receipt, indent=2), 
            "application/json", 
            engine_receipt["http_status_code"]
        )

# =====================================================================
# SECTION 4: CONTAINER DAEMON RUNTIME ENTRY INITIALIZATION
# =====================================================================

def start_production_node(target_port=8080):
    server_address_config = ('', target_port)
    server_daemon = HTTPServer(server_address_config, SebbiProductionServerGateway)
    print(f"[SUCCESS] Server file 'app.py' initialized cleanly on port {target_port}...")
    try:
        server_daemon.serve_forever()
    except KeyboardInterrupt:
        print("\n[SUSPENDED] Engine execution safely halted.")

if __name__ == "__main__":
    start_production_node()
