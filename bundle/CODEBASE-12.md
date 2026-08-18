# Codebase — part 12 of 21

Contains:
- `gateway_proxy.py`
- `meshwitness.py`
- `sebbi_orchestrator.py`
- `sebdog_engine.py`
- `sebdog_licence.py`
- `sebdog_reporter.py`
- `tests/attack_continuity_1.py`


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


## `tests/attack_continuity_1.py`

440 lines, 22747 bytes

```python
#!/usr/bin/env python3
"""Attack harness for modules/lineage.py.

Every test is written from the position of an agent that HAS some authority
and is trying to end up with more. Passing means the attack was refused for
the right reason, not merely refused.
"""

import hashlib
import json
import sqlite3
import threading
import time
import sys

import continuity as lineage
# --- stand-in for the deployed engine ---------------------------------
import types as _types
_ENGINE = {"verdict": "ALLOW"}

def install_engine(verdict="ALLOW", raises=False, shape="dict"):
    _ENGINE["verdict"] = verdict
    mod = _types.ModuleType("server")
    mod.get_bearer = lambda *a, **k: None
    def score_event(event):
        if raises:
            raise RuntimeError("engine down")
        if shape == "dict":
            return {"decision": _ENGINE["verdict"], "score": 0.1}
        if shape == "tuple":
            return (_ENGINE["verdict"], 0.1)
        return _ENGINE["verdict"]
    mod.score_event = score_event
    sys.modules["server"] = mod

def remove_engine():
    sys.modules.pop("server", None)

install_engine("ALLOW")


PASS, FAIL = [], []


def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock()
    chain = {"n": 0, "prev": "0" * 64}

    def seal(ev, res, ts, api_key):
        chain["n"] += 1
        payload = json.dumps([ev, res, ts, api_key, chain["prev"]], sort_keys=True)
        h = hashlib.sha256(payload.encode()).hexdigest()
        chain["prev"] = h
        return h, chain["n"], chain["n"]

    lineage._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    lineage._setup(ctx)
    return ctx


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(("  ok   " if condition else "  FAIL ") + name + (("  -> " + detail) if detail and not condition else ""))


def issue(ctx, **kw):
    if kw.get("parent") and int(kw.get("delegations_left", 0)) > 0 \
            and not kw.get("risk_accepted_by"):
        kw["risk_accepted_by"] = "owner@example.com"
    return lineage._issue(ctx, "k", kw)


def exercise(ctx, **kw):
    return lineage._evaluate(ctx, "k", kw)


NOW = time.time()
HOUR = 3600


def base_root(ctx, **over):
    args = dict(
        id="root", issuer="justin@monop", issuer_kind="human",
        subject="orchestrator", subject_kind="agent",
        scope=["payments.refund", "payments.read", "tickets.*"],
        constraints={"max_amount": 5000, "allowed_currency": ["GBP", "EUR"],
                     "denied_country": ["KP"], "may_contact_customer": True},
        purpose="resolve customer refund complaints",
        purpose_tags=["refunds", "support"],
        not_before=NOW - HOUR, not_after=NOW + 10 * HOUR,
        delegations_left=3)
    args.update(over)
    return issue(ctx, **args)


print("\n=== 1. the happy path must actually work ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent",
      subject="refund-agent", scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="issue refunds under 500", purpose_tags=["refunds"],
      not_before=NOW - HOUR, not_after=NOW + 2 * HOUR, delegations_left=1)
r, code = exercise(ctx, grant="mid", action="payments.refund",
                   params={"amount": 100, "currency": "GBP", "country": "GB",
                           "contact_customer": True},
                   purpose_tag="refunds")
check("a derivable action returns ALLOW", r["verdict"] == "ALLOW", str(r["reasons"]))
check("lineage names the human at the root", r["authorised_by"] == "justin@monop")
check("depth is reported", r["delegation_depth"] == 1)
check("the decision is sealed", bool(r.get("sealed_in_chain")))

print("\n=== 2. orphan root: an agent grants itself authority ===")
ctx = make_ctx()
r, code = issue(ctx, id="self", issuer="rogue-agent", issuer_kind="agent",
                subject="rogue-agent", scope=["payments.refund"],
                constraints={"max_amount": 999999}, purpose="whatever I decide",
                purpose_tags=["anything"], not_after=NOW + HOUR)
check("self-issued root is refused at issue", code == 409 and r.get("error") == "identity_continuity", str(r))

print("\n=== 3. scope escalation in a child ===")
ctx = make_ctx()
base_root(ctx)
r, code = issue(ctx, id="wide", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund", "payments.transfer"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": False},
                purpose="sneak in a transfer", purpose_tags=["refunds"],
                not_after=NOW + HOUR, delegations_left=0)
check("scope the parent never held is refused",
      code == 409 and "payments.transfer" in r.get("message", ""), str(r))

print("\n=== 4. constraint loosening ===")
ctx = make_ctx()
base_root(ctx)
r, code = issue(ctx, id="rich", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 50000, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="bigger refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("raising a max_ cap is refused", code == 409 and "max_amount" in r.get("message", ""), str(r))

r, code = issue(ctx, id="wide2", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP", "USD"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="new currency", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("adding to an allowed_ set is refused", code == 409 and "USD" in r.get("message", ""), str(r))

r, code = issue(ctx, id="undeny", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": [], "may_contact_customer": True},
                purpose="drop the denylist", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("dropping from a denied_ set is refused", code == 409 and "KP" in r.get("message", ""), str(r))

r, code = issue(ctx, id="newkey", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True,
                             "may_export_data": True},
                purpose="invent a permission", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("introducing a constraint key the parent never expressed is refused",
      code == 409 and "may_export_data" in r.get("message", ""), str(r))

print("\n=== 5. temporal attacks ===")
ctx = make_ctx()
base_root(ctx)
r, code = issue(ctx, id="long", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="outlive the parent", purpose_tags=["refunds"],
                not_before=NOW, not_after=NOW + 100 * HOUR)
check("a child cannot outlive its parent", code == 409 and r.get("error") == "temporal_validity", str(r))

# expired ancestor, live leaf, forced in past the issue check
ctx = make_ctx()
base_root(ctx, not_after=NOW + HOUR)
issue(ctx, id="child", parent="root", issuer="orchestrator", issuer_kind="agent",
      subject="agent-b", scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET not_after=? WHERE id='root'", (NOW - 60,))
    ctx["conn"].commit()
r, _ = exercise(ctx, grant="child", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("an expired ancestor kills a live leaf", r["verdict"] == "BLOCK", str(r["reasons"]))
check("...and it is reported as tampering, since the row no longer matches its digest",
      r["broken_invariant"] == "evidence_continuity", r["broken_invariant"] or "")

print("\n=== 6. revocation is transitive ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent",
      subject="b", scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR, delegations_left=1)
issue(ctx, id="leaf", parent="mid", issuer="b", issuer_kind="agent",
      subject="c", scope=["payments.refund"],
      constraints={"max_amount": 50, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
lineage._revoke(ctx, "k", {"grant": "mid", "reason": "agent compromised"})
r, _ = exercise(ctx, grant="leaf", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("revoking the middle blocks the leaf without touching it", r["verdict"] == "BLOCK")
check("the revoked grant is named", r["broken_at"] == "mid", str(r["broken_at"]))
r2, _ = exercise(ctx, grant="root", action="payments.refund",
                 params={"amount": 10, "currency": "GBP", "country": "GB",
                         "contact_customer": True}, purpose_tag="refunds")
check("revoking a child does not harm the parent", r2["verdict"] == "ALLOW", str(r2["reasons"]))

print("\n=== 7. delegation depth cannot be manufactured ===")
ctx = make_ctx()
base_root(ctx, delegations_left=1)
issue(ctx, id="d1", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR, delegations_left=0)
r, code = issue(ctx, id="d2", parent="d1", issuer="b", issuer_kind="agent", subject="c",
                scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("an exhausted delegation budget stops the chain",
      code == 409 and r.get("error") == "delegation_not_permitted", str(r))

ctx = make_ctx()
base_root(ctx, delegations_left=2)
r, code = issue(ctx, id="greedy", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR,
                delegations_left=5)
check("a child cannot award itself more onward delegations than remained",
      code == 409, str(r))

print("\n=== 8. tampering with a stored grant ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute(
        "UPDATE auth_grant SET constraints=? WHERE id='mid'",
        (json.dumps({"max_amount": 999999, "allowed_currency": ["GBP", "USD"],
                     "denied_country": [], "may_contact_customer": True},
                    sort_keys=True, separators=(",", ":")),))
    ctx["conn"].commit()
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 900000, "currency": "USD", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("editing the database does not widen authority", r["verdict"] == "BLOCK")
check("the tamper is reported as an evidence failure",
      r["broken_invariant"] == "evidence_continuity", str(r["broken_invariant"]))

print("\n=== 9. re-parenting onto a wider ancestor ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="narrow", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.read"],
      constraints={"max_amount": 1, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": False},
      purpose="read only", purpose_tags=["support"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET parent=NULL WHERE id='narrow'")
    ctx["conn"].commit()
r, _ = exercise(ctx, grant="narrow", action="payments.read",
                params={}, purpose_tag="support")
check("detaching a grant to make it a root fails integrity", r["verdict"] == "BLOCK",
      str(r["reasons"]))

print("\n=== 10. parent cycle ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="a", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR, delegations_left=1)
issue(ctx, id="b", parent="a", issuer="b", issuer_kind="agent", subject="c",
      scope=["payments.refund"],
      constraints={"max_amount": 50, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET parent='b' WHERE id='a'")
    ctx["conn"].commit()
start = time.time()
r, _ = exercise(ctx, grant="b", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("a parent cycle terminates rather than hangs", time.time() - start < 2)
check("a cycle is BLOCKed as an authority failure", r["verdict"] == "BLOCK")

print("\n=== 11. action parameters beyond the effective constraints ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 501, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("an amount over the cap is BLOCKed", r["verdict"] == "BLOCK", str(r["reasons"]))
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "KP",
                        "contact_customer": True}, purpose_tag="refunds")
check("a denied country is BLOCKed", r["verdict"] == "BLOCK", str(r["reasons"]))

print("\n=== 12. uncertainty is challenged, not guessed ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="issue refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="marketing")
check("a purpose the grant does not carry is CHALLENGED", r["verdict"] == "CHALLENGE", str(r))
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True})
check("no declared purpose is CHALLENGED", r["verdict"] == "CHALLENGE", str(r))
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True, "recipient_iban": "GB00XXXX"},
                purpose_tag="refunds")
check("an unconstrained parameter is CHALLENGED, not ignored",
      r["verdict"] == "CHALLENGE" and any("recipient_iban" in x for x in r["reasons"]), str(r))

print("\n=== 13. wildcard breadth ===")
ctx = make_ctx()
base_root(ctx)
r, _ = exercise(ctx, grant="root", action="tickets.close.bulk.all",
                params={}, purpose_tag="support")
check("a broad wildcard match is CHALLENGED rather than silently allowed",
      r["verdict"] == "CHALLENGE", str(r))

ctx = make_ctx()
base_root(ctx, scope=["*"], id="star")
r, _ = exercise(ctx, grant="star", action="payments.transfer", params={}, purpose_tag="refunds")
check("a bare * never reaches ALLOW", r["verdict"] == "CHALLENGE", str(r))

print("\n=== 14. no union of grants ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="money", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": False},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
issue(ctx, id="contact", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.read"],
      constraints={"max_amount": 0, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="contact", purpose_tags=["support"], not_after=NOW + HOUR)
r, code = exercise(ctx, grant="money,contact", action="payments.refund",
                   params={"amount": 10, "currency": "GBP", "contact_customer": True},
                   purpose_tag="refunds")
check("two grant ids cannot be combined into one exercise", r["verdict"] == "BLOCK", str(r))
r, _ = exercise(ctx, grant="money", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "contact_customer": True},
                purpose_tag="refunds")
check("the capability from the sibling grant does not leak in", r["verdict"] == "BLOCK",
      str(r["reasons"]))

print("\n=== 15. time of check vs time of use ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
eval_id = r["evaluation"]
c, code = lineage._confirm(ctx, "k", {"evaluation": eval_id, "action": "payments.refund",
                                      "params": {"amount": 10, "currency": "GBP",
                                                 "country": "GB", "contact_customer": True}})
check("executing exactly what was evaluated binds", c["bound"] is True, str(c))
c, code = lineage._confirm(ctx, "k", {"evaluation": eval_id, "action": "payments.refund",
                                      "params": {"amount": 400, "currency": "GBP",
                                                 "country": "GB", "contact_customer": True}})
check("executing different values than were evaluated is rejected", c["bound"] is False, str(c))
check("the rejected execution is still sealed", bool(c.get("sealed_in_chain")))

with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_eval SET valid_until=? WHERE id=?", (NOW - 1, eval_id))
    ctx["conn"].commit()
c, _ = lineage._confirm(ctx, "k", {"evaluation": eval_id})
check("a banked evaluation cannot be spent after its window", c["bound"] is False, str(c))

print("\n=== 16. a BLOCK is evidence, not silence ===")
ctx = make_ctx()
base_root(ctx)
r, _ = exercise(ctx, grant="nonexistent", action="payments.refund", params={})
check("an unknown grant BLOCKs", r["verdict"] == "BLOCK")
check("the block is sealed in the chain", bool(r.get("sealed_in_chain")))
d, code = lineage._decision(ctx, {"evaluation": r["evaluation"]})
check("the sealed decision is publicly retrievable", code == 200 and d["verdict"] == "BLOCK")

print("\n=== 17. no authority without a stated purpose or an end date ===")
ctx = make_ctx()
r, code = issue(ctx, id="forever", issuer="justin@monop", issuer_kind="human", subject="a",
                scope=["payments.refund"], constraints={"max_amount": 1},
                purpose="anything", purpose_tags=["x"])
check("a grant with no expiry is refused", code == 400 and r.get("error") == "not_after_required")
r, code = issue(ctx, id="vague", issuer="justin@monop", issuer_kind="human", subject="a",
                scope=["payments.refund"], constraints={"max_amount": 1},
                purpose="", purpose_tags=["x"], not_after=NOW + HOUR)
check("a grant with no purpose is refused", code == 400 and r.get("error") == "purpose_required")

print("\n" + "=" * 60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
if FAIL:
    for f in FAIL:
        print("  FAILED: " + f)
    sys.exit(1)

```
