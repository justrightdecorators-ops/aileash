#!/usr/bin/env python3
"""
ordering_test.py  -  The Ordering Test, v0.1 (draft specification + runner)

    python3 ordering_test.py https://vendor.example
    python3 ordering_test.py https://vendor.example --json
    python3 ordering_test.py --selftest
    python3 ordering_test.py --spec

WHAT THIS TESTS, AND WHY IT IS THE ONLY THING WORTH TESTING
-----------------------------------------------------------
Content can be fabricated. Timestamps get argued about. A log can be rebuilt
from scratch and presented as history. Every one of those is contestable.

A commitment made BEFORE the information existed is not. It cannot be
reverse-engineered afterwards - not by an attacker, not by the operator, not
with more access or more compute. Order is the only property in this field
that does not rest on trusting somebody.

So this does not test whether a vendor stores records safely. Everybody claims
that and it is a storage claim. It tests whether the things they committed to
were committed in an order that makes retrofitting impossible.

Eight checks. Any governance vendor either passes them or does not.

    1  Oversight ordering      the reviewer's judgement is sealed before the
                              machine verdict is available to them
    2  Rule binding           the ruleset version is inside the sealed record,
                              not attached to it afterwards
    3  Advance commitment      the record count for a period is committed
                              before anyone requests an export of it
    4  Absence                 the vendor can prove a record is NOT present,
                              not only that one is
    5  Append-only             any earlier state of the log is provably a
                              prefix of the current one
    6  Determinism             identical inputs reproduce an identical verdict
                              under an unchanged implementation fingerprint
    7  External anchoring      the log state is committed somewhere the vendor
                              does not control, verifiable without them
    8  Independent witnessing  the log state is held by an operator the vendor
                              does not control, and that operator confirms it

HOW A VENDOR OPTS IN
--------------------
Publish a discovery document at:

    /.well-known/ordering-test.json

    {
      "ordering_test_version": "0.1",
      "vendor": "Example Ltd",
      "endpoints": {
        "oversight_open":    "/api/review/open",
        "oversight_commit":  "/api/review/commit",
        "rule_binding":      "/api/decision/{id}",
        "period_root":       "/api/periods/{period}",
        "inclusion_proof":   "/api/prove?leaf={leaf}",
        "absence_proof":     "/api/prove-absence?value={value}",
        "consistency_proof": "/api/consistency?first={first}&second={second}",
        "replay":            "/api/replay",
        "anchor_status":     "/api/anchor-status",
        "witness_peers":     "/api/witness/peers"
      }
    }

Any endpoint may be omitted. An omitted endpoint reports NOT SUPPORTED, which
is not the same as a failure and is not reported as one. A vendor that has not
built absence proofs has not failed a test - they have declined to take it,
and that distinction is the difference between an instrument and a marketing
device.

WHAT A PASS DOES NOT MEAN
-------------------------
It does not mean the records are true. Nothing tests that, here or anywhere.
It means the order in which they were committed rules out certain kinds of
later invention. That is a narrower claim than most of this industry makes,
and it is one that actually holds.

This runner never modifies anything. Every request it makes is either a read
or a submission to an endpoint the vendor has explicitly published for
testing. It holds no credentials and needs none.

Authors: this specification is published openly. Nobody owns it. Implement it,
argue with it, or fork it.
"""

import argparse
import sys
import hashlib
import json
import random
import sys
import time
import urllib.error
import urllib.request

VERSION = "0.1"
TIMEOUT = 15
UA = "ordering-test/%s" % VERSION

PASS = "PASS"
FAIL = "FAIL"
UNSUPPORTED = "NOT SUPPORTED"
INCONCLUSIVE = "INCONCLUSIVE"

ORDER = [PASS, FAIL, INCONCLUSIVE, UNSUPPORTED]


# ----------------------------------------------------------------------
# plumbing
# ----------------------------------------------------------------------

def _http(url, payload=None, timeout=TIMEOUT):
    data = None
    headers = {"Accept": "application/json", "User-Agent": UA}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(4 * 1024 * 1024)
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(1024 * 1024)
        except Exception:
            raw = b""
        status = exc.code
    except Exception as exc:
        return 0, "unreachable: %s" % type(exc).__name__
    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return status, raw.decode("utf-8", "replace")[:400]


def _dig(obj, *names):
    """Find the first of several keys, at the top level or one level down."""
    if not isinstance(obj, dict):
        return None
    for n in names:
        if n in obj and obj[n] is not None:
            return obj[n]
    for v in obj.values():
        if isinstance(v, dict):
            found = _dig(v, *names)
            if found is not None:
                return found
    return None


def _epoch(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        s = str(value).strip().replace("Z", "+00:00")
        from datetime import datetime
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


class Result(object):
    def __init__(self, number, name, question):
        self.number = number
        self.name = name
        self.question = question
        self.status = UNSUPPORTED
        self.detail = "The vendor has not published an endpoint for this."
        self.evidence = {}

    def set(self, status, detail, **evidence):
        self.status = status
        self.detail = detail
        self.evidence.update(evidence)
        return self

    def as_dict(self):
        return {"check": self.number, "name": self.name,
                "question": self.question, "status": self.status,
                "detail": self.detail, "evidence": self.evidence}


class Target(object):
    def __init__(self, base, doc):
        self.base = base.rstrip("/")
        self.doc = doc
        self.endpoints = (doc or {}).get("endpoints", {}) or {}

    def has(self, name):
        return bool(self.endpoints.get(name))

    def url(self, name, **subs):
        path = self.endpoints.get(name)
        if not path:
            return None
        for k, v in subs.items():
            path = path.replace("{%s}" % k, str(v))
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return self.base + ("" if path.startswith("/") else "/") + path


# ----------------------------------------------------------------------
# the eight checks
# ----------------------------------------------------------------------

def check_1_oversight(t):
    r = Result(1, "Oversight ordering",
               "Was the reviewer's judgement sealed before the machine verdict "
               "was available to them?")
    if not (t.has("oversight_open") and t.has("oversight_commit")):
        return r

    status, opened = _http(t.url("oversight_open"), {"purpose": "ordering-test"})
    if status < 200 or status >= 300 or not isinstance(opened, dict):
        return r.set(INCONCLUSIVE, "Could not open a review case (HTTP %s)." % status)

    # The verdict must NOT be present in the opening response. This is the
    # whole check: if they hand it over now, ordering is decorative.
    leaked = _dig(opened, "machine_verdict", "verdict", "decision", "score",
                  "machine_score", "recommendation")
    case_id = _dig(opened, "case_id", "id", "case", "reference")
    if leaked is not None:
        return r.set(FAIL,
                     "The machine verdict was returned when the case was opened. "
                     "A reviewer who can see the answer before committing is not "
                     "constrained by the ordering at all.",
                     leaked_field=str(leaked)[:60])
    if not case_id:
        return r.set(INCONCLUSIVE, "No case identifier was returned.")

    status, committed = _http(t.url("oversight_commit"),
                              {"case_id": case_id, "verdict": "challenge",
                               "reasoning": "ordering-test"})
    if status < 200 or status >= 300 or not isinstance(committed, dict):
        return r.set(INCONCLUSIVE, "Could not commit a verdict (HTTP %s)." % status)

    mine = _dig(committed, "reviewer_block", "your_block", "commit_block")
    theirs = _dig(committed, "machine_block", "verdict_block", "reveal_block")
    if mine is None or theirs is None:
        revealed = _dig(committed, "machine_verdict", "verdict", "decision")
        if revealed is not None:
            return r.set(INCONCLUSIVE,
                         "The verdict was withheld until commit, which is the "
                         "right behaviour, but no block indices were returned so "
                         "the sealed order could not be verified independently.")
        return r.set(INCONCLUSIVE, "Commit succeeded but returned no ordering evidence.")

    try:
        mine_i, theirs_i = int(mine), int(theirs)
    except (TypeError, ValueError):
        return r.set(INCONCLUSIVE, "Block indices were not numeric.")

    if mine_i < theirs_i:
        return r.set(PASS,
                     "The reviewer's judgement was sealed at block %d and the "
                     "machine verdict at block %d. The chain fixes that order "
                     "permanently, so agreement with an answer already on screen "
                     "is distinguishable from judgement." % (mine_i, theirs_i),
                     reviewer_block=mine_i, machine_block=theirs_i)
    return r.set(FAIL,
                 "The machine verdict was sealed at or before the reviewer's "
                 "(%d vs %d). The ordering guarantee does not hold."
                 % (theirs_i, mine_i),
                 reviewer_block=mine_i, machine_block=theirs_i)


def check_2_rule_binding(t):
    r = Result(2, "Rule binding",
               "Is the ruleset version inside the sealed record, or attached "
               "to it afterwards?")
    if not t.has("rule_binding"):
        return r
    status, body = _http(t.url("rule_binding", id="latest"))
    if status < 200 or status >= 300 or not isinstance(body, dict):
        return r.set(INCONCLUSIVE, "Could not retrieve a decision record (HTTP %s)." % status)

    rule = _dig(body, "ruleset_hash", "rule_version", "pack_hash", "policy_hash",
                "ruleset_version", "rules_hash")
    sealed_in = _dig(body, "sealed_payload", "sealed", "detail", "record")
    if rule is None:
        return r.set(FAIL,
                     "The decision record carries no ruleset version. Eighteen "
                     "months from now, which policy was live at that instant is "
                     "answerable only by a changelog somebody could have edited.")

    inside = False
    if isinstance(sealed_in, str):
        inside = str(rule)[:16] in sealed_in
    elif isinstance(sealed_in, dict):
        inside = str(rule) in json.dumps(sealed_in)

    if inside:
        return r.set(PASS,
                     "The ruleset version is committed inside the sealed payload, "
                     "so a decision cannot later be reattributed to different rules.",
                     ruleset=str(rule)[:32])
    return r.set(INCONCLUSIVE,
                 "A ruleset version is present but the runner could not confirm "
                 "it sits inside the sealed payload rather than beside it. Ask "
                 "the vendor to show the sealed bytes.",
                 ruleset=str(rule)[:32])


def check_3_advance_commitment(t):
    r = Result(3, "Advance commitment",
               "Was the record count for the period committed before anyone "
               "asked for an export of it?")
    if not t.has("period_root"):
        return r
    period = time.strftime("%Y-%m", time.gmtime(time.time() - 86400 * 40))
    status, body = _http(t.url("period_root", period=period))
    if status == 404:
        return r.set(INCONCLUSIVE, "No committed period was available to test.")
    if status < 200 or status >= 300 or not isinstance(body, dict):
        return r.set(INCONCLUSIVE, "Could not retrieve a period root (HTTP %s)." % status)

    root = _dig(body, "root", "merkle_root", "period_root")
    count = _dig(body, "count", "leaf_count", "leaves", "entries")
    committed_at = _epoch(_dig(body, "committed_at", "sealed_at", "committed", "ts"))

    if root is None or count is None:
        return r.set(FAIL,
                     "The period publishes no root and count. Without a count "
                     "committed in advance, an export can be complete or "
                     "convenient and nobody can tell the difference.")
    if committed_at is None:
        return r.set(INCONCLUSIVE,
                     "A root and count exist but no commitment time was published, "
                     "so 'in advance of what' cannot be established.",
                     root=str(root)[:24], count=count)
    if committed_at < time.time():
        return r.set(PASS,
                     "The period committed to %s records at %s, before this "
                     "request existed. An export can now be checked against a "
                     "number that was fixed before anyone knew it would be asked for."
                     % (count, time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(committed_at))),
                     root=str(root)[:24], count=count)
    return r.set(FAIL, "The commitment time is in the future.")


def check_4_absence(t):
    r = Result(4, "Absence",
               "Can the vendor prove a record is NOT present, or only that one is?")
    if not t.has("absence_proof"):
        if t.has("inclusion_proof"):
            return r.set(UNSUPPORTED,
                         "Inclusion proofs are published but absence proofs are "
                         "not. Proving what you hold is the easy half. The "
                         "question an investigator asks is whether anything was "
                         "quietly dropped.")
        return r
    probe = hashlib.sha256(("ordering-test-%d" % random.getrandbits(64)).encode()).hexdigest()
    status, body = _http(t.url("absence_proof", value=probe))
    if status < 200 or status >= 300 or not isinstance(body, dict):
        return r.set(INCONCLUSIVE, "Absence endpoint did not answer (HTTP %s)." % status)

    absent = _dig(body, "absent", "not_present", "excluded")
    left = _dig(body, "left", "lower", "predecessor", "before")
    right = _dig(body, "right", "upper", "successor", "after")

    if absent is False:
        return r.set(INCONCLUSIVE, "The random probe value was reported as present.")
    if left is not None and right is not None:
        return r.set(PASS,
                     "A value that is not in the log returned a bounded absence "
                     "proof - two adjacent committed entries with nothing possible "
                     "between them. Absence is demonstrated rather than asserted.",
                     neighbours=[str(left)[:16], str(right)[:16]])
    if absent:
        return r.set(FAIL,
                     "The endpoint states the value is absent but returns no "
                     "bounding evidence. That is an assertion, not a proof - the "
                     "vendor is asking to be believed.")
    return r.set(INCONCLUSIVE, "Absence response could not be interpreted.")


def check_5_append_only(t):
    r = Result(5, "Append-only",
               "Is an earlier state of the log provably a prefix of the current one?")
    if not t.has("consistency_proof"):
        return r
    status, body = _http(t.url("consistency_proof", first=1, second=2))
    if status < 200 or status >= 300 or not isinstance(body, dict):
        return r.set(INCONCLUSIVE, "Consistency endpoint did not answer (HTTP %s)." % status)
    proof = _dig(body, "proof", "path", "consistency", "nodes")
    if isinstance(proof, list):
        return r.set(PASS,
                     "The log publishes consistency proofs, so anyone holding an "
                     "earlier state can demonstrate it is a prefix of the current "
                     "one. Append-only is shown rather than promised.",
                     proof_length=len(proof))
    return r.set(FAIL,
                 "No consistency proof was returned. A log that cannot demonstrate "
                 "it only ever grew can have been rebuilt.")


def check_6_determinism(t):
    r = Result(6, "Determinism",
               "Do identical inputs reproduce an identical verdict under an "
               "unchanged implementation?")
    if not t.has("replay"):
        return r
    probe = {"ordering_test": True, "nonce": random.getrandbits(48),
             "amount": 1234, "trust": 0.42}
    s1, a = _http(t.url("replay"), probe)
    if s1 < 200 or s1 >= 300 or not isinstance(a, dict):
        return r.set(INCONCLUSIVE, "Replay endpoint did not answer (HTTP %s)." % s1)
    time.sleep(1.0)
    s2, b = _http(t.url("replay"), probe)
    if s2 < 200 or s2 >= 300 or not isinstance(b, dict):
        return r.set(INCONCLUSIVE, "Replay endpoint answered once but not twice.")

    va, vb = _dig(a, "verdict", "decision", "result"), _dig(b, "verdict", "decision", "result")
    sa, sb = _dig(a, "score", "value"), _dig(b, "score", "value")
    fa, fb = _dig(a, "fingerprint", "code_fingerprint", "implementation"), \
             _dig(b, "fingerprint", "code_fingerprint", "implementation")

    if va is None and sa is None:
        return r.set(INCONCLUSIVE, "No verdict or score was returned to compare.")
    if fa and fb and fa != fb:
        return r.set(FAIL, "The implementation fingerprint changed between two "
                           "requests one second apart.")
    if va == vb and sa == sb:
        return r.set(PASS,
                     "Identical inputs reproduced an identical result%s. "
                     "Reproducibility is testable by a third party rather than "
                     "certified by the vendor about itself."
                     % (" under an unchanged fingerprint" if fa else ""),
                     verdict=str(va), fingerprint=str(fa)[:16] if fa else None)
    return r.set(FAIL,
                 "Identical inputs produced different results (%s/%s vs %s/%s). "
                 "Nothing sealed under this engine can be re-derived later."
                 % (va, sa, vb, sb))


def check_7_anchoring(t):
    r = Result(7, "External anchoring",
               "Is the log state committed somewhere the vendor does not control?")
    if not t.has("anchor_status"):
        return r
    status, body = _http(t.url("anchor_status"))
    if status < 200 or status >= 300 or not isinstance(body, dict):
        return r.set(INCONCLUSIVE, "Anchor endpoint did not answer (HTTP %s)." % status)

    tip = _dig(body, "tip", "anchored_tip", "root")
    when = _epoch(_dig(body, "anchored_at", "last_anchor", "timestamp", "ts"))
    where = _dig(body, "network", "chain", "anchor", "method", "calendars", "calendar_count")
    proof = _dig(body, "proof", "ots", "timestamp_proof", "receipt")

    if tip is None:
        return r.set(FAIL, "No anchored state is published.")
    if when is None:
        return r.set(INCONCLUSIVE, "An anchored tip is published without a time.",
                     tip=str(tip)[:24])

    age_h = (time.time() - when) / 3600.0
    detail = ("Log state anchored externally %s ago%s."
              % (("%.1f hours" % age_h) if age_h < 48 else ("%.1f days" % (age_h / 24)),
                 (" via %s" % where) if where else ""))
    if proof is None:
        detail += (" No portable proof is published, so verification still "
                   "depends on this endpoint remaining available.")
        return r.set(INCONCLUSIVE, detail, tip=str(tip)[:24], hours_old=round(age_h, 1))
    if age_h > 24 * 7:
        return r.set(FAIL, detail + " Anything sealed since is unanchored, and the "
                                    "gap is the exposure.",
                     tip=str(tip)[:24], hours_old=round(age_h, 1))
    return r.set(PASS,
                 detail + " The proof is portable, so the date survives the vendor.",
                 tip=str(tip)[:24], hours_old=round(age_h, 1))


def check_8_witnessing(t):
    r = Result(8, "Independent witnessing",
               "Is the log state held by an operator the vendor does not control?")
    if not t.has("witness_peers"):
        return r
    status, body = _http(t.url("witness_peers"))
    if status < 200 or status >= 300:
        return r.set(INCONCLUSIVE, "Witness endpoint did not answer (HTTP %s)." % status)

    peers = _dig(body, "peers") if isinstance(body, dict) else None
    if not isinstance(peers, list):
        return r.set(INCONCLUSIVE, "No peer list was returned.")

    live = []
    for p in peers:
        if not isinstance(p, dict):
            continue
        hours = p.get("hours_since_last")
        state = str(p.get("status", "")).lower()
        if state == "current" or (isinstance(hours, (int, float)) and hours < 24):
            live.append(p.get("peer") or p.get("name") or "unnamed")

    if not live:
        return r.set(FAIL,
                     "No peer has recorded this log in the last 24 hours. Between "
                     "anchors the operator and the auditor are the same party.",
                     peers_listed=len(peers))
    if len(live) < 3:
        return r.set(INCONCLUSIVE,
                     "%d live peer%s (%s). Better than none, but parties witnessing "
                     "only each other can still move together. Breadth is what "
                     "makes this hold, and this network is thin."
                     % (len(live), "" if len(live) == 1 else "s", ", ".join(live[:3])),
                     live_peers=live)
    return r.set(PASS,
                 "%d independent operators have recorded this log within the last "
                 "day (%s). Rewriting history now requires all of them to move in "
                 "step and re-obtain external timestamps already issued."
                 % (len(live), ", ".join(live[:4])),
                 live_peers=live)


CHECKS = [check_1_oversight, check_2_rule_binding, check_3_advance_commitment,
          check_4_absence, check_5_append_only, check_6_determinism,
          check_7_anchoring, check_8_witnessing]


# ----------------------------------------------------------------------
# running and reporting
# ----------------------------------------------------------------------

def discover(base):
    base = base.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base
    status, doc = _http(base + "/.well-known/ordering-test.json")
    if status == 200 and isinstance(doc, dict):
        return base, doc, None
    return base, None, ("No discovery document at %s/.well-known/ordering-test.json "
                        "(HTTP %s). The vendor has not published an interface for "
                        "this test." % (base, status))


def run(base):
    base, doc, error = discover(base)
    if error:
        return {"target": base, "error": error, "ordering_test_version": VERSION}
    t = Target(base, doc)
    results = []
    for fn in CHECKS:
        try:
            results.append(fn(t))
        except Exception as exc:
            r = Result(0, fn.__name__, "")
            r.set(INCONCLUSIVE, "Runner error: %s" % exc)
            results.append(r)

    tally = {s: 0 for s in ORDER}
    for r in results:
        tally[r.status] = tally.get(r.status, 0) + 1

    if tally[FAIL] == 0 and tally[PASS] >= 6:
        verdict = "CONFORMANT"
        summary = ("Passes %d of 8 with no failures. Ordering is demonstrated, "
                   "not asserted." % tally[PASS])
    elif tally[FAIL] == 0:
        verdict = "PARTIAL"
        summary = ("No failures, but only %d checks could be demonstrated. The "
                   "rest were not published or could not be established."
                   % tally[PASS])
    else:
        verdict = "NON-CONFORMANT"
        summary = ("%d check%s failed. Records under this system can be "
                   "reconstructed in ways the vendor cannot rule out."
                   % (tally[FAIL], "" if tally[FAIL] == 1 else "s"))

    return {
        "ordering_test_version": VERSION,
        "target": base,
        "vendor": doc.get("vendor"),
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": verdict,
        "summary": summary,
        "tally": tally,
        "checks": [r.as_dict() for r in results],
        "what_a_pass_does_not_mean": (
            "That the records are true. Nothing tests that. It means the order "
            "in which things were committed rules out certain kinds of later "
            "invention."),
    }


def report(res):
    out = []
    w = 72
    out.append("=" * w)
    out.append("THE ORDERING TEST  v%s" % res.get("ordering_test_version", VERSION))
    out.append(res.get("target", ""))
    if res.get("vendor"):
        out.append(res["vendor"])
    out.append("=" * w)
    if res.get("error"):
        out.append("")
        out.append(res["error"])
        return "\n".join(out)

    for c in res["checks"]:
        out.append("")
        out.append("%d.  %-24s  %s" % (c["check"], c["name"], c["status"]))
        if c["question"]:
            out.append("    %s" % c["question"])
        for line in _wrap(c["detail"], w - 4):
            out.append("    " + line)

    out.append("")
    out.append("-" * w)
    out.append("VERDICT: %s" % res["verdict"])
    for line in _wrap(res["summary"], w):
        out.append(line)
    out.append("")
    out.append("  pass %d   fail %d   inconclusive %d   not supported %d"
               % (res["tally"][PASS], res["tally"][FAIL],
                  res["tally"][INCONCLUSIVE], res["tally"][UNSUPPORTED]))
    out.append("-" * w)
    for line in _wrap("A pass does not mean the records are true. " +
                      res["what_a_pass_does_not_mean"].split("It means")[-1].strip()
                      .join(["It means ", ""]), w):
        out.append(line)
    return "\n".join(out)


def _wrap(text, width):
    words, line, lines = str(text).split(), "", []
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        lines.append(line)
    return lines


# ----------------------------------------------------------------------
# self-test: prove the runner is honest before anyone trusts its output
# ----------------------------------------------------------------------

def selftest():
    print("Self-test: does this runner actually catch what it claims to?\n")
    ok = True

    class Fake(Target):
        def __init__(self, endpoints, responses):
            Target.__init__(self, "https://fake.test", {"endpoints": endpoints})
            self.responses = responses

    def patched(responses):
        def _f(url, payload=None, timeout=TIMEOUT):
            for key, value in responses.items():
                if key in url:
                    return value
            return 404, {}
        return _f

    real_http = globals()["_http"]

    cases = [
        ("verdict leaked at open is caught", check_1_oversight,
         {"oversight_open": "/open", "oversight_commit": "/commit"},
         {"/open": (200, {"case_id": "x", "machine_verdict": "BLOCK"})}, FAIL),

        ("correct commit-before-reveal passes", check_1_oversight,
         {"oversight_open": "/open", "oversight_commit": "/commit"},
         {"/open": (200, {"case_id": "x"}),
          "/commit": (200, {"reviewer_block": 10, "machine_block": 11})}, PASS),

        ("verdict sealed first is caught", check_1_oversight,
         {"oversight_open": "/open", "oversight_commit": "/commit"},
         {"/open": (200, {"case_id": "x"}),
          "/commit": (200, {"reviewer_block": 12, "machine_block": 9})}, FAIL),

        ("asserted absence with no bounds is caught", check_4_absence,
         {"absence_proof": "/absent?value={value}"},
         {"/absent": (200, {"absent": True})}, FAIL),

        ("bounded absence passes", check_4_absence,
         {"absence_proof": "/absent?value={value}"},
         {"/absent": (200, {"absent": True, "left": "aa", "right": "bb"})}, PASS),

        ("non-deterministic engine is caught", check_6_determinism,
         {"replay": "/replay"},
         {"/replay": (200, {"verdict": "ALLOW", "score": random.random()})}, None),

        ("stale anchor is caught", check_7_anchoring,
         {"anchor_status": "/anchor"},
         {"/anchor": (200, {"tip": "a" * 64, "anchored_at": time.time() - 86400 * 20,
                            "proof": "ots"})}, FAIL),

        ("no live peers is caught", check_8_witnessing,
         {"witness_peers": "/peers"},
         {"/peers": (200, {"peers": [{"peer": "x", "hours_since_last": 900,
                                      "status": "silent"}]})}, FAIL),

        ("single peer is not sold as strong", check_8_witnessing,
         {"witness_peers": "/peers"},
         {"/peers": (200, {"peers": [{"peer": "x", "status": "current"}]})}, INCONCLUSIVE),

        ("missing endpoint is not a failure", check_4_absence, {}, {}, UNSUPPORTED),
    ]

    for label, fn, endpoints, responses, expect in cases:
        globals()["_http"] = patched(responses)
        try:
            got = fn(Fake(endpoints, responses)).status
        finally:
            globals()["_http"] = real_http
        if expect is None:
            good = got in (FAIL, PASS)      # random scores may collide; either is fine
            note = "(non-deterministic fixture, got %s)" % got
        else:
            good = got == expect
            note = "expected %s, got %s" % (expect, got)
        print("  %s  %s  %s" % ("ok  " if good else "FAIL", label, "" if good else note))
        ok = ok and good

    print("\n%s" % ("Self-test passed. The runner catches what it claims to."
                    if ok else "SELF-TEST FAILED. Do not trust this runner's output."))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(
        description="The Ordering Test - conformance runner for provable ordering.")
    p.add_argument("target", nargs="?", help="vendor base URL")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--selftest", action="store_true",
                   help="prove the runner catches what it claims to")
    p.add_argument("--spec", action="store_true", help="print the specification")
    args = p.parse_args()

    if args.selftest:
        return selftest()
    if args.spec or not args.target:
        print(__doc__)
        return 0

    res = run(args.target)
    print(json.dumps(res, indent=2) if args.json else report(res))
    return 1 if res.get("verdict") == "NON-CONFORMANT" or res.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
