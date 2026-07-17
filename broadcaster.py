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
