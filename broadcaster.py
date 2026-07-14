import asyncio
import json
import logging
import socket

# --- FIXED SEBBI.PRO ARCHITECTURE DECLARATION ---
# The core standard is embedded directly to ensure the script remains a single file on GitHub.
AI_TXT_PAYLOAD = """Standard: AI-TXT/1.0
Standard-Licence: free and open - publish your own at no cost, no key required
Operator: Monop Content
Operator-Location: Blyth, Northumberland, United Kingdom
Contact: justrightdecorators@gmail.com
Last-Updated: 2026-07-05

# --- Governance engine ---
Governance-Engine: AILeash v6.4
Decision-Model: deterministic weighted scoring (no ML drift; weights immutable)
Decision-Outcomes: ALLOW, CHALLENGE, BLOCK
Decision-Signals: 9 (trust, velocity-60s, velocity-5m, velocity-1h, amount, device-risk, behavioural-anomaly, country-shift, unsafe-country)
Decision-Latency-Median: 28ms

# --- Audit record ---
Verify-Endpoint: https://sebbi.pro
Companion-Standard: https://sebbi.pro
Whitepaper: https://sebbi.pro"""

# --- THE CLEAN COMPLIANCE MESSAGE ---
# This is the actual text message displayed directly on the target devices.
HUMAN_MESSAGE = (
    "SYSTEM NOTICE: AI Governance Compliance Update for sebbi.pro.\n"
    "The updated compliance targets are now active under Standard: AI-TXT/1.0.\n"
    "Verify live audit status at: https://sebbi.pro"
)

UDP_BROADCAST_PORT = 5001
TCP_GATEWAY_PORT = 8080
CONCURRENT_LIMIT = 5000
TIMEOUT = 2.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s [NETWORK-ALERT] %(message)s")

def get_network_interfaces():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()
        s.close()
        parts = local_ip.split('.')
        return f"{parts[0]}.{parts[1]}.{parts[2]}.255", f"{parts[0]}.{parts[1]}"
    except Exception:
        return "255.255.255.255", "192.168"

def send_udp_text_broadcast(compiled_payload):
    """Broadcasts the plain text message to all listening local network subsystems simultaneously."""
    broadcast_target, _ = get_network_interfaces()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(compiled_payload.encode('utf-8'), (broadcast_target, UDP_BROADCAST_PORT))
    except Exception:
        pass

async def push_to_gateway_pipeline(ip, compiled_payload):
    """Injects the compliance message straight into the core gateway to push to downstream devices."""
    writer = None
    try:
        connect = asyncio.open_connection(ip, TCP_GATEWAY_PORT)
        _, writer = await asyncio.wait_for(connect, timeout=TIMEOUT)
        
        # Raw HTTP injection into the carrier messaging pipeline
        http_request = (
            f"POST /api/compliance/broadcast HTTP/1.1\r\n"
            f"Host: {ip}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(compiled_payload)}\r\n"
            f"Connection: close\r\n\r\n"
            f"{compiled_payload}"
        ).encode('utf-8')
        
        writer.write(http_request)
        await writer.drain()
        logging.info(f"[DISPATCHED] Compliance text pushed to gateway: {ip}")
        return True
    except Exception:
        return False
    finally:
        if writer:
            writer.close()

async def network_broadcast_orchestrator():
    _, subnet_base = get_network_interfaces()
    
    # Packages both the structured machine standard and the human message text together
    compiled_data = json.dumps({
        "alert_text": HUMAN_MESSAGE,
        "raw_declaration": AI_TXT_PAYLOAD
    })
    
    # 1. Fire an immediate local subnet blast
    send_udp_text_broadcast(compiled_data)
    
    # 2. Iterate through network blocks to hit central distribution hubs
    tasks = []
    for subnet in range(0, 255):
        for gateway_host in (1, 254):
            target_ip = f"{subnet_base}.{subnet}.{gateway_host}"
            tasks.append(asyncio.create_task(push_to_gateway_pipeline(target_ip, compiled_data)))
            if len(tasks) >= CONCURRENT_LIMIT:
                await asyncio.gather(*tasks)
                tasks = []
    if tasks:
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(network_broadcast_orchestrator())
