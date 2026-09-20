"""
modules/integrity.py  v1.3.1  -  the AI Integrity Declaration, and a public checker

Serves the open standard that rates every AI deployment from L0_DIARY
(no checkable record) up to L4_OVERSIGHT_VERIFIED, and checks any domain
against it. Reads only. Seals nothing, writes nothing, creates no tables.
Every route is public.

Routes:
  https://sebbi.pro/x/integrity/status                    what this is
  https://sebbi.pro/x/integrity/declaration               the standard, as JSON
  https://sebbi.pro/x/integrity/self                      sebbi.pro's own declaration
  https://sebbi.pro/x/integrity/check?domain=example.com  rate any domain

HOW THE CHECKER DECIDES
It looks for a declaration at https://<domain>/.well-known/ai-integrity.json,
then https://<domain>/x/integrity/self. None found: L0_DIARY.
It never takes the declaration's word. It walks the declared chain and
recomputes every public block itself, asks each declared witness for its
tip, and opens each anchor proof. A level is awarded only when every check
that level needs has passed. Claiming more than that is OVERCLAIMED.

Human-oversight checks (INV-005, INV-006) cannot be tested from outside yet,
so this checker never awards L4. It says so rather than guessing.

SAFETY
The checker fetches addresses taken from other people's declarations, so
it only fetches https on port 443, refuses redirects, refuses any host that
resolves to a private, loopback or internal address, caps every response
size and every timeout, and caps the number of fetches per check.
"""

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

VERSION = "1.3.1"
BASE = "https://sebbi.pro/x/integrity/"

PUBLIC = {("GET", "status"), ("GET", "declaration"), ("GET", "spec"),
          ("GET", "self"), ("GET", "check")}

# ---------------------------------------------------------------- the standard

DECLARATION = json.loads(r'''{
  "spec": "ai-integrity-declaration",
  "version": "1.0.2",
  "declaration_id": "DEC-2026-AI-INTEGRITY",
  "status": "open_standard",
  "published": "2026-09-19",
  "issuer": {
    "name": "Monop Content",
    "product": "sebbi.pro",
    "url": "https://sebbi.pro"
  },
  "principle": "A record kept only by the party it describes is a diary, not evidence. Any AI deployment can be checked against this standard by anyone, without an account, a key, or permission.",
  "scope": "Autonomous agents and AI systems that make or support decisions affecting people, money, access or safety.",
  "maps_to": [
    {
      "framework": "EU AI Act",
      "provisions": [
        "Article 12 record-keeping",
        "Article 14 human oversight"
      ]
    },
    {
      "framework": "UK Online Safety Act 2023",
      "provisions": [
        "record-keeping and review duties"
      ]
    },
    {
      "framework": "ICO Age Appropriate Design Code",
      "provisions": [
        "data minimisation",
        "transparency"
      ]
    }
  ],
  "related": {
    "ordering_test": "https://sebbi.pro/.well-known/ordering-test.json",
    "relationship": "The Ordering Test lists which checks a vendor supports and which anyone can run without an account. This declaration turns those checks into levels, so every AI deployment gets a rating whether or not it publishes."
  },
  "discovery": {
    "paths": [
      "/.well-known/ai-integrity.json",
      "/x/integrity/self"
    ],
    "rule": "Every AI deployment is rated. A verifier looks for a declaration at each path in order, over HTTPS, on the deployment's own domain. A deployment with no declaration at any of these paths is rated L0_DIARY. Absence is itself the result.",
    "absence_verdict": "L0_DIARY"
  },
  "levels": {
    "L0_DIARY": {
      "badge": "GREY",
      "meaning": "No public, independently checkable record. The operator's word is the only evidence.",
      "requires": []
    },
    "L1_SEALED": {
      "badge": "BRONZE",
      "meaning": "Every decision is sealed into a public append-only chain that anyone can walk and recompute.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-007"
      ]
    },
    "L2_WITNESSED": {
      "badge": "SILVER",
      "meaning": "Independent parties hold the chain's fingerprints, so the operator cannot rewrite history unnoticed.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-003",
        "INV-007"
      ]
    },
    "L3_ANCHORED": {
      "badge": "GOLD",
      "meaning": "The chain is also anchored to a public timestamp no single party controls.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-003",
        "INV-004",
        "INV-007"
      ]
    },
    "L4_OVERSIGHT_VERIFIED": {
      "badge": "GOLD_LIVE_VERIFIED",
      "meaning": "Human oversight is itself provable: reviewers commit before seeing the machine, and rubber-stamping is detected.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-003",
        "INV-004",
        "INV-005",
        "INV-006",
        "INV-007"
      ]
    }
  },
  "invariants": {
    "INV-001-SEALED-CHAIN": {
      "requirement": "Every decision is sealed at the moment it is made, with what it rested on, into an append-only hash chain.",
      "test": "Fetch the declared walk endpoint. Starting from genesis, recompute every public block from the served preimage and confirm each block names its parent.",
      "pass": "All public blocks recompute; all links unbroken; the tip reached equals the tip published.",
      "fail_verdict": "L0_DIARY"
    },
    "INV-002-FINGERPRINTS-ONLY": {
      "requirement": "Raw prompts, documents and personal data stay with their owner. Only fingerprints are published. Short or guessable personal values are salted or keyed before hashing.",
      "test": "Inspect public blocks. No raw personal data, secrets or credentials appear. The declaration states the hashing method for personal values.",
      "pass": "No raw personal data in any public block; method declared.",
      "fail_verdict": "L0_DIARY"
    },
    "INV-003-INDEPENDENT-WITNESS": {
      "requirement": "At least one party independent of the operator holds the chain's tip. The declaration states how many independent parties would have to collude or fail at the same time for the history to be rewritten unnoticed.",
      "independence": "A witness is independent when the operator cannot alter, delete or withhold the witness's record of the tip. Payment does not by itself break independence; control does. Any commercial relationship between operator and witness is disclosed in the declaration.",
      "test": "Query each declared witness. Its recorded tip must appear in the operator's chain at the position it claims.",
      "pass": "At least one independent witness confirms; the collusion threshold is disclosed.",
      "fail_verdict": "L1_SEALED"
    },
    "INV-004-PUBLIC-TIME-ANCHOR": {
      "requirement": "Chain tips are anchored to a public timestamp no single party controls, such as OpenTimestamps on Bitcoin.",
      "test": "Verify the anchor proof offline against the tip it names.",
      "pass": "Proof commits to a tip present in the chain.",
      "fail_verdict": "L2_WITNESSED"
    },
    "INV-005-COMMIT-BEFORE-REVEAL": {
      "requirement": "Where a human reviews an AI decision, the reviewer's verdict is sealed before the machine's verdict is shown to them.",
      "test": "For each reviewed case, the reviewer's sealed commitment sits in an earlier block than the reveal of the machine verdict.",
      "pass": "Every reviewed case shows commit before reveal.",
      "fail_verdict": "L3_ANCHORED"
    },
    "INV-006-ANTI-RUBBER-STAMP": {
      "requirement": "Review behaviour that indicates rubber-stamping is detected and sealed.",
      "parameters": {
        "minimum_review_seconds": 1.5,
        "maximum_agreement_rate": 0.98,
        "window": "rolling 30 days, per reviewer"
      },
      "test": "Any reviewer approving in under minimum_review_seconds, or agreeing with the machine more often than maximum_agreement_rate across the window, has a flag sealed into the chain.",
      "pass": "Flags are raised and sealed whenever the thresholds are crossed; the thresholds in use are declared.",
      "fail_verdict": "L3_ANCHORED"
    },
    "INV-007-DISCLOSED-DISCONTINUITY": {
      "requirement": "Where the chain is reset, or the meaning of a field or the referent of an identifier changes after records using it have been sealed, the change is sealed into the record itself with the date it took effect. Records sealed under the earlier meaning remain valid under that meaning and are never silently repaired.",
      "test": "Every discontinuity or change of meaning is disclosed either as a block sealed in the chain, or in the declaration with the kind of change and the evidence a verifier can use to detect it. Where the checker can detect a discontinuity itself (for example records sealed long after the window they cover), an undisclosed one fails.",
      "pass": "Every discontinuity is disclosed in the chain.",
      "fail_verdict": "L0_DIARY"
    }
  },
  "verifier_rules": [
    "Never accept an operator's own statement that its record is valid. Recompute.",
    "A verifier assigns the highest level whose every required invariant passes.",
    "If a declaration claims a higher level than verification supports, the verdict is OVERCLAIMED, shown alongside the verified level.",
    "A declaration that cannot be fetched, or cannot be parsed, is rated L0_DIARY."
  ],
  "declaration_template": {
    "spec": "ai-integrity-declaration",
    "version": "1.0.0",
    "organisation": "",
    "system": "",
    "claimed_level": "",
    "chain": {
      "walk_endpoint": "",
      "genesis_hash": "",
      "seal_method_url": ""
    },
    "personal_data_hashing": "",
    "witnesses": [
      {
        "name": "",
        "tip_endpoint": ""
      }
    ],
    "collusion_threshold": 0,
    "anchor": {
      "method": "",
      "proof_endpoint": ""
    },
    "oversight": {
      "commit_before_reveal": false,
      "anti_rubber_stamp": {
        "minimum_review_seconds": 1.5,
        "maximum_agreement_rate": 0.98
      }
    },
    "discontinuities": [
      {
        "date": "",
        "disclosure_block": "",
        "kind": "",
        "detail": ""
      }
    ],
    "known_gaps": []
  },
  "not_yet_rated": {
    "availability": "Every level answers 'has this been altered'. None yet answers 'will this still be served'. Until a level for availability is defined, declare availability limits in known_gaps."
  },
  "reference_implementation": {
    "name": "sebbi.pro",
    "walk": "https://sebbi.pro/x/walk/status",
    "method": "https://sebbi.pro/x/walk/spec",
    "genesis": "https://sebbi.pro/x/walk/genesis",
    "discontinuity_example": "https://sebbi.pro/x/walk/block?index=2013"
  },
  "changelog": [
    {
      "version": "1.0.1",
      "date": "2026-09-20",
      "change": "Added /x/integrity/self as a second discovery path, for deployments whose server cannot serve /.well-known. Added the public checker."
    },
    {
      "version": "1.0.2",
      "date": "2026-09-20",
      "change": "Defined witness independence (control, not payment). INV-007 accepts discontinuities disclosed in the declaration with detection evidence, and fails undisclosed ones the checker can detect. Added known_gaps and the unrated availability axis. All three raised by Richard Whitney (MIRegistry) while writing the first external declaration."
    }
  ],
  "public_checker": "https://sebbi.pro/x/integrity/check?domain=example.com"
}''')

_CANONICAL = json.dumps(DECLARATION, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False)
DECLARATION_SHA256 = hashlib.sha256(_CANONICAL.encode("utf-8")).hexdigest()

# ---------------------------------------------------------------- our own declaration
#
# sebbi.pro's own claim. Kept honest: it claims only what the checker can
# confirm today. To move up a level, add a witness below - an address run
# by someone else that returns the sebbi.pro tip they hold - and raise
# claimed_level only once the checker agrees.

SELF_WITNESSES = [
    {"name": "MIR (MIRegistry)",
     "tip_endpoint": "https://mir.events/v1/transparency/held/tips?peer=sebbi",
     "note": "MIR records each sebbi.pro tip it observes against its own "
             "anchored chain position and never refreshes an entry. As MIR "
             "states in its own payload, these observations are bound to an "
             "anchored MIR tip, not sealed inside MIR's merkle root."},
    {"name": "Red Flag AI Pro",
     "tip_endpoint": "https://www.redflagaipro.com/",
     "note": "Red Flag's public witness page publishes the receipt for each "
             "exchange, including the sebbi.pro block hash it was sealed in."},
]

SELF = {
    "spec": "ai-integrity-declaration",
    "version": "1.0.2",
    "organisation": "Monop Content",
    "system": "sebbi.pro",
    "claimed_level": "L1_SEALED",
    "chain": {
        "walk_endpoint": "https://sebbi.pro/x/walk/blocks",
        "genesis_hash": "534f9e5cefb1a48566674911262151f34eedc1e6840a094d9465af4d846972c6",
        "seal_method_url": "https://sebbi.pro/x/walk/spec",
    },
    "personal_data_hashing": "Customer decisions are never published. Blocks sealed under a customer key, from non-public sources, or carrying anything secret-shaped are served without payload; only their hash and link are public.",
    "witnesses": SELF_WITNESSES,
    "collusion_threshold": len(SELF_WITNESSES),
    "anchor": {
        "method": "OpenTimestamps on Bitcoin",
        "proof_endpoint": "",
        "status_url": "https://sebbi.pro/x/ots/status",
    },
    "oversight": {
        "commit_before_reveal": True,
        "demonstration": "https://sebbi.pro/x/demo/review",
        "anti_rubber_stamp": {"minimum_review_seconds": 1.5,
                              "maximum_agreement_rate": 0.98},
    },
    "discontinuities": [
        {"date": "2026-09-07", "disclosure_block": 2013},
    ],
}

# ---------------------------------------------------------------- safe fetching

FETCH_TIMEOUT = 8
MAX_DECL_BYTES = 262144
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_FETCHES = 45
WALK_PAGE = 500
WALK_MAX_BLOCKS = 20000
CHECK_BUDGET_SECONDS = 60
CACHE_SECONDS = 600
USER_AGENT = "sebbi-integrity-checker/1.3.1 (+https://sebbi.pro/x/integrity/status)"

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home",
                     ".corp", ".intranet", ".arpa")

_cache = {}
_cache_lock = threading.Lock()
_running = threading.BoundedSemaphore(2)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code,
                                     "redirect refused", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


class _Budget(object):
    def __init__(self):
        self.fetches = 0
        self.deadline = time.time() + CHECK_BUDGET_SECONDS

    def spend(self):
        self.fetches += 1
        if self.fetches > MAX_FETCHES:
            raise RuntimeError("fetch limit reached")
        if time.time() > self.deadline:
            raise RuntimeError("time limit reached")


def _clean_domain(raw):
    d = str(raw or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d)
    d = d.split("/")[0].split("?")[0].split("#")[0]
    if "@" in d or ":" in d:
        return None
    d = d.rstrip(".")
    if not _HOST_RE.match(d):
        return None
    if d == "localhost" or d.endswith(_BLOCKED_SUFFIXES):
        return None
    return d


def _host_is_public(host):
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except Exception:
        return False, "does not resolve"
    if not infos:
        return False, "does not resolve"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, "unreadable address"
        if (ip.is_private or ip.is_loopback or ip.is_link_local or
                ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False, "resolves to a non-public address"
    return True, None


def _safe_url(url):
    try:
        p = urllib.parse.urlsplit(str(url))
    except Exception:
        return None, "unreadable address"
    if p.scheme != "https":
        return None, "only https addresses are fetched"
    if p.port not in (None, 443):
        return None, "only port 443 is fetched"
    if p.username or p.password:
        return None, "addresses with credentials are refused"
    host = _clean_domain(p.hostname or "")
    if not host:
        return None, "not a public domain name"
    ok, why = _host_is_public(host)
    if not ok:
        return None, why
    return urllib.parse.urlunsplit(("https", host, p.path or "/", p.query, "")), None


def _fetch_raw(url, budget, max_bytes=MAX_DECL_BYTES, accept="application/json"):
    """Returns (bytes, error). Never raises."""
    safe, why = _safe_url(url)
    if not safe:
        return None, why
    try:
        budget.spend()
    except RuntimeError as exc:
        return None, str(exc)
    req = urllib.request.Request(safe, headers={
        "User-Agent": USER_AGENT, "Accept": accept})
    try:
        with _OPENER.open(req, timeout=FETCH_TIMEOUT) as resp:
            raw = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        return None, "HTTP %s" % exc.code
    except Exception as exc:
        return None, "could not fetch (%s)" % exc.__class__.__name__
    if len(raw) > max_bytes:
        return None, "response too large"
    return raw, None


def _fetch_json(url, budget, max_bytes=MAX_DECL_BYTES, allow_text=False):
    """Returns (data, error). Never raises.

    allow_text: if the response is not JSON (an ordinary web page), return
    {"_text": <page text>} instead of an error, so a witness can publish its
    record as a normal page."""
    raw, err = _fetch_raw(url, budget, max_bytes)
    if err:
        return None, err
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text), None
    except Exception:
        if allow_text:
            return {"_text": text}, None
        return None, "not valid JSON"


# ---------------------------------------------------------------- checks

_HEX64 = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
WITNESS_MAX_BYTES = 2 * 1024 * 1024
_SECRET_SHAPES = [
    ("api key", re.compile(r"\b(?:al|sb|se)_live_[0-9a-f]{16,}")),
    ("api key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("cloud key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("access token", re.compile(r"\b(?:ghp|gho|xox[abp])[_-][A-Za-z0-9-]{10,}")),
    ("private key", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")),
    ("email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]


_ZERO64 = "0" * 64
BACKFILL_HOURS = 6


def _iso_ts(v):
    try:
        return time.mktime(time.strptime(str(v)[:19], "%Y-%m-%dT%H:%M:%S")) \
            - time.timezone
    except Exception:
        return None


def _walk(endpoint, budget):
    """Walk a declared chain and recompute it.

    Two published formats are understood:
      blocks       the sebbi.pro walk format (https://sebbi.pro/x/walk/spec)
      checkpoints  the MIR checkpoint format (seq/tip/prevTip, newest first)
    The format is detected from what the endpoint serves, never assumed."""
    first, err = _fetch_json(endpoint, budget, MAX_PAGE_BYTES)
    if err:
        out = _empty_walk(endpoint)
        out["first_problem"] = "could not read walk endpoint: %s" % err
        return out, {}, {}, {}
    if isinstance(first, dict) and isinstance(first.get("checkpoints"), list):
        return _walk_checkpoints(endpoint, first, budget)
    if isinstance(first, dict) and isinstance(first.get("blocks"), list):
        return _walk_blocks(endpoint, budget)
    out = _empty_walk(endpoint)
    out["first_problem"] = ("endpoint serves neither the blocks nor the "
                            "checkpoints walk format")
    return out, {}, {}, {}


def _empty_walk(endpoint):
    return {"endpoint": endpoint, "format": None, "blocks": 0,
            "public_recomputed": 0, "withheld_linkage_only": 0,
            "complete": False, "genesis_prev_is_GENESIS": None,
            "first_problem": None, "tip": None}


def _walk_blocks(endpoint, budget):
    out = _empty_walk(endpoint)
    out["format"] = "blocks"
    hashes = {}
    public_text = {}
    prev = "GENESIS"
    after = 0
    base = endpoint.split("?")[0]
    while True:
        url = "%s?after=%d&limit=%d" % (base, after, WALK_PAGE)
        page, err = _fetch_json(url, budget, MAX_PAGE_BYTES)
        if err:
            out["first_problem"] = out["first_problem"] or (
                "could not read page after block %d: %s" % (after, err))
            break
        blocks = page.get("blocks") if isinstance(page, dict) else None
        if not isinstance(blocks, list):
            out["first_problem"] = "endpoint does not serve the walk format"
            break
        if after == 0:
            first_prev = page.get("previous_audit_hash")
            out["genesis_prev_is_GENESIS"] = (first_prev == "GENESIS")
        for b in blocks:
            idx = b.get("block_index")
            h = str(b.get("audit_hash") or "")
            if "preimage" in b:
                pre = b.get("preimage")
                if not isinstance(pre, str) or \
                        hashlib.sha256(pre.encode("utf-8")).hexdigest() != h:
                    out["first_problem"] = out["first_problem"] or (
                        "block %s does not recompute" % idx)
                try:
                    stated_prev = json.loads(pre).get("prev_hash")
                except Exception:
                    stated_prev = None
                out["public_recomputed"] += 1
                public_text[idx] = pre
            else:
                stated_prev = b.get("prev_hash")
                out["withheld_linkage_only"] += 1
            if stated_prev != prev:
                out["first_problem"] = out["first_problem"] or (
                    "block %s does not link to the block before it" % idx)
            prev = h
            hashes[h] = idx
            out["blocks"] += 1
        if out["blocks"] >= WALK_MAX_BLOCKS:
            out["first_problem"] = out["first_problem"] or (
                "stopped at %d blocks; the checker walks at most %d"
                % (out["blocks"], WALK_MAX_BLOCKS))
            break
        if not page.get("has_more"):
            out["complete"] = True
            break
        nxt = page.get("next_after")
        if not isinstance(nxt, int) or nxt <= after:
            out["first_problem"] = out["first_problem"] or "paging did not advance"
            break
        after = nxt
    out["tip"] = prev if out["blocks"] else None
    return out, hashes, public_text, {}


def _walk_checkpoints(endpoint, first, budget):
    """MIR format: tip = sha256(seq:rangeStart:rangeEnd:eventCount:
    merkleRoot:prevTip), newest first, paged backwards with beforeSeq."""
    out = _empty_walk(endpoint)
    out["format"] = "checkpoints"
    base = endpoint.split("?")[0]
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(endpoint).query))
    limit = q.get("limit", "200")
    rows = {}
    page = first
    while True:
        cps = page.get("checkpoints") if isinstance(page, dict) else None
        if not isinstance(cps, list) or not cps:
            break
        for cp in cps:
            try:
                rows[int(cp.get("seq"))] = cp
            except (TypeError, ValueError):
                out["first_problem"] = out["first_problem"] or \
                    "a checkpoint has no readable seq"
        lowest = min(int(c.get("seq")) for c in cps
                     if str(c.get("seq", "")).lstrip("-").isdigit())
        if lowest <= 0:
            break
        if len(rows) >= WALK_MAX_BLOCKS:
            out["first_problem"] = out["first_problem"] or (
                "stopped at %d checkpoints; the checker walks at most %d"
                % (len(rows), WALK_MAX_BLOCKS))
            break
        url = "%s?limit=%s&beforeSeq=%d" % (base, limit, lowest)
        page, err = _fetch_json(url, budget, MAX_PAGE_BYTES)
        if err:
            out["first_problem"] = out["first_problem"] or (
                "could not read page before seq %d: %s" % (lowest, err))
            break

    hashes, public_text, meta = {}, {}, {}
    backfilled, backfill_through = 0, None
    prev = _ZERO64
    seqs = sorted(rows)
    if seqs and seqs[0] != 0:
        out["first_problem"] = out["first_problem"] or \
            "walk did not reach genesis (seq 0)"
    for n, seq in enumerate(seqs):
        cp = rows[seq]
        if n and seq != seqs[n - 1] + 1:
            out["first_problem"] = out["first_problem"] or \
                "gap in seq before %d" % seq
        tip = str(cp.get("tip") or "").lower()
        pre = ":".join([str(seq), str(cp.get("rangeStart")),
                        str(cp.get("rangeEnd")), str(cp.get("eventCount")),
                        str(cp.get("merkleRoot")), str(cp.get("prevTip"))])
        if hashlib.sha256(pre.encode("utf-8")).hexdigest() != tip:
            out["first_problem"] = out["first_problem"] or \
                "checkpoint %d does not recompute" % seq
        if str(cp.get("prevTip") or "").lower() != prev:
            out["first_problem"] = out["first_problem"] or \
                "checkpoint %d does not link to the one before it" % seq
        if seq == 0:
            out["genesis_prev_is_GENESIS"] = \
                (str(cp.get("prevTip") or "") == _ZERO64)
        created, rend = _iso_ts(cp.get("createdAt")), _iso_ts(cp.get("rangeEnd"))
        if created is not None and rend is not None and \
                created - rend > BACKFILL_HOURS * 3600:
            backfilled += 1
            backfill_through = seq
        prev = tip
        hashes[tip] = seq
        public_text[seq] = json.dumps(cp, sort_keys=True)
        meta[seq] = cp
        out["public_recomputed"] += 1
        out["blocks"] += 1
    out["complete"] = bool(seqs) and seqs[0] == 0 and not out["first_problem"]
    out["tip"] = prev if seqs else None
    out["backfill_detected"] = {
        "checkpoints": backfilled, "through_seq": backfill_through,
        "rule": "sealed more than %d hours after the window it covers"
                % BACKFILL_HOURS}
    return out, hashes, public_text, meta


def _hex_values(obj, found=None):
    found = found if found is not None else set()
    if isinstance(obj, dict):
        for v in obj.values():
            _hex_values(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _hex_values(v, found)
    elif isinstance(obj, str):
        for m in _HEX64.findall(obj.lower()):
            found.add(m)
    return found


def _anchor_check(proof_endpoint, hashes, budget, meta=None):
    if not proof_endpoint:
        return "fail", "no anchor proof address declared"
    tip, raw = None, None
    if "{seq}" in proof_endpoint:
        done = [sq for sq, cp in (meta or {}).items()
                if str(cp.get("otsStatus")) in ("upgraded", "confirmed")]
        if not done:
            return "fail", "no checkpoint is marked as anchored"
        seq = max(done)
        tip = str(meta[seq].get("tip") or "").lower()
        raw, err = _fetch_raw(proof_endpoint.replace("{seq}", str(seq)),
                              budget, MAX_DECL_BYTES, "*/*")
        if err:
            return "fail", "could not read anchor proof: %s" % err
        if raw[:1] in (b"{", b"["):
            try:
                data = json.loads(raw.decode("utf-8"))
                import base64
                raw = base64.b64decode(data.get("ots_base64") or "")
            except Exception:
                return "fail", "anchor proof could not be read"
    else:
        data, err = _fetch_json(proof_endpoint, budget)
        if err:
            return "fail", "could not read anchor proof: %s" % err
        tip = str(data.get("tip") or "").lower() if isinstance(data, dict) else ""
        b64 = data.get("ots_base64") if isinstance(data, dict) else None
        if not b64:
            return "fail", "no proof bytes served (expected ots_base64)"
        import base64
        try:
            raw = base64.b64decode(b64)
        except Exception:
            return "fail", "anchor proof could not be read"
    if not tip or tip not in hashes:
        return "fail", "the anchored tip is not in the walked chain"
    try:
        from opentimestamps.core.serialize import BytesDeserializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile
        from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
    except Exception:
        return "untested", "proof reader not available on this checker"
    try:
        det = DetachedTimestampFile.deserialize(BytesDeserializationContext(raw))
    except Exception:
        return "fail", "anchor proof could not be read"
    tb = bytes.fromhex(tip)
    candidates = (hashlib.sha256(tb).digest(), tb,
                  hashlib.sha256(tip.encode("ascii")).digest())
    if det.file_digest not in candidates:
        return "fail", "anchor proof is for a different value than the tip it names"
    heights = []

    def walk(ts):
        for att in ts.attestations:
            if isinstance(att, BitcoinBlockHeaderAttestation):
                heights.append(att.height)
        for _, sub in ts.ops.items():
            walk(sub)
    try:
        walk(det.timestamp)
    except Exception:
        return "fail", "anchor proof could not be walked"
    if not heights:
        return "fail", "anchor proof is still pending, not yet in Bitcoin"
    return "pass", ("proof commits a chain tip to Bitcoin block %s; the block "
                    "header itself is not re-checked here - run ots verify "
                    "to confirm against Bitcoin" % min(heights))


def _is_declaration(data):
    spec = str(data.get("spec") or "")
    return spec == "ai-integrity-declaration" or \
        spec.rstrip("/").endswith("/x/integrity/declaration")


_ORDER = ["L0_DIARY", "L1_SEALED", "L2_WITNESSED", "L3_ANCHORED",
          "L4_OVERSIGHT_VERIFIED"]


def _check(domain):
    budget = _Budget()
    result = {"domain": domain, "checked_at": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "checker_version": VERSION,
        "standard": BASE + "declaration"}

    decl, found_at, tried = None, None, []
    for path in DECLARATION["discovery"]["paths"]:
        url = "https://%s%s" % (domain, path)
        data, err = _fetch_json(url, budget)
        tried.append({"url": url, "result": err or "found"})
        if data is not None and isinstance(data, dict) and \
                _is_declaration(data):
            decl, found_at = data, url
            break
        if data is not None and not err:
            tried[-1]["result"] = "not an ai-integrity-declaration"
    result["looked_at"] = tried

    if decl is None:
        result.update({
            "verified_level": "L0_DIARY", "badge": "GREY",
            "verdict": "No declaration found. Under the standard, silence is "
                       "a rating: L0_DIARY, the operator's word is the only "
                       "evidence.",
            "how_to_improve": "Publish a declaration at https://%s/.well-known/"
                              "ai-integrity.json using the declaration_template "
                              "in %s" % (domain, BASE + "declaration")})
        return result

    result["declaration_url"] = found_at
    claimed = str(decl.get("claimed_level") or "")
    result["claimed_level"] = claimed or None
    checks = {}

    # INV-001 and INV-007 need the chain.
    chain = decl.get("chain") or {}
    endpoint = chain.get("walk_endpoint")
    hashes, public_text, walk, meta = {}, {}, None, {}
    if not endpoint:
        checks["INV-001"] = {"result": "fail", "why": "no walk_endpoint declared"}
    else:
        walk, hashes, public_text, meta = _walk(endpoint, budget)
        ok = (walk["complete"] and walk["blocks"] > 0 and
              walk["genesis_prev_is_GENESIS"] and not walk["first_problem"])
        genesis_ok = True
        declared_genesis = str(chain.get("genesis_hash") or "").lower()
        if declared_genesis and hashes:
            first = min(hashes.items(), key=lambda kv: kv[1] if isinstance(kv[1], int) else 0)
            genesis_ok = (first[0] == declared_genesis)
        checks["INV-001"] = {
            "result": "pass" if (ok and genesis_ok) else "fail",
            "why": walk["first_problem"] or (
                None if genesis_ok else "declared genesis_hash is not the first block"),
            "walk": walk}

    # INV-002: no secret-shaped or personal values in public blocks.
    hits = []
    for idx, text in public_text.items():
        for label, rx in _SECRET_SHAPES:
            if rx.search(text):
                hits.append({"block_index": idx, "found": label})
                break
        if len(hits) >= 10:
            break
    if not decl.get("personal_data_hashing"):
        checks["INV-002"] = {"result": "fail",
                             "why": "personal_data_hashing not declared"}
    elif not public_text:
        checks["INV-002"] = {"result": "fail",
                             "why": "no public records to inspect"}
    elif hits:
        checks["INV-002"] = {"result": "fail",
                             "why": "public blocks contain values that look "
                                    "personal or secret (values not repeated here)",
                             "blocks": hits}
    else:
        checks["INV-002"] = {"result": "pass",
                             "why": "%d public blocks inspected; nothing "
                                    "personal or secret-shaped found"
                                    % len(public_text)}

    # INV-007: every discontinuity is disclosed - sealed in the chain, or
    # declared with the evidence to detect it - and anything the checker
    # can detect for itself must have been declared.
    discs = decl.get("discontinuities") or []
    missing, sealed, declared = [], 0, []
    for disc in discs:
        if not isinstance(disc, dict):
            missing.append(str(disc))
            continue
        blk = disc.get("disclosure_block")
        if blk not in (None, ""):
            try:
                blk = int(blk)
            except (TypeError, ValueError):
                missing.append(str(blk))
                continue
            if blk in public_text:
                sealed += 1
            else:
                missing.append(str(blk))
        elif disc.get("kind") and disc.get("detail"):
            declared.append(str(disc.get("kind")))
        else:
            missing.append("an entry with neither a disclosure_block nor kind and detail")
    undisclosed = None
    bf = (walk or {}).get("backfill_detected") or {}
    if bf.get("checkpoints"):
        claimed_bf = [d for d in discs if isinstance(d, dict) and
                      "backfill" in str(d.get("kind", "")).lower()]
        if not claimed_bf:
            undisclosed = ("%d checkpoints were sealed long after the window "
                           "they cover, and no backfill is declared"
                           % bf["checkpoints"])
    if checks["INV-001"]["result"] != "pass":
        checks["INV-007"] = {"result": "fail", "why": "chain could not be verified"}
    elif missing:
        checks["INV-007"] = {"result": "fail",
                             "why": "declared disclosures not found: %s"
                                    % ", ".join(missing)}
    elif undisclosed:
        checks["INV-007"] = {"result": "fail", "why": undisclosed}
    else:
        parts = []
        if sealed:
            parts.append("%d sealed in the chain" % sealed)
        if declared:
            parts.append("%d declared with detection evidence (%s)"
                         % (len(declared), ", ".join(declared)))
        checks["INV-007"] = {
            "result": "pass",
            "why": ("discontinuities disclosed: " + "; ".join(parts))
                   if parts else "no discontinuities declared, and none detected"}
        if bf.get("checkpoints"):
            checks["INV-007"]["independently_detected"] = {
                "backfilled_checkpoints": bf["checkpoints"],
                "through_seq": bf["through_seq"],
                "note": "Found by the checker from createdAt against "
                        "rangeEnd, not taken from the declaration."}

    # INV-003: at least one declared witness holds a tip that is in our chain.
    witnesses = decl.get("witnesses") or []
    witness_results = []
    for w in witnesses[:5]:
        if not isinstance(w, dict) or not w.get("tip_endpoint"):
            continue
        data, err = _fetch_json(w.get("tip_endpoint"), budget,
                                WITNESS_MAX_BYTES, allow_text=True)
        if err:
            witness_results.append({"name": w.get("name"), "result": "fail",
                                    "why": err})
            continue
        held = _hex_values(data) & set(hashes.keys())
        entry = {
            "name": w.get("name"),
            "url": w.get("tip_endpoint"),
            "result": "pass" if held else "fail",
            "why": "publishes %d hash(es) that are blocks in the chain"
                   % len(held) if held else
                   "published no value found in the chain"}
        if held:
            entry["matched_blocks"] = sorted(
                hashes[h] for h in held if isinstance(hashes.get(h), int))[-5:]
        witness_results.append(entry)
    if any(r["result"] == "pass" for r in witness_results):
        checks["INV-003"] = {"result": "pass", "witnesses": witness_results,
                             "collusion_threshold_declared":
                                 decl.get("collusion_threshold"),
                             "note": "Independence of each witness is as "
                                     "declared; the checker confirms they "
                                     "hold the tip, not who runs them."}
    else:
        checks["INV-003"] = {"result": "fail",
                             "why": "no declared witness confirmed a tip in "
                                    "the chain" if witness_results else
                                    "no witnesses declared",
                             "witnesses": witness_results}

    # INV-004: an anchor proof committing a chain tip to Bitcoin.
    anchor = decl.get("anchor") or {}
    res, why = _anchor_check(anchor.get("proof_endpoint"), hashes, budget, meta)
    checks["INV-004"] = {"result": res, "why": why}

    # INV-005 / INV-006 cannot be tested from outside yet.
    for inv in ("INV-005", "INV-006"):
        checks[inv] = {"result": "untested",
                       "why": "human-oversight checks cannot yet be tested "
                              "from outside; this checker never awards L4"}

    level = "L0_DIARY"
    for name in _ORDER[1:]:
        needs = [r.split("-")[0] + "-" + r.split("-")[1]
                 for r in DECLARATION["levels"][name]["requires"]]
        if all(checks.get(n, {}).get("result") == "pass" for n in needs):
            level = name
        else:
            break

    if decl.get("known_gaps"):
        result["known_gaps_declared"] = decl.get("known_gaps")
    result["checks"] = checks
    result["verified_level"] = level
    result["badge"] = DECLARATION["levels"][level]["badge"]
    if claimed in _ORDER and _ORDER.index(claimed) > _ORDER.index(level):
        result["verdict"] = "OVERCLAIMED: declares %s, verifies as %s." % (claimed, level)
        result["overclaimed"] = True
    else:
        result["verdict"] = "Verifies as %s." % level
        result["overclaimed"] = False
    result["rule"] = ("Nothing in the declaration was taken on trust. Every "
                      "pass above was recomputed or fetched by this checker.")
    return result


def _check_route(data):
    domain = _clean_domain((data or {}).get("domain"))
    if not domain:
        return {"ok": False, "error": "domain_required",
                "example": BASE + "check?domain=example.com",
                "detail": "Give a public domain name, e.g. domain=example.com"}, 400
    now = time.time()
    with _cache_lock:
        hit = _cache.get(domain)
        if hit and now - hit[0] < CACHE_SECONDS:
            out = dict(hit[1])
            out["cached_seconds_ago"] = int(now - hit[0])
            return out, 200
    if not _running.acquire(blocking=False):
        return {"ok": False, "error": "busy",
                "detail": "Two checks are already running. Try again in a "
                          "minute."}, 429
    try:
        out = _check(domain)
    except Exception as exc:
        out = {"domain": domain, "verified_level": "L0_DIARY", "badge": "GREY",
               "error": "check_failed", "detail": str(exc)[:200]}
    finally:
        _running.release()
    out["ok"] = True
    with _cache_lock:
        _cache[domain] = (time.time(), out)
        if len(_cache) > 500:
            oldest = sorted(_cache.items(), key=lambda kv: kv[1][0])[:100]
            for k, _ in oldest:
                _cache.pop(k, None)
    return out, 200


def _status():
    return {
        "ok": True,
        "module": "integrity",
        "version": VERSION,
        "standard": DECLARATION.get("spec"),
        "standard_version": DECLARATION.get("version"),
        "declaration_id": DECLARATION.get("declaration_id"),
        "declaration_sha256": DECLARATION_SHA256,
        "levels": list(DECLARATION.get("levels", {}).keys()),
        "invariants": list(DECLARATION.get("invariants", {}).keys()),
        "links": {
            "declaration": BASE + "declaration",
            "check_any_domain": BASE + "check?domain=example.com",
            "sebbi_self_declaration": BASE + "self",
            "check_sebbi": BASE + "check?domain=sebbi.pro",
            "ordering_test": "https://sebbi.pro/.well-known/ordering-test.json",
        },
        "how_to_adopt": "Publish your own filled-in declaration_template at "
                        "/.well-known/ai-integrity.json on your own domain, "
                        "then check it at " + BASE + "check?domain=yourdomain",
        "hash_note": "declaration_sha256 is SHA-256 of the declaration as "
                     "compact JSON with sorted keys, so anyone can confirm "
                     "the text they are reading is the text published.",
    }


def handle(method, action, data, api_key, ctx):
    data = data or {}
    if isinstance(data.get("domain"), list):
        data = dict(data)
        data["domain"] = data["domain"][0] if data["domain"] else ""
    if method == "GET" and action in ("status", "spec", ""):
        return _status(), 200
    if method == "GET" and action == "declaration":
        return DECLARATION, 200
    if method == "GET" and action == "self":
        return SELF, 200
    if method == "GET" and action == "check":
        return _check_route(data)
    return {"ok": False, "error": "unknown_action",
            "get": sorted(a for m, a in PUBLIC if m == "GET"),
            "post": []}, 404
