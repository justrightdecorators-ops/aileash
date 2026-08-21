# Codebase — part 7 of 25

Contains:
- `modules/pack.py`
- `modules/packconsole.py`
- `modules/peer.py`
- `modules/peerconsole.py`
- `modules/publish.py`


## `modules/pack.py`

501 lines, 20695 bytes

```python
"""
Evidence pack - /x/pack/<action>

WHAT THIS IS
------------
The sellable artifact. Everything else in this platform produces evidence;
this produces the document someone hands an auditor.

For a chosen period it does not summarise the chain, it RE-VERIFIES it:
every block in the range is rehashed from its stored contents using the
same function that sealed it, and compared to the hash recorded at the
time. Then the links between blocks are walked, and for a single key the
gapless receipt sequence is checked end to end.

A summary is a claim. A re-verification is a check anyone can repeat.

WHAT IT DOES NOT PROVE
----------------------
- That any decision recorded here was correct. Wrong answers seal just as
  cleanly as right ones.
- That an external peer's own chain is honest. That is checked at the
  peer's host, not here.
- Anything about periods outside the range requested.

    GET  /x/pack/spec                        public - what this does
    GET  /x/pack/preview?period=2026-Q2      keyed  - the pack as JSON
    GET  /x/pack/render?period=2026-Q2       keyed  - the pack as one page
    GET  /x/pack/history                     keyed  - packs issued
    POST /x/pack/issue                       keyed  - seal it into the chain

period accepts YYYY, YYYY-MM, YYYY-Qn. Add scope=me to limit the pack to
your own key; omit scope for a deployment-wide pack.
"""

import calendar
import datetime
import hashlib
import json
import time

VERSION = "1.0"

# (METHOD, action). Only the spec is open - a pack is customer evidence.
PUBLIC = {("GET", "spec")}

MAX_ROWS = 200000

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS pack_issued("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
            "period TEXT,scope TEXT,digest TEXT,issued REAL,"
            "entries INTEGER,verified INTEGER,mismatches INTEGER,"
            "audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_pack_key "
            "ON pack_issued(api_key)")
        ctx["conn"].commit()
    _ready = True


def _sha(p):
    """Identical to the engine's own sha(). Written out here rather than
    imported so this module depends on no other module's internals."""
    return hashlib.sha256(
        json.dumps(p, sort_keys=True).encode()).hexdigest()


def _iso(ts):
    if ts is None:
        return None
    return datetime.datetime.utcfromtimestamp(
        float(ts)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(ts):
    if ts is None:
        return None
    return datetime.datetime.utcfromtimestamp(
        float(ts)).strftime("%Y-%m-%d")


def _epoch(y, m, d):
    return float(calendar.timegm((y, m, d, 0, 0, 0, 0, 0, 0)))


def _bounds(period):
    """YYYY | YYYY-MM | YYYY-Qn -> (start, end, label)."""
    p = str(period or "").strip().upper()
    try:
        if len(p) == 4:
            y = int(p)
            return _epoch(y, 1, 1), _epoch(y + 1, 1, 1), p
        if len(p) == 7 and p[4] == "-" and p[5] == "Q":
            y, q = int(p[:4]), int(p[6])
            if q < 1 or q > 4:
                return None
            m = (q - 1) * 3 + 1
            em, ey = m + 3, y
            if em > 12:
                em, ey = em - 12, y + 1
            return _epoch(y, m, 1), _epoch(ey, em, 1), p
        if len(p) == 7 and p[4] == "-":
            y, m = int(p[:4]), int(p[5:])
            em, ey = m + 1, y
            if em > 12:
                em, ey = 1, y + 1
            return _epoch(y, m, 1), _epoch(ey, em, 1), p
    except (ValueError, IndexError):
        return None
    return None


# ----------------------------------------------------------------------
# assembly - the actual re-verification
# ----------------------------------------------------------------------

def _assemble(ctx, start, end, label, scope):
    c = ctx["conn"]
    cols = ("id,ts,event_json,result_json,prev_hash,audit_hash,"
            "api_key,key_seq")

    with ctx["lock"]:
        if scope:
            rows = c.execute(
                "SELECT " + cols + " FROM audit_log WHERE ts>=? AND ts<? "
                "AND api_key=? ORDER BY id ASC LIMIT ?",
                (start, end, scope, MAX_ROWS)).fetchall()
            began = c.execute(
                "SELECT MIN(ts) FROM audit_log WHERE api_key=?",
                (scope,)).fetchone()
            dev_all = c.execute(
                "SELECT COUNT(*) FROM device_seen WHERE api_key=?",
                (scope,)).fetchone()
            dev_new = c.execute(
                "SELECT COUNT(*) FROM device_seen WHERE api_key=? "
                "AND first_seen>=? AND first_seen<?",
                (scope, start, end)).fetchone()
        else:
            rows = c.execute(
                "SELECT " + cols + " FROM audit_log WHERE ts>=? AND ts<? "
                "ORDER BY id ASC LIMIT ?",
                (start, end, MAX_ROWS)).fetchall()
            began = c.execute("SELECT MIN(ts) FROM audit_log").fetchone()
            dev_all = c.execute(
                "SELECT COUNT(*) FROM device_seen").fetchone()
            dev_new = c.execute(
                "SELECT COUNT(*) FROM device_seen "
                "WHERE first_seen>=? AND first_seen<?",
                (start, end)).fetchone()
        chain_total = c.execute(
            "SELECT COUNT(*) FROM audit_log").fetchone()[0]

    verdicts = {}
    actions = {}
    seqs = []
    verified = 0
    mismatched = []
    link_breaks = []
    expect_prev = None
    per_day = {}

    for rid, ts, ev_j, res_j, prev, ah, akey, kseq in rows:
        try:
            ev = json.loads(ev_j)
            res = json.loads(res_j)
        except Exception:
            mismatched.append(rid)
            expect_prev = ah
            continue

        if _sha({"prev_hash": prev, "ts": ts,
                 "event": ev, "result": res}) == ah:
            verified += 1
        else:
            mismatched.append(rid)

        if expect_prev is not None and prev != expect_prev:
            link_breaks.append(rid)
        expect_prev = ah

        d = str(res.get("decision", "UNRECORDED"))
        verdicts[d] = verdicts.get(d, 0) + 1
        a = str(ev.get("action", "unrecorded"))
        actions[a] = actions.get(a, 0) + 1
        if kseq is not None:
            try:
                seqs.append(int(kseq))
            except (TypeError, ValueError):
                pass
        k = _day(ts)
        per_day[k] = per_day.get(k, 0) + 1

    # does the first block in the period chain to the one before it
    entry_link = "no_entries_in_period"
    if rows:
        with ctx["lock"]:
            before = c.execute(
                "SELECT audit_hash FROM audit_log WHERE id<? "
                "ORDER BY id DESC LIMIT 1", (rows[0][0],)).fetchone()
        if before is None:
            entry_link = ("intact_from_genesis"
                          if rows[0][4] == "GENESIS" else "broken")
        else:
            entry_link = "intact" if rows[0][4] == before[0] else "broken"

    seq = {"applicable": bool(scope and seqs)}
    if seq["applicable"]:
        lo, hi = min(seqs), max(seqs)
        have = set(seqs)
        missing = [n for n in range(lo, hi + 1) if n not in have]
        seq.update({"first": lo, "last": hi, "received": len(seqs),
                    "expected": hi - lo + 1,
                    "missing": missing[:200],
                    "gapless": not missing,
                    "note": "Receipt numbers are issued with no gaps by "
                            "construction. A missing number is a record "
                            "that left this chain."})

    clean = (not mismatched and not link_breaks
             and entry_link in ("intact", "intact_from_genesis"))

    p = {
        "pack_version": VERSION,
        "period": label,
        "period_start": _iso(start),
        "period_end": _iso(end),
        "generated_at": _iso(time.time()),
        "scope": ("key " + str(scope)[:12] + "\u2026") if scope
                 else "deployment-wide",
        "unbroken_since": _day(began[0] if began else None),
        "entries_in_period": len(rows),
        "chain_total_entries": chain_total,
        "first_block": rows[0][0] if rows else None,
        "first_hash": rows[0][5] if rows else None,
        "last_block": rows[-1][0] if rows else None,
        "last_hash": rows[-1][5] if rows else None,
        "integrity": {
            "clean": clean,
            "blocks_recomputed": len(rows),
            "hashes_verified": verified,
            "hash_mismatches": mismatched[:50],
            "link_breaks": link_breaks[:50],
            "link_into_period": entry_link,
            "method": "SHA-256 over {prev_hash, ts, event, result}, "
                      "recomputed from the stored row and compared to "
                      "the hash sealed at the time",
        },
        "receipt_sequence": seq,
        "verdicts": verdicts,
        "actions": dict(sorted(actions.items(), key=lambda x: -x[1])[:20]),
        "devices": {"total_ever": dev_all[0] if dev_all else 0,
                    "first_seen_in_period": dev_new[0] if dev_new else 0},
        "busiest_days": [{"day": d, "entries": n} for d, n in
                         sorted(per_day.items(), key=lambda x: -x[1])[:5]],
        "check_this_yourself": {
            "offline": "aileash_verify.py - stdlib only, no network",
            "still_on_this_chain": "/x/consistency/ancestor?tip=<last_hash>",
            "append_only": "/x/consistency/proof?first=&second=",
            "record_included": "/x/complete/prove",
            "who_witnessed_us": "/x/witness/peers",
        },
        "this_does_not_prove": [
            "That any decision recorded here was correct.",
            "That an external peer's own chain is honest - that is "
            "checked at the peer's host, not here.",
            "Anything about periods outside the dates above.",
        ],
    }
    p["pack_digest"] = hashlib.sha256(
        b"AILEASH-PACK-v1\x00" + json.dumps(
            p, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return p


# ----------------------------------------------------------------------
# one page, self contained
# ----------------------------------------------------------------------

def _html(p):
    ig = p["integrity"]
    sq = p["receipt_sequence"]
    good = "#7fe3b0"
    bad = "#ff8a80"

    def card(inner):
        return ("<div style='background:#10182e;border:1px solid #223055;"
                "border-radius:12px;padding:16px;margin-bottom:14px'>"
                + inner + "</div>")

    def row(k, v):
        return ("<tr><td style='padding:7px 0;border-bottom:1px solid "
                "#1d2a4a'>" + str(k) + "</td><td style='padding:7px 0;"
                "border-bottom:1px solid #1d2a4a;text-align:right;"
                "color:#c9a84c;font-weight:600'>" + str(v) + "</td></tr>")

    def mono(v):
        return ("<code style='font:12px ui-monospace,monospace;"
                "color:#9fb3d9;word-break:break-all'>" + str(v)
                + "</code>")

    integ = ("<div style='font-size:26px;font-weight:600;color:"
             + (good if ig["clean"] else bad) + "'>"
             + str(ig["hashes_verified"]) + " of "
             + str(ig["blocks_recomputed"]) + " blocks re-verified</div>"
             "<div style='color:#93a0bd;font-size:13px;margin-top:6px'>"
             + ig["method"] + "</div>")
    if not ig["clean"]:
        integ += ("<div style='color:" + bad + ";font-size:13px;"
                  "margin-top:8px'>mismatched blocks "
                  + str(ig["hash_mismatches"]) + " &middot; link breaks "
                  + str(ig["link_breaks"]) + " &middot; entry link "
                  + ig["link_into_period"] + "</div>")

    if sq.get("applicable"):
        seqbox = ("<div style='font-size:20px;font-weight:600;color:"
                  + (good if sq["gapless"] else bad) + "'>"
                  + ("Receipt sequence complete" if sq["gapless"]
                     else "GAPS IN RECEIPT SEQUENCE") + "</div>"
                  "<div style='color:#93a0bd;font-size:13px'>"
                  + str(sq["received"]) + " of " + str(sq["expected"])
                  + " received, numbers " + str(sq["first"]) + " to "
                  + str(sq["last"]) + "</div>")
        if not sq["gapless"]:
            seqbox += ("<div style='color:" + bad + ";font:12px "
                       "ui-monospace,monospace;margin-top:6px'>missing "
                       + str(sq["missing"]) + "</div>")
    else:
        seqbox = ("<div style='color:#93a0bd;font-size:13px'>Receipt "
                  "sequence applies to a single key. This pack is "
                  "deployment-wide.</div>")

    checks = "".join("<li><b>" + k.replace("_", " ") + "</b> " + mono(v)
                     + "</li>" for k, v in
                     p["check_this_yourself"].items())
    nots = "".join("<li>" + x + "</li>" for x in p["this_does_not_prove"])

    return (
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Evidence Pack " + p["period"] + " - AILeash</title>"
        "<body style='background:#0a0f1e;color:#e8ecf5;margin:0;"
        "padding:22px;font:15px/1.55 -apple-system,system-ui,sans-serif'>"
        "<div style='max-width:760px;margin:0 auto'>"
        "<h1 style='font-size:21px;margin:0 0 4px;color:#c9a84c'>"
        "Evidence Pack &mdash; " + p["period"] + "</h1>"
        "<div style='color:#93a0bd;font-size:13px;margin-bottom:20px'>"
        + p["scope"] + " &middot; " + str(p["period_start"]) + " to "
        + str(p["period_end"]) + " &middot; generated "
        + str(p["generated_at"]) + "</div>"
        + card("<div style='color:#93a0bd;font-size:13px'>Unbroken since"
               "</div><div style='font-size:26px;color:" + good
               + ";font-weight:600'>" + str(p["unbroken_since"])
               + "</div>")
        + card(integ)
        + card(seqbox)
        + card("<table style='width:100%;border-collapse:collapse;"
               "font-size:14px'>"
               + row("Entries in period", p["entries_in_period"])
               + row("Chain total entries", p["chain_total_entries"])
               + row("Devices, total ever", p["devices"]["total_ever"])
               + row("Devices first seen this period",
                     p["devices"]["first_seen_in_period"])
               + "".join(row(k, v) for k, v in sorted(
                   p["verdicts"].items()))
               + "".join(row(k, v) for k, v in p["actions"].items())
               + "</table>")
        + card("<div style='color:#93a0bd;font-size:13px'>First block</div>"
               + mono("#" + str(p["first_block"]) + " "
                      + str(p["first_hash"]))
               + "<div style='color:#93a0bd;font-size:13px;margin-top:10px'>"
                 "Last block</div>"
               + mono("#" + str(p["last_block"]) + " "
                      + str(p["last_hash"]))
               + "<div style='color:#93a0bd;font-size:13px;margin-top:10px'>"
                 "Pack digest</div>" + mono(p["pack_digest"]))
        + card("<div style='color:#93a0bd;font-size:13px'>Check every "
               "figure above yourself:</div><ul style='margin:6px 0 0 18px;"
               "padding:0;font-size:13px'>" + checks + "</ul>"
               "<div style='color:#93a0bd;font-size:13px;margin-top:14px'>"
               "What this pack does not prove:</div>"
               "<ul style='margin:6px 0 0 18px;padding:0;color:#93a0bd;"
               "font-size:13px'>" + nots + "</ul>")
        + "<div style='color:#6d7b99;font-size:12px;margin-top:18px'>"
          "AILeash &middot; sebbi.pro</div></div>")


# ----------------------------------------------------------------------

def _resolve(data, api_key):
    b = _bounds(data.get("period"))
    if not b:
        return None, ({"error": "period_required",
                       "accepts": ["YYYY", "YYYY-MM", "YYYY-Qn"],
                       "example": "/x/pack/preview?period=2026-Q2"}, 400)
    start, end, label = b
    if end > time.time():
        return None, ({"error": "period_not_closed", "period": label,
                       "message": "A pack can only cover a period that "
                                  "has finished."}, 409)
    scope = data.get("scope")
    if scope == "me":
        scope = api_key
    return (start, end, label, scope or None), None


def handle(method, action, data, api_key, ctx):
    if action == "spec":
        return {"module": "pack", "version": VERSION,
                "purpose": "Re-verifies every block in a period against "
                           "the hash sealed at the time, and checks the "
                           "gapless receipt sequence for a single key.",
                "periods": ["YYYY", "YYYY-MM", "YYYY-Qn"],
                "routes": {"GET /x/pack/spec": "public",
                           "GET /x/pack/preview?period=": "keyed, json",
                           "GET /x/pack/render?period=": "keyed, one page",
                           "GET /x/pack/history": "keyed",
                           "POST /x/pack/issue": "keyed, seals the pack"},
                "scope": "add scope=me for your key only; omit for "
                         "deployment-wide",
                "does_not_prove": [
                    "That any decision recorded here was correct.",
                    "That an external peer's chain is honest.",
                ]}, 200

    if not api_key:
        return {"error": "invalid_api_key"}, 401

    _setup(ctx)

    if method == "GET":
        if action == "history":
            with ctx["lock"]:
                rows = ctx["conn"].execute(
                    "SELECT period,scope,digest,issued,entries,verified,"
                    "mismatches,audit_hash,block_index FROM pack_issued "
                    "WHERE api_key=? ORDER BY id DESC LIMIT 200",
                    (api_key,)).fetchall()
            return {"count": len(rows), "packs": [
                {"period": r[0], "scope": r[1], "digest": r[2],
                 "issued": _iso(r[3]), "entries": r[4],
                 "hashes_verified": r[5], "mismatches": r[6],
                 "sealed_in_chain": r[7], "block_index": r[8]}
                for r in rows]}, 200

        if action in ("preview", "render"):
            got, err = _resolve(data, api_key)
            if err:
                return err
            start, end, label, scope = got
            p = _assemble(ctx, start, end, label, scope)
            if action == "preview":
                return p, 200
            return {"period": label, "content_type": "text/html",
                    "html": _html(p)}, 200

    if method == "POST" and action == "issue":
        got, err = _resolve(data, api_key)
        if err:
            return err
        start, end, label, scope = got
        p = _assemble(ctx, start, end, label, scope)
        ig = p["integrity"]
        ts = time.time()
        ev = {"user_id": "pack:" + label, "action": "evidence_pack_issued",
              "amount": 0, "country": "UK", "device_id": "pack",
              "anomaly": 0, "device_risk": 0}
        res = {"decision": "PACK_ISSUED", "score": 0, "pack_version": VERSION,
               "timestamp": ts, "period": label, "scope": p["scope"],
               "entries": p["entries_in_period"],
               "blocks_recomputed": ig["blocks_recomputed"],
               "hashes_verified": ig["hashes_verified"],
               "clean": ig["clean"], "pack_digest": p["pack_digest"],
               "note": "evidence pack issued; the pack's own digest is "
                       "now sealed, so the document cannot be edited "
                       "after the fact"}
        h, idx, seq = ctx["seal"](ev, res, ts, api_key)
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO pack_issued(api_key,period,scope,digest,"
                "issued,entries,verified,mismatches,audit_hash,"
                "block_index) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (api_key, label, p["scope"], p["pack_digest"], ts,
                 p["entries_in_period"], ig["hashes_verified"],
                 len(ig["hash_mismatches"]), h, idx))
            ctx["conn"].commit()
        p["sealed"] = {"audit_hash": h, "block_index": idx,
                       "receipt_seq": seq}
        return p, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "preview", "render", "history"],
            "POST": ["issue"]}, 404

```


## `modules/packconsole.py`

426 lines, 16973 bytes

```python
"""
modules/packconsole.py  -  the evidence pack page at /pack

WHY IT EXISTS
-------------
/x/pack/preview, render, issue and history are all keyed. A browser address
bar cannot send an Authorization header, so from a phone they are unreachable.
This serves one page that can.

It is deliberately NOT part of console.py. That file is large and editing it
on a phone risks the whole thing. This adds a second page and touches nothing
that already works.

SAME PATCH AS console.py / network.py
-------------------------------------
The router hands whatever handle() returns to send_json, so a module cannot
return HTML through it. This patches do_GET at runtime under its own
attribute name, adds two paths, and passes everything else straight through
to whatever was there before - including console.py's patch, whichever
installs first.

And the same catch: after every deploy one /x/ request must arrive before
/pack exists. Opening /x/packconsole/status does it, and Railway's
healthcheck on /x/console/status will arm this too once it is listed in
console.py's SIBLINGS.

THE KEY
-------
Typed in, held in a variable for that tab, never written to storage. Close
the tab and it is gone.
"""

import sys
from urllib.parse import urlparse

VERSION = "1.0"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/pack", "/pack.html", "/pack-console")

_patched = [False]


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Evidence pack - AILeash</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#0a0f1e;--panel:#131b2e;--panel2:#1a2338;
 --edge:rgba(201,168,76,.22);--gold:#c9a84c;--gold-dim:#8a7233;
 --text:#f2efe6;--mute:rgba(242,239,230,.42);--ok:#7fe3b0;--bad:#c8362b;
 --mono:ui-monospace,'IBM Plex Mono',monospace}
body{background:var(--ink);color:var(--text);font:16px/1.6 system-ui,
 -apple-system,sans-serif;padding:0 0 60px}
.wrap{max-width:640px;margin:0 auto;padding:0 18px}
header{padding:32px 0 20px;border-bottom:1px solid var(--edge);
 margin-bottom:24px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.24em;
 text-transform:uppercase;color:var(--gold);margin-bottom:10px}
h1{font-size:34px;line-height:1;letter-spacing:-.02em;font-weight:800}
h1 span{color:var(--gold)}
.sub{color:var(--mute);font-size:14.5px;margin-top:12px;max-width:46ch}
label{display:block;font-family:var(--mono);font-size:10px;
 letter-spacing:.16em;text-transform:uppercase;color:var(--mute);
 margin-bottom:7px}
input{width:100%;background:var(--panel);border:1px solid var(--edge);
 color:var(--text);font-family:var(--mono);font-size:13px;padding:12px 13px;
 border-radius:4px;outline:none}
input:focus{border-color:var(--gold)}
.box{background:var(--panel2);border:1px solid var(--edge);border-radius:6px;
 padding:16px;margin-bottom:16px}
.note{font-size:12px;color:var(--mute);margin-top:9px;line-height:1.55}
.field{margin-bottom:12px}
.seg{display:flex;gap:8px}
.seg button{flex:1}
button{width:100%;background:var(--gold);color:var(--ink);border:none;
 border-radius:4px;padding:13px;font-weight:700;font-size:14.5px;
 cursor:pointer;font-family:inherit}
button:hover:not(:disabled){background:#dbbd63}
button:disabled{opacity:.45;cursor:default}
button.quiet{background:transparent;color:var(--mute);
 border:1px solid var(--edge)}
button.quiet.on{color:var(--ink);background:var(--gold);border-color:var(--gold)}
button.quiet:hover:not(:disabled):not(.on){color:var(--text);
 border-color:var(--gold)}
.row{display:flex;gap:8px;margin-top:10px}
.row button{flex:1}
#out{margin-top:24px}
.verdict{border:1px solid var(--edge);border-radius:6px;background:var(--panel);
 overflow:hidden;margin-bottom:14px}
.v-head{padding:22px 18px;border-bottom:1px solid var(--edge)}
.v-word{font-size:38px;line-height:1;letter-spacing:-.02em;font-weight:800}
.v-ok{color:var(--ok)}.v-bad{color:var(--bad)}.v-mute{color:var(--mute)}
.v-why{color:var(--mute);font-size:13.5px;margin-top:10px;line-height:1.6}
.v-stats{display:flex;flex-wrap:wrap;gap:18px;padding:14px 18px;
 border-bottom:1px solid var(--edge);font-family:var(--mono);font-size:11px}
.v-stats b{display:block;font-size:19px;color:var(--text);font-weight:700;
 margin-top:3px;font-family:inherit}
.v-stats span{color:var(--mute);letter-spacing:.1em;text-transform:uppercase}
.lin{padding:14px 18px;border-bottom:1px solid var(--edge)}
.lin:last-child{border-bottom:none}
.strip-l{font-family:var(--mono);font-size:10px;letter-spacing:.16em;
 text-transform:uppercase;color:var(--gold);margin-bottom:10px}
.kv{display:flex;justify-content:space-between;gap:14px;padding:6px 0;
 border-bottom:1px solid rgba(201,168,76,.10);font-size:13.5px}
.kv:last-child{border-bottom:none}
.kv b{color:var(--gold);font-family:var(--mono);font-size:12.5px}
pre{font-family:var(--mono);font-size:11.5px;line-height:1.65;
 background:#080c16;color:var(--ok);padding:15px;border-radius:5px;
 overflow-x:auto;border:1px solid var(--edge);max-height:320px}
.msg{font-family:var(--mono);font-size:12.5px;padding:13px 15px;
 border-radius:5px;border:1px solid var(--edge);color:var(--mute);
 margin-bottom:14px}
.msg.bad{color:#ffb4ad;border-color:rgba(200,54,43,.5);
 background:rgba(200,54,43,.08)}
.msg.good{color:var(--ok);border-color:rgba(127,227,176,.35);
 background:rgba(26,158,110,.08)}
.working:after{content:'';animation:dots 1.2s steps(4,end) infinite}
@keyframes dots{0%{content:''}25%{content:'.'}50%{content:'..'}
 75%{content:'...'}}
iframe{width:100%;height:70vh;border:1px solid var(--edge);border-radius:6px;
 background:#0a0f1e;margin-top:12px}
code{font-family:var(--mono);font-size:12px;color:#9fb3d9;
 word-break:break-all}
footer{margin-top:32px;padding-top:18px;border-top:1px solid var(--edge);
 font-family:var(--mono);font-size:10.5px;color:var(--mute);line-height:1.8}
a{color:var(--gold)}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">AILeash &middot; evidence pack</p>
  <h1>The <span>document</span></h1>
  <p class="sub">Re-verifies every block in a period against the hash sealed
  at the time. Not a summary of the chain &mdash; a check of it.</p>
</header>

<div class="box">
  <label for="key">API key</label>
  <input id="key" type="password" placeholder="al_live_&hellip;"
   autocomplete="off" spellcheck="false">
  <p class="note">Held in memory for this tab only. Nothing is written to
  the device.</p>
</div>

<div class="box">
  <div class="field">
    <label for="period">Period</label>
    <input id="period" value="2026-Q2" autocomplete="off"
     placeholder="2026-Q2, 2026-07 or 2026">
  </div>
  <label>Scope</label>
  <div class="seg">
    <button class="quiet on" id="sc-me" onclick="setScope('me')">My key</button>
    <button class="quiet" id="sc-all" onclick="setScope('')">Whole deployment</button>
  </div>
  <p class="note">Receipt-sequence checking only applies to a single key.
  A deployment-wide pack still re-verifies every hash.</p>
  <div class="row">
    <button onclick="go('preview')">Preview</button>
    <button onclick="go('render')">View page</button>
  </div>
  <div class="row">
    <button class="quiet" onclick="go('history')">Past packs</button>
    <button class="quiet" onclick="go('issue')">Issue &amp; seal</button>
  </div>
  <p class="note">Issuing seals the pack's own digest into the chain, so the
  document cannot be edited afterwards. It cannot be withdrawn.</p>
</div>

<div id="out"></div>

<footer>
  Spec: <a href="/x/pack/spec">/x/pack/spec</a> &middot;
  Chain: <a href="/api/verify-chain">/api/verify-chain</a> &middot;
  Console: <a href="/console">/console</a>
</footer>

</div>

<script>
(function(){
  var out=document.getElementById('out'), busy=false, scope='me';

  window.setScope=function(v){
    scope=v;
    document.getElementById('sc-me').classList.toggle('on',v==='me');
    document.getElementById('sc-all').classList.toggle('on',v==='');
  };

  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function msg(t,k){out.innerHTML='<div class="msg '+(k||'')+'">'+esc(t)+'</div>';}
  function raw(o){return '<pre>'+esc(JSON.stringify(o,null,2))+'</pre>';}
  function key(){var k=document.getElementById('key').value.trim();
    if(!k){msg('Paste your API key at the top first.','bad');return null;}return k;}

  async function call(path,method,body){
    var k=key(); if(!k) return null;
    var o={method:method,headers:{'Authorization':'Bearer '+k}};
    if(body){o.headers['Content-Type']='application/json';
      o.body=JSON.stringify(body);}
    var r=await fetch(path,o), d;
    try{d=await r.json();}catch(e){d={error:'unreadable_response'};}
    return {status:r.status,data:d};
  }

  function qs(){
    var p=encodeURIComponent(document.getElementById('period').value.trim());
    return '?period='+p+(scope?'&scope='+scope:'');
  }

  function renderPack(d){
    var ig=d.integrity||{}, sq=d.receipt_sequence||{};
    var clean=!!ig.clean;
    var h='<div class="verdict"><div class="v-head">'
      +'<div class="v-word '+(clean?'v-ok':'v-bad')+'">'
      +esc(ig.hashes_verified)+' of '+esc(ig.blocks_recomputed)
      +'</div><div class="v-why">blocks re-verified &mdash; '
      +esc(ig.method||'')+'</div></div>'
      +'<div class="v-stats">'
      +'<div><span>period</span><b>'+esc(d.period)+'</b></div>'
      +'<div><span>entries</span><b>'+esc(d.entries_in_period)+'</b></div>'
      +'<div><span>unbroken since</span><b style="font-size:14px">'
      +esc(d.unbroken_since)+'</b></div>'
      +'<div><span>devices</span><b>'
      +esc((d.devices||{}).total_ever)+'</b></div></div>';

    if(!clean){
      h+='<div class="lin"><div class="strip-l">Problems found</div>'
        +'<div class="kv"><span>mismatched blocks</span><b>'
        +esc(JSON.stringify(ig.hash_mismatches||[]))+'</b></div>'
        +'<div class="kv"><span>link breaks</span><b>'
        +esc(JSON.stringify(ig.link_breaks||[]))+'</b></div>'
        +'<div class="kv"><span>link into period</span><b>'
        +esc(ig.link_into_period)+'</b></div></div>';
    }

    h+='<div class="lin"><div class="strip-l">Receipt sequence</div>';
    if(sq.applicable){
      h+='<div class="kv"><span>'+(sq.gapless?'Complete, no gaps'
         :'GAPS FOUND')+'</span><b>'+esc(sq.received)+' of '
         +esc(sq.expected)+'</b></div>';
      if(!sq.gapless){h+='<div class="kv"><span>missing</span><b>'
         +esc(JSON.stringify(sq.missing))+'</b></div>';}
    } else {
      h+='<div class="kv"><span>Not applicable to a deployment-wide pack'
         +'</span><b>&mdash;</b></div>';
    }
    h+='</div>';

    var vs=d.verdicts||{};
    if(Object.keys(vs).length){
      h+='<div class="lin"><div class="strip-l">Verdicts in period</div>';
      Object.keys(vs).sort().forEach(function(k){
        h+='<div class="kv"><span>'+esc(k)+'</span><b>'+esc(vs[k])
          +'</b></div>';});
      h+='</div>';
    }

    h+='<div class="lin"><div class="strip-l">Chain range</div>'
      +'<div class="kv"><span>first</span><b>#'+esc(d.first_block)
      +'</b></div><div class="kv"><span>last</span><b>#'+esc(d.last_block)
      +'</b></div><div class="kv"><span>pack digest</span></div>'
      +'<code>'+esc(d.pack_digest)+'</code></div>';

    if(d.sealed){
      h+='<div class="lin"><div class="strip-l">Sealed into the chain</div>'
        +'<div class="kv"><span>block</span><b>'+esc(d.sealed.block_index)
        +'</b></div><code>'+esc(d.sealed.audit_hash)+'</code></div>';
    }
    h+='</div>';
    return h;
  }

  function renderHistory(d){
    if(!d.count) return '<div class="msg">No packs issued yet.</div>';
    var h='<div class="verdict"><div class="v-head">'
      +'<div class="v-word v-ok">'+esc(d.count)+'</div>'
      +'<div class="v-why">packs issued and sealed</div></div><div class="lin">';
    (d.packs||[]).forEach(function(p){
      h+='<div class="kv"><span>'+esc(p.period)+' &middot; '+esc(p.issued)
        +'</span><b>'+esc(p.hashes_verified)+' verified'
        +(p.mismatches?' / '+esc(p.mismatches)+' bad':'')+'</b></div>';});
    h+='</div></div>';
    return h;
  }

  window.go=async function(what){
    if(busy) return;
    var period=document.getElementById('period').value.trim();
    if(what!=='history' && !period){
      msg('Give a period: 2026-Q2, 2026-07 or 2026.','bad'); return; }
    busy=true;
    out.innerHTML='<div class="msg"><span class="working">Re-verifying every '
      +'block in the period</span></div>';
    try{
      var res;
      if(what==='preview') res=await call('/x/pack/preview'+qs(),'GET');
      else if(what==='render') res=await call('/x/pack/render'+qs(),'GET');
      else if(what==='history') res=await call('/x/pack/history','GET');
      else res=await call('/x/pack/issue','POST',
        {period:period,scope:scope||undefined});
      if(!res){busy=false;return;}

      if(res.status===401){
        msg('That key was refused. Check it and try again.','bad');
      } else if(res.status===404 && res.data
                && res.data.error==='unknown_module'){
        msg('The pack module is not deployed. Open /x/pack/spec first.','bad');
      } else if(res.status>=400){
        out.innerHTML='<div class="msg bad">'
          +esc((res.data&&(res.data.message||res.data.error))
               ||('HTTP '+res.status))+'</div>'+raw(res.data);
      } else if(what==='render' && res.data.html){
        var f=document.createElement('iframe');
        f.setAttribute('sandbox','');
        f.srcdoc=res.data.html;
        out.innerHTML='<div class="msg good">The pack as one page. Long-press '
          +'to save, or screenshot it.</div>';
        out.appendChild(f);
      } else if(what==='history'){
        out.innerHTML=renderHistory(res.data)+raw(res.data);
      } else if(res.data.integrity){
        var pre = (what==='issue')
          ? '<div class="msg good">Issued and sealed. This cannot be '
            +'withdrawn.</div>' : '';
        out.innerHTML=pre+renderPack(res.data)+raw(res.data);
      } else {
        out.innerHTML='<div class="msg good">Done.</div>'+raw(res.data);
      }
    }catch(e){
      msg('Could not reach the server.','bad');
    }
    busy=false;
  };
})();
</script>
</body>
</html>
"""


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_packconsole_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            body = PAGE.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Robots-Tag", "noindex, nofollow")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._packconsole_patched = True
    _patched[0] = True
    print("PACKCONSOLE: /pack page installed at runtime", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("PACKCONSOLE: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    if method == "GET" and (action or "") in ("", "status"):
        return {"page": "/pack",
                "installed": bool(_patched[0]),
                "install_result": state,
                "version": VERSION,
                "calls": ["/x/pack/preview", "/x/pack/render",
                          "/x/pack/issue", "/x/pack/history"],
                "note": ("The page holds no credentials. Every route it "
                         "calls checks the key itself.")}, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status"]}, 404

```


## `modules/peer.py`

775 lines, 31547 bytes

```python
"""
modules/peer.py  v1.1  --  signed peer submission (shared secret)

READ THIS FIRST: WHAT THIS LANE BINDS, AND WHAT IT DOES NOT
    This lane authenticates with HMAC-SHA256 over a shared secret.

    A shared secret is held by BOTH parties. So a valid signature proves
    the submission came from someone holding that secret -- which is the
    peer, and also the operator of this deployment.

        It closes third-party submission under your name.
        It does NOT close operator submission under your name.

    That is a normal property of HMAC and not a defect. It is stated here,
    at the top, because "signed" reads stronger than it is, and a peer
    choosing between lanes should not have to work that out for
    themselves. Raised by Ishaan (Shango MID), who was right.

    If you need the operator excluded as well, use /x/signed/submit
    instead. There you generate an Ed25519 keypair, keep the private half,
    and this deployment holds only the public half -- so it can verify a
    signature and can never produce one. That property is arithmetic
    rather than a promise about our conduct.

    Both lanes stay open. This one is simpler to implement and costs the
    peer no key custody, which is a real advantage if a long-lived private
    key is a liability you would rather not carry. The other is stronger.
    Pick deliberately.

WHY THIS EXISTS
    /x/witness/observe is unauthenticated on purpose. Anyone can submit a
    tip without an account, and that openness is what answers the
    collusion objection -- nobody has to trust us to audit the network.

    The cost of that openness is that anyone can submit a tip under any
    name. Name binding catches most of it; it does not prevent it.

    A named peer exchanging period roots wants a stronger guarantee than
    the open endpoint gives. This module provides one WITHOUT changing the
    open endpoint. All three run side by side.

WHAT IT COVERS
    canonicalization, HMAC-SHA256 signing, nonce, replay window, clock
    skew, idempotency, retry semantics, suspension, key rotation with
    overlap.

AUTH LIVES IN THE BODY, NOT IN HEADERS
    The module router hands modules a parsed body, not the raw headers,
    so every authentication field travels in the JSON body. This also
    makes the scheme trivial to implement from any language and easy to
    replay in a test.

THE SCHEME, IN FULL
    Envelope:
        {
          "peer_id":         "prae-001",
          "ts":              1755432000,          integer unix seconds
          "nonce":           "<>=16 chars, unique per peer>",
          "idempotency_key": "<optional, <=128 chars>",
          "payload":         { ... the thing being submitted ... },
          "signature":       "<hex hmac-sha256>"
        }

    THOSE FIELDS AND NO OTHERS. The server rebuilds the envelope from the
    known field names before checking the signature, so any extra
    top-level field you signed will not be part of what we verify and the
    signature will not match. Put anything of your own inside payload.
    This trips people up and now it is written down.

    String to sign:
        "AILEASH-PEER-v1\\n" + canonical(envelope_without_signature)

    canonical() is exactly:
        json.dumps(obj, sort_keys=True, separators=(",",":"),
                   ensure_ascii=True)

    signature = hmac_sha256(secret, string_to_sign).hexdigest()

    POST /x/peer/canonical returns the exact string to sign for a given
    envelope, so an implementer can debug canonicalization without
    holding or revealing a secret.

RULES
    clock skew      +/- 300s. Outside that: 401 clock_skew.
    nonce           unique per peer for 900s. Reused: 409 replay.
    idempotency     same key + same payload digest returns the FIRST
                    response verbatim, sealed once. Same key + different
                    payload: 409 idempotency_conflict.
    retry           safe. Retry the identical envelope; idempotency makes
                    it a no-op that returns the original receipt.
    suspension      403 peer_suspended. Submissions refused, nothing
                    deleted, the peer's history stands.
    rotation        two secrets live at once. A new secret is issued and
                    the previous one stays valid for ROTATION_OVERLAP
                    (default 24h) so a peer can roll without downtime.

                    Note the asymmetry with the other lane: here the
                    OPERATOR issues and rotates the secret, because the
                    operator holds it too. At /x/signed/rotate the peer
                    rotates their own key and the operator cannot, because
                    a rotation must be signed by the key being replaced.

ROUTES
    GET  spec       public   full implementation guide
    POST canonical  public   the exact string to sign. no secret needed.
    GET  peers      public   peer ids, status, rotation state. no secrets.
    POST submit     public route, SIGNATURE authenticated
    POST register   keyed    operator issues a peer credential
    POST rotate     keyed    issue a new secret, overlap the old
    POST suspend    keyed
    POST resume     keyed
    GET  history    keyed    submissions by peer

TABLES OWNED
    peer_registry, peer_nonce, peer_submission
"""

import hashlib
import hmac
import json
import os
import re
import time

VERSION = "1.1"

PUBLIC = {
    ("GET", "spec"),
    ("POST", "canonical"),
    ("GET", "peers"),
    ("POST", "submit"),
}

SIGN_PREFIX = "AILEASH-PEER-v1\n"

CLOCK_SKEW_SECONDS = 300
NONCE_TTL_SECONDS = 900
NONCE_MIN_LENGTH = 16
ROTATION_OVERLAP_SECONDS = 86400
MAX_PAYLOAD_BYTES = 65536
MAX_IDEMPOTENCY_KEY = 128

# The one paragraph that must appear anywhere this lane describes itself.
# Kept as a constant so it cannot drift between the spec route, the
# register response and the peers listing.
SHARED_SECRET_SCOPE = (
    "This lane authenticates with a shared secret, held by both the peer "
    "and the operator of this deployment. A valid signature proves the "
    "submission came from a holder of that secret. It closes third-party "
    "submission under your name and it does not close operator submission "
    "under your name. That is a normal property of HMAC, stated rather "
    "than implied. For a lane where the operator is excluded too, use "
    "/x/signed/submit - you keep the private key and we hold only the "
    "public half, so we can verify a signature and can never produce one."
)

_PEER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")

_ready = False


# ---------------------------------------------------------------- storage

def _setup(ctx):
    global _ready
    if _ready:
        return
    conn = ctx["conn"]
    with ctx["lock"]:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS peer_registry (
                peer_id          TEXT PRIMARY KEY,
                chain_name       TEXT,
                url              TEXT,
                secret_current   TEXT,
                secret_previous  TEXT,
                rotated_at       REAL,
                status           TEXT DEFAULT 'active',
                created          REAL,
                submissions      INTEGER DEFAULT 0,
                last_seen        REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS peer_nonce (
                peer_id   TEXT,
                nonce     TEXT,
                seen_at   REAL,
                PRIMARY KEY (peer_id, nonce)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS peer_submission (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                peer_id          TEXT,
                ts               REAL,
                idempotency_key  TEXT,
                payload_digest   TEXT,
                response_json    TEXT,
                audit_hash       TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_peer_sub_idem "
            "ON peer_submission(peer_id, idempotency_key)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_peer_nonce_time "
            "ON peer_nonce(seen_at)")
        conn.commit()
    _ready = True


# ------------------------------------------------------------ primitives

def canonical(obj):
    """
    THE canonicalization. Any implementation in any language must produce
    this byte-for-byte. Sorted keys, no whitespace, ASCII-escaped.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def string_to_sign(envelope):
    """Envelope WITHOUT the signature field, prefixed and canonicalized."""
    unsigned = {k: v for k, v in envelope.items() if k != "signature"}
    return SIGN_PREFIX + canonical(unsigned)


def sign(secret, envelope):
    return hmac.new(secret.encode("utf-8"),
                    string_to_sign(envelope).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _digest(payload):
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def _new_secret():
    return os.urandom(32).hex()


def _now():
    return time.time()


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except Exception:
        return None


def _sweep_nonces(ctx):
    cutoff = _now() - NONCE_TTL_SECONDS
    with ctx["lock"]:
        ctx["conn"].execute("DELETE FROM peer_nonce WHERE seen_at < ?",
                            (cutoff,))
        ctx["conn"].commit()


# ------------------------------------------------------------ the submit

def _submit(ctx, data):
    """
    Signature-authenticated. No API key. Every rule on the list is
    enforced here, in a fixed order, and each failure names itself.
    """
    _setup(ctx)

    # ---- shape
    peer_id = (data.get("peer_id") or "").strip()
    signature = (data.get("signature") or "").strip()
    nonce = (data.get("nonce") or "").strip()
    payload = data.get("payload")
    idem = (data.get("idempotency_key") or "").strip()[:MAX_IDEMPOTENCY_KEY]

    if not peer_id or not signature or not nonce or payload is None:
        return {"ok": False, "error": "malformed_envelope",
                "required": ["peer_id", "ts", "nonce", "payload",
                             "signature"]}, 400

    try:
        ts = int(data.get("ts"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "malformed_ts",
                "detail": "ts must be an integer of unix seconds"}, 400

    if len(nonce) < NONCE_MIN_LENGTH:
        return {"ok": False, "error": "nonce_too_short",
                "minimum": NONCE_MIN_LENGTH}, 400

    if len(canonical(payload).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        return {"ok": False, "error": "payload_too_large",
                "max_bytes": MAX_PAYLOAD_BYTES}, 413

    # ---- peer known and active
    row = ctx["conn"].execute(
        "SELECT peer_id, chain_name, secret_current, secret_previous, "
        "rotated_at, status FROM peer_registry WHERE peer_id = ?",
        (peer_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "unknown_peer", "peer_id": peer_id}, 401
    if row[5] == "suspended":
        return {"ok": False, "error": "peer_suspended",
                "detail": "Submissions refused. Existing history stands "
                          "and nothing has been removed."}, 403

    # ---- clock skew, before any expensive work
    skew = abs(_now() - ts)
    if skew > CLOCK_SKEW_SECONDS:
        return {"ok": False, "error": "clock_skew",
                "detail": "Timestamp is %.0fs from server time; the window "
                          "is +/-%ds." % (skew, CLOCK_SKEW_SECONDS),
                "server_time": int(_now())}, 401

    # ---- signature, against current then previous secret
    #
    # Note the envelope is rebuilt from KNOWN field names only. Any extra
    # top-level field the caller signed is not part of what we verify, so
    # the signature will not match. Documented in the spec; the failure
    # response points at /x/peer/canonical, which is the fastest way for
    # an implementer to see the difference.
    envelope = {"peer_id": peer_id, "ts": ts, "nonce": nonce,
                "payload": payload}
    if idem:
        envelope["idempotency_key"] = idem

    accepted_with = None
    if row[2] and hmac.compare_digest(sign(row[2], envelope), signature):
        accepted_with = "current"
    elif row[3] and (row[4] or 0) + ROTATION_OVERLAP_SECONDS > _now():
        if hmac.compare_digest(sign(row[3], envelope), signature):
            accepted_with = "previous"

    if not accepted_with:
        return {"ok": False, "error": "bad_signature",
                "detail": "HMAC did not match. POST the same envelope to "
                          "/x/peer/canonical to see the exact string this "
                          "server signs.",
                "common_cause": "An extra top-level field in your envelope. "
                                "Only peer_id, ts, nonce, payload and "
                                "idempotency_key are signed; anything else "
                                "belongs inside payload.",
                "string_to_sign_sha256":
                    hashlib.sha256(
                        string_to_sign(envelope).encode()).hexdigest(),
                }, 401

    payload_digest = _digest(payload)

    # ---- idempotency, before the nonce check so a retry is a clean no-op
    if idem:
        prior = ctx["conn"].execute(
            "SELECT payload_digest, response_json FROM peer_submission "
            "WHERE peer_id = ? AND idempotency_key = ?",
            (peer_id, idem)).fetchone()
        if prior:
            if prior[0] != payload_digest:
                return {"ok": False, "error": "idempotency_conflict",
                        "detail": "That idempotency key was used with a "
                                  "different payload."}, 409
            out = json.loads(prior[1])
            out["replayed"] = True
            out["note"] = ("Idempotent retry. This is the original receipt; "
                           "nothing was sealed twice.")
            return out, 200

    # ---- replay
    _sweep_nonces(ctx)
    seen = ctx["conn"].execute(
        "SELECT seen_at FROM peer_nonce WHERE peer_id = ? AND nonce = ?",
        (peer_id, nonce)).fetchone()
    if seen:
        return {"ok": False, "error": "replay",
                "detail": "That nonce has already been used by this peer "
                          "within the %ds window. Use a fresh nonce, or "
                          "send an idempotency_key if you meant to retry."
                          % NONCE_TTL_SECONDS}, 409

    # ---- accept: seal it
    now = _now()
    event = {"module": "peer", "action": "submit", "peer_id": peer_id,
             "chain_name": row[1], "payload_digest": payload_digest,
             "payload": payload}
    result = {"accepted": True, "signed_with": accepted_with,
              "auth": "hmac-shared-secret"}
    audit_hash = block_index = receipt_seq = None
    try:
        audit_hash, block_index, receipt_seq = ctx["seal"](
            event, result, now, None)
    except Exception:
        pass

    out = {
        "ok": True,
        "accepted": True,
        "peer_id": peer_id,
        "chain_name": row[1],
        "payload_digest": payload_digest,
        "signed_with": accepted_with,
        "auth": "hmac-shared-secret",
        "auth_scope": SHARED_SECRET_SCOPE,
        "received_at": _iso(now),
        "receipt": {"audit_hash": audit_hash,
                    "block_index": block_index,
                    "receipt_seq": receipt_seq},
        "verify": {
            "inclusion": "/x/complete/prove",
            "ancestry": "/x/consistency/ancestor?tip=<any tip we served>",
            "append_only": "/x/consistency/proof?first=&second=",
        },
    }

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO peer_nonce (peer_id, nonce, seen_at) "
            "VALUES (?,?,?)", (peer_id, nonce, now))
        ctx["conn"].execute(
            "INSERT INTO peer_submission (peer_id, ts, idempotency_key, "
            "payload_digest, response_json, audit_hash) VALUES (?,?,?,?,?,?)",
            (peer_id, now, idem or None, payload_digest,
             json.dumps(out), audit_hash))
        ctx["conn"].execute(
            "UPDATE peer_registry SET submissions = submissions + 1, "
            "last_seen = ? WHERE peer_id = ?", (now, peer_id))
        ctx["conn"].commit()

    if accepted_with == "previous":
        out["warning"] = ("Accepted with the previous secret. The overlap "
                          "window ends %s." % _iso((row[4] or 0) +
                                                   ROTATION_OVERLAP_SECONDS))
    return out, 200


# ------------------------------------------------------------- operator

def _register(ctx, data):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    if not _PEER_ID_RE.match(peer_id):
        return {"ok": False, "error": "bad_peer_id",
                "detail": "lowercase letters, digits, dot, dash, "
                          "underscore; 2-63 chars"}, 400
    if ctx["conn"].execute("SELECT 1 FROM peer_registry WHERE peer_id = ?",
                           (peer_id,)).fetchone():
        return {"ok": False, "error": "peer_exists",
                "detail": "Use /x/peer/rotate to issue a new secret."}, 409

    secret = _new_secret()
    now = _now()
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO peer_registry (peer_id, chain_name, url, "
            "secret_current, secret_previous, rotated_at, status, created) "
            "VALUES (?,?,?,?,NULL,NULL,'active',?)",
            (peer_id, (data.get("chain_name") or peer_id).strip()[:120],
             (data.get("url") or "").strip()[:400], secret, now))
        ctx["conn"].commit()
    try:
        ctx["seal"]({"module": "peer", "action": "register",
                     "peer_id": peer_id},
                    {"registered": True}, now, None)
    except Exception:
        pass

    return {
        "ok": True,
        "peer_id": peer_id,
        "secret": secret,
        "warning": "This secret is shown once and is not recoverable. "
                   "Send it to the peer over a channel you trust.",
        "tell_the_peer_this": SHARED_SECRET_SCOPE,
        "endpoint": "/x/peer/submit",
        "spec": "/x/peer/spec",
        "stronger_lane": "/x/signed/spec",
    }, 200


def _rotate(ctx, data):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    row = ctx["conn"].execute(
        "SELECT secret_current FROM peer_registry WHERE peer_id = ?",
        (peer_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "unknown_peer"}, 404

    new = _new_secret()
    now = _now()
    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE peer_registry SET secret_previous = secret_current, "
            "secret_current = ?, rotated_at = ? WHERE peer_id = ?",
            (new, now, peer_id))
        ctx["conn"].commit()
    try:
        ctx["seal"]({"module": "peer", "action": "rotate",
                     "peer_id": peer_id}, {"rotated": True}, now, None)
    except Exception:
        pass

    return {
        "ok": True,
        "peer_id": peer_id,
        "secret": new,
        "previous_valid_until": _iso(now + ROTATION_OVERLAP_SECONDS),
        "detail": "Both secrets are accepted until then, so the peer can "
                  "roll over without downtime. Submissions signed with the "
                  "old one come back marked.",
        "note": "The operator rotates this credential because the operator "
                "holds it. At /x/signed/rotate the peer rotates their own "
                "key and the operator cannot, because a rotation there must "
                "be signed by the key being replaced.",
    }, 200


def _set_status(ctx, data, status):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    if not ctx["conn"].execute("SELECT 1 FROM peer_registry WHERE peer_id = ?",
                               (peer_id,)).fetchone():
        return {"ok": False, "error": "unknown_peer"}, 404
    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE peer_registry SET status = ? WHERE peer_id = ?",
            (status, peer_id))
        ctx["conn"].commit()
    try:
        ctx["seal"]({"module": "peer", "action": status,
                     "peer_id": peer_id}, {"status": status}, _now(), None)
    except Exception:
        pass
    return {"ok": True, "peer_id": peer_id, "status": status}, 200


def _peers(ctx):
    _setup(ctx)
    now = _now()
    rows = ctx["conn"].execute(
        "SELECT peer_id, chain_name, url, status, created, submissions, "
        "last_seen, rotated_at FROM peer_registry ORDER BY created"
    ).fetchall()
    return {
        "ok": True,
        "count": len(rows),
        "auth": "hmac-shared-secret",
        "auth_scope": SHARED_SECRET_SCOPE,
        "peers": [{
            "peer_id": r[0], "chain_name": r[1], "url": r[2] or None,
            "status": r[3], "registered": _iso(r[4]),
            "submissions": r[5], "last_seen": _iso(r[6]) if r[6] else None,
            "rotation_overlap_active":
                bool(r[7] and r[7] + ROTATION_OVERLAP_SECONDS > now),
        } for r in rows],
        "note": "Secrets are never returned by any route.",
    }, 200


def _history(ctx, data):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    try:
        limit = min(int(data.get("limit", 50)), 500)
    except (TypeError, ValueError):
        limit = 50
    q = ("SELECT peer_id, ts, idempotency_key, payload_digest, audit_hash "
         "FROM peer_submission")
    args = []
    if peer_id:
        q += " WHERE peer_id = ?"
        args.append(peer_id)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    rows = ctx["conn"].execute(q, args).fetchall()
    return {
        "ok": True, "count": len(rows),
        "submissions": [{
            "peer_id": r[0], "at": _iso(r[1]), "idempotency_key": r[2],
            "payload_digest": r[3], "audit_hash": r[4],
        } for r in rows],
    }, 200


def _canonical_route(data):
    """
    Debugging aid. Give it an envelope, get back the exact string this
    server will sign. Reveals nothing -- the secret is not involved.
    """
    env = dict(data or {})
    env.pop("signature", None)
    if "ts" in env:
        try:
            env["ts"] = int(env["ts"])
        except (TypeError, ValueError):
            return {"ok": False, "error": "malformed_ts"}, 400
    s = string_to_sign(env)
    known = {"peer_id", "ts", "nonce", "payload", "idempotency_key"}
    extra = sorted(k for k in env if k not in known)
    out = {
        "ok": True,
        "string_to_sign": s,
        "sha256": hashlib.sha256(s.encode("utf-8")).hexdigest(),
        "byte_length": len(s.encode("utf-8")),
        "recipe": "\"AILEASH-PEER-v1\\n\" + json.dumps(envelope_without_"
                  "signature, sort_keys=True, separators=(\",\",\":\"), "
                  "ensure_ascii=True)",
        "then": "signature = hmac_sha256(secret, string_to_sign).hexdigest()",
    }
    if extra:
        out["warning"] = (
            "This route echoes whatever you sent, but /x/peer/submit "
            "rebuilds the envelope from known fields only. These extra "
            "top-level fields would NOT be part of what submit verifies, "
            "so a signature over the string above would be rejected: %s. "
            "Move them inside payload." % ", ".join(extra))
    return out, 200


# ------------------------------------------------------------------ spec

def _spec():
    return {
        "module": "peer",
        "version": VERSION,
        "auth": "hmac-shared-secret",
        "read_this_first": SHARED_SECRET_SCOPE,
        "purpose":
            "Signed submission for named peers. Sits beside the open "
            "/x/witness/observe endpoint rather than replacing it. The "
            "open endpoint stays unauthenticated so anyone can audit the "
            "network without an account; this one guarantees that only a "
            "holder of the peer secret can submit as that chain -- noting "
            "that the operator is also a holder.",
        "choosing_a_lane": {
            "/x/witness/observe": "Open. No credential. Anyone can submit "
                                  "under any name; the record says how "
                                  "strong the claim is rather than "
                                  "refusing it.",
            "/x/peer/submit": "This lane. Shared secret. Excludes third "
                              "parties, does not exclude the operator. No "
                              "key custody burden on the peer.",
            "/x/signed/submit": "Ed25519. The peer holds the private key "
                                "and this deployment holds only the public "
                                "half, so the operator is excluded too. "
                                "Strongest, at the cost of the peer "
                                "carrying a long-lived private key.",
        },
        "envelope": {
            "peer_id": "string, issued at registration",
            "ts": "integer unix seconds",
            "nonce": "string, at least %d chars, unique per peer for %ds"
                     % (NONCE_MIN_LENGTH, NONCE_TTL_SECONDS),
            "idempotency_key": "optional string, max %d chars"
                               % MAX_IDEMPOTENCY_KEY,
            "payload": "object. period roots, tips, whatever is agreed. "
                       "max %d bytes canonicalized." % MAX_PAYLOAD_BYTES,
            "signature": "hex hmac-sha256",
            "no_other_top_level_fields":
                "The server rebuilds the envelope from exactly the field "
                "names above before verifying. Any extra top-level field "
                "you signed is not part of what we verify and your "
                "signature will not match. Put your own data inside "
                "payload.",
        },
        "canonicalization": {
            "recipe": "json.dumps(obj, sort_keys=True, "
                      "separators=(\",\",\":\"), ensure_ascii=True)",
            "string_to_sign": "\"AILEASH-PEER-v1\\n\" + canonical(envelope "
                              "with the signature field removed)",
            "signature": "hmac_sha256(secret, string_to_sign).hexdigest()",
            "debug": "POST the envelope to /x/peer/canonical to get the "
                     "exact string back. No secret required.",
        },
        "rules": {
            "clock_skew": "+/-%ds. Outside: 401 clock_skew, with the "
                          "server's time in the body."
                          % CLOCK_SKEW_SECONDS,
            "replay": "A nonce is single-use per peer for %ds. Reused: "
                      "409 replay." % NONCE_TTL_SECONDS,
            "idempotency": "Same idempotency_key and same payload returns "
                           "the original receipt verbatim with "
                           "replayed=true; nothing is sealed twice. Same "
                           "key with a different payload: 409 "
                           "idempotency_conflict.",
            "retry": "Retry the identical envelope. With an "
                     "idempotency_key that is a safe no-op. Without one, "
                     "a retry inside the nonce window returns 409 replay "
                     "-- so send an idempotency_key if you intend to "
                     "retry at all.",
            "suspension": "403 peer_suspended. Nothing is deleted and the "
                          "peer's sealed history stands.",
            "rotation": "A new secret is issued and the previous one stays "
                        "valid for %ds. Submissions accepted on the old "
                        "secret come back with signed_with=previous and a "
                        "warning naming the cutoff. The operator performs "
                        "the rotation, because the operator holds the "
                        "secret."
                        % ROTATION_OVERLAP_SECONDS,
        },
        "on_acceptance":
            "The payload is sealed into the audit chain and you get "
            "audit_hash, block_index and receipt_seq. Verify "
            "independently: inclusion at /x/complete/prove, ancestry at "
            "/x/consistency/ancestor, append-only at "
            "/x/consistency/proof. Both offline verifiers "
            "(aileash_verify.py, verify_authority.py) are stdlib only and "
            "touch no network.",
        "routes": {
            "GET spec": "public. this document.",
            "POST canonical": "public. the exact string to sign.",
            "GET peers": "public. peer ids and status. never secrets.",
            "POST submit": "signature authenticated. no API key.",
            "POST register": "keyed. operator issues a credential.",
            "POST rotate": "keyed. new secret, old one overlaps.",
            "POST suspend / POST resume": "keyed.",
            "GET history": "keyed. submissions, optionally by peer.",
        },
        "what_this_does_not_do": [
            "It does not exclude the operator of this deployment. A shared "
            "secret is held by both parties, so a valid signature means a "
            "holder of the secret submitted - which is you and also us. "
            "Use /x/signed/submit if that matters to you.",
            "It does not make a submitted root true. It proves who "
            "submitted it and when, and that it has not changed since.",
            "It does not replace /x/witness/observe. Peers who prefer the "
            "open path keep using it and lose nothing.",
            "A shared secret authenticates a channel, not a person. If "
            "the secret leaks, rotate it.",
        ],
        "worked_example": {
            "envelope_before_signing": {
                "peer_id": "example-001",
                "ts": 1755432000,
                "nonce": "0123456789abcdef",
                "payload": {"period": "2026-Q3", "root": "ab12...", "count": 4096},
            },
            "note": "POST exactly that to /x/peer/canonical and you will "
                    "get the string to sign, so you can confirm your "
                    "implementation before you hold a secret.",
        },
    }


# ---------------------------------------------------------------- router

def handle(method, action, data, api_key, ctx):
    data = data or {}

    if action == "spec":
        return _spec(), 200
    if action == "canonical":
        return _canonical_route(data)
    if action == "peers":
        return _peers(ctx)
    if action == "submit":
        return _submit(ctx, data)

    if not api_key:
        return {"ok": False, "error": "api_key_required"}, 401

    if action == "register":
        return _register(ctx, data)
    if action == "rotate":
        return _rotate(ctx, data)
    if action == "suspend":
        return _set_status(ctx, data, "suspended")
    if action == "resume":
        return _set_status(ctx, data, "active")
    if action == "history":
        return _history(ctx, data)

    return {"ok": False, "error": "unknown_action", "action": action}, 404

```


## `modules/peerconsole.py`

376 lines, 15478 bytes

```python
"""
modules/peerconsole.py  v1.0  -  the peer credential page at /peers

Register a peer, rotate their secret, suspend them, see who is on.
Keyed POSTs a browser address bar cannot reach.

Own patch attribute so it composes with console.py and packconsole.py.
After a deploy, one /x/ request arms it: /x/peerconsole/status
"""

import sys
from urllib.parse import urlparse

VERSION = "1.0"
PUBLIC = {("GET", "status")}
PAGE_PATHS = ("/peers", "/peers.html", "/peer-console")

_patched = [False]

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Peers — AILeash</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#0a0f1e;--panel:#131b2e;--panel2:#1a2338;--edge:rgba(201,168,76,.22);
--gold:#c9a84c;--text:#f2efe6;--mute:rgba(242,239,230,.42);--ok:#7fe3b0;--err:#ff8a80;
--mono:'IBM Plex Mono',ui-monospace,monospace;--body:system-ui,-apple-system,sans-serif}
body{background:var(--ink);color:var(--text);font-family:var(--body);font-size:16px;
line-height:1.6;padding:0 0 60px}
.wrap{max-width:640px;margin:0 auto;padding:0 18px}
header{padding:30px 0 20px;border-bottom:1px solid var(--edge);margin-bottom:24px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.24em;
text-transform:uppercase;color:var(--gold);margin-bottom:8px}
h1{font-size:34px;line-height:1;font-weight:800;letter-spacing:-.02em}
h1 span{color:var(--gold)}
.sub{color:var(--mute);font-size:14px;margin-top:10px}
label{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.16em;
text-transform:uppercase;color:var(--mute);margin-bottom:6px}
input{width:100%;background:var(--panel);border:1px solid var(--edge);color:var(--text);
font-family:var(--mono);font-size:13px;padding:12px;border-radius:4px;outline:none}
input:focus{border-color:var(--gold)}
.keybar{background:var(--panel2);border:1px solid var(--edge);border-radius:6px;
padding:16px;margin-bottom:24px}
.keynote{font-size:12px;color:var(--mute);margin-top:8px}
.op{border:1px solid var(--edge);border-radius:6px;background:var(--panel);
margin-bottom:12px;overflow:hidden}
.op-head{display:flex;align-items:baseline;gap:10px;padding:15px 16px;cursor:pointer}
.op-head:hover{background:var(--panel2)}
.op-n{font-family:var(--mono);font-size:10px;color:var(--gold);opacity:.6}
.op-t{font-size:17px;font-weight:700}
.op-r{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--mute)}
.op-body{padding:0 16px 16px;display:none}
.op.open .op-body{display:block}
.op-why{font-size:13.5px;color:var(--mute);margin-bottom:14px}
.field{margin-bottom:12px}
button{width:100%;background:var(--gold);color:var(--ink);border:none;border-radius:4px;
padding:14px;font-weight:700;font-size:14.5px;cursor:pointer}
button:hover:not(:disabled){background:#dbbd63}
button.quiet{background:transparent;color:var(--mute);border:1px solid var(--edge)}
.two{display:flex;gap:10px}
.two button{flex:1}
#out{margin-top:24px}
pre{font-family:var(--mono);font-size:11.5px;line-height:1.6;background:#080c16;
color:var(--ok);padding:14px;border-radius:5px;overflow-x:auto;
border:1px solid var(--edge);max-height:320px}
.msg{font-family:var(--mono);font-size:12.5px;padding:13px 15px;border-radius:5px;
border:1px solid var(--edge);color:var(--mute);margin-bottom:12px}
.msg.bad{color:var(--err);border-color:rgba(200,54,43,.5);background:rgba(200,54,43,.08)}
.msg.good{color:var(--ok);border-color:rgba(127,227,176,.35);background:rgba(26,158,110,.08)}
.secret{background:#080c16;border:2px solid var(--gold);border-radius:6px;padding:18px;
margin-bottom:14px}
.secret .lbl{font-family:var(--mono);font-size:10px;letter-spacing:.16em;
text-transform:uppercase;color:var(--gold);margin-bottom:10px}
.secret .val{font-family:var(--mono);font-size:13px;color:var(--text);word-break:break-all;
line-height:1.7;background:var(--panel);padding:12px;border-radius:4px}
.secret .warn{color:var(--err);font-size:13px;margin-top:12px}
.peer{padding:12px 0;border-bottom:1px solid var(--edge)}
.peer:last-child{border-bottom:none}
.peer .id{font-family:var(--mono);font-size:13.5px;color:var(--gold)}
.peer .meta{font-size:12.5px;color:var(--mute);margin-top:3px}
.pill{display:inline-block;font-family:var(--mono);font-size:10px;padding:2px 7px;
border-radius:3px;letter-spacing:.1em;text-transform:uppercase}
.pill.active{background:rgba(26,158,110,.18);color:var(--ok)}
.pill.suspended{background:rgba(200,54,43,.15);color:var(--err)}
footer{margin-top:30px;padding-top:16px;border-top:1px solid var(--edge);
font-family:var(--mono);font-size:10.5px;color:var(--mute);line-height:1.8}
a{color:var(--gold)}
</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">AILeash · peer credentials</p>
  <h1>Signed <span>peers</span></h1>
  <p class="sub">The open endpoint stays open. This issues credentials to peers who need a guarantee that only they can submit as their chain.</p>
</header>

<div class="keybar">
  <label for="key">API key</label>
  <input id="key" type="password" placeholder="al_live_…" autocomplete="off" spellcheck="false">
  <p class="keynote">Held in this tab only. Close it and the key is gone.</p>
</div>

<div class="op open" id="op-reg">
  <div class="op-head" onclick="tog('op-reg')">
    <span class="op-n">01</span><span class="op-t">Register a peer</span>
    <span class="op-r">POST /x/peer/register</span>
  </div>
  <div class="op-body">
    <p class="op-why">Issues their secret. It is shown once here and never again — send it to them over a channel you trust, not the same email as everything else.</p>
    <div class="field">
      <label for="r-id">Peer id (lowercase, no spaces)</label>
      <input id="r-id" placeholder="praesidium" autocomplete="off">
    </div>
    <div class="field">
      <label for="r-name">Chain name</label>
      <input id="r-name" placeholder="PRAXIS" autocomplete="off">
    </div>
    <div class="field">
      <label for="r-url">Their public tip URL</label>
      <input id="r-url" placeholder="https://example.com/api/tip" autocomplete="off">
    </div>
    <button onclick="run('register')">Issue the credential</button>
  </div>
</div>

<div class="op" id="op-rot">
  <div class="op-head" onclick="tog('op-rot')">
    <span class="op-n">02</span><span class="op-t">Rotate a secret</span>
    <span class="op-r">POST /x/peer/rotate</span>
  </div>
  <div class="op-body">
    <p class="op-why">New secret now, old one keeps working for 24 hours so they can roll over without downtime.</p>
    <div class="field">
      <label for="o-id">Peer id</label>
      <input id="o-id" placeholder="praesidium" autocomplete="off">
    </div>
    <button onclick="run('rotate')">Rotate</button>
  </div>
</div>

<div class="op" id="op-sus">
  <div class="op-head" onclick="tog('op-sus')">
    <span class="op-n">03</span><span class="op-t">Suspend or resume</span>
    <span class="op-r">POST /x/peer/suspend</span>
  </div>
  <div class="op-body">
    <p class="op-why">Suspending refuses new submissions. Nothing is deleted and their sealed history stands.</p>
    <div class="field">
      <label for="s-id">Peer id</label>
      <input id="s-id" placeholder="praesidium" autocomplete="off">
    </div>
    <div class="two">
      <button onclick="run('suspend')">Suspend</button>
      <button class="quiet" onclick="run('resume')">Resume</button>
    </div>
  </div>
</div>

<div class="op" id="op-list">
  <div class="op-head" onclick="tog('op-list')">
    <span class="op-n">04</span><span class="op-t">Who is registered</span>
    <span class="op-r">GET /x/peer/peers</span>
  </div>
  <div class="op-body">
    <p class="op-why">Public route. Secrets are never returned by anything.</p>
    <button class="quiet" onclick="run('peers')">List them</button>
  </div>
</div>

<div class="op" id="op-hist">
  <div class="op-head" onclick="tog('op-hist')">
    <span class="op-n">05</span><span class="op-t">Submissions</span>
    <span class="op-r">GET /x/peer/history</span>
  </div>
  <div class="op-body">
    <p class="op-why">What has come in, with the receipt for each. Leave the id blank for everything.</p>
    <div class="field">
      <label for="h-id">Peer id (optional)</label>
      <input id="h-id" placeholder="leave blank for all" autocomplete="off">
    </div>
    <button class="quiet" onclick="run('history')">Show them</button>
  </div>
</div>

<div id="out"></div>

<footer>
  Spec for peers to implement: <a href="/x/peer/spec">/x/peer/spec</a><br>
  Open endpoint, unchanged: <a href="/x/witness/peers">/x/witness/peers</a><br>
  Other consoles: <a href="/console">/console</a> · <a href="/pack">/pack</a>
</footer>

</div>

<script>
(function(){
  var out=document.getElementById('out'), busy=false;
  window.tog=function(id){document.getElementById(id).classList.toggle('open');};
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function msg(t,k){out.innerHTML='<div class="msg '+(k||'')+'">'+esc(t)+'</div>';}
  function raw(o){return '<pre>'+esc(JSON.stringify(o,null,2))+'</pre>';}
  function val(id){return document.getElementById(id).value.trim();}
  function key(){var k=val('key');if(!k){msg('Paste your API key at the top first.','bad');return null;}return k;}

  async function call(path,method,body){
    var k=key(); if(!k) return null;
    var o={method:method,headers:{'Authorization':'Bearer '+k}};
    if(body){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body);}
    var r=await fetch(path,o); var d;
    try{d=await r.json();}catch(e){d={error:'unreadable_response'};}
    return {status:r.status,data:d};
  }

  function showSecret(d,title,extra){
    return '<div class="secret"><div class="lbl">'+esc(title)+' — '+esc(d.peer_id)+'</div>'
      +'<div class="val">'+esc(d.secret)+'</div>'
      +'<div class="warn">Shown once. Not recoverable. Copy it now and send it to them '
      +'separately from anything else.</div>'
      +(extra?'<div class="warn" style="color:var(--mute)">'+esc(extra)+'</div>':'')
      +'</div>';
  }

  function showPeers(d){
    if(!d.peers||!d.peers.length) return '<div class="msg">No peers registered yet.</div>';
    var h='<div class="msg good">'+d.count+' registered</div><div class="op open"><div class="op-body" style="padding:16px">';
    d.peers.forEach(function(p){
      h+='<div class="peer"><span class="id">'+esc(p.peer_id)+'</span> '
        +'<span class="pill '+esc(p.status)+'">'+esc(p.status)+'</span>'
        +'<div class="meta">'+esc(p.chain_name||'')
        +' · '+esc(p.submissions)+' submissions'
        +(p.last_seen?' · last '+esc(p.last_seen):' · never submitted')
        +(p.rotation_overlap_active?' · rotating':'')
        +'</div>'
        +(p.url?'<div class="meta">'+esc(p.url)+'</div>':'')
        +'</div>';
    });
    return h+'</div></div>';
  }

  window.run=async function(what){
    if(busy) return;
    var path,method='POST',body=null;

    if(what==='register'){
      var id=val('r-id');
      if(!id){msg('Give the peer an id.','bad');return;}
      path='/x/peer/register';
      body={peer_id:id.toLowerCase(),chain_name:val('r-name')||id,url:val('r-url')};
    }
    else if(what==='rotate'){
      var oid=val('o-id');
      if(!oid){msg('Which peer?','bad');return;}
      path='/x/peer/rotate'; body={peer_id:oid.toLowerCase()};
    }
    else if(what==='suspend'||what==='resume'){
      var sid=val('s-id');
      if(!sid){msg('Which peer?','bad');return;}
      path='/x/peer/'+what; body={peer_id:sid.toLowerCase()};
    }
    else if(what==='peers'){path='/x/peer/peers';method='GET';}
    else if(what==='history'){
      var hid=val('h-id');
      path='/x/peer/history'+(hid?'?peer_id='+encodeURIComponent(hid.toLowerCase()):'');
      method='GET';
    }
    else return;

    busy=true;
    out.innerHTML='<div class="msg">Working…</div>';
    try{
      var res=await call(path,method,body);
      if(!res){busy=false;return;}
      var d=res.data;
      if(res.status===401){msg('That key was refused.','bad');}
      else if(res.status===404&&d&&d.error==='unknown_module'){
        msg('modules/peer.py is not deployed yet.','bad');}
      else if(res.status>=400){
        out.innerHTML='<div class="msg bad">'+esc((d&&(d.detail||d.error))||('HTTP '+res.status))+'</div>'+raw(d);}
      else if(what==='register'&&d.secret){
        out.innerHTML=showSecret(d,'Peer secret')
          +'<div class="msg good">Registered. Send them /x/peer/spec so they can implement the signing.</div>'+raw(d);}
      else if(what==='rotate'&&d.secret){
        out.innerHTML=showSecret(d,'New secret','Previous secret valid until '+(d.previous_valid_until||''))+raw(d);}
      else if(what==='peers'){out.innerHTML=showPeers(d)+raw(d);}
      else{out.innerHTML='<div class="msg good">Done.</div>'+raw(d);}
    }catch(e){msg('Could not reach the server.','bad');}
    busy=false;
  };
})();
</script>
</body>
</html>
"""


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_peerconsole_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            body = PAGE.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Robots-Tag", "noindex, nofollow")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._peerconsole_patched = True
    _patched[0] = True
    print("PEERCONSOLE: /peers page installed at runtime", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("PEERCONSOLE: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    if method == "GET" and (action or "") in ("", "status"):
        return {
            "page": "/peers",
            "installed": bool(_patched[0]),
            "install_result": state,
            "version": VERSION,
            "paths": list(PAGE_PATHS),
            "note": "The page holds no credentials. Every route it calls "
                    "checks the key itself.",
        }, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```


## `modules/publish.py`

491 lines, 21976 bytes

```python
#!/usr/bin/env python3
"""
modules/publish.py  -  sealing what you published, at the moment you publish it
===============================================================================

THE PROBLEM THIS EXISTS TO NEVER HAVE AGAIN
-------------------------------------------
Somebody asks when a page was published. You answer from git history. They
point out - correctly - that git commit dates are fields in the commit
object which anyone can set to anything with an environment variable before
committing. Your strongest evidence turns out to be the weakest thing in
the room, and it drags the credible parts down with it.

The fix is not a better argument. It is sealing the page the moment it goes
live, so the question never depends on anybody's word again.

WHAT THIS DOES
--------------
    POST /x/publish/seal {"url": "https://example.com/spec"}

We fetch the URL ourselves, hash exactly what was served, and seal the hash,
the URL and the fetch time into the chain - where it is anchored externally
and handed to peer chains like every other block.

From then on:

  - "this exact content was served at this address no later than T" is
    arithmetic rather than a claim;
  - re-sealing the same URL later builds a permanent revision history that
    the publisher cannot edit, because each version is its own block;
  - and anyone can check it without an account.

Seal at publication and you never argue about a publication date again. That
is the entire point, and it takes one call.

WHAT IT HONESTLY CANNOT DO
--------------------------
It cannot reach backwards. A seal made today proves the content existed
today, not that it existed last week. Nothing can prove that - not this, not
Bitcoin, not a notary. Timestamps are one-directional by nature.

So for anything already published before it was sealed, the module records
EXTERNAL REFERENCES alongside: a GitHub push event, a Wayback Machine
snapshot, a DigiCert or OpenTimestamps proof. Those are stored and sealed as
supplied. We do not verify them and we do not present them as ours - they
are somebody else's record, named so a third party can check it at source.
That distinction is stated in every response rather than left to be
discovered.

Two references are worth knowing about, because they are the ones that
actually carry an earlier date:

  GitHub push events   api.github.com/repos/<owner>/<repo>/events
                       The push timestamp is recorded server-side by GitHub
                       and cannot be set by the pusher, unlike commit dates.
                       Retained roughly 90 days - so it must be captured
                       while it still exists.

  Wayback Machine      archive.org/wayback/available?url=...&timestamp=...
                       An independent party with no stake in the dispute.
                       If it caught the page, that settles it outright.

FETCHING SAFELY
---------------
This module makes the server fetch a URL. Done naively that is a hole worse
than the one it closes. So the fetcher speaks only http and https, only on
ports 80 and 443, resolves the hostname first and refuses any address that
is private, loopback, link-local, reserved or multicast, never follows a
redirect, times out fast, and stops reading after a cap. Sealing is keyed,
so this is not an anonymous capability either.

    POST /x/publish/seal      fetch, hash and seal a live URL     (keyed)
    GET  /x/publish/history   every version ever sealed of a URL  (public)
    GET  /x/publish/verify    was this exact content served, when (public)
    GET  /x/publish/list      everything sealed                   (public)
    GET  /x/publish/spec      how to check any of it              (public)
"""

import hashlib
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Reading is open. A publication record only settles an argument if the
# other side can check it without going through the publisher.
PUBLIC = {("GET", "history"), ("GET", "verify"), ("GET", "list"),
          ("GET", "spec")}

CONTENT_PREFIX = b"AILEASH-PUBLISH-v1:"

FETCH_TIMEOUT = 8
MAX_FETCH_BYTES = 2 * 1024 * 1024
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)
MAX_EXTERNAL = 8

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS publish_seal("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,url TEXT,"
                  "content_hash TEXT,byte_length INTEGER,http_status INTEGER,"
                  "content_type TEXT,note TEXT,external TEXT,"
                  "fetched REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pub_url ON publish_seal(url,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pub_hash ON publish_seal(content_hash)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ----------------------------------------------------------------------
# fetching - read the SSRF note above before touching any of this
# ----------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an instruction to fetch a second URL we never checked."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _address_allowed(host, port):
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "could not resolve host (%s)" % type(exc).__name__
    if not infos:
        return False, "host resolved to nothing"
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, "unreadable address"
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, "address is not publicly routable"
    return True, None


def _url_allowed(url):
    if not url or not isinstance(url, str) or len(url) > 500:
        return False, "no usable url"
    try:
        parts = urlparse(url.strip())
    except Exception:
        return False, "unparseable url"
    if parts.scheme not in ALLOWED_SCHEMES:
        return False, "scheme not allowed"
    if not parts.hostname:
        return False, "no host in url"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        return False, "port not allowed"
    return _address_allowed(parts.hostname, port)


def _fetch(url):
    """Returns (body_bytes, status, content_type, error)."""
    ok, why = _url_allowed(url)
    if not ok:
        return None, None, None, why
    request = urllib.request.Request(url, headers={
        "Accept": "*/*",
        "User-Agent": "aileash-publish/%s" % VERSION,
    })
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            status = response.getcode()
            content_type = response.headers.get("Content-Type", "")
            body = response.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return None, exc.code, None, "url answered %s" % exc.code
    except Exception as exc:
        return None, None, None, "could not reach url (%s)" % type(exc).__name__
    if len(body) > MAX_FETCH_BYTES:
        return None, status, content_type, "response larger than the %d byte cap" % MAX_FETCH_BYTES
    return body, status, content_type, None


def _content_hash(body):
    """Hash exactly the bytes served. No normalisation, no cleverness -
    a whitespace-tolerant hash would be a hash of our opinion of the page
    rather than of the page."""
    return hashlib.sha256(CONTENT_PREFIX + body).hexdigest()


# ----------------------------------------------------------------------
# seal
# ----------------------------------------------------------------------

def _clean_external(value):
    """External references are recorded verbatim and never verified."""
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:MAX_EXTERNAL]:
        if isinstance(item, dict):
            source = str(item.get("source", "")).strip()[:60]
            reference = str(item.get("reference", item.get("url", ""))).strip()[:400]
            claimed = str(item.get("claimed_time", "")).strip()[:60]
            if source and reference:
                out.append({"source": source, "reference": reference,
                            "claimed_time": claimed or None})
        elif isinstance(item, str) and item.strip():
            out.append({"source": "unnamed", "reference": item.strip()[:400],
                        "claimed_time": None})
    return out


def _seal(ctx, api_key, data):
    url = str(data.get("url", "")).strip()
    if not url:
        return {"error": "url_required",
                "message": "The address of the page you have just published."}, 400

    note = str(data.get("note", "") or "").strip()[:300]
    external = _clean_external(data.get("external"))

    body, status, content_type, why = _fetch(url)
    if why:
        return {"error": "fetch_failed", "url": url, "message": why,
                "note": "Nothing was sealed. A record of a page we could not read would be "
                        "worse than no record."}, 502

    digest = _content_hash(body)
    now = time.time()

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT content_hash,fetched,audit_hash FROM publish_seal "
            "WHERE url=? ORDER BY id ASC", (url,)).fetchall()

    unchanged = bool(prior) and prior[-1][0] == digest
    first_of_this_version = None
    for row in prior:
        if row[0] == digest:
            first_of_this_version = row[1]
            break

    external_summary = ";".join("%s=%s" % (e["source"], e["reference"][:60]) for e in external)
    ev = {"user_id": "pub:" + digest[:16], "action": "publication_sealed", "amount": 0,
          "country": "UK", "device_id": "publish", "anomaly": 0, "device_risk": 0}
    res = {"decision": "PUBLICATION_SEALED", "score": 0, "publish_version": VERSION,
           "url": url, "content_hash": digest, "bytes": len(body),
           "http_status": status,
           "detail": "url=%s;sha256=%s;bytes=%d%s"
                     % (url, digest, len(body),
                        ";external=" + external_summary if external_summary else "")}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO publish_seal(api_key,url,content_hash,byte_length,http_status,"
            "content_type,note,external,fetched,audit_hash,block_index) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (api_key, url, digest, len(body), status, content_type or None,
             note or None,
             "|".join("%s %s %s" % (e["source"], e["reference"], e["claimed_time"] or "")
                      for e in external) or None,
             now, audit_hash, block_index))
        ctx["conn"].commit()

    out = {
        "url": url, "content_hash": digest, "bytes": len(body),
        "http_status": status, "content_type": content_type,
        "sealed_at": _iso(now),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "version_number": len(prior) + 1,
        "publish_version": VERSION,
        "what_this_proves": "This exact content was served at this address when we fetched it, "
                            "and the record of that cannot be altered afterwards.",
        "what_it_does_not": "It does not prove the page existed earlier than this moment. "
                            "Nothing can prove that after the fact - timestamps only run "
                            "forwards. Seal at publication and the question never arises.",
        "history": "/x/publish/history?url=" + url,
        "verify_this_block": "/x/consistency/ancestor?tip=" + audit_hash,
    }

    if unchanged:
        out["unchanged"] = True
        out["first_sealed_in_this_form"] = _iso(first_of_this_version)
        out["message"] = ("Identical to the last sealed version. The page has not changed since "
                          "%s and now has an additional dated witness." % _iso(first_of_this_version))
    elif prior:
        out["changed"] = True
        out["previous_hash"] = prior[-1][0]
        out["previous_sealed_at"] = _iso(prior[-1][1])
        out["message"] = ("The content has changed since the last seal. Both versions remain in "
                          "the chain - a revision history the publisher cannot edit.")
    else:
        out["message"] = ("First seal for this address. Every later seal builds a permanent, "
                          "dated revision history from here.")

    if external:
        out["external_references"] = external
        out["external_caveat"] = ("Recorded exactly as supplied and sealed with the block. We do "
                                  "not verify them and they are not our evidence - they are "
                                  "somebody else's record, named so you can check them at "
                                  "source.")
    else:
        out["advice"] = ("If this page was published before today, add external references - a "
                         "GitHub push event, a Wayback snapshot - and they will be sealed "
                         "alongside. Those carry an earlier date; a seal made now cannot.")
    return out, 200


# ----------------------------------------------------------------------
# reading
# ----------------------------------------------------------------------

def _parse_external(blob):
    if not blob:
        return []
    out = []
    for line in blob.split("|"):
        parts = line.strip().split(" ", 2)
        if len(parts) >= 2:
            out.append({"source": parts[0], "reference": parts[1],
                        "claimed_time": parts[2] if len(parts) > 2 and parts[2] else None})
    return out


def _history(ctx, data):
    url = str(data.get("url", "")).strip()
    if not url:
        return {"error": "url_required"}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT content_hash,byte_length,fetched,audit_hash,block_index,note,external "
            "FROM publish_seal WHERE url=? ORDER BY id ASC LIMIT 500", (url,)).fetchall()
    if not rows:
        return {"error": "never_sealed", "url": url,
                "message": "No seal recorded for that address."}, 404

    versions, last_hash = [], None
    for content_hash, length, fetched, audit_hash, block_index, note, external in rows:
        versions.append({
            "content_hash": content_hash, "bytes": length,
            "sealed_at": _iso(fetched), "sealed_in_chain": audit_hash,
            "block_index": block_index, "note": note,
            "changed_from_previous": last_hash is not None and content_hash != last_hash,
            "external_references": _parse_external(external),
        })
        last_hash = content_hash

    distinct = len({v["content_hash"] for v in versions})
    return {"url": url, "seals": len(versions), "distinct_versions": distinct,
            "first_sealed": versions[0]["sealed_at"], "latest_sealed": versions[-1]["sealed_at"],
            "current_hash": versions[-1]["content_hash"],
            "versions": versions,
            "publish_version": VERSION,
            "what_this_is": "A dated revision history the publisher cannot edit. Each version is "
                            "its own block; altering or removing one breaks every block after it.",
            "limit": "The first seal fixes an upper bound, not a lower one. Anything published "
                     "before its first seal rests on external evidence, which is recorded here "
                     "but not verified by us."}, 200


def _verify(ctx, data):
    url = str(data.get("url", "")).strip()
    digest = str(data.get("hash", data.get("content_hash", ""))).strip().lower()
    if not digest or not HEX64.match(digest):
        return {"error": "hash_required",
                "message": "sha256 of AILEASH-PUBLISH-v1: followed by the exact bytes served"}, 400

    with ctx["lock"]:
        if url:
            rows = ctx["conn"].execute(
                "SELECT url,fetched,audit_hash,block_index FROM publish_seal "
                "WHERE url=? AND content_hash=? ORDER BY id ASC", (url, digest)).fetchall()
        else:
            rows = ctx["conn"].execute(
                "SELECT url,fetched,audit_hash,block_index FROM publish_seal "
                "WHERE content_hash=? ORDER BY id ASC", (digest,)).fetchall()

    if not rows:
        return {"sealed": False, "content_hash": digest, "url": url or None,
                "message": "We hold no seal for that exact content. Either it was never sealed, "
                           "or the content differs from what was - a single byte is enough."}, 404

    return {"sealed": True, "content_hash": digest,
            "url": rows[0][0], "times_sealed": len(rows),
            "first_sealed": _iso(rows[0][1]),
            "latest_sealed": _iso(rows[-1][1]),
            "sealed_in_chain": rows[0][2], "block_index": rows[0][3],
            "publish_version": VERSION,
            "what_this_proves": "Content with exactly this fingerprint was served at that "
                                "address no later than the first sealing time, and the record "
                                "of it has not been altered since.",
            "verify_the_block": "/x/consistency/ancestor?tip=" + rows[0][2]}, 200


def _list(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT url,COUNT(*),MIN(fetched),MAX(fetched),COUNT(DISTINCT content_hash) "
            "FROM publish_seal GROUP BY url ORDER BY MAX(fetched) DESC LIMIT 500").fetchall()
    return {"count": len(rows),
            "pages": [{"url": r[0], "seals": r[1], "first_sealed": _iso(r[2]),
                       "latest_sealed": _iso(r[3]), "distinct_versions": r[4],
                       "history": "/x/publish/history?url=" + r[0]} for r in rows],
            "publish_version": VERSION,
            "note": "Everything this platform has sealed about its own published pages. Ours is "
                    "in here too - a publisher who seals everyone's pages but not their own is "
                    "telling you something."}, 200


def _spec():
    return {
        "publish_version": VERSION,
        "content_hash": "sha256('AILEASH-PUBLISH-v1:' || exact_bytes_served) as lowercase hex",
        "no_normalisation": "The bytes are hashed exactly as served. Nothing is trimmed, "
                            "reordered or cleaned up first - a whitespace-tolerant hash would "
                            "be a hash of our opinion of the page rather than of the page.",
        "reproduce_it": "curl the URL, pipe the raw bytes through sha256 with that prefix, and "
                        "compare with what we sealed. If your bytes differ, the page changed.",
        "what_a_seal_proves": "That content with this exact fingerprint was served at this "
                              "address no later than the sealing time, and that the record has "
                              "not been altered since - it is a chain block like any other, "
                              "anchored externally and witnessed by peers.",
        "what_it_cannot_prove": "That the page existed before the seal. Timestamps run forwards "
                                "only. Any product implying otherwise is misdescribing what a "
                                "timestamp is.",
        "for_earlier_dates": {
            "github_push": "api.github.com/repos/<owner>/<repo>/events - the push timestamp is "
                           "recorded by GitHub, not the pusher, unlike commit author and "
                           "committer dates which are settable fields. Retained around 90 days, "
                           "so capture it while it exists.",
            "wayback": "archive.org/wayback/available - an independent party with no stake in "
                       "the dispute.",
            "status": "Both are recorded and sealed as supplied, and neither is verified by us. "
                      "They are somebody else's evidence, named so you can check them at source.",
        },
        "the_discipline": "Seal at publication. One call at the moment a page goes live means "
                          "the publication date never rests on anyone's word, anyone's git "
                          "history, or anyone's memory again.",
    }, 200


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec()
        if action == "history":
            return _history(ctx, data)
        if action == "verify":
            return _verify(ctx, data)
        if action == "list":
            return _list(ctx)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "seal":
            return _seal(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "verify", "list"],
            "POST": ["seal (keyed)"]}, 404

```
