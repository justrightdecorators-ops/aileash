"""
modules/snapshot.py  v1.0  -  the public chain, copied daily to an independent archive

THE GAP THIS CLOSES
Every block sebbi.pro seals is public at /x/walk, but only sebbi.pro serves
it. Witnesses hold the chain's fingerprints, which stops history being
rewritten - but a fingerprint with no record to match it against proves
nothing. If this server disappeared, the record would go with it.

WHAT THIS DOES
Once a day it asks the Internet Archive (web.archive.org) - a party with no
obligation to sebbi.pro and its own reason to keep what it holds - to take
its own copy of every page of the public chain. Each page of 500 blocks is
fixed forever once it is full, so full pages are archived once; the page
still filling, the genesis block and the verify method are archived daily.

Before asking, it fetches each page itself and records the SHA-256 of what
it served. That record - page, hash, archive link - is then sealed into the
chain as a public block. So anyone can later fetch the archived copy, hash
it, and check it against the hash sealed here, then recompute every block
in it with the published method. If sebbi.pro is gone, the archive still
answers.

WHAT IT DOES NOT COVER
Blocks withheld from the public walk (sealed under a customer's key) are not
public, so they are not archived. Their owners keep their own copies.

Starts when /x/snapshot/status is first opened after a deploy (that is what
arms it), then runs daily. Routes: status, latest, spec public. run keyed.
"""

import hashlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0"
BASE = "https://sebbi.pro/x/snapshot/"
SITE = "https://sebbi.pro"
PAGE = 500
USER_ID = "system_snapshot"
ARCHIVE_SAVE = "https://web.archive.org/save/"
FETCH_TIMEOUT = 30
ARCHIVE_TIMEOUT = 120
ARCHIVE_PAUSE = 12          # seconds between archive requests - be polite
RUN_EVERY = 24 * 3600
MAX_PAGE_BYTES = 16 * 1024 * 1024
UA = "sebbi-snapshot/1.0 (+https://sebbi.pro/x/snapshot/spec)"

PUBLIC = {("GET", "status"), ("GET", "latest"), ("GET", "spec")}

_state = {"armed": False, "running": False, "last_run": None,
          "last_result": None, "ctx": None}
_lock = threading.Lock()


# ---------------------------------------------------------------- storage

def _ensure(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS snapshot_pages ("
        "url TEXT PRIMARY KEY, full INTEGER, sha256 TEXT, bytes INTEGER, "
        "archive_url TEXT, raw_url TEXT, status TEXT, archived_at REAL)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS snapshot_runs ("
        "day TEXT PRIMARY KEY, sealed_block INTEGER, sealed_hash TEXT, "
        "pages INTEGER, archived INTEGER, failed INTEGER, tip TEXT, ran_at REAL)")
    conn.commit()


# ---------------------------------------------------------------- pages

def _page_urls(conn):
    """Every walk page of PAGE blocks. A page is full - and so never changes
    again - once PAGE blocks exist after its starting point."""
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM audit_log ORDER BY id ASC").fetchall()]
    pages = []
    start = 0
    i = 0
    while i < len(ids):
        chunk = ids[i:i + PAGE]
        pages.append({
            "url": "%s/x/walk/blocks?after=%d&limit=%d" % (SITE, start, PAGE),
            "full": len(chunk) == PAGE,
            "first_block": chunk[0], "last_block": chunk[-1]})
        start = chunk[-1]
        i += PAGE
    tip = conn.execute(
        "SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return pages, (tip[0] if tip else None)


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        body = resp.read(MAX_PAGE_BYTES + 1)
    if len(body) > MAX_PAGE_BYTES:
        raise ValueError("page too large")
    return body


def _archive(url):
    """Ask the Internet Archive to take its own copy. Returns
    (archive_url, raw_url, status)."""
    req = urllib.request.Request(ARCHIVE_SAVE + url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=ARCHIVE_TIMEOUT) as resp:
            final = resp.geturl()
            loc = resp.headers.get("Content-Location") or ""
    except urllib.error.HTTPError as exc:
        return None, None, "archive refused (HTTP %s)" % exc.code
    except Exception as exc:
        return None, None, "archive unreachable (%s)" % exc.__class__.__name__
    link = None
    for cand in (final, loc):
        if cand and "/web/" in cand:
            link = cand if cand.startswith("http") else \
                "https://web.archive.org" + cand
            break
    if not link:
        return None, None, "archive accepted; copy link not returned"
    raw = None
    try:
        part = link.split("/web/", 1)[1]
        stamp, rest = part.split("/", 1)
        stamp = "".join(c for c in stamp if c.isdigit())
        raw = "https://web.archive.org/web/%sid_/%s" % (stamp, rest)
    except Exception:
        pass
    return link, raw, "archived"


# ---------------------------------------------------------------- the run

def _run(ctx, force=False):
    conn, dblock, seal = ctx.get("conn"), ctx.get("lock"), ctx.get("seal")
    if conn is None or dblock is None:
        return {"ok": False, "error": "no database handle"}
    day = time.strftime("%Y-%m-%d", time.gmtime())
    with dblock:
        _ensure(conn)
        done = conn.execute("SELECT sealed_block FROM snapshot_runs WHERE day = ?",
                            (day,)).fetchone()
        if done and not force:
            return {"ok": True, "skipped": "already ran today",
                    "sealed_block": done[0]}
        pages, tip = _page_urls(conn)
        archived_full = set(r[0] for r in conn.execute(
            "SELECT url FROM snapshot_pages WHERE full = 1 AND status = 'archived'"
        ).fetchall())

    todo = [p for p in pages if not (p["full"] and p["url"] in archived_full)]
    todo += [{"url": SITE + "/x/walk/genesis", "full": False},
             {"url": SITE + "/x/walk/spec", "full": False}]

    record, ok, failed = [], 0, 0
    for i, p in enumerate(todo):
        entry = {"page": p["url"], "full": p["full"]}
        if "first_block" in p:
            entry["blocks"] = [p["first_block"], p["last_block"]]
        try:
            body = _fetch(p["url"])
            entry["sha256"] = hashlib.sha256(body).hexdigest()
            entry["bytes"] = len(body)
        except Exception as exc:
            entry["status"] = "could not fetch our own page (%s)" % \
                exc.__class__.__name__
            failed += 1
            record.append(entry)
            continue
        link, raw, status = _archive(p["url"])
        entry.update({"archive": link, "raw_copy": raw, "status": status})
        if status == "archived":
            ok += 1
        else:
            failed += 1
        with dblock:
            conn.execute(
                "INSERT OR REPLACE INTO snapshot_pages "
                "(url, full, sha256, bytes, archive_url, raw_url, status, "
                "archived_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (p["url"], 1 if p["full"] else 0, entry.get("sha256"),
                 entry.get("bytes"), link, raw, status, time.time()))
            conn.commit()
        record.append(entry)
        if i < len(todo) - 1:
            time.sleep(ARCHIVE_PAUSE)

    result = {"decision": "SNAPSHOT", "score": 0, "day": day,
              "archive": "Internet Archive (web.archive.org)",
              "chain_tip_at_snapshot": tip,
              "pages_in_chain": len(pages),
              "pages_this_run": record,
              "archived": ok, "failed": failed,
              "how_to_check": "Fetch raw_copy, SHA-256 it, compare with sha256 "
                              "here, then recompute its blocks with "
                              "https://sebbi.pro/x/walk/spec",
              "timestamp": time.time()}
    sealed_block, sealed_hash = None, None
    if callable(seal):
        event = {"user_id": USER_ID, "action": "public_chain_archived",
                 "amount": 0, "country": "UK", "device_id": "snapshot",
                 "anomaly": 0, "device_risk": 0}
        try:
            res = seal(event, result, result["timestamp"])
            if isinstance(res, (list, tuple)):
                sealed_hash, sealed_block = res[0], (res[1] if len(res) > 1 else None)
            elif isinstance(res, dict):
                sealed_hash = res.get("audit_hash") or res.get("hash")
                sealed_block = res.get("block_index") or res.get("index")
        except Exception:
            pass
    with dblock:
        conn.execute(
            "INSERT OR REPLACE INTO snapshot_runs (day, sealed_block, "
            "sealed_hash, pages, archived, failed, tip, ran_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (day, sealed_block, sealed_hash, len(record), ok, failed, tip,
             time.time()))
        conn.commit()
    return {"ok": True, "day": day, "archived": ok, "failed": failed,
            "pages_this_run": len(record), "sealed_block": sealed_block,
            "check_block": ("%s/x/walk/block?index=%s" % (SITE, sealed_block))
            if sealed_block else None}


def _loop():
    time.sleep(60)
    while True:
        ctx = _state.get("ctx")
        if ctx:
            with _lock:
                _state["running"] = True
            try:
                _state["last_result"] = _run(ctx)
            except Exception as exc:
                _state["last_result"] = {"ok": False, "error": str(exc)[:200]}
            _state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime())
            with _lock:
                _state["running"] = False
        time.sleep(3600)   # wakes hourly; _run itself only acts once a day


def _arm(ctx):
    with _lock:
        _state["ctx"] = ctx
        if _state["armed"]:
            return
        _state["armed"] = True
    threading.Thread(target=_loop, name="snapshot", daemon=True).start()


# ---------------------------------------------------------------- routes

def _status(ctx):
    conn, dblock = ctx.get("conn"), ctx.get("lock")
    runs, pages = [], []
    if conn is not None and dblock is not None:
        with dblock:
            _ensure(conn)
            runs = conn.execute(
                "SELECT day, sealed_block, pages, archived, failed, tip "
                "FROM snapshot_runs ORDER BY day DESC LIMIT 14").fetchall()
            pages = conn.execute(
                "SELECT url, full, sha256, archive_url, raw_url, status "
                "FROM snapshot_pages ORDER BY url").fetchall()
    return {
        "ok": True, "module": "snapshot", "version": VERSION,
        "armed": _state["armed"], "running": _state["running"],
        "last_run": _state["last_run"], "last_result": _state["last_result"],
        "archive": "Internet Archive (web.archive.org) - independent of "
                   "sebbi.pro, with no obligation to it",
        "recent_runs": [{"day": d, "sealed_block": b,
                         "check_block": ("%s/x/walk/block?index=%s" % (SITE, b))
                         if b else None,
                         "pages": p, "archived": a, "failed": f, "tip": t}
                        for d, b, p, a, f, t in runs],
        "pages": [{"page": u, "full": bool(fl), "sha256": s,
                   "archive": a, "raw_copy": r, "status": st}
                  for u, fl, s, a, r, st in pages],
        "note": "Full pages are fixed forever and archived once. The page "
                "still filling, genesis and the verify method are archived "
                "daily. Each run is sealed into the chain as a public block.",
    }, 200


def _latest(ctx):
    conn, dblock = ctx.get("conn"), ctx.get("lock")
    with dblock:
        _ensure(conn)
        r = conn.execute(
            "SELECT day, sealed_block, archived, failed, tip FROM snapshot_runs "
            "ORDER BY day DESC LIMIT 1").fetchone()
    if not r:
        return {"ok": False, "error": "no_snapshot_yet",
                "detail": "The first run starts about a minute after "
                          "/x/snapshot/status is opened."}, 404
    return {"ok": True, "day": r[0], "sealed_block": r[1],
            "check_block": ("%s/x/walk/block?index=%s" % (SITE, r[1]))
            if r[1] else None,
            "archived": r[2], "failed": r[3], "chain_tip_at_snapshot": r[4]}, 200


def _spec():
    return {
        "module": "snapshot", "version": VERSION,
        "what": "Copies every page of the public chain to the Internet Archive "
                "daily, and seals each run into the chain.",
        "why": "Witnesses stop history being rewritten. This stops it being "
               "lost: if sebbi.pro disappears, an independent archive with no "
               "obligation to it still holds the record.",
        "verify_without_us": [
            "Take a raw_copy link from https://sebbi.pro/x/snapshot/status or "
            "from the sealed run block",
            "SHA-256 the bytes it returns; compare with the sealed sha256",
            "Recompute every block in it using https://sebbi.pro/x/walk/spec",
        ],
        "not_covered": "Blocks withheld from the public walk (customer-keyed) "
                       "are not public and are not archived.",
        "routes": {"status": BASE + "status", "latest": BASE + "latest",
                   "spec": BASE + "spec",
                   "run": "POST, keyed. Runs now, even if today already ran."},
    }


def handle(method, action, data, api_key, ctx):
    ctx = ctx or {}
    try:
        _arm(ctx)
        if action in ("status", ""):
            return _status(ctx)
        if action == "latest":
            return _latest(ctx)
        if action == "spec":
            return _spec(), 200
        if action == "run":
            if not api_key:
                return {"ok": False, "error": "api_key_required"}, 401
            return _run(ctx, force=True), 200
        return {"ok": False, "error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET"),
                "post": ["run"]}, 404
    except Exception as exc:
        return {"ok": False, "error": "snapshot_failed",
                "detail": str(exc)[:200]}, 500
