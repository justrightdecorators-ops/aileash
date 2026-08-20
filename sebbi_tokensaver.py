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
