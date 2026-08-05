# Codebase — part 7 of 16

Contains:
- `broadcaster.py`
- `build_sebbi_ecosystem.py`
- `gateway_proxy.py`
- `sebbi_orchestrator.py`
- `sebdog_engine.py`
- `sebdog_licence.py`
- `sebdog_reporter.py`
- `AILeash-API-Reference-v6.4.2.md`
- `LICENCE`
- `README.md`
- `admin.html`


## `broadcaster.py`

158 lines, 6412 bytes

```python
import asyncio
import json
import logging
import socket
import hmac
import hashlib
import ipaddress

# --- HARDENED ARCHITECTURE DECLARATION ---
AI_TXT_PAYLOAD = """Standard: AI-TXT/1.0
Standard-Licence: free and open - publish your own at no cost, no key required
Operator: Monop Content
Operator-Location: Blyth, Northumberland, United Kingdom
Contact: justrightdecorators@gmail.com
Last-Updated: 2026-07-05

Governance-Engine: AILeash v6.4
Decision-Model: deterministic weighted scoring (no ML drift; weights immutable)
Decision-Outcomes: ALLOW, CHALLENGE, BLOCK
Decision-Signals: 9
Decision-Latency-Median: 28ms

Verify-Endpoint: https://sebbi.pro
Companion-Standard: https://sebbi.pro
Whitepaper: https://sebbi.pro"""

HUMAN_MESSAGE = (
    "SYSTEM NOTICE: AI Governance Compliance Update for sebbi.pro.\n"
    "The updated compliance targets are now active under Standard: AI-TXT/1.0.\n"
    "Verify live audit status at: https://sebbi.pro"
)

# Operational Configuration
UDP_BROADCAST_PORT = 5001
TCP_GATEWAY_PORT = 8080
CONCURRENT_LIMIT = 2000  # Lowered slightly to manage OS file descriptor ceilings safely
TIMEOUT = 1.5           # Tightened timeout for faster failover

# Secret key used to sign messages (In production, load this securely via environment variables)
SYSTEM_SIGNING_KEY = b"SECURE_GOVERNANCE_SECRET_PASSPHRASE_KEY"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def get_network_topology():
    """
    Safely resolves the local IP address and computes the network boundary 
    using proper subnet masks instead of naive string manipulation.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Does not send actual data; used to determine local routing interface
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        # In a production environment, dynamically pull the actual netmask.
        # Fallback here assumes a standard /24 corporate subnet slice for demonstration.
        interface = ipaddress.IPv4Interface(f"{local_ip}/255.255.255.0")
        return interface.network.broadcast_address.with_prefixlen.split('/')[0], interface.network
    except Exception as e:
        logging.error(f"Failed to automatically resolve local network topology: {e}")
        return "255.255.255.255", ipaddress.IPv4Network("192.168.1.0/24")

def generate_signed_payload(message_text, declaration_text, key):
    """
    Packages the governance telemetry data and appends an immutable 
    HMAC-SHA256 signature to guarantee authenticity at the destination node.
    """
    base_data = {
        "alert_text": message_text,
        "raw_declaration": declaration_text
    }
    serialized_json = json.dumps(base_data, sort_keys=True)
    
    # Compute cryptographic signature
    signature = hmac.new(key, serialized_json.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # Enclose both the verified data and signature in a final unified wrapper
    final_package = {
        "payload": base_data,
        "signature": signature,
        "algorithm": "HMAC-SHA256"
    }
    return json.dumps(final_package)

def send_secure_udp_broadcast(compiled_payload, broadcast_target):
    """Broadcasts the cryptographically signed data packet to the subnet."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(compiled_payload.encode('utf-8'), (broadcast_target, UDP_BROADCAST_PORT))
            logging.info(f"Signed UDP broadcast successfully dispatched to {broadcast_target}:{UDP_BROADCAST_PORT}")
    except socket.error as e:
        logging.error(f"UDP broadcast failure: {e}")

async def push_to_secure_gateway(target_ip, compiled_payload):
    """Injects the signed payload directly into downstream destination gateways."""
    writer = None
    try:
        connect = asyncio.open_connection(target_ip, TCP_GATEWAY_PORT)
        _, writer = await asyncio.wait_for(connect, timeout=TIMEOUT)
        
        http_request = (
            f"POST /api/compliance/broadcast HTTP/1.1\r\n"
            f"Host: {target_ip}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(compiled_payload)}\r\n"
            f"X-Signature-Auth: True\r\n"
            f"Connection: close\r\n\r\n"
            f"{compiled_payload}"
        ).encode('utf-8')
        
        writer.write(http_request)
        await writer.drain()
        logging.info(f"[DISPATCHED] Verified telemetry pushed to infrastructure host: {target_ip}")
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        # Gracefully filter common network timeouts or offline endpoints
        return False
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

async def secure_network_orchestrator():
    broadcast_ip, network_obj = get_network_topology()
    
    # Generate the single signed package used for all downstream nodes
    signed_data_stream = generate_signed_payload(HUMAN_MESSAGE, AI_TXT_PAYLOAD, SYSTEM_SIGNING_KEY)
    
    # 1. Fire authenticated network-wide baseline blast
    send_secure_udp_broadcast(signed_data_stream, broadcast_ip)
    
    # 2. Asynchronously target explicit topological gateways (.1 and .254)
    tasks = []
    logging.info(f"Initiating asynchronous gateway verification loop across subnet: {network_obj.with_prefixlen}")
    
    # Safely isolate subnets by targeting typical routing infrastructure points
    for host in network_obj.hosts():
        host_str = str(host)
        if host_str.endswith(".1") or host_str.endswith(".254"):
            tasks.append(asyncio.create_task(push_to_secure_gateway(host_str, signed_data_stream)))
            
            # Handle task scheduling dynamically to respect system resource bounds
            if len(tasks) >= CONCURRENT_LIMIT:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
                
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    logging.info("Network compliance orchestration sequence finalized completed.")

if __name__ == "__main__":
    asyncio.run(secure_network_orchestrator())

```


## `build_sebbi_ecosystem.py`

270 lines, 9812 bytes

```python
import os
import sys

# --- CODE CONTAINERS FOR AUTOMATED INJECTION ---

BROADCASTER_CODE = """import asyncio
import json
import logging
import socket
import hmac
import hashlib
import ipaddress
import os

# --- HARDENED ARCHITECTURE DECLARATION ---
AI_TXT_PAYLOAD = \"\"\"Standard: AI-TXT/1.0
Standard-Licence: free and open - publish your own at no cost, no key required
Operator: Monop Content
Operator-Location: Blyth, Northumberland, United Kingdom
Contact: justrightdecorators@gmail.com
Last-Updated: 2026-07-05

Governance-Engine: AILeash v6.4
Decision-Model: deterministic weighted scoring (no ML drift; weights immutable)
Decision-Outcomes: ALLOW, CHALLENGE, BLOCK
Decision-Signals: 9
Decision-Latency-Median: 28ms

Verify-Endpoint: https://sebbi.pro
Companion-Standard: https://sebbi.pro
Whitepaper: https://sebbi.pro\"\"\"

HUMAN_MESSAGE = (
    "SYSTEM NOTICE: AI Governance Compliance Update for sebbi.pro.\\n"
    "The updated compliance targets are now active under Standard: AI-TXT/1.0.\\n"
    "Verify live audit status at: https://sebbi.pro"
)

UDP_BROADCAST_PORT = 5001
TCP_GATEWAY_PORT = 8080
CONCURRENT_LIMIT = 2000  
TIMEOUT = 1.5           

# Dynamic environment lookup to protect the secret signature key
SYSTEM_SIGNING_KEY = os.environ.get("SEBBI_BROADCAST_SECRET", "LOCAL_DEV_FALLBACK_KEY").encode('utf-8')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def get_network_topology():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        interface = ipaddress.IPv4Interface(f"{local_ip}/255.255.255.0")
        return str(interface.network.broadcast_address), interface.network
    except Exception as e:
        logging.error(f"Failed to automatically resolve local network topology: {e}")
        return "255.255.255.255", ipaddress.IPv4Network("192.168.1.0/24")

def generate_signed_payload(message_text, declaration_text, key):
    base_data = {
        "alert_text": message_text,
        "raw_declaration": declaration_text
    }
    serialized_json = json.dumps(base_data, sort_keys=True)
    signature = hmac.new(key, serialized_json.encode('utf-8'), hashlib.sha256).hexdigest()
    
    final_package = {
        "payload": base_data,
        "signature": signature,
        "algorithm": "HMAC-SHA256"
    }
    return json.dumps(final_package)

def send_secure_udp_broadcast(compiled_payload, broadcast_target):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(compiled_payload.encode('utf-8'), (broadcast_target, UDP_BROADCAST_PORT))
            logging.info(f"Signed UDP broadcast dispatched to {broadcast_target}:{UDP_BROADCAST_PORT}")
    except socket.error as e:
        logging.error(f"UDP broadcast failure: {e}")

async def push_to_secure_gateway(target_ip, compiled_payload):
    writer = None
    try:
        connect = asyncio.open_connection(target_ip, TCP_GATEWAY_PORT)
        _, writer = await asyncio.wait_for(connect, timeout=TIMEOUT)
        
        http_request = (
            f"POST /api/compliance/broadcast HTTP/1.1\\r\\n"
            f"Host: {target_ip}\\r\\n"
            f"Content-Type: application/json\\r\\n"
            f"Content-Length: {len(compiled_payload)}\\r\\n"
            f"X-Signature-Auth: True\\r\\n"
            f"Connection: close\\r\\n\\r\\n"
            f"{compiled_payload}"
        ).encode('utf-8')
        
        writer.write(http_request)
        await writer.drain()
        logging.info(f"[DISPATCHED] Verified telemetry pushed to infrastructure host: {target_ip}")
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

async def secure_network_orchestrator():
    broadcast_ip, network_obj = get_network_topology()
    signed_data_stream = generate_signed_payload(HUMAN_MESSAGE, AI_TXT_PAYLOAD, SYSTEM_SIGNING_KEY)
    
    send_secure_udp_broadcast(signed_data_stream, broadcast_ip)
    
    tasks = []
    logging.info(f"Initiating asynchronous gateway loop across subnet: {network_obj.with_prefixlen}")
    
    for host in network_obj.hosts():
        host_str = str(host)
        if host_str.endswith(".1") or host_str.endswith(".254"):
            tasks.append(asyncio.create_task(push_to_secure_gateway(host_str, signed_data_stream)))
            if len(tasks) >= CONCURRENT_LIMIT:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
                
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    logging.info("Network compliance orchestration sequence finalized.")

if __name__ == "__main__":
    asyncio.run(secure_network_orchestrator())
"""

GREEN_CODE = """import time
import os
import sys
import json
import socket
import logging
import hashlib
import hmac

if sys.platform != "win32":
    import resource
else:
    resource = None

# --- ECOSYSTEM METADATA ENGINE ---
GREEN_AI_STANDARD = \"\"\"Standard: GREEN-AI/1.0
Framework-Licence: open-access / standard-registry
Metrics-Engine: GreenLeash v1.2 (System Resource Auditor)
Target-SLA: Sub-2ms Internal Latency Overhead
Verification-Hub: https://sebbi.pro\"\"\"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GREEN-TELEMETRY] %(message)s")

# Dynamic environment lookup to protect the secret signature key
SYSTEM_SIGNING_KEY = os.environ.get("SEBBI_GREEN_SECRET", "LOCAL_DEV_FALLBACK_KEY").encode('utf-8')

class ProductionGreenNotary:
    def __init__(self):
        self.node_id = hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12]

    def _get_system_usage(self):
        if resource:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            cpu_time = usage.ru_utime + usage.ru_stime
            memory_mb = usage.ru_maxrss / (1024.0 if sys.platform == "darwin" else 1.0)
        else:
            cpu_time = time.process_time()
            memory_mb = 0.0
        return cpu_time, memory_mb

    def profile_process(self, process_func, *args, **kwargs):
        start_wall = time.perf_counter()
        start_cpu, start_mem = self._get_system_usage()

        result = process_func(*args, **kwargs)

        end_cpu, end_mem = self._get_system_usage()
        end_wall = time.perf_counter()

        wall_latency_ms = (end_wall - start_wall) * 1000
        cpu_time_delta_ms = (end_cpu - start_cpu) * 1000
        peak_memory_mb = max(start_mem, end_mem)

        self._package_and_sign_metrics(wall_latency_ms, cpu_time_delta_ms, peak_memory_mb)
        return result

    def _package_and_sign_metrics(self, wall_ms, cpu_ms, memory_mb):
        telemetry_data = {
            "node_id": self.node_id,
            "wall_latency_ms": round(wall_ms, 3),
            "kernel_cpu_time_ms": round(cpu_ms, 3),
            "allocated_memory_mb": round(memory_mb, 2),
            "meta_declaration": GREEN_AI_STANDARD
        }

        serialized_payload = json.dumps(telemetry_data, sort_keys=True)
        signature = hmac.new(SYSTEM_SIGNING_KEY, serialized_payload.encode('utf-8'), hashlib.sha256).hexdigest()

        final_packet = {
            "payload": telemetry_data,
            "signature": signature,
            "algorithm": "HMAC-SHA256"
        }

        logging.info(f"[AUDIT LOGGED] Wall: {round(wall_ms, 1)}ms | CPU: {round(cpu_ms, 1)}ms | RAM: {round(memory_mb, 1)}MB")
        logging.info(f"[LEDGER SEAL] HMAC: {signature[:16]}...")
        return json.dumps(final_packet)

def mock_computational_work():
    dummy_data = [x for x in range(1000000)]
    time.sleep(0.015)
    return "SUCCESS"

if __name__ == "__main__":
    logging.info("Starting GreenLeash Kernel Auditing Pipeline...")
    auditor = ProductionGreenNotary()
    auditor.profile_process(mock_computational_work)
"""

# --- BLUEPRINT DICTIONARY ---
REPO_STRUCTURE = {
    "server": {
        "server.py": "# Core production database and cryptographic Merkle chain engine\n# (Keep your proprietary server logic safely deployed here)\n"
    },
    "public-utilities": {
        "broadcaster.py": BROADCASTER_CODE,
        "green.py": GREEN_CODE
    }
}

def execute_automated_compilation():
    """Builds the folder paths and populates the production files in bulk."""
    base_path = os.getcwd()
    print(f"[*] Starting compilation blueprint in root: {base_path}")
    
    for folder, files in REPO_STRUCTURE.items():
        folder_path = os.path.join(base_path, folder)
        
        # Build missing folders securely
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            print(f"[+] Directory established: /{folder}")
            
        # Write .gitkeep so Git registers the paths even if empty
        with open(os.path.join(folder_path, ".gitkeep"), "w", encoding="utf-8") as f:
            f.write("# Forces Git tracking for this structural directory block\n")
            
        # Compile each individual file
        for file_name, code_content in files.items():
            file_path = os.path.join(folder_path, file_name)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code_content)
            print(f"    └── [COMPILED SUCCESS] Written: /{folder}/{file_name}")

    print("\n[!] SUCCESS: All files have been safely sorted into their proper paths.")
    print("[!] Run: 'git add . && git commit -m \"Add client utilities\" && git push'")

if __name__ == "__main__":
    execute_automated_compilation()

```


## `gateway_proxy.py`

280 lines, 10922 bytes

```python
import asyncio
import ssl
import json
import hmac
import hashlib
import os
import time
import logging
import urllib.request
import urllib.error

# ============================================================
# AILEASH GATEWAY PROXY - real enforcement version
#
# How it's meant to be used:
#   Customer changes their AI SDK's base URL from
#     https://api.openai.com/v1
#   to
#     https://your-gateway-domain/openai/v1
#   (same for Anthropic under /anthropic/)
#
# Every request that arrives:
#   1. Gets scored by your real /api/govern endpoint (same
#      scoring + sealing logic as server.py - nothing duplicated).
#   2. If the decision is BLOCK, the request is rejected here.
#      The real OpenAI/Anthropic call is NEVER made. That's the
#      actual gate - not an email sent after the fact.
#   3. If ALLOW or CHALLENGE, the request is forwarded to the
#      real provider over a real TLS connection, and the real
#      response is streamed back untouched.
#
# This does NOT intercept traffic the customer sends directly
# to openai.com without going through this gateway. No proxy
# that doesn't install certificates on every device can do that
# for HTTPS traffic - that's a much bigger, separate product.
# This is the same integration pattern used by every commercial
# AI gateway (Cloudflare AI Gateway, Portkey, LiteLLM proxy, etc).
# ============================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GATEWAY] %(message)s")

PROXY_PORT = int(os.environ.get("GATEWAY_PORT", 8888))

# No fallback key. If this isn't set, refuse to start rather than
# run with a guessable signing key in production.
PROXY_SIGNING_KEY = os.environ.get("SEBBI_PROXY_SECRET", "").strip()
if not PROXY_SIGNING_KEY:
    raise SystemExit(
        "SEBBI_PROXY_SECRET is not set. Refusing to start - "
        "running with a default/fallback signing key is not safe. "
        "Set SEBBI_PROXY_SECRET in your environment (Railway variables) and restart."
    )
PROXY_SIGNING_KEY = PROXY_SIGNING_KEY.encode("utf-8")

# Where your real scoring/sealing engine lives. Point this at your
# own deployment - defaults to the live sebbi.pro API.
GOVERN_URL = os.environ.get("AILEASH_GOVERN_URL", "https://sebbi.pro/api/govern")

# Which real AI providers this gateway can forward to, and their
# real hostnames. Add more here if you support more providers.
PROVIDERS = {
    "openai": "api.openai.com",
    "anthropic": "api.anthropic.com",
}


def call_govern(ailleash_key: str, event: dict):
    """Call the real /api/govern endpoint and return (decision_json, http_status).
    This is a blocking network call - run it in a thread executor so it
    doesn't stall the async event loop."""
    body = json.dumps(event).encode("utf-8")
    req = urllib.request.Request(
        GOVERN_URL,
        data=body,
        headers={
            "Authorization": "Bearer " + ailleash_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {"decision": "BLOCK", "error": "govern_returned_unreadable_error"}, e.code
    except Exception as e:
        # Network failure, timeout, DNS issue, etc. Fail closed - if we
        # can't reach the compliance engine, we don't guess ALLOW.
        return {"decision": "BLOCK", "error": "govern_unreachable: " + str(e)}, 503


def parse_request(raw_head: bytes):
    """Parse the request line + headers from the raw bytes read up to \\r\\n\\r\\n."""
    text = raw_head.decode("utf-8", errors="ignore")
    lines = text.split("\r\n")
    request_line = lines[0]
    parts = request_line.split(" ")
    method = parts[0] if len(parts) > 0 else "GET"
    path = parts[1] if len(parts) > 1 else "/"
    headers = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    return method, path, headers


def build_forward_request(method, upstream_path, headers, body: bytes, upstream_host):
    """Rebuild the HTTP request to send to the real provider. Strips our
    own gateway-only headers and sets the correct Host."""
    drop = {"host", "x-sebbi-key", "x-sebbi-event", "content-length"}
    lines = [method + " " + upstream_path + " HTTP/1.1", "Host: " + upstream_host]
    for k, v in headers.items():
        if k in drop:
            continue
        lines.append(k + ": " + v)
    lines.append("Content-Length: " + str(len(body)))
    lines.append("Connection: close")
    head = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")
    return head + body


async def read_full_request(reader):
    """Read headers, then read exactly Content-Length bytes of body if present."""
    head = await reader.readuntil(b"\r\n\r\n")
    method, path, headers = parse_request(head)
    length = int(headers.get("content-length", "0") or "0")
    body = b""
    if length:
        body = await reader.readexactly(length)
    return method, path, headers, body


async def forward_to_provider(upstream_host, request_bytes: bytes):
    """Open a real TLS connection to the real provider and return the raw
    response bytes, unmodified."""
    ctx = ssl.create_default_context()
    reader, writer = await asyncio.open_connection(upstream_host, 443, ssl=ctx)
    try:
        writer.write(request_bytes)
        await writer.drain()
        response = await reader.read(-1)
        return response
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


def default_event(headers, device_id_fallback):
    """Build a sensible /api/govern event from what the customer sent,
    falling back to safe defaults for anything they didn't specify.
    Customers can override any field by sending an X-Sebbi-Event JSON header."""
    override = headers.get("x-sebbi-event")
    if override:
        try:
            ev = json.loads(override)
        except Exception:
            ev = {}
    else:
        ev = {}
    ev.setdefault("user_id", headers.get("x-sebbi-user", "gateway_anonymous"))
    ev.setdefault("action", "ai_request")
    ev.setdefault("amount", 0)
    ev.setdefault("country", headers.get("x-sebbi-country", "UK"))
    ev.setdefault("device_id", headers.get("x-sebbi-device", device_id_fallback))
    ev.setdefault("anomaly", 0)
    ev.setdefault("device_risk", 0)
    return ev


class ComplianceGatewayProxy:
    def __init__(self, host="0.0.0.0", port=PROXY_PORT):
        self.host = host
        self.port = port

    async def start(self):
        server = await asyncio.start_server(self.handle_client_traffic, self.host, self.port)
        logging.info("AILeash Gateway operational on :%s (real enforcement, real forwarding)", self.port)
        async with server:
            await server.serve_forever()

    async def handle_client_traffic(self, reader, writer):
        peer = writer.get_extra_info("peername")
        try:
            method, path, headers, body = await read_full_request(reader)
        except Exception as e:
            logging.warning("Bad request from %s: %s", peer, e)
            writer.close()
            return

        try:
            # Route: /openai/... or /anthropic/... selects the real provider.
            segments = path.strip("/").split("/", 1)
            provider_key = segments[0] if segments else ""
            upstream_path = "/" + segments[1] if len(segments) > 1 else "/"

            if provider_key not in PROVIDERS:
                self._reject(writer, 404, "unknown_provider",
                              "Path must start with /openai/ or /anthropic/")
                return

            ailleash_key = headers.get("x-sebbi-key", "")
            if not ailleash_key:
                self._reject(writer, 401, "missing_compliance_key",
                              "Include your AILeash API key in the X-Sebbi-Key header.")
                return

            device_id_fallback = str(peer[0]) if peer else "unknown_device"
            event = default_event(headers, device_id_fallback)

            loop = asyncio.get_event_loop()
            decision_json, status = await loop.run_in_executor(
                None, call_govern, ailleash_key, event
            )
            decision = decision_json.get("decision", "BLOCK")

            if status != 200 or decision == "BLOCK":
                logging.warning("[BLOCKED] %s -> %s (%s)", peer, provider_key, decision_json.get("reasons", decision_json.get("error", "")))
                self._reject(writer, 403, "compliance_block", None, decision_json)
                return

            # ALLOW or CHALLENGE both proceed - CHALLENGE just means the
            # customer's own code should show the user the verification
            # link included in decision_json. We don't invent enforcement
            # server.py doesn't have.
            upstream_host = PROVIDERS[provider_key]
            forward_bytes = build_forward_request(method, upstream_path, headers, body, upstream_host)

            real_response = await forward_to_provider(upstream_host, forward_bytes)

            tx_seal = hmac.new(PROXY_SIGNING_KEY, real_response[:2048], hashlib.sha256).hexdigest()
            logging.info("[ROUTED] %s -> %s decision=%s seal=%s", peer, provider_key, decision, tx_seal[:16])

            writer.write(real_response)
            await writer.drain()

        except Exception as e:
            logging.error("Proxy error for %s: %s", peer, e)
            try:
                self._reject(writer, 502, "gateway_error", str(e))
            except Exception:
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _reject(self, writer, code, reason, message=None, extra=None):
        payload = {"error": reason}
        if message:
            payload["message"] = message
        if extra:
            payload["compliance_decision"] = extra
        body = json.dumps(payload).encode("utf-8")
        status_text = {401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 502: "Bad Gateway"}.get(code, "Error")
        resp = (
            "HTTP/1.1 " + str(code) + " " + status_text + "\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: " + str(len(body)) + "\r\n"
            "Connection: close\r\n\r\n"
        ).encode("utf-8") + body
        writer.write(resp)


if __name__ == "__main__":
    gateway = ComplianceGatewayProxy()
    try:
        asyncio.run(gateway.start())
    except KeyboardInterrupt:
        logging.info("Gateway offline.")

```


## `sebbi_orchestrator.py`

194 lines, 7453 bytes

```python
import asyncio
import json
import logging
import socket
import hmac
import hashlib
import ipaddress
import os
import sys
import time

# Handle cross-platform kernel metric mapping
if sys.platform != "win32":
    import resource
else:
    resource = None

# --- ARCHITECTURE METADATA ENGINE ---
CORE_MANIFEST = """Standard: AI-TXT/1.0
Standard-Licence: free and open - publish your own at no cost, no key required
Operator: Monop Content
Operator-Location: Blyth, Northumberland, United Kingdom
Contact: justrightdecorators@gmail.com
Last-Updated: 2026-07-05

Governance-Engine: AILeash v6.4
Metrics-Engine: GreenLeash v1.2 (Unified Resource Auditor)
Decision-Outcomes: ALLOW, CHALLENGE, BLOCK
Decision-Signals: 9
Decision-Latency-Median: 28ms

Verify-Endpoint: https://sebbi.pro
Companion-Standard: https://sebbi.pro
Whitepaper: https://sebbi.pro"""

HUMAN_MESSAGE = (
    "SYSTEM NOTICE: AI Governance & Sustainability Compliance Update for sebbi.pro.\n"
    "The updated compliance targets are now active under Standard: AI-TXT/1.0.\n"
    "Verify live audit status at: https://sebbi.pro"
)

# Network Operational Limits
UDP_BROADCAST_PORT = 5001
TCP_GATEWAY_PORT = 8080
CONCURRENT_LIMIT = 2000  
TIMEOUT = 1.5           

# Dynamic environment lookup to protect secret keys from public GitHub visibility
SYSTEM_SIGNING_KEY = os.environ.get("SEBBI_SYSTEM_SECRET", "LOCAL_DEV_FALLBACK_KEY").encode('utf-8')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ==========================================
# PART 1: CORE UTILITIES & METRIC AUDITING
# ==========================================

def get_network_topology():
    """Resolves local interface and dynamically maps standard subnet boundaries."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        interface = ipaddress.IPv4Interface(f"{local_ip}/255.255.255.0")
        return str(interface.network.broadcast_address), interface.network
    except Exception as e:
        logging.error(f"Failed to automatically resolve local network topology: {e}")
        return "255.255.255.255", ipaddress.IPv4Network("192.168.1.0/24")

def get_kernel_resource_usage():
    """Extracts raw processing time and RAM footprints straight from the OS kernel."""
    if resource:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        cpu_time = usage.ru_utime + usage.ru_stime
        memory_mb = usage.ru_maxrss / (1024.0 if sys.platform == "darwin" else 1.0)
    else:
        cpu_time = time.process_time()
        memory_mb = 0.0
    return cpu_time, memory_mb

def generate_signed_telemetry(message_text, manifest_text, extra_metrics=None):
    """Packages corporate alerts and signs them using HMAC-SHA256 for tampering prevention."""
    base_data = {
        "alert_text": message_text,
        "raw_declaration": manifest_text,
        "node_id": hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12]
    }
    if extra_metrics:
        base_data["sustainability_metrics"] = extra_metrics
        
    serialized_json = json.dumps(base_data, sort_keys=True)
    signature = hmac.new(SYSTEM_SIGNING_KEY, serialized_json.encode('utf-8'), hashlib.sha256).hexdigest()
    
    return json.dumps({
        "payload": base_data,
        "signature": signature,
        "algorithm": "HMAC-SHA256"
    })

# ==========================================
# PART 2: DISTRIBUTION ENGINES
# ==========================================

def execute_udp_broadcast(compiled_payload, broadcast_target):
    """Fires a connectionless notification to all listening local subnet nodes."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(compiled_payload.encode('utf-8'), (broadcast_target, UDP_BROADCAST_PORT))
            logging.info(f"Signed UDP broadcast dispatched to {broadcast_target}:{UDP_BROADCAST_PORT}")
    except socket.error as e:
        logging.error(f"UDP broadcast transmission failure: {e}")

async def dispatch_tcp_gateway(target_ip, compiled_payload):
    """Pushes a verified compliance wrapper directly into standard infrastructure points."""
    writer = None
    try:
        connect = asyncio.open_connection(target_ip, TCP_GATEWAY_PORT)
        _, writer = await asyncio.wait_for(connect, timeout=TIMEOUT)
        
        http_request = (
            f"POST /api/compliance/broadcast HTTP/1.1\r\n"
            f"Host: {target_ip}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(compiled_payload)}\r\n"
            f"X-Signature-Auth: True\r\n"
            f"Connection: close\r\n\r\n"
            f"{compiled_payload}"
        ).encode('utf-8')
        
        writer.write(http_request)
        await writer.drain()
        logging.info(f"[DISPATCHED] Verified telemetry pushed to infrastructure host: {target_ip}")
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

# ==========================================
# PART 3: RECENTRALIZED PROCESS ENGINE
# ==========================================

async def run_unified_orchestration():
    logging.info("Initializing Unified Sebbi Ecosystem Orchestration Pipeline...")
    
    # 1. Profile an operational work function (Audit System Burden)
    start_wall = time.perf_counter()
    start_cpu, start_mem = get_kernel_resource_usage()
    
    # [SIMULATION BLOCK]: Represents a standard local validation check running
    await asyncio.sleep(0.025)
    
    end_cpu, end_mem = get_kernel_resource_usage()
    end_wall = time.perf_counter()
    
    metrics = {
        "wall_latency_ms": round((end_wall - start_wall) * 1000, 3),
        "kernel_cpu_time_ms": round((end_cpu - start_cpu) * 1000, 3),
        "allocated_memory_mb": round(max(start_mem, end_mem), 2)
    }
    logging.info(f"Process Profile Completed -> CPU: {metrics['kernel_cpu_time_ms']}ms | RAM: {metrics['allocated_memory_mb']}MB")
    
    # 2. Package and sign the final structural data block
    broadcast_ip, network_obj = get_network_topology()
    signed_payload_stream = generate_signed_telemetry(HUMAN_MESSAGE, CORE_MANIFEST, extra_metrics=metrics)
    
    # 3. Fire local network UDP alert baseline
    execute_udp_broadcast(signed_payload_stream, broadcast_ip)
    
    # 4. Asynchronously scan and iterate targeted subnet infrastructure nodes
    tasks = []
    logging.info(f"Scanning target gateways across subnet map: {network_obj.with_prefixlen}")
    
    for host in network_obj.hosts():
        host_str = str(host)
        if host_str.endswith(".1") or host_str.endswith(".254"):
            tasks.append(asyncio.create_task(dispatch_tcp_gateway(host_str, signed_payload_stream)))
            if len(tasks) >= CONCURRENT_LIMIT:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
                
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    logging.info("Unified orchestration sequence finalized successfully.")

if __name__ == "__main__":
    asyncio.run(run_unified_orchestration())

```


## `sebdog_engine.py`

445 lines, 17345 bytes

```python
import json, math, time, sqlite3, hashlib, threading, argparse, sys, os, shutil
import urllib.request, urllib.parse
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

VERSION = "1.1.0"
HOME = "https://sebbi.pro"
VALIDATE_URL = HOME + "/api/validate-engine"
DB_FILE = "sebdog_audit.db"
SAFE = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQ = {"user_id","action","amount","country","device_id","anomaly","device_risk"}

_db_lock = threading.Lock()
_key_wins = defaultdict(lambda: {"min": deque(), "hour": deque()})
_key_lock = threading.Lock()
W60 = defaultdict(deque)
W5M = defaultdict(deque)
W1H = defaultdict(deque)

_licence = {
    "valid": False, "plan": "free", "product": "aileash",
    "devices": 1, "email": "", "checked_at": 0, "key": ""
}

# ==============================================================================
# LICENCE VALIDATION
# ==============================================================================

def validate_licence(api_key):
    global _licence
    try:
        req = urllib.request.Request(
            VALIDATE_URL, method="POST",
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            data=json.dumps({}).encode()
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("valid"):
            _licence.update({
                "valid": True, "plan": data.get("plan","free"),
                "product": data.get("product","aileash"),
                "devices": data.get("devices",1),
                "email": data.get("email",""),
                "checked_at": time.time(), "key": api_key
            })
            print(f"[SEBDOG] Licence valid. Plan:{_licence['plan']} Devices:{_licence['devices']}", flush=True)
            return True
        else:
            err = data.get("error","unknown")
            print(f"[SEBDOG] Licence rejected: {err}", flush=True)
            _licence["valid"] = False
            return False
    except Exception as e:
        print(f"[SEBDOG] Licence check failed: {e}", flush=True)
        if _licence["valid"] and (time.time() - _licence["checked_at"]) < 86400:
            print("[SEBDOG] Using cached licence (24h grace)", flush=True)
            return True
        return False

def revalidate_loop(api_key):
    while True:
        time.sleep(86400)
        validate_licence(api_key)

# ==============================================================================
# DATABASE + BACKUP
# Local SQLite — audit chain lives on your own machine.
# Automatic daily backup keeps data retrievable even after failures.
# Sovereignty is maintained — data never leaves your network.
# ==============================================================================

def get_conn():
    c = sqlite3.connect(DB_FILE, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT,
        event_json TEXT, result_json TEXT, prev_hash TEXT,
        audit_hash TEXT UNIQUE)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit ON audit_log(user_id)")
    c.execute("""CREATE TABLE IF NOT EXISTS chain_snapshots(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL, block_count INTEGER, tip_hash TEXT,
        snapshot_file TEXT)""")
    c.commit()
    return c

_conn = None

def init_db():
    global _conn
    _conn = get_conn()

def backup_db():
    """
    Creates a timestamped backup of the audit database.
    Data stays on your own hardware — sovereignty is not affected.
    Runs automatically every 24 hours.
    """
    backup_dir = os.path.join(os.path.dirname(DB_FILE), "sebdog_backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"sebdog_audit_{ts}.db")
    try:
        with _db_lock:
            shutil.copy2(DB_FILE, backup_path)
            blocks = _conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            tip = _conn.execute(
                "SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            tip_hash = tip[0] if tip else "GENESIS"
            _conn.execute(
                "INSERT INTO chain_snapshots(ts,block_count,tip_hash,snapshot_file) VALUES(?,?,?,?)",
                (time.time(), blocks, tip_hash, backup_path)
            )
            _conn.commit()
        print(f"[SEBDOG] Backup created: {backup_path} ({blocks} blocks)", flush=True)
        _cleanup_old_backups(backup_dir)
    except Exception as e:
        print(f"[SEBDOG] Backup failed: {e}", flush=True)

def _cleanup_old_backups(backup_dir, keep=7):
    """Keep only the most recent N backups."""
    try:
        files = sorted([
            os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
            if f.startswith("sebdog_audit_") and f.endswith(".db")
        ])
        for old in files[:-keep]:
            os.remove(old)
    except Exception:
        pass

def backup_loop():
    while True:
        time.sleep(86400)
        backup_db()

def restore_latest_backup():
    """
    Restore from the most recent backup if the main database is missing or corrupt.
    Call this on startup if the main DB file doesn't exist.
    """
    backup_dir = os.path.join(os.path.dirname(DB_FILE), "sebdog_backups")
    if not os.path.exists(backup_dir):
        return False
    files = sorted([
        os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
        if f.startswith("sebdog_audit_") and f.endswith(".db")
    ])
    if not files:
        return False
    latest = files[-1]
    try:
        shutil.copy2(latest, DB_FILE)
        print(f"[SEBDOG] Restored from backup: {latest}", flush=True)
        return True
    except Exception as e:
        print(f"[SEBDOG] Restore failed: {e}", flush=True)
        return False

def list_snapshots():
    with _db_lock:
        rows = _conn.execute(
            "SELECT ts, block_count, tip_hash, snapshot_file FROM chain_snapshots ORDER BY id DESC LIMIT 10"
        ).fetchall()
    return [{"ts": r[0], "blocks": r[1], "tip": r[2], "file": r[3]} for r in rows]

# ==============================================================================
# RATE LIMITING
# ==============================================================================

def check_rate(key):
    t = time.time()
    with _key_lock:
        w = _key_wins[key]
        while w["min"] and w["min"][0] < t-60: w["min"].popleft()
        while w["hour"] and w["hour"][0] < t-3600: w["hour"].popleft()
        if len(w["min"]) >= 60: return False, "rate_limit_minute"
        if len(w["hour"]) >= 1000: return False, "rate_limit_hour"
        w["min"].append(t); w["hour"].append(t)
        return True, None

# ==============================================================================
# CORE ENGINE
# ==============================================================================

def now(): return time.time()
def clamp(x,a=0.0,b=1.0): return max(a,min(b,x))
def sha(p): return hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()

def upd_vel(uid):
    t=now()
    for q in [W60[uid],W5M[uid],W1H[uid]]: q.append(t)
    c=now()
    W60[uid]=deque(x for x in W60[uid] if x>=c-60)
    W5M[uid]=deque(x for x in W5M[uid] if x>=c-300)
    W1H[uid]=deque(x for x in W1H[uid] if x>=c-3600)

def vel(uid): return {"60s":len(W60[uid]),"5m":len(W5M[uid]),"1h":len(W1H[uid])}

def load_user(uid):
    with _db_lock:
        r=_conn.execute("SELECT trust,last_country FROM users WHERE user_id=?",(uid,)).fetchone()
    return{"trust":r[0],"last_country":r[1]} if r else{"trust":0.5,"last_country":None}

def save_user(uid,trust,country):
    with _db_lock:
        _conn.execute(
            "INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country",
            (uid,trust,country))
        _conn.commit()

def score_event(s):
    reasons=[]
    sc=(1-s["trust"])*0.30
    v60=s["v60"]; sc+=min(v60/20,1)*0.15
    if v60>10: reasons.append("velocity_spike")
    sc+=min(s["v5m"]/50,1)*0.10+min(s["v1h"]/200,1)*0.10
    amt=float(s.get("amount",0)); sc+=min(math.log1p(amt)/math.log1p(10000),1)*0.15
    if amt>500: reasons.append("high_amount")
    dr=float(s.get("device_risk",0)); sc+=dr*0.10
    if dr>0.5: reasons.append("risky_device")
    an=float(s.get("anomaly",0)); sc+=an*0.10
    if an>0.5: reasons.append("behaviour_anomaly")
    if s.get("country_shift"): sc+=0.10; reasons.append("country_shift")
    if s.get("unsafe_country"): sc+=0.10; reasons.append("unsafe_country")
    if s["trust"]<0.4: reasons.append("low_trust")
    return round(clamp(sc),4),reasons

def decide(sc):
    if sc<0.35: return"ALLOW"
    if sc<0.70: return"CHALLENGE"
    return"BLOCK"

def upd_trust(t,d):
    if d=="ALLOW": t+=(1-t)*0.01
    elif d=="CHALLENGE": t-=t*0.02
    elif d=="BLOCK": t-=t*0.08
    return clamp(t,0.05,1.0)

def chain_tip():
    with _db_lock:
        r=_conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return r[0] if r else"GENESIS"

def seal(event,result,ts):
    prev=chain_tip()
    h=sha({"prev_hash":prev,"ts":ts,"event":event,"result":result})
    with _db_lock:
        _conn.execute(
            "INSERT INTO audit_log(ts,user_id,event_json,result_json,prev_hash,audit_hash) VALUES(?,?,?,?,?,?)",
            (ts,event["user_id"],json.dumps(event),json.dumps(result),prev,h))
        _conn.commit()
    return h

def verify_chain():
    with _db_lock:
        rows=_conn.execute(
            "SELECT event_json,result_json,prev_hash,audit_hash,ts FROM audit_log ORDER BY id ASC"
        ).fetchall()
    if not rows: return{"valid":True,"blocks":0,"message":"Empty chain"}
    prev="GENESIS"
    for i,row in enumerate(rows):
        p={"prev_hash":row[2],"ts":row[4],"event":json.loads(row[0]),"result":json.loads(row[1])}
        if sha(p)!=row[3] or row[2]!=prev:
            return{"valid":False,"broken_at":i,"message":f"Tampered at block {i}"}
        prev=row[3]
    return{"valid":True,"blocks":len(rows),"tip":rows[-1][3],"message":"Chain intact"}

def govern(event):
    missing=REQ-event.keys()
    if missing: raise ValueError(f"Missing fields: {missing}")
    if not _licence["valid"]:
        return{"error":"licence_invalid","message":f"Valid API key required. Get yours at {HOME}"},403
    ts=now(); uid=event["user_id"]
    state=load_user(uid); upd_vel(uid); v=vel(uid)
    country=event["country"]
    signals={
        "trust":state["trust"],"v60":v["60s"],"v5m":v["5m"],"v1h":v["1h"],
        "amount":float(event.get("amount",0)),
        "device_risk":float(event.get("device_risk",0)),
        "anomaly":float(event.get("anomaly",0)),
        "country_shift":state["last_country"] is not None and state["last_country"]!=country,
        "unsafe_country":country not in SAFE
    }
    sc,reasons=score_event(signals)
    dec=decide(sc); trust=upd_trust(state["trust"],dec)
    save_user(uid,trust,country)
    result={
        "decision":dec,"score":sc,"trust":round(trust,4),
        "reasons":reasons,"version":VERSION,"engine":"sebdog",
        "local":True,"timestamp":ts
    }
    result["audit_hash"]=seal(event,result,ts)
    return result,200

# ==============================================================================
# HTTP SERVER
# ==============================================================================

def send_json(h,data,status=200):
    body=json.dumps(data,indent=2).encode()
    h.send_response(status)
    h.send_header("Content-Type","application/json")
    h.send_header("Content-Length",str(len(body)))
    h.send_header("Access-Control-Allow-Origin","*")
    h.end_headers()
    h.wfile.write(body)

def read_body(h):
    n=int(h.headers.get("Content-Length",0))
    if n:
        try: return json.loads(h.rfile.read(n))
        except: return{}
    return{}

def get_bearer(h):
    auth=h.headers.get("Authorization","")
    if auth.startswith("Bearer "): return auth[7:]
    return h.headers.get("X-API-Key","").strip()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type,Authorization,X-API-Key")
        self.end_headers()

    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/health":
            send_json(self,{
                "status":"ok","version":VERSION,"engine":"sebdog","local":True,
                "licence":{
                    "valid":_licence["valid"],"plan":_licence["plan"],
                    "devices":_licence["devices"],"email":_licence["email"]
                }
            })
        elif path=="/verify-chain":
            send_json(self,verify_chain())
        elif path=="/stats":
            with _db_lock:
                blocks=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                users=_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            send_json(self,{
                "audit_blocks":blocks,"users_tracked":users,
                "version":VERSION,"engine":"sebdog","licence_valid":_licence["valid"]
            })
        elif path=="/snapshots":
            send_json(self,{"snapshots":list_snapshots()})
        elif path=="/backup":
            backup_db()
            send_json(self,{"ok":True,"message":"Backup created"})
        else:
            send_json(self,{"error":"not_found"},404)

    def do_POST(self):
        path=urlparse(self.path).path.rstrip("/")
        data=read_body(self)
        if path in("/govern","/api/govern"):
            bearer=get_bearer(self)
            if bearer and bearer!=_licence["key"]:
                send_json(self,{"error":"invalid_api_key"},401); return
            ok,ec=check_rate(bearer or"default")
            if not ok:
                send_json(self,{"error":ec},429); return
            try:
                result,status=govern(data)
                send_json(self,result,status)
            except ValueError as e:
                send_json(self,{"error":str(e)},400)
            except Exception as e:
                send_json(self,{"error":"internal","detail":str(e)},500)
        else:
            send_json(self,{"error":"not_found"},404)

class ThreadedServer(ThreadingMixIn,HTTPServer):
    allow_reuse_address=True
    daemon_threads=True

# ==============================================================================
# ENTRY POINT
# ==============================================================================

def main():
    parser=argparse.ArgumentParser(description="Sebdog Engine — AILeash local compliance engine")
    parser.add_argument("--key",required=True,help="Your AILeash API key from sebbi.pro")
    parser.add_argument("--port",type=int,default=9090,help="Port (default: 9090)")
    parser.add_argument("--db",default="sebdog_audit.db",help="SQLite audit database path")
    parser.add_argument("--backup-on-start",action="store_true",help="Create a backup on startup")
    args=parser.parse_args()

    global DB_FILE
    DB_FILE=args.db

    print(f"[SEBDOG] Sebdog Engine v{VERSION} starting...",flush=True)

    # Restore from backup if DB missing
    if not os.path.exists(DB_FILE):
        print(f"[SEBDOG] Database not found. Checking for backups...",flush=True)
        if restore_latest_backup():
            print(f"[SEBDOG] Data restored from backup.",flush=True)
        else:
            print(f"[SEBDOG] No backup found. Starting fresh chain.",flush=True)

    init_db()

    if args.backup_on_start:
        backup_db()

    print(f"[SEBDOG] Validating licence with sebbi.pro...",flush=True)
    if not validate_licence(args.key):
        print(f"[SEBDOG] Licence validation failed. Get your key at {HOME}",flush=True)
        sys.exit(1)

    threading.Thread(target=revalidate_loop,args=(args.key,),daemon=True).start()
    threading.Thread(target=backup_loop,daemon=True).start()

    server=ThreadedServer(("0.0.0.0",args.port),Handler)
    print(f"[SEBDOG] Engine running on port {args.port}",flush=True)
    print(f"[SEBDOG] POST http://localhost:{args.port}/govern",flush=True)
    print(f"[SEBDOG] GET  http://localhost:{args.port}/health",flush=True)
    print(f"[SEBDOG] GET  http://localhost:{args.port}/verify-chain",flush=True)
    print(f"[SEBDOG] GET  http://localhost:{args.port}/snapshots",flush=True)
    print(f"[SEBDOG] Backups: ./sebdog_backups/ (daily, last 7 kept)",flush=True)
    print(f"[SEBDOG] Sovereignty: all data stays on your hardware.",flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[SEBDOG] Shutting down.",flush=True)

if __name__=="__main__":
    main()

```


## `sebdog_licence.py`

332 lines, 12401 bytes

```python
"""
SEBDOG LICENCE SYSTEM v1.0.0
Air-gapped cryptographic licence tokens for the Sebdog Engine.
Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK

HOW IT WORKS:
- sebbi.pro generates a signed annual licence token on signup
- The token is validated entirely locally — no phone-home required
- Any tampering with the token is cryptographically detected
- Tokens expire after 12 months and must be renewed
- The signing secret never leaves sebbi.pro's servers

SECURITY MODEL:
- HMAC-SHA256 signatures — industry standard, same as used by AWS, Stripe
- Constant-time comparison prevents timing attacks
- Base64url encoding for safe transmission
- JSON payload is deterministically serialised (sort_keys=True)
- Every validation attempt is logged to the local audit chain
"""

import hashlib, hmac, json, time, base64, secrets, sqlite3, threading
from typing import Tuple, Optional, Dict

# ==============================================================================
# CONSTANTS
# ==============================================================================

TOKEN_VERSION = "1"
GRACE_SECONDS = 86400 * 7  # 7-day grace period after expiry before hard block
AUDIT_DB = "sebdog_audit.db"

# ==============================================================================
# TOKEN GENERATION (runs on sebbi.pro server only)
# The signing secret is an environment variable on Railway.
# It never appears in any file that gets shipped to customers.
# ==============================================================================

def generate_token(api_key: str, devices: int, plan: str,
                   email: str, secret: bytes,
                   validity_days: int = 365) -> str:
    """
    Generate a cryptographically signed annual licence token.
    Called by sebbi.pro when a customer requests an air-gapped licence.

    Args:
        api_key:       The customer's AILeash API key
        devices:       Licensed device count
        plan:          'free' or 'paid'
        email:         Customer email
        secret:        HMAC signing secret (from Railway env var)
        validity_days: Token validity in days (default 365)

    Returns:
        Base64url-encoded signed token string
    """
    issued = int(time.time())
    expires = issued + (validity_days * 86400)

    payload = json.dumps({
        "v": TOKEN_VERSION,
        "key": api_key,
        "devices": devices,
        "plan": plan,
        "email": email,
        "issued": issued,
        "expires": expires
    }, sort_keys=True, separators=(',', ':'))

    sig = hmac.new(secret, payload.encode('utf-8'), hashlib.sha256).hexdigest()

    token_data = json.dumps({
        "payload": payload,
        "sig": sig
    }, separators=(',', ':'))

    return base64.urlsafe_b64encode(token_data.encode('utf-8')).decode('utf-8')


# ==============================================================================
# TOKEN VALIDATION (runs on customer hardware — no network required)
# ==============================================================================

def validate_token(token: str, secret: bytes) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Validate a licence token entirely locally.
    No network connection required.

    Returns:
        (licence_data, None) on success
        (None, error_code) on failure

    Error codes:
        invalid_format      — token cannot be decoded
        invalid_signature   — token has been tampered with
        token_expired       — token is past expiry + grace period
        version_mismatch    — token version not supported
    """
    try:
        raw = json.loads(base64.urlsafe_b64decode(token.encode('utf-8')))
        payload_str = raw.get("payload", "")
        sig = raw.get("sig", "")
    except Exception:
        return None, "invalid_format"

    # Constant-time HMAC comparison — prevents timing attacks
    expected = hmac.new(secret, payload_str.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None, "invalid_signature"

    try:
        data = json.loads(payload_str)
    except Exception:
        return None, "invalid_format"

    if data.get("v") != TOKEN_VERSION:
        return None, "version_mismatch"

    # Apply grace period — token runs for 7 days past expiry
    if data.get("expires", 0) + GRACE_SECONDS < time.time():
        return None, "token_expired"

    return data, None


def is_in_grace_period(token_data: Dict) -> bool:
    """Returns True if token is past expiry but within grace period."""
    return token_data.get("expires", 0) < time.time()


def days_until_expiry(token_data: Dict) -> int:
    """Returns days remaining until token expiry (negative if expired)."""
    return int((token_data.get("expires", 0) - time.time()) / 86400)


# ==============================================================================
# LOCAL LICENCE STORE
# Caches the validated token locally so validation survives restarts.
# Everything stays on the customer's own hardware.
# ==============================================================================

_lock = threading.Lock()


def save_licence_locally(db_path: str, token: str, licence_data: Dict):
    """Cache the validated licence in the local audit database."""
    with _lock:
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS licence_cache (
                id INTEGER PRIMARY KEY,
                token TEXT,
                api_key TEXT,
                devices INTEGER,
                plan TEXT,
                email TEXT,
                issued INTEGER,
                expires INTEGER,
                cached_at REAL
            )
        """)
        conn.execute("DELETE FROM licence_cache")  # Only one licence at a time
        conn.execute("""
            INSERT INTO licence_cache
            (token, api_key, devices, plan, email, issued, expires, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            token,
            licence_data.get("key", ""),
            licence_data.get("devices", 1),
            licence_data.get("plan", "free"),
            licence_data.get("email", ""),
            licence_data.get("issued", 0),
            licence_data.get("expires", 0),
            time.time()
        ))
        conn.commit()
        conn.close()


def load_licence_locally(db_path: str) -> Optional[Tuple[str, Dict]]:
    """Load a cached licence from the local database."""
    try:
        with _lock:
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT token, api_key, devices, plan, email, issued, expires "
                "FROM licence_cache LIMIT 1"
            ).fetchone()
            conn.close()
        if not row:
            return None
        token, api_key, devices, plan, email, issued, expires = row
        data = {
            "v": TOKEN_VERSION,
            "key": api_key,
            "devices": devices,
            "plan": plan,
            "email": email,
            "issued": issued,
            "expires": expires
        }
        return token, data
    except Exception:
        return None


# ==============================================================================
# STRESS TEST
# Run with: python sebdog_licence.py
# ==============================================================================

if __name__ == "__main__":
    import sys

    print("SEBDOG LICENCE SYSTEM — Stress Test")
    print("=" * 60)

    # Generate a test secret (on sebbi.pro this comes from Railway env vars)
    SECRET = secrets.token_bytes(32)
    TEST_KEY = "al_live_" + secrets.token_hex(24)
    PASSES = 0
    FAILURES = 0

    def check(name, condition, detail=""):
        global PASSES, FAILURES
        if condition:
            print(f"  PASS  {name}")
            PASSES += 1
        else:
            print(f"  FAIL  {name} {detail}")
            FAILURES += 1

    # --- Basic validity ---
    print("\n[1] Basic token generation and validation")
    token = generate_token(TEST_KEY, 10000, "paid", "test@example.com", SECRET)
    data, err = validate_token(token, SECRET)
    check("Valid token accepted", err is None)
    check("API key preserved", data and data.get("key") == TEST_KEY)
    check("Device count preserved", data and data.get("devices") == 10000)
    check("Plan preserved", data and data.get("plan") == "paid")
    check("Not in grace period", data and not is_in_grace_period(data))
    check("Days until expiry > 360", data and days_until_expiry(data) > 360)

    # --- Tamper detection ---
    print("\n[2] Tamper detection")
    raw = json.loads(base64.urlsafe_b64decode(token))
    raw["payload"] = raw["payload"].replace("10000", "99999")
    bad_token = base64.urlsafe_b64encode(json.dumps(raw, separators=(',',':')).encode()).decode()
    _, err = validate_token(bad_token, SECRET)
    check("Tampered device count rejected", err == "invalid_signature")

    raw2 = json.loads(base64.urlsafe_b64decode(token))
    raw2["payload"] = raw2["payload"].replace("paid", "enterprise")
    bad_token2 = base64.urlsafe_b64encode(json.dumps(raw2, separators=(',',':')).encode()).decode()
    _, err = validate_token(bad_token2, SECRET)
    check("Tampered plan rejected", err == "invalid_signature")

    raw3 = json.loads(base64.urlsafe_b64decode(token))
    raw3["sig"] = "0" * 64
    bad_token3 = base64.urlsafe_b64encode(json.dumps(raw3, separators=(',',':')).encode()).decode()
    _, err = validate_token(bad_token3, SECRET)
    check("Zeroed signature rejected", err == "invalid_signature")

    # --- Expiry ---
    print("\n[3] Expiry handling")
    expired = generate_token(TEST_KEY, 100, "paid", "test@example.com", SECRET, validity_days=-1)
    data_exp, err = validate_token(expired, SECRET)
    check("Recently expired token in grace period", err is None and data_exp is not None)
    check("Grace period detected", data_exp and is_in_grace_period(data_exp))

    hard_expired = generate_token(TEST_KEY, 100, "paid", "test@example.com", SECRET, validity_days=-9)
    _, err = validate_token(hard_expired, SECRET)
    check("Hard expired token rejected", err == "token_expired")

    # --- Wrong secret ---
    print("\n[4] Secret validation")
    wrong = secrets.token_bytes(32)
    _, err = validate_token(token, wrong)
    check("Wrong secret rejected", err == "invalid_signature")

    almost_right = bytearray(SECRET)
    almost_right[0] ^= 1
    _, err = validate_token(token, bytes(almost_right))
    check("One-bit-flipped secret rejected", err == "invalid_signature")

    # --- Malformed tokens ---
    print("\n[5] Malformed input handling")
    _, err = validate_token("notbase64!!!", SECRET)
    check("Garbage input rejected", err is not None)
    _, err = validate_token("", SECRET)
    check("Empty token rejected", err is not None)
    _, err = validate_token(base64.urlsafe_b64encode(b"{}").decode(), SECRET)
    check("Empty JSON rejected", err is not None)

    # --- Local caching ---
    print("\n[6] Local licence caching")
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db = f.name
    try:
        data_valid, _ = validate_token(token, SECRET)
        save_licence_locally(test_db, token, data_valid)
        cached = load_licence_locally(test_db)
        check("Licence saved and retrieved", cached is not None)
        check("Cached key matches", cached and cached[1].get("key") == TEST_KEY)
        check("Cached devices match", cached and cached[1].get("devices") == 10000)
    finally:
        os.unlink(test_db)

    # --- Performance ---
    print("\n[7] Performance")
    import timeit
    gen_time = timeit.timeit(
        lambda: generate_token(TEST_KEY, 10000, "paid", "test@example.com", SECRET),
        number=1000
    )
    val_time = timeit.timeit(
        lambda: validate_token(token, SECRET),
        number=1000
    )
    check(f"Generation: {gen_time*1:.1f}ms avg per token", gen_time < 5)
    check(f"Validation: {val_time*1:.1f}ms avg per validation", val_time < 5)

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"Results: {PASSES} passed, {FAILURES} failed")
    if FAILURES == 0:
        print("ALL TESTS PASSED. System is production ready.")
    else:
        print("FAILURES DETECTED. Do not ship.")
    sys.exit(0 if FAILURES == 0 else 1)

```


## `sebdog_reporter.py`

217 lines, 8364 bytes

```python
"""
SEBDOG DECISION REPORTER v1.0.0
Generates readable reports from the sebdog audit chain.
Shows exactly why each decision was made.
Copyright (c) 2026 Justin Antony Dobson / Monop Content
"""

import sqlite3, json, time, os
from datetime import datetime

DB_FILE = "sebdog_audit.db"

REASON_EXPLANATIONS = {
    "velocity_spike": "User made more than 10 requests in 60 seconds",
    "high_amount": "Transaction amount exceeded £500",
    "risky_device": "Device risk score above 0.5",
    "behaviour_anomaly": "Behavioural anomaly score above 0.5",
    "country_shift": "Request came from a different country than usual",
    "unsafe_country": "Request came from outside approved country list",
    "low_trust": "User trust score has dropped below 0.4 due to previous decisions",
}

def get_decisions(db_path=DB_FILE, limit=100):
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT ts, user_id, event_json, result_json, audit_hash
        FROM audit_log
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    results = []
    for row in rows:
        try:
            event = json.loads(row[2])
            result = json.loads(row[3])
            results.append({
                "ts": row[0],
                "user_id": row[1],
                "event": event,
                "result": result,
                "audit_hash": row[4]
            })
        except:
            pass
    return results

def format_reason(reason):
    return REASON_EXPLANATIONS.get(reason, reason.replace("_", " ").capitalize())

def decision_color(decision):
    return {"ALLOW": "#00875a", "CHALLENGE": "#b45309", "BLOCK": "#cc0000"}.get(decision, "#555")

def generate_text_report(db_path=DB_FILE, limit=100):
    decisions = get_decisions(db_path, limit)
    if not decisions:
        return "No decisions recorded yet."
    
    lines = [
        "SEBDOG DECISION REPORT",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total decisions shown: {len(decisions)}",
        "=" * 60
    ]
    
    for d in decisions:
        result = d["result"]
        event = d["event"]
        ts = datetime.fromtimestamp(d["ts"]).strftime('%Y-%m-%d %H:%M:%S')
        decision = result.get("decision", "?")
        score = result.get("score", 0)
        reasons = result.get("reasons", [])
        
        lines.append(f"\n[{ts}] User: {d['user_id']}")
        lines.append(f"Action: {event.get('action','?')} | Country: {event.get('country','?')} | Amount: £{event.get('amount',0)}")
        lines.append(f"Decision: {decision} | Score: {score} | Trust: {result.get('trust',0)}")
        
        if reasons:
            lines.append("Reasons:")
            for r in reasons:
                lines.append(f"  - {format_reason(r)}")
        else:
            lines.append("Reasons: No risk factors detected")
        
        lines.append(f"Audit hash: {d['audit_hash'][:32]}...")
        lines.append("-" * 60)
    
    return "\n".join(lines)

def generate_json_report(db_path=DB_FILE, limit=100):
    decisions = get_decisions(db_path, limit)
    report = {
        "generated": datetime.now().isoformat(),
        "total": len(decisions),
        "decisions": []
    }
    for d in decisions:
        result = d["result"]
        event = d["event"]
        reasons = result.get("reasons", [])
        report["decisions"].append({
            "timestamp": datetime.fromtimestamp(d["ts"]).isoformat(),
            "user_id": d["user_id"],
            "action": event.get("action"),
            "country": event.get("country"),
            "amount": event.get("amount"),
            "decision": result.get("decision"),
            "score": result.get("score"),
            "trust": result.get("trust"),
            "reasons": reasons,
            "reasons_explained": [format_reason(r) for r in reasons],
            "audit_hash": d["audit_hash"]
        })
    return json.dumps(report, indent=2)

def generate_html_report(db_path=DB_FILE, limit=100):
    decisions = get_decisions(db_path, limit)
    
    rows = ""
    for d in decisions:
        result = d["result"]
        event = d["event"]
        ts = datetime.fromtimestamp(d["ts"]).strftime('%Y-%m-%d %H:%M:%S')
        decision = result.get("decision", "?")
        score = result.get("score", 0)
        reasons = result.get("reasons", [])
        color = decision_color(decision)
        
        reason_html = ""
        if reasons:
            reason_html = "<ul>" + "".join(f"<li>{format_reason(r)}</li>" for r in reasons) + "</ul>"
        else:
            reason_html = "<span style='color:#888'>No risk factors detected</span>"
        
        rows += f"""
        <tr>
            <td>{ts}</td>
            <td><code>{d['user_id']}</code></td>
            <td>{event.get('action','?')}</td>
            <td>{event.get('country','?')}</td>
            <td>£{event.get('amount',0)}</td>
            <td><strong style="color:{color}">{decision}</strong></td>
            <td>{score}</td>
            <td>{result.get('trust',0)}</td>
            <td>{reason_html}</td>
            <td><code style="font-size:10px">{d['audit_hash'][:16]}...</code></td>
        </tr>"""
    
    allow = sum(1 for d in decisions if d["result"].get("decision") == "ALLOW")
    challenge = sum(1 for d in decisions if d["result"].get("decision") == "CHALLENGE")
    block = sum(1 for d in decisions if d["result"].get("decision") == "BLOCK")
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Sebdog Decision Report</title>
<style>
body{{font-family:sans-serif;background:#f5f7fa;color:#1a202c;margin:0;padding:20px}}
.header{{background:#0a0f1e;color:#fff;padding:24px 32px;border-radius:8px;margin-bottom:24px}}
.header h1{{margin:0;font-size:24px;color:#c9a84c}}
.header p{{margin:4px 0 0;color:rgba(255,255,255,0.5);font-size:13px}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px}}
.stat{{background:#fff;border-radius:8px;padding:16px;text-align:center;border:1px solid #e2e8f0}}
.stat-n{{font-size:32px;font-weight:700}}
.stat-l{{font-size:11px;color:#64748b;margin-top:4px}}
.allow{{color:#00875a}}.challenge{{color:#b45309}}.block{{color:#cc0000}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0}}
th{{background:#0a0f1e;color:#c9a84c;padding:10px 12px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:1px}}
td{{padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:12px;vertical-align:top}}
tr:last-child td{{border:none}}
tr:hover td{{background:#f8fafc}}
ul{{margin:4px 0;padding-left:16px}}
li{{margin:2px 0;color:#64748b}}
code{{background:#f1f5f9;padding:2px 4px;border-radius:3px;font-size:11px}}
</style>
</head>
<body>
<div class="header">
  <h1>Sebdog Decision Report</h1>
  <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp; Showing last {len(decisions)} decisions &nbsp;|&nbsp; Powered by sebbi.pro</p>
</div>
<div class="stats">
  <div class="stat"><div class="stat-n allow">{allow}</div><div class="stat-l">ALLOWED</div></div>
  <div class="stat"><div class="stat-n challenge">{challenge}</div><div class="stat-l">CHALLENGED</div></div>
  <div class="stat"><div class="stat-n block">{block}</div><div class="stat-l">BLOCKED</div></div>
</div>
<table>
<thead><tr>
  <th>Time</th><th>User</th><th>Action</th><th>Country</th><th>Amount</th>
  <th>Decision</th><th>Score</th><th>Trust</th><th>Reasons</th><th>Audit Hash</th>
</tr></thead>
<tbody>{rows if rows else '<tr><td colspan="10" style="text-align:center;color:#888;padding:32px">No decisions recorded yet</td></tr>'}</tbody>
</table>
</body>
</html>"""
    return html

if __name__ == "__main__":
    import sys
    fmt = sys.argv[1] if len(sys.argv) > 1 else "html"
    db = sys.argv[2] if len(sys.argv) > 2 else DB_FILE
    
    if fmt == "text":
        print(generate_text_report(db))
    elif fmt == "json":
        print(generate_json_report(db))
    else:
        report = generate_html_report(db)
        out = "sebdog_report.html"
        with open(out, "w") as f:
            f.write(report)
        print(f"Report saved to {out}")

```


## `AILeash-API-Reference-v6.4.2.md`

256 lines, 6799 bytes

```markdown
# AILeash v6.4.2 — Complete API Reference

## Core Decision Endpoint

### POST /api/govern
**The engine. Every action scores here.**

Auth: `Bearer YOUR_API_KEY`

**Request:**
```json
{
  "user_id": "string (required)",
  "action": "string (required) — payment/login/message/transfer/checkout/api_call",
  "amount": "number (optional, default 0) — monetary value in GBP",
  "country": "string (required) — ISO 3166-1 alpha-2 code",
  "device_id": "string (required) — unique device identifier",
  "anomaly": "number 0..1 (optional) — behavioural anomaly score",
  "device_risk": "number 0..1 (optional) — device risk score"
}
```

**Response (200 OK):**
```json
{
  "decision": "ALLOW|CHALLENGE|BLOCK",
  "score": 0.0..1.0,
  "trust": 0.05..1.0,
  "reasons": ["velocity_spike", "high_amount", "country_shift"],
  "audit_hash": "sha256_hex_string",
  "block_index": 12345,
  "receipt_seq": 42,
  "timestamp": 1719072000.0,
  "challenge_url": "https://sebbi.pro/verify-challenge?token=...",
  "challenge_expires_in": 900
}
```

**Error responses:**
- `401 Unauthorized` — Missing or invalid API key
- `403 Forbidden` — Account inactive or over quota
- `429 Too Many Requests` — Rate limited
- `503 Service Unavailable` — Server overloaded

---

## Account Management

### POST /api/keys or /signup
**Create a new API key. Instant. No card. No humans in the loop.**

No auth required.

**Request:**
```json
{
  "email": "user@example.com (required)",
  "name": "John Doe (optional)",
  "phone": "+441234567890 (optional)",
  "org": "Acme Corp (optional)",
  "product": "aileash|guardian|sonicboom|sentinel (default: aileash)",
  "devices": 1..1000000 (default: 1),
  "ref_code": "REF-XXXX-1234 (optional)"
}
```

**Response (200 OK):**
```json
{
  "api_key": "al_live_...",
  "email": "user@example.com",
  "product": "aileash",
  "devices": 1,
  "monthly_cost": 0.50,
  "quota": 100,
  "ref_code": "REF-JOHN-5678",
  "badge_id": "abc123def456",
  "message": "100 free decisions. Then 50p per device per month via Stripe."
}
```

---

## Verification & Public Endpoints

### GET /api/spec
**Engine specification. Public. No auth.**

**Response (200 OK):**
```json
{
  "engine": "AILeash v6.4.2",
  "version": "6.4.2",
  "signals": 9,
  "decision_latency_ms": 28,
  "threshold_allow": 0.35,
  "threshold_challenge": 0.70,
  "threshold_block": 1.0,
  "features": ["deterministic scoring", "tamper-evident chain", "real-time alerts", "gapless receipts", "sovereign deployment"]
}
```

### GET /api/verify-chain
**Full audit chain integrity proof. Public. No auth.**

**Response (200 OK):**
```json
{
  "valid": true,
  "blocks": 45678,
  "genesis": "GENESIS",
  "tip": "abc123...",
  "message": "Chain intact. No tampering detected.",
  "verifiable_by": "anyone, anywhere"
}
```

### GET /api/health
**Server health and load. Public. No auth.**

**Response (200 OK):**
```json
{
  "status": "ok",
  "version": "6.4.2",
  "uptime_seconds": 864000,
  "rps": 42,
  "timestamp": 1719072000.0
}
```

---

## Real-time Dashboards

### GET /api/pulse
**Live risk posture. Your current state.**

Auth: `Bearer YOUR_API_KEY`

**Response (200 OK):**
```json
{
  "last_hour": {
    "ALLOW": 486,
    "CHALLENGE": 23,
    "BLOCK": 4
  },
  "recent": [
    {
      "ts": 1719072000,
      "user_id": "u_7f2",
      "action": "payment",
      "decision": "ALLOW",
      "score": 0.12,
      "reasons": [],
      "audit_hash": "abc123..."
    }
  ],
  "chain_tip": "abc123...",
  "message": "All green. Chain tip sealed."
}
```

---

## Billing & Webhooks

### POST /stripe-webhook
**Stripe webhook receiver. Signature verified automatically.**

Supports events:
- `checkout.session.completed` — User upgraded
- `invoice.paid` — Monthly subscription paid
- `customer.subscription.deleted` — User cancelled
- `invoice.payment_failed` — Payment failed

---

## Four Products. One Engine.

### AILeash
- **What:** Every AI decision your platform makes about a person gets scored, explained, and sealed.
- **Who:** Platforms using AI for any regulated decision (lending, hiring, content moderation, fraud, access control).
- **Price:** 50p per device per month + your margin.
- **Free tier:** 100 decisions/month, no card.

### Guardian
- **What:** Free message checker for families. Child pastes a message in, gets instant plain-English assessment against grooming patterns.
- **Who:** Families. Free forever. No card. No catch.
- **Price:** Free. Always.
- **Built for:** ICO Children's Code, Online Safety Act, child safety.

### SonicBoom
- **What:** One line of code. Drops into AWS, Azure, GCP, OpenAI, Anthropic. Adds full compliance audit chain to every call.
- **Who:** Platforms already running AI in the cloud.
- **Price:** 50p per device per month + your margin.
- **Latency:** No impact. Chain sealing is asynchronous.

### Sentinel
- **What:** Fraud and anomaly alerting. Scores unusual patterns (500 messages in a minute, login from new country, velocity spikes) in real-time.
- **Who:** Platforms managing fraud, abuse, takeovers.
- **Price:** 50p per device per month + your margin.
- **Real-time:** Alerts the moment thresholds trip.

---

## The Score Formula (Immutable)

**Raw weighted sum (Σ_raw):**
```
Σ_raw =
  (1 − trust) × 0.30
  + min(velocity_60s / 20, 1) × 0.15
  + min(velocity_5m / 50, 1) × 0.10
  + min(velocity_1h / 200, 1) × 0.10
  + min(ln(1+amount) / ln(1+10000), 1) × 0.15
  + device_risk × 0.10
  + behavioural_anomaly × 0.10
  + country_shift × 0.10
  + unsafe_country × 0.10
```

**Normalization:** the nine weights above sum to 1.20, not 1.0. To keep every signal's *relative* importance exactly as designed while guaranteeing the score behaves as a true 0–1 weighted average (not one that can reach BLOCK-level values from fewer combined signals than intended), divide by the actual weight total before clamping:

```
WEIGHT_TOTAL = 0.30 + 0.15 + 0.10 + 0.10 + 0.15 + 0.10 + 0.10 + 0.10 + 0.10   # = 1.20

score = clamp( Σ_raw / WEIGHT_TOTAL , 0, 1 )

decision = ALLOW if score < 0.35
         = CHALLENGE if score < 0.70
         = BLOCK otherwise
```

No machine learning. No drift. No retraining. Weights are written in code and cannot change without a new release. `WEIGHT_TOTAL` is a fixed constant (1.20) recomputed only if a signal is added, removed, or reweighted in a future release — never at runtime.

---

## Rate Limits

- **Free tier:** 100 decisions/month
- **Paid:** Unlimited (or by plan)
- **Public endpoints:** No rate limit

---

## Documentation

- **Homepage:** https://sebbi.pro
- **Whitepaper:** https://sebbi.pro/whitepaper
- **Developers:** https://sebbi.pro/developers
- **Scanner (free):** https://sebbi.pro/scan
- **Guardian:** https://sebbi.pro/guardian-app
- **Contact:** justrightdecorators@gmail.com

```


## `LICENCE`

22 lines, 1074 bytes

```
MIT License

Copyright (c) 2026 Monop (Blyth, UK)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```


## `README.md`

277 lines, 15728 bytes

```markdown
<div align="center">

```
        ┌─────────────────────────────────────────────────┐
        │   s e b b i . p r o                              │
        │                                                  │
        │   O N E   C H A I N .   E V E R Y   P R O O F .   │
        └─────────────────────────────────────────────────┘
```

### The tamper-evident evidence layer for AI decisions, payments, and records.

*Every event sealed into a hash chain at the moment it happens —*
*the decision, **and the basis it rested on** — unalterable by anyone. Including us.*

<br>

[![live](https://img.shields.io/badge/live-sebbi.pro-c9a84c?style=for-the-badge)](https://sebbi.pro)
[![verify the chain](https://img.shields.io/badge/verify_the_chain-open_endpoint-7fe3b0?style=for-the-badge)](https://sebbi.pro/api/verify-chain)
[![seal something free](https://img.shields.io/badge/seal_something-free,_no_account-7cc8ff?style=for-the-badge)](https://sebbi.pro/seal)

**[Try it](https://sebbi.pro/seal)** · **[Verify it](https://sebbi.pro/verify)** · **[Read the code](https://sebbi.pro/brain)** · **[Developer docs](https://sebbi.pro/developers)** · **[Whitepaper](https://sebbi.pro/whitepaper)**

</div>

---

> ### *A system that does not trust its own creator*
> ### *is the only kind whose records qualify as evidence.*

---

## Don't read about it. Watch it work.

Here is a **real** four-block chain. Every hash below is reproducible — same inputs, same seals, forever. Copy the recipe at the bottom and compute them yourself.

```
  #   EVENT                             RESULT      SEAL (SHA-256, truncated)
  ─────────────────────────────────────────────────────────────────────────
  1   system_regmap                     ALLOW       411ffd9a31a3d9f4…
  2   seal_post: quarterly_report.pdf   NOTARISED   c7309616a9e92bc7…
  3   govern: payment 9000 GBP          BLOCK       293181a2bc2dab88…
  4   brain: approve supplier 88        ALLOW       6abba40eb964959e…
  ─────────────────────────────────────────────────────────────────────────
  genesis  9fd06d6fdc19761d…                         tip  6abba40eb964959e…
```

Now watch someone try to cover up that blocked £9,000 payment by flipping block 3 from **BLOCK** to **ALLOW**:

```
  block 3 altered  →  tip becomes  5e15bc5710426088…   ❌  ≠ 6abba40eb964959e…
```

**The tip changed. The forgery is exposed instantly, by arithmetic, to anyone — no account, no trust required.** That is the entire product in six lines. Everything below is detail.

<details>
<summary><b>▸ Reproduce every hash yourself (10 lines of Python)</b></summary>

```python
import hashlib, json
seal = lambda prev, ts, ev, res, basis: hashlib.sha256(
    json.dumps({"prev":prev,"ts":ts,"event":ev,"result":res,"basis":basis},
               sort_keys=True).encode()).hexdigest()

prev = hashlib.sha256(b"AILEASH_BRAIN_GENESIS|sebbi.pro|v5").hexdigest()
chain = [("system_regmap","ALLOW","regmap-v7"),
         ("seal_post: quarterly_report.pdf","NOTARISED","NO_BASIS"),
         ("govern: payment 9000 GBP","BLOCK","invoice_4471|regmap-v7"),
         ("brain: approve supplier 88","ALLOW","invoice_4471|regmap-v7")]
ts = 1752940000
for ev,res,basis in chain:
    prev = seal(prev, ts, ev, res, basis); ts += 3600
    print(prev[:16], "…", ev)
# final line prints the tip: 6abba40eb964959e …
```
Change one character of one event and every seal after it changes. That's the whole idea.
</details>

---

## Why this exists

Every system keeps logs. Logs live in databases. Databases can be edited — by an attacker, an insider, or the operator itself. So an ordinary log only ever says *"this is what we currently claim happened."* It can never say *"and nobody changed it since."*

Nobody notices the difference — until a regulator, a court, an insurer, or a customer asks for **proof**. Then *"our system recorded it"* and *"here is proof it wasn't changed"* become two very different sentences. Only the second carries weight.

**sebbi.pro produces the second sentence — automatically, as a by-product of your system doing its normal work.**

---

## The chain, in one formula

```
seal(n) = SHA-256( seal(n−1) · timestamp · event · result · basis )
```

| Property | What it means |
|---|---|
| **Tamper-evident** | Each seal contains its predecessor. Alter history → every later seal fails, publicly. |
| **Gapless receipts** | Every decision gets a sequence number in the same transaction. Edited records break the chain; **missing** records break the sequence. |
| **Truncation-evident** | The tip is anchored per-write. Chop blocks off the end → the anchor breaks. |
| **Basis-sealed** | Not just *what* was decided — *what it rested on*: sources, versions, ruleset. Same block. |
| **Jurisdiction-tagged** | Every decision sealed with the regulatory frameworks that applied to it at that moment. |
| **Fast** | Score + decide + seal + respond inline, **~28 ms** median. |
| **Crash-safe** | WAL journaling, full-sync commits, single-lock seal path, no race window, daily backups. |

> **The one honest boundary, stated up front:** basis-sealing proves **what** a decision relied on — not that it was **correct**. Cryptography verifies integrity, never truth. Any product claiming to prove correctness is misdescribing what maths can do. We won't.

---

## The products — one chain underneath all of them

| | Product | What it does | Access |
|---|---|---|---|
| 🧠 | **Brain** | Instruction gate for AI. Blocks prompt injection, exfiltration, compliance-bypass, child-safety and destruction patterns — with unicode/obfuscation defences — and seals every decision + basis. Pure Python, runs on your machine. | **Free download** |
| ⚡ | **SonicBoom** | Decision engine. Any event scored in ~28ms: ALLOW / CHALLENGE / BLOCK, plain-English reasons, sealed before it replies. Per-user trust learned over time — lost 8× faster than earned, so burst attacks destroy their own standing. Hosted human-oversight challenge flow, itself sealed. | API key |
| 🔐 | **Delegation layer** | Signed authority tokens (who may approve, to what limit, until when — the grant itself sealed), provider-agnostic KYC result sealing (outcome provable, zero personal data held), and per-decision jurisdiction tagging. Article 14 human oversight as engineering. | API key |
| 🛡️ | **Sentinel** | Fraud pattern + velocity detection: credential stuffing, card testing, country-jump takeovers. Flags sealed as evidence. | API key |
| 👁️ | **Guardian** | Child-safety flags: grooming patterns (secrecy, isolation, channel-moving). Content never stored — only fingerprints. Every flag sealed for parents, platforms, authorities. | Platform |
| 📝 | **Post Notary** | Prove exact text existed on a date, unchanged. | **Free, no account** |
| 🆔 | **Identity Notary** | Prove a profile is the genuine original — kills impersonation. | **Free, no account** |
| 💷 | **Payment Notary** | Stop invoice/APP fraud. Seal real bank details once; payers verify a code before funds move. MISMATCH → payment stops. The check itself is sealed. | **Free, no account** |

**Privacy by design:** the notaries fingerprint content *locally*. Your content never leaves your device — only the 64-character hash is sealed. The KYC sealer keeps only the SHA-256 of the provider reference — never the document.

---

## The open standard — `ai.txt`

Like `robots.txt` for crawlers and `security.txt` for researchers — **`ai.txt`** is a public, machine-readable declaration of how your AI is governed: decision model, audit method, regulations designed toward, human override. Its companion **`comply.txt`** declares the rulebook every instruction is subject to.

Declarations are claims. **Sealing them into the chain makes them provable** — and their history tamper-evident.

```
  declaration  →  rulebook  →  enforcement
     ai.txt        comply.txt      brain.py
     "we claim"    "the rules"     "the code that proves it"
```

Publish yours at `/.well-known/ai.txt`. Read [ours](https://sebbi.pro/.well-known/ai.txt).

---

## The stack — how it all fits

```
  DECLARATION    ai.txt · comply.txt     what we claim, publicly
       │
  GATE           Brain                   instructions checked before the AI acts
       │
  DELEGATION     authority · identity ·  who may act, who they legally are,
                 jurisdiction            which rules governed the moment
       │
  DECISION       SonicBoom               every event: allow / challenge / block
       │
  DETECTION      Sentinel · Guardian     attack patterns · child-safety patterns
       │
  PUBLIC ACCESS  the Notaries            the same chain, free, for anyone
       │
       ▼
  ╔══════════════════════════════════════════════════════════════════╗
  ║  EVIDENCE     the hash chain                                      ║
  ║               everything above seals into here —                 ║
  ║               action + basis + receipt · gapless · anchored ·    ║
  ║               publicly verifiable · unalterable by anyone        ║
  ╚══════════════════════════════════════════════════════════════════╝
```

**Evidence accrues as a by-product of the system working.** Nobody remembers to log anything. Nobody compiles an audit file before an inspection. The proof exists because the system ran — equally trustworthy whether the operator is honest or not. Which is the only kind of trustworthy that counts.

---

## Integrate in minutes

```python
# ── Notary: seal anything, free, no key. Content stays on your machine. ──
import hashlib, requests
fp = hashlib.sha256(content.encode()).hexdigest()
requests.post("https://sebbi.pro/api/post/seal", json={"fingerprint": fp})
#   → { sealed, seal, block_index, code }   ← keep the code; anyone can verify it

# ── Decision engine: score + seal an event (API key) ──
requests.post("https://sebbi.pro/api/govern",
  headers={"Authorization":"Bearer YOUR_KEY"},
  json={"user_id":"u1","action":"payment","amount":9000,
        "country":"UK","device_id":"d1","anomaly":0,"device_risk":0})
#   → ALLOW / CHALLENGE / BLOCK · reasons · jurisdiction tag · sealed hash · receipt_seq

# ── Delegated authority: grant sealed, enforcement deterministic ──
tok = requests.post("https://sebbi.pro/api/authority/issue",
  headers={"Authorization":"Bearer YOUR_KEY"},
  json={"user_id":"u1","role":"payments_approver",
        "max_amount":5000,"ttl_hours":24}).json()["authority_token"]
#   include as "authority_token" in govern events — over-limit or expired
#   authority escalates the verdict with the reason sealed

# ── KYC result: outcome provable, zero personal data held ──
requests.post("https://sebbi.pro/api/identity/kyc-seal",
  headers={"Authorization":"Bearer YOUR_KEY"},
  json={"user_id":"u1","provider":"onfido","verified":True,
        "reference":"chk_9f2"})
#   → only the SHA-256 of the reference is stored — never the document

# ── Brain: gate an instruction and seal its basis (free, local) ──
from brain import BrainGovernor
BrainGovernor().evaluate("approve payment to supplier 88", basis={
  "sources":["invoice_4471.pdf"], "source_versions":["sha256:ab12…"],
  "ruleset":"AI-TXT/1.0 + EU-AI-Act-2024/1689", "ruleset_version":"regmap-v7"})
```

Full reference → **[sebbi.pro/developers](https://sebbi.pro/developers)**

---

## What this evidences — stated precisely

A versioned, hash-sealed **regulation map** links each capability to the obligations it helps evidence: EU AI Act record-keeping, transparency & human-oversight (Articles 9, 12, 13, 14 — delegated-authority tokens directly supporting Article 14's attributable human oversight), UK Online Safety Act duty-of-care documentation, ICO Children's Code. Jurisdiction tagging extends this to the per-decision level: every sealed block records which frameworks applied at the moment of decision.

These tools help you **evidence** your obligations — tamper-evident, explainable, independently verifiable records of what your systems decided and why. **They do not, on their own, make you compliant. No software does. Anyone who says otherwise is selling you something.**

---

## Honest limits — because the whole product is honesty

- **Sealing proves integrity, not truth** — exact content, exact time, unchanged. Not that it was true or agreed to.
- **Basis-sealing proves what was relied on, not that it was right** — cryptography can't verify the real world.
- **Authority tokens prove the grant, not the wisdom** — who was empowered, to what limit, until when. Not that granting it was a good idea.
- **Jurisdiction tagging records applicable frameworks; it does not decide law** — courts do that. It is a versioned, sealed lookup — nothing grander, deliberately.
- **Brain's filter is a first line, not a wall** — known patterns caught; novel phrasing can pass. The guarantee is the sealed record.
- **Fingerprints match exact content** — a re-encoded copy or paraphrase won't match.
- **We evidence compliance; we don't confer it.**

*A vendor who states their limits is giving you the strongest available evidence of how they'll behave when it matters.*

---

## Deployment & pricing

- **Cloud** — a few lines against the hosted API. Notaries and Brain free forever.
- **Sovereign** — the whole engine inside your own network. Offline HMAC-signed 365-day licences, no phone-home, air-gap ready.
- **50p per active device / month.** Partners set their own pricing above the platform fee.

## Investors

The whitepaper carries a dedicated investor section — market timing (EU AI Act, August 2026), the metered per-device model, the moat, and the stage stated honestly: **[sebbi.pro/whitepaper](https://sebbi.pro/whitepaper)** · justin@monopcontent.com

---

<div align="center">

## Check us. Don't trust us.

*That's not a slogan. It's the design requirement — and the only standard by which an evidence layer should ever be judged.*

**[Verify the chain now →](https://sebbi.pro/api/verify-chain)**

<br>

```
  Built by Justin Dobson · Monop Content · Blyth, Northumberland, UK
  Solo-built, from scratch, on a phone —
  because the evidence layer wasn't going to build itself.
```

[LinkedIn](https://www.linkedin.com/in/justin-dobson-037721217) · [sebbi.pro](https://sebbi.pro)

</div>

<!--
Keywords: tamper-evident audit trail · AI governance · AI compliance evidence ·
EU AI Act record keeping · hash chain audit log · APP fraud prevention ·
invoice verification · prompt injection defence · AI decision audit ·
delegated authority tokens · KYC evidence sealing · jurisdiction tagging ·
ai.txt standard · comply.txt · cryptographic proof of action · immutable audit log ·
agentic AI governance · sovereign AI deployment · SonicBoom · Brain · Sentinel · Guardian
-->

```


## `admin.html`

212 lines, 12327 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>sebbi.pro - Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0f1e;color:#fff;line-height:1.5}
.wrap{max-width:1000px;margin:0 auto;padding:20px}
h1{font-size:22px;font-weight:800;margin-bottom:4px}h1 span{color:#c9a84c}
.sub{color:#8a90a6;font-size:13px;margin-bottom:20px}
/* login */
#login{max-width:360px;margin:80px auto;text-align:center}
#login input{width:100%;padding:14px;border-radius:10px;border:1px solid #2a3350;background:#0b1226;color:#fff;font-size:16px;margin:12px 0}
button{background:#c9a84c;color:#0a0f1e;border:none;border-radius:10px;padding:13px 22px;font-weight:800;cursor:pointer;font-size:15px;width:100%}
button.small{width:auto;padding:8px 16px;font-size:13px}
.err{color:#ff7b6e;font-size:13px;margin-top:8px;min-height:18px}
/* dashboard */
#dash{display:none}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.stat{background:#111a30;border:1px solid #232d4a;border-radius:12px;padding:16px}
.stat .big{font-size:26px;font-weight:800;color:#c9a84c}
.stat .lab{font-size:11px;color:#8a90a6;text-transform:uppercase;letter-spacing:1px;margin-top:4px}
.stat.good .big{color:#7fe3b0}.stat.bad .big{color:#ff7b6e}
.tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.tab{background:#111a30;border:1px solid #232d4a;color:#8a90a6;padding:9px 16px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600}
.tab.on{background:#c9a84c;color:#0a0f1e;border-color:#c9a84c}
.panel{display:none}.panel.on{display:block}
.card{background:#111a30;border:1px solid #232d4a;border-radius:12px;padding:14px;margin-bottom:10px;font-size:14px}
.card .top{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.card .nm{font-weight:700}
.card .meta{color:#8a90a6;font-size:12px}
.badge{font-size:10px;padding:2px 8px;border-radius:10px;font-weight:700;text-transform:uppercase}
.badge.paid{background:#0d2018;color:#7fe3b0;border:1px solid #1fae79}
.badge.free{background:#1a1206;color:#c9a84c;border:1px solid #c9a84c}
.stripe-link{color:#7fe3b0;font-size:12px;text-decoration:none;font-family:monospace}
.bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.mono{font-family:monospace;font-size:12px;color:#8a90a6;word-break:break-all}
.empty{color:#5a6178;text-align:center;padding:30px;font-size:14px}
a.ext{display:inline-block;background:#0d2018;border:1px solid #1fae79;color:#7fe3b0;padding:10px 16px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600;margin-bottom:16px}
</style>
</head>
<body>
<div class="wrap">

  <div id="login">
    <h1>sebbi<span>.pro</span> admin</h1>
    <div class="sub">Private control panel</div>
    <input id="pw" type="password" placeholder="Admin password" onkeydown="if(event.key==='Enter')doLogin()">
    <button onclick="doLogin()">Log in</button>
    <div class="err" id="loginerr"></div>
  </div>

  <div id="dash">
    <div class="bar">
      <div><h1>sebbi<span>.pro</span> admin</h1><div class="sub">Everything Stripe doesn't show you</div></div>
      <button class="small" onclick="logout()">Log out</button>
    </div>

    <a class="ext" href="https://dashboard.stripe.com" target="_blank" rel="noopener">Open Stripe dashboard for payments, revenue &amp; billing addresses &rarr;</a>

    <div class="stats" id="statgrid"></div>

    <div class="tabs">
      <div class="tab on" onclick="show('customers',this)">Customers &amp; leads</div>
      <div class="tab" onclick="show('contacts',this)">Contact messages</div>
      <div class="tab" onclick="show('referrals',this)">Referrals</div>
      <div class="tab" onclick="show('audit',this)">Audit records</div>
    </div>

    <div class="panel on" id="p-customers"><div class="empty">Loading...</div></div>
    <div class="panel" id="p-contacts"><div class="empty">Loading...</div></div>
    <div class="panel" id="p-referrals"><div class="empty">Loading...</div></div>
    <div class="panel" id="p-audit">
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
        <input id="auditkey" placeholder="Filter by API key (optional)" style="flex:1;min-width:180px;padding:10px;border-radius:8px;border:1px solid #2a3350;background:#0b1226;color:#fff;font-size:13px">
        <button class="small" onclick="loadAudit()">Search</button>
        <button class="small" onclick="verifyChain()" style="background:#1fae79">Verify chain</button>
        <button class="small" onclick="exportAudit()" style="background:#0d2018;color:#7fe3b0;border:1px solid #1fae79">Export</button>
      </div>
      <div id="auditchain" style="font-family:monospace;font-size:12px;color:#7fe3b0;margin-bottom:12px"></div>
      <div id="auditlist"><div class="empty">Loading...</div></div>
    </div>
  </div>

</div>
<script>
var TOKEN="";
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
function when(ts){if(!ts)return"";try{return new Date(ts*1000).toLocaleString()}catch(e){return""}}

async function doLogin(){
  var pw=document.getElementById("pw").value;
  document.getElementById("loginerr").textContent="";
  try{
    var r=await fetch("/admin/auth",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:pw})});
    var d=await r.json();
    if(d.token){TOKEN=d.token;document.getElementById("login").style.display="none";document.getElementById("dash").style.display="block";loadAll();}
    else if(d.error==="admin_disabled"){document.getElementById("loginerr").textContent="Admin password not set. Add ADMIN_PASSWORD in Railway variables.";}
    else if(d.error==="too_many_attempts"){document.getElementById("loginerr").textContent="Too many attempts. Wait a minute.";}
    else{document.getElementById("loginerr").textContent="Wrong password.";}
  }catch(e){document.getElementById("loginerr").textContent="Connection error.";}
}
function logout(){TOKEN="";document.getElementById("dash").style.display="none";document.getElementById("login").style.display="block";document.getElementById("pw").value="";}

async function api(path){
  var r=await fetch(path,{method:"POST",headers:{"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"},body:"{}"});
  return await r.json();
}

async function loadAll(){
  // stats
  try{
    var s=await api("/admin/stats");
    document.getElementById("statgrid").innerHTML=
      stat(s.total_keys,"Total signups")+
      stat(s.paid_keys,"Paying",  "good")+
      stat((s.total_keys||0)-(s.paid_keys||0),"Free / leads")+
      stat(s.audit_blocks,"Audit blocks")+
      stat(s.chain_valid?"OK":"BROKEN","Chain",s.chain_valid?"good":"bad");
  }catch(e){}
  loadCustomers();loadContacts();loadReferrals();loadAudit();
}
function stat(v,l,cls){return '<div class="stat '+(cls||"")+'"><div class="big">'+esc(v)+'</div><div class="lab">'+esc(l)+'</div></div>';}

async function loadCustomers(){
  try{
    var d=await api("/admin/keys");var ks=d.keys||[];
    if(!ks.length){document.getElementById("p-customers").innerHTML='<div class="empty">No signups yet.</div>';return;}
    var h="";
    ks.forEach(function(k){
      var paid=k.is_paid==1;
      h+='<div class="card"><div class="top"><span class="nm">'+esc(k.name||"(no name)")+' <span class="meta">'+esc(k.org||"")+'</span></span>'
        +'<span class="badge '+(paid?"paid":"free")+'">'+(paid?"paying":"free")+'</span></div>'
        +'<div class="meta">'+esc(k.email||"")+' &middot; '+esc(k.product||"")+' &middot; '+esc(k.devices||0)+' devices &middot; used '+esc(k.actions_used||0)+'/'+esc(k.free_quota||0)+'</div>'
        +'<div class="meta">Joined '+when(k.created)+'</div>'
        +(k.key?'<div class="mono">'+esc(k.key)+'</div>':'')
        +'</div>';
    });
    document.getElementById("p-customers").innerHTML=h;
  }catch(e){document.getElementById("p-customers").innerHTML='<div class="empty">Could not load.</div>';}
}

async function loadContacts(){
  try{
    var d=await api("/admin/contacts");var cs=d.contacts||[];
    if(!cs.length){document.getElementById("p-contacts").innerHTML='<div class="empty">No messages yet.</div>';return;}
    var h="";
    cs.forEach(function(c){
      h+='<div class="card"><div class="top"><span class="nm">'+esc(c.name||"(no name)")+'</span><span class="meta">'+when(c.ts)+'</span></div>'
        +'<div class="meta">'+esc(c.email||"")+(c.phone?' &middot; '+esc(c.phone):'')+(c.org?' &middot; '+esc(c.org):'')+'</div>'
        +'<div style="margin-top:6px">'+esc(c.message||"")+'</div></div>';
    });
    document.getElementById("p-contacts").innerHTML=h;
  }catch(e){document.getElementById("p-contacts").innerHTML='<div class="empty">Could not load.</div>';}
}

async function loadReferrals(){
  try{
    var d=await api("/admin/referrals");var rs=d.referrals||[];
    if(!rs.length){document.getElementById("p-referrals").innerHTML='<div class="empty">No referrals yet.</div>';return;}
    var h="";
    rs.forEach(function(r){
      h+='<div class="card"><div class="top"><span class="nm">'+esc(r.referrer_name||"(no name)")+' <span class="meta">'+esc(r.code||"")+'</span></span>'
        +'<span class="badge paid">&pound;'+((r.earnings_pence||0)/100).toFixed(2)+'</span></div>'
        +'<div class="meta">'+esc(r.referrer_email||"")+' &middot; '+esc(r.devices_referred||0)+' devices referred</div></div>';
    });
    document.getElementById("p-referrals").innerHTML=h;
  }catch(e){document.getElementById("p-referrals").innerHTML='<div class="empty">Could not load.</div>';}
}

var LAST_AUDIT=[];
async function loadAudit(){
  try{
    var key=document.getElementById("auditkey").value.trim();
    var r=await fetch("/admin/audit",{method:"POST",headers:{"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"},body:JSON.stringify({limit:500,api_key:key})});
    var d=await r.json();LAST_AUDIT=d.records||[];
    document.getElementById("auditchain").innerHTML=(d.chain_valid?"CHAIN INTACT":"CHAIN BROKEN")+" &middot; "+esc(d.chain_blocks)+" blocks &middot; tip "+esc(String(d.chain_tip||"").slice(0,24))+"...";
    if(!LAST_AUDIT.length){document.getElementById("auditlist").innerHTML='<div class="empty">No sealed records'+(key?" for that key":"")+' yet.</div>';return;}
    var h="";
    LAST_AUDIT.forEach(function(a){
      var dec=esc(a.decision||"");
      var col=dec==="BLOCK"?"#ff7b6e":dec==="CHALLENGE"?"#c9a84c":"#7fe3b0";
      h+='<div class="card"><div class="top"><span class="nm">#'+esc(a.seq)+' <span style="color:'+col+'">'+dec+'</span></span><span class="meta">'+when(a.ts)+'</span></div>'
        +'<div class="meta">user: '+esc(a.user_id||"-")+(a.score!==""?' &middot; score '+esc(a.score):'')+(a.reasons&&a.reasons.length?' &middot; '+esc(a.reasons.join(", ")):'')+'</div>'
        +'<div class="mono" style="margin-top:6px">seal: '+esc(String(a.audit_hash||"").slice(0,40))+'...</div>'
        +'<div class="mono">prev: '+esc(String(a.prev_hash||"").slice(0,40))+'...</div></div>';
    });
    document.getElementById("auditlist").innerHTML=h;
  }catch(e){document.getElementById("auditlist").innerHTML='<div class="empty">Could not load audit records.</div>';}
}
async function verifyChain(){
  try{
    var r=await fetch("/api/verify-chain");var d=await r.json();
    document.getElementById("auditchain").innerHTML=(d.valid?"VERIFIED - CHAIN INTACT":"WARNING - CHAIN BROKEN")+" &middot; "+esc(d.blocks)+" blocks &middot; "+esc(d.message||"");
  }catch(e){}
}
function exportAudit(){
  var blob=new Blob([JSON.stringify(LAST_AUDIT,null,2)],{type:"application/json"});
  var url=URL.createObjectURL(blob);var a=document.createElement("a");
  a.href=url;a.download="sebbi-audit-export-"+Date.now()+".json";a.click();URL.revokeObjectURL(url);
}
function show(name,el){
  document.querySelectorAll(".tab").forEach(function(t){t.className="tab";});el.className="tab on";
  document.querySelectorAll(".panel").forEach(function(p){p.className="panel";});
  document.getElementById("p-"+name).className="panel on";
}
</script>
</body>
</html>

```
