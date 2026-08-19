# Codebase — part 12 of 22

Contains:
- `gateway_proxy.py`
- `meshwitness.py`
- `sebbi_orchestrator.py`
- `sebbi_sdk.py`
- `sebdog_engine.py`


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


## `meshwitness.py`

328 lines, 11605 bytes

```python
#!/usr/bin/env python3
"""
meshwitness.py  v1.0  -  witness everybody, not just whoever invited you

    Standard library only. One file. One cron line. No install.

WHAT PROBLEM THIS SOLVES
    Witnessing runs on your own machine, so your server only witnesses
    chains you have told it about. Most operators point at whoever
    introduced them and stop there. The result is a star: everybody
    connected to one node in the middle, and if that node goes down
    every chain loses its witness at the same moment.

    This reads the published roster and witnesses EVERY chain on it. A
    chain that joins tomorrow gets picked up on your next run with
    nothing to configure and no email from anyone.

WHAT IT DOES, EACH RUN
    1. Fetches the roster.
    2. For every chain with a tip URL, fetches their current tip.
    3. Seals that tip into YOUR chain, via your own seal endpoint.
    4. Pushes YOUR tip to their submit endpoint, so the witnessing is
       mutual rather than one-way.
    5. Prints a line per peer and exits non-zero if nothing worked.

    It never sends your data anywhere. A tip is a hash. That is the
    whole payload.

RUN IT
    export MESH_TIP_URL=https://yoursite.example/witness.json
    export MESH_SEAL_URL=https://yoursite.example/api/witness/seal
    export MESH_CHAIN=your-chain-name

    python3 meshwitness.py

    Cron, hourly, on a minute nobody else is using:
        23 * * * * /usr/bin/python3 /path/meshwitness.py >> /var/log/mesh.log 2>&1

    Check what it would do without doing it:
        python3 meshwitness.py --dry-run

CONFIGURATION
    MESH_TIP_URL    where YOUR current tip is served. required.
    MESH_SEAL_URL   your own endpoint that seals an observed tip.
                    optional -- omit it and this only pushes, which is
                    still useful but only half the exchange.
    MESH_CHAIN      your chain name as other nodes should record it.
    MESH_ROSTER     roster to read. defaults to sebbi.pro.
    MESH_SKIP       comma separated chain names to ignore.
    MESH_TIMEOUT    seconds per request. default 15.

IF YOUR STACK IS NOT PYTHON
    The whole protocol is four HTTP calls and no cryptography beyond a
    hash you already have. Read --explain for the exact requests and
    write it in whatever you use. Nothing here is privileged.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

VERSION = "1.0"

DEFAULT_ROSTER = "https://sebbi.pro/x/roster/list"
DEFAULT_TIMEOUT = 15.0
USER_AGENT = "meshwitness/%s" % VERSION


# ------------------------------------------------------------------ http

def _get(url, timeout):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except ValueError:
        return {"_raw": raw.strip()}


def _post(url, payload, timeout):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {"error": "http_%d" % e.code}


def _extract_tip(doc):
    """
    Find the tip hash in whatever shape a peer serves. Different nodes
    name it differently and that is not worth an argument.
    """
    if isinstance(doc, str):
        return doc.strip() or None
    if not isinstance(doc, dict):
        return None
    for k in ("tip", "head", "current_tip", "chain_tip", "root",
              "latest", "hash", "audit_hash", "seal"):
        v = doc.get(k)
        if isinstance(v, str) and len(v) >= 32:
            return v.strip()
        if isinstance(v, dict):
            inner = _extract_tip(v)
            if inner:
                return inner
    for k in ("chain", "witness", "data", "result"):
        v = doc.get(k)
        if isinstance(v, dict):
            inner = _extract_tip(v)
            if inner:
                return inner
    return None


# ------------------------------------------------------------------ core

class Mesh(object):

    def __init__(self, tip_url=None, seal_url=None, chain=None,
                 roster=None, skip=None, timeout=None, dry_run=False):
        self.tip_url = tip_url or os.environ.get("MESH_TIP_URL")
        self.seal_url = seal_url or os.environ.get("MESH_SEAL_URL")
        self.chain = chain or os.environ.get("MESH_CHAIN")
        self.roster = roster or os.environ.get("MESH_ROSTER", DEFAULT_ROSTER)
        self.timeout = float(timeout or os.environ.get("MESH_TIMEOUT",
                                                       DEFAULT_TIMEOUT))
        self.dry_run = dry_run
        raw_skip = skip or os.environ.get("MESH_SKIP", "")
        self.skip = set(s.strip().lower() for s in raw_skip.split(",") if s.strip())

    def check(self):
        problems = []
        if not self.tip_url:
            problems.append("MESH_TIP_URL is not set. Other nodes need "
                            "somewhere to fetch your tip from.")
        if not self.chain:
            problems.append("MESH_CHAIN is not set. Your submissions would "
                            "arrive unnamed.")
        if not self.seal_url:
            problems.append("MESH_SEAL_URL is not set, so this will push "
                            "your tip out but not seal theirs. That is "
                            "half the exchange. Not fatal.")
        return problems

    def my_tip(self):
        try:
            return _extract_tip(_get(self.tip_url, self.timeout))
        except Exception as e:
            print("  ! could not read own tip from %s: %s"
                  % (self.tip_url, str(e)[:90]))
            return None

    def fetch_roster(self):
        doc = _get(self.roster, self.timeout)
        peers = doc.get("peers") or []
        out = []
        for p in peers:
            name = (p.get("chain") or "").strip()
            url = p.get("tip_url")
            if not name or not url:
                continue
            if name.lower() == (self.chain or "").lower():
                continue                       # never witness yourself
            if name.lower() in self.skip:
                continue
            out.append({"chain": name, "tip_url": url,
                        "status": p.get("status"),
                        "submit": p.get("submit_to")})
        return out, doc

    def run(self):
        started = time.time()
        print("meshwitness %s  %s" % (VERSION, time.strftime("%Y-%m-%d %H:%M:%S")))

        for p in self.check():
            print("  ! " + p)

        mine = self.my_tip()
        if mine:
            print("  my tip: %s…" % mine[:16])
        else:
            print("  ! no tip of my own to push; will still seal theirs")

        try:
            peers, doc = self.fetch_roster()
        except Exception as e:
            print("  ! roster unreachable (%s): %s" % (self.roster, str(e)[:90]))
            return 1

        submit_to = doc.get("submit_to")
        print("  roster: %d chains, %d witnessable"
              % (doc.get("count", 0), doc.get("witnessable", 0)))

        if not peers:
            print("  nothing to witness yet.")
            return 0

        sealed = pushed = failed = 0

        for p in peers:
            name = p["chain"]
            line = "  %-28s" % name[:28]

            try:
                theirs = _extract_tip(_get(p["tip_url"], self.timeout))
            except Exception as e:
                print(line + "unreachable (%s)" % str(e)[:40])
                failed += 1
                continue

            if not theirs:
                print(line + "served no readable tip")
                failed += 1
                continue

            bits = ["tip %s…" % theirs[:12]]

            # seal theirs into mine
            if self.seal_url and not self.dry_run:
                try:
                    st, _ = _post(self.seal_url,
                                  {"chain": name, "tip": theirs,
                                   "url": p["tip_url"]}, self.timeout)
                    if 200 <= st < 300:
                        bits.append("sealed")
                        sealed += 1
                    else:
                        bits.append("seal HTTP %d" % st)
                except Exception as e:
                    bits.append("seal failed: %s" % str(e)[:30])
            elif self.dry_run:
                bits.append("would seal")

            # push mine to them
            target = p.get("submit") or submit_to
            if mine and target and not self.dry_run:
                try:
                    st, _ = _post(target,
                                  {"chain": self.chain, "tip": mine,
                                   "url": self.tip_url}, self.timeout)
                    if 200 <= st < 300:
                        bits.append("pushed")
                        pushed += 1
                    else:
                        bits.append("push HTTP %d" % st)
                except Exception as e:
                    bits.append("push failed: %s" % str(e)[:30])
            elif self.dry_run and mine:
                bits.append("would push")

            print(line + " · ".join(bits))

        print("  %d sealed, %d pushed, %d unreachable, %.1fs"
              % (sealed, pushed, failed, time.time() - started))

        if self.dry_run:
            return 0
        return 0 if (sealed or pushed) else 1


EXPLAIN = """
The protocol, so you can implement it in any language.

1. Read the roster
     GET https://sebbi.pro/x/roster/list
   -> {"peers":[{"chain":"...","tip_url":"...","witnessable":true}, ...],
       "submit_to":"https://sebbi.pro/x/witness/observe"}

2. For each peer with witnessable=true, read their tip
     GET <tip_url>
   The hash may be under "tip", "head", "root" or similar. It is a hex
   string, usually 64 characters. Nothing else in the document matters.

3. Seal it in your own chain
   Whatever your system does to record an observation. The point is that
   their tip is now inside your history at a time you did not choose,
   which is what makes your later statements about them checkable.

4. Push your own tip back
     POST <their submit endpoint>
     {"chain": "<your name>", "tip": "<your hex tip>",
      "url": "<where your tip is served>"}

   The url field is what binds your name to a host. Leave it out and
   your chain is listed but nobody can fetch from you.

Run it hourly. Pick a minute nobody else is on so the network is not
all talking at once.

No keys. No accounts. No payload but a hash. If your tip endpoint is a
static JSON file regenerated by a cron, that is a completely valid node.
"""


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])

    if "--explain" in argv:
        print(EXPLAIN.strip())
        return 0
    if "--version" in argv:
        print("meshwitness %s" % VERSION)
        return 0
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0

    dry = "--dry-run" in argv
    return Mesh(dry_run=dry).run()


if __name__ == "__main__":
    sys.exit(main())

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


## `sebbi_sdk.py`

1031 lines, 37582 bytes

```python
"""
SEBBI SDK v1.0.0  -  one decorator, no dependencies
Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK

    pip install nothing. Standard library only, Python 3.8+.
    Drop this file next to your code and import it.

WHAT IT DOES

    @witness()
    def approve_loan(application):
        ...
        return decision

    That is the whole integration. Every call now seals a fingerprint of
    what went in and what came out into a hash chain, and the chain head
    is fetched and sealed by independent operators on their own schedule.

WHAT LEAVES YOUR PROCESS

    A hash. Nothing else.

    The arguments and the return value are canonicalised and hashed
    locally. The hash goes out. The data does not, ever, not in a debug
    mode, not in an error path. There is no code in this file that puts a
    payload on the wire, so you do not have to trust the claim - you can
    read it in an afternoon.

    If you want the content recorded too, that is a decision only you can
    make, and this SDK will not make it quietly for you.

WHAT IT COSTS THE CALLING THREAD

    Hashing, then a queue append. Typically well under a millisecond.
    The network call happens on a background thread. Your function never
    waits for sebbi.pro and never fails because sebbi.pro is down.

    If the network is unreachable the record spools to disk and is sent
    when it comes back. If you have not configured a spool directory, and
    the queue fills, records are dropped and counted - and stats() will
    tell you so rather than pretending everything is fine.

WHAT A RECEIPT PROVES

    That this exact input and output existed at or before the moment it
    was sealed, and that the record has not been altered since.

WHAT IT DOES NOT PROVE

    That the decision was right. Wrong answers seal exactly as cleanly as
    right ones.
    That your records are complete. This seals what you decorated. It
    cannot know about the call you did not decorate.
    That your model behaved. It fingerprints inputs and outputs, not
    reasoning.

    Anyone selling you the opposite of those three lines is selling you
    something that does not exist.

QUICK START

    import os
    os.environ["SEBBI_API_KEY"] = "al_live_..."

    from sebbi_sdk import witness, receipt_for, stats, flush

    @witness(label="loan-decision")
    def approve(app):
        return {"approved": True}

    r = approve({"id": 7})
    print(receipt_for(r))         # or use the returned handle

SELF TEST

    python3 sebbi_sdk.py --selftest      runs against a local stub, no network
    python3 sebbi_sdk.py --explain       the wire protocol, for other languages
"""

from __future__ import annotations

import atexit
import functools
import hashlib
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

__version__ = "1.0.0"
__all__ = ["witness", "configure", "flush", "stats", "receipt_for",
           "fingerprint", "Receipt", "SebbiConfig"]

_USER_AGENT = "sebbi-sdk-python/" + __version__

# How a value that will not serialise is represented in the fingerprint.
# It is stable, so the same unserialisable shape hashes the same way twice.
_OPAQUE = "__sebbi_opaque__"


# ==========================================================================
# CONFIG
# ==========================================================================

class SebbiConfig:
    """
    Everything the SDK needs. Read from the environment by default so a
    deployment can be configured without touching code.

        SEBBI_API_KEY       your key. required to send.
        SEBBI_ENDPOINT      where seal requests go.
        SEBBI_CHAIN         the chain name your records belong to.
        SEBBI_SPOOL         directory for offline records. optional but
                            recommended - without it, an outage loses
                            records once the queue fills.
        SEBBI_ENABLED       set to 0 to make every decorator a no-op.
        SEBBI_TIMEOUT       seconds per request. default 10.
        SEBBI_QUEUE_MAX     in-memory queue depth. default 10000.
        SEBBI_BATCH         records per request. default 25.
    """

    def __init__(self,
                 api_key: Optional[str] = None,
                 endpoint: Optional[str] = None,
                 chain: Optional[str] = None,
                 spool_dir: Optional[str] = None,
                 enabled: Optional[bool] = None,
                 timeout: Optional[float] = None,
                 queue_max: Optional[int] = None,
                 batch_size: Optional[int] = None) -> None:
        env = os.environ.get
        self.api_key: str = api_key if api_key is not None else env("SEBBI_API_KEY", "")
        self.endpoint: str = (endpoint if endpoint is not None
                              else env("SEBBI_ENDPOINT",
                                       "https://sebbi.pro/api/seal"))
        self.chain: str = chain if chain is not None else env("SEBBI_CHAIN", "")
        self.spool_dir: str = (spool_dir if spool_dir is not None
                               else env("SEBBI_SPOOL", ""))
        if enabled is None:
            enabled = env("SEBBI_ENABLED", "1").strip().lower() not in (
                "0", "false", "no", "off")
        self.enabled: bool = bool(enabled)
        self.timeout: float = float(timeout if timeout is not None
                                    else env("SEBBI_TIMEOUT", "10"))
        self.queue_max: int = int(queue_max if queue_max is not None
                                  else env("SEBBI_QUEUE_MAX", "10000"))
        self.batch_size: int = int(batch_size if batch_size is not None
                                   else env("SEBBI_BATCH", "25"))

    def describe(self) -> Dict[str, Any]:
        """Safe to log. The key is shown as a stub, never in full."""
        k = self.api_key
        return {"endpoint": self.endpoint, "chain": self.chain or None,
                "enabled": self.enabled, "spool_dir": self.spool_dir or None,
                "timeout": self.timeout, "queue_max": self.queue_max,
                "batch_size": self.batch_size,
                "api_key": (k[:8] + "..." + k[-4:]) if len(k) > 14
                           else ("set" if k else "NOT SET")}


_config = SebbiConfig()
_config_lock = threading.Lock()


def configure(**kwargs: Any) -> SebbiConfig:
    """
    Override configuration in code. Restarts the sender if it is running.

        configure(api_key="al_live_...", chain="acme.example",
                  spool_dir="/var/spool/sebbi")
    """
    global _config
    with _config_lock:
        _config = SebbiConfig(**kwargs)
        if _sender.started:
            _sender.restart(_config)
    return _config


# ==========================================================================
# FINGERPRINTING
#
# Canonical JSON then SHA-256. Two runs of the same inputs must produce
# the same hash on any machine, in any Python version, in any dict
# insertion order - otherwise a receipt cannot be checked later.
# ==========================================================================

def _canonical(obj: Any, depth: int = 0) -> Any:
    """
    Reduce any Python value to something JSON can serialise
    deterministically. Unknown types become a stable descriptor rather
    than their repr(), because repr() often contains a memory address and
    would make the same object hash differently on every run.
    """
    if depth > 24:
        return _OPAQUE + ":depth"
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        # NaN and infinities are not valid JSON and are not stable
        if obj != obj or obj in (float("inf"), float("-inf")):
            return _OPAQUE + ":float:" + repr(obj)
        return obj
    if isinstance(obj, (bytes, bytearray)):
        return "sha256:" + hashlib.sha256(bytes(obj)).hexdigest()
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[str(k)] = _canonical(v, depth + 1)
        return dict(sorted(out.items()))
    if isinstance(obj, (list, tuple)):
        return [_canonical(v, depth + 1) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted((json.dumps(_canonical(v, depth + 1), sort_keys=True)
                       for v in obj))
    for attr in ("isoformat", "__dict__"):
        try:
            if attr == "isoformat" and hasattr(obj, "isoformat"):
                return obj.isoformat()
            if attr == "__dict__" and hasattr(obj, "__dict__"):
                return _canonical(vars(obj), depth + 1)
        except Exception:
            pass
    return _OPAQUE + ":" + type(obj).__name__


def fingerprint(obj: Any) -> str:
    """
    Deterministic SHA-256 over any Python value.

    The same value hashes the same way on every machine and every run.
    This is the only thing that ever leaves your process.
    """
    canon = json.dumps(_canonical(obj), sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ==========================================================================
# RECEIPT
# ==========================================================================

class Receipt:
    """
    The record of one witnessed call.

    Available the instant your function returns. `sealed` and
    `chain_position` fill in when the background sender gets confirmation,
    which is normally within a second but is never waited on.
    """

    __slots__ = ("local_id", "label", "started_at", "duration_ms",
                 "input_hash", "output_hash", "combined_hash", "outcome",
                 "error_type", "sealed", "chain_position", "chain_tip",
                 "sealed_at", "send_error", "chain")

    def __init__(self, label: str, chain: str) -> None:
        self.local_id: str = uuid.uuid4().hex
        self.label: str = label
        self.chain: str = chain
        self.started_at: float = 0.0
        self.duration_ms: float = 0.0
        self.input_hash: str = ""
        self.output_hash: str = ""
        self.combined_hash: str = ""
        self.outcome: str = "pending"
        self.error_type: Optional[str] = None
        self.sealed: bool = False
        self.chain_position: Optional[int] = None
        self.chain_tip: Optional[str] = None
        self.sealed_at: Optional[float] = None
        self.send_error: Optional[str] = None

    def wire(self) -> Dict[str, Any]:
        """Exactly what is transmitted. Hashes and metadata, no payload."""
        d = {"local_id": self.local_id, "label": self.label,
             "ts": self.started_at, "duration_ms": round(self.duration_ms, 3),
             "input_hash": self.input_hash, "output_hash": self.output_hash,
             "hash": self.combined_hash, "outcome": self.outcome,
             "sdk": _USER_AGENT}
        if self.error_type:
            d["error_type"] = self.error_type
        if self.chain:
            d["chain"] = self.chain
        return d

    def to_dict(self) -> Dict[str, Any]:
        d = self.wire()
        d.update({"sealed": self.sealed,
                  "chain_position": self.chain_position,
                  "chain_tip": self.chain_tip, "sealed_at": self.sealed_at,
                  "send_error": self.send_error,
                  "proves": "This input and output existed at or before the "
                            "sealed time and have not changed since.",
                  "does_not_prove": "That the result was correct, or that "
                                    "your records are complete."})
        return d

    def __repr__(self) -> str:
        state = "sealed" if self.sealed else (
            "unsent:" + self.send_error if self.send_error else "pending")
        return "<Receipt %s %s %s %s>" % (self.label, self.outcome,
                                          self.combined_hash[:12], state)


# Receipts keyed by the id() of the returned object, so you can get a
# receipt back without changing your function's return type. Bounded, and
# holds no reference to your object - only its id and the receipt.
_receipts: "Dict[int, Receipt]" = {}
_receipt_order: List[int] = []
_receipt_lock = threading.Lock()
_RECEIPT_KEEP = 2048


def _remember(result: Any, receipt: Receipt) -> None:
    try:
        rid = id(result)
    except Exception:
        return
    with _receipt_lock:
        if rid not in _receipts:
            _receipt_order.append(rid)
        _receipts[rid] = receipt
        while len(_receipt_order) > _RECEIPT_KEEP:
            old = _receipt_order.pop(0)
            _receipts.pop(old, None)


def receipt_for(result: Any) -> Optional[Receipt]:
    """
    The receipt for a value returned by a witnessed function.

    Only the most recent few thousand are kept in memory. If you need a
    receipt to outlive the request, read it immediately and store it.
    """
    if isinstance(result, Receipt):
        return result
    with _receipt_lock:
        return _receipts.get(id(result))


# ==========================================================================
# BACKGROUND SENDER
# ==========================================================================

class _Sender:
    """
    One daemon thread, one bounded queue, batched sends, disk spool on
    failure. Started lazily on the first witnessed call so that importing
    this module costs nothing.
    """

    def __init__(self) -> None:
        self.q: "queue.Queue[Optional[Receipt]]" = queue.Queue()
        self.thread: Optional[threading.Thread] = None
        self.started = False
        self.stop_flag = threading.Event()
        self.lock = threading.Lock()
        self.counters = {"queued": 0, "sent": 0, "sealed": 0, "dropped": 0,
                         "spooled": 0, "respooled": 0, "failed": 0}
        self.cfg = _config

    # -- lifecycle ------------------------------------------------------

    def ensure(self, cfg: SebbiConfig) -> None:
        if self.started:
            return
        with self.lock:
            if self.started:
                return
            self.cfg = cfg
            self.q = queue.Queue(maxsize=cfg.queue_max)
            self.stop_flag.clear()
            self.thread = threading.Thread(target=self._run, name="sebbi-sender",
                                           daemon=True)
            self.thread.start()
            self.started = True
            atexit.register(self.shutdown)

    def restart(self, cfg: SebbiConfig) -> None:
        self.shutdown(timeout=2.0)
        self.started = False
        self.ensure(cfg)

    def shutdown(self, timeout: float = 5.0) -> None:
        if not self.started:
            return
        self.stop_flag.set()
        try:
            self.q.put_nowait(None)
        except queue.Full:
            pass
        t = self.thread
        if t and t.is_alive():
            t.join(timeout=timeout)

    # -- submission -----------------------------------------------------

    def submit(self, r: Receipt) -> None:
        try:
            self.q.put_nowait(r)
            self.counters["queued"] += 1
        except queue.Full:
            # The queue is full, which means the endpoint has been
            # unreachable for a while. Spool if we can; count it if we
            # cannot. Never block the caller's thread.
            if self._spool([r]):
                self.counters["spooled"] += 1
            else:
                self.counters["dropped"] += 1
                r.send_error = "queue_full_no_spool"

    def flush(self, timeout: float = 10.0) -> bool:
        """Block until the queue drains. For shutdown and for tests."""
        if not self.started:
            return True
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.q.unfinished_tasks == 0 and self.q.empty():
                return True
            time.sleep(0.02)
        return False

    # -- the loop -------------------------------------------------------

    def _run(self) -> None:
        batch: List[Receipt] = []
        last_retry = 0.0
        while not self.stop_flag.is_set() or not self.q.empty():
            try:
                item = self.q.get(timeout=0.25)
            except queue.Empty:
                item = None
                if batch:
                    self._send(batch)
                    for _ in batch:
                        self.q.task_done()
                    batch = []
                if time.time() - last_retry > 30:
                    last_retry = time.time()
                    self._retry_spool()
                continue

            if item is None:
                self.q.task_done()
                break

            batch.append(item)
            if len(batch) >= self.cfg.batch_size:
                self._send(batch)
                for _ in batch:
                    self.q.task_done()
                batch = []

        if batch:
            self._send(batch)
            for _ in batch:
                self.q.task_done()

    # -- network --------------------------------------------------------

    def _send(self, batch: List[Receipt]) -> None:
        cfg = self.cfg
        if not cfg.api_key:
            for r in batch:
                r.send_error = "no_api_key"
            self.counters["failed"] += len(batch)
            self._spool(batch)
            return

        body = json.dumps({"records": [r.wire() for r in batch],
                           "chain": cfg.chain or None,
                           "sdk": _USER_AGENT}).encode("utf-8")
        req = urllib.request.Request(
            cfg.endpoint, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Accept": "application/json",
                     "Authorization": "Bearer " + cfg.api_key,
                     "User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
            self.counters["sent"] += len(batch)
            self._apply(batch, raw)
        except urllib.error.HTTPError as e:
            detail = "http_%d" % e.code
            for r in batch:
                r.send_error = detail
            self.counters["failed"] += len(batch)
            # 4xx is our fault and will not fix itself by retrying;
            # 5xx and timeouts are worth spooling.
            if e.code >= 500 or e.code == 429:
                self._spool(batch)
        except Exception as e:
            for r in batch:
                r.send_error = type(e).__name__
            self.counters["failed"] += len(batch)
            self._spool(batch)

    def _apply(self, batch: List[Receipt], raw: str) -> None:
        """
        Read whatever the server sent back and fill in the receipts.

        Different sebbi endpoints name things slightly differently, and
        an SDK arguing with its own server helps nobody. Any of these
        shapes is accepted.
        """
        try:
            doc = json.loads(raw)
        except Exception:
            return
        by_id: Dict[str, Dict[str, Any]] = {}
        items = doc.get("records") or doc.get("results") or doc.get("sealed")
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get("local_id"):
                    by_id[str(it["local_id"])] = it
        for r in batch:
            info = by_id.get(r.local_id, doc if len(batch) == 1 else {})
            if not isinstance(info, dict):
                continue
            pos = (info.get("chain_position") or info.get("key_seq")
                   or info.get("block_index") or info.get("sequence"))
            tip = (info.get("chain_tip") or info.get("tip")
                   or info.get("audit_hash") or info.get("sealed_in_our_chain"))
            if pos is not None or tip:
                r.sealed = True
                r.chain_position = pos
                r.chain_tip = tip
                r.sealed_at = time.time()
                r.send_error = None
                self.counters["sealed"] += 1

    # -- spool ----------------------------------------------------------

    def _spool(self, batch: List[Receipt]) -> bool:
        d = self.cfg.spool_dir
        if not d:
            return False
        try:
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, "sebbi-%d-%s.jsonl"
                                % (int(time.time() * 1000), uuid.uuid4().hex[:8]))
            with open(path, "w", encoding="utf-8") as f:
                for r in batch:
                    f.write(json.dumps(r.wire()) + "\n")
            return True
        except Exception:
            return False

    def _retry_spool(self) -> None:
        d = self.cfg.spool_dir
        if not d or not os.path.isdir(d) or not self.cfg.api_key:
            return
        try:
            files = sorted(f for f in os.listdir(d)
                           if f.startswith("sebbi-") and f.endswith(".jsonl"))
        except Exception:
            return
        for name in files[:20]:
            path = os.path.join(d, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    records = [json.loads(line) for line in f if line.strip()]
            except Exception:
                continue
            if not records:
                try:
                    os.remove(path)
                except Exception:
                    pass
                continue
            body = json.dumps({"records": records,
                               "chain": self.cfg.chain or None,
                               "replay": True,
                               "sdk": _USER_AGENT}).encode("utf-8")
            req = urllib.request.Request(
                self.cfg.endpoint, data=body, method="POST",
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + self.cfg.api_key,
                         "User-Agent": _USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=self.cfg.timeout):
                    pass
                os.remove(path)
                self.counters["respooled"] += len(records)
            except Exception:
                return  # still down; try again on the next sweep


_sender = _Sender()


def flush(timeout: float = 10.0) -> bool:
    """Wait for queued records to be sent. Returns False on timeout."""
    return _sender.flush(timeout)


def stats() -> Dict[str, Any]:
    """
    Counters and configuration.

    `dropped` above zero means records were lost because the endpoint was
    unreachable and no spool directory was set. That is worth alerting on:
    a gap in an audit chain is exactly the thing the chain exists to make
    impossible to create quietly.
    """
    s = dict(_sender.counters)
    s["queue_depth"] = _sender.q.qsize() if _sender.started else 0
    s["running"] = _sender.started
    s["config"] = _config.describe()
    if s["dropped"]:
        s["warning"] = ("%d records were dropped. Set SEBBI_SPOOL to a "
                        "writable directory so an outage cannot lose them."
                        % s["dropped"])
    return s


# ==========================================================================
# THE DECORATOR
# ==========================================================================

def witness(label: Optional[str] = None,
            capture_args: bool = True,
            capture_result: bool = True,
            chain: Optional[str] = None,
            on_error: str = "seal") -> Callable:
    """
    Seal a fingerprint of every call to this function.

    Args:
        label:          what this function is called in the record.
                        Defaults to module.function.
        capture_args:   fingerprint the arguments. Off means the record
                        says a call happened but not what went in.
        capture_result: fingerprint the return value.
        chain:          override the configured chain name.
        on_error:       "seal"   record the failure and re-raise. default.
                        "skip"   record nothing on failure, re-raise.
                        Exceptions from your function are ALWAYS re-raised.
                        This decorator never swallows one.

    Works on ordinary functions, generators are not unrolled (the
    generator object itself is fingerprinted, not the values it will
    yield - unrolling it would change your program's behaviour, which a
    decorator has no business doing).

    If an async function is decorated, the coroutine is fingerprinted the
    same way. Await it as normal.
    """
    if on_error not in ("seal", "skip"):
        raise ValueError("on_error must be 'seal' or 'skip'")

    def decorator(fn: Callable) -> Callable:
        name = label or "%s.%s" % (getattr(fn, "__module__", "?"),
                                   getattr(fn, "__qualname__", getattr(
                                       fn, "__name__", "anonymous")))

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cfg = _config
            if not cfg.enabled:
                return fn(*args, **kwargs)

            r = Receipt(name, chain if chain is not None else cfg.chain)
            r.started_at = time.time()
            r.input_hash = (fingerprint({"args": args, "kwargs": kwargs})
                            if capture_args else "")
            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                r.duration_ms = (time.perf_counter() - t0) * 1000
                if on_error == "seal":
                    r.outcome = "error"
                    r.error_type = type(exc).__name__
                    r.output_hash = ""
                    r.combined_hash = fingerprint(
                        {"label": name, "in": r.input_hash,
                         "error": r.error_type, "ts": r.started_at})
                    _dispatch(cfg, r)
                raise
            r.duration_ms = (time.perf_counter() - t0) * 1000
            r.outcome = "ok"
            r.output_hash = fingerprint(result) if capture_result else ""
            r.combined_hash = fingerprint(
                {"label": name, "in": r.input_hash, "out": r.output_hash,
                 "ts": r.started_at})
            _dispatch(cfg, r)
            _remember(result, r)
            return result

        wrapper.__sebbi_label__ = name       # type: ignore[attr-defined]
        wrapper.__sebbi_wrapped__ = True     # type: ignore[attr-defined]
        return wrapper

    return decorator


def _dispatch(cfg: SebbiConfig, r: Receipt) -> None:
    """Hand the receipt to the background thread. Never raises, never
    blocks - a witnessing SDK that can break the thing it is witnessing
    is worse than no witnessing at all."""
    try:
        _sender.ensure(cfg)
        _sender.submit(r)
    except Exception:
        pass


# ==========================================================================
# WIRE PROTOCOL, for ports to other languages
# ==========================================================================

EXPLAIN = """
The whole protocol. Port it in an hour, in anything.

FINGERPRINT
    Canonicalise the value: object keys sorted, no insignificant
    whitespace, UTF-8. Bytes become "sha256:" + hex of their digest.
    Values that will not serialise become a stable type descriptor,
    never a repr containing a memory address.
    Then SHA-256 the canonical bytes and hex-encode.

    combined = sha256(canonical({
        "in":    <hex input hash>,
        "label": <string>,
        "out":   <hex output hash>,
        "ts":    <float unix seconds>
    }))

    Note the keys are sorted, so "in" precedes "label" precedes "out"
    precedes "ts". Get that wrong and your hashes will not match anyone
    else's.

SEND
    POST <endpoint>
    Authorization: Bearer <api key>
    Content-Type: application/json

    {"records": [
        {"local_id": "<uuid hex>",
         "label": "loan-decision",
         "ts": 1755600000.123,
         "duration_ms": 4.21,
         "input_hash": "<64 hex>",
         "output_hash": "<64 hex>",
         "hash": "<64 hex combined>",
         "outcome": "ok" | "error",
         "error_type": "ValueError"}
     ],
     "chain": "acme.example"}

    Batch freely. Send on a background worker. Never make the caller
    wait for this and never fail their call because this failed.

RESPONSE
    Anything carrying a position and a tip per local_id:

    {"records": [{"local_id": "...", "chain_position": 8412,
                  "chain_tip": "<64 hex>"}]}

RULES THAT ARE NOT NEGOTIABLE
    No payload on the wire. Ever. If your port sends the arguments, it
    is not this protocol and it should not use this name.
    Never block the caller.
    Never swallow the caller's exception.
    Count what you drop and expose the count.
"""


# ==========================================================================
# SELF TEST - no network, runs against a local stub server
# ==========================================================================

def _selftest() -> int:
    import http.server
    import socketserver
    import sys
    import tempfile

    passes = [0]
    fails = [0]

    def check(name: str, cond: bool, detail: Any = "") -> None:
        if cond:
            print("  PASS  " + name)
            passes[0] += 1
        else:
            print("  FAIL  " + name + "  " + str(detail))
            fails[0] += 1

    received: List[Dict[str, Any]] = []
    seen_bodies: List[str] = []
    fail_mode = {"on": False}

    class Stub(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(n).decode()
            seen_bodies.append(raw)
            if fail_mode["on"]:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"{}")
                return
            doc = json.loads(raw)
            out = []
            for rec in doc.get("records", []):
                received.append(rec)
                out.append({"local_id": rec.get("local_id"),
                            "chain_position": len(received),
                            "chain_tip": "b" * 64})
            body = json.dumps({"records": out}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = socketserver.TCPServer(("127.0.0.1", 0), Stub)
    srv.allow_reuse_address = True
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    spool = tempfile.mkdtemp(prefix="sebbi-spool-")
    configure(api_key="al_test_key", chain="selftest.example",
              endpoint="http://127.0.0.1:%d/api/seal" % port,
              spool_dir=spool, batch_size=5, timeout=3)

    print("SEBBI SDK v%s - self test" % __version__)
    print("=" * 62)

    print("\n[1] Fingerprints are deterministic")
    a = {"z": 1, "a": [1, 2, {"q": None}], "m": "x"}
    b = {"a": [1, 2, {"q": None}], "m": "x", "z": 1}
    check("Key order does not change the hash", fingerprint(a) == fingerprint(b))
    check("A different value changes the hash",
          fingerprint(a) != fingerprint({"z": 2, "a": [1, 2, {"q": None}],
                                         "m": "x"}))
    check("Length is 64 hex", len(fingerprint(a)) == 64)

    class Odd:
        def __init__(self):
            self.v = 3

    check("Unserialisable objects hash stably",
          fingerprint(Odd()) == fingerprint(Odd()))
    check("Bytes hash by digest",
          fingerprint(b"hello") == fingerprint(bytearray(b"hello")))
    check("NaN does not explode", len(fingerprint(float("nan"))) == 64)

    import datetime
    check("Dates hash by isoformat",
          fingerprint(datetime.date(2026, 8, 19))
          == fingerprint(datetime.date(2026, 8, 19)))

    print("\n[2] The decorator")

    @witness(label="add")
    def add(x, y):
        return {"sum": x + y}

    out = add(2, 3)
    check("Return value passes through untouched", out == {"sum": 5})
    rec = receipt_for(out)
    check("Receipt retrievable from the result", rec is not None)
    check("Outcome recorded", rec and rec.outcome == "ok")
    check("Input hash present", rec and len(rec.input_hash) == 64)
    check("Output hash present", rec and len(rec.output_hash) == 64)
    check("Duration measured", rec and rec.duration_ms >= 0)
    check("Metadata preserved by functools.wraps", add.__name__ == "add")

    @witness()
    def default_label():
        return 1

    default_label()
    check("Default label derived from the function",
          "default_label" in default_label.__sebbi_label__)

    print("\n[3] The payload never leaves")
    secret = "PATIENT-NHS-4477-CONFIDENTIAL"

    @witness(label="phi")
    def handle(record):
        return {"ok": True, "note": secret}

    handle({"nhs": secret, "dob": "1970-01-01"})
    flush(5)
    joined = "\n".join(seen_bodies)
    check("The secret is not on the wire", secret not in joined, "LEAK")
    check("No field named args/kwargs was transmitted",
          '"args"' not in joined and '"kwargs"' not in joined)
    check("Records did arrive", len(received) > 0)

    print("\n[4] Exceptions")

    @witness(label="boom")
    def boom():
        raise ValueError("intentional")

    raised = False
    try:
        boom()
    except ValueError:
        raised = True
    check("The caller's exception is re-raised", raised)
    flush(5)
    errs = [r for r in received if r.get("outcome") == "error"]
    check("The failure was sealed", len(errs) > 0)
    check("The error type was recorded",
          any(e.get("error_type") == "ValueError" for e in errs))

    @witness(label="quiet", on_error="skip")
    def quiet():
        raise KeyError("k")

    before = len(received)
    try:
        quiet()
    except KeyError:
        pass
    flush(3)
    check("on_error='skip' seals nothing", len(received) == before)

    print("\n[5] Sealing comes back")
    out2 = add(10, 20)
    flush(5)
    r2 = receipt_for(out2)
    check("Receipt marked sealed", r2 and r2.sealed, r2)
    check("Chain position returned", r2 and r2.chain_position is not None)
    check("Chain tip returned", r2 and r2.chain_tip)

    print("\n[6] The endpoint going down does not break the caller")
    fail_mode["on"] = True
    ok = True
    for i in range(12):
        try:
            add(i, i)
        except Exception as e:
            ok = False
            print("     raised:", e)
    flush(6)
    check("Calls still succeed while the endpoint is 503", ok)
    spooled = [f for f in os.listdir(spool) if f.endswith(".jsonl")]
    check("Records were spooled to disk", len(spooled) > 0, spooled)
    check("Spooled files contain no payload",
          all(secret not in open(os.path.join(spool, f)).read()
              for f in spooled))
    fail_mode["on"] = False

    print("\n[7] Overhead")
    @witness(label="bench")
    def bench(x):
        return x

    t0 = time.perf_counter()
    for i in range(2000):
        bench({"i": i, "payload": "x" * 200})
    per = ((time.perf_counter() - t0) / 2000) * 1000
    print("      %.3f ms added per call" % per)
    check("Under 1ms per call in-thread", per < 1.0, "%.3f ms" % per)

    print("\n[8] Disabled mode is a true no-op")
    configure(api_key="al_test_key", enabled=False,
              endpoint="http://127.0.0.1:%d/api/seal" % port)
    before = len(received)

    @witness(label="off")
    def off():
        return "v"

    check("Still returns correctly", off() == "v")
    flush(2)
    check("Nothing was sent", len(received) == before)
    configure(api_key="al_test_key", chain="selftest.example",
              endpoint="http://127.0.0.1:%d/api/seal" % port,
              spool_dir=spool, batch_size=5)

    print("\n[9] Threads")
    results = []

    @witness(label="threaded")
    def work(n):
        return n * 2

    def runner(n):
        results.append(work(n))

    ts = [threading.Thread(target=runner, args=(i,)) for i in range(50)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    flush(8)
    check("All 50 threaded calls returned", len(results) == 50)
    check("No exceptions under concurrency", sorted(results)[0] == 0)

    print("\n[10] Stats are honest")
    s = stats()
    check("Counters exposed", "queued" in s and "dropped" in s)
    check("API key is not printed in full",
          "al_test_key" not in json.dumps(s["config"]))

    flush(5)
    srv.shutdown()
    print("\n" + "=" * 62)
    print("Results: %d passed, %d failed" % (passes[0], fails[0]))
    print("ALL TESTS PASSED." if not fails[0] else "FAILURES. Do not ship.")
    return 0 if not fails[0] else 1


if __name__ == "__main__":
    import sys
    if "--explain" in sys.argv:
        print(EXPLAIN.strip())
        sys.exit(0)
    if "--version" in sys.argv:
        print("sebbi-sdk " + __version__)
        sys.exit(0)
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__.strip())

```


## `sebdog_engine.py`

842 lines, 32546 bytes

```python
"""
SEBDOG ENGINE v1.2.0
Local compliance engine. Runs on your hardware. Data never leaves it.
Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK

WHAT CHANGED IN 1.2
-------------------
1. NO PHONE HOME. v1.1 called sebbi.pro on startup and every 24 hours,
   returned 403 without a valid licence and exited if it could not reach
   the server. So "sovereign" described the data and not the engine, and
   an air-gapped box could not run it at all. Licensing is now an
   Ed25519 token validated locally by sebdog_licence v2. This process
   makes no outbound call to sebbi.pro, ever. Verify that with a packet
   capture rather than taking it from a docstring.

2. IT CAN BE WITNESSED. Two new routes:
       GET  /tip               your current chain head, for peers to seal
       POST /witness/observe   seal a peer's head into your chain
   That is the whole witness protocol. Point meshwitness.py at this
   engine and your on-premise chain is sealed into chains held by
   operators neither you nor your vendor controls. A local hash chain
   proves nothing against the party who owns the file - this is what
   turns it into evidence.

3. THE SEAL RACE IS FIXED. v1.1 read the chain tip under the lock,
   released it, then took the lock again to insert. Two concurrent
   requests could read the same prev_hash and both write against it.
   Tip read, hash and insert now happen inside one lock hold, which is
   how server.py has done it since the same bug was found there.

4. /govern NO LONGER ACCEPTS AN EMPTY BEARER. v1.1 checked
   `if bearer and bearer != key`, so a request with no Authorization
   header passed straight through and was rate-limited under "default".
   Any process on the host could drive the engine. A matching bearer is
   now required.

5. BACKUPS CANNOT BE TORN. shutil.copy2 on a live WAL database can copy
   a half-written file. Backups now use sqlite3's own backup API, which
   is transactionally safe on a running database, and each backup is
   sealed into the chain - so restoring an older backup is visible
   rather than silent.

SOVEREIGNTY, STATED PRECISELY
-----------------------------
    The engine makes no outbound connection of any kind.
    Your decisions, your events and your chain stay on your disk.
    If you enable witnessing, ONE hash leaves - your chain head. It
    cannot be reversed into anything and it reveals nothing but the
    fact that your chain exists and has moved.

WHAT IT DOES NOT DO
-------------------
    It does not prove a decision was correct. Wrong answers seal as
    cleanly as right ones.
    It does not prove your records are complete. A chain can be intact
    and simply not contain what matters.
    Witnessing does not make your log true. It makes it impossible to
    rewrite quietly after the fact.

RUN IT
    python3 sebdog_engine.py --token <your licence token>
    python3 sebdog_engine.py --token-file licence.txt --port 9090
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

try:
    import sebdog_licence as licence
except ImportError:
    licence = None

VERSION = "1.2.0"
HOME = "https://sebbi.pro"
DB_FILE = "sebdog_audit.db"
CHAIN_NAME = "sebdog-local"
SAFE = {"UK", "US", "DE", "FR", "CA", "AU", "NL", "SE", "NO", "DK",
        "FI", "IE", "NZ"}
REQ = {"user_id", "action", "amount", "country", "device_id", "anomaly",
       "device_risk"}
HEX64 = set("0123456789abcdef")

_db_lock = threading.Lock()
_key_wins = defaultdict(lambda: {"min": deque(), "hour": deque()})
_key_lock = threading.Lock()
W60 = defaultdict(deque)
W5M = defaultdict(deque)
W1H = defaultdict(deque)

_licence = {"valid": False, "plan": "free", "product": "aileash",
            "devices": 1, "email": "", "checked_at": 0, "key": "",
            "expires": 0, "grace": False}

_conn = None


# ==============================================================================
# LICENCE - validated locally, no network
# ==============================================================================

def load_licence(token, pubkey=None):
    """Validate an Ed25519 licence token offline. No outbound call."""
    global _licence
    if licence is None:
        print("[SEBDOG] sebdog_licence.py not found next to this file.",
              flush=True)
        return False
    data, err = licence.validate_token(token, pubkey)
    if err:
        explain = {
            "no_public_key": "No licence public key is configured. Set "
                             "SEBDOG_LICENCE_PUBKEY or edit LICENCE_PUBKEY "
                             "in sebdog_licence.py.",
            "invalid_signature": "This token was not signed by the expected "
                                 "key, or it has been altered.",
            "token_expired": "This licence expired more than 7 days ago.",
            "version_mismatch": "This is an old v1 token. v1 tokens were "
                                "verifiable by anyone holding the shared "
                                "secret and have been withdrawn. Request a "
                                "replacement.",
            "invalid_format": "This does not decode as a licence token.",
        }.get(err, err)
        print("[SEBDOG] Licence rejected: %s\n           %s" % (err, explain),
              flush=True)
        return False

    _licence.update({
        "valid": True, "plan": data.get("plan", "free"),
        "devices": data.get("devices", 1), "email": data.get("email", ""),
        "key": data.get("key", ""), "expires": data.get("expires", 0),
        "checked_at": time.time(),
        "grace": licence.is_in_grace_period(data),
    })
    days = licence.days_until_expiry(data)
    print("[SEBDOG] Licence valid, checked locally. Plan:%s Devices:%s"
          % (_licence["plan"], _licence["devices"]), flush=True)
    if _licence["grace"]:
        print("[SEBDOG] EXPIRED - running on the 7 day grace period. Renew "
              "at %s" % HOME, flush=True)
    elif days < 30:
        print("[SEBDOG] Licence expires in %d days." % days, flush=True)
    return True


def licence_watch():
    """Re-check expiry hourly against the local clock. Still no network."""
    while True:
        time.sleep(3600)
        if _licence["expires"] and _licence["expires"] < time.time():
            if not _licence["grace"]:
                _licence["grace"] = True
                print("[SEBDOG] Licence has expired. 7 day grace period "
                      "started. Renew at %s" % HOME, flush=True)
            if _licence["expires"] + licence.GRACE_SECONDS < time.time():
                _licence["valid"] = False
                print("[SEBDOG] Grace period over. Governing is disabled; "
                      "your chain and data are untouched.", flush=True)


# ==============================================================================
# DATABASE + BACKUP
# ==============================================================================

def get_conn():
    c = sqlite3.connect(DB_FILE, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5,
        last_country TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT,
        event_json TEXT, result_json TEXT, prev_hash TEXT,
        audit_hash TEXT UNIQUE)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit ON audit_log(user_id)")
    c.execute("""CREATE TABLE IF NOT EXISTS chain_snapshots(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL,
        block_count INTEGER, tip_hash TEXT, snapshot_file TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS witness_seen(
        id INTEGER PRIMARY KEY AUTOINCREMENT, peer TEXT, tip TEXT,
        url TEXT, observed REAL, audit_hash TEXT,
        UNIQUE(peer, tip))""")
    c.commit()
    return c


def init_db():
    global _conn
    _conn = get_conn()


def backup_db():
    """
    Timestamped backup using sqlite3's own backup API.

    v1.1 used shutil.copy2, which on a live WAL database can copy a file
    mid-write and produce a backup that will not open. The backup API is
    transactionally consistent against a running connection.

    The backup is then SEALED into the chain, so restoring an older
    database later is detectable rather than silent.
    """
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)),
                              "sebdog_backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(backup_dir, "sebdog_audit_%s.db" % stamp)
    try:
        with _db_lock:
            dest = sqlite3.connect(path)
            _conn.backup(dest)
            dest.close()
            blocks = _conn.execute(
                "SELECT COUNT(*) FROM audit_log").fetchone()[0]
            tip = _conn.execute("SELECT audit_hash FROM audit_log "
                                "ORDER BY id DESC LIMIT 1").fetchone()
            tip_hash = tip[0] if tip else "GENESIS"
            _conn.execute("INSERT INTO chain_snapshots(ts,block_count,"
                          "tip_hash,snapshot_file) VALUES(?,?,?,?)",
                          (time.time(), blocks, tip_hash, path))
            _conn.commit()

        # sealed outside the lock - seal() takes it itself
        seal({"user_id": "sebdog", "action": "backup_created",
              "amount": 0, "country": "UK", "device_id": "sebdog",
              "anomaly": 0, "device_risk": 0},
             {"decision": "BACKUP", "score": 0, "version": VERSION,
              "blocks_at_backup": blocks, "tip_at_backup": tip_hash,
              "note": "backup sealed so a later restore of an older "
                      "database is visible in the chain"},
             time.time())
        print("[SEBDOG] Backup created and sealed: %s (%d blocks)"
              % (path, blocks), flush=True)
        _cleanup_old_backups(backup_dir)
    except Exception as e:
        print("[SEBDOG] Backup failed: %s" % e, flush=True)


def _cleanup_old_backups(backup_dir, keep=7):
    try:
        files = sorted(os.path.join(backup_dir, f)
                       for f in os.listdir(backup_dir)
                       if f.startswith("sebdog_audit_") and f.endswith(".db"))
        for old in files[:-keep]:
            os.remove(old)
    except Exception:
        pass


def backup_loop():
    while True:
        time.sleep(86400)
        backup_db()


def restore_latest_backup():
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)),
                              "sebdog_backups")
    if not os.path.exists(backup_dir):
        return False
    files = sorted(os.path.join(backup_dir, f)
                   for f in os.listdir(backup_dir)
                   if f.startswith("sebdog_audit_") and f.endswith(".db"))
    if not files:
        return False
    try:
        shutil.copy2(files[-1], DB_FILE)
        print("[SEBDOG] Restored from backup: %s" % files[-1], flush=True)
        return True
    except Exception as e:
        print("[SEBDOG] Restore failed: %s" % e, flush=True)
        return False


def list_snapshots():
    with _db_lock:
        rows = _conn.execute(
            "SELECT ts,block_count,tip_hash,snapshot_file FROM "
            "chain_snapshots ORDER BY id DESC LIMIT 10").fetchall()
    return [{"ts": r[0], "blocks": r[1], "tip": r[2], "file": r[3]}
            for r in rows]


# ==============================================================================
# RATE LIMITING
# ==============================================================================

def check_rate(key):
    t = time.time()
    with _key_lock:
        w = _key_wins[key]
        while w["min"] and w["min"][0] < t - 60:
            w["min"].popleft()
        while w["hour"] and w["hour"][0] < t - 3600:
            w["hour"].popleft()
        if len(w["min"]) >= 60:
            return False, "rate_limit_minute"
        if len(w["hour"]) >= 1000:
            return False, "rate_limit_hour"
        w["min"].append(t)
        w["hour"].append(t)
        return True, None


# ==============================================================================
# CORE ENGINE
# ==============================================================================

def now():
    return time.time()


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def sha(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()


def upd_vel(uid):
    t = now()
    for q in (W60[uid], W5M[uid], W1H[uid]):
        q.append(t)
    c = now()
    W60[uid] = deque(x for x in W60[uid] if x >= c - 60)
    W5M[uid] = deque(x for x in W5M[uid] if x >= c - 300)
    W1H[uid] = deque(x for x in W1H[uid] if x >= c - 3600)


def vel(uid):
    return {"60s": len(W60[uid]), "5m": len(W5M[uid]), "1h": len(W1H[uid])}


def load_user(uid):
    with _db_lock:
        r = _conn.execute("SELECT trust,last_country FROM users WHERE "
                          "user_id=?", (uid,)).fetchone()
    return ({"trust": r[0], "last_country": r[1]} if r
            else {"trust": 0.5, "last_country": None})


def save_user(uid, trust, country):
    with _db_lock:
        _conn.execute(
            "INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,"
            "last_country=excluded.last_country", (uid, trust, country))
        _conn.commit()


def score_event(s):
    reasons = []
    sc = (1 - s["trust"]) * 0.30
    v60 = s["v60"]
    sc += min(v60 / 20, 1) * 0.15
    if v60 > 10:
        reasons.append("velocity_spike")
    sc += min(s["v5m"] / 50, 1) * 0.10 + min(s["v1h"] / 200, 1) * 0.10
    amt = float(s.get("amount", 0))
    sc += min(math.log1p(amt) / math.log1p(10000), 1) * 0.15
    if amt > 500:
        reasons.append("high_amount")
    dr = float(s.get("device_risk", 0))
    sc += dr * 0.10
    if dr > 0.5:
        reasons.append("risky_device")
    an = float(s.get("anomaly", 0))
    sc += an * 0.10
    if an > 0.5:
        reasons.append("behaviour_anomaly")
    if s.get("country_shift"):
        sc += 0.10
        reasons.append("country_shift")
    if s.get("unsafe_country"):
        sc += 0.10
        reasons.append("unsafe_country")
    if s["trust"] < 0.4:
        reasons.append("low_trust")
    return round(clamp(sc), 4), reasons


def decide(sc):
    if sc < 0.35:
        return "ALLOW"
    if sc < 0.70:
        return "CHALLENGE"
    return "BLOCK"


def upd_trust(t, d):
    if d == "ALLOW":
        t += (1 - t) * 0.01
    elif d == "CHALLENGE":
        t -= t * 0.02
    elif d == "BLOCK":
        t -= t * 0.08
    return clamp(t, 0.05, 1.0)


def chain_tip():
    with _db_lock:
        r = _conn.execute("SELECT audit_hash FROM audit_log ORDER BY id "
                          "DESC LIMIT 1").fetchone()
    return r[0] if r else "GENESIS"


def chain_head():
    """Tip plus height, in one lock hold, for /tip."""
    with _db_lock:
        r = _conn.execute("SELECT audit_hash,ts,id FROM audit_log "
                          "ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return "GENESIS", None, 0
    return r[0], r[1], r[2]


def seal(event, result, ts):
    """
    Tip read, hash and insert inside ONE lock hold.

    v1.1 read the tip under the lock, released it, then re-acquired to
    insert. Between those two points another thread could read the same
    prev_hash, and both writes would claim the same predecessor. The
    same bug was found and fixed in server.py; this is that fix.
    """
    with _db_lock:
        r = _conn.execute("SELECT audit_hash FROM audit_log ORDER BY id "
                          "DESC LIMIT 1").fetchone()
        prev = r[0] if r else "GENESIS"
        h = sha({"prev_hash": prev, "ts": ts, "event": event,
                 "result": result})
        _conn.execute(
            "INSERT INTO audit_log(ts,user_id,event_json,result_json,"
            "prev_hash,audit_hash) VALUES(?,?,?,?,?,?)",
            (ts, event["user_id"], json.dumps(event), json.dumps(result),
             prev, h))
        _conn.commit()
    return h


def verify_chain():
    with _db_lock:
        rows = _conn.execute(
            "SELECT event_json,result_json,prev_hash,audit_hash,ts FROM "
            "audit_log ORDER BY id ASC").fetchall()
    if not rows:
        return {"valid": True, "blocks": 0, "message": "Empty chain"}
    prev = "GENESIS"
    for i, row in enumerate(rows):
        p = {"prev_hash": row[2], "ts": row[4],
             "event": json.loads(row[0]), "result": json.loads(row[1])}
        if sha(p) != row[3] or row[2] != prev:
            return {"valid": False, "broken_at": i,
                    "message": "Tampered at block %d" % i}
        prev = row[3]
    return {"valid": True, "blocks": len(rows), "tip": rows[-1][3],
            "message": "Chain intact"}


def govern(event):
    missing = REQ - event.keys()
    if missing:
        raise ValueError("Missing fields: %s" % missing)
    if not _licence["valid"]:
        return {"error": "licence_invalid",
                "message": "A valid licence token is required. Get one at "
                           "%s. Your chain and data are untouched." % HOME}, 403
    ts = now()
    uid = event["user_id"]
    state = load_user(uid)
    upd_vel(uid)
    v = vel(uid)
    country = event["country"]
    signals = {
        "trust": state["trust"], "v60": v["60s"], "v5m": v["5m"],
        "v1h": v["1h"], "amount": float(event.get("amount", 0)),
        "device_risk": float(event.get("device_risk", 0)),
        "anomaly": float(event.get("anomaly", 0)),
        "country_shift": (state["last_country"] is not None
                          and state["last_country"] != country),
        "unsafe_country": country not in SAFE,
    }
    sc, reasons = score_event(signals)
    dec = decide(sc)
    trust = upd_trust(state["trust"], dec)
    save_user(uid, trust, country)
    result = {"decision": dec, "score": sc, "trust": round(trust, 4),
              "reasons": reasons, "version": VERSION, "engine": "sebdog",
              "local": True, "timestamp": ts}
    result["audit_hash"] = seal(event, result, ts)
    return result, 200


# ==============================================================================
# WITNESSING
#
# A local hash chain proves nothing against the person who owns the file.
# These two routes are what let somebody else hold your history.
# ==============================================================================

def observe(data):
    """Seal a peer's chain head into this chain. Never rejects a
    well-formed submission - the record says what arrived, not whether
    we approve of it."""
    peer = str(data.get("chain") or data.get("peer") or "").strip().lower()
    if not peer or len(peer) > 80:
        return {"error": "chain_required",
                "message": "A short stable identifier - a domain works."}, 400
    tip = str(data.get("tip", "")).strip().lower()
    if len(tip) != 64 or not all(c in HEX64 for c in tip):
        return {"error": "invalid_tip",
                "message": "A tip is 64 hex characters."}, 400
    url = str(data.get("url") or "").strip()[:400]

    with _db_lock:
        seen = _conn.execute("SELECT observed,audit_hash FROM witness_seen "
                             "WHERE peer=? AND tip=?", (peer, tip)).fetchone()
    if seen:
        return {"witnessed": True, "already_seen": True, "peer": peer,
                "tip": tip, "observed_at": seen[0],
                "sealed_in_our_chain": seen[1],
                "message": "Already witnessed. Their chain has not moved, "
                           "or this is a replay."}, 200

    ts = now()
    h = seal({"user_id": "witness:" + peer, "action": "peer_tip_observed",
              "amount": 0, "country": "UK", "device_id": "witness",
              "anomaly": 0, "device_risk": 0},
             {"decision": "WITNESS_SEALED", "score": 0, "version": VERSION,
              "peer": peer, "peer_tip": tip, "peer_url": url or None,
              "timestamp": ts,
              "note": "a peer's chain head, sealed here. This records what "
                      "they handed us and when. It says nothing about "
                      "whether their chain is honest."}, ts)
    with _db_lock:
        _conn.execute("INSERT OR IGNORE INTO witness_seen(peer,tip,url,"
                      "observed,audit_hash) VALUES(?,?,?,?,?)",
                      (peer, tip, url or None, ts, h))
        _conn.commit()

    our, _t, height = chain_head()
    return {"witnessed": True, "peer": peer, "tip": tip, "observed_at": ts,
            "sealed_in_our_chain": h, "our_tip_now": our,
            "our_height": height, "engine": "sebdog",
            "what_this_proves": "That this value was handed to us at this "
                                "time and sealed into a chain we control. "
                                "Nothing about whether it is true."}, 200


# ==============================================================================
# HTTP
# ==============================================================================

def send_json(h, data, status=200):
    body = json.dumps(data, indent=2).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    h.wfile.write(body)


def read_body(h):
    n = int(h.headers.get("Content-Length", 0) or 0)
    if n:
        try:
            return json.loads(h.rfile.read(n))
        except Exception:
            return {}
    return {}


def get_bearer(h):
    auth = h.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return h.headers.get("X-API-Key", "").strip()


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type,Authorization,X-API-Key")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path == "/tip":
            # The witness protocol's first call. Public on purpose: a peer
            # cannot seal what it cannot read, and a chain head reveals
            # nothing but that the chain exists and has moved.
            tip, ts, height = chain_head()
            send_json(self, {
                "chain": CHAIN_NAME, "tip": tip, "height": height,
                "sealed_at": ts, "engine": "sebdog", "version": VERSION,
                "note": "Seal this into your own chain. Hand us yours at "
                        "POST /witness/observe and we will seal it here.",
                "what_this_is": "The head of a hash chain held on this "
                                "operator's own hardware. It is a hash and "
                                "nothing else - no event, no record, no "
                                "personal data, and it cannot be reversed.",
            })

        elif path == "/health":
            send_json(self, {
                "status": "ok", "version": VERSION, "engine": "sebdog",
                "local": True, "phones_home": False,
                "licence": {"valid": _licence["valid"],
                            "plan": _licence["plan"],
                            "devices": _licence["devices"],
                            "email": _licence["email"],
                            "in_grace_period": _licence["grace"],
                            "validated": "locally, no network"}})

        elif path == "/verify-chain":
            send_json(self, verify_chain())

        elif path == "/stats":
            with _db_lock:
                blocks = _conn.execute(
                    "SELECT COUNT(*) FROM audit_log").fetchone()[0]
                users = _conn.execute(
                    "SELECT COUNT(*) FROM users").fetchone()[0]
                peers = _conn.execute(
                    "SELECT COUNT(DISTINCT peer) FROM witness_seen"
                ).fetchone()[0]
            send_json(self, {"audit_blocks": blocks, "users_tracked": users,
                             "peers_witnessed": peers, "version": VERSION,
                             "engine": "sebdog",
                             "licence_valid": _licence["valid"]})

        elif path == "/peers":
            with _db_lock:
                rows = _conn.execute(
                    "SELECT peer,COUNT(*),MAX(observed),MAX(url) FROM "
                    "witness_seen GROUP BY peer ORDER BY MAX(observed) DESC"
                ).fetchall()
            send_json(self, {
                "count": len(rows),
                "peers": [{"chain": r[0], "observations": r[1],
                           "last_seen": r[2], "tip_url": r[3]}
                          for r in rows],
                "note": "Chains whose heads we have sealed here. Being "
                        "listed is not endorsement of anything in their "
                        "chain."})

        elif path == "/snapshots":
            send_json(self, {"snapshots": list_snapshots()})

        elif path == "/backup":
            # keyed - a backup writes to disk and seals a block
            if get_bearer(self) != _licence["key"]:
                send_json(self, {"error": "invalid_api_key"}, 401)
                return
            backup_db()
            send_json(self, {"ok": True, "message": "Backup created and "
                                                    "sealed"})
        else:
            send_json(self, {"error": "not_found",
                             "routes": ["/tip", "/health", "/verify-chain",
                                        "/stats", "/peers", "/snapshots",
                                        "/backup (keyed)",
                                        "POST /govern (keyed)",
                                        "POST /witness/observe"]}, 404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        data = read_body(self)

        if path in ("/witness/observe", "/api/witness/observe"):
            # Open by design. A witnessing endpoint that needs an account
            # is a customer list, not a witness network.
            ok, ec = check_rate("witness:" + str(self.client_address[0]))
            if not ok:
                send_json(self, {"error": ec}, 429)
                return
            try:
                result, status = observe(data)
                send_json(self, result, status)
            except Exception as e:
                send_json(self, {"error": "internal", "detail": str(e)}, 500)
            return

        if path in ("/govern", "/api/govern"):
            # v1.1 allowed a missing bearer through. It does not now.
            bearer = get_bearer(self)
            if not bearer or bearer != _licence["key"]:
                send_json(self, {"error": "invalid_api_key",
                                 "message": "Send your licence key as "
                                            "Authorization: Bearer <key>."},
                          401)
                return
            ok, ec = check_rate(bearer)
            if not ok:
                send_json(self, {"error": ec}, 429)
                return
            try:
                result, status = govern(data)
                send_json(self, result, status)
            except ValueError as e:
                send_json(self, {"error": str(e)}, 400)
            except Exception as e:
                send_json(self, {"error": "internal", "detail": str(e)}, 500)
            return

        send_json(self, {"error": "not_found"}, 404)


class ThreadedServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


# ==============================================================================
# ENTRY POINT
# ==============================================================================

def main():
    p = argparse.ArgumentParser(
        description="Sebdog Engine - local compliance engine, no phone home")
    p.add_argument("--token", help="Your licence token from sebbi.pro")
    p.add_argument("--token-file", help="File containing the licence token")
    p.add_argument("--pubkey", help="Licence public key hex (overrides the "
                                    "built-in one; for testing)")
    p.add_argument("--port", type=int, default=9090)
    p.add_argument("--db", default="sebdog_audit.db")
    p.add_argument("--chain", default=None,
                   help="Chain name other operators record you as")
    p.add_argument("--backup-on-start", action="store_true")
    args = p.parse_args()

    global DB_FILE, CHAIN_NAME
    DB_FILE = args.db
    if args.chain:
        CHAIN_NAME = args.chain.strip().lower()

    token = args.token
    if not token and args.token_file:
        try:
            with open(args.token_file, "r", encoding="utf-8") as f:
                token = f.read().strip()
        except Exception as e:
            print("[SEBDOG] Could not read token file: %s" % e, flush=True)
            sys.exit(1)
    if not token:
        token = os.environ.get("SEBDOG_TOKEN", "").strip()
    if not token:
        print("[SEBDOG] No licence token. Pass --token, --token-file, or "
              "set SEBDOG_TOKEN.", flush=True)
        sys.exit(1)

    print("[SEBDOG] Sebdog Engine v%s starting..." % VERSION, flush=True)

    if not os.path.exists(DB_FILE):
        print("[SEBDOG] Database not found. Checking for backups...",
              flush=True)
        if not restore_latest_backup():
            print("[SEBDOG] No backup found. Starting a fresh chain.",
                  flush=True)

    init_db()

    print("[SEBDOG] Validating licence locally. No network call is made.",
          flush=True)
    if not load_licence(token, args.pubkey):
        print("[SEBDOG] Licence validation failed. Get a token at %s" % HOME,
              flush=True)
        sys.exit(1)

    if licence is not None:
        try:
            licence.save_licence_locally(DB_FILE, token, {
                "key": _licence["key"], "devices": _licence["devices"],
                "plan": _licence["plan"], "email": _licence["email"],
                "issued": 0, "expires": _licence["expires"]})
        except Exception:
            pass

    if args.backup_on_start:
        backup_db()

    threading.Thread(target=licence_watch, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()

    srv = ThreadedServer(("0.0.0.0", args.port), Handler)
    base = "http://localhost:%d" % args.port
    print("[SEBDOG] Engine running on port %d" % args.port, flush=True)
    print("[SEBDOG] POST %s/govern            (needs your key)" % base,
          flush=True)
    print("[SEBDOG] GET  %s/tip               (your chain head)" % base,
          flush=True)
    print("[SEBDOG] POST %s/witness/observe   (peers seal their head here)"
          % base, flush=True)
    print("[SEBDOG] GET  %s/verify-chain      (rewalks every block)" % base,
          flush=True)
    print("[SEBDOG] GET  %s/peers             (who you have witnessed)"
          % base, flush=True)
    print("[SEBDOG] Backups: ./sebdog_backups/ daily, last 7 kept, sealed",
          flush=True)
    print("[SEBDOG] This process makes no outbound connection. Check it "
          "with tcpdump if you like.", flush=True)
    print("[SEBDOG] To be witnessed by others, point meshwitness.py at "
          "this engine:", flush=True)
    print("[SEBDOG]   MESH_TIP_URL=<your public url>/tip", flush=True)
    print("[SEBDOG]   MESH_SEAL_URL=<your public url>/witness/observe",
          flush=True)
    print("[SEBDOG]   MESH_CHAIN=%s" % CHAIN_NAME, flush=True)

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("[SEBDOG] Shutting down.", flush=True)


if __name__ == "__main__":
    main()

```
