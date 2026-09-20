"""
modules/ots.py  v1.2  -  serve the OpenTimestamps proofs, and upgrade them

anchor.py stamps the chain tip hourly and writes the .ots proof to the
anchor volume. Nothing served those files, so "anchored to Bitcoin" was a
claim a third party had to take on trust.

PENDING IS NOT CONFIRMED. A proof written at stamping time holds a PENDING
attestation - a calendar's promise to commit the digest to Bitcoin. It is
not evidence of anything on chain until it is UPGRADED, after the
calendar's transaction lands. anchor.py never upgraded, so every proof
written before this module is pending. Said plainly because an auditor's
own verifier says it first.

v1.1: the automatic upgrade now skips proofs that are already confirmed.
v1.0 took the oldest 20 every run whether or not they were finished, so
once those 20 confirmed it kept re-checking them forever and never reached
the pending ones behind them. Confirmed counts now only count proofs that
became confirmed in that run, not ones that already were.

v1.2: the newest proofs matter most. Every run now upgrades half its batch
from the newest end as well as half from the oldest, so tips of the chain
running today confirm within hours instead of waiting behind the backlog.
A new public route, latest_confirmed, serves the newest proof that is
confirmed in Bitcoin AND whose tip is a block in the chain running now -
the one address a verifier needs. Two more calendars are asked (bob and
finney), because proofs name whichever calendars accepted them.

Routes: spec, status, list, proof, latest_confirmed public. upgrade keyed.
Proofs live at ANCHOR_DIR (default /data/anchors) - only durable on Railway
if a volume is mounted there. /x/ots/status reports what is really present.
"""

import base64
import hashlib
import json
import os
import threading
import time

VERSION = "1.2"

PUBLIC = {("GET", "spec"), ("GET", "status"), ("GET", "list"),
          ("GET", "proof"), ("GET", "latest_confirmed")}

ANCHOR_DIR = os.environ.get("ANCHOR_DIR", "/data/anchors")
MAX_PROOF_BYTES = 262144

CALENDARS = [
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://alice.btc.calendar.opentimestamps.org",
    "https://bob.btc.calendar.opentimestamps.org",
    "https://finney.calendar.eternitywall.com",
]

# ---- automatic upgrading
#
# anchor.py stamps and walks away, which is how 767 proofs ended up pending.
# This finishes the job on a timer so nobody has to remember to.
#
# The calendars are free public infrastructure run by volunteers. Firing 767
# requests at them in one go would be rude and would probably get us rate
# limited, so this works in small batches, oldest first, and skips anything
# too young to have confirmed yet, and anything already confirmed. A backlog
# clears over days rather than minutes, which is fine - nothing is lost by a
# proof staying pending a little longer, and the stamp time is already fixed.
AUTO_UPGRADE_ENABLED = os.environ.get("OTS_AUTO_UPGRADE", "1") == "1"
AUTO_UPGRADE_INTERVAL = int(os.environ.get("OTS_UPGRADE_INTERVAL", "3600"))
AUTO_UPGRADE_BATCH = int(os.environ.get("OTS_UPGRADE_BATCH", "20"))

# A Bitcoin confirmation takes an hour or more, and the calendars aggregate
# before they commit. Asking about a proof stamped ten minutes ago wastes a
# request and gets a "not ready" every time.
MIN_AGE_SECONDS = int(os.environ.get("OTS_MIN_AGE", "10800"))

# Breathing room between calendar calls.
CALENDAR_PAUSE = 0.5

_auto = {"started": False, "runs": 0, "last_run": None, "last_result": None,
         "upgraded_total": 0, "confirmed_total": 0}

# Stamp ids already seen confirmed. A confirmed proof never goes back to
# pending, so once seen it is never read or asked about again.
_confirmed_seen = set()
_file_lock = threading.Lock()


def _read_index():
    path = os.path.join(ANCHOR_DIR, "anchors.jsonl")
    rows = []
    if not os.path.exists(path):
        return rows
    try:
        with open(path, "r") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
    except Exception:
        pass
    return rows


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except Exception:
        return None


def _stamp_id(path):
    if not path:
        return None
    name = os.path.basename(path)
    if name.startswith("tip_") and name.endswith(".ots"):
        return name[4:-4]
    return None


def _describe(raw):
    """What is actually inside this proof. Never guesses."""
    out = {"pending_calendars": [], "bitcoin_block_heights": [],
           "state": "unknown", "read_error": None}
    try:
        from opentimestamps.core.serialize import BytesDeserializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile
        from opentimestamps.core.notary import (PendingAttestation,
                                                BitcoinBlockHeaderAttestation)
    except Exception as exc:
        out["read_error"] = "opentimestamps library not available: %s" % exc
        return out

    try:
        detached = DetachedTimestampFile.deserialize(
            BytesDeserializationContext(raw))
    except Exception as exc:
        out["read_error"] = "could not parse proof: %s" % exc
        out["state"] = "unreadable"
        return out

    def walk(timestamp):
        for att in timestamp.attestations:
            if isinstance(att, PendingAttestation):
                uri = att.uri
                if isinstance(uri, bytes):
                    uri = uri.decode("utf-8", "replace")
                if uri not in out["pending_calendars"]:
                    out["pending_calendars"].append(uri)
            elif isinstance(att, BitcoinBlockHeaderAttestation):
                h = getattr(att, "height", None)
                if h is not None and h not in out["bitcoin_block_heights"]:
                    out["bitcoin_block_heights"].append(h)
        for _, sub in timestamp.ops.items():
            walk(sub)

    try:
        walk(detached.timestamp)
    except Exception as exc:
        out["read_error"] = "could not walk proof: %s" % exc
        return out

    if out["bitcoin_block_heights"]:
        out["state"] = "confirmed"
        out["means"] = ("Committed in Bitcoin block %s. Verifiable against "
                        "the blockchain by anyone, with nothing from us."
                        % ", ".join(str(h) for h in out["bitcoin_block_heights"]))
    elif out["pending_calendars"]:
        out["state"] = "pending"
        out["means"] = ("A calendar has accepted this digest and promised to "
                        "commit it to Bitcoin. NOT yet evidence of anything "
                        "on chain. Upgrade it once the transaction confirms.")
    else:
        out["state"] = "empty"
        out["means"] = "No attestations found in this proof."
    return out


def _proof_bytes(stamp_id):
    path = os.path.join(ANCHOR_DIR, "tip_%s.ots" % stamp_id)
    if not os.path.exists(path):
        return None, path, "no proof file at %s" % path
    try:
        if os.path.getsize(path) > MAX_PROOF_BYTES:
            return None, path, "proof unexpectedly large"
        with open(path, "rb") as handle:
            return handle.read(), path, None
    except Exception as exc:
        return None, path, "could not read proof: %s" % exc


def _tip_for(stamp_id):
    try:
        with open(os.path.join(ANCHOR_DIR, "tip_%s.txt" % stamp_id)) as h:
            return h.read().strip()
    except Exception:
        return None


def _is_confirmed(sid):
    """True if this proof already carries a Bitcoin attestation."""
    if sid in _confirmed_seen:
        return True
    raw, _p, _e = _proof_bytes(sid)
    if raw is None:
        return False
    if _describe(raw)["state"] == "confirmed":
        _confirmed_seen.add(sid)
        return True
    return False


def _pending_candidates(limit=None):
    """Stamps old enough to be worth asking about and not yet confirmed,
    oldest first.

    Oldest first on purpose: the oldest pending proofs are the ones most
    likely to have confirmed, so a backlog clears from the far end rather
    than the recent end. Already-confirmed proofs are skipped, otherwise
    they would fill every batch forever.
    """
    now = time.time()
    out = []
    for row in _read_index():
        if not row.get("ots"):
            continue
        sid = _stamp_id(row.get("ots_file"))
        if not sid or not sid.isdigit():
            continue
        if now - float(sid) < MIN_AGE_SECONDS:
            continue
        if not os.path.exists(os.path.join(ANCHOR_DIR, "tip_%s.ots" % sid)):
            continue
        if _is_confirmed(sid):
            continue
        out.append(sid)
        if limit is not None and len(out) >= limit:
            break
    return out


def _pending_count():
    return len(_pending_candidates())


def _newest_pending(limit):
    """Pending proofs old enough to have confirmed, NEWEST first. These are
    the tips of the chain running today, the ones a verifier asks about."""
    now = time.time()
    out = []
    for row in reversed(_read_index()):
        if not row.get("ots"):
            continue
        sid = _stamp_id(row.get("ots_file"))
        if not sid or not sid.isdigit():
            continue
        if now - float(sid) < MIN_AGE_SECONDS:
            continue
        if not os.path.exists(os.path.join(ANCHOR_DIR, "tip_%s.ots" % sid)):
            continue
        if _is_confirmed(sid):
            continue
        out.append(sid)
        if len(out) >= limit:
            break
    return out


def _tip_in_chain(tip, ctx):
    conn, lock = (ctx or {}).get("conn"), (ctx or {}).get("lock")
    if conn is None or lock is None or not tip:
        return None
    try:
        with lock:
            r = conn.execute("SELECT id FROM audit_log WHERE audit_hash = ?",
                             (tip,)).fetchone()
        return r[0] if r else False
    except Exception:
        return None


LATEST_SCAN = 500


def _latest_confirmed(ctx):
    """The newest proof that is confirmed in Bitcoin and whose tip is a
    block in the chain running now. Checked in that order, newest first."""
    rows = [r for r in reversed(_read_index()) if r.get("ots")]
    looked = 0
    for row in rows[:LATEST_SCAN]:
        sid = _stamp_id(row.get("ots_file"))
        if not sid or not sid.isdigit():
            continue
        looked += 1
        raw, _p, _e = _proof_bytes(sid)
        if raw is None:
            continue
        d = _describe(raw)
        if d["state"] != "confirmed":
            continue
        _confirmed_seen.add(sid)
        tip = (_tip_for(sid) or row.get("tip") or "").strip().lower()
        block = _tip_in_chain(tip, ctx)
        if block is False:
            continue
        out, status = _proof({"ts": sid})
        if status != 200:
            continue
        out["tip_is_block"] = block
        out["check_block"] = ("https://sebbi.pro/x/walk/block?index=%s" % block
                              if block else None)
        out["why_this_one"] = ("The newest proof that is confirmed in Bitcoin "
                               "and whose tip is a block in the chain running "
                               "now. Older confirmations of earlier chains are "
                               "skipped, not hidden - they stay at /x/ots/list.")
        return out, 200
    return {"ok": False, "error": "no_confirmed_current_proof_yet",
            "looked_at": looked,
            "detail": "No proof of a current-chain tip has confirmed in Bitcoin "
                      "yet. The upgrader works the newest end every hour, and "
                      "a confirmation takes a few hours. Nothing is wrong; it "
                      "is simply not there yet.",
            "status": "https://sebbi.pro/x/ots/status"}, 404


def _status():
    rows = _read_index()
    exists = os.path.isdir(ANCHOR_DIR)
    files = []
    if exists:
        try:
            files = [f for f in os.listdir(ANCHOR_DIR) if f.endswith(".ots")]
        except Exception:
            files = []

    stamped = [r for r in rows if r.get("ots")]
    out = {
        "ok": True, "module": "ots", "version": VERSION,
        "anchor_dir": ANCHOR_DIR,
        "storage_present": exists,
        "proof_files_on_disk": len(files),
        "anchor_attempts_recorded": len(rows),
        "stamped": len(stamped),
        "failed": len(rows) - len(stamped),
        "first_attempt": _iso(rows[0].get("ts")) if rows else None,
        "last_attempt": _iso(rows[-1].get("ts")) if rows else None,
    }

    if not exists:
        out["warning"] = (
            "The anchor directory does not exist on this container. Either "
            "no anchor has run, or no persistent volume is mounted at %s - "
            "in which case every proof is lost on redeploy and the history "
            "restarts silently. Check before calling this durable."
            % ANCHOR_DIR)
    elif len(files) < len(stamped):
        out["warning"] = (
            "%d successful stamps recorded but only %d proof files on disk. "
            "Files have been lost, most likely to a redeploy without a "
            "persistent volume." % (len(stamped), len(files)))

    if stamped:
        sid = _stamp_id(stamped[-1].get("ots_file"))
        if sid:
            raw, _p, err = _proof_bytes(sid)
            if raw:
                d = _describe(raw)
                out["latest_proof"] = {
                    "stamp_id": sid, "tip": stamped[-1].get("tip"),
                    "stamped_at": _iso(stamped[-1].get("ts")),
                    "state": d["state"],
                    "bitcoin_block_heights": d["bitcoin_block_heights"],
                    "pending_calendars": d["pending_calendars"],
                    "means": d.get("means"),
                    "read_error": d.get("read_error"),
                }
            else:
                out["latest_proof"] = {"stamp_id": sid, "error": err}

    out["auto_upgrade"] = {
        "enabled": AUTO_UPGRADE_ENABLED,
        "running": _auto["started"],
        "every_seconds": AUTO_UPGRADE_INTERVAL,
        "batch_size": AUTO_UPGRADE_BATCH,
        "skips_proofs_under_hours": MIN_AGE_SECONDS // 3600,
        "runs": _auto["runs"],
        "last_run": _auto["last_run"],
        "last_result": _auto["last_result"],
        "upgraded_since_start": _auto["upgraded_total"],
        "newly_confirmed_since_start": _auto["confirmed_total"],
        "confirmed_seen": len(_confirmed_seen),
        "pending_eligible_now": _pending_count(),
        "note": ("Each run takes half its batch from the newest proofs and half "
                 "from the oldest, skipping proofs already confirmed. The calendars are free infrastructure run by "
                 "volunteers, so a backlog clears over days rather than "
                 "minutes. Nothing is lost by a proof staying pending longer "
                 "- the stamp time is already fixed."),
    }

    out["honest_note"] = (
        "A proof written at stamping time is PENDING - a promise to commit "
        "the digest to Bitcoin, not evidence that it has been. It becomes "
        "confirmed only after being upgraded. The auto-upgrade does that on "
        "a timer; until a proof is upgraded, pending is what it is.")
    return out, 200


def _list(data):
    rows = _read_index()
    try:
        limit = min(int(data.get("limit", 50)), 500)
    except (TypeError, ValueError):
        limit = 50

    out = []
    for row in list(reversed(rows))[:limit]:
        sid = _stamp_id(row.get("ots_file"))
        entry = {"stamp_id": sid, "tip": row.get("tip"),
                 "stamped_at": _iso(row.get("ts")),
                 "ots_written": bool(row.get("ots")),
                 "note": row.get("note")}
        if sid:
            entry["proof_on_disk"] = os.path.exists(
                os.path.join(ANCHOR_DIR, "tip_%s.ots" % sid))
            entry["proof"] = "https://sebbi.pro/x/ots/proof?ts=%s" % sid
        out.append(entry)

    return {"ok": True, "count": len(out), "anchors": out,
            "note": "Newest first. ots_written false is a recorded failure, "
                    "kept rather than hidden - a gap in anchoring is exactly "
                    "what an auditor needs to see."}, 200


def _proof(data):
    stamp_id = str(data.get("ts") or data.get("stamp_id") or "").strip()
    tip = str(data.get("tip") or "").strip().lower()

    if not stamp_id and tip:
        for row in reversed(_read_index()):
            if str(row.get("tip", "")).lower() == tip and row.get("ots_file"):
                stamp_id = _stamp_id(row.get("ots_file"))
                break
        if not stamp_id:
            return {"ok": False, "error": "no_proof_for_tip", "tip": tip,
                    "detail": "No successful stamp recorded for that tip. "
                              "https://sebbi.pro/x/ots/list shows every "
                              "attempt."}, 404

    if not stamp_id:
        return {"ok": False, "error": "ts_or_tip_required",
                "detail": "?ts=<stamp_id> or ?tip=<64 hex>. Ids at "
                          "https://sebbi.pro/x/ots/list"}, 400
    if not stamp_id.isdigit():
        return {"ok": False, "error": "bad_stamp_id"}, 400

    raw, _path, err = _proof_bytes(stamp_id)
    if raw is None:
        return {"ok": False, "error": "proof_unavailable",
                "detail": err, "stamp_id": stamp_id}, 404

    d = _describe(raw)
    recorded_tip = _tip_for(stamp_id)
    return {
        "ok": True, "stamp_id": stamp_id, "stamped_at": _iso(stamp_id),
        "tip": recorded_tip, "digest_sha256": recorded_tip,
        "proof_bytes": len(raw),
        "proof_sha256": hashlib.sha256(raw).hexdigest(),
        "ots_base64": base64.b64encode(raw).decode("ascii"),
        "state": d["state"],
        "bitcoin_block_heights": d["bitcoin_block_heights"],
        "pending_calendars": d["pending_calendars"],
        "means": d.get("means"), "read_error": d.get("read_error"),
        "how_to_verify": {
            "1": "base64 -d the ots_base64 field into tip.ots",
            "2": "printf '%s' <tip> | xxd -r -p > tip.bin",
            "3": "ots verify -f tip.bin tip.ots",
            "4": "if pending: ots upgrade tip.ots",
            "needs": "pip install opentimestamps-client. Nothing of ours.",
        },
        "note": "These are the bytes as written at stamping time, plus any "
                "Bitcoin path added by upgrading. Nothing regenerated or "
                "normalised.",
    }, 200


def _upgrade(data):
    """Ask the calendars to complete pending proofs.

    Upgrading only ADDS the path from the digest to a Bitcoin block. It
    cannot change what was committed or when, which is why the standard
    client overwrites the file too.
    """
    try:
        from opentimestamps.calendar import RemoteCalendar
        from opentimestamps.core.serialize import (BytesDeserializationContext,
                                                   BytesSerializationContext)
        from opentimestamps.core.timestamp import DetachedTimestampFile
        from opentimestamps.core.notary import PendingAttestation
    except Exception as exc:
        return {"ok": False, "error": "library_unavailable", "detail": str(exc),
                "fix": "add opentimestamps-client to requirements.txt"}, 501

    try:
        limit = min(int(data.get("limit", 25)), 200)
    except (TypeError, ValueError):
        limit = 25
    only = str(data.get("ts") or "").strip()

    auto = bool(data.get("auto"))

    if auto:
        # Half from the newest end (today's chain, what verifiers ask about),
        # half from the oldest (the backlog). Never the same proof twice.
        newest = _newest_pending(max(1, limit // 2))
        oldest = [c for c in _pending_candidates(limit) if c not in newest]
        candidates = newest + oldest[:max(0, limit - len(newest))]
    elif only:
        candidates = [only]
    else:
        # Manual run: newest first, which is what someone checking by hand
        # usually wants to see.
        candidates = [_stamp_id(r.get("ots_file"))
                      for r in reversed(_read_index()) if r.get("ots")]
        candidates = [c for c in candidates if c][:limit]

    results = []
    upgraded = newly_confirmed = already_confirmed = still_pending = errors = 0

    for sid in candidates:
        if not sid:
            continue
        with _file_lock:
            raw, path, err = _proof_bytes(sid)
            if raw is None:
                results.append({"stamp_id": sid, "ok": False, "detail": err})
                errors += 1
                continue

            before = _describe(raw)
            if before["state"] == "confirmed":
                _confirmed_seen.add(sid)
                already_confirmed += 1
                results.append({"stamp_id": sid, "ok": True,
                                "state": "confirmed",
                                "bitcoin_block_heights":
                                    before["bitcoin_block_heights"],
                                "action": "already complete, left alone"})
                continue

            try:
                detached = DetachedTimestampFile.deserialize(
                    BytesDeserializationContext(raw))
            except Exception as exc:
                results.append({"stamp_id": sid, "ok": False,
                                "detail": "could not parse: %s" % exc})
                errors += 1
                continue

            merged = [0]

            def attempt(timestamp):
                for att in list(timestamp.attestations):
                    if not isinstance(att, PendingAttestation):
                        continue
                    uri = att.uri
                    if isinstance(uri, bytes):
                        uri = uri.decode("utf-8", "replace")
                    if uri not in CALENDARS:
                        continue
                    try:
                        completed = RemoteCalendar(uri).get_timestamp(
                            timestamp.msg)
                        timestamp.merge(completed)
                        merged[0] += 1
                    except Exception:
                        # Not ready yet is the normal case, not an error.
                        pass
                    # Free volunteer-run infrastructure. Do not hammer it.
                    time.sleep(CALENDAR_PAUSE)
                for _, sub in list(timestamp.ops.items()):
                    attempt(sub)

            try:
                attempt(detached.timestamp)
            except Exception as exc:
                results.append({"stamp_id": sid, "ok": False,
                                "detail": "upgrade walk failed: %s" % exc})
                errors += 1
                continue

            if merged[0] == 0:
                still_pending += 1
                results.append({"stamp_id": sid, "ok": True,
                                "state": "pending",
                                "action": "no calendar had it ready yet",
                                "detail": "Normal. A Bitcoin confirmation "
                                          "takes hours. Run again later."})
                continue

            try:
                ctx = BytesSerializationContext()
                detached.serialize(ctx)
                new_bytes = ctx.getbytes()
                tmp = path + ".tmp"
                with open(tmp, "wb") as handle:
                    handle.write(new_bytes)
                os.replace(tmp, path)
            except Exception as exc:
                results.append({"stamp_id": sid, "ok": False,
                                "detail": "upgraded but could not write: %s"
                                          % exc})
                errors += 1
                continue

        after = _describe(new_bytes)
        upgraded += 1
        if after["state"] == "confirmed":
            _confirmed_seen.add(sid)
            newly_confirmed += 1
        results.append({"stamp_id": sid, "ok": True, "state": after["state"],
                        "bitcoin_block_heights": after["bitcoin_block_heights"],
                        "action": "upgraded, %d calendar response(s) merged"
                                  % merged[0],
                        "proof_bytes": len(new_bytes)})

    return {"ok": True, "examined": len(results), "upgraded": upgraded,
            "newly_confirmed": newly_confirmed,
            "already_confirmed": already_confirmed,
            "still_pending": still_pending,
            "errors": errors, "results": results,
            "note": "Upgrading only adds the path from digest to Bitcoin "
                    "block. It cannot alter what was committed or when. "
                    "Proofs not yet ready stay pending; nothing is lost by "
                    "trying early."}, 200


def _upgrade_loop():
    """Finish what anchor.py starts. Quiet, slow, and never fatal."""
    time.sleep(90)          # let the server come up
    while True:
        try:
            result, _status_code = _upgrade({"limit": AUTO_UPGRADE_BATCH,
                                             "auto": True})
            _auto["runs"] += 1
            _auto["last_run"] = _iso(time.time())
            _auto["last_result"] = {
                "examined": result.get("examined"),
                "upgraded": result.get("upgraded"),
                "newly_confirmed": result.get("newly_confirmed"),
                "still_pending": result.get("still_pending"),
                "errors": result.get("errors"),
            }
            _auto["upgraded_total"] += int(result.get("upgraded") or 0)
            _auto["confirmed_total"] += int(result.get("newly_confirmed") or 0)
            if result.get("upgraded"):
                print("OTS: upgraded %s proof(s), %s newly confirmed"
                      % (result.get("upgraded"),
                         result.get("newly_confirmed")), flush=True)
        except Exception as exc:
            print("OTS upgrade loop error: %s" % exc, flush=True)
        time.sleep(AUTO_UPGRADE_INTERVAL)


def _start_auto():
    if _auto["started"] or not AUTO_UPGRADE_ENABLED:
        return
    _auto["started"] = True
    threading.Thread(target=_upgrade_loop, name="ots-upgrade",
                     daemon=True).start()
    print("OTS: auto-upgrade every %ds, %d per batch, skipping proofs under "
          "%dh old and proofs already confirmed"
          % (AUTO_UPGRADE_INTERVAL, AUTO_UPGRADE_BATCH,
             MIN_AGE_SECONDS // 3600), flush=True)


def _spec():
    return {
        "module": "ots", "version": VERSION,
        "what": "Serves the OpenTimestamps proofs for the chain tip, and "
                "upgrades pending ones to confirmed.",
        "why": "anchor.py has stamped the tip hourly since July and nothing "
               "served the proofs, so external anchoring was a claim rather "
               "than something a third party could check.",
        "pending_vs_confirmed": {
            "pending": "Written when a calendar accepts the digest. A promise "
                       "to commit it to Bitcoin. NOT evidence of anything on "
                       "chain yet.",
            "confirmed": "Carries the full path from digest to a Bitcoin "
                         "block header. Verifiable by anyone against the "
                         "blockchain, with nothing from us.",
            "the_gap": "A proof does not become confirmed on its own. It must "
                       "be upgraded - fetched again from the calendar after "
                       "its transaction lands. This module does that on a "
                       "timer, newest and oldest together, skipping ones "
                       "already done.",
        },
        "routes": {
            "status": "https://sebbi.pro/x/ots/status",
            "list": "https://sebbi.pro/x/ots/list",
            "proof": "https://sebbi.pro/x/ots/proof?ts=<stamp_id>",
            "latest_confirmed": "https://sebbi.pro/x/ots/latest_confirmed",
            "spec": "https://sebbi.pro/x/ots/spec",
            "upgrade": "POST, keyed. asks the calendars to complete pending "
                       "proofs.",
        },
        "verifying_without_us": [
            "base64 -d the ots_base64 field into tip.ots",
            "printf '%s' <tip> | xxd -r -p > tip.bin",
            "ots verify -f tip.bin tip.ots",
            "pip install opentimestamps-client - no code of ours involved",
        ],
        "what_this_does_not_prove": [
            "That the records under the tip are true. It fixes when a hash "
            "existed, nothing else.",
            "Anything about blocks sealed since the last anchor. Anchoring is "
            "hourly, so the most recent hour rests on peer witnessing.",
            "That a pending proof will confirm. Calendars are free public "
            "infrastructure and can fail.",
        ],
        "storage_warning": "Proofs live at %s. On Railway that is only "
                           "durable with a persistent volume mounted there. "
                           "https://sebbi.pro/x/ots/status reports what is "
                           "present." % ANCHOR_DIR,
    }


try:
    _start_auto()
except Exception as exc:
    print("OTS: could not start auto-upgrade: %s" % exc, flush=True)


def handle(method, action, data, api_key, ctx):
    data = data or {}
    if action == "spec":
        return _spec(), 200
    if action in ("status", ""):
        return _status()
    if action == "list":
        return _list(data)
    if action == "proof":
        return _proof(data)
    if action == "latest_confirmed":
        return _latest_confirmed(ctx)
    if action == "upgrade":
        if not api_key:
            return {"ok": False, "error": "api_key_required"}, 401
        return _upgrade(data)
    return {"ok": False, "error": "unknown_action", "action": action}, 404
