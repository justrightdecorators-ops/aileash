# Codebase — part 12 of 53

Contains:
- `modules/gateway.py`
- `modules/genesis.py`
- `modules/grade.py`


## `modules/gateway.py`

908 lines, 44082 bytes

```python
"""
modules/gateway.py  v1.0.0  -  Seal at the wire, and the AI-Decision-Receipt header

    Arm:       https://sebbi.pro/x/arm/status
    Page:      https://sebbi.pro/gateway
    Standard:  https://sebbi.pro/standard/ai-decision-receipt
    OpenAI:    https://sebbi.pro/g/openai/v1        (or /g/<gateway token>/openai/v1)
    Anthropic: https://sebbi.pro/g/anthropic        (or /g/<gateway token>/anthropic)

OPTION 1 - SEAL AT THE WIRE
---------------------------
A customer changes one setting: the base URL their app uses to reach OpenAI or
Anthropic. Every call then passes through sebbi.pro:

  1. the request is fingerprinted (SHA-256) - the prompt itself is never stored
  2. it is scored by the real engine (server.govern - same scoring, billing,
     trial and rate rules as /api/govern) and sealed into the chain
  3. BLOCK stops it here: the provider is never called
  4. ALLOW (and CHALLENGE, unless the customer asks for challenges to be held)
     is forwarded to the provider over TLS and the answer streamed straight
     back, token by token
  5. the request and response fingerprints go to the Bitcoin notary

The customer's provider key passes through untouched and is never stored.

OPTION 2 - THE AI-DECISION-RECEIPT HEADER
-----------------------------------------
Every governed response carries one standard header (RFC 8941 dictionary):

  AI-Decision-Receipt: v=1, issuer="sebbi.pro", decision=ALLOW, score=0.12,
      block=1042, seal="9f2c...", req="<sha256>", call="GC-...",
      verify="https://sebbi.pro/forever?block=1042"

It is added to gateway responses and to every /api/govern response, so any
system using sebbi.pro carries a receipt anyone can check against Bitcoin.
The format is published as an open standard at /standard/ai-decision-receipt.

SAFETY
------
server.py is not edited. The chain is written only through server.govern -
the same path every /api/govern call uses. /api/govern responses gain one
header; their body is untouched. Upstream hosts are fixed (no open proxy).
"""

import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone

VERSION = "1.0.0"
SITE = "https://sebbi.pro"
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "call"), ("POST", "parse"), ("GET", "")}

UPSTREAM = {
    "openai": os.environ.get("GATEWAY_UPSTREAM_OPENAI", "https://api.openai.com").rstrip("/"),
    "anthropic": os.environ.get("GATEWAY_UPSTREAM_ANTHROPIC", "https://api.anthropic.com").rstrip("/"),
}
MAX_BODY = 25 * 1024 * 1024
UPSTREAM_TIMEOUT = int(os.environ.get("GATEWAY_TIMEOUT", "600"))
HOP = {"host", "content-length", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
       "trailer", "transfer-encoding", "upgrade", "accept-encoding", "x-forwarded-for", "x-forwarded-proto",
       "x-forwarded-host", "x-real-ip", "forwarded", "cf-connecting-ip", "x-request-start"}
RESP_DROP = {"content-length", "connection", "keep-alive", "transfer-encoding", "trailer", "upgrade",
             "proxy-authenticate", "alt-svc", "strict-transport-security"}
PATH_RE = re.compile(r"^/[A-Za-z0-9/_.:\-]{0,300}$")
TOKEN_RE = re.compile(r"^gw_[0-9a-f]{32}$")
CALL_RE = re.compile(r"^GC-[A-Z2-9]{10}$")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
HEADER = "AI-Decision-Receipt"

_state = {"pages": False, "wire": False, "headers": False, "mcp": False, "calls": 0, "blocked": 0,
          "forwarded": 0, "upstream_errors": 0, "receipts_added": 0, "last_error": None}
_lock = threading.Lock()
_count_lock = threading.Lock()


def _inc(k):
    with _count_lock:
        _state[k] += 1


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _db(sql, args=(), one=False, write=False):
    s = _srv()
    with s._db_lock:
        cur = s._conn.execute(sql, args)
        if write:
            s._conn.commit()
            return cur.lastrowid
        return cur.fetchone() if one else cur.fetchall()


def _setup():
    s = _srv()
    with s._db_lock:
        s._conn.execute("CREATE TABLE IF NOT EXISTS gateway_token(token TEXT PRIMARY KEY, key_hash TEXT, api_key TEXT,"
                        "label TEXT, created REAL, revoked INTEGER DEFAULT 0)")
        s._conn.execute("CREATE TABLE IF NOT EXISTS gateway_call(id TEXT PRIMARY KEY, ts REAL, key_hash TEXT,"
                        "provider TEXT, model TEXT, endpoint TEXT, decision TEXT, score REAL, block_index INTEGER,"
                        "audit_hash TEXT, req_sha256 TEXT, resp_sha256 TEXT, status INTEGER, ms INTEGER,"
                        "resp_bytes INTEGER, notary_req TEXT, notary_resp TEXT)")
        s._conn.execute("CREATE INDEX IF NOT EXISTS idx_gw_key ON gateway_call(key_hash, ts)")
        s._conn.commit()


def _kh(key):
    return hashlib.sha256(("gw|" + key).encode()).hexdigest()[:24]


def _new_call():
    raw = secrets.token_bytes(10)
    return "GC-" + "".join(ALPHABET[b % len(ALPHABET)] for b in raw)


# ---------------------------------------------------------------------------
# the receipt header (option 2)
# ---------------------------------------------------------------------------

def _sf_str(v):
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def receipt_header(decision, score, block, seal, req=None, call=None):
    parts = ["v=1", "issuer=" + _sf_str("sebbi.pro")]
    if decision and re.match(r"^[A-Z_]{2,20}$", str(decision)):
        parts.append("decision=" + str(decision))
    try:
        parts.append("score=%s" % ("%.3f" % float(score)).rstrip("0").rstrip("."))
    except (TypeError, ValueError):
        pass
    if block is not None:
        parts.append("block=%d" % int(block))
    if seal:
        parts.append("seal=" + _sf_str(seal))
    if req:
        parts.append("req=" + _sf_str(req))
    if call:
        parts.append("call=" + _sf_str(call))
    if block is not None:
        parts.append("verify=" + _sf_str("%s/forever?block=%d" % (SITE, int(block))))
    return ", ".join(parts)


def parse_receipt(value):
    """Parse an AI-Decision-Receipt header value (RFC 8941 dictionary subset)."""
    out = {}
    for m in re.finditer(r'\s*([a-z][a-z0-9_\-.*]*)\s*(?:=\s*("(?:[^"\\]|\\.)*"|[^,\s]+))?\s*(?:,|$)', str(value or "")):
        k, v = m.group(1), m.group(2)
        if v is None:
            out[k] = True
        elif v.startswith('"'):
            out[k] = re.sub(r'\\(.)', r'\1', v[1:-1])
        else:
            try:
                out[k] = int(v) if re.match(r"^-?\d+$", v) else (float(v) if re.match(r"^-?\d+\.\d+$", v) else v)
            except ValueError:
                out[k] = v
    return out


# ---------------------------------------------------------------------------
# the wire (option 1)
# ---------------------------------------------------------------------------

def _resolve_key(h, token):
    s = _srv()
    if token:
        if not TOKEN_RE.match(token):
            return None, "bad_gateway_token"
        r = _db("SELECT api_key, revoked FROM gateway_token WHERE token=?", (token,), one=True)
        if not r or r[1]:
            return None, "gateway_token_not_found"
        key = r[0]
    else:
        key = (h.headers.get("X-Sebbi-Key") or "").strip()
        if not key:
            return None, "sebbi_key_required"
    try:
        if not s.get_key(key):
            return None, "invalid_sebbi_key"
    except Exception:
        return None, "invalid_sebbi_key"
    return key, None


def _err(h, provider, status, kind, message, receipt=None):
    if provider == "anthropic":
        body = {"type": "error", "error": {"type": "permission_error" if status == 403 else kind, "message": message},
                "sebbi": {"error": kind}}
    else:
        body = {"error": {"message": message, "type": kind, "code": kind}}
    raw = json.dumps(body).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(raw)))
    if receipt:
        h.send_header(HEADER, receipt)
    h.send_header("Access-Control-Expose-Headers", HEADER + ", AI-Decision-Call")
    h.send_header("Connection", "close")
    h.end_headers()
    h.wfile.write(raw)
    h.close_connection = True


def _num(v, default=0.0, lo=0.0, hi=1e12):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def _event(h, provider, model, endpoint, req_digest, body_json):
    uid = (h.headers.get("X-Sebbi-User") or "").strip()
    if not uid and isinstance(body_json, dict):
        uid = str(body_json.get("user") or body_json.get("safety_identifier") or
                  ((body_json.get("metadata") or {}).get("user_id") if isinstance(body_json.get("metadata"), dict) else "") or "")
    uid = re.sub(r"[\x00-\x1f]", "", uid)[:120] or "gateway"
    country = (h.headers.get("X-Sebbi-Country") or "UK").strip().upper()[:2] or "UK"
    ev = {"user_id": uid, "action": (h.headers.get("X-Sebbi-Action") or "ai_call").strip()[:60] or "ai_call",
          "amount": _num(h.headers.get("X-Sebbi-Amount"), 0.0),
          "country": country,
          "device_id": ((h.headers.get("X-Sebbi-Device") or "").strip() or (uid if uid != "gateway" else "gateway"))[:120],
          "anomaly": _num(h.headers.get("X-Sebbi-Anomaly"), 0.0, 0.0, 1.0),
          "device_risk": _num(h.headers.get("X-Sebbi-Device-Risk"), 0.0, 0.0, 1.0),
          "provider": provider, "model": str(model or "")[:80], "endpoint": endpoint[:120],
          "request_sha256": req_digest, "via": "sebbi-gateway/1"}
    pack = (h.headers.get("X-Sebbi-Pack") or "").strip()
    if pack:
        ev["pack"] = pack[:80]
    return ev


def _notarise(key, digests, label, ip):
    try:
        try:
            from modules import notary as N
        except Exception:
            import notary as N
        r, st = N.stamp(digests, label, key, ip)
        if st == 200:
            return [x["code"] for x in r.get("receipts", [])]
    except Exception as e:
        _state["last_error"] = "notary: %s" % str(e)[:120]
    return []


def _client_ip(h):
    xff = h.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()[:64]
    try:
        return str(h.client_address[0])[:64]
    except Exception:
        return "unknown"


def serve_wire(h):
    """Handle one /g/... request end to end. Always answers."""
    t0 = time.time()
    raw_path = h.path
    path, _, query = raw_path.partition("?")
    parts = path.split("/")  # ['', 'g', provider|token, ...]
    token = None
    if len(parts) > 2 and parts[2].startswith("gw_"):
        token = parts[2]
        parts = parts[:2] + parts[3:]
    provider = parts[2] if len(parts) > 2 else ""
    rest = "/" + "/".join(parts[3:]) if len(parts) > 3 else "/"
    if provider not in UPSTREAM:
        return _err(h, "openai", 404, "unknown_provider", "Use /g/openai/v1 or /g/anthropic/v1.")
    if not PATH_RE.match(rest) or ".." in rest:
        return _err(h, provider, 400, "bad_path", "That path is not allowed.")
    key, why = _resolve_key(h, token)
    if not key:
        return _err(h, provider, 401, why, "Add your sebbi.pro key as the X-Sebbi-Key header, or use your gateway "
                                           "URL from https://sebbi.pro/gateway.")
    n = int(h.headers.get("Content-Length") or 0)
    if h.command in ("POST", "PUT", "PATCH") and not h.headers.get("Content-Length"):
        return _err(h, provider, 411, "length_required", "Send a Content-Length header.")
    if n > MAX_BODY:
        return _err(h, provider, 413, "too_large", "Request body over 25 MB.")
    body = h.rfile.read(n) if n else b""
    req_digest = hashlib.sha256(body).hexdigest()
    body_json = None
    model = None
    if body and "json" in (h.headers.get("Content-Type") or "json"):
        try:
            body_json = json.loads(body)
            model = body_json.get("model") if isinstance(body_json, dict) else None
        except Exception:
            body_json = None
    s = _srv()
    call_id = _new_call()
    _inc("calls")
    try:
        result, status = s.govern(_event(h, provider, model, rest, req_digest, body_json), key)
    except Exception as e:
        _state["last_error"] = "govern: %s" % str(e)[:150]
        return _err(h, provider, 500, "sebbi_error", "Governance check failed, so the call was not sent.")
    if status != 200:
        msg = result.get("message") or result.get("error") or "Governance check refused the call."
        if result.get("checkout_url"):
            msg += " " + str(result["checkout_url"])
        return _err(h, provider, status, str(result.get("error") or "sebbi_refused"), msg)
    dec = result.get("decision")
    block, seal = result.get("block_index"), result.get("audit_hash")
    rcpt = receipt_header(dec, result.get("score"), block, seal, req_digest, call_id)
    kh = _kh(key)
    hold_challenge = (h.headers.get("X-Sebbi-On-Challenge") or "").strip().lower() == "block"
    if dec == "BLOCK" or (dec == "CHALLENGE" and hold_challenge):
        _inc("blocked")
        _db("INSERT INTO gateway_call(id,ts,key_hash,provider,model,endpoint,decision,score,block_index,audit_hash,"
            "req_sha256,status,ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (call_id, t0, kh, provider, str(model or "")[:80], rest[:120], dec, result.get("score"), block, seal,
             req_digest, 403, int((time.time() - t0) * 1000)), write=True)
        why = ", ".join(result.get("reasons") or []) or "risk score"
        h_extra = {"AI-Decision-Call": call_id}
        if dec == "CHALLENGE" and result.get("challenge_url"):
            h_extra["AI-Decision-Challenge"] = result["challenge_url"]
        _err_with(h, provider, 403, "sebbi_blocked",
                  "Stopped by sebbi.pro before reaching the provider (%s: %s). Receipt: %s/x/gateway/call?id=%s"
                  % (dec, why, SITE, call_id), rcpt, h_extra)
        threading.Thread(target=_after, args=(call_id, key, req_digest, None, _client_ip(h)), daemon=True).start()
        return

    # forward
    up = urllib.parse.urlsplit(UPSTREAM[provider])
    fwd = {}
    for k, v in h.headers.items():
        lk = k.lower()
        if lk in HOP or lk.startswith("x-sebbi-"):
            continue
        fwd[k] = v
    fwd["Accept-Encoding"] = "identity"
    if body:
        fwd["Content-Length"] = str(len(body))
    target = (up.path.rstrip("/") + rest) + (("?" + query) if query else "")
    try:
        Conn = http.client.HTTPSConnection if up.scheme == "https" else http.client.HTTPConnection
        conn = Conn(up.hostname, up.port, timeout=UPSTREAM_TIMEOUT)
        conn.request(h.command, target, body=body or None, headers=fwd)
        resp = conn.getresponse()
    except Exception as e:
        _inc("upstream_errors")
        _db("INSERT INTO gateway_call(id,ts,key_hash,provider,model,endpoint,decision,score,block_index,audit_hash,"
            "req_sha256,status,ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (call_id, t0, kh, provider, str(model or "")[:80], rest[:120], dec, result.get("score"), block, seal,
             req_digest, 502, int((time.time() - t0) * 1000)), write=True)
        return _err_with(h, provider, 502, "upstream_unreachable",
                         "The provider could not be reached (%s). The decision was sealed; nothing was sent twice."
                         % type(e).__name__, rcpt, {"AI-Decision-Call": call_id})
    _inc("forwarded")
    h.send_response(resp.status)
    for k, v in resp.getheaders():
        if k.lower() in RESP_DROP:
            continue
        h.send_header(k, v)
    h.send_header(HEADER, rcpt)
    h.send_header("AI-Decision-Call", call_id)
    h.send_header("Access-Control-Expose-Headers", HEADER + ", AI-Decision-Call")
    h.send_header("Connection", "close")
    h.end_headers()
    h.close_connection = True
    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(8192)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            h.wfile.write(chunk)
            try:
                h.wfile.flush()
            except Exception:
                pass
    except Exception as e:
        _state["last_error"] = "stream: %s" % type(e).__name__
    finally:
        try:
            conn.close()
        except Exception:
            pass
    resp_digest = digest.hexdigest()
    _db("INSERT INTO gateway_call(id,ts,key_hash,provider,model,endpoint,decision,score,block_index,audit_hash,"
        "req_sha256,resp_sha256,status,ms,resp_bytes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (call_id, t0, kh, provider, str(model or "")[:80], rest[:120], dec, result.get("score"), block, seal,
         req_digest, resp_digest, resp.status, int((time.time() - t0) * 1000), total), write=True)
    threading.Thread(target=_after, args=(call_id, key, req_digest, resp_digest, _client_ip(h)), daemon=True).start()


def _err_with(h, provider, status, kind, message, receipt, extra):
    if provider == "anthropic":
        body = {"type": "error", "error": {"type": "permission_error" if status == 403 else "api_error", "message": message},
                "sebbi": {"error": kind}}
    else:
        body = {"error": {"message": message, "type": kind, "code": kind}}
    raw = json.dumps(body).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(raw)))
    h.send_header(HEADER, receipt)
    for k, v in (extra or {}).items():
        h.send_header(k, v)
    h.send_header("Access-Control-Expose-Headers", HEADER + ", AI-Decision-Call")
    h.send_header("Connection", "close")
    h.end_headers()
    h.wfile.write(raw)
    h.close_connection = True


def _after(call_id, key, req_digest, resp_digest, ip):
    digests = [req_digest] + ([resp_digest] if resp_digest else [])
    codes = _notarise(key, digests, "gateway " + call_id, ip)
    if codes:
        try:
            _db("UPDATE gateway_call SET notary_req=?, notary_resp=? WHERE id=?",
                (codes[0], codes[1] if len(codes) > 1 else None, call_id), write=True)
        except Exception:
            pass


def call_record(cid):
    cid = str(cid or "").strip().upper()
    if not CALL_RE.match(cid):
        return {"error": "bad_call_id", "message": "Call ids look like GC-7Q2M9X4KDP."}, 400
    r = _db("SELECT id,ts,provider,model,endpoint,decision,score,block_index,audit_hash,req_sha256,resp_sha256,status,"
            "ms,resp_bytes,notary_req,notary_resp FROM gateway_call WHERE id=?", (cid,), one=True)
    if not r:
        return {"error": "not_found"}, 404
    out = {"call": r[0], "utc": _iso(r[1]), "provider": r[2], "model": r[3], "endpoint": r[4], "decision": r[5],
           "score": r[6], "block": r[7], "seal": r[8], "request_sha256": r[9], "response_sha256": r[10],
           "upstream_status": r[11] if r[5] != "BLOCK" else None, "stopped_before_provider": r[11] == 403 and r[10] is None,
           "ms": r[12], "response_bytes": r[13],
           "receipt_header": receipt_header(r[5], r[6], r[7], r[8], r[9], r[0]),
           "verify_decision": "%s/forever?block=%s" % (SITE, r[7]) if r[7] is not None else None,
           "notary": {"request": r[14], "response": r[15]},
           "how_to_check": "SHA-256 the exact request body you sent and the exact response bytes you received; they "
                           "must equal request_sha256 and response_sha256. The decision block checks against Bitcoin at "
                           "verify_decision; the fingerprints are timestamped through the notary receipts."}
    if r[14]:
        out["notary"]["request_receipt"] = "%s/n/%s" % (SITE, r[14])
    if r[15]:
        out["notary"]["response_receipt"] = "%s/n/%s" % (SITE, r[15])
    return out, 200


def new_token(api_key, label=None):
    tok = "gw_" + secrets.token_hex(16)
    _db("INSERT INTO gateway_token(token,key_hash,api_key,label,created) VALUES(?,?,?,?,?)",
        (tok, _kh(api_key), api_key, re.sub(r"[\x00-\x1f<>]", "", str(label or ""))[:60] or None, time.time()), write=True)
    return {"token": tok, "openai_base_url": "%s/g/%s/openai/v1" % (SITE, tok),
            "anthropic_base_url": "%s/g/%s/anthropic" % (SITE, tok),
            "note": "Keep this URL private: it bills your sebbi.pro key. Your OpenAI or Anthropic key still goes in "
                    "your app as normal and passes through untouched. Revoke any time: POST /x/gateway/revoke {token}."}


# ---------------------------------------------------------------------------
# installing
# ---------------------------------------------------------------------------

BACKLOG = int(os.environ.get("SERVER_BACKLOG", "512"))


def _raise_backlog(h):
    """Python's HTTPServer listens with a queue of 5 new connections, so a burst of
    simultaneous clients gets refused. Re-listening on the live socket raises the
    queue in place; nothing is restarted and no connection is dropped."""
    _state["backlog"] = True
    try:
        sock = h.server.socket
        sock.listen(BACKLOG)
        _state["backlog_size"] = BACKLOG
    except Exception as e:
        _state["last_error"] = "backlog: %s" % str(e)[:120]


def _install_wire():
    if _state["wire"]:
        return True
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_gateway_wire", False):
        _state["wire"] = True
        return True

    def wrap(name):
        orig = getattr(H, name, None)

        def method(self):
            if not _state.get("backlog"):
                _raise_backlog(self)
            p = (self.path or "").split("?")[0]
            if p.startswith("/g/"):
                try:
                    return serve_wire(self)
                except Exception as e:
                    _state["last_error"] = "wire: %s" % str(e)[:150]
                    try:
                        return _err(self, "openai", 500, "gateway_error", "Gateway error.")
                    except Exception:
                        return
            try:
                if p in ("/gateway", "/gateway/"):
                    return _send(self, _gateway_page(), "text/html; charset=utf-8")
                if p in ("/standard/ai-decision-receipt", "/standard/ai-decision-receipt/"):
                    return _send(self, _standard_page(), "text/html; charset=utf-8")
            except Exception as e:
                _state["last_error"] = "page: %s" % str(e)[:150]
            if orig is None:
                self.send_error(405)
                return
            return orig(self)
        return method

    H.do_GET = wrap("do_GET")
    H.do_POST = wrap("do_POST")
    H.do_DELETE = wrap("do_DELETE")
    H._gateway_wire = True
    _state["wire"] = True
    _state["pages"] = True
    return True


class _Out(object):
    """Adds the receipt header to /api/govern answers. Everything else passes straight through."""

    def __init__(self, real, handler):
        self.real, self.h = real, handler
        self.buf = bytearray()
        self.mode = None

    def write(self, data):
        if self.mode == "pass":
            return self.real.write(data)
        self.buf += data
        if self.mode is None:
            end = self.buf.find(b"\r\n\r\n")
            if end < 0:
                if len(self.buf) > 65536:
                    self._go_pass()
                return len(data)
            head = bytes(self.buf[:end]).lower()
            p = (getattr(self.h, "path", "") or "").split("?")[0].rstrip("/")
            if (getattr(self.h, "command", "") == "POST" and p in ("/api/govern", "/govern")
                    and b"application/json" in head and HEADER.lower().encode() not in head):
                self.mode = "hold"
            else:
                self._go_pass()
        elif len(self.buf) > 1024 * 1024:
            self._go_pass()
        return len(data)

    def _go_pass(self):
        self.mode = "pass"
        if self.buf:
            self.real.write(bytes(self.buf))
        self.buf = bytearray()

    def flush(self):
        if self.mode == "pass":
            try:
                self.real.flush()
            except Exception:
                pass

    @property
    def closed(self):
        return getattr(self.real, "closed", False)

    def __getattr__(self, name):
        return getattr(self.real, name)

    def finish(self):
        if self.mode == "pass" or not self.buf:
            return
        raw = bytes(self.buf)
        self.buf = bytearray()
        end = raw.find(b"\r\n\r\n")
        if self.mode != "hold" or end < 0:
            self.real.write(raw)
            return
        head, body = raw[:end], raw[end + 4:]
        try:
            d = json.loads(body.decode("utf-8"))
            if isinstance(d, dict) and d.get("block_index") is not None and d.get("decision"):
                rc = receipt_header(d.get("decision"), d.get("score"), d.get("block_index"), d.get("audit_hash"))
                head = head + ("\r\n%s: %s\r\nAccess-Control-Expose-Headers: %s" % (HEADER, rc, HEADER)).encode()
                _inc("receipts_added")
        except Exception:
            pass
        self.real.write(head + b"\r\n\r\n" + body)
        try:
            self.real.flush()
        except Exception:
            pass


def _install_headers():
    if _state["headers"]:
        return True
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_gateway_headers", False):
        _state["headers"] = True
        return True
    original = H.handle_one_request

    def handle_one_request(self):
        real = self.wfile
        out = _Out(real, self)
        self.wfile = out
        try:
            original(self)
        finally:
            self.wfile = real
            try:
                out.finish()
            except Exception as e:
                _state["last_error"] = "header: %s" % str(e)[:150]
                try:
                    if out.buf:
                        real.write(bytes(out.buf))
                except Exception:
                    pass

    H.handle_one_request = handle_one_request
    H._gateway_headers = True
    _state["headers"] = True
    return True


MCP_TOOL = {"name": "sebbi_gateway_setup",
            "description": "Put every OpenAI or Anthropic call the customer's app makes through sebbi.pro with a one-line "
                           "change: returns a private gateway base URL for their sebbi.pro key and the exact line to change "
                           "for their stack. Every call is then scored, sealed, blocked if needed, and carries an "
                           "AI-Decision-Receipt header.",
            "inputSchema": {"type": "object", "required": ["api_key"],
                            "properties": {"api_key": {"type": "string"},
                                           "stack": {"type": "string", "description": "e.g. 'Python OpenAI SDK', 'Node Anthropic SDK', 'LangChain', 'curl'"},
                                           "label": {"type": "string"}}}}


def _setup_lines(tok, stack):
    st = (stack or "").lower()
    o, a = tok["openai_base_url"], tok["anthropic_base_url"]
    if "anthropic" in st or "claude" in st:
        if "node" in st or "js" in st or "typescript" in st:
            return "new Anthropic({ baseURL: '%s' })" % a
        return "anthropic.Anthropic(base_url='%s')" % a
    if "node" in st or "js" in st or "typescript" in st:
        return "new OpenAI({ baseURL: '%s' })" % o
    if "langchain" in st:
        return "ChatOpenAI(base_url='%s')" % o
    if "curl" in st:
        return "curl %s/chat/completions -H 'Authorization: Bearer $OPENAI_API_KEY' ..." % o
    return "OpenAI(base_url='%s')" % o


def _install_mcp():
    if _state["mcp"]:
        return True
    try:
        try:
            from modules import mcp as M
        except Exception:
            import mcp as M
    except Exception as e:
        _state["last_error"] = "mcp: %s" % e
        return False
    if getattr(M, "_gateway_tool", False):
        _state["mcp"] = True
        return True
    if MCP_TOOL["name"] not in {t["name"] for t in M.TOOLS}:
        M.TOOLS.append(MCP_TOOL)
    original = M._call

    def _call(name, a, ip, agent):
        if name != MCP_TOOL["name"]:
            return original(name, a, ip, agent)
        a = a or {}
        key = str(a.get("api_key") or "").strip()
        if not key or not _srv().get_key(key):
            return {"error": "invalid_api_key", "message": "Open an account first with sebbi_create_account."}, 401
        tok = new_token(key, a.get("label"))
        tok["change_this_line"] = _setup_lines(tok, a.get("stack"))
        tok["what_changes"] = ("Every AI call now goes through sebbi.pro: scored, sealed, stopped if BLOCK, and answered "
                               "with an AI-Decision-Receipt header the customer can check at https://sebbi.pro/forever.")
        return tok, 200

    M._call = _call
    note = (" To govern every OpenAI or Anthropic call an app makes with a one-line change, call sebbi_gateway_setup.")
    if isinstance(getattr(M, "INSTRUCTIONS", None), str) and note not in M.INSTRUCTIONS:
        M.INSTRUCTIONS = M.INSTRUCTIONS + note
    M._gateway_tool = True
    _state["mcp"] = True
    return True


def arm(ctx=None):
    with _lock:
        _setup()
        _install_wire()
        _install_headers()
        try:
            _install_mcp()
        except Exception as e:
            _state["last_error"] = "mcp: %s" % str(e)[:150]


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

def _send(h, body, ctype):
    if isinstance(body, str):
        body = body.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "public, max-age=120")
    h.end_headers()
    if getattr(h, "command", "GET") != "HEAD":
        h.wfile.write(body)


def _N():
    try:
        from modules import notary as N
    except Exception:
        import notary as N
    return N


def _gateway_page():
    N = _N()
    body = r"""<title>Gateway — every AI call governed with one line — sebbi.pro</title>
<meta name="description" content="Change one line and every OpenAI or Anthropic call your app makes is scored, sealed, stopped if it should be, and answered with a receipt anyone can check against Bitcoin.">
</head><body>""" + N._TOP + r"""
<main class="wrap">
<section class="hero"><div class="kick"><i></i>GATEWAY · ONE LINE</div>
<h1>Change one line.<br><em>Govern every AI call.</em></h1>
<p>Point your app's OpenAI or Anthropic base URL at sebbi.pro. Every call is scored before it leaves, stopped if it should be, sealed into the chain, and answered with a receipt anyone can check against Bitcoin. No SDK. No integration project. Your provider key passes straight through.</p>
</section>
<section class="card"><h2>1 · Get your gateway URL</h2><p class="sub">Paste your sebbi.pro API key. No key yet? <a href="/connect">Get one free</a>. Your first 1,000 gateway calls are free; then add a card — 50p per device a month. Want us to set it all up? <a href="/pilot">Governed in 7 days — £495</a>.</p>
<div class="row"><input type="text" id="k" placeholder="sebbi.pro API key" autocomplete="off"><button class="btn b" id="go">Get my gateway URL</button></div>
<p class="msg" id="m"></p><pre id="out" hidden></pre></section>
<section class="card"><h2>2 · Change one line</h2>
<div class="tabs"><button class="on" data-t="py">Python · OpenAI</button><button data-t="node">Node · OpenAI</button><button data-t="anth">Python · Anthropic</button><button data-t="lc">LangChain</button><button data-t="curl">curl</button></div>
<pre id="code"></pre>
<p class="sub" style="margin-top:10px">Prefer to keep the URL clean? Use <code>https://sebbi.pro/g/openai/v1</code> and send your sebbi.pro key in an <code>X-Sebbi-Key</code> header instead.</p></section>
<section class="card"><h2>3 · Every answer carries a receipt</h2>
<p class="sub">Each response comes back with one standard header. Anyone can check the decision against Bitcoin.</p>
<pre>AI-Decision-Receipt: v=1, issuer="sebbi.pro", decision=ALLOW, score=0.12,
  block=1042, seal="9f2c…", req="&lt;sha256 of your request&gt;", call="GC-7Q2M9X4KDP",
  verify="https://sebbi.pro/forever?block=1042"</pre>
<p class="sub" style="margin-top:10px">The request and response fingerprints are timestamped in Bitcoin too, so you can later prove exactly what was asked and exactly what the AI answered. <a href="/standard/ai-decision-receipt">The open standard →</a></p></section>
<section class="card"><h2>What happens to each call</h2>
<div class="how"><div><b>01 · FINGERPRINT</b><p>The request is hashed. The prompt itself is never stored.</p></div>
<div><b>02 · DECIDE</b><p>The engine scores it ALLOW, CHALLENGE or BLOCK in milliseconds and seals the decision.</p></div>
<div><b>03 · GATE</b><p>BLOCK stops here — the provider is never called. ALLOW streams straight through, token by token.</p></div>
<div><b>04 · PROVE</b><p>Request and response fingerprints go into Bitcoin. The receipt header ties it all together.</p></div></div>
<p class="sub">Optional headers: <code>X-Sebbi-User</code> (who the call is for — also the billing meter unless you send a device), <code>X-Sebbi-Device</code> (billing meter), <code>X-Sebbi-Country</code>, <code>X-Sebbi-Pack</code> (your Signal Pack), <code>X-Sebbi-On-Challenge: block</code> (hold CHALLENGE calls).</p></section>
</main>""" + N._FOOT + r"""
<script>
const $=s=>document.querySelector(s);let O='https://sebbi.pro/g/<your gateway token>/openai/v1',A='https://sebbi.pro/g/<your gateway token>/anthropic',tab='py';
const C={py:()=>'from openai import OpenAI\n\nclient = OpenAI(base_url="'+O+'")   # the one line\n\nr = client.chat.completions.create(model="gpt-4o-mini",\n    messages=[{"role": "user", "content": "Hello"}])',
node:()=>"import OpenAI from 'openai';\n\nconst client = new OpenAI({ baseURL: '"+O+"' });   // the one line",
anth:()=>'import anthropic\n\nclient = anthropic.Anthropic(base_url="'+A+'")   # the one line',
lc:()=>'from langchain_openai import ChatOpenAI\n\nllm = ChatOpenAI(base_url="'+O+'")   # the one line',
curl:()=>"curl "+O+"/chat/completions \\\n  -H \"Authorization: Bearer $OPENAI_API_KEY\" -H 'Content-Type: application/json' \\\n  -d '{\"model\":\"gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}' -i"};
function draw(){$('#code').textContent=C[tab]()}
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{tab=b.dataset.t;document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('on',x===b));draw()});draw();
$('#go').onclick=async()=>{const k=$('#k').value.trim();if(!k){$('#m').className='msg err';$('#m').textContent='Paste your sebbi.pro API key first.';return}
 $('#m').className='msg';$('#m').textContent='Creating your gateway URL…';
 try{const r=await fetch('/x/gateway/token',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+k},body:JSON.stringify({label:'from /gateway'})});const j=await r.json();
  if(!r.ok)throw Error(j.message||j.error);O=j.openai_base_url;A=j.anthropic_base_url;draw();$('#out').hidden=false;$('#out').textContent='OpenAI:    '+O+'\nAnthropic: '+A;
  $('#m').className='msg ok';$('#m').textContent='Done. Keep this URL private — it bills your sebbi.pro key.'}catch(e){$('#m').className='msg err';$('#m').textContent=e.message}};
</script></body></html>"""
    return N._page(N._HEAD + body)


def _standard_page():
    N = _N()
    body = r"""<title>AI-Decision-Receipt — an open HTTP header for proving AI decisions — sebbi.pro</title>
<meta name="description" content="AI-Decision-Receipt is an open HTTP response header that carries a checkable receipt for an AI decision: verdict, sealed block, request fingerprint and where to verify it against Bitcoin.">
</head><body>""" + N._TOP + r"""
<main class="wrap">
<section class="hero"><div class="kick"><i></i>OPEN STANDARD · DRAFT 1</div>
<h1>AI-Decision-Receipt</h1>
<p>One HTTP response header that travels with every governed AI decision: what was decided, where it is sealed, a fingerprint of the request, and where anyone can check it against Bitcoin. Free for anyone to emit, read or implement.</p></section>
<section class="card"><h2>The header</h2>
<pre>AI-Decision-Receipt: v=1, issuer="sebbi.pro", decision=ALLOW, score=0.12,
  block=1042, seal="9f2c…", req="&lt;sha256&gt;", call="GC-7Q2M9X4KDP",
  verify="https://sebbi.pro/forever?block=1042"</pre>
<p class="sub" style="margin-top:10px">Syntax: an RFC 8941 Structured Field Dictionary.</p>
<table><thead><tr><th>Key</th><th>Meaning</th></tr></thead><tbody>
<tr><td>v</td><td>Version. Integer, currently 1. Required.</td></tr>
<tr><td>issuer</td><td>Who sealed the decision. String host name. Required.</td></tr>
<tr><td>decision</td><td>Token: ALLOW, CHALLENGE or BLOCK (issuers may define others in capitals).</td></tr>
<tr><td>score</td><td>Decimal risk score, 0 to 1.</td></tr>
<tr><td>block</td><td>Integer position of the sealed decision in the issuer's chain.</td></tr>
<tr><td>seal</td><td>String: the chain hash of that block (hex SHA-256).</td></tr>
<tr><td>req</td><td>String: SHA-256 (hex) of the exact request body the decision was made on.</td></tr>
<tr><td>call</td><td>String: the issuer's identifier for this call, when sent through a gateway.</td></tr>
<tr><td>verify</td><td>String URL where the decision can be checked — for sebbi.pro, a Forever Proof against Bitcoin.</td></tr>
</tbody></table>
<p class="sub" style="margin-top:10px">Browsers: issuers should send <code>Access-Control-Expose-Headers: AI-Decision-Receipt</code> so web apps can read it.</p></section>
<section class="card"><h2>Checking a receipt</h2>
<ol class="steps" style="border:0;padding-left:0;list-style:decimal inside"><li style="padding-left:0">Hash the request body you sent; it must equal <code>req</code>.</li>
<li style="padding-left:0">Fetch the proof for <code>block</code> from <code>verify</code>. Its subject's chain hash must equal <code>seal</code>.</li>
<li style="padding-left:0">Check the proof against Bitcoin — in a browser or offline with <a href="/forever-verify.py">forever-verify.py</a>. The decision existed before that Bitcoin block.</li></ol>
<p class="sub">Paste a header to try it:</p>
<textarea id="hv" placeholder='v=1, issuer="sebbi.pro", decision=ALLOW, block=1042, seal="…", verify="https://sebbi.pro/forever?block=1042"'></textarea>
<div class="row"><button class="btn b" id="chk">Check this receipt</button><span class="msg" id="m"></span></div></section>
<section class="card"><h2>Where it comes from</h2>
<p class="sub">Every response through the <a href="/gateway">sebbi.pro gateway</a> and every <code>/api/govern</code> answer carries it. Any governance system may emit it under its own <code>issuer</code>. Version 1 is a draft published openly for comment; the intent is to take it through the IETF as an Internet-Draft.</p></section>
</main>""" + N._FOOT + r"""
<script>
function parse(v){const o={};(v.match(/[a-z][a-z0-9_\-.*]*\s*(=\s*("(?:[^"\\]|\\.)*"|[^,\s]+))?/g)||[]).forEach(p=>{const i=p.indexOf('=');if(i<0){o[p.trim()]=true;return}let k=p.slice(0,i).trim(),x=p.slice(i+1).trim();if(x[0]=='"')x=x.slice(1,-1).replace(/\\(.)/g,'$1');o[k]=x});return o}
document.getElementById('chk').onclick=()=>{const m=document.getElementById('m');let v=document.getElementById('hv').value.trim().replace(/^AI-Decision-Receipt:\s*/i,'');const r=parse(v);
 if(!r.block){m.className='msg err';m.textContent='No block in that receipt.';return}
 if(r.verify&&/^https:\/\/sebbi\.pro\/forever\?block=\d+$/.test(r.verify)){location.href=r.verify+(r.seal?'#seal='+r.seal:'');return}
 if(r.issuer==='sebbi.pro'){location.href='/forever?block='+encodeURIComponent(r.block);return}
 m.className='msg';m.textContent='Issued by '+(r.issuer||'unknown')+'. Open its verify link: '+(r.verify||'none given')};
</script></body></html>"""
    return N._page(N._HEAD + body)


# ---------------------------------------------------------------------------
# router entry
# ---------------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    try:
        arm(ctx)
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:150]
    data = data or {}
    if action in ("", "status"):
        try:
            n = _db("SELECT COUNT(*) FROM gateway_call", one=True)[0]
        except Exception:
            n = None
        return {"module": "gateway", "version": VERSION, "armed": _state["wire"] and _state["headers"],
                "page": SITE + "/gateway", "standard": SITE + "/standard/ai-decision-receipt",
                "base_urls": {"openai": SITE + "/g/openai/v1", "anthropic": SITE + "/g/anthropic"},
                "upstreams": UPSTREAM, "calls_recorded": n, "since_start": {k: _state[k] for k in
                ("calls", "forwarded", "blocked", "upstream_errors", "receipts_added")},
                "receipt_header_on_govern": _state["headers"], "ai_connector_tool": _state["mcp"],
                "connection_queue": _state.get("backlog_size", "raised on first request"),
                "last_error": _state["last_error"]}, 200
    if action == "spec":
        return {"module": "gateway", "version": VERSION, "header": HEADER,
                "header_syntax": "RFC 8941 dictionary: v, issuer, decision, score, block, seal, req, call, verify",
                "example": receipt_header("ALLOW", 0.12, 1042, "9f2c" + "0" * 60, "ab" * 32, "GC-7Q2M9X4KDP"),
                "routes": {"openai": SITE + "/g/openai/v1 (X-Sebbi-Key header) or /g/<token>/openai/v1",
                           "anthropic": SITE + "/g/anthropic (X-Sebbi-Key header) or /g/<token>/anthropic",
                           "token": "POST %s/x/gateway/token {label} - API key" % SITE,
                           "revoke": "POST %s/x/gateway/revoke {token} - API key" % SITE,
                           "call": "GET %s/x/gateway/call?id=GC-..." % SITE,
                           "parse": "POST %s/x/gateway/parse {header}" % SITE},
                "optional_headers": ["X-Sebbi-User", "X-Sebbi-Device", "X-Sebbi-Country", "X-Sebbi-Amount",
                                     "X-Sebbi-Anomaly", "X-Sebbi-Device-Risk", "X-Sebbi-Pack", "X-Sebbi-Action",
                                     "X-Sebbi-On-Challenge: block"],
                "stored": "request and response SHA-256 fingerprints, model, endpoint, decision - never prompts, "
                          "answers or provider keys"}, 200
    if action == "call":
        return call_record(data.get("id"))
    if action == "parse" and method == "POST":
        return {"receipt": parse_receipt(data.get("header"))}, 200
    if action == "token" and method == "POST":
        if not api_key:
            return {"error": "api_key_required"}, 401
        return new_token(api_key, data.get("label")), 200
    if action == "revoke" and method == "POST":
        if not api_key:
            return {"error": "api_key_required"}, 401
        tok = str(data.get("token", "")).strip()
        n = _db("UPDATE gateway_token SET revoked=1 WHERE token=? AND key_hash=?", (tok, _kh(api_key)), write=True)
        r = _db("SELECT revoked FROM gateway_token WHERE token=? AND key_hash=?", (tok, _kh(api_key)), one=True)
        return {"revoked": bool(r and r[0])}, (200 if r else 404)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/genesis.py`

282 lines, 12662 bytes

```python
"""
Chain identity - /x/genesis/<action>

WHY THIS EXISTS
---------------
A receipt that does not say which chain state it belongs to is ambiguous the
moment a chain is ever reset, and this one was: on 7 September 2026, during
registry work, the chain was reset. Receipts issued before that date belong to
a state that does not continue forward. Nothing in those receipts says so, and
a peer holding one has no way to discover it from the receipt itself.

Philip Pinol (PRAXIS / ThePraesidium.ai) independently verified block 846 of
the prior state. That verification was sound for the state it was performed
against. It is not continuous with the chain running now, and saying so is
this module's job.

WHAT IT DOES
------------
Publishes the genesis hash of the current chain state and a short stable
identifier derived from it, so any party can pin their own records to a named
state rather than to a block number that may refer to two different things.

    chain_id = first 16 characters of the genesis block's audit hash

Deliberately a slice rather than a computation. Anyone can confirm the
identifier against the genesis hash by eye, in the response that carries both,
without running anything.

WHY IT IS A SEPARATE MODULE
---------------------------
Read-only, by construction. It opens the same database as the sealing code and
never writes to it: no inserts, no schema changes, no seal calls. A fault here
returns a 500 on this route and the chain carries on sealing, because the
module that seals does not import this one and does not know it exists.

That is not tidiness. Editing a file that writes an append-only chain in order
to add a reporting route is how the 7 September reset happened.

WHAT IT DOES NOT CLAIM
----------------------
- It does not assert when the reset occurred. It reports the sealed timestamp
  of block 1 as the database holds it, and states the reset date separately as
  a claim by the operator. If the two disagree, the disagreement is visible in
  the response rather than resolved quietly here.
- A chain_id identifies a state. It says nothing about whether the records in
  that state are true, complete, or externally anchored. Check /x/ots/status
  for anchoring and /api/verify-chain for internal validity.
- Two different deployments could in principle produce the same 16-character
  identifier. The full genesis hash is returned alongside it and is what
  should be pinned where collision matters.

    GET /x/genesis/chain    genesis hash, chain_id, height, current tip
    GET /x/genesis/status   is this module loaded and can it read the chain
    GET /x/genesis/spec     what the identifier is and how to pin it
"""

from datetime import datetime, timezone

VERSION = "1.0.1"

# Length of the genesis hash used as the chain identifier. Sixteen hex
# characters is 64 bits - long enough that two states will not collide by
# accident, short enough to quote in an email without wrapping.
CHAIN_ID_LEN = 16

# Routes that need no API key. A third party must be able to establish which
# chain state a receipt belongs to without holding an account, or the receipt
# is only checkable by customers.
PUBLIC = {("GET", "chain"), ("GET", "status"), ("GET", "spec")}

# ----------------------------------------------------------------------
# everything a reader sees
# ----------------------------------------------------------------------

# The reset moment, stated to the second and in UTC, because a date alone was
# ambiguous: the chain was reset just after midnight UK time, so the calendar
# date differs between UTC and local and the route appeared to contradict
# itself. Stated precisely rather than rounded to whichever date reads better.
RESET_AT_UTC = "2026-09-06T23:11:12Z"

RESET_RECORD = {
    "occurred": RESET_AT_UTC,
    "occurred_local": (
        "00:11 on 7 September 2026, UK time. The same moment. Recorded in UTC "
        "above because a calendar date is ambiguous within an hour of "
        "midnight and this one falls inside that hour."),
    "reason": "chain reset during registry work",
    "effect": (
        "Receipts, block indexes and audit hashes issued before this date "
        "belong to a prior chain state. That state does not continue forward "
        "into the chain running now. A block index from before the reset and "
        "a block index from after it are not comparable and do not refer to "
        "the same sequence."),
    "prior_verification": (
        "Block 846 of the prior state was independently verified by Philip "
        "Pinol (PRAXIS / ThePraesidium.ai). That verification was sound for "
        "the state it was performed against. It is not evidence about the "
        "current state, and neither party describes it as continuous with it."),
    "what_was_not_lost": (
        "The prior state's records were sealed under the rules in force at "
        "the time and were valid under them. What changed is that the "
        "sequence does not extend. Nothing here claims the earlier records "
        "were wrong."),
    "disclosed_because": (
        "A peer holding a pre-reset receipt cannot discover any of this from "
        "the receipt itself. Published rather than left for someone to find "
        "when their records fail to reconcile."),
}

VOCABULARY = {
    "chain_id": (
        "A short stable identifier for one chain state, being the first %d "
        "characters of that state's genesis block hash. Pin your records to "
        "this rather than to a block index. If a chain is ever reset, the "
        "chain_id changes and the mismatch is visible immediately; a block "
        "index silently refers to a different thing." % CHAIN_ID_LEN),
    "genesis_hash": (
        "The audit hash of block 1 of the current chain state. This is the "
        "value to pin where a 16-character identifier is not enough. It does "
        "not change for the life of the state."),
    "genesis_sealed_at": (
        "The timestamp stored against block 1, as the database holds it. It "
        "is this deployment's own clock at the moment that block was written "
        "and is not evidence of when anything happened. The external "
        "timestamp proofs at /x/ots/status are the answer to that question."),
    "height": (
        "How many blocks the current state holds. Counts from block 1 of this "
        "state, not from the beginning of any prior state."),
    "current_tip": (
        "The audit hash of the most recent block. Changes constantly. "
        "Included so one call establishes the whole identity of the state; "
        "/x/witness/tip is the route to poll."),
}


def _iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _first_block(ctx):
    """Block 1 of the current state. Read-only."""
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT audit_hash,ts,id FROM audit_log ORDER BY id ASC LIMIT 1"
        ).fetchone()


def _last_block(ctx):
    """Current tip. Read-only. Same query witness.py uses, deliberately."""
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT audit_hash,ts,id FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()


def _chain(ctx):
    first = _first_block(ctx)
    if not first:
        return {"error": "no_genesis",
                "message": ("The audit chain holds no blocks, so there is no "
                            "genesis to report. This is an empty chain rather "
                            "than a fault."),
                "genesis_version": VERSION}, 404

    genesis_hash = str(first[0])
    chain_id = genesis_hash[:CHAIN_ID_LEN]
    last = _last_block(ctx)

    out = {
        "chain_id": chain_id,
        "genesis_hash": genesis_hash,
        "genesis_block_index": first[2],
        "genesis_sealed_at": _iso(first[1]),
        "height": last[2] if last else first[2],
        "current_tip": last[0] if last else genesis_hash,
        "current_sealed_at": _iso(last[1]) if last else _iso(first[1]),
        "genesis_version": VERSION,
        "reset_record": RESET_RECORD,
        "vocabulary": VOCABULARY,
        "how_to_pin": (
            "Record chain_id alongside every receipt you hold from this "
            "deployment. When you later check a receipt, read this route "
            "first: if chain_id has changed, your receipt belongs to a state "
            "that no longer continues and no block index in it is comparable "
            "to a current one."),
        "verify_the_identifier": (
            "chain_id is the first %d characters of genesis_hash. Both are in "
            "this response. Check it by eye - nothing needs to be run."
            % CHAIN_ID_LEN),
        "this_does_not_establish": (
            "That the records in this state are true, complete, or externally "
            "anchored. /api/verify-chain checks the chain end to end. "
            "/x/ots/status shows the state of each external timestamp proof."),
    }

    # State rather than assert. The stated reset moment and the sealed
    # timestamp of block 1 should be the same event. If they are not, the
    # reader sees the disagreement here rather than being told a tidy story.
    #
    # Compared to the minute, in UTC, on both sides. Comparing calendar dates
    # was wrong: this chain was reset at 23:11 UTC, which is the following day
    # locally, so a date comparison reported a contradiction that did not
    # exist. A route that cries wolf about its own honesty is worse than one
    # that says nothing.
    sealed = out["genesis_sealed_at"]
    if sealed and sealed[:16] != RESET_AT_UTC[:16]:
        out["date_note"] = (
            "The sealed timestamp of block 1 (%s) does not match the reset "
            "moment stated in reset_record (%s). Both values are reported as "
            "they are. Reconcile them against the external timestamp proofs "
            "rather than against either party's account."
            % (sealed, RESET_AT_UTC))

    return out, 200


def _status(ctx):
    """Arming route. Says whether this module loaded and can read the chain."""
    readable = False
    detail = None
    try:
        readable = _first_block(ctx) is not None
        if not readable:
            detail = "chain is readable and holds no blocks"
    except Exception as exc:
        detail = "could not read the audit chain (%s)" % type(exc).__name__

    return {"module": "genesis",
            "version": VERSION,
            "chain_readable": readable,
            "detail": detail,
            "writes": "none - this module never writes to the database",
            "routes": sorted(a for _m, a in PUBLIC),
            "genesis_version": VERSION}, 200


def _spec():
    return {"module": "genesis",
            "genesis_version": VERSION,
            "purpose": (
                "Publishes which chain state this deployment is running, so a "
                "receipt can be pinned to a named state rather than to a "
                "block index that may refer to two different sequences."),
            "chain_id_rule": (
                "The first %d characters of the genesis block's audit hash. "
                "Not a hash of a hash, not a derived key - a slice, so it can "
                "be checked by eye against the genesis hash returned beside "
                "it." % CHAIN_ID_LEN),
            "routes": {
                "GET /x/genesis/chain": "chain_id, genesis hash, height, tip",
                "GET /x/genesis/status": "module loaded, chain readable",
                "GET /x/genesis/spec": "this document",
            },
            "vocabulary": VOCABULARY,
            "reset_record": RESET_RECORD,
            "read_only": (
                "This module performs no writes of any kind. It opens the "
                "same database the sealing code uses and issues two SELECT "
                "statements. A fault here cannot affect the chain."),
            "related": {
                "/x/witness/tip": "current tip, for peers to record",
                "/api/verify-chain": "checks this chain end to end",
                "/x/ots/status": "state of each external timestamp proof",
            }}, 200


def handle(method, action, data, api_key, ctx):
    if method == "GET":
        if action == "chain":
            return _chain(ctx)
        if action == "status":
            return _status(ctx)
        if action == "spec":
            return _spec()
    return {"error": "unknown_action", "action": action,
            "routes": sorted(a for _m, a in PUBLIC)}, 404

```


## `modules/grade.py`

674 lines, 26478 bytes

```python
"""
modules/grade.py  v1.0.0  —  public transparency-file scanner

WHAT IT DOES
------------
Fetches a domain's public convention files and reports, per file, what was
actually found: served or not, parses or not, and the specific fields present.
Nothing else.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not issue a letter grade, a score, or a verdict, and the words
"compliant" and "non-compliant" appear nowhere in its output.

The reason is not squeamishness. Half of these files are conventions rather
than requirements. No law anywhere obliges a company to serve ai.txt,
comply.txt, llms.txt or an AI-safety file, and two of those are conventions
this operator helped write. Scoring the market against your own file format
and publishing a letter is marking other people's homework with your own
marking scheme. So this reports observations and lets the reader conclude.

Absence is reported as absence. That is a fact about a file. It is not a
finding about a company, and this module never converts one into the other.

THE CLOAKING CHECK WAS REMOVED
------------------------------
An earlier version compared homepage byte-length under two user agents and
scored a >10% difference as cloaking. Any page with a clock, a nonce or a
rotating banner fails that; real cloaking returning a similar-length page
passes it. It measured noise and reported it as a signal, so it is gone
rather than reworded.

ROUTES
------
  POST /x/grade/scan          KEYED   scan a domain, seal the result
  GET  /x/grade/report        public  ?domain= — the last scan of that domain
  GET  /x/grade/list          public  domains scanned, most recent first
  GET  /x/grade/spec          public  what each check means
  GET  /grade-badge?domain=   public  SVG, served from cache ONLY

BADGE BEHAVIOUR THAT MATTERS
----------------------------
The badge never triggers a fetch of the target. An earlier version re-ran
every check on every image load, so embedding the badge on a busy page would
have pointed sustained unsolicited traffic at somebody else's server from
this IP. The badge now renders from the stored scan or says "not scanned".

SAFETY
------
https only, port 443, DNS resolved and checked against private, loopback,
link-local, multicast and reserved ranges before any request, redirects not
followed, 8s timeout, 256KB cap per file. Known limit, stated rather than
hidden: resolve-then-connect leaves a DNS rebinding window, the same gap
witness.py has.

/robots.txt is read first and its Disallow rules for * are honoured. A
scanner that ignores robots while grading other people on transparency
would be a poor advertisement for the point being made.
"""

import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

VERSION = "1.0.0"

PUBLIC = {("GET", "report"), ("GET", "list"), ("GET", "spec"), ("GET", "")}

PAGE_PATHS = ("/grade-badge",)

UA = "AILeash-Transparency-Scan/1.0 (+https://sebbi.pro/x/grade/spec)"
TIMEOUT = 8
MAX_BYTES = 262144
CACHE_TTL = 3600

# Files that are genuine public-web standards with an RFC or a long-standing
# convention behind them. Absence here is still not a legal finding, but the
# expectation is at least widely shared.
STANDARDS = [
    ("security_txt", "/.well-known/security.txt", "RFC 9116 security contact"),
    ("robots_txt", "/robots.txt", "crawler directives"),
    ("sitemap_xml", "/sitemap.xml", "site index"),
]

# Files that are emerging AI-transparency conventions. Reported as adoption
# facts, never scored, because nobody is obliged to serve any of them.
CONVENTIONS = [
    ("ai_txt", "/.well-known/ai.txt", "AI system manifest"),
    ("ai_txt_root", "/ai.txt", "AI system manifest at root"),
    ("comply_txt", "/.well-known/comply.txt", "compliance index"),
    ("llms_txt", "/llms.txt", "guidance for language models"),
    ("ai_safety_txt", "/.well-known/ai-safety.txt", "AI-safety declaration"),
]

_patched = [False]
_ready = [False]
_cache = {}


def _setup(ctx):
    if _ready[0]:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS grade_scan("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,domain TEXT,scanned REAL,"
            "findings TEXT,standards_served INTEGER,conventions_served INTEGER,"
            "audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_grade_domain ON grade_scan(domain)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_grade_hash ON grade_scan(audit_hash)")
        ctx["conn"].commit()
    _ready[0] = True


# ----------------------------------------------------------------------
# safety
# ----------------------------------------------------------------------

def _clean_domain(raw):
    d = str(raw or "").strip().lower()
    d = d.replace("https://", "").replace("http://", "")
    d = d.split("/")[0].split("?")[0].strip().rstrip(".")
    if "@" in d or ":" in d or " " in d:
        return None
    if not d or "." not in d or len(d) > 253:
        return None
    for ch in d:
        if not (ch.isalnum() or ch in ".-"):
            return None
    return d


def _private(ip):
    parts = ip.split(".")
    if len(parts) == 4:
        try:
            a, b = int(parts[0]), int(parts[1])
        except ValueError:
            return True
        if a == 10 or a == 127 or a == 0:
            return True
        if a == 172 and 16 <= b <= 31:
            return True
        if a == 192 and b == 168:
            return True
        if a == 169 and b == 254:
            return True
        if a == 100 and 64 <= b <= 127:
            return True
        if a >= 224:
            return True
        return False
    low = ip.lower()
    if low in ("::1", "::", "") or low.startswith(("fc", "fd", "fe80", "::ffff:")):
        return True
    return False


def _resolvable(domain):
    try:
        infos = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "dns_failed: " + type(exc).__name__
    for info in infos:
        ip = info[4][0]
        if _private(ip):
            return False, "resolves_to_non_public_address"
    return True, None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _get(url):
    """One request. Returns (status, text, note). Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    opener = urllib.request.build_opener(
        _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            raw = resp.read(MAX_BYTES + 1)
            truncated = len(raw) > MAX_BYTES
            text = raw[:MAX_BYTES].decode("utf-8", errors="replace")
            return resp.status, text, ("truncated" if truncated else None)
    except urllib.error.HTTPError as exc:
        return exc.code, None, None
    except Exception as exc:
        return None, None, type(exc).__name__


# ----------------------------------------------------------------------
# parsing — every check states exactly what it looked at
# ----------------------------------------------------------------------

def _fields(text):
    """Key: value lines, lowercased keys. Comments and blanks ignored."""
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip().lower()
        if k and k not in out:
            out[k] = v.strip()
    return out


def _check_security(text):
    f = _fields(text)
    return {
        "parses_as_fields": bool(f),
        "has_contact": "contact" in f,
        "has_expires": "expires" in f,
        "expires_value": f.get("expires"),
        "note": ("RFC 9116 requires Contact and Expires. Both presence checks "
                 "above are literal: the field is there or it is not. Whether "
                 "the contact works is not tested."),
    }


def _check_robots(text):
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    directives = [l for l in lines if ":" in l and not l.startswith("#")]
    return {
        "non_empty": bool(lines),
        "directive_lines": len(directives),
        "note": "Presence and shape only. The rules themselves are not judged.",
    }


def _check_sitemap(text):
    try:
        import xml.etree.ElementTree as ET
        ET.fromstring(text or "")
        return {"parses_as_xml": True,
                "note": "Parsed as XML. Contents and freshness are not checked."}
    except Exception as exc:
        return {"parses_as_xml": False, "parse_error": type(exc).__name__,
                "note": "Served but did not parse as XML."}


def _check_ai_safety(text):
    """The old version passed if the file contained 'ai-safe:' and the word
    'true' anywhere in it, so 'AI-Safe: false' with 'true' elsewhere passed.
    This reads the field's own value and reports it verbatim."""
    f = _fields(text)
    val = f.get("ai-safe")
    return {
        "has_ai_safe_field": val is not None,
        "ai_safe_value": val,
        "declared_safe": (val.strip().lower() == "true") if val else None,
        "note": ("This reports what the domain declares about itself. A "
                 "self-declaration is not a verification, and nothing here "
                 "checks whether the declaration is true."),
    }


def _check_manifest(text):
    f = _fields(text)
    interesting = ["standard", "domain", "chain-head", "chain-tip-url", "witness-tip",
                   "verify-chain", "consistency-proof", "self-check",
                   "security-contact", "contact", "governance-engine"]
    return {
        "parses_as_fields": bool(f),
        "field_count": len(f),
        "fields_present": [k for k in interesting if k in f],
        "declares_standard": f.get("standard"),
        "note": ("Fields are reported as served. Nothing here follows the URLs "
                 "they contain or verifies any chain they point at."),
    }


def _check_present(text):
    return {"non_empty": bool(text and text.strip()),
            "bytes": len(text or ""),
            "note": "Presence and size only."}


PARSERS = {
    "security_txt": _check_security,
    "robots_txt": _check_robots,
    "sitemap_xml": _check_sitemap,
    "ai_safety_txt": _check_ai_safety,
    "ai_txt": _check_manifest,
    "ai_txt_root": _check_manifest,
    "comply_txt": _check_manifest,
    "llms_txt": _check_present,
}


def _disallowed(robots_text):
    """Paths Disallowed for * in robots.txt. Honoured for every other fetch."""
    blocked = []
    applies = False
    for line in (robots_text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            applies = (v == "*")
        elif k == "disallow" and applies and v:
            blocked.append(v)
    return blocked


def _blocked(path, rules):
    for rule in rules:
        if rule == "/" or path.startswith(rule):
            return True
    return False


# ----------------------------------------------------------------------
# the scan
# ----------------------------------------------------------------------

def _scan(domain):
    base = "https://" + domain
    findings = {}

    status, robots_text, note = _get(base + "/robots.txt")
    rules = _disallowed(robots_text) if status == 200 else []
    findings["robots_txt"] = {
        "path": "/robots.txt", "http_status": status,
        "served": status == 200, "transport_note": note,
        "detail": _check_robots(robots_text) if status == 200 else None,
        "kind": "standard", "description": "crawler directives",
    }

    for key, path, desc in STANDARDS + CONVENTIONS:
        if key == "robots_txt":
            continue
        if _blocked(path, rules):
            findings[key] = {
                "path": path, "served": None, "http_status": None,
                "skipped": "disallowed_by_robots_txt",
                "kind": "standard" if key in [k for k, _, _ in STANDARDS] else "convention",
                "description": desc,
                "note": ("This domain's robots.txt disallows it, so it was not "
                         "requested. Not requested is not the same as absent."),
            }
            continue
        st, text, tnote = _get(base + path)
        served = (st == 200 and bool(text and text.strip()))
        findings[key] = {
            "path": path, "http_status": st, "served": served,
            "transport_note": tnote,
            "detail": PARSERS[key](text) if served else None,
            "kind": "standard" if key in [k for k, _, _ in STANDARDS] else "convention",
            "description": desc,
        }

    std_keys = [k for k, _, _ in STANDARDS]
    conv_keys = [k for k, _, _ in CONVENTIONS]
    std_served = sum(1 for k in std_keys if findings.get(k, {}).get("served"))
    conv_served = sum(1 for k in conv_keys if findings.get(k, {}).get("served"))

    return findings, std_served, conv_served


def _summary(domain, findings, std, conv, scanned, receipt=None, block=None):
    return {
        "domain": domain,
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(scanned)),
        "standards_served": "%d of %d" % (std, len(STANDARDS)),
        "conventions_served": "%d of %d" % (conv, len(CONVENTIONS)),
        "findings": findings,
        "receipt": receipt,
        "block_index": block,
        "what_this_is": (
            "A record of which public files this domain served at the time of "
            "the scan, and what each one contained. Every check is named and "
            "every result is what the fetch returned."),
        "what_this_is_not": (
            "Not a grade, not a score, and not a statement about whether this "
            "organisation complies with anything. No law requires any of the "
            "files above. Absence of a file is absence of a file."),
        "conventions_disclaimer": (
            "ai.txt and comply.txt are conventions sebbi.pro publishes and helped "
            "shape. A domain not serving them has declined nothing and broken "
            "nothing - it has simply not adopted a format that is not a standard."),
        "if_you_are_the_domain_owner": (
            "This scan requested public files over https and followed your "
            "robots.txt. Nothing was crawled beyond the paths listed. The scan "
            "is sealed, so exactly what was fetched and when is on record and "
            "can be produced. Contact justrightdecorators@gmail.com to have a "
            "scan removed from the public list."),
    }


# ----------------------------------------------------------------------
# badge — cache only, never triggers a fetch of the target
# ----------------------------------------------------------------------

def _badge_svg(label, value, colour):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="260" height="20" '
        'role="img" aria-label="%s %s">'
        '<rect width="176" height="20" fill="#0a0f1e"/>'
        '<rect x="176" width="84" height="20" fill="%s"/>'
        '<text x="88" y="14" fill="#fff" font-family="Verdana,sans-serif" '
        'font-size="10" text-anchor="middle">%s</text>'
        '<text x="218" y="14" fill="#0a0f1e" font-family="Verdana,sans-serif" '
        'font-size="10" font-weight="bold" text-anchor="middle">%s</text>'
        '</svg>' % (label, value, colour, label, value))


def _srv():
    import sys
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s, ctx):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_grade_patched", False):
        _patched[0] = True
        return "already installed"

    conn, lock = ctx["conn"], ctx["lock"]
    original = H.do_GET

    def do_GET(self):
        try:
            u = urlparse(self.path)
            p = u.path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            domain = ""
            try:
                q = dict(pair.split("=", 1) for pair in (u.query or "").split("&") if "=" in pair)
                domain = _clean_domain(q.get("domain", "")) or ""
            except Exception:
                domain = ""
            label = "transparency files"
            value, colour = "not scanned", "#6b6353"
            if domain:
                try:
                    with lock:
                        row = conn.execute(
                            "SELECT standards_served,conventions_served FROM grade_scan "
                            "WHERE domain=? ORDER BY id DESC LIMIT 1", (domain,)).fetchone()
                    if row:
                        value = "%d/%d std · %d/%d conv" % (
                            row[0], len(STANDARDS), row[1], len(CONVENTIONS))
                        colour = "#7fe3b0" if row[0] == len(STANDARDS) else "#c9a84c"
                except Exception:
                    pass
            body = _badge_svg(label, value, colour).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._grade_patched = True
    _patched[0] = True
    print("GRADE: /grade-badge installed at runtime", flush=True)
    return "installed"


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _do_scan(ctx, api_key, data):
    domain = _clean_domain((data or {}).get("domain"))
    if not domain:
        return {"error": "domain_required",
                "message": "Send {\"domain\": \"example.com\"}."}, 400

    cached = _cache.get(domain)
    if cached and (time.time() - cached[0]) < CACHE_TTL and not (data or {}).get("force"):
        out = dict(cached[1])
        out["from_cache"] = True
        out["cache_age_seconds"] = int(time.time() - cached[0])
        return out, 200

    ok, why = _resolvable(domain)
    if not ok:
        return {"error": "domain_refused", "domain": domain, "reason": why,
                "message": "Only public, resolvable hosts are scanned."}, 400

    scanned = time.time()
    findings, std, conv = _scan(domain)

    ev = {"user_id": "grade:" + domain, "action": "transparency_scan",
          "amount": 0, "country": "UK", "device_id": "grade",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "SCAN_RECORDED", "score": 0, "grade_version": VERSION,
           "domain": domain, "standards_served": std, "conventions_served": conv,
           "timestamp": scanned,
           "detail": "domain=%s;standards=%d/%d;conventions=%d/%d"
                     % (domain, std, len(STANDARDS), conv, len(CONVENTIONS))}
    try:
        h, idx, seq = ctx["seal"](ev, res, scanned, api_key)
    except Exception as exc:
        return {"error": "seal_failed",
                "detail": type(exc).__name__ + ": " + str(exc)[:250],
                "message": ("The scan ran but was not recorded, so nothing is "
                            "published. A scan nobody can audit is not published "
                            "here.")}, 500
    if not h:
        return {"error": "seal_failed", "detail": "seal returned no hash"}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO grade_scan(domain,scanned,findings,standards_served,"
            "conventions_served,audit_hash,block_index) VALUES(?,?,?,?,?,?,?)",
            (domain, scanned, json.dumps(findings), std, conv, h, idx))
        ctx["conn"].commit()

    out = _summary(domain, findings, std, conv, scanned, h, idx)
    out["receipt_seq"] = seq
    out["badge"] = "https://sebbi.pro/grade-badge?domain=" + domain
    out["report"] = "https://sebbi.pro/x/grade/report?domain=" + domain
    _cache[domain] = (scanned, out)
    if len(_cache) > 500:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
            _cache.pop(k, None)
    return out, 200


def _report(ctx, data):
    domain = _clean_domain((data or {}).get("domain"))
    if not domain:
        return {"error": "domain_required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT scanned,findings,standards_served,conventions_served,"
            "audit_hash,block_index FROM grade_scan WHERE domain=? "
            "ORDER BY id DESC LIMIT 1", (domain,)).fetchone()
    if not row:
        return {"found": False, "domain": domain,
                "message": "This domain has not been scanned."}, 404
    try:
        findings = json.loads(row[1])
    except Exception:
        findings = {}
    out = _summary(domain, findings, row[2], row[3], row[0], row[4], row[5])
    out["found"] = True
    out["badge"] = "https://sebbi.pro/grade-badge?domain=" + domain
    return out, 200


def _list(ctx, data):
    try:
        limit = min(200, max(1, int((data or {}).get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT domain,MAX(scanned),standards_served,conventions_served "
            "FROM grade_scan GROUP BY domain ORDER BY MAX(scanned) DESC LIMIT ?",
            (limit,)).fetchall()
    return {
        "count": len(rows),
        "scans": [{
            "domain": r[0],
            "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[1])),
            "standards_served": "%d of %d" % (r[2], len(STANDARDS)),
            "conventions_served": "%d of %d" % (r[3], len(CONVENTIONS)),
            "report": "/x/grade/report?domain=" + r[0],
        } for r in rows],
        "what_this_list_is": (
            "Domains that have been scanned, with what they served. It is not a "
            "ranking, not a shortlist and not an allegation about anyone on it."),
    }, 200


def _spec():
    return {
        "module": "grade", "version": VERSION,
        "question": "Which public transparency files does this domain serve, and what is in them?",
        "standards_checked": [{"key": k, "path": p, "what": d} for k, p, d in STANDARDS],
        "conventions_checked": [{"key": k, "path": p, "what": d} for k, p, d in CONVENTIONS],
        "no_grade": (
            "This module issues no letter, no score and no verdict, and the word "
            "compliant appears nowhere in its output. Half of these files are "
            "conventions rather than requirements, two of them are conventions "
            "sebbi.pro helped write, and grading strangers against your own "
            "format would be marking their homework with your marking scheme."),
        "absence": (
            "A file that is not served is reported as not served. That is a fact "
            "about a file and never a finding about a company."),
        "self_declarations": (
            "Where a file declares something about the domain - ai-safe: true, a "
            "chain head, a standard version - the declaration is reported "
            "verbatim and is never treated as verified. Nothing here follows the "
            "URLs a manifest contains."),
        "how_it_fetches": {
            "scheme": "https only, port 443",
            "redirects": "not followed",
            "timeout_seconds": TIMEOUT,
            "max_bytes_per_file": MAX_BYTES,
            "address_check": ("DNS resolved and rejected if it points at private, "
                              "loopback, link-local, multicast or reserved space"),
            "known_limit": ("resolve-then-connect leaves a DNS rebinding window; "
                            "stated rather than hidden"),
            "robots": "/robots.txt is read first and Disallow rules for * are honoured",
            "user_agent": UA,
        },
        "badge": {
            "url": "https://sebbi.pro/grade-badge?domain=example.com",
            "behaviour": ("renders from the stored scan only and never fetches the "
                          "target, so embedding it cannot point traffic at anyone"),
        },
        "every_scan_is_sealed": (
            "Each scan is written into the audit chain with its receipt, so a "
            "domain owner who objects can be shown exactly what was requested "
            "and when."),
        "auth": "scan is keyed. report, list, spec and the badge are public.",
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    s = _srv()
    if s is not None and not _patched[0]:
        try:
            _install(s, ctx)
        except Exception as exc:
            print("GRADE: patch failed - " + str(exc), flush=True)

    action = (action or "").strip("/").lower()

    if method == "POST":
        if action == "scan":
            if not api_key:
                return {"error": "api_key_required",
                        "message": ("Scanning fetches somebody else's server, so it "
                                    "is keyed and attributable. Reading results is "
                                    "public.")}, 401
            return _do_scan(ctx, api_key, data)
        return {"error": "unknown_action", "action": action, "POST": ["scan"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "report":
        return _report(ctx, data)
    if action == "list":
        return _list(ctx, data)
    if action == "status":
        return {"module": "grade", "version": VERSION,
                "badge_installed": bool(_patched[0]),
                "cached_domains": len(_cache)}, 200
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "report", "list", "status"], "POST": ["scan"]}, 404

```
