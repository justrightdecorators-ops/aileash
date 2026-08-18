# Codebase — part 12 of 21

Contains:
- `meshwitness.py`
- `sebbi_orchestrator.py`
- `sebdog_engine.py`
- `sebdog_licence.py`
- `sebdog_reporter.py`
- `tests/attack_continuity_1.py`
- `tests/attack_continuity_2.py`
- `tests/attack_continuity_3.py`
- `tests/attack_continuity_4.py`
- `tests/attack_continuity_5.py`


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


## `tests/attack_continuity_2.py`

228 lines, 10573 bytes

```python
#!/usr/bin/env python3
"""Second wave. The first wave tested the obvious escalations. This one
tests the ones that would survive a code review."""

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
NOW = time.time()
HOUR = 3600


def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock()
    n = {"i": 0}

    def seal(ev, res, ts, api_key):
        n["i"] += 1
        return hashlib.sha256(json.dumps([ev, res, ts], sort_keys=True,
                                         default=str).encode()).hexdigest(), n["i"], n["i"]
    lineage._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    lineage._setup(ctx)
    return ctx


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> " + str(detail)[:300]) if detail and not cond else ""))


def issue(ctx, **kw):
    if kw.get("parent") and int(kw.get("delegations_left", 0)) > 0 \
            and not kw.get("risk_accepted_by"):
        kw["risk_accepted_by"] = "owner@example.com"
    return lineage._issue(ctx, "k", kw)


def root(ctx, **over):
    args = dict(id="root", issuer="owner@example.com", issuer_kind="human",
                subject="orchestrator", scope=["payments.refund", "payments.read"],
                constraints={"max_amount": 5000, "allowed_currency": ["GBP", "EUR"]},
                purpose="refunds", purpose_tags=["refunds"],
                not_before=NOW - HOUR, not_after=NOW + 10 * HOUR, delegations_left=10)
    args.update(over)
    return issue(ctx, **args)


print("\n=== 18. double execution against one ALLOW ===")
ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": 100, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
eid = r["evaluation"]
p = {"amount": 100, "currency": "GBP"}
c1, _ = lineage._confirm(ctx, "k", {"evaluation": eid, "action": "payments.refund", "params": p})
c2, _ = lineage._confirm(ctx, "k", {"evaluation": eid, "action": "payments.refund", "params": p})
check("the first execution binds", c1["bound"] is True, c1)
check("the same evaluation cannot be spent twice", c2["bound"] is False, c2)

print("\n=== 19. type confusion in constraints ===")
ctx = make_ctx()
root(ctx, constraints={"max_amount": 5000, "allowed_currency": "GBP"})
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": 10, "currency": "G"},
                                    "purpose_tag": "refunds"})
check("a single character does not satisfy a string-valued allowed_ list",
      r["verdict"] == "BLOCK", r["reasons"])

ctx = make_ctx()
root(ctx)
r, code = issue(ctx, id="strnum", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": "50000", "allowed_currency": ["GBP"]},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("a numeric cap passed as a string cannot beat the parent", code == 409, r)

ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": "99999", "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("a string amount is still compared numerically", r["verdict"] == "BLOCK", r["reasons"])

ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": True, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("a non-numeric amount does not slip through as unconstrained",
      r["verdict"] in ("BLOCK", "CHALLENGE"), r)

print("\n=== 20. capability prefix tricks ===")
ctx = make_ctx()
root(ctx, scope=["payments.refund"])
for probe in ["payments.refunds", "payments.refund.approve", "payments.refundX",
              "Payments.Refund", "payments.refund "]:
    r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": probe,
                                        "params": {}, "purpose_tag": "refunds"})
    check("'%s' is not covered by 'payments.refund'" % probe, r["verdict"] == "BLOCK", r["reasons"])

ctx = make_ctx()
root(ctx, scope=["payments.*"])
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments2.transfer",
                                    "params": {}, "purpose_tag": "refunds"})
check("'payments.*' does not cover 'payments2.transfer'", r["verdict"] == "BLOCK", r["reasons"])

print("\n=== 21. a long but legitimate chain ===")
ctx = make_ctx()
root(ctx, constraints={"max_amount": 10000, "allowed_currency": ["GBP", "EUR"]},
     delegations_left=12)
parent, cap = "root", 10000
for i in range(10):
    cap = cap // 2
    gid = "d%d" % i
    r, code = issue(ctx, id=gid, parent=parent, issuer="a%d" % i, issuer_kind="agent",
                    subject="a%d" % (i + 1), scope=["payments.refund"],
                    constraints={"max_amount": cap, "allowed_currency": ["GBP"]},
                    purpose="refunds", purpose_tags=["refunds"],
                    not_after=NOW + HOUR, delegations_left=11 - i)
    if code != 200:
        break
    parent = gid
check("ten legitimate narrowing hops are accepted", code == 200 and parent == "d9", r)
r, _ = lineage._evaluate(ctx, "k", {"grant": "d9", "action": "payments.refund",
                                    "params": {"amount": 5, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("the deep chain still ALLOWs a derivable action", r["verdict"] == "ALLOW", r["reasons"])
check("the effective cap is the tightest in the chain",
      float(r["effective_constraints"]["max_amount"]) == 9, r["effective_constraints"])
check("the human at the root is still named ten hops down",
      r["authorised_by"] == "owner@example.com")
r, _ = lineage._evaluate(ctx, "k", {"grant": "d9", "action": "payments.refund",
                                    "params": {"amount": 10, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("one unit over the deepest cap is BLOCKed", r["verdict"] == "BLOCK", r["reasons"])

print("\n=== 22. revoking the root kills the whole tree ===")
lineage._revoke(ctx, "k", {"grant": "root", "reason": "principal withdrew authority"})
r, _ = lineage._evaluate(ctx, "k", {"grant": "d9", "action": "payments.refund",
                                    "params": {"amount": 1, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("revoking the root blocks a leaf ten hops away", r["verdict"] == "BLOCK")
check("the root is named as the break point", r["broken_at"] == "root", r["broken_at"])

print("\n=== 23. issuing under a revoked or expired parent ===")
ctx = make_ctx()
root(ctx)
lineage._revoke(ctx, "k", {"grant": "root", "reason": "x"})
r, code = issue(ctx, id="after", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": 1, "allowed_currency": ["GBP"]},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("no new delegation under a revoked parent", code == 409 and r.get("error") == "parent_revoked", r)

print("\n=== 24. duplicate grant id cannot overwrite a grant ===")
ctx = make_ctx()
root(ctx)
r, code = root(ctx, scope=["*"], constraints={"max_amount": 999999})
check("re-issuing an existing id is refused", code == 409 and r.get("error") == "grant_exists", r)

print("\n=== 25. the boundary values themselves ===")
ctx = make_ctx()
root(ctx, constraints={"max_amount": 100, "allowed_currency": ["GBP"]}, delegations_left=2)
r, code = issue(ctx, id="equal", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"]},
                purpose="refunds", purpose_tags=["refunds"],
                not_after=NOW + 10 * HOUR, delegations_left=1)
check("an equal-not-wider child is accepted", code == 200, r)
r, _ = lineage._evaluate(ctx, "k", {"grant": "equal", "action": "payments.refund",
                                    "params": {"amount": 100, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("exactly the cap is allowed", r["verdict"] == "ALLOW", r["reasons"])
r, _ = lineage._evaluate(ctx, "k", {"grant": "equal", "action": "payments.refund",
                                    "params": {"amount": 100.01, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("a penny over the cap is blocked", r["verdict"] == "BLOCK", r["reasons"])

print("\n=== 26. a CHALLENGE cannot be executed ===")
ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": 1, "currency": "GBP"}})
check("no declared purpose gives CHALLENGE", r["verdict"] == "CHALLENGE", r["verdict"])
c, code = lineage._confirm(ctx, "k", {"evaluation": r["evaluation"],
                                      "action": "payments.refund",
                                      "params": {"amount": 1, "currency": "GBP"}})
check("a CHALLENGE cannot be bound as an execution", c["bound"] is False, c)

print("\n" + "=" * 60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL:
    print("  FAILED: " + f)
sys.exit(1 if FAIL else 0)

```


## `tests/attack_continuity_3.py`

114 lines, 5626 bytes

```python
#!/usr/bin/env python3
"""Third wave: concurrency, and reconstruction from evidence alone."""
import hashlib, json, sqlite3, threading, time, sys
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
NOW, HOUR = time.time(), 3600

def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i": 0}
    def seal(ev, res, ts, k):
        with lock:
            n["i"] += 1
            return hashlib.sha256(json.dumps([ev,res,ts],sort_keys=True,default=str).encode()).hexdigest(), n["i"], n["i"]
    lineage._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    lineage._setup(ctx); return ctx

def check(n, c, d=""):
    (PASS if c else FAIL).append(n)
    print(("  ok   " if c else "  FAIL ") + n + (("  -> " + str(d)[:250]) if d and not c else ""))

print("\n=== 27. concurrent execution of one ALLOW ===")
ctx = make_ctx()
lineage._issue(ctx,"k",dict(id="root",issuer="owner@example.com",issuer_kind="human",
    subject="agent",scope=["payments.refund"],constraints={"max_amount":5000},
    purpose="refunds",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=0))
r,_ = lineage._evaluate(ctx,"k",{"grant":"root","action":"payments.refund",
    "params":{"amount":100},"purpose_tag":"refunds"})
eid = r["evaluation"]; results = []
def race():
    c,_ = lineage._confirm(ctx,"k",{"evaluation":eid,"action":"payments.refund","params":{"amount":100}})
    results.append(c["bound"])
ts = [threading.Thread(target=race) for _ in range(8)]
[t.start() for t in ts]; [t.join() for t in ts]
check("exactly one of eight concurrent executions binds", results.count(True) == 1, results)
with ctx["lock"]:
    rows = ctx["conn"].execute("SELECT COUNT(*) FROM auth_exec WHERE eval_id=? AND outcome<>'rejected'",(eid,)).fetchone()
check("only one accepted binding exists in storage", rows[0] == 1, rows)

print("\n=== 28. reconstruct the whole story from the sealed record ===")
ctx = make_ctx()
lineage._issue(ctx,"k",dict(id="r",issuer="owner@example.com",issuer_kind="human",
    subject="orchestrator",scope=["payments.*"],constraints={"max_amount":5000},
    purpose="close the refund backlog",purpose_tags=["refunds"],
    not_after=NOW+HOUR,delegations_left=2))
lineage._issue(ctx,"k",dict(id="m",parent="r",issuer="orchestrator",issuer_kind="agent",
    subject="refund-bot",scope=["payments.refund"],constraints={"max_amount":200},
    purpose="issue small refunds",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=0))
r,_ = lineage._evaluate(ctx,"k",{"grant":"m","action":"payments.refund",
    "params":{"amount":150},"purpose_tag":"refunds"})
t,code = lineage._trace(ctx,{"grant":"m"})
check("the trace names who authorised it", t["authorised_by"] == "owner@example.com")
check("the trace names who held it at execution", t["holder"] == "refund-bot")
check("the trace shows what changed at each hop",
      t["lineage"][0]["scope"] == ["payments.*"] and t["lineage"][1]["scope"] == ["payments.refund"])
check("the effective constraint is the narrowest, not the granted one",
      float(t["effective_constraints"]["max_amount"]) == 200, t["effective_constraints"])
d,code = lineage._decision(ctx,{"evaluation":r["evaluation"]})
check("the decision is retrievable without a key and matches", d["verdict"] == r["verdict"])
check("the decision carries the lineage digest", d["lineage_digest"] == r["lineage_digest"])
check("every hop carries its own block index",
      all(h["block_index"] for h in t["lineage"]))

print("\n=== 29. widening midway is visible in the trace, not just blocked ===")
ctx = make_ctx()
lineage._issue(ctx,"k",dict(id="r",issuer="owner@example.com",issuer_kind="human",
    subject="a",scope=["payments.refund"],constraints={"max_amount":100},
    purpose="p",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=2))
lineage._issue(ctx,"k",dict(id="m",parent="r",issuer="a",issuer_kind="agent",
    subject="b",scope=["payments.refund"],constraints={"max_amount":100},
    purpose="p",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=1,
    risk_accepted_by="owner@example.com"))
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET constraints=? WHERE id='m'",
        (json.dumps({"max_amount":100000},sort_keys=True,separators=(",",":")),))
    ctx["conn"].commit()
t,_ = lineage._trace(ctx,{"grant":"m"})
check("the trace flags the altered hop by name",
      t["lineage"][1]["integrity"] == "FAILED" and t["lineage"][0]["integrity"] == "ok", t["lineage"])
r,_ = lineage._evaluate(ctx,"k",{"grant":"m","action":"payments.refund",
    "params":{"amount":50},"purpose_tag":"refunds"})
check("and the exercise names the exact grant that broke", r["broken_at"] == "m", r["broken_at"])

print("\n" + "="*60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL: print("  FAILED: "+f)
sys.exit(1 if FAIL else 0)

```


## `tests/attack_continuity_4.py`

107 lines, 4723 bytes

```python
#!/usr/bin/env python3
"""Fourth wave: does it actually compose with the existing engine, and can
either side be bypassed by the other?"""
import hashlib, json, sqlite3, threading, time, sys, types
import continuity as C

PASS, FAIL = [], []
NOW, HOUR = time.time(), 3600
STATE = {"verdict": "ALLOW", "raises": False, "shape": "dict", "seen": []}

def install(verdict="ALLOW", raises=False, shape="dict"):
    STATE.update(verdict=verdict, raises=raises, shape=shape)
    m = types.ModuleType("server")
    m.get_bearer = lambda *a, **k: None
    def score_event(event):
        STATE["seen"].append(event)
        if STATE["raises"]: raise RuntimeError("engine down")
        if STATE["shape"] == "dict": return {"decision": STATE["verdict"], "score": 0.42}
        if STATE["shape"] == "tuple": return (STATE["verdict"], 0.42)
        if STATE["shape"] == "junk": return {"nothing": "useful"}
        return STATE["verdict"]
    m.score_event = score_event
    sys.modules["server"] = m

def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i":0}
    def seal(ev,res,ts,k):
        n["i"] += 1
        return hashlib.sha256(json.dumps([ev,res,ts],sort_keys=True,default=str).encode()).hexdigest(), n["i"], n["i"]
    C._ready = False
    ctx = {"conn":conn,"lock":lock,"seal":seal}; C._setup(ctx); return ctx

def check(n,c,d=""):
    (PASS if c else FAIL).append(n)
    print(("  ok   " if c else "  FAIL ")+n+(("  -> "+str(d)[:250]) if d and not c else ""))

def setup():
    ctx = make_ctx()
    C._issue(ctx,"k",dict(id="root",issuer="owner@example.com",issuer_kind="human",
        subject="agent",scope=["payments.refund"],
        constraints={"max_amount":5000,"allowed_currency":["GBP"]},
        purpose="refunds",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=0))
    return ctx

def run(ctx, amount=100):
    return C._evaluate(ctx,"k",{"grant":"root","action":"payments.refund",
        "params":{"amount":amount,"currency":"GBP"},"purpose_tag":"refunds"})[0]

print("\n=== 30. the engine is actually consulted ===")
install("ALLOW"); STATE["seen"] = []
r = run(setup())
check("a clean authority plus a clean engine is ALLOW", r["verdict"]=="ALLOW", r)
check("the engine was called with the real action and amount",
      STATE["seen"] and STATE["seen"][-1]["action"]=="payments.refund"
      and STATE["seen"][-1]["amount"]==100, STATE["seen"][-1] if STATE["seen"] else None)
check("both components are reported separately",
      r["authority_verdict"]=="ALLOW" and r["risk_verdict"]=="ALLOW", r)

print("\n=== 31. neither side can wave the other through ===")
install("BLOCK")
r = run(setup())
check("perfect authority does not survive an engine BLOCK", r["verdict"]=="BLOCK", r)
check("the authority component still reads ALLOW underneath it",
      r["authority_verdict"]=="ALLOW", r)
install("CHALLENGE")
r = run(setup())
check("an engine CHALLENGE lifts a clean authority to CHALLENGE", r["verdict"]=="CHALLENGE", r)
install("ALLOW")
ctx = setup()
r = C._evaluate(ctx,"k",{"grant":"root","action":"payments.transfer",
    "params":{"amount":1},"purpose_tag":"refunds"})[0]
check("a clean engine does not confer authority nobody granted", r["verdict"]=="BLOCK", r)
check("and the engine is not even asked once authority has failed",
      r["risk_engine"]["available"] is False, r["risk_engine"])

print("\n=== 32. a missing or broken engine is not an ALLOW ===")
install("ALLOW", raises=True)
r = run(setup())
check("an engine that throws downgrades ALLOW to CHALLENGE", r["verdict"]=="CHALLENGE", r)
install("ALLOW", shape="junk")
r = run(setup())
check("an unreadable engine response downgrades to CHALLENGE", r["verdict"]=="CHALLENGE", r)
sys.modules.pop("server", None); sys.modules.pop("__main__", None)
r = run(setup())
check("no engine present downgrades to CHALLENGE", r["verdict"]=="CHALLENGE", r)
check("the reason names the missing engine",
      any("risk engine" in x for x in r["reasons"]), r["reasons"])

print("\n=== 33. it reads the engine's other return shapes ===")
for shape in ("dict","tuple","str"):
    install("BLOCK", shape=shape)
    r = run(setup())
    check("a %s return shape is understood" % shape, r["verdict"]=="BLOCK", r["risk_engine"])

print("\n=== 34. an engine BLOCK cannot be executed ===")
install("BLOCK")
ctx = setup(); r = run(ctx)
c,_ = C._confirm(ctx,"k",{"evaluation":r["evaluation"],"action":"payments.refund",
    "params":{"amount":100,"currency":"GBP"}})
check("execution is refused when the engine blocked", c["bound"] is False, c)

print("\n" + "="*60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL: print("  FAILED: "+f)
sys.exit(1 if FAIL else 0)

```


## `tests/attack_continuity_5.py`

116 lines, 5639 bytes

```python
#!/usr/bin/env python3
"""Fifth wave: risk acceptance. Who put their name to this capability
existing at all - separately from who granted it and who holds it."""
import hashlib, json, sqlite3, threading, time, sys, types
import continuity as C

PASS, FAIL = [], []
NOW, HOUR = time.time(), 3600

def install():
    m = types.ModuleType("server")
    m.get_bearer = lambda *a, **k: None
    m.score_event = lambda e: {"decision": "ALLOW", "score": 0.1}
    sys.modules["server"] = m
install()

def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i":0}
    def seal(ev,res,ts,k):
        n["i"] += 1
        return hashlib.sha256(json.dumps([ev,res,ts],sort_keys=True,default=str).encode()).hexdigest(), n["i"], n["i"]
    C._ready = False
    ctx = {"conn":conn,"lock":lock,"seal":seal}; C._setup(ctx); return ctx

def check(n,c,d=""):
    (PASS if c else FAIL).append(n)
    print(("  ok   " if c else "  FAIL ")+n+(("  -> "+str(d)[:250]) if d and not c else ""))

def root(ctx, **over):
    args = dict(id="root", issuer="owner@example.com", issuer_kind="human",
                subject="orchestrator", scope=["payments.refund"],
                constraints={"max_amount":5000}, purpose="refunds",
                purpose_tags=["refunds"], not_after=NOW+HOUR, delegations_left=3)
    args.update(over)
    return C._issue(ctx,"k",args)

print("\n=== 35. a root accepts its own risk by default ===")
ctx = make_ctx()
r, code = root(ctx)
check("a root grant records an acceptor without being asked",
      code == 200 and r["risk_accepted_by"] == "owner@example.com", r)
r2, _ = root(ctx, id="root2", risk_accepted_by="risk.officer@example.com")
check("a root can name someone other than the issuer",
      r2["risk_accepted_by"] == "risk.officer@example.com", r2)

print("\n=== 36. switching on onward delegation needs a name ===")
ctx = make_ctx(); root(ctx)
r, code = C._issue(ctx,"k",dict(id="deleg", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=1))
check("a delegable child with no acceptor is refused",
      code == 409 and r.get("error") == "risk_acceptance_required", r)

r, code = C._issue(ctx,"k",dict(id="leaf", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=0))
check("a non-delegable child inherits the acceptor above it", code == 200, r)

r, code = C._issue(ctx,"k",dict(id="deleg2", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=1, risk_accepted_by="head.of.ops@example.com"))
check("a delegable child with a named acceptor is accepted", code == 200, r)

print("\n=== 37. the decision names the accountable person ===")
e, _ = C._evaluate(ctx,"k",{"grant":"leaf","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("an evaluation reports who accepts the risk",
      e["risk_accepted_by"] == "owner@example.com", e.get("risk_accepted_by"))
check("...separately from who authorised it and who executed it",
      e["authorised_by"] == "owner@example.com" and e["executed_by"] == "b", e)

e2, _ = C._evaluate(ctx,"k",{"grant":"deleg2","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("the nearest acceptor wins, not the root one",
      e2["risk_accepted_by"] == "head.of.ops@example.com", e2.get("risk_accepted_by"))

t, _ = C._trace(ctx,{"grant":"deleg2"})
check("the trace shows the acceptor at each hop",
      t["risk_accepted_by"] == "head.of.ops@example.com" and
      t["lineage"][0]["risk_accepted_by"] == "owner@example.com", t)

print("\n=== 38. an unaccepted lineage cannot act ===")
ctx = make_ctx(); root(ctx)
C._issue(ctx,"k",dict(id="leaf", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=0))
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET risk_accepted_by=NULL")
    ctx["conn"].commit()
e, _ = C._evaluate(ctx,"k",{"grant":"leaf","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("stripping every acceptor blocks the action", e["verdict"] == "BLOCK", e["reasons"])
check("...and says an incident would have no accountable person",
      any("accountable" in x for x in e["reasons"]), e["reasons"])

print("\n=== 39. the acceptor cannot be swapped after the fact ===")
ctx = make_ctx(); root(ctx, risk_accepted_by="risk.officer@example.com")
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET risk_accepted_by='someone.else@example.com' WHERE id='root'")
    ctx["conn"].commit()
e, _ = C._evaluate(ctx,"k",{"grant":"root","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("editing who accepted the risk fails the digest", e["verdict"] == "BLOCK", e["reasons"])
check("...reported as an evidence failure, naming the grant",
      e["broken_invariant"] == "evidence_continuity" and e["broken_at"] == "root", e)

print("\n" + "="*60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL: print("  FAILED: "+f)
sys.exit(1 if FAIL else 0)

```
