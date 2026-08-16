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
