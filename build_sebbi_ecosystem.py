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
