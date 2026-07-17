import asyncio
import logging
import socket
import hmac
import hashlib
import os

# --- ENTERPRISE GOVERNANCE ENGINE CONFIG ---
GATEWAY_STANDARD = """Standard: SEBBI-PROXY/1.0
Engine: AILeash-Gateway v1.0
Enforcement-Mode: ZERO-TRUST BALANCING
Target-Latency: Sub-5ms Inspection overhead
Central-Registry: https://sebbi.pro"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GATEWAY-PROXY] %(message)s")

# Load your secure infrastructure key from environment variables
PROXY_SIGNING_KEY = os.environ.get("SEBBI_PROXY_SECRET", "GATEWAY_DEV_FALLBACK_KEY").encode('utf-8')
PROXY_PORT = 8888

class ComplianceGatewayProxy:
    def __init__(self, host="0.0.0.0", port=PROXY_PORT):
        self.host = host
        self.port = port

    async def start(self):
        """Spins up the core network interception listener."""
        server = await asyncio.start_server(self.handle_client_traffic, self.host, self.port)
        logging.info(f"Sebbi Compliance Gateway operational on intercept port {self.host}:{self.port}")
        async with server:
            await server.serve_forever()

    async def handle_client_traffic(self, reader, writer):
        """Intercepts, inspects, and evaluates transit corporate AI payloads."""
        try:
            # Read incoming raw HTTP header stream
            header_data = await reader.readuntil(b"\r\n\r\n")
            header_text = header_data.decode('utf-8', errors='ignore')
            
            # Extract basic routing destination details from the HTTP request line
            first_line = header_text.split('\r\n')[0]
            logging.info(f"Inspecting outbound traffic: {first_line}")

            # --- THE ENFORCEMENT HOOK ---
            # Check if the traffic is interacting with known AI processing infrastructure
            is_ai_traffic = any(domain in header_text for domain in ["://openai.com", "anthropic", "v1/chat/completions", "localhost:11434"])
            has_compliance_token = "X-Sebbi-Compliance-Auth" in header_text

            if is_ai_traffic and not has_compliance_token:
                # BLOCK & CHALLENGE: The connection is denied because it lacks an audit ledger trail
                logging.warning(f"[TRAFFIC BLOCKED] Non-compliant AI data path detected from host: {writer.get_extra_info('peername')}")
                
                rejection_response = (
                    "HTTP/1.1 403 Forbidden\r\n"
                    "Content-Type: application/json\r\n"
                    "Connection: close\r\n\r\n"
                    '{"error": "Compliance Violation", "reason": "Missing authenticated AI-TXT/1.0 ledger signature. Clear through https://sebbi.pro"}'
                ).encode('utf-8')
                
                writer.write(rejection_response)
                await writer.drain()
                return

            # --- THE CAPTURE HOOK ---
            # If validated or non-AI, generate an internal cryptographic transaction hash
            tx_seal = hmac.new(PROXY_SIGNING_KEY, header_data, hashlib.sha256).hexdigest()
            logging.info(f"[ROUTED VERIFIED] Transaction locked. SHA-256 Record Signature: {tx_seal[:16]}...")

            # In operational production, you would forward the stream to the destination remote host here.
            # To keep this file fully self-contained as a test agent, we simulate a clean mock routing loop:
            mock_success_response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/plain\r\n"
                "X-Sebbi-Audit-Signature: " + tx_seal + "\r\n"
                "Connection: close\r\n\r\n"
                "GATEWAY_ROUTING_SUCCESSFUL"
            ).encode('utf-8')
            
            writer.write(mock_success_response)
            await writer.drain()

        except Exception as e:
            logging.error(f"Traffic parsing exception: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

if __name__ == "__main__":
    gateway = ComplianceGatewayProxy()
    try:
        asyncio.run(gateway.start())
    except KeyboardInterrupt:
        logging.info("Interception proxy offline.")
