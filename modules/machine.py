"""
modules/machine.py  v1.0.3  -  the machine

Ask it in a web address. It goes out to the internet, does the work, and
answers in data anyone - person or program - can check.

    https://sebbi.pro/x/machine/ask?q=find 35ff59fa
    https://sebbi.pro/x/machine/ask?q=bitcoin
    https://sebbi.pro/x/machine/ask?q=verify today
    https://sebbi.pro/x/machine/ask?q=block 2013
    https://sebbi.pro/x/machine/ask?q=check openai.com
    https://sebbi.pro/x/machine/ask?q=archive today
    https://sebbi.pro/x/machine/ask?q=witness
    https://sebbi.pro/x/machine/ask?q=walk
    https://sebbi.pro/x/machine/help

Every command is also its own route (/x/machine/find?sha256=..., etc).

Every answer carries:
  sources   - each thing it fetched, with the SHA-256 of what came back
  evidence  - what it computed from that
  check_it_yourself - how to redo the same work without this machine

The machine reads and checks. It never changes anything. All routes public.
"""

import base64
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

VERSION = "1.0.3"
SITE = "https://sebbi.pro"
BASE = SITE + "/x/machine/"
UA = "sebbi-machine/1.0.3 (+https://sebbi.pro/x/machine/help)"
TIMEOUT = 30
MAX_BYTES = 96 * 1024 * 1024
EXPLORERS = [
    ("mempool.space", "https://mempool.space/api"),
    ("blockstream.info", "https://blockstream.info/api"),
]

PUBLIC = {("GET", a) for a in (
    "help", "ask", "find", "verify", "bitcoin", "block", "check",
    "archive", "witness", "walk", "register", "status", "spec")}

_busy = threading.BoundedSemaphore(3)


# ---------------------------------------------------------------- fetching

class _Trail(object):
    """Every fetch is recorded with the hash of what came back."""

    def __init__(self):
        self.sources = []

    def get(self, url, max_bytes=MAX_BYTES, accept="application/json"):
        t0 = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read(max_bytes + 1)
                final = resp.geturl()
        except urllib.error.HTTPError as exc:
            self.sources.append({"url": url, "result": "HTTP %s" % exc.code})
            raise
        except Exception as exc:
            self.sources.append({"url": url, "result": "unreachable (%s)"
                                 % exc.__class__.__name__})
            raise
        if len(raw) > max_bytes:
            self.sources.append({"url": url, "result": "too large"})
            raise ValueError("response too large")
        compressed = raw[:2] == b"\x1f\x8b"
        if compressed:
            # Archives keep a page exactly as it was sent - often zipped.
            raw = gzip.decompress(raw)
        self.sources.append({"url": url, "final_url": final,
                             "was_compressed": compressed,
                             "bytes": len(raw),
                             "sha256": hashlib.sha256(raw).hexdigest(),
                             "ms": int((time.time() - t0) * 1000)})
        return raw

    def json(self, url, **kw):
        return json.loads(self.get(url, **kw).decode("utf-8"))

    def text(self, url):
        return self.get(url, accept="text/plain").decode("utf-8").strip()


def _public_https(url):
    """For addresses a caller supplies: https, port 443, public host only."""
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


def _canonical_sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")
                          ).hexdigest()


def _answer(command, answer, evidence, trail, check, ok=True, **extra):
    out = {"ok": ok, "machine": VERSION, "command": command,
           "answer": answer, "evidence": evidence,
           "sources": trail.sources, "check_it_yourself": check,
           "answered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    out.update(extra)
    return out


# ---------------------------------------------------------------- the chain

def _recompute(blocks, prev="GENESIS"):
    problems, public, withheld = [], 0, 0
    for b in blocks:
        h = b.get("audit_hash")
        if "preimage" in b:
            pre = b["preimage"]
            if hashlib.sha256(pre.encode("utf-8")).hexdigest() != h:
                problems.append("block %s does not recompute" % b.get("block_index"))
            try:
                stated = json.loads(pre).get("prev_hash")
            except Exception:
                stated = None
            public += 1
        else:
            stated = b.get("prev_hash")
            withheld += 1
        if stated != prev:
            problems.append("block %s does not link to the block before it"
                            % b.get("block_index"))
        prev = h
    return {"blocks": len(blocks), "recomputed_from_own_text": public,
            "linkage_only": withheld, "tip": prev,
            "problems": problems[:20]}


def _walk_all(trail):
    blocks, after = [], 0
    while True:
        page = trail.json("%s/x/walk/blocks?after=%d&limit=500" % (SITE, after))
        blocks.extend(page.get("blocks") or [])
        if not page.get("has_more"):
            return blocks
        nxt = page.get("next_after")
        if not isinstance(nxt, int) or nxt <= after:
            raise ValueError("walk paging did not advance")
        after = nxt


def cmd_walk(q):
    t = _Trail()
    blocks = _walk_all(t)
    r = _recompute(blocks)
    ok = not r["problems"]
    return _answer(
        "walk",
        "Walked all %d blocks from genesis to tip and recomputed them: %s."
        % (r["blocks"], "PASS" if ok else "FAIL"),
        r, t,
        ["Fetch https://sebbi.pro/x/walk/blocks?after=0&limit=500 and each "
         "next page", "For every block with a preimage: SHA-256 it, compare "
         "with audit_hash, and check its prev_hash is the block before",
         "Method: https://sebbi.pro/x/walk/spec"], ok=ok)


def cmd_block(q):
    t = _Trail()
    try:
        n = int(q.get("n") or q.get("index"))
    except (TypeError, ValueError):
        return _answer("block", "Give a block number, e.g. block 2013.", {},
                       t, [], ok=False)
    data = t.json("%s/x/walk/block?index=%d" % (SITE, n))
    b = data.get("block") or {}
    ev = {"block_index": n, "audit_hash": b.get("audit_hash"),
          "previous_block_hash": data.get("previous_audit_hash")}
    if "preimage" in b:
        pre = b["preimage"]
        ev["recomputed_hash"] = hashlib.sha256(pre.encode("utf-8")).hexdigest()
        ev["matches"] = ev["recomputed_hash"] == b.get("audit_hash")
        try:
            ev["sealed_text"] = json.loads(pre)
            ev["links_to_previous"] = (ev["sealed_text"].get("prev_hash") ==
                                       data.get("previous_audit_hash"))
        except Exception:
            pass
        ans = ("Block %d recomputes from its own sealed text and links to the "
               "block before it." % n) if ev.get("matches") and \
            ev.get("links_to_previous") else "Block %d does NOT check out." % n
        ok = bool(ev.get("matches") and ev.get("links_to_previous"))
    else:
        ev["withheld_reason"] = b.get("withheld_reason")
        ev["links_to_previous"] = b.get("prev_hash") == data.get("previous_audit_hash")
        ans = ("Block %d is withheld from public view (%s); its link to the "
               "block before it checks out." % (n, b.get("withheld_reason")))
        ok = bool(ev["links_to_previous"])
    return _answer("block", ans, ev, t,
                   ["Open https://sebbi.pro/x/walk/block?index=%d" % n,
                    "SHA-256 the preimage text; it must equal audit_hash"],
                   ok=ok)


# ---------------------------------------------------------------- archive files

def _manifest(t):
    return t.json(SITE + "/x/archive/manifest").get("files") or []


def _resolve_file(t, ref):
    """ref: 'today', 'latest', a date, or a fingerprint or its prefix."""
    files = _manifest(t)
    ref = (ref or "latest").strip().lower()
    if ref in ("today", "latest", ""):
        return files[0] if files else None
    for f in files:
        if f.get("date") == ref:
            return f
        if len(ref) >= 8 and str(f.get("sha256", "")).startswith(ref):
            return f
    return None


def _wayback_captures(t, target):
    """Every capture the Internet Archive holds of an address, newest first.
    Uses the capture index; falls back to the availability lookup."""
    try:
        rows = t.json("https://web.archive.org/cdx/search/cdx?url=" +
                      urllib.parse.quote(target, safe="") +
                      "&output=json&filter=statuscode:200&limit=-10")
        stamps = [r[1] for r in rows[1:] if len(r) > 1]
        if stamps:
            return sorted(stamps, reverse=True)
    except Exception:
        pass
    try:
        avail = t.json("https://archive.org/wayback/available?url=" +
                       urllib.parse.quote(target, safe=""))
        snap = (avail.get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available"):
            return [re.sub(r"[^0-9]", "", str(snap.get("timestamp", "")))]
        return []
    except Exception:
        return None


def cmd_find(q):
    """Hunt for copies of an archive file across the internet, and prove
    each one is the sealed file."""
    t = _Trail()
    ref = q.get("sha256") or q.get("ref") or "latest"
    f = _resolve_file(t, ref)
    if not f:
        return _answer("find", "No sealed file matches '%s'." % ref, {}, t,
                       ["List every sealed file: https://sebbi.pro/x/archive/manifest"],
                       ok=False)
    sha = f["sha256"]
    file_url = "%s/x/archive/file?sha256=%s" % (SITE, sha)
    copies = []

    # 1. the operator's own server
    try:
        body = json.loads(t.get(file_url).decode("utf-8"))
        got = _canonical_sha(body)
        copies.append({"where": "sebbi.pro (the operator)", "url": file_url,
                       "fingerprint": got, "is_the_sealed_file": got == sha})
    except Exception:
        copies.append({"where": "sebbi.pro (the operator)", "url": file_url,
                       "found": False})

    # 2. the Internet Archive - independent, owes nothing to the operator
    stamps = _wayback_captures(t, file_url)
    if stamps is None:
        copies.append({"where": "Internet Archive (independent)",
                       "found": None, "note": "archive could not be asked"})
    elif not stamps:
        copies.append({"where": "Internet Archive (independent)",
                       "found": False,
                       "archive_it_now": "https://web.archive.org/save/" + file_url,
                       "note": "Not archived yet. Opening archive_it_now "
                               "from any phone or browser makes an "
                               "independent copy."})
    else:
        best = None
        for stamp in stamps[:3]:
            raw_url = "https://web.archive.org/web/%sid_/%s" % (stamp, file_url)
            try:
                body = json.loads(t.get(raw_url).decode("utf-8"))
                got = _canonical_sha(body)
                best = {"where": "Internet Archive (independent)",
                        "url": "https://web.archive.org/web/%s/%s" % (stamp, file_url),
                        "raw_copy": raw_url, "captured": stamp,
                        "fingerprint": got, "is_the_sealed_file": got == sha,
                        "captures_listed": len(stamps)}
                if got == sha:
                    break
            except Exception:
                best = best or {"where": "Internet Archive (independent)",
                                "found": True, "captured": stamp,
                                "note": "capture listed but could not be read"}
        copies.append(best)

    # 3. registered holders (custody) - read if the module exists
    try:
        holders = t.json(SITE + "/x/custody/holders").get("holders") or []
        for h in holders:
            copies.append({"where": h.get("name") or "holder",
                           "url": h.get("url"),
                           "fingerprint": h.get("last_fingerprint"),
                           "is_the_sealed_file": h.get("last_fingerprint") == sha,
                           "last_verified": h.get("last_verified")})
    except Exception:
        pass

    verified = [c for c in copies if c.get("is_the_sealed_file")]
    independent = [c for c in verified if "operator" not in c["where"]]
    return _answer(
        "find",
        "Found %d verified cop%s of file %s… (%d independent of sebbi.pro)."
        % (len(verified), "y" if len(verified) == 1 else "ies", sha[:12],
           len(independent)),
        {"file": {"date": f.get("date"), "sha256": sha,
                  "sealed_in_block": f.get("sealed_in_block"),
                  "check_block": f.get("check_block")},
         "copies": copies}, t,
        ["Take any copy's raw bytes, parse the JSON, re-serialise it with "
         "sorted keys and no spaces, SHA-256 it",
         "It must equal the fingerprint sealed in block %s" % f.get("sealed_in_block"),
         "Then run the checker inside the file: python3 -c \"import json,sys;"
         "exec(json.load(open(sys.argv[1]))['verifier_py'])\" FILE.json"])


def cmd_verify(q):
    """Verify a whole archive file here: fingerprint, every block, every link."""
    t = _Trail()
    url = q.get("url")
    sealed = {f["sha256"]: f for f in _manifest(t)}
    if url:
        if not _public_https(url):
            return _answer("verify", "Only public https addresses are fetched.",
                           {}, t, [], ok=False)
        where = url
    else:
        f = _resolve_file(t, q.get("sha256") or q.get("ref") or "latest")
        if not f:
            return _answer("verify", "No sealed file matches that.", {}, t,
                           [], ok=False)
        where = "%s/x/archive/file?sha256=%s" % (SITE, f["sha256"])
    body = json.loads(t.get(where).decode("utf-8"))
    fp = _canonical_sha(body)
    chain = (body.get("chain") or {})
    r = _recompute(chain.get("blocks") or [])
    checks = {
        "fingerprint": fp,
        "fingerprint_is_sealed": fp in sealed,
        "sealed_in_block": (sealed.get(fp) or {}).get("sealed_in_block"),
        "chain": r,
        "tip_matches_declared": r["tip"] == chain.get("tip"),
        "genesis_matches_declared": bool(chain.get("blocks")) and
        chain["blocks"][0].get("audit_hash") == chain.get("genesis_hash"),
        "previous_file": body.get("previous_file_sha256"),
    }
    ok = (checks["fingerprint_is_sealed"] and not r["problems"] and
          checks["tip_matches_declared"] and checks["genesis_matches_declared"])
    return _answer(
        "verify",
        "%s: file %s… is %s, and its %d blocks %s." % (
            "PASS" if ok else "FAIL", fp[:12],
            "a sealed file" if checks["fingerprint_is_sealed"] else "NOT a sealed file",
            r["blocks"], "all check out" if not r["problems"] else "do not all check out"),
        checks, t,
        ["The same checks run with nothing from us: the program is inside the "
         "file. python3 -c \"import json,sys;exec(json.load(open(sys.argv[1]))"
         "['verifier_py'])\" FILE.json"], ok=ok)


def cmd_archive(q):
    """Ask the Internet Archive to take an independent copy, and hand back
    a one-tap link that works from any phone if it refuses a server."""
    t = _Trail()
    what = (q.get("what") or "today").strip().lower()
    if what in ("today", "latest", "file"):
        f = _resolve_file(t, "latest")
        target = "%s/x/archive/file?sha256=%s" % (SITE, f["sha256"]) if f else None
    elif what.startswith("block"):
        n = re.sub(r"[^0-9]", "", what)
        target = "%s/x/walk/block?index=%s" % (SITE, n) if n else None
    elif what in ("chain", "genesis"):
        target = SITE + "/x/walk/genesis"
    elif what in ("register", "ratings"):
        target = SITE + "/x/integrity/register"
    else:
        target = None
    if not target:
        return _answer("archive", "Say what to archive: today, block 2013, "
                       "genesis or register.", {}, t, [], ok=False)
    tap = "https://web.archive.org/save/" + target
    result = None
    try:
        t.get(tap, accept="*/*", max_bytes=4 * 1024 * 1024)
        result = "the archive accepted the request from this server"
    except Exception:
        result = ("the archive turned this server away, as it often does "
                  "with cloud servers - the one-tap link below works from "
                  "any phone or browser")
    return _answer(
        "archive",
        "Archive request for %s: %s." % (target, result),
        {"target": target, "one_tap_archive": tap,
         "then_find_it": BASE + "find?ref=latest"}, t,
        ["Open one_tap_archive on your own device", "Then ask the machine to "
         "find it: https://sebbi.pro/x/machine/ask?q=find today"])


# ---------------------------------------------------------------- bitcoin

def cmd_bitcoin(q):
    """Follow the chain's anchor all the way into Bitcoin, and check it
    against two independent Bitcoin explorers."""
    t = _Trail()
    a = t.json(SITE + "/x/ots/latest_confirmed")
    if not a.get("ok"):
        return _answer("bitcoin", "No confirmed Bitcoin proof yet.", a, t, [],
                       ok=False)
    tip = str(a.get("tip") or "").lower()
    ev = {"chain_tip": tip, "tip_is_block": a.get("tip_is_block"),
          "stamp_id": a.get("stamp_id")}
    attest = []
    try:
        from opentimestamps.core.serialize import BytesDeserializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile
        from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
        det = DetachedTimestampFile.deserialize(BytesDeserializationContext(
            base64.b64decode(a["ots_base64"])))
        tb = bytes.fromhex(tip)
        forms = {
            "sha256 of the tip's bytes": hashlib.sha256(tb).digest(),
            "the tip's bytes directly": tb,
            "sha256 of the tip as text": hashlib.sha256(tip.encode("ascii")).digest(),
            "sha256 of the tip as a line of text":
                hashlib.sha256((tip + "\n").encode("ascii")).digest(),
        }
        match = [name for name, d in forms.items() if det.file_digest == d]
        ev["proof_is_for_this_tip"] = bool(match)
        ev["proof_commits_to"] = match[0] if match else None
        for msg, att in det.timestamp.all_attestations():
            if isinstance(att, BitcoinBlockHeaderAttestation):
                attest.append((att.height, msg[::-1].hex()))
    except ImportError:
        ev["note"] = "proof reader not installed on this server"
    except Exception as exc:
        ev["note"] = "proof could not be read: %s" % exc.__class__.__name__
    if not attest:
        heights = a.get("bitcoin_block_heights") or []
        attest = [(h, None) for h in heights]
    results = []
    for height, expected_root in attest[:2]:
        row = {"bitcoin_block": height,
               "proof_computes_merkle_root": expected_root, "explorers": []}
        for name, api in EXPLORERS:
            try:
                bh = t.text("%s/block-height/%d" % (api, height))
                blk = t.json("%s/block/%s" % (api, bh))
                row["explorers"].append({
                    "explorer": name, "block_hash": bh,
                    "merkle_root": blk.get("merkle_root"),
                    "time": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime(blk.get("timestamp", 0))),
                    "matches_proof": (expected_root is not None and
                                      blk.get("merkle_root") == expected_root)})
            except Exception:
                row["explorers"].append({"explorer": name,
                                         "result": "unreachable"})
        roots = set(e.get("merkle_root") for e in row["explorers"]
                    if e.get("merkle_root"))
        row["explorers_agree"] = len(roots) == 1
        row["proof_lands_on_block"] = bool(expected_root) and \
            roots == {expected_root}
        results.append(row)
    ev["bitcoin"] = results
    ok = bool(results) and all(r.get("proof_lands_on_block") for r in results) \
        and ev.get("proof_is_for_this_tip", False)
    first = results[0] if results else {}
    when = next((e.get("time") for e in first.get("explorers", [])
                 if e.get("time")), None)
    return _answer(
        "bitcoin",
        ("The chain tip at block %s is committed in Bitcoin block %s (%s). "
         "The proof lands exactly on that block's merkle root, and two "
         "independent explorers agree on it." % (
             a.get("tip_is_block"), first.get("bitcoin_block"), when))
        if ok else "The Bitcoin proof could not be fully confirmed; see evidence.",
        ev, t,
        ["Download the proof: https://sebbi.pro/x/ots/latest_confirmed "
         "(ots_base64)", "Run: ots verify, which checks the same merkle root "
         "against your own Bitcoin node",
         "Or open the block on mempool.space and blockstream.info and compare "
         "its merkle root with proof_computes_merkle_root"], ok=ok)


# ---------------------------------------------------------------- others

def cmd_check(q):
    t = _Trail()
    d = (q.get("domain") or "").strip().lower()
    if not d:
        return _answer("check", "Give a domain, e.g. check openai.com.", {}, t,
                       [], ok=False)
    r = t.json(SITE + "/x/integrity/check?domain=" + urllib.parse.quote(d))
    return _answer(
        "check", "%s verifies as %s (%s)." % (d, r.get("verified_level"),
                                              r.get("badge")),
        {k: r.get(k) for k in ("domain", "verified_level", "badge",
                               "claimed_level", "overclaimed", "verdict",
                               "request_sealed", "verdict_sealed")}, t,
        ["Full result: https://sebbi.pro/x/integrity/check?domain=" + d,
         "The verdict is sealed in the block shown; recompute it with "
         "https://sebbi.pro/x/machine/ask?q=block <number>"])


def cmd_witness(q):
    t = _Trail()
    held = t.json("https://mir.events/v1/transparency/held/tips?peer=sebbi")
    tips = [e.get("peer_tip") for e in (held.get("tips") or []) if e.get("peer_tip")]
    found = []
    blocks = _walk_all(t)
    index = {b["audit_hash"]: b.get("block_index") for b in blocks}
    for tip in tips:
        if tip in index:
            found.append(index[tip])
    return _answer(
        "witness",
        "MIR, an independent chain, holds %d of sebbi.pro's tips; %d are "
        "blocks in the chain as served today." % (len(tips), len(found)),
        {"witness": "MIR (MIRegistry)", "tips_held": len(tips),
         "matched_blocks": sorted(found)[-20:]}, t,
        ["Fetch https://mir.events/v1/transparency/held/tips?peer=sebbi",
         "Look each peer_tip up in the walk; every match is a block MIR holds"])


def cmd_register(q):
    t = _Trail()
    r = t.json(SITE + "/x/integrity/register")
    rows = [{"domain": e.get("domain"), "level": e.get("verified_level"),
             "badge": e.get("badge"), "sealed_in_block": e.get("sealed_in_block")}
            for e in r.get("entries") or []]
    return _answer("register", "%d domains rated; every rating is sealed."
                   % len(rows), {"entries": rows}, t,
                   ["Recompute any rating's block: "
                    "https://sebbi.pro/x/machine/ask?q=block <number>"])


def cmd_help(q):
    ex = lambda s: BASE + "ask?q=" + urllib.parse.quote(s)
    return {"ok": True, "machine": VERSION,
            "what": "Ask in a web address. The machine goes out to the "
                    "internet, does the work, and answers with its sources "
                    "and a way to check the answer without it.",
            "commands": {
                "find <fingerprint|today|date>": ex("find today"),
                "verify <fingerprint|today>": ex("verify today"),
                "bitcoin": ex("bitcoin"),
                "block <number>": ex("block 2013"),
                "walk": ex("walk"),
                "check <domain>": ex("check openai.com"),
                "witness": ex("witness"),
                "archive <today|block N|genesis|register>": ex("archive today"),
                "register": ex("register"),
            },
            "rule": "The machine reads and checks. It never changes anything."}


COMMANDS = {"find": cmd_find, "verify": cmd_verify, "bitcoin": cmd_bitcoin,
            "block": cmd_block, "walk": cmd_walk, "check": cmd_check,
            "witness": cmd_witness, "archive": cmd_archive,
            "register": cmd_register, "help": cmd_help}


def _parse(text):
    words = str(text or "").strip().split()
    if not words:
        return "help", {}
    cmd = words[0].lower()
    arg = " ".join(words[1:]).strip()
    q = {}
    if cmd in ("find", "verify"):
        q["ref"] = arg or "latest"
    elif cmd == "block":
        q["n"] = arg
    elif cmd == "check":
        q["domain"] = arg
    elif cmd == "archive":
        q["what"] = arg or "today"
    return cmd, q


def handle(method, action, data, api_key, ctx):
    q = {}
    for k, v in (data or {}).items():
        q[k] = v[0] if isinstance(v, list) and v else v
    action = action or "help"
    if action == "ask":
        action, parsed = _parse(q.get("q"))
        q.update(parsed)
    if action in ("status", "spec"):
        action = "help"
    fn = COMMANDS.get(action)
    if not fn:
        out = cmd_help(q)
        out.update({"ok": False, "error": "unknown command: %s" % action})
        return out, 404
    if action == "help":
        return fn(q), 200
    if not _busy.acquire(timeout=20):
        return {"ok": False, "error": "busy",
                "detail": "Three commands are running. Try again shortly."}, 429
    try:
        out = fn(q)
        return out, 200
    except Exception as exc:
        return {"ok": False, "command": action,
                "error": "%s: %s" % (exc.__class__.__name__, str(exc)[:200])}, 502
    finally:
        _busy.release()
