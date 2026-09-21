"""
modules/custody.py  v1.0.2  -  independent copies, proven and counted

The self-proving archive file (/x/archive) can be checked anywhere. This
module proves WHERE it is actually held, by parties other than sebbi.pro.

Every day it:
  1. asks the Internet Archive whether it holds each recent sealed file, and
     if it does, fetches that copy and checks its fingerprint;
  2. fetches every registered holder's copy and checks its fingerprint;
  3. counts the independent holders whose copy is byte-for-byte a sealed
     file, and SEALS that count - with every holder, address and
     fingerprint - into the chain as a public block.

A copy only counts if it matches a fingerprint sealed in the chain. A holder
only counts if it is not sebbi.pro. The count can be checked by anyone, and
cannot be inflated: every entry names an address you can fetch yourself.

Anyone can become a holder:
  - tap the Internet Archive link on /x/custody/status, or
  - keep the file anywhere public and register the address:
      https://sebbi.pro/x/custody/offer?url=https://your.site/sebbi.json&name=You
    (it is fetched and checked before it is listed), or
  - run the keeper script (/x/custody/keeper) daily to fetch, verify and keep
    each day's file automatically.

Routes (public): status, holders, offer, keeper, spec. run is keyed.
Armed by the first visit to /x/custody/status.
"""

import gzip
import hashlib
import ipaddress
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0.2"
SITE = "https://sebbi.pro"
BASE = SITE + "/x/custody/"
USER_ID = "system_custody"
UA = "sebbi-custody/1.0.2 (+https://sebbi.pro/x/custody/spec)"
TIMEOUT = 60
MAX_BYTES = 256 * 1024 * 1024
RECENT_FILES = 3
OPERATOR_HOSTS = ("sebbi.pro", "www.sebbi.pro")

PUBLIC = {("GET", a) for a in ("status", "holders", "offer", "keeper", "spec")}

_state = {"armed": False, "ctx": None, "last_run": None, "last_result": None}
_lock = threading.Lock()
_run_lock = threading.Lock()
_offer_busy = threading.BoundedSemaphore(2)


# ---------------------------------------------------------------- helpers

def _ensure(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS custody_holders ("
        "url TEXT PRIMARY KEY, name TEXT, host TEXT, added_at REAL, "
        "last_checked REAL, last_verified REAL, last_fingerprint TEXT, "
        "last_date TEXT, last_status TEXT, times_verified INTEGER DEFAULT 0)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS custody_runs ("
        "day TEXT PRIMARY KEY, sealed_block INTEGER, sealed_hash TEXT, "
        "independent_holders INTEGER, holding_latest INTEGER, "
        "latest_sha256 TEXT, ran_at REAL)")
    conn.commit()


def _host(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


def _public_https(url):
    try:
        p = urllib.parse.urlsplit(url)
    except Exception:
        return False
    if p.scheme != "https" or p.port not in (None, 443) or not p.hostname:
        return False
    if p.username or p.password:
        return False
    try:
        for info in socket.getaddrinfo(p.hostname, 443,
                                       proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or
                    ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
    except Exception:
        return False
    return True


def _get(url, max_bytes=MAX_BYTES):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("too large")
    if raw[:2] == b"\x1f\x8b":
        # Archives keep a page exactly as it was sent - often zipped.
        raw = gzip.decompress(raw)
    return raw


def _canonical_sha(raw):
    obj = json.loads(raw.decode("utf-8"))
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")
                          ).hexdigest()


def _sealed_files():
    """date -> sha256, and sha256 -> file row, from the archive manifest."""
    data = json.loads(_get(SITE + "/x/archive/manifest").decode("utf-8"))
    files = data.get("files") or []
    return files, {f["sha256"]: f for f in files if f.get("sha256")}


def _seal(ctx, action, result):
    seal = (ctx or {}).get("seal")
    if not callable(seal):
        return None, None
    now = time.time()
    result = dict(result, decision=action.upper(), score=0, timestamp=now)
    event = {"user_id": USER_ID, "action": action, "amount": 0,
             "country": "UK", "device_id": "custody", "anomaly": 0,
             "device_risk": 0}
    try:
        res = seal(event, result, now)
    except Exception:
        return None, None
    if isinstance(res, (list, tuple)):
        return res[0], (res[1] if len(res) > 1 else None)
    if isinstance(res, dict):
        return (res.get("audit_hash") or res.get("hash"),
                res.get("block_index") or res.get("index"))
    return res, None


# ---------------------------------------------------------------- checks

def _wayback_captures(target):
    """Every capture the Internet Archive holds of an address, newest first.
    Uses the capture index; falls back to the availability lookup."""
    try:
        rows = json.loads(_get(
            "https://web.archive.org/cdx/search/cdx?url=" +
            urllib.parse.quote(target, safe="") +
            "&output=json&filter=statuscode:200&limit=-10",
            4 * 1024 * 1024).decode("utf-8"))
        stamps = [r[1] for r in rows[1:] if len(r) > 1]
        if stamps:
            return sorted(stamps, reverse=True)
    except Exception:
        pass
    try:
        avail = json.loads(_get(
            "https://archive.org/wayback/available?url=" +
            urllib.parse.quote(target, safe=""), 1024 * 1024).decode("utf-8"))
        snap = (avail.get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available"):
            return [re.sub(r"[^0-9]", "", str(snap.get("timestamp", "")))]
        return []
    except Exception:
        return None


def _check_internet_archive(files):
    """For each recent sealed file: does the Internet Archive hold it, and
    is its copy byte-for-byte the sealed file?"""
    out = []
    for f in files[:RECENT_FILES]:
        target = "%s/x/archive/file?sha256=%s" % (SITE, f["sha256"])
        row = {"holder": "Internet Archive", "date": f.get("date"),
               "sealed_sha256": f["sha256"],
               "archive_it": "https://web.archive.org/save/" + target}
        stamps = _wayback_captures(target)
        if stamps is None:
            row.update({"held": None, "note": "archive could not be asked"})
        elif not stamps:
            row.update({"held": False})
        else:
            row.update({"held": False, "captures_listed": len(stamps)})
            for stamp in stamps[:3]:
                raw_url = "https://web.archive.org/web/%sid_/%s" % (stamp, target)
                try:
                    fp = _canonical_sha(_get(raw_url))
                except Exception:
                    continue
                row.update({"held": fp == f["sha256"], "copy": raw_url,
                            "captured": stamp, "fingerprint": fp})
                if fp == f["sha256"]:
                    break
        out.append(row)
    return out


def _check_holder(url, by_sha):
    try:
        fp = _canonical_sha(_get(url))
    except Exception as exc:
        return {"fingerprint": None, "status": "unreachable (%s)"
                % exc.__class__.__name__}
    f = by_sha.get(fp)
    if not f:
        return {"fingerprint": fp,
                "status": "serves a file that is not a sealed archive file"}
    return {"fingerprint": fp, "date": f.get("date"), "status": "verified"}


def _run(ctx, force=False):
    conn, dblock = ctx.get("conn"), ctx.get("lock")
    day = time.strftime("%Y-%m-%d", time.gmtime())
    with dblock:
        _ensure(conn)
        done = conn.execute("SELECT sealed_block FROM custody_runs WHERE day = ?",
                            (day,)).fetchone()
        if done and not force:
            return {"ok": True, "skipped": "already counted today",
                    "sealed_block": done[0]}
        holders = conn.execute("SELECT url, name FROM custody_holders").fetchall()

    files, by_sha = _sealed_files()
    if not files:
        return {"ok": False, "error": "no sealed archive files yet"}
    latest = files[0]["sha256"]

    ia = _check_internet_archive(files)
    results = []
    for url, name in holders:
        r = _check_holder(url, by_sha)
        r.update({"holder": name, "url": url})
        results.append(r)
        now = time.time()
        with dblock:
            if r["status"] == "verified":
                conn.execute(
                    "UPDATE custody_holders SET last_checked = ?, "
                    "last_verified = ?, last_fingerprint = ?, last_date = ?, "
                    "last_status = ?, times_verified = times_verified + 1 "
                    "WHERE url = ?", (now, now, r["fingerprint"], r.get("date"),
                                      r["status"], url))
            else:
                conn.execute(
                    "UPDATE custody_holders SET last_checked = ?, "
                    "last_status = ? WHERE url = ?", (now, r["status"], url))
            conn.commit()

    verified = [r for r in results if r["status"] == "verified"]
    ia_held = [r for r in ia if r.get("held")]
    hosts = set(_host(r["url"]) for r in verified)
    if ia_held:
        hosts.add("web.archive.org")
    holding_latest = len([r for r in verified if r["fingerprint"] == latest]) + \
        (1 if any(r["sealed_sha256"] == latest for r in ia_held) else 0)

    result = {"day": day, "latest_file_sha256": latest,
              "independent_holders": len(hosts),
              "holding_latest_file": holding_latest,
              "internet_archive": ia, "registered_holders": results,
              "rule": "A copy counts only if its canonical fingerprint is a "
                      "sealed archive file, and only if it is held somewhere "
                      "other than sebbi.pro. Every entry names an address "
                      "anyone can fetch to check it."}
    sealed_hash, sealed_block = _seal(ctx, "custody_counted", result)
    with dblock:
        conn.execute(
            "INSERT OR REPLACE INTO custody_runs (day, sealed_block, sealed_hash, "
            "independent_holders, holding_latest, latest_sha256, ran_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (day, sealed_block, sealed_hash, len(hosts), holding_latest,
             latest, time.time()))
        conn.commit()
    return {"ok": True, "day": day, "independent_holders": len(hosts),
            "holding_latest_file": holding_latest, "sealed_block": sealed_block,
            "check_block": ("%s/x/walk/block?index=%s" % (SITE, sealed_block))
            if sealed_block else None}


def _loop():
    time.sleep(120)
    while True:
        ctx = _state.get("ctx")
        if ctx and _run_lock.acquire(blocking=False):
            try:
                _state["last_result"] = _run(ctx)
            except Exception as exc:
                _state["last_result"] = {"ok": False, "error": str(exc)[:200]}
            finally:
                _run_lock.release()
            _state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime())
        time.sleep(3600)


def _arm(ctx):
    with _lock:
        _state["ctx"] = ctx
        if _state["armed"]:
            return
        _state["armed"] = True
    threading.Thread(target=_loop, name="custody", daemon=True).start()


# ---------------------------------------------------------------- routes

def _q(data, k):
    v = (data or {}).get(k)
    return v[0] if isinstance(v, list) and v else v


def _offer(data, ctx):
    url = str(_q(data, "url") or "").strip()
    name = re.sub(r"[^A-Za-z0-9 .,&'()_-]", "", str(_q(data, "name") or ""))[:60]
    if not url:
        return {"ok": False, "error": "url_required",
                "example": BASE + "offer?url=https://your.site/sebbi.json&name=Your%20Name"}, 400
    if _host(url) in OPERATOR_HOSTS:
        return {"ok": False, "error": "operator_host",
                "detail": "A copy on sebbi.pro is not independent of sebbi.pro."}, 400
    if not _public_https(url):
        return {"ok": False, "error": "not_a_public_https_address"}, 400
    if not _offer_busy.acquire(timeout=10):
        return {"ok": False, "error": "busy"}, 429
    try:
        files, by_sha = _sealed_files()
        r = _check_holder(url, by_sha)
    finally:
        _offer_busy.release()
    if r["status"] != "verified":
        return {"ok": False, "error": "copy_not_verified", "detail": r["status"],
                "fingerprint": r.get("fingerprint"),
                "sealed_files": SITE + "/x/archive/manifest"}, 400
    conn, dblock = ctx["conn"], ctx["lock"]
    now = time.time()
    with dblock:
        _ensure(conn)
        conn.execute(
            "INSERT OR IGNORE INTO custody_holders (url, name, host, added_at, "
            "last_checked, last_verified, last_fingerprint, last_date, "
            "last_status, times_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (url, name or _host(url), _host(url), now, now, now,
             r["fingerprint"], r.get("date"), "verified"))
        conn.commit()
    _, block = _seal(ctx, "custody_holder_registered", {
        "holder": name or _host(url), "url": url,
        "fingerprint": r["fingerprint"], "file_date": r.get("date")})
    return {"ok": True, "registered": url, "holder": name or _host(url),
            "fingerprint": r["fingerprint"], "file_date": r.get("date"),
            "sealed_in_block": block,
            "note": "Your copy was fetched and matches a sealed file. It will "
                    "be re-checked daily and counted in the sealed custody "
                    "count."}, 200


def _holders(ctx):
    conn, dblock = ctx["conn"], ctx["lock"]
    with dblock:
        _ensure(conn)
        rows = conn.execute(
            "SELECT url, name, last_verified, last_fingerprint, last_date, "
            "last_status, times_verified FROM custody_holders "
            "ORDER BY added_at").fetchall()
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)) if t else None
    return {"ok": True, "holders": [
        {"url": u, "name": n, "last_verified": iso(lv),
         "last_fingerprint": fp, "file_date": d, "status": st,
         "times_verified": tv} for u, n, lv, fp, d, st, tv in rows]}, 200


def _status(ctx):
    conn, dblock = ctx["conn"], ctx["lock"]
    with dblock:
        _ensure(conn)
        runs = conn.execute(
            "SELECT day, sealed_block, independent_holders, holding_latest, "
            "latest_sha256 FROM custody_runs ORDER BY day DESC LIMIT 14").fetchall()
        n_holders = conn.execute("SELECT COUNT(*) FROM custody_holders").fetchone()[0]
    latest_link = None
    try:
        files, _ = _sealed_files()
        if files:
            latest_link = ("https://web.archive.org/save/%s/x/archive/file?"
                           "sha256=%s" % (SITE, files[0]["sha256"]))
    except Exception:
        pass
    return {
        "ok": True, "module": "custody", "version": VERSION,
        "armed": _state["armed"], "last_run": _state["last_run"],
        "last_result": _state["last_result"],
        "independent_holders_today": runs[0][2] if runs else None,
        "registered_holders": n_holders,
        "recent_counts": [{"day": d, "sealed_block": b,
                           "check_block": ("%s/x/walk/block?index=%s" % (SITE, b))
                           if b else None,
                           "independent_holders": i, "holding_latest_file": h,
                           "latest_file": s} for d, b, i, h, s in runs],
        "become_a_holder": {
            "one_tap": latest_link,
            "register_your_own_copy": BASE + "offer?url=https://your.site/sebbi.json&name=You",
            "keep_it_automatically": BASE + "keeper"},
        "rule": "Counted only if byte-for-byte a sealed file, and only if held "
                "somewhere other than sebbi.pro. Each day's count is sealed.",
    }, 200


KEEPER = r'''#!/usr/bin/env python3
"""sebbi.pro keeper - fetch, verify and keep each day's self-proving file.

Run daily (for example from cron). Standard library only.
    python3 keeper.py /path/to/public/folder
Keeps every day's file that PASSES its own built-in checks, plus latest.json.
Serve that folder publicly, then register your latest.json once at:
    https://sebbi.pro/x/custody/offer?url=https://YOUR.SITE/latest.json&name=YOU
"""
import json, os, subprocess, sys, tempfile, urllib.request

out = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(out, exist_ok=True)
ua = {"User-Agent": "sebbi-keeper/1.0"}
latest = json.load(urllib.request.urlopen(urllib.request.Request(
    "https://sebbi.pro/x/archive/latest", headers=ua), timeout=60))
url = latest["file"]
raw = urllib.request.urlopen(urllib.request.Request(url, headers=ua),
                             timeout=300).read()
fd, tmp = tempfile.mkstemp(suffix=".json")
os.write(fd, raw); os.close(fd)
check = subprocess.run([sys.executable, "-c",
    "import json,sys;exec(json.load(open(sys.argv[1]))['verifier_py'])", tmp],
    capture_output=True, text=True)
print(check.stdout)
if check.returncode != 0:
    os.remove(tmp)
    sys.exit("Not kept: the file failed its own checks.")
name = "sebbi-chain-%s-%s.json" % (latest["date"], latest["sha256"])
os.replace(tmp, os.path.join(out, name))
with open(os.path.join(out, "latest.json"), "wb") as fh:
    fh.write(raw)
print("Kept", name, "and latest.json in", out)
'''


def handle(method, action, data, api_key, ctx):
    ctx = ctx or {}
    try:
        _arm(ctx)
        if action in ("status", ""):
            return _status(ctx)
        if action == "holders":
            return _holders(ctx)
        if action == "offer":
            return _offer(data, ctx)
        if action == "keeper":
            return {"ok": True, "keeper_py": KEEPER,
                    "how": "Save keeper_py as keeper.py, run it daily with a "
                           "folder you serve publicly, then register that "
                           "folder's latest.json once."}, 200
        if action == "spec":
            return {"module": "custody", "version": VERSION,
                    "counts": "independent holders whose copy is byte-for-byte "
                              "a sealed archive file",
                    "sealed": "each day's count, with every holder and "
                              "fingerprint, is sealed into the chain",
                    "routes": {"status": BASE + "status",
                               "holders": BASE + "holders",
                               "offer": BASE + "offer?url=<https address>&name=<name>",
                               "keeper": BASE + "keeper"}}, 200
        if action == "run":
            if not api_key:
                return {"ok": False, "error": "api_key_required"}, 401
            with _run_lock:
                return _run(ctx, force=True), 200
        return {"ok": False, "error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET")}, 404
    except Exception as exc:
        return {"ok": False, "error": "custody_failed",
                "detail": str(exc)[:200]}, 500
