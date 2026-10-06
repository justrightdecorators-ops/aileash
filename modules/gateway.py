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
<section class="card"><h2>1 · Get your gateway URL</h2><p class="sub">Paste your sebbi.pro API key. No key yet? <a href="/connect">Get one free</a>. Your first 1,000 gateway calls are free; then add a card — 50p per device a month. Want us to set it all up? <a href="/pilot">Governed in 7 days</a>.</p>
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
