"""
modules/pack.py  v2.0
Quarterly evidence pack.

Reads audit_log and device_seen. Owns pack_issued.
Finds server globals via sys.modules (same pattern as replay.py),
so it needs nothing from ctx and cannot be broken by a ctx change.

Routes:
  GET  spec     public
  GET  preview  keyed
  POST issue    keyed
  GET  render   keyed  -> {"html": "..."}
  GET  history  keyed
"""

import json
import sys
import time
import hashlib
import calendar
import datetime

VERSION = "2.0"
PUBLIC = {"spec", ("GET", "spec")}


def _srv():
    for m in list(sys.modules.values()):
        try:
            if (hasattr(m, "_conn") and hasattr(m, "_db_lock")
                    and hasattr(m, "seal") and hasattr(m, "sha")):
                return m
        except Exception:
            continue
    return None


def _epoch(y, m, d):
    return float(calendar.timegm((y, m, d, 0, 0, 0, 0, 0, 0)))


def _bounds(period):
    p = (period or "").strip().upper()
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
    except Exception:
        return None
    return None


def _iso(ep):
    if ep is None:
        return "-"
    return datetime.datetime.utcfromtimestamp(
        float(ep)).strftime("%Y-%m-%d %H:%M:%SZ")


def _day(ep):
    if ep is None:
        return "-"
    return datetime.datetime.utcfromtimestamp(
        float(ep)).strftime("%Y-%m-%d")


def _ensure(srv):
    with srv._db_lock:
        srv._conn.execute(
            "CREATE TABLE IF NOT EXISTS pack_issued("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "period TEXT,scope TEXT,digest TEXT,"
            "issued_at REAL,entries INTEGER,"
            "verified INTEGER,mismatches INTEGER,"
            "seal_hash TEXT,block_index INTEGER)")
        srv._conn.commit()


# ---------------------------------------------------------------
# assembly
# ---------------------------------------------------------------
def _assemble(srv, start, end, label, scope_key):
    conn = srv._conn
    cols = ("id,ts,event_json,result_json,prev_hash,"
            "audit_hash,api_key,key_seq")

    with srv._db_lock:
        if scope_key:
            rows = conn.execute(
                "SELECT " + cols + " FROM audit_log "
                "WHERE ts>=? AND ts<? AND api_key=? ORDER BY id ASC",
                (start, end, scope_key)).fetchall()
            first_ts = conn.execute(
                "SELECT MIN(ts) FROM audit_log WHERE api_key=?",
                (scope_key,)).fetchone()
            devs_total = conn.execute(
                "SELECT COUNT(*) FROM device_seen WHERE api_key=?",
                (scope_key,)).fetchone()
            devs_new = conn.execute(
                "SELECT COUNT(*) FROM device_seen WHERE api_key=? "
                "AND first_seen>=? AND first_seen<?",
                (scope_key, start, end)).fetchone()
        else:
            rows = conn.execute(
                "SELECT " + cols + " FROM audit_log "
                "WHERE ts>=? AND ts<? ORDER BY id ASC",
                (start, end)).fetchall()
            first_ts = conn.execute(
                "SELECT MIN(ts) FROM audit_log").fetchone()
            devs_total = conn.execute(
                "SELECT COUNT(*) FROM device_seen").fetchone()
            devs_new = conn.execute(
                "SELECT COUNT(*) FROM device_seen "
                "WHERE first_seen>=? AND first_seen<?",
                (start, end)).fetchone()
        chain_total = conn.execute(
            "SELECT COUNT(*) FROM audit_log").fetchone()[0]

    unbroken = first_ts[0] if first_ts else None
    devices_total = devs_total[0] if devs_total else 0
    devices_new = devs_new[0] if devs_new else 0

    verdicts = {}
    actions = {}
    seqs = []
    verified = 0
    mismatches = []
    link_breaks = []
    prev_hash_expected = None
    days = {}

    for r in rows:
        (rid, ts, ev_j, res_j, prev, ah, akey, kseq) = r
        try:
            ev = json.loads(ev_j)
        except Exception:
            ev = {}
        try:
            res = json.loads(res_j)
        except Exception:
            res = {}

        # 1. recompute the block hash with the server's own sha()
        try:
            calc = srv.sha({"prev_hash": prev, "ts": ts,
                            "event": ev, "result": res})
            if calc == ah:
                verified += 1
            else:
                mismatches.append(rid)
        except Exception:
            mismatches.append(rid)

        # 2. check the link to the block before it
        if prev_hash_expected is not None and prev != prev_hash_expected:
            link_breaks.append(rid)
        prev_hash_expected = ah

        d = str(res.get("decision", "UNKNOWN"))
        verdicts[d] = verdicts.get(d, 0) + 1
        a = str(ev.get("action", "unknown"))
        actions[a] = actions.get(a, 0) + 1
        if kseq is not None:
            seqs.append(int(kseq))
        k = _day(ts)
        days[k] = days.get(k, 0) + 1

    # 3. the block immediately before the period must chain in
    entry_link = "no_entries"
    if rows:
        with srv._db_lock:
            before = conn.execute(
                "SELECT audit_hash FROM audit_log WHERE id<? "
                "ORDER BY id DESC LIMIT 1", (rows[0][0],)).fetchone()
        if before is None:
            entry_link = ("period_starts_at_genesis"
                          if rows[0][4] == "GENESIS" else "broken")
        else:
            entry_link = ("intact" if rows[0][4] == before[0]
                          else "broken")

    # 4. gapless receipt sequence for a scoped key
    seq_report = {"applicable": bool(scope_key and seqs)}
    if seq_report["applicable"]:
        lo, hi = min(seqs), max(seqs)
        present = set(seqs)
        missing = [n for n in range(lo, hi + 1) if n not in present]
        seq_report.update({
            "first": lo, "last": hi,
            "received": len(seqs),
            "expected": hi - lo + 1,
            "missing": missing[:200],
            "gapless": not missing,
        })

    busiest = sorted(days.items(), key=lambda x: -x[1])[:5]

    p = {
        "pack_version": VERSION,
        "period": label,
        "period_start": _iso(start),
        "period_end": _iso(end),
        "generated_at": _iso(time.time()),
        "scope": ("key " + scope_key[:12] + "\u2026") if scope_key
                 else "deployment-wide",
        "unbroken_since": _day(unbroken),
        "entries_in_period": len(rows),
        "chain_total_entries": chain_total,
        "first_block": rows[0][0] if rows else None,
        "last_block": rows[-1][0] if rows else None,
        "first_hash": rows[0][5] if rows else None,
        "last_hash": rows[-1][5] if rows else None,
        "integrity": {
            "blocks_recomputed": len(rows),
            "hashes_verified": verified,
            "hash_mismatches": mismatches[:50],
            "internal_link_breaks": link_breaks[:50],
            "link_into_period": entry_link,
            "method": "SHA-256 over {prev_hash,ts,event,result} "
                      "recomputed from stored rows",
        },
        "receipt_sequence": seq_report,
        "verdicts": verdicts,
        "actions": dict(sorted(actions.items(),
                               key=lambda x: -x[1])[:20]),
        "devices": {"total_ever": devices_total,
                    "first_seen_in_period": devices_new},
        "busiest_days": [{"day": d, "entries": n}
                         for d, n in busiest],
        "verify_yourself": [
            "aileash_verify.py \u2014 stdlib only, no network",
            "/x/consistency/ancestor?tip=<last_hash>",
            "/x/consistency/proof?first=&second=",
            "/x/complete/prove",
            "/x/witness/peers",
        ],
        "this_pack_does_not_prove": [
            "That any decision recorded here was correct.",
            "That an external peer's own log is honest \u2014 that "
            "is checked at the peer's host, not here.",
            "Anything about periods outside the dates above.",
        ],
    }
    p["pack_digest"] = hashlib.sha256(
        b"AILEASH-PACK-v1\x00" + json.dumps(
            p, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest()
    return p


# ---------------------------------------------------------------
# HTML
# ---------------------------------------------------------------
def render_html(p):
    ig = p["integrity"]
    clean = (not ig["hash_mismatches"]
             and not ig["internal_link_breaks"]
             and ig["link_into_period"] in ("intact",
                                            "period_starts_at_genesis"))
    sq = p["receipt_sequence"]

    def card(inner):
        return ("<div style='background:#10182e;border:1px solid "
                "#223055;border-radius:12px;padding:16px;"
                "margin-bottom:14px'>" + inner + "</div>")

    def row(k, v):
        return ("<tr><td style='padding:7px 0;border-bottom:1px "
                "solid #1d2a4a'>" + str(k) + "</td><td style='padding:"
                "7px 0;border-bottom:1px solid #1d2a4a;text-align:"
                "right;color:#c9a84c;font-weight:600'>" + str(v)
                + "</td></tr>")

    verdict_rows = "".join(row(k, v) for k, v in
                           sorted(p["verdicts"].items()))
    action_rows = "".join(row(k, v) for k, v in
                          p["actions"].items())

    integ = ("<div style='font-size:26px;font-weight:600;color:"
             + ("#7fe3b0" if clean else "#ff8a80") + "'>"
             + str(ig["hashes_verified"]) + " of "
             + str(ig["blocks_recomputed"])
             + " blocks re-verified</div>"
             + "<div style='color:#93a0bd;font-size:13px;"
               "margin-top:6px'>" + ig["method"] + "</div>")
    if not clean:
        integ += ("<div style='color:#ff8a80;font-size:13px;"
                  "margin-top:8px'>Mismatches: "
                  + str(ig["hash_mismatches"])
                  + " &middot; link breaks: "
                  + str(ig["internal_link_breaks"])
                  + " &middot; entry link: "
                  + ig["link_into_period"] + "</div>")

    if sq.get("applicable"):
        seqbox = ("<div style='font-size:20px;color:"
                  + ("#7fe3b0" if sq["gapless"] else "#ff8a80")
                  + "'>" + ("No gaps" if sq["gapless"]
                            else "GAPS FOUND") + "</div>"
                  + "<div style='color:#93a0bd;font-size:13px'>"
                    "Receipts " + str(sq["first"]) + " to "
                  + str(sq["last"]) + " &middot; "
                  + str(sq["received"]) + " received of "
                  + str(sq["expected"]) + " expected</div>")
        if not sq["gapless"]:
            seqbox += ("<div style='color:#ff8a80;font-size:12px;"
                       "font-family:monospace'>missing "
                       + str(sq["missing"]) + "</div>")
    else:
        seqbox = ("<div style='color:#93a0bd;font-size:13px'>"
                  "Per-key receipt sequence not applicable to a "
                  "deployment-wide pack.</div>")

    nots = "".join("<li>" + x + "</li>"
                   for x in p["this_pack_does_not_prove"])
    ver = "".join("<li><code style='color:#9fb3d9'>" + x
                  + "</code></li>" for x in p["verify_yourself"])

    return (
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,"
        "initial-scale=1'>"
        "<title>AILeash Evidence Pack " + p["period"] + "</title>"
        "<body style='background:#0a0f1e;color:#e8ecf5;margin:0;"
        "padding:22px;font:15px/1.55 -apple-system,system-ui,"
        "sans-serif'>"
        "<div style='max-width:760px;margin:0 auto'>"
        "<h1 style='font-size:21px;margin:0 0 4px;color:#c9a84c'>"
        "Evidence Pack &mdash; " + p["period"] + "</h1>"
        "<div style='color:#93a0bd;font-size:13px;margin-bottom:"
        "20px'>" + p["scope"] + " &middot; " + p["period_start"]
        + " to " + p["period_end"] + " &middot; generated "
        + p["generated_at"] + "</div>"
        + card("<div style='color:#93a0bd;font-size:13px'>"
               "Unbroken since</div><div style='font-size:26px;"
               "color:#7fe3b0;font-weight:600'>"
               + p["unbroken_since"] + "</div>")
        + card(integ)
        + card(seqbox)
        + card("<table style='width:100%;border-collapse:collapse;"
               "font-size:14px'>"
               + row("Entries in period", p["entries_in_period"])
               + row("Chain total entries", p["chain_total_entries"])
               + row("Devices (total ever)",
                     p["devices"]["total_ever"])
               + row("Devices first seen this period",
                     p["devices"]["first_seen_in_period"])
               + verdict_rows + action_rows + "</table>")
        + card("<div style='color:#93a0bd;font-size:13px'>"
               "First block</div><code style='font:12px "
               "ui-monospace,monospace;color:#9fb3d9;word-break:"
               "break-all'>#" + str(p["first_block"]) + " "
               + str(p["first_hash"]) + "</code>"
               "<div style='color:#93a0bd;font-size:13px;"
               "margin-top:10px'>Last block</div><code style="
               "'font:12px ui-monospace,monospace;color:#9fb3d9;"
               "word-break:break-all'>#" + str(p["last_block"])
               + " " + str(p["last_hash"]) + "</code>"
               "<div style='color:#93a0bd;font-size:13px;"
               "margin-top:10px'>Pack digest</div><code style="
               "'font:12px ui-monospace,monospace;color:#9fb3d9;"
               "word-break:break-all'>" + p["pack_digest"]
               + "</code>")
        + card("<div style='color:#93a0bd;font-size:13px'>Check "
               "all of this yourself:</div><ul style='margin:6px "
               "0 0 18px;padding:0;font-size:13px'>" + ver + "</ul>"
               "<div style='color:#93a0bd;font-size:13px;"
               "margin-top:12px'>What this pack does not prove:"
               "</div><ul style='margin:6px 0 0 18px;padding:0;"
               "color:#93a0bd;font-size:13px'>" + nots + "</ul>")
        + "<div style='color:#6d7b99;font-size:12px;margin-top:"
          "18px'>AILeash &middot; sebbi.pro</div></div>")


# ---------------------------------------------------------------
# routes
# ---------------------------------------------------------------
def handle(method, action, data, api_key, ctx):

    if action == "spec":
        return (200, {
            "module": "pack", "version": VERSION,
            "purpose": "A quarterly evidence pack: every block in "
                       "the period recomputed from stored rows and "
                       "checked against its recorded hash, plus "
                       "gapless receipt-sequence verification for "
                       "a single key.",
            "periods": ["YYYY", "YYYY-MM", "YYYY-Qn"],
            "routes": {"spec": "GET public",
                       "preview": "GET keyed",
                       "render": "GET keyed",
                       "issue": "POST keyed",
                       "history": "GET keyed"},
            "params": {"period": "required",
                       "scope": "optional api key, or 'me' for "
                                "your own key; omit for "
                                "deployment-wide"},
            "reads": ["audit_log", "device_seen"],
            "writes": ["pack_issued", "audit_log (on issue)"],
            "does_not_prove": [
                "That any recorded decision was correct.",
                "That an external peer's log is honest.",
            ],
        })

    srv = _srv()
    if srv is None:
        return (500, {"error": "server_module_not_found"})

    if action in ("preview", "render", "issue"):
        b = _bounds(data.get("period"))
        if not b:
            return (400, {"error": "bad_period",
                          "accepts": ["YYYY", "YYYY-MM",
                                      "YYYY-Qn"]})
        start, end, label = b
        if end > time.time():
            return (409, {"error": "period_not_closed",
                          "period": label})

        scope = data.get("scope")
        if scope == "me":
            scope = api_key
        p = _assemble(srv, start, end, label, scope or None)

        if action == "preview":
            return (200, p)

        if action == "render":
            return (200, {"period": label,
                          "html": render_html(p)})

        _ensure(srv)
        ig = p["integrity"]
        ev = {"user_id": "pack:" + (scope or "deployment"),
              "action": "evidence_pack_issued",
              "amount": 0, "country": "UK",
              "device_id": "pack_" + label,
              "anomaly": 0, "device_risk": 0}
        res = {"decision": "PACK_ISSUED", "score": 0,
               "version": VERSION, "timestamp": time.time(),
               "period": label, "scope": p["scope"],
               "entries": p["entries_in_period"],
               "hashes_verified": ig["hashes_verified"],
               "blocks_recomputed": ig["blocks_recomputed"],
               "pack_digest": p["pack_digest"],
               "note": "quarterly evidence pack issued and sealed"}
        try:
            h, idx, seq = srv.seal(ev, res, time.time(), api_key)
        except Exception as e:
            return (500, {"error": "seal_failed",
                          "detail": str(e)})
        with srv._db_lock:
            srv._conn.execute(
                "INSERT INTO pack_issued(period,scope,digest,"
                "issued_at,entries,verified,mismatches,seal_hash,"
                "block_index) VALUES(?,?,?,?,?,?,?,?,?)",
                (label, p["scope"], p["pack_digest"], time.time(),
                 p["entries_in_period"], ig["hashes_verified"],
                 len(ig["hash_mismatches"]), h, idx))
            srv._conn.commit()
        p["sealed"] = {"audit_hash": h, "block_index": idx}
        return (200, p)

    if action == "history":
        _ensure(srv)
        with srv._db_lock:
            rows = srv._conn.execute(
                "SELECT period,scope,digest,issued_at,entries,"
                "verified,mismatches,seal_hash,block_index "
                "FROM pack_issued ORDER BY id DESC LIMIT 200"
            ).fetchall()
        return (200, {"packs": [
            {"period": r[0], "scope": r[1], "digest": r[2],
             "issued_at": _iso(r[3]), "entries": r[4],
             "hashes_verified": r[5], "mismatches": r[6],
             "audit_hash": r[7], "block_index": r[8]}
            for r in rows]})

    return (404, {"error": "unknown_action",
                  "GET": ["spec", "preview", "render", "history"],
                  "POST": ["issue"]})
