# Codebase — part 17 of 29

Contains:
- `sebbi_tokensaver.py`
- `sebdog_engine.py`
- `sebdog_licence.py`
- `sebdog_reporter.py`


## `sebbi_tokensaver.py`

880 lines, 32471 bytes

```python
#!/usr/bin/env python3
"""
sebbi_tokensaver.py  v1.0.0
sebbi.pro - the token saver, customer side

WHAT YOU CHANGE
---------------
One line. The address your code already sends model requests to.

    before:  base_url = "https://api.anthropic.com"
    after:   base_url = "http://127.0.0.1:8788"

That is the whole integration. Nothing else in your application
changes. Same request format, same response format, same everything.

RUN IT
------
    python3 sebbi_tokensaver.py --key YOUR_SEBBI_KEY

First run writes sebbi_tokensaver.json next to itself and tells you
exactly what to paste. After that, just:

    python3 sebbi_tokensaver.py

Check it is working:
    http://127.0.0.1:8788/saver          a plain page, what it has saved
    http://127.0.0.1:8788/saver/stats    the same as JSON

WHAT LEAVES YOUR BUILDING
-------------------------
Your prompts and your answers do not. They are stored in a SQLite file
on this machine and nowhere else.

What goes to sebbi.pro is a digest: a SHA-256 fingerprint, and counts.
How many characters, how many turns, how many tools, what output
ceiling you set, and whether the request was deterministic. There is no
way to read a prompt back out of a SHA-256 hash.

You can see every byte of it before it goes:
    --show-digest       print each digest as it is sent
    --offline           never contact sebbi.pro at all

WHAT HAPPENS IF SEBBI.PRO IS DOWN
---------------------------------
Your traffic keeps flowing. This is the most important line in this
file. If sebbi.pro cannot be reached, the local cache still serves
repeats, local hard rules still stop runaways, and everything else goes
straight to your provider as normal. It fails open, always. A cost tool
that can take your production down is not worth any saving.

Requests that were gated while sebbi.pro was unreachable are queued and
sent when it comes back, so the record catches up.

HOW IT SAVES YOU MONEY
----------------------
1. An identical request is answered from the local store. Nothing is
   bought and there is no round trip to anywhere.
2. A runaway loop is stopped locally in microseconds, before the money
   goes. This is the one that pays for itself overnight.
3. A spend ceiling that is actually enforced.
4. It tells you, per request, what in that request is costing money it
   does not need to cost: turns you are re-sending, tool definitions
   nothing calls, temperature set above zero for no reason.

Standard library only. No dependencies. Python 3.8 or newer.
"""

import argparse
import hashlib
import json
import math
import os
import queue
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.0.0"
DEFAULT_PORT = 8788
CONFIG_NAME = "sebbi_tokensaver.json"
DB_NAME = "sebbi_tokensaver.db"
SEBBI_DEFAULT = "https://sebbi.pro"

PROVIDERS = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com",
    "azure": None,
    "local": "http://127.0.0.1:11434",
}

KEYED_FIELDS = (
    "model", "messages", "system", "prompt", "input",
    "temperature", "top_p", "top_k",
    "max_tokens", "max_completion_tokens",
    "stop", "stop_sequences",
    "tools", "tool_choice", "response_format", "seed",
)

FORWARD_HEADERS = ("authorization", "x-api-key", "anthropic-version",
                   "anthropic-beta", "openai-organization", "openai-beta",
                   "content-type", "accept")

# Local hard rules. Identical to the ones on the platform, so the
# behaviour does not change when the network does.
LOOP_WINDOW = 120
LOOP_HARD = 8
LOOP_HARD_UNATTENDED = 4
BURST_HARD = 120

DEFAULT_TTL = 30 * 24 * 3600
MAX_BODY = 8 * 1024 * 1024
CHARS_PER_TOKEN = 4.0
CTX_FLAG_TURNS = 12
CTX_KEEP_TURNS = 8


# ------------------------------------------------------------------ util

def canonical(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def sha(d):
    if isinstance(d, str):
        d = d.encode("utf-8")
    return hashlib.sha256(d).hexdigest()


def fingerprint(req):
    keyed = {k: req[k] for k in KEYED_FIELDS if k in req}
    return sha(b"SEBBI-TOKENSAVER-v2\n" + canonical(keyed))


def content_chars(v):
    if v is None:
        return 0
    if isinstance(v, str):
        return len(v)
    return len(canonical(v))


def prompt_chars(req):
    t = 0
    for k in ("prompt", "input", "system"):
        t += content_chars(req.get(k))
    msgs = req.get("messages")
    if isinstance(msgs, list):
        for m in msgs:
            t += content_chars(m.get("content") if isinstance(m, dict) else m)
    if req.get("tools") is not None:
        t += content_chars(req.get("tools"))
    return t


def ask_ceiling(req):
    v = req.get("max_tokens")
    if v is None:
        v = req.get("max_completion_tokens")
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def deterministic(req):
    t = req.get("temperature")
    if t is None:
        return True
    try:
        return float(t) == 0.0
    except (TypeError, ValueError):
        return False


def usage_of(resp):
    if not isinstance(resp, dict):
        return (None, None)
    u = resp.get("usage")
    if not isinstance(u, dict):
        return (None, None)
    i = u.get("input_tokens", u.get("prompt_tokens"))
    o = u.get("output_tokens", u.get("completion_tokens"))
    try:
        return (int(i) if i is not None else None,
                int(o) if o is not None else None)
    except (TypeError, ValueError):
        return (None, None)


def digest_of(req):
    """Exactly what is sent to sebbi.pro. Nothing else, ever."""
    return {
        "fingerprint": fingerprint(req),
        "model": req.get("model"),
        "prompt_characters": prompt_chars(req),
        "max_tokens": ask_ceiling(req),
        "conversation_turns": len(req.get("messages") or []),
        "tool_definitions": len(req.get("tools") or []),
        "deterministic": deterministic(req),
    }


def est_tokens(chars):
    return int(chars / CHARS_PER_TOKEN)


# ----------------------------------------------------------------- store

SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    fp        TEXT PRIMARY KEY,
    model     TEXT,
    body      BLOB NOT NULL,
    tok_in    INTEGER,
    tok_out   INTEGER,
    stored_at REAL NOT NULL,
    expires   REAL,
    hits      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS seen (
    fp TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS totals (
    k TEXT PRIMARY KEY,
    v REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outbox (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    action  TEXT NOT NULL,
    payload TEXT NOT NULL,
    ts      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS seen_ts ON seen(ts);
CREATE INDEX IF NOT EXISTS seen_fp ON seen(fp, ts);
CREATE INDEX IF NOT EXISTS ans_exp ON answers(expires);
"""


class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.executescript(SCHEMA)
        self.c.commit()

    def bump(self, key, by=1):
        self.c.execute(
            "INSERT INTO totals (k, v) VALUES (?, ?) "
            "ON CONFLICT(k) DO UPDATE SET v = v + ?", (key, by, by))

    def total(self, key):
        r = self.c.execute("SELECT v FROM totals WHERE k=?", (key,)).fetchone()
        return r[0] if r else 0

    def note_seen(self, fp, now):
        self.c.execute("INSERT INTO seen (fp, ts) VALUES (?,?)", (fp, now))
        self.c.execute("DELETE FROM seen WHERE ts < ?", (now - 3600,))

    def counts(self, fp, now):
        loop = self.c.execute(
            "SELECT COUNT(*) FROM seen WHERE fp=? AND ts > ?",
            (fp, now - LOOP_WINDOW)).fetchone()[0]
        burst = self.c.execute(
            "SELECT COUNT(*) FROM seen WHERE ts > ?", (now - 60,)).fetchone()[0]
        return loop, burst

    def get(self, fp, now):
        r = self.c.execute(
            "SELECT body, tok_in, tok_out, hits, expires FROM answers "
            "WHERE fp=?", (fp,)).fetchone()
        if not r:
            return None
        if r[4] is not None and r[4] < now:
            self.c.execute("DELETE FROM answers WHERE fp=?", (fp,))
            self.c.commit()
            return None
        return r

    def put(self, fp, model, body, ti, to, now, ttl):
        self.c.execute(
            "INSERT OR REPLACE INTO answers (fp, model, body, tok_in, "
            "tok_out, stored_at, expires, hits) VALUES (?,?,?,?,?,?,?,0)",
            (fp, model, body, ti, to, now, now + ttl if ttl else None))

    def hit(self, fp):
        self.c.execute("UPDATE answers SET hits=hits+1 WHERE fp=?", (fp,))

    def enqueue(self, action, payload, now):
        self.c.execute(
            "INSERT INTO outbox (action, payload, ts) VALUES (?,?,?)",
            (action, json.dumps(payload), now))

    def take_outbox(self, n=25):
        rows = self.c.execute(
            "SELECT id, action, payload FROM outbox ORDER BY id LIMIT ?",
            (n,)).fetchall()
        return rows

    def drop_outbox(self, ids):
        self.c.executemany("DELETE FROM outbox WHERE id=?",
                           [(i,) for i in ids])


# ----------------------------------------------------------------- uplink

class Uplink:
    """
    Talks to sebbi.pro. Never blocks a request for long and never stops
    one. Everything it sends is a digest.
    """

    def __init__(self, base, key, store, timeout=2.0, offline=False,
                 show=False):
        self.base = (base or SEBBI_DEFAULT).rstrip("/")
        self.key = key
        self.store = store
        self.timeout = timeout
        self.offline = offline
        self.show = show
        self.up = None if offline else True
        self.last_fail = 0.0
        self.q = queue.Queue(maxsize=5000)
        t = threading.Thread(target=self._drain, daemon=True)
        t.start()

    def _post(self, action, payload):
        url = "%s/x/tokensaver/%s" % (self.base, action)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + self.key)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def gate(self, dig, unattended):
        """
        Ask the platform. Returns its answer, or None if it could not be
        reached. None means carry on locally, never means stop.
        """
        if self.offline:
            return None
        if self.show:
            sys.stderr.write("[digest] " + json.dumps(dig) + "\n")
        # Back off for a minute after a failure rather than adding the
        # timeout to every single request.
        if self.up is False and (time.time() - self.last_fail) < 60:
            return None
        try:
            out = self._post("gate", {"digest": dig, "unattended": unattended})
            if self.up is not True:
                sys.stderr.write("[saver] sebbi.pro reachable again\n")
            self.up = True
            return out
        except Exception as e:  # noqa: BLE001
            if self.up is not False:
                sys.stderr.write("[saver] sebbi.pro unreachable (%s). "
                                 "Traffic continues; records will catch up.\n"
                                 % e.__class__.__name__)
            self.up = False
            self.last_fail = time.time()
            return None

    def later(self, action, payload):
        """Fire and forget. Queued to disk if the network is down."""
        if self.offline:
            return
        try:
            self.q.put_nowait((action, payload))
        except queue.Full:
            pass

    def _drain(self):
        while True:
            try:
                action, payload = self.q.get(timeout=5)
            except queue.Empty:
                self._flush_outbox()
                continue
            try:
                self._post(action, payload)
                self.up = True
            except Exception:  # noqa: BLE001
                self.up = False
                self.last_fail = time.time()
                with self.store.lock:
                    self.store.enqueue(action, payload, time.time())
                    self.store.c.commit()

    def _flush_outbox(self):
        if self.offline or self.up is False:
            return
        with self.store.lock:
            rows = self.store.take_outbox()
        if not rows:
            return
        done = []
        for rid, action, payload in rows:
            try:
                self._post(action, json.loads(payload))
                done.append(rid)
            except Exception:  # noqa: BLE001
                self.up = False
                self.last_fail = time.time()
                break
        if done:
            with self.store.lock:
                self.store.drop_outbox(done)
                self.store.c.commit()


# --------------------------------------------------------------- findings

def local_findings(req, loop_n, has_stored):
    """
    Computed here, where the content is. These never go to sebbi.pro.
    """
    out = []
    msgs = req.get("messages") or []
    depth = len(msgs)
    tools = req.get("tools") or []

    if loop_n >= 2 and not has_stored:
        out.append("This exact request has gone out %d times in %d seconds "
                   "and no answer has been stored yet." % (loop_n, LOOP_WINDOW))
    if not deterministic(req):
        out.append("temperature is above zero, so this answer cannot be "
                   "reused. If it does not need to vary, setting it to zero "
                   "makes every repeat free.")
    if depth > CTX_FLAG_TURNS:
        carried = msgs[:-CTX_KEEP_TURNS]
        chars = sum(content_chars(m.get("content") if isinstance(m, dict)
                                  else m) for m in carried)
        out.append("%d turns re-sent every call; the oldest %d are roughly "
                   "%d tokens (estimated), paid again each time."
                   % (depth, len(carried), est_tokens(chars)))
    if tools:
        used = any("tool_use" in json.dumps(m, default=str)
                   or "tool_call" in json.dumps(m, default=str) for m in msgs)
        if not used:
            out.append("%d tool definitions attached and none has been "
                       "called; roughly %d tokens (estimated) on every request."
                       % (len(tools), est_tokens(content_chars(tools))))
    return out


# ----------------------------------------------------------------- server

PAGE = """<!doctype html><meta charset=utf-8>
<title>sebbi.pro token saver</title>
<style>
 body{{font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;
      background:#101E24;color:#ECEEEC;margin:0;padding:28px}}
 .w{{max-width:640px;margin:0 auto}}
 h1{{font-size:19px;letter-spacing:.02em;margin:0 0 4px}}
 .s{{color:#8fa6ae;font-size:13px;margin-bottom:26px}}
 .big{{font-size:42px;font-weight:700;color:#F5B31B;line-height:1.1}}
 .lbl{{color:#8fa6ae;font-size:13px;margin-bottom:26px}}
 .row{{display:table;width:100%;border-top:1px solid #1C3A44;padding:9px 0}}
 .k{{display:table-cell;color:#8fa6ae;font-size:14px}}
 .v{{display:table-cell;text-align:right;font-variant-numeric:tabular-nums}}
 .n{{margin-top:26px;color:#8fa6ae;font-size:12.5px;border-top:1px solid #1C3A44;
     padding-top:14px}}
 .ok{{color:#7fd1a8}} .no{{color:#e8a33d}}
</style>
<div class=w>
<h1>sebbi.pro token saver</h1>
<div class=s>listening on 127.0.0.1:{port} &middot; forwarding to {upstream}</div>
<div class=big>{saved}</div>
<div class=lbl>tokens not bought &middot; exact, from your provider's own counts</div>
<div class=row><div class=k>requests seen</div><div class=v>{seen}</div></div>
<div class=row><div class=k>served from your store</div><div class=v>{served}</div></div>
<div class=row><div class=k>stopped before the model</div><div class=v>{blocked}</div></div>
<div class=row><div class=k>answers stored here</div><div class=v>{stored}</div></div>
<div class=row><div class=k>sebbi.pro</div><div class="v {cls}">{link}</div></div>
<div class=n>Your prompts and answers are on this machine only. What goes to
sebbi.pro is a fingerprint and a set of counts. If it cannot be reached your
traffic carries on and the records catch up afterwards.</div>
</div>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    cfg = None
    store = None
    uplink = None

    def log_message(self, *a):
        pass

    def _out(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, str(v))
        self.end_headers()
        self.wfile.write(body)

    # ---- status pages -------------------------------------------------

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/") or "/"
        if p in ("/saver", "/"):
            return self._out(200, self._page(), "text/html; charset=utf-8")
        if p == "/saver/stats":
            return self._out(200, self._stats())
        if p == "/saver/health":
            return self._out(200, {"ok": True, "version": VERSION,
                                   "sebbi": self._link()})
        return self._out(404, {"error": "not found",
                               "try": ["/saver", "/saver/stats"]})

    def _link(self):
        if self.uplink.offline:
            return "offline by choice"
        return "connected" if self.uplink.up else "unreachable"

    def _stats(self):
        s = self.store
        with s.lock:
            stored = s.c.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
            ti = s.c.execute(
                "SELECT COALESCE(SUM(tok_in*hits),0), "
                "COALESCE(SUM(tok_out*hits),0) FROM answers").fetchone()
            out = {
                "version": VERSION,
                "requests_seen": int(s.total("seen")),
                "served_from_store": int(s.total("served")),
                "stopped_before_the_model": int(s.total("blocked")),
                "sent_to_the_model": int(s.total("forwarded")),
                "answers_stored_here": stored,
                "tokens_not_bought": {
                    "input": int(ti[0]), "output": int(ti[1]),
                    "total": int(ti[0] + ti[1]),
                    "certainty": "exact, as reported by your provider on the "
                                 "original call",
                },
                "queued_for_sebbi": s.c.execute(
                    "SELECT COUNT(*) FROM outbox").fetchone()[0],
                "sebbi_pro": self._link(),
                "content_sent_to_sebbi_pro": "none. A fingerprint and counts "
                                             "only.",
            }
        return out

    def _page(self):
        st = self._stats()
        return PAGE.format(
            port=self.cfg["port"], upstream=self.cfg["upstream"],
            saved="{:,}".format(st["tokens_not_bought"]["total"]),
            seen="{:,}".format(st["requests_seen"]),
            served="{:,}".format(st["served_from_store"]),
            blocked="{:,}".format(st["stopped_before_the_model"]),
            stored="{:,}".format(st["answers_stored_here"]),
            link=st["sebbi_pro"],
            cls="ok" if st["sebbi_pro"] == "connected" else "no")

    # ---- the actual gate ----------------------------------------------

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._out(400, {"error": "bad content length"})
        if n > MAX_BODY:
            return self._out(413, {"error": "request too large"})
        raw = self.rfile.read(n) if n else b"{}"

        try:
            req = json.loads(raw)
            if not isinstance(req, dict):
                raise ValueError
        except ValueError:
            # Not something we understand. Pass it through untouched.
            return self._forward(raw, None, "passthrough")

        if req.get("stream"):
            return self._forward(raw, req, "streaming-not-cached")

        now = time.time()
        fp = fingerprint(req)
        s = self.store

        with s.lock:
            row = s.get(fp, now)
            loop_n, burst_n = s.counts(fp, now)
            s.bump("seen")
            s.note_seen(fp, now)
            s.c.commit()

        # 1. Local store. No network, no provider, nothing bought.
        if row:
            with s.lock:
                s.hit(fp)
                s.bump("served")
                s.c.commit()
            self.uplink.later("gate", {"digest": digest_of(req),
                                       "unattended": self.cfg["unattended"]})
            return self._out(200, row[0], "application/json", {
                "X-Saver": "served-from-your-store",
                "X-Saver-Tokens-Not-Bought": (row[1] or 0) + (row[2] or 0),
            })

        # 2. Local hard rules. These run with or without a network.
        unattended = self.cfg["unattended"]
        rule = None
        if loop_n >= LOOP_HARD:
            rule = "runaway_loop"
        elif unattended and loop_n >= LOOP_HARD_UNATTENDED:
            rule = "runaway_loop_unattended"
        elif burst_n >= BURST_HARD:
            rule = "runaway_burst"

        if rule:
            with s.lock:
                s.bump("blocked")
                s.c.commit()
            self.uplink.later("gate", {"digest": digest_of(req),
                                       "unattended": unattended})
            return self._refuse(rule, req, loop_n, burst_n)

        # 3. The platform. If it does not answer, we carry on.
        verdict = None
        receipt = None
        findings = []
        if not self.cfg["local_only"]:
            ans = self.uplink.gate(digest_of(req), unattended)
            if ans:
                verdict = ans.get("verdict")
                receipt = (ans.get("receipt") or {}).get("hash")
                findings = [f.get("detail") for f in (ans.get("findings") or [])]

        if verdict == "BLOCK":
            with s.lock:
                s.bump("blocked")
                s.c.commit()
            return self._refuse(ans.get("rule") or "score", req, loop_n,
                                burst_n, receipt, ans.get("score"))

        if verdict == "CHALLENGE" and self.cfg["strict"]:
            with s.lock:
                s.bump("blocked")
                s.c.commit()
            return self._refuse("held_for_a_person", req, loop_n, burst_n,
                                receipt, ans.get("score"))

        if not findings:
            with s.lock:
                has = s.get(fp, now) is not None
            findings = local_findings(req, loop_n, has)

        return self._forward(raw, req, "sent-to-the-model", verdict, receipt,
                             findings)

    def _refuse(self, rule, req, loop_n, burst_n, receipt=None, score=None):
        ask = ask_ceiling(req)
        body = {
            "error": {
                "type": "sebbi_tokensaver_refused",
                "rule": rule,
                "message": {
                    "runaway_loop":
                        "The same request has gone out %d times in %d "
                        "seconds. It was stopped here rather than paid for."
                        % (loop_n, LOOP_WINDOW),
                    "runaway_loop_unattended":
                        "The same request has gone out %d times in %d "
                        "seconds with no human watching. Stopped here."
                        % (loop_n, LOOP_WINDOW),
                    "runaway_burst":
                        "%d requests in the last minute. Stopped here."
                        % burst_n,
                    "budget_exhausted":
                        "This key has reached its token ceiling.",
                    "exceeds_remaining_budget":
                        "This single call could cost more than the budget "
                        "left.",
                    "held_for_a_person":
                        "Held for a person to look at before spending.",
                }.get(rule, "Refused before reaching the model."),
                "tokens_not_spent": "this request never reached your provider, "
                                    "so no completion was paid for",
                "output_ceiling_it_would_have_authorised": ask,
            }
        }
        if receipt:
            body["error"]["receipt"] = receipt
        if score is not None:
            body["error"]["score"] = score
        return self._out(429, body, "application/json",
                         {"X-Saver": "refused", "X-Saver-Rule": rule})

    def _forward(self, raw, req, why, verdict=None, receipt=None,
                 findings=None):
        url = self.cfg["upstream"].rstrip("/") + self.path
        r = urllib.request.Request(url, data=raw, method="POST")
        for h in FORWARD_HEADERS:
            v = self.headers.get(h)
            if v:
                r.add_header(h, v)
        for k, v in (self.cfg.get("headers") or {}).items():
            r.add_header(k, v)

        try:
            with urllib.request.urlopen(r, timeout=self.cfg["timeout"]) as up:
                body, code = up.read(), up.getcode()
        except urllib.error.HTTPError as e:
            body, code = e.read(), e.code
        except Exception as e:  # noqa: BLE001
            return self._out(502, {"error": {
                "type": "upstream_unreachable",
                "message": "Your provider could not be reached. This is "
                           "between you and them; the saver only forwards.",
                "detail": str(e)}})

        with self.store.lock:
            self.store.bump("forwarded")
            self.store.c.commit()

        if code == 200 and isinstance(req, dict) and why == "sent-to-the-model":
            self._keep(req, body)

        extra = {"X-Saver": why}
        if verdict:
            extra["X-Saver-Verdict"] = verdict
        if receipt:
            extra["X-Saver-Receipt"] = receipt
        if findings:
            extra["X-Saver-Findings"] = str(len(findings))
            for i, f in enumerate(findings[:3]):
                extra["X-Saver-Finding-%d" % (i + 1)] = f[:180]
        return self._out(code, body, "application/json", extra)

    def _keep(self, req, body):
        """Store the answer here, and tell sebbi.pro only what it cost."""
        if not deterministic(req) and not self.cfg["store_varied"]:
            return
        try:
            resp = json.loads(body)
        except ValueError:
            return
        ti, to = usage_of(resp)
        now = time.time()
        fp = fingerprint(req)
        with self.store.lock:
            self.store.put(fp, req.get("model"), body, ti, to, now,
                           self.cfg["ttl"])
            self.store.c.commit()
        self.uplink.later("record", {
            "digest": digest_of(req),
            "usage": {"input_tokens": ti, "output_tokens": to},
        })


# ------------------------------------------------------------------- cli

def load_config(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_config(path, cfg):
    safe = dict(cfg)
    with open(path, "w") as f:
        json.dump(safe, f, indent=2)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        description="sebbi.pro token saver - change one line in your app")
    ap.add_argument("--key", help="your sebbi.pro key")
    ap.add_argument("--upstream", help="your provider, e.g. "
                                       "https://api.anthropic.com")
    ap.add_argument("--provider", choices=sorted(PROVIDERS),
                    help="shorthand for --upstream")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--sebbi", default=None, help="platform base url")
    ap.add_argument("--ttl-days", type=float, default=30.0)
    ap.add_argument("--timeout", type=float, default=300.0,
                    help="how long to wait on your provider")
    ap.add_argument("--gate-timeout", type=float, default=2.0,
                    help="how long to wait on sebbi.pro before carrying on")
    ap.add_argument("--unattended", action="store_true",
                    help="no human is watching this system")
    ap.add_argument("--strict", action="store_true",
                    help="also refuse requests marked for a person to check")
    ap.add_argument("--store-varied", action="store_true",
                    help="also store answers where temperature is above zero")
    ap.add_argument("--offline", action="store_true",
                    help="never contact sebbi.pro; local saving only")
    ap.add_argument("--local-only", action="store_true",
                    help="local rules decide; still send records to sebbi.pro")
    ap.add_argument("--show-digest", action="store_true",
                    help="print every digest before it is sent")
    ap.add_argument("--db", default=os.path.join(here, DB_NAME))
    ap.add_argument("--config", default=os.path.join(here, CONFIG_NAME))
    a = ap.parse_args()

    saved = load_config(a.config)
    key = a.key or saved.get("key") or os.environ.get("SEBBI_KEY")
    upstream = a.upstream or (PROVIDERS.get(a.provider) if a.provider else None) \
        or saved.get("upstream")
    sebbi = a.sebbi or saved.get("sebbi") or SEBBI_DEFAULT

    if not upstream:
        print("Which provider are you calling? Use one of:")
        print("  --provider anthropic      (https://api.anthropic.com)")
        print("  --provider openai         (https://api.openai.com)")
        print("  --upstream https://...    (anything else)")
        return 2

    if not key and not a.offline:
        print("No sebbi.pro key. Either:")
        print("  --key YOUR_KEY      to seal your savings as receipts")
        print("  --offline           to save tokens locally with no account")
        return 2

    cfg = {"key": key, "upstream": upstream, "sebbi": sebbi,
           "port": a.port, "unattended": a.unattended, "strict": a.strict,
           "store_varied": a.store_varied, "ttl": a.ttl_days * 86400,
           "timeout": a.timeout, "local_only": a.local_only,
           "headers": saved.get("headers") or {}}
    save_config(a.config, {"key": key, "upstream": upstream, "sebbi": sebbi,
                           "headers": cfg["headers"]})

    store = Store(a.db)
    uplink = Uplink(sebbi, key or "", store, timeout=a.gate_timeout,
                    offline=a.offline, show=a.show_digest)

    Handler.cfg = cfg
    Handler.store = store
    Handler.uplink = uplink

    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    srv.daemon_threads = True

    where = "http://%s:%d" % (a.host, a.port)
    print("")
    print("  sebbi.pro token saver %s" % VERSION)
    print("  ---------------------------------------------")
    print("  Change ONE line in your application:")
    print("")
    print("      base_url = \"%s\"" % where)
    print("")
    print("  forwarding to      %s" % upstream)
    print("  sebbi.pro          %s" % ("offline by choice" if a.offline
                                       else sebbi))
    print("  answers stored at  %s" % a.db)
    print("  what it has saved  %s/saver" % where)
    print("")
    print("  Your prompts stay on this machine. Only a fingerprint and")
    print("  counts go to sebbi.pro. If it is unreachable your traffic")
    print("  keeps flowing and the records catch up.")
    print("")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopping. Nothing was lost.")
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

500 lines, 18698 bytes

```python
"""
SEBDOG LICENCE SYSTEM v2.0.0
Air-gapped cryptographic licence tokens for the Sebdog Engine.
Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK

WHAT CHANGED IN 2.0, AND WHY IT HAD TO
--------------------------------------
Version 1 signed tokens with HMAC-SHA256. HMAC is symmetric: the same
secret both signs and verifies. So validating a token offline required
that secret to be present on the customer's hardware - and anyone
holding it can mint their own token for any device count, any plan, any
expiry.

Version 1's docstring said the signing secret never leaves sebbi.pro's
servers. With an offline HMAC check, that could not be true. One of the
two claims had to give, and it should not be the one about not shipping
the key.

Version 2 uses Ed25519. The server holds a private seed and signs. The
customer's copy holds only the PUBLIC key, which verifies signatures and
cannot produce one. Offline validation and an unshippable signing key
stop being in conflict, because they are no longer the same key.

    v1  customer holds the minting key   offline validation works
    v2  customer holds a public key      offline validation works

Everything else is unchanged: 7-day grace, local cache, tamper
detection, deterministic payload, constant-time comparison where it
still applies.

NO DEPENDENCY
-------------
Ed25519 is implemented here in pure standard library, the same way it
is in continuity.py and modules/signed.py. Nothing to pip install on a
customer's air-gapped box, which is the entire point of shipping this
rather than a library.

SETTING IT UP, ONCE
-------------------
    python3 sebdog_licence.py --keygen

Put the private seed in a Railway environment variable as
SEBDOG_LICENCE_SEED. Paste the public key into LICENCE_PUBKEY below and
into sebdog_engine.py. The private seed never appears in any file that
ships.

MIGRATING A v1 TOKEN
--------------------
There is no migration and there should not be one. A v1 token was
verifiable by anyone who had the secret, so any v1 token in the wild
should be treated as compromised and reissued. validate_token rejects
v1 tokens by version rather than pretending they are fine.
"""

import base64
import hashlib
import json
import os
import sqlite3
import threading
import time
from typing import Dict, Optional, Tuple

TOKEN_VERSION = "2"
GRACE_SECONDS = 86400 * 7          # 7 days past expiry before a hard block
AUDIT_DB = "sebdog_audit.db"

# The public half of the signing key. Safe to ship, safe to publish, and
# useless for producing a token. Overridable by environment for testing.
LICENCE_PUBKEY = os.environ.get("SEBDOG_LICENCE_PUBKEY", "")


# ==============================================================================
# Ed25519 - RFC 8032, standard library only
#
# Extended coordinates for the scalar multiplication so a verify is
# milliseconds rather than seconds. sign() is here for the server side; a
# customer's deployment only ever calls verify().
# ==============================================================================

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _xrecover(y):
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BY = 4 * pow(5, _P - 2, _P) % _P
_BX = _xrecover(_BY)
_B = (_BX % _P, _BY % _P, 1, _BX * _BY % _P)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = t1 * 2 * _D * t2 % _P
    dd = z1 * 2 * z2 % _P
    e, f, g, h = b - a, dd - c, dd + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _scalarmult(p, e):
    if e == 0:
        return (0, 1, 1, 0)
    q = _scalarmult(p, e >> 1)
    q = _add(q, q)
    if e & 1:
        q = _add(q, p)
    return q


def _encodepoint(p):
    x, y, z, _t = p
    zi = pow(z, _P - 2, _P)
    x = x * zi % _P
    y = y * zi % _P
    raw = bytearray(y.to_bytes(32, "little"))
    raw[31] |= (x & 1) << 7
    return bytes(raw)


def _decodepoint(raw):
    y = int.from_bytes(raw, "little") & ((1 << 255) - 1)
    if y >= _P:
        return None
    x = _xrecover(y)
    if x & 1 != (raw[31] >> 7) & 1:
        x = _P - x
    if (-x * x + y * y - 1 - _D * x * x * y * y) % _P != 0:
        return None
    return (x, y, 1, x * y % _P)


def _secret_scalar(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed: bytes) -> bytes:
    """The 32-byte public key for a 32-byte private seed."""
    a, _ = _secret_scalar(seed)
    return _encodepoint(_scalarmult(_B, a))


def sign(seed: bytes, message: bytes) -> bytes:
    """Server side only. Never called on customer hardware."""
    a, prefix = _secret_scalar(seed)
    pk = _encodepoint(_scalarmult(_B, a))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _L
    rp = _encodepoint(_scalarmult(_B, r))
    k = int.from_bytes(hashlib.sha512(rp + pk + message).digest(), "little") % _L
    s = (r + k * a) % _L
    return rp + s.to_bytes(32, "little")


def verify(pk: bytes, message: bytes, signature: bytes) -> bool:
    """True if the signature is valid. Never raises."""
    try:
        if len(pk) != 32 or len(signature) != 64:
            return False
        a = _decodepoint(pk)
        if a is None:
            return False
        r = _decodepoint(signature[:32])
        if r is None:
            return False
        s = int.from_bytes(signature[32:], "little")
        if s >= _L:
            return False
        k = int.from_bytes(
            hashlib.sha512(signature[:32] + pk + message).digest(),
            "little") % _L
        left = _scalarmult(_B, s)
        right = _add(r, _scalarmult(a, k))
        lx, ly, lz, _lt = left
        rx, ry, rz, _rt = right
        return ((lx * rz - rx * lz) % _P == 0
                and (ly * rz - ry * lz) % _P == 0)
    except Exception:
        return False


def keygen() -> Tuple[str, str]:
    """(private_seed_hex, public_key_hex). Run once, keep the first secret."""
    seed = os.urandom(32)
    return seed.hex(), public_key(seed).hex()


# ==============================================================================
# TOKEN GENERATION - sebbi.pro only
# ==============================================================================

def generate_token(api_key: str, devices: int, plan: str, email: str,
                   seed: bytes, validity_days: int = 365) -> str:
    """
    Sign an annual licence token.

    seed is the 32-byte Ed25519 private seed, read from the
    SEBDOG_LICENCE_SEED environment variable on the server. It is never
    written to a file that ships and never sent to a customer.
    """
    if isinstance(seed, str):
        seed = bytes.fromhex(seed.strip())
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")

    issued = int(time.time())
    payload = json.dumps({
        "v": TOKEN_VERSION,
        "key": api_key,
        "devices": devices,
        "plan": plan,
        "email": email,
        "issued": issued,
        "expires": issued + (validity_days * 86400),
    }, sort_keys=True, separators=(",", ":"))

    sig = sign(seed, payload.encode("utf-8")).hex()
    token = json.dumps({"payload": payload, "sig": sig, "alg": "ed25519"},
                       separators=(",", ":"))
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8")


# ==============================================================================
# TOKEN VALIDATION - customer hardware, no network, public key only
# ==============================================================================

def validate_token(token: str, pubkey=None) -> Tuple[Optional[Dict],
                                                     Optional[str]]:
    """
    Validate a licence token entirely locally.

    pubkey is the 32-byte public key, as hex or bytes. Defaults to
    LICENCE_PUBKEY. It cannot be used to produce a token, so shipping it
    inside the engine costs nothing.

    Returns (licence_data, None) or (None, error_code).

        invalid_format      cannot be decoded
        no_public_key       nothing configured to verify against
        invalid_signature   tampered with, or signed by the wrong key
        version_mismatch    not a v2 token - v1 HMAC tokens land here
        token_expired       past expiry plus the grace period
    """
    if pubkey is None:
        pubkey = LICENCE_PUBKEY
    if isinstance(pubkey, str):
        pubkey = pubkey.strip()
        if not pubkey:
            return None, "no_public_key"
        try:
            pubkey = bytes.fromhex(pubkey)
        except ValueError:
            return None, "no_public_key"
    if not pubkey or len(pubkey) != 32:
        return None, "no_public_key"

    try:
        raw = json.loads(base64.urlsafe_b64decode(token.encode("utf-8")))
        payload_str = raw.get("payload", "")
        sig_hex = raw.get("sig", "")
        if not payload_str or not sig_hex:
            return None, "invalid_format"
        sig = bytes.fromhex(sig_hex)
    except Exception:
        return None, "invalid_format"

    if not verify(pubkey, payload_str.encode("utf-8"), sig):
        return None, "invalid_signature"

    try:
        data = json.loads(payload_str)
    except Exception:
        return None, "invalid_format"

    if data.get("v") != TOKEN_VERSION:
        return None, "version_mismatch"

    if data.get("expires", 0) + GRACE_SECONDS < time.time():
        return None, "token_expired"

    return data, None


def is_in_grace_period(token_data: Dict) -> bool:
    return token_data.get("expires", 0) < time.time()


def days_until_expiry(token_data: Dict) -> int:
    return int((token_data.get("expires", 0) - time.time()) / 86400)


# ==============================================================================
# LOCAL LICENCE STORE
# ==============================================================================

_lock = threading.Lock()


def save_licence_locally(db_path: str, token: str, licence_data: Dict):
    with _lock:
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS licence_cache (
                id INTEGER PRIMARY KEY, token TEXT, api_key TEXT,
                devices INTEGER, plan TEXT, email TEXT,
                issued INTEGER, expires INTEGER, cached_at REAL)""")
        conn.execute("DELETE FROM licence_cache")
        conn.execute(
            "INSERT INTO licence_cache(token,api_key,devices,plan,email,"
            "issued,expires,cached_at) VALUES(?,?,?,?,?,?,?,?)",
            (token, licence_data.get("key", ""),
             licence_data.get("devices", 1), licence_data.get("plan", "free"),
             licence_data.get("email", ""), licence_data.get("issued", 0),
             licence_data.get("expires", 0), time.time()))
        conn.commit()
        conn.close()


def load_licence_locally(db_path: str) -> Optional[Tuple[str, Dict]]:
    """Returns (token, data) or None. The token is re-verified by the caller -
    a cached row is a convenience, never an authority."""
    try:
        with _lock:
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT token,api_key,devices,plan,email,issued,expires "
                "FROM licence_cache LIMIT 1").fetchone()
            conn.close()
        if not row:
            return None
        return row[0], {"v": TOKEN_VERSION, "key": row[1], "devices": row[2],
                        "plan": row[3], "email": row[4], "issued": row[5],
                        "expires": row[6]}
    except Exception:
        return None


# ==============================================================================
# STRESS TEST      python3 sebdog_licence.py
# KEY GENERATION   python3 sebdog_licence.py --keygen
# ==============================================================================

if __name__ == "__main__":
    import sys

    if "--keygen" in sys.argv:
        priv, pub = keygen()
        print("PRIVATE SEED - server only, never ships, never leaves Railway")
        print("  SEBDOG_LICENCE_SEED=" + priv)
        print()
        print("PUBLIC KEY - paste into LICENCE_PUBKEY here and in the engine")
        print("  " + pub)
        print()
        print("Losing the private seed means no new tokens can be issued and")
        print("every deployed public key must be replaced. Back it up.")
        sys.exit(0)

    print("SEBDOG LICENCE SYSTEM v2 - Ed25519 - Stress Test")
    print("=" * 62)

    SEED = os.urandom(32)
    PUB = public_key(SEED)
    TEST_KEY = "al_live_" + os.urandom(12).hex()
    PASSES = FAILURES = 0

    def check(name, condition, detail=""):
        global PASSES, FAILURES
        if condition:
            print("  PASS  " + name)
            PASSES += 1
        else:
            print("  FAIL  " + name + " " + str(detail))
            FAILURES += 1

    print("\n[1] Generation and validation")
    token = generate_token(TEST_KEY, 10000, "paid", "test@example.com", SEED)
    data, err = validate_token(token, PUB)
    check("Valid token accepted", err is None, err)
    check("API key preserved", data and data.get("key") == TEST_KEY)
    check("Device count preserved", data and data.get("devices") == 10000)
    check("Plan preserved", data and data.get("plan") == "paid")
    check("Not in grace period", data and not is_in_grace_period(data))
    check("Over 360 days remaining", data and days_until_expiry(data) > 360)
    check("Public key accepted as hex", validate_token(token, PUB.hex())[1] is None)

    print("\n[2] THE POINT OF VERSION 2")
    print("      A customer holds the public key. Can they mint a licence?")
    # Feeding the public key in as a seed does not error - it is 32 bytes,
    # so it derives some other keypair entirely. The property that matters
    # is that whatever comes out does NOT verify against the real key.
    attempt = generate_token(TEST_KEY, 999999, "enterprise",
                             "attacker@example.com", PUB)
    _, err = validate_token(attempt, PUB)
    check("Token minted with the public key does not verify",
          err == "invalid_signature", err)
    check("Public key is not the private seed",
          public_key(PUB) != PUB)
    other_seed = os.urandom(32)
    self_signed = generate_token(TEST_KEY, 999999, "enterprise",
                                 "attacker@example.com", other_seed)
    _, err = validate_token(self_signed, PUB)
    check("Token signed by any other key rejected", err == "invalid_signature")

    print("\n[3] Tamper detection")
    for label, old, new in [("device count", "10000", "99999"),
                            ("plan", "paid", "enterprise"),
                            ("expiry", '"expires"', '"expiries"')]:
        raw = json.loads(base64.urlsafe_b64decode(token))
        raw["payload"] = raw["payload"].replace(old, new)
        bad = base64.urlsafe_b64encode(
            json.dumps(raw, separators=(",", ":")).encode()).decode()
        _, err = validate_token(bad, PUB)
        check("Tampered " + label + " rejected", err == "invalid_signature", err)
    raw = json.loads(base64.urlsafe_b64decode(token))
    raw["sig"] = "00" * 64
    bad = base64.urlsafe_b64encode(
        json.dumps(raw, separators=(",", ":")).encode()).decode()
    check("Zeroed signature rejected",
          validate_token(bad, PUB)[1] == "invalid_signature")

    print("\n[4] Expiry")
    exp = generate_token(TEST_KEY, 100, "paid", "t@e.com", SEED, validity_days=-1)
    d, err = validate_token(exp, PUB)
    check("Recently expired token still runs in grace", err is None and d)
    check("Grace period reported", d and is_in_grace_period(d))
    hard = generate_token(TEST_KEY, 100, "paid", "t@e.com", SEED, validity_days=-9)
    check("Hard expired token rejected",
          validate_token(hard, PUB)[1] == "token_expired")

    print("\n[5] Wrong key")
    check("Unrelated public key rejected",
          validate_token(token, public_key(os.urandom(32)))[1] == "invalid_signature")
    flipped = bytearray(PUB)
    flipped[0] ^= 1
    check("One-bit-flipped public key rejected",
          validate_token(token, bytes(flipped))[1] == "invalid_signature")

    print("\n[6] Malformed input")
    for label, bad_in in [("garbage", "notbase64!!!"), ("empty", ""),
                          ("empty json", base64.urlsafe_b64encode(b"{}").decode())]:
        check(label + " rejected", validate_token(bad_in, PUB)[1] is not None)
    check("Missing public key reported",
          validate_token(token, "")[1] == "no_public_key")

    print("\n[7] v1 tokens are not silently accepted")
    v1_payload = json.dumps({"v": "1", "key": TEST_KEY, "devices": 10,
                             "plan": "paid", "email": "t@e.com",
                             "issued": int(time.time()),
                             "expires": int(time.time()) + 86400},
                            sort_keys=True, separators=(",", ":"))
    v1 = base64.urlsafe_b64encode(json.dumps(
        {"payload": v1_payload, "sig": sign(SEED, v1_payload.encode()).hex()},
        separators=(",", ":")).encode()).decode()
    check("v1 token rejected by version",
          validate_token(v1, PUB)[1] == "version_mismatch")

    print("\n[8] Local cache")
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db = f.name
    try:
        d, _ = validate_token(token, PUB)
        save_licence_locally(test_db, token, d)
        cached = load_licence_locally(test_db)
        check("Saved and retrieved", cached is not None)
        check("Cached token re-verifies",
              cached and validate_token(cached[0], PUB)[1] is None)
        check("Cached devices match", cached and cached[1]["devices"] == 10000)
    finally:
        os.unlink(test_db)

    print("\n[9] Performance")
    import timeit
    g = timeit.timeit(lambda: generate_token(TEST_KEY, 1, "paid", "t@e.com",
                                             SEED), number=50) / 50
    v = timeit.timeit(lambda: validate_token(token, PUB), number=50) / 50
    print("      sign   %.1f ms" % (g * 1000))
    print("      verify %.1f ms" % (v * 1000))
    check("Verification under 50ms", v < 0.05)

    print("\n" + "=" * 62)
    print("Results: %d passed, %d failed" % (PASSES, FAILURES))
    print("ALL TESTS PASSED." if not FAILURES else "FAILURES. Do not ship.")
    sys.exit(0 if not FAILURES else 1)

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
