# Codebase — part 8 of 36

Contains:
- `modules/integrity.py`
- `modules/investor.py`


## `modules/integrity.py`

1487 lines, 65650 bytes

```python
"""
modules/integrity.py  v1.4.4  -  the AI Integrity Declaration, a public checker,
                              and a sealed public register of verdicts

Serves the open standard that rates every AI deployment from L0_DIARY
(no checkable record) up to L4_OVERSIGHT_VERIFIED, and checks any domain
against it. Reads only. Seals nothing, writes nothing, creates no tables.
Every route is public.

Routes:
  https://sebbi.pro/x/integrity/status                    what this is
  https://sebbi.pro/x/integrity/declaration               the standard, as JSON
  https://sebbi.pro/x/integrity/self                      sebbi.pro's own declaration
  https://sebbi.pro/x/integrity/check?domain=example.com  rate any domain
  https://sebbi.pro/x/integrity/register                  every sealed verdict

v1.4: THE CHECKER'S OWN VERDICTS ARE NOW EVIDENCE.
Every fresh verdict is sealed into the sebbi.pro chain as a public block,
so a rating cannot be quietly changed later - not by the domain rated, and
not by sebbi.pro.

v1.4.3: THE REQUEST IS SEALED TOO, BEFORE THE CHECK RUNS.
A sealed verdict proves what the checker said, not what it left unsaid: an
inconvenient result could simply go unsealed, and from outside, silence and
never-asked look the same. Now the request is sealed first. A domain that
was asked about and has no verdict after it shows up in the register as
exactly that. (Raised by Richard Whitney, MIRegistry.) The register lists the latest sealed verdict per domain,
each with the block that holds it. A checker that rates others by whether
their records can be altered now holds its own ratings to the same rule.

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

VERSION = "1.4.4"
BASE = "https://sebbi.pro/x/integrity/"

PUBLIC = {("GET", "status"), ("GET", "declaration"), ("GET", "spec"),
          ("GET", "self"), ("GET", "check"), ("GET", "register")}

# ---------------------------------------------------------------- the standard

DECLARATION = json.loads(r'''{
  "spec": "ai-integrity-declaration",
  "version": "1.0.4",
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
      "witness_strength": {
        "sealed": "The witness sealed the tip inside its own hash chain, and the checker recomputed that block and found the tip in it.",
        "bound": "The witness recorded the tip against a position in its own anchored chain, which dates the record but does not seal it.",
        "listed": "The witness publishes the tip, with nothing in its own chain binding the record.",
        "note": "Strength is reported for every passing witness. It does not yet change the level; it will be graded from 1.1.0. A witness can climb from listed to bound to sealed, and the declaration shows which it is."
      },
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
      "detection_rule": "A discontinuity that is detected rather than asserted states the rule that detected it (for example \"createdAt - rangeEnd > 2 hours\"), so any verifier can recount it and get the same number. Where a rule is declared, the checker applies that rule rather than its own and reports whether it reproduces the declared count. In 1.0.3 a missing rule is reported; from 1.1.0 it fails.",
      "detection_rule_location": "Inside the discontinuity it describes: discontinuities[].detection_rule, beside that entry's own counts (checkpoints, through_seq). A rule anywhere else is not read.",
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
      "version": "1.0.4",
      "date": "2026-09-20",
      "change": "Fixed where detection_rule lives: inside its discontinuity, beside the counts it produces. Where a rule is declared, the checker now reports the count under that rule first and its own default second, instead of leading with its default. Check requests are now sealed before the check runs, so a request with no verdict after it is visible in the register. Both raised by Richard Whitney (MIRegistry)."
    },
    {
      "version": "1.0.3",
      "date": "2026-09-20",
      "change": "detection_rule for detected discontinuities, applied by the checker to recount the declared figure. Witness strength (sealed, bound, listed) reported for every witness. Both raised by Richard Whitney (MIRegistry). Every fresh checker verdict is now sealed into the sebbi.pro chain and listed in a public register, so ratings themselves cannot be quietly altered."
    },
    {
      "version": "1.0.2",
      "date": "2026-09-20",
      "change": "Defined witness independence (control, not payment). INV-007 accepts discontinuities disclosed in the declaration with detection evidence, and fails undisclosed ones the checker can detect. Added known_gaps and the unrated availability axis. All three raised by Richard Whitney (MIRegistry) while writing the first external declaration."
    }
  ],
  "public_checker": "https://sebbi.pro/x/integrity/check?domain=example.com",
  "public_register": "https://sebbi.pro/x/integrity/register"
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
]

SELF = {
    "spec": "ai-integrity-declaration",
    "version": "1.0.3",
    "organisation": "Monop Content",
    "system": "sebbi.pro",
    "claimed_level": "L3_ANCHORED",
    "chain": {
        "walk_endpoint": "https://sebbi.pro/x/walk/blocks",
        "genesis_hash": "534f9e5cefb1a48566674911262151f34eedc1e6840a094d9465af4d846972c6",
        "seal_method_url": "https://sebbi.pro/x/walk/spec",
    },
    "personal_data_hashing": "Customer decisions are never published. Blocks sealed under a customer key, from non-public sources, or carrying anything secret-shaped are served without payload; only their hash and link are public.",
    "witnesses": SELF_WITNESSES,
    "collusion_threshold": 1,
    "collusion_note": "One: only witnesses a machine can verify are counted. Other chains witness sebbi.pro but do not yet publish a list the checker can read, so they are not counted.",
    "held_for_others": "https://sebbi.pro/x/held/peers",
    "anchor": {
        "method": "OpenTimestamps on Bitcoin",
        "proof_endpoint": "https://sebbi.pro/x/ots/latest_confirmed",
        "status_url": "https://sebbi.pro/x/ots/status",
        "note": "Tips are stamped hourly. proof_endpoint always serves the newest proof that is confirmed in Bitcoin and whose tip is a block in the current chain. Anchoring is not claimed until the checker verifies it.",
    },
    "oversight": {
        "commit_before_reveal": True,
        "demonstration": "https://sebbi.pro/x/demo/review",
        "anti_rubber_stamp": {"minimum_review_seconds": 1.5,
                              "maximum_agreement_rate": 0.98},
    },
    "discontinuities": [
        {"date": "2026-09-07", "disclosure_block": 2013, "kind": "chain_reset",
         "detail": "The chain restarted from genesis. The reset is sealed in block 2013; block indexes quoted before that date belong to the earlier chain."},
    ],
    "known_gaps": [
        "Availability: every level answers 'has this been altered', none yet answers 'will this still be served'. A reader currently depends on sebbi.pro continuing to serve these endpoints.",
        "Anchoring: tips are stamped to Bitcoin hourly and confirm a few hours later, so the newest hour or so rests on witnessing until its proof confirms.",
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
USER_AGENT = "sebbi-integrity-checker/1.4.4 (+https://sebbi.pro/x/integrity/status)"

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

_RULE_RE = re.compile(
    r"createdAt\s*-\s*rangeEnd\s*(>=|>)\s*([0-9]+(?:\.[0-9]+)?)\s*"
    r"(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", re.I)


def _parse_rule(text):
    """'createdAt - rangeEnd > 2 hours' -> (op, seconds) or None."""
    m = _RULE_RE.search(str(text or ""))
    if not m:
        return None
    n = float(m.group(2))
    unit = m.group(3).lower()
    mult = 3600 if unit.startswith("h") else 60 if unit.startswith("m") else 1
    return m.group(1), n * mult


def _recount(meta, op, seconds):
    count, through = 0, None
    for seq in sorted(meta):
        cp = meta[seq]
        c, r = _iso_ts(cp.get("createdAt")), _iso_ts(cp.get("rangeEnd"))
        if c is None or r is None:
            continue
        lag = c - r
        if (lag >= seconds) if op == ">=" else (lag > seconds):
            count += 1
            through = seq
    return count, through


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
        "rule": "checker default: sealed more than %d hours after the window "
                "it covers" % BACKFILL_HOURS,
        "note": "Where the declaration states its own detection_rule, the "
                "count under that rule is in INV-007."}
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


def _witness_strength(data, held, budget):
    """sealed / bound / listed - how the witness binds its record."""
    rows = []
    if isinstance(data, dict):
        for key in ("tips", "held", "observations", "entries"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
    row = None
    for r in rows:
        if isinstance(r, dict) and \
                str(r.get("peer_tip") or r.get("tip") or "").lower() in held:
            row = r
            break
    if row is None:
        return {"grade": "listed",
                "why": "tip found on the witness's page; no binding record read"}
    tip = str(row.get("peer_tip") or row.get("tip") or "").lower()
    blk_url, blk_hash = row.get("check_block"), row.get("sealed_block_hash")
    if blk_url and blk_hash:
        page, err = _fetch_json(blk_url, budget)
        blk = page.get("block") if isinstance(page, dict) else None
        pre = blk.get("preimage") if isinstance(blk, dict) else None
        if isinstance(pre, str) and tip in pre.lower() and \
                hashlib.sha256(pre.encode("utf-8")).hexdigest() == \
                str(blk_hash).lower():
            return {"grade": "sealed",
                    "why": "the witness's own block was recomputed and "
                           "contains the tip",
                    "witness_block": blk_url}
        return {"grade": "listed",
                "why": "a sealed block was claimed but could not be "
                       "recomputed here (%s)" % (err or "mismatch")}
    if row.get("our_tip_at_observation") or row.get("witness_tip_at_observation"):
        return {"grade": "bound",
                "why": "recorded against a position in the witness's own "
                       "anchored chain; dated, not sealed"}
    return {"grade": "listed",
            "why": "published with nothing binding it in the witness's chain"}


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
    result["declaration_sha256"] = hashlib.sha256(json.dumps(
        decl, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()
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
        checker_default = None
        if bf.get("checkpoints"):
            checker_default = {
                "backfilled_checkpoints": bf["checkpoints"],
                "through_seq": bf["through_seq"],
                "rule": str(bf.get("rule")),
                "note": "The checker's own threshold, used only when no rule "
                        "is declared. Shown for comparison."}
        recounts = []
        for d in discs:
            if not isinstance(d, dict) or \
                    "backfill" not in str(d.get("kind", "")).lower():
                continue
            rule_text = d.get("detection_rule") or d.get("detectionRule")
            entry = {"kind": d.get("kind"), "declared_rule": rule_text,
                     "declared_count": d.get("checkpoints") or d.get("count"),
                     "declared_through_seq": d.get("through_seq")}
            parsed = _parse_rule(rule_text) if rule_text else None
            if not rule_text:
                entry["result"] = "rule_missing"
                entry["note"] = ("No detection_rule declared. Reported in "
                                 "1.0.3; from 1.1.0 this fails.")
            elif not parsed or not meta:
                entry["result"] = "rule_unreadable"
                entry["note"] = ("The declared rule could not be applied "
                                 "automatically. Reported, not failed.")
            else:
                n, through = _recount(meta, parsed[0], parsed[1])
                entry["recounted_under_declared_rule"] = n
                entry["recounted_through_seq"] = through
                try:
                    ok = int(entry["declared_count"]) == n
                except (TypeError, ValueError):
                    ok = None
                entry["reproduces"] = ok
                entry["result"] = ("reproduced" if ok else
                                   "differs" if ok is False else "recounted")
            recounts.append(entry)
        applied = [r for r in recounts
                   if r.get("result") in ("reproduced", "differs", "recounted")]
        if applied:
            a = applied[0]
            checks["INV-007"]["independently_detected"] = {
                "backfilled_checkpoints": a.get("recounted_under_declared_rule"),
                "through_seq": a.get("recounted_through_seq"),
                "rule": "declared: " + str(a.get("declared_rule")),
                "reproduces_declared_count": a.get("reproduces"),
                "note": "Recounted by the checker from createdAt against "
                        "rangeEnd, under the rule the declaration states. "
                        "Nothing taken on trust."}
            if checker_default:
                checks["INV-007"]["checker_default_for_comparison"] = checker_default
        elif checker_default:
            checks["INV-007"]["independently_detected"] = checker_default
        if recounts:
            checks["INV-007"]["detection_rule_recount"] = recounts

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
            entry["witness_strength"] = _witness_strength(data, held, budget)
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


VERDICT_USER = "system_integrity_verdict"
VERDICT_RESEAL_SECONDS = 24 * 3600
VERDICT_MAX_PER_HOUR = 30
_seal_times = []
_seal_lock = threading.Lock()


def _verdict_fingerprint(out):
    return (out.get("verified_level"), out.get("claimed_level"),
            out.get("overclaimed"), bool(out.get("error")))


def _verdict_ref(idx, h):
    return {"block_index": idx, "audit_hash": h,
            "check_block": ("https://sebbi.pro/x/walk/block?index=%s" % idx)
            if idx is not None else None}


def _already_sealed(conn, domain, fp, now):
    """The chain itself is the memory: find a verdict for this domain,
    sealed today (UTC), with the same outcome. Per UTC day, like requests,
    so each day's first request is always followed by a verdict."""
    rows = conn.execute(
        "SELECT id, audit_hash, result_json FROM audit_log "
        "WHERE user_id = ? AND ts >= ? ORDER BY id DESC LIMIT 200",
        (VERDICT_USER, now - (now % 86400))).fetchall()
    for idx, h, rj in rows:
        try:
            r = json.loads(rj)
        except Exception:
            continue
        if r.get("domain") != domain:
            continue
        if (r.get("verified_level"), r.get("claimed_level"),
                r.get("overclaimed")) == fp[:3]:
            return _verdict_ref(idx, h)
        return None   # latest verdict for this domain differs: reseal
    return None


REQUEST_USER = "system_integrity_request"


def _claim(conn, domain, day, key, now):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS integrity_verdict_claims ("
        "domain TEXT, day TEXT, verdict TEXT, claimed_at REAL, "
        "PRIMARY KEY (domain, day, verdict))")
    cur = conn.execute(
        "INSERT OR IGNORE INTO integrity_verdict_claims "
        "(domain, day, verdict, claimed_at) VALUES (?, ?, ?, ?)",
        (domain, day, key, now))
    conn.commit()
    return cur.rowcount == 1


def _seal_request(domain, ctx):
    """Seal that a check was asked for, before it runs. Once per domain per
    UTC day, so the chain shows every domain that was asked about - and the
    register can show any request with no verdict after it."""
    seal = (ctx or {}).get("seal")
    conn, lock = (ctx or {}).get("conn"), (ctx or {}).get("lock")
    if not callable(seal) or conn is None or lock is None:
        return None
    now = time.time()
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    with lock:
        won = _claim(conn, domain, day, "__request__", now)
        if not won:
            r = conn.execute(
                "SELECT id, audit_hash FROM audit_log WHERE user_id = ? AND "
                "ts > ? AND result_json LIKE ? ORDER BY id DESC LIMIT 1",
                (REQUEST_USER, now - 86400,
                 '%"domain": "' + domain + '"%')).fetchone()
            ref = _verdict_ref(r[0], r[1]) if r else {}
            return dict(ref, sealed_now=False)
    with _seal_lock:
        while _seal_times and now - _seal_times[0] > 3600:
            _seal_times.pop(0)
        if len(_seal_times) >= VERDICT_MAX_PER_HOUR:
            return {"sealed_now": False,
                    "note": "hourly sealing limit reached; request not sealed"}
        _seal_times.append(now)
    event = {"user_id": REQUEST_USER, "action": "integrity_check_requested",
             "amount": 0, "country": "UK", "device_id": "checker",
             "anomaly": 0, "device_risk": 0}
    result = {"decision": "REQUESTED", "score": 0, "domain": domain,
              "checker_version": VERSION,
              "standard_version": DECLARATION.get("version"),
              "requested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime(now)),
              "timestamp": now}
    try:
        res = seal(event, result, now)
    except Exception as exc:
        with lock:
            conn.execute("DELETE FROM integrity_verdict_claims WHERE "
                         "domain = ? AND day = ? AND verdict = ?",
                         (domain, day, "__request__"))
            conn.commit()
        return {"sealed_now": False, "note": "could not seal: %s" % exc}
    if isinstance(res, (list, tuple)):
        h, idx = res[0], (res[1] if len(res) > 1 else None)
    elif isinstance(res, dict):
        h = res.get("audit_hash") or res.get("hash")
        idx = res.get("block_index") or res.get("index")
    else:
        h, idx = res, None
    return dict(_verdict_ref(idx, h), sealed_now=True)


def _seal_verdict(domain, out, ctx):
    """Seal a verdict into the chain at most once per domain per UTC day,
    unless the verdict changes.

    v1.4 kept that limit in server memory, so a server running several
    copies of itself sealed once per copy. v1.4.1 asks the chain first,
    then claims the seal in a table every copy shares, so only one copy
    can seal a given verdict on a given day."""
    seal = (ctx or {}).get("seal")
    conn, lock = (ctx or {}).get("conn"), (ctx or {}).get("lock")
    if not callable(seal) or conn is None or lock is None:
        return None
    if out.get("error"):
        # A check that failed to run has no verdict to seal. Its request is
        # already sealed, so the register shows it as asked and unanswered.
        return {"sealed_now": False,
                "note": "the check did not complete, so no verdict was sealed; "
                        "the request stays on record without one"}
    now = time.time()
    fp = _verdict_fingerprint(out)
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    claim = json.dumps(list(fp))
    with lock:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS integrity_verdict_claims ("
            "domain TEXT, day TEXT, verdict TEXT, claimed_at REAL, "
            "PRIMARY KEY (domain, day, verdict))")
        ref = _already_sealed(conn, domain, fp, now)
        if ref:
            conn.commit()
            return dict(ref, sealed_now=False)
        won = _claim(conn, domain, day, claim, now)
    if not won:
        return {"sealed_now": False,
                "note": "this verdict was already sealed today"}
    with _seal_lock:
        while _seal_times and now - _seal_times[0] > 3600:
            _seal_times.pop(0)
        if len(_seal_times) >= VERDICT_MAX_PER_HOUR:
            return {"sealed_now": False,
                    "note": "hourly sealing limit reached; verdict not sealed"}
        _seal_times.append(now)
    walk = ((out.get("checks") or {}).get("INV-001") or {}).get("walk") or {}
    event = {"user_id": VERDICT_USER, "action": "integrity_verdict",
             "amount": 0, "country": "UK", "device_id": "checker",
             "anomaly": 0, "device_risk": 0}
    result = {"decision": "VERDICT", "score": 0, "domain": domain,
              "verified_level": out.get("verified_level"),
              "badge": out.get("badge"),
              "claimed_level": out.get("claimed_level"),
              "overclaimed": out.get("overclaimed"),
              "declaration_url": out.get("declaration_url"),
              "declaration_sha256": out.get("declaration_sha256"),
              "chain_tip_reached": walk.get("tip"),
              "blocks_walked": walk.get("blocks"),
              "checker_version": VERSION,
              "standard_version": DECLARATION.get("version"),
              "checked_at": out.get("checked_at"),
              "timestamp": now}
    try:
        res = seal(event, result, now)
    except Exception as exc:
        with lock:
            conn.execute("DELETE FROM integrity_verdict_claims WHERE "
                         "domain = ? AND day = ? AND verdict = ?",
                         (domain, day, claim))
            conn.commit()
        return {"sealed_now": False, "note": "could not seal: %s" % exc}
    if isinstance(res, (list, tuple)):
        h, idx = res[0], (res[1] if len(res) > 1 else None)
    elif isinstance(res, dict):
        h = res.get("audit_hash") or res.get("hash")
        idx = res.get("block_index") or res.get("index")
    else:
        h, idx = res, None
    return dict(_verdict_ref(idx, h), sealed_now=True)


def _register(data, ctx):
    conn, lock = (ctx or {}).get("conn"), (ctx or {}).get("lock")
    if conn is None or lock is None:
        return {"ok": False, "error": "register_unavailable"}, 503
    with lock:
        rows = conn.execute(
            "SELECT id, ts, audit_hash, result_json FROM audit_log "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 2000",
            (VERDICT_USER,)).fetchall()
    with lock:
        req_rows = conn.execute(
            "SELECT id, ts, result_json FROM audit_log WHERE user_id = ? "
            "ORDER BY id DESC LIMIT 2000", (REQUEST_USER,)).fetchall()
    last_request = {}
    for ridx, rts, rj in req_rows:
        try:
            d = json.loads(rj).get("domain")
        except Exception:
            continue
        if d and d not in last_request:
            last_request[d] = (ridx, rts)
    latest = {}
    history = {}
    for idx, ts, h, rj in rows:
        try:
            r = json.loads(rj)
        except Exception:
            continue
        d = r.get("domain")
        if not d:
            continue
        history[d] = history.get(d, 0) + 1
        if d in latest:
            continue
        latest[d] = {"domain": d, "verified_level": r.get("verified_level"),
                     "badge": r.get("badge"),
                     "claimed_level": r.get("claimed_level"),
                     "overclaimed": r.get("overclaimed"),
                     "checked_at": r.get("checked_at"),
                     "sealed_in_block": idx, "sealed_block_hash": h,
                     "check_block": "https://sebbi.pro/x/walk/block?index=%d" % idx,
                     "check_now": BASE + "check?domain=" + d}
    order = {n: i for i, n in enumerate(_ORDER)}
    entries = sorted(latest.values(), key=lambda e: (
        -order.get(e.get("verified_level"), -1), e["domain"]))
    for e in entries:
        e["verdicts_sealed"] = history.get(e["domain"], 0)
        lr = last_request.get(e["domain"])
        if lr:
            e["last_request_block"] = lr[0]
    unanswered = []
    for d, (ridx, rts) in sorted(last_request.items()):
        v = latest.get(d)
        if v is None or v["sealed_in_block"] < ridx:
            # a verdict sealed earlier the same day still answers a request
            # sealed later only if the verdict was unchanged; show it anyway
            # so a reader can judge, and say which case it is.
            unanswered.append({
                "domain": d, "request_block": ridx,
                "check_request": "https://sebbi.pro/x/walk/block?index=%d" % ridx,
                "latest_verdict_block": v["sealed_in_block"] if v else None,
                "reading": ("an unchanged verdict sealed earlier the same day "
                            "stands for this request") if v else
                           "asked about, and no verdict has been sealed"})
    return {"ok": True, "register": "AI Integrity Declaration - sealed verdicts",
            "standard": BASE + "declaration",
            "domains": len(entries), "entries": entries,
            "requests_without_a_later_verdict": unanswered,
            "what_this_is": "The latest verdict the checker sealed for each "
                            "domain, highest level first. Every row points "
                            "at the public block that holds it, so no rating "
                            "here can be changed after it was given - by the "
                            "domain, or by sebbi.pro. Every request is sealed "
                            "before its check runs, so a question that was "
                            "asked and never answered is visible below the "
                            "list, not hidden by it."}, 200


def _check_route(data, ctx=None):
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
    request = _seal_request(domain, ctx)
    try:
        out = _check(domain)
    except Exception as exc:
        out = {"domain": domain, "verified_level": "L0_DIARY", "badge": "GREY",
               "error": "check_failed", "detail": str(exc)[:200]}
    finally:
        _running.release()
    out["ok"] = True
    if request:
        out["request_sealed"] = request
    sealed = _seal_verdict(domain, out, ctx)
    if sealed:
        out["verdict_sealed"] = sealed
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
            "register": BASE + "register",
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
        return _check_route(data, ctx)
    if method == "GET" and action == "register":
        return _register(data, ctx)
    return {"ok": False, "error": "unknown_action",
            "get": sorted(a for m, a in PUBLIC if m == "GET"),
            "post": []}, 404

```


## `modules/investor.py`

298 lines, 23897 bytes

```python
"""
modules/investor.py  v1.3.0
Serves the investor / partner page at /investor-prospectus.

Page module, same family as map.py / console.py / network.py: a runtime do_GET
patch puts the page at a clean URL, armed by hitting /x/investor/status once
after each deploy. server.py is never edited. Page is base64-embedded.

v1.3.0 changes, all wording:
  * "externally anchored" and "anchored to a clock nobody controls" replaced
    with per-proof timestamping language. Anchoring is a state each individual
    proof is in, not a property the chain has, and /x/ots/status is where an
    investor will look it up in front of you.
  * the /x/ots/status line now says plainly that submitted is not confirmed.
  * contact address aligned with ai.txt v2.0.
Founding seats language is unchanged, deliberately.

NOTE: investor-prospectus.html also exists at the repo root. Two investor
pages on two paths will drift. Decide which one is canonical and delete the
other.
"""

import base64
import sys

VERSION = "1.3.0"
PAGE_PATH = "/investor-prospectus"

_B64 = (
    "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0i"
    "dmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLjAiPgo8dGl0bGU+c2ViYmkucHJv"
    "IOKAlCB0aGUgZXZpZGVuY2UgbGF5ZXIgZm9yIEFJLiBQYXJ0bmVyIG9wcG9ydHVuaXR5LjwvdGl0bGU+CjxtZXRhIG5hbWU9ImRl"
    "c2NyaXB0aW9uIiBjb250ZW50PSJBIGxpdmUsIHB1YmxpY2x5IHZlcmlmaWFibGUgZXZpZGVuY2UgbGF5ZXIgZm9yIEFJIGRlY2lz"
    "aW9ucy4gQnVpbHQsIHJ1bm5pbmcsIGFuZCBzdHJ1Y3R1cmFsbHkgaW1wb3NzaWJsZSBmb3IgaW5jdW1iZW50cyB0byBjb3B5LiBT"
    "ZWVraW5nIG9uZSBvcGVyYXRpbmcgcGFydG5lciB0byB0YWtlIGl0IGludG8gcmVndWxhdGVkIGVudGVycHJpc2UuIj4KPGxpbmsg"
    "cmVsPSJwcmVjb25uZWN0IiBocmVmPSJodHRwczovL2ZvbnRzLmdvb2dsZWFwaXMuY29tIj4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9m"
    "b250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1OZXdzcmVhZGVyOm9wc3osd2dodEA2Li43Miw0MDA7Ni4uNzIsNTAwOzYu"
    "LjcyLDYwMDs2Li43Miw3MDAmZmFtaWx5PUlCTStQbGV4K1NhbnM6d2dodEA0MDA7NTAwOzYwMDs3MDAmZmFtaWx5PUlCTStQbGV4"
    "K01vbm86d2dodEA0MDA7NTAwOzYwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7CiAgLS1w"
    "YXBlcjojRkFGQUY2Oy0taW5rOiMxNDE3MUM7LS1pbmstc29mdDojNDU0QjU0Oy0tY2hhaW46IzJFNUU0RTsKICAtLWNoYWluLWxp"
    "Z2h0OiNFNEVDRTg7LS1nb2xkOiM5QTdCMUY7LS1nb2xkLWxpZ2h0OiNGM0VDRDg7LS1saW5lOiNERURCRDE7Cn0KKntib3gtc2l6"
    "aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQpib2R5e2ZvbnQtZmFtaWx5OidJQk0gUGxleCBTYW5zJyxzYW5zLXNl"
    "cmlmO2JhY2tncm91bmQ6dmFyKC0tcGFwZXIpO2NvbG9yOnZhcigtLWluayk7bGluZS1oZWlnaHQ6MS42Oy13ZWJraXQtZm9udC1z"
    "bW9vdGhpbmc6YW50aWFsaWFzZWR9CmgxLGgyLGgzLC5kaXNwbGF5e2ZvbnQtZmFtaWx5OidOZXdzcmVhZGVyJyxzZXJpZjtmb250"
    "LXdlaWdodDo1MDA7bGV0dGVyLXNwYWNpbmc6LTAuMDFlbX0KLm1vbm97Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9z"
    "cGFjZX0KYXtjb2xvcjp2YXIoLS1jaGFpbil9Ci53cmFwe21heC13aWR0aDo3NjBweDttYXJnaW46MCBhdXRvO3BhZGRpbmc6MCAy"
    "OHB4fQoKaGVhZGVye3BhZGRpbmc6NTZweCAwIDQwcHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSl9Ci5kb2Mt"
    "bGFiZWx7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzow"
    "LjFlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi1ib3R0b206MjBweDtkaXNw"
    "bGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47ZmxleC13cmFwOndyYXA7Z2FwOjhweH0KaDF7Zm9udC1zaXpl"
    "OmNsYW1wKDM0cHgsNXZ3LDUwcHgpO2xpbmUtaGVpZ2h0OjEuMDg7bWF4LXdpZHRoOjE3Y2g7bWFyZ2luLWJvdHRvbToxOHB4fQou"
    "dGFnbGluZXtmb250LXNpemU6MThweDtjb2xvcjp2YXIoLS1pbmstc29mdCk7bWF4LXdpZHRoOjU0Y2h9Ci50YWdsaW5lIGJ7Y29s"
    "b3I6dmFyKC0taW5rKX0KCi5ibG9ja3twb3NpdGlvbjpyZWxhdGl2ZTtwYWRkaW5nOjhweCAwIDQ0cHggMjRweDtib3JkZXItbGVm"
    "dDoxcHggc29saWQgdmFyKC0tbGluZSk7bWFyZ2luLWxlZnQ6NHB4fQouYmxvY2s6bGFzdC1vZi10eXBle2JvcmRlci1sZWZ0OjFw"
    "eCBzb2xpZCB0cmFuc3BhcmVudH0KLmJsb2NrLW51bXtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlO2ZvbnQt"
    "c2l6ZToxMXB4O2NvbG9yOnZhcigtLWNoYWluKTtsZXR0ZXItc3BhY2luZzowLjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNl"
    "O21hcmdpbi1ib3R0b206MTBweH0KLmJsb2NrIGgye2ZvbnQtc2l6ZToyN3B4O21hcmdpbi1ib3R0b206MTZweDtsaW5lLWhlaWdo"
    "dDoxLjE1fQouYmxvY2sgaDN7Zm9udC1zaXplOjE3cHg7bWFyZ2luOjIycHggMCA4cHh9Ci5ibG9jayBwe2ZvbnQtc2l6ZToxNS41"
    "cHg7Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi1ib3R0b206MTRweDttYXgtd2lkdGg6NjBjaH0KLmJsb2NrIHA6bGFzdC1j"
    "aGlsZHttYXJnaW4tYm90dG9tOjB9Ci5ibG9jayB1bHttYXJnaW46MCAwIDE0cHggMThweH0KLmJsb2NrIGxpe2ZvbnQtc2l6ZTox"
    "NXB4O2NvbG9yOnZhcigtLWluay1zb2Z0KTttYXJnaW4tYm90dG9tOjhweDttYXgtd2lkdGg6NThjaH0KLmJsb2NrIGxpIGIsLmJs"
    "b2NrIHAgYntjb2xvcjp2YXIoLS1pbmspfQoKLnByb29mLWdyaWR7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczox"
    "ZnIgMWZyO2dhcDoxNHB4O21hcmdpbi10b3A6MThweH0KQG1lZGlhKG1heC13aWR0aDo1NjBweCl7LnByb29mLWdyaWR7Z3JpZC10"
    "ZW1wbGF0ZS1jb2x1bW5zOjFmcn19Ci5wcm9vZntiYWNrZ3JvdW5kOndoaXRlO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7"
    "cGFkZGluZzoxOHB4IDIwcHg7Ym9yZGVyLXJhZGl1czo0cHh9Ci5wcm9vZi1ue2ZvbnQtZmFtaWx5OidOZXdzcmVhZGVyJyxzZXJp"
    "Zjtmb250LXNpemU6MjZweDtmb250LXdlaWdodDo2MDA7Y29sb3I6dmFyKC0tY2hhaW4pfQoucHJvb2YtbHtmb250LXNpemU6MTIu"
    "NXB4O2NvbG9yOnZhcigtLWluay1zb2Z0KTttYXJnaW4tdG9wOjNweH0KLnByb29mLXNyY3tmb250LWZhbWlseTonSUJNIFBsZXgg"
    "TW9ubycsbW9ub3NwYWNlO2ZvbnQtc2l6ZToxMHB4O2NvbG9yOiM5OTk7bWFyZ2luLXRvcDo2cHh9CgouY291bnRkb3due2JhY2tn"
    "cm91bmQ6dmFyKC0tZ29sZC1saWdodCk7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDE1NCwxMjMsMzEsMC4yNSk7Ym9yZGVyLXJhZGl1"
    "czo0cHg7cGFkZGluZzoyMHB4IDI0cHg7bWFyZ2luOjIwcHggMH0KLmNvdW50ZG93bi1sYWJlbHtmb250LWZhbWlseTonSUJNIFBs"
    "ZXggTW9ubycsbW9ub3NwYWNlO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLWdvbGQpO3RleHQtdHJhbnNmb3JtOnVwcGVyY2Fz"
    "ZTtsZXR0ZXItc3BhY2luZzowLjA4ZW07bWFyZ2luLWJvdHRvbTo4cHh9Ci5jb3VudGRvd24tZGF5c3tmb250LWZhbWlseTonTmV3"
    "c3JlYWRlcicsc2VyaWY7Zm9udC1zaXplOjM4cHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLWdvbGQpO2xpbmUtaGVpZ2h0"
    "OjF9Ci5jb3VudGRvd24tc3Vie2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLWluay1zb2Z0KTttYXJnaW4tdG9wOjZweDtsaW5l"
    "LWhlaWdodDoxLjZ9CgoucHVsbHtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tY2hhaW4pO3BhZGRpbmc6NnB4IDAgNnB4IDIw"
    "cHg7bWFyZ2luOjIwcHggMDtmb250LWZhbWlseTonTmV3c3JlYWRlcicsc2VyaWY7Zm9udC1zaXplOjIycHg7bGluZS1oZWlnaHQ6"
    "MS4zNTtjb2xvcjp2YXIoLS1pbmspfQoKLmFzay1ib3h7YmFja2dyb3VuZDp2YXIoLS1pbmspO2NvbG9yOnZhcigtLXBhcGVyKTti"
    "b3JkZXItcmFkaXVzOjRweDtwYWRkaW5nOjMycHg7bWFyZ2luLXRvcDoyMHB4fQouYXNrLWFtb3VudHtmb250LWZhbWlseTonTmV3"
    "c3JlYWRlcicsc2VyaWY7Zm9udC1zaXplOjQ0cHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOndoaXRlO2xpbmUtaGVpZ2h0OjEuMDV9"
    "Ci5hc2stbGFiZWx7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtmb250LXNpemU6MTFweDtsZXR0ZXItc3Bh"
    "Y2luZzowLjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOiM4RkE4OUM7bWFyZ2luLWJvdHRvbTo2cHh9Ci5hc2st"
    "Ym94IHB7Zm9udC1zaXplOjE0LjVweDtjb2xvcjojQzdEMkNDO21hcmdpbi10b3A6MTRweDttYXgtd2lkdGg6NTZjaH0KLmFzay1i"
    "b3ggcCBie2NvbG9yOiNmZmZ9CgoudXNlLW9mLWZ1bmRze21hcmdpbi10b3A6MjJweDtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rp"
    "b246Y29sdW1uO2dhcDoxMHB4fQoudWYtcm93e2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGln"
    "bi1pdGVtczpiYXNlbGluZTtwYWRkaW5nLWJvdHRvbToxMHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwy"
    "NTUsMC4xMik7Zm9udC1zaXplOjE0cHg7Z2FwOjE2cHh9Ci51Zi1yb3c6bGFzdC1jaGlsZHtib3JkZXItYm90dG9tOm5vbmV9Ci51"
    "Zi1yb3cgc3BhbjpmaXJzdC1jaGlsZHtjb2xvcjojQzdEMkNDfQoudWYtcGN0e2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxt"
    "b25vc3BhY2U7Y29sb3I6IzhGQTg5QztmbGV4OjAgMCBhdXRvfQoKLnZlcmlmeS1ib3h7YmFja2dyb3VuZDp2YXIoLS1jaGFpbi1s"
    "aWdodCk7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDQ2LDk0LDc4LDAuMjUpO2JvcmRlci1yYWRpdXM6NHB4O3BhZGRpbmc6MjBweCAy"
    "NHB4O21hcmdpbi10b3A6MThweH0KLnZlcmlmeS1ib3ggaDR7Zm9udC1zaXplOjE1cHg7bWFyZ2luLWJvdHRvbToxMHB4fQoudmVy"
    "aWZ5LWJveCBwe2ZvbnQtc2l6ZToxNHB4O21hcmdpbi1ib3R0b206OHB4fQoudmVyaWZ5LWJveCBjb2Rle2ZvbnQtZmFtaWx5OidJ"
    "Qk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC1zaXplOjEyLjVweDtiYWNrZ3JvdW5kOndoaXRlO2JvcmRlcjoxcHggc29saWQg"
    "dmFyKC0tbGluZSk7cGFkZGluZzoycHggN3B4O2JvcmRlci1yYWRpdXM6M3B4O2NvbG9yOnZhcigtLWNoYWluKX0KCi5jb250YWN0"
    "LWJsb2Nre3BhZGRpbmc6NDRweCAwIDY0cHh9Ci5jb250YWN0LWNhcmR7YmFja2dyb3VuZDp2YXIoLS1jaGFpbi1saWdodCk7Ym9y"
    "ZGVyOjFweCBzb2xpZCByZ2JhKDQ2LDk0LDc4LDAuMik7Ym9yZGVyLXJhZGl1czo0cHg7cGFkZGluZzoyOHB4fQouY29udGFjdC1j"
    "YXJkIGgze2ZvbnQtc2l6ZToyMHB4O21hcmdpbi1ib3R0b206MTBweH0KLmNvbnRhY3QtY2FyZCBwe2ZvbnQtc2l6ZToxNC41cHg7"
    "Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi1ib3R0b206MTZweH0KLmNvbnRhY3QtbGlua3N7ZGlzcGxheTpmbGV4O2ZsZXgt"
    "ZGlyZWN0aW9uOmNvbHVtbjtnYXA6NnB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC1zaXplOjE0"
    "cHh9Ci5jb250YWN0LWxpbmtzIGF7Y29sb3I6dmFyKC0tY2hhaW4pO3RleHQtZGVjb3JhdGlvbjpub25lO2ZvbnQtd2VpZ2h0OjUw"
    "MH0KCmZvb3RlcntwYWRkaW5nOjAgMCA0OHB4fQpmb290ZXIgcHtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNl"
    "O2ZvbnQtc2l6ZToxMXB4O2NvbG9yOiM5OTk7bGluZS1oZWlnaHQ6MS44fQoKQG1lZGlhKHByZWZlcnMtcmVkdWNlZC1tb3Rpb246"
    "cmVkdWNlKXsqe3RyYW5zaXRpb246bm9uZSFpbXBvcnRhbnQ7YW5pbWF0aW9uOm5vbmUhaW1wb3J0YW50fX0KPC9zdHlsZT4KPC9o"
    "ZWFkPgo8Ym9keT4KCjxkaXYgY2xhc3M9IndyYXAiPgoKPGhlYWRlcj4KICA8ZGl2IGNsYXNzPSJkb2MtbGFiZWwiPgogICAgPHNw"
    "YW4+UGFydG5lciBPcHBvcnR1bml0eSAmbWlkZG90OyBzZWJiaS5wcm88L3NwYW4+CiAgICA8c3BhbiBpZD0iZG9jLWRhdGUiPiZt"
    "ZGFzaDs8L3NwYW4+CiAgPC9kaXY+CiAgPGgxPlRoZSBldmlkZW5jZSBsYXllciBmb3IgQUkgaXMgYnVpbHQsIGxpdmUsIGFuZCBs"
    "b29raW5nIGZvciBvbmUgcGFydG5lci48L2gxPgogIDxwIGNsYXNzPSJ0YWdsaW5lIj5zZWJiaS5wcm8gaXMgYSBwdWJsaWNseSB2"
    "ZXJpZmlhYmxlIGV2aWRlbmNlIGxheWVyIGZvciBBSSBkZWNpc2lvbnMgJm1kYXNoOyBydW5uaW5nIGluIHByb2R1Y3Rpb24gdG9k"
    "YXksIGNoZWNrYWJsZSBieSBhbnlvbmUgd2l0aCB0aGUgY29tcGFueSBzd2l0Y2hlZCBvZmYuIDxiPlRoZSBoYXJkIHBhcnQgaXMg"
    "ZG9uZS4gV2hhdCdzIGxlZnQgaXMgZGlzdHJpYnV0aW9uLjwvYj48L3A+CjwvaGVhZGVyPgoKPGRpdiBjbGFzcz0iYmxvY2siPgog"
    "IDxkaXYgY2xhc3M9ImJsb2NrLW51bSI+MDEgJm1kYXNoOyBUaGUgb3Bwb3J0dW5pdHk8L2Rpdj4KICA8aDI+RXZlcnkgQUkgZGVj"
    "aXNpb24gaXMgYWJvdXQgdG8gbmVlZCBldmlkZW5jZS4gQWxtb3N0IG5vdGhpbmcgcHJvZHVjZXMgaXQuPC9oMj4KICA8cD5UaHJl"
    "ZSByZWd1bGF0b3J5IHJlZ2ltZXMgYXJlIGNvbnZlcmdpbmcgb24gdGhlIHNhbWUgZGVtYW5kOiByZWNvcmRzIHRoYXQgc3Vydml2"
    "ZSBzY3J1dGlueS4gVGhlIEVVIEFJIEFjdCwgdGhlIFVLIE9ubGluZSBTYWZldHkgQWN0LCBhbmQgdGhlIDIwMjQgUGF5bWVudCBT"
    "ZXJ2aWNlcyByZWltYnVyc2VtZW50IHJ1bGVzIGFsbCByZXF1aXJlIGFuIG9yZ2FuaXNhdGlvbiB0byBwcm92ZSB3aGF0IGl0cyBz"
    "eXN0ZW1zIGRpZCAmbWRhc2g7IG5vdCBhc3NlcnQgaXQsIHByb3ZlIGl0LjwvcD4KICA8cD5BbG1vc3QgZXZlcnkgb3JnYW5pc2F0"
    "aW9uIG1lZXRzIHRoYXQgZGVtYW5kIHdpdGggZGF0YWJhc2UgbG9ncyB0aGVpciBvd24gdGVhbSBjYW4gZWRpdC4gVGhhdCBpcyBu"
    "b3QgZXZpZGVuY2UsIGFuZCB0aGUgZGF5IGEgcmVndWxhdG9yLCBjb3VydCBvciBjdXN0b21lciBzdG9wcyB0YWtpbmcgdGhlaXIg"
    "d29yZCBmb3IgaXQsIHRoZXkgZGlzY292ZXIgdGhlIGdhcC4gPGI+VGhlIG1hcmtldCB0aGF0IGNsb3NlcyB0aGF0IGdhcCBkb2Vz"
    "IG5vdCByZWFsbHkgZXhpc3QgeWV0LjwvYj4gc2ViYmkucHJvIGlzIGFscmVhZHkgaW4gaXQuPC9wPgoKICA8ZGl2IGNsYXNzPSJw"
    "dWxsIj5BIGxvZyB5b3UgY2FuIGVkaXQgdGVsbHMgcGVvcGxlIHdoYXQgeW91IGN1cnJlbnRseSBjbGFpbSBoYXBwZW5lZC4gSXQg"
    "Y2Fubm90IHRlbGwgdGhlbSBub2JvZHkgY2hhbmdlZCBpdCBzaW5jZS4gT25seSBvbmUgb2YgdGhvc2UgaXMgd29ydGggYW55dGhp"
    "bmcgd2hlbiBpdCBtYXR0ZXJzLjwvZGl2PgoKICA8ZGl2IGNsYXNzPSJjb3VudGRvd24iPgogICAgPGRpdiBjbGFzcz0iY291bnRk"
    "b3duLWxhYmVsIj5VbnRpbCBoaWdoLXJpc2sgQUkgb2JsaWdhdGlvbnMgYXBwbHk8L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNvdW50"
    "ZG93bi1kYXlzIG1vbm8iIGlkPSJjb3VudGRvd24tZGF5cyI+Jm1kYXNoOyBkYXlzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjb3Vu"
    "dGRvd24tc3ViIj5Db3VudGluZyB0byAyIERlY2VtYmVyIDIwMjcuIFRoZSBldmlkZW5jZSB0aGVzZSBvYmxpZ2F0aW9ucyByZXF1"
    "aXJlIGlzIGhpc3RvcmljYWwgJm1kYXNoOyBpdCBjYW5ub3QgYmUgY3JlYXRlZCBhZnRlciB0aGUgZmFjdC4gRXZlcnkgb3JnYW5p"
    "c2F0aW9uIG5vdCByZWNvcmRpbmcgbm93IGlzIGFjY3J1aW5nIGEgZ2FwIGl0IGNhbiBuZXZlciBmaWxsLiBUaGF0IGlzIHRoZSBi"
    "dXlpbmcgcHJlc3N1cmUsIGFuZCBpdCBvbmx5IGdyb3dzLjwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImJsb2Nr"
    "Ij4KICA8ZGl2IGNsYXNzPSJibG9jay1udW0iPjAyICZtZGFzaDsgV2hhdCBpcyBhbHJlYWR5IGJ1aWx0PC9kaXY+CiAgPGgyPkxp"
    "dmUgaW4gcHJvZHVjdGlvbi4gTm90IGEgZGVjaywgbm90IGEgZGVtby48L2gyPgogIDxwPlRoaXMgcnVucyB0b2RheSwgb24gcmVh"
    "bCBpbmZyYXN0cnVjdHVyZSwgYW5kIGV2ZXJ5IGNsYWltIGJlbG93IGNhbiBiZSB2ZXJpZmllZCBieSBhIHRoaXJkIHBhcnR5IHdp"
    "dGggbm8gYWNjb3VudCBhbmQgbm8gcGVybWlzc2lvbi4gU2l4IHByb2R1Y3RzIG9uIG9uZSBlbmdpbmUsIG9uZSB0YW1wZXItZXZp"
    "ZGVudCBjaGFpbiB1bmRlcm5lYXRoIGFsbCBvZiB0aGVtLjwvcD4KCiAgPGRpdiBjbGFzcz0icHJvb2YtZ3JpZCI+CiAgICA8ZGl2"
    "IGNsYXNzPSJwcm9vZiI+PGRpdiBjbGFzcz0icHJvb2YtbiBtb25vIj42PC9kaXY+PGRpdiBjbGFzcz0icHJvb2YtbCI+UHJvZHVj"
    "dHMsIG9uZSBlbmdpbmU8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1zcmMiPkFJTGVhc2gsIEd1YXJkaWFuLCBTZW50aW5lbCwgU29u"
    "aWNCb29tLCBTZWJkb2csIFRva2VuIFNhdmVyPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwcm9vZiI+PGRpdiBjbGFzcz0i"
    "cHJvb2YtbiBtb25vIj5+MjhtczwvZGl2PjxkaXYgY2xhc3M9InByb29mLWwiPk1lZGlhbiBkZWNpc2lvbiB0aW1lPC9kaXY+PGRp"
    "diBjbGFzcz0icHJvb2Ytc3JjIj5EZXRlcm1pbmlzdGljLCBvbiBsaXZlIHRyYWZmaWM8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xh"
    "c3M9InByb29mIj48ZGl2IGNsYXNzPSJwcm9vZi1uIG1vbm8iPlNIQS0yNTY8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1sIj5IYXNo"
    "LWNoYWluZWQsIHRpbWVzdGFtcGVkIHBlciBwcm9vZjwvZGl2PjxkaXYgY2xhc3M9InByb29mLXNyYyI+Q3Jvc3Mtd2l0bmVzc2Vk"
    "IGJ5IGluZGVwZW5kZW50IHN5c3RlbXM8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InByb29mIj48ZGl2IGNsYXNzPSJwcm9v"
    "Zi1uIG1vbm8iPlB1YmxpYzwvZGl2PjxkaXYgY2xhc3M9InByb29mLWwiPlZlcmlmaWFibGUgd2l0aCB0aGUgdmVuZG9yIHN3aXRj"
    "aGVkIG9mZjwvZGl2PjxkaXYgY2xhc3M9InByb29mLXNyYyI+U3RhbmRhbG9uZSB2ZXJpZmllciwgbm8gYWNjb3VudDwvZGl2Pjwv"
    "ZGl2PgogIDwvZGl2PgoKICA8cCBzdHlsZT0ibWFyZ2luLXRvcDoxOHB4Ij5UaGUgd2hvbGUgcmFuZ2Ugc2hhcmVzIG9uZSBzcGlu"
    "ZTogZXZlcnkgZGVjaXNpb24gc2VhbGVkIGFzIGl0IGhhcHBlbnMsIHN1Ym1pdHRlZCBmb3IgZXh0ZXJuYWwgdGltZXN0YW1waW5n"
    "IHByb29mIGJ5IHByb29mLCBhbmQgd2l0bmVzc2VkIGhvdXJseSBieSBhbiBpbmRlcGVuZGVudCBwbGF0Zm9ybSAmbWRhc2g7IHVu"
    "YXR0ZW5kZWQsIHJ1bm5pbmcgbm93LiBBIHJlZ3VsYXRvciwgYW4gYXVkaXRvciBvciBhIGN1c3RvbWVyIGNoZWNrcyBhbnkgb2Yg"
    "aXQgdGhlbXNlbHZlcy4gVGhhdCBpcyB0aGUgcHJvZHVjdCwgYW5kIGl0IGV4aXN0cy48L3A+CjwvZGl2PgoKPGRpdiBjbGFzcz0i"
    "YmxvY2siPgogIDxkaXYgY2xhc3M9ImJsb2NrLW51bSI+MDMgJm1kYXNoOyBXaHkgaW5jdW1iZW50cyBjYW4ndCBmb2xsb3c8L2Rp"
    "dj4KICA8aDI+VGhlIG1vYXQgaXMgc3RydWN0dXJhbCwgbm90IGEgaGVhZCBzdGFydC48L2gyPgogIDxwPkV2ZXJ5IGxvZ2dpbmcs"
    "IG1vbml0b3JpbmcgYW5kIGF1ZGl0IHBsYXRmb3JtIG9uIHRoZSBtYXJrZXQga2VlcHMgYSByZWNvcmQgaXRzIG93biBjdXN0b21l"
    "ciBjb250cm9scy4gVGhhdCBpcyBub3QgYSBmbGF3IHRoZXkgY2FuIHBhdGNoICZtZGFzaDsgaXQgaXMgdGhlIGZvdW5kYXRpb24g"
    "dGhlaXIgYnVzaW5lc3Mgc3RhbmRzIG9uLiBUbyBtYXRjaCBzZWJiaS5wcm8gdGhleSB3b3VsZCBoYXZlIHRvIGdpdmUgdGhlIGN1"
    "c3RvbWVyIGEgcmVjb3JkIHRoZSBjdXN0b21lciBjYW5ub3QgZWRpdCwgd2hpY2ggYnJlYWtzIHRoZSB0aGluZyB0aGV5IHNlbGwu"
    "PC9wPgogIDx1bD4KICAgIDxsaT48Yj5UaGV5IGNhbid0IGNvcHkgdGhlIHF1ZXN0aW9uLjwvYj4gIkNhbiB0aGUgcGVvcGxlIGJl"
    "aW5nIGF1ZGl0ZWQgZWRpdCB0aGUgYXVkaXQ/IiBpbmRpY3RzIHRoZWlyIGVudGlyZSBjYXRlZ29yeS4gVGhleSBhbnN3ZXIgbm8g"
    "YnkgYWRtaXR0aW5nIHRoZWlyIGV2aWRlbmNlIHdhcyBuZXZlciBldmlkZW5jZS48L2xpPgogICAgPGxpPjxiPlRoZXkgY2FuJ3Qg"
    "Y29weSB0aGUgdGltZS48L2I+IEFuIHVuYnJva2VuLCBleHRlcm5hbGx5IHdpdG5lc3NlZCByZWNvcmQgaXMgdGhlIG9uZSBpbnB1"
    "dCBub2JvZHkgY2FuIHNob3J0Y3V0LiBUaGUgb25seSB3YXkgdG8gaGF2ZSBsYXN0IHllYXIgY292ZXJlZCB3YXMgdG8gYmUgcmVj"
    "b3JkaW5nIGxhc3QgeWVhci48L2xpPgogICAgPGxpPjxiPlRoZXkgY2FuJ3QgY29weSB0aGUgaG9uZXN0eS48L2I+IEV2ZXJ5IGNv"
    "bXBldGl0b3Igb3ZlcmNsYWltcy4gc2ViYmkucHJvIHB1Ymxpc2hlcyBpdHMgb3duIGxpbWl0cyBvbiBldmVyeSBwYWdlIGFuZCBz"
    "ZWFscyB0aGVtIGludG8gaXRzIG93biBjaGFpbiAmbWRhc2g7IHdoaWNoIGlzIGV4YWN0bHkgdGhlIHByb3BlcnR5IGEgYnV5ZXIg"
    "b2YgZXZpZGVuY2UgaW5mcmFzdHJ1Y3R1cmUgaXMgcGF5aW5nIGZvci48L2xpPgogIDwvdWw+CgogIDxkaXYgY2xhc3M9InZlcmlm"
    "eS1ib3giPgogICAgPGg0PlZlcmlmeSBpdCBiZWZvcmUgeW91IHJlYWQgYW5vdGhlciBsaW5lPC9oND4KICAgIDxwPk5vdGhpbmcg"
    "aGVyZSBhc2tzIHRvIGJlIGJlbGlldmVkLiA8Y29kZT4veC93aXRuZXNzL3RpcDwvY29kZT4gcmV0dXJucyB0aGUgbGl2ZSBjaGFp"
    "biB0aXAuIDxjb2RlPi94L290cy9zdGF0dXM8L2NvZGU+IHNob3dzIHRoZSBzdGF0ZSBvZiBlYWNoIGV4dGVybmFsIHRpbWVzdGFt"
    "cCBwcm9vZiAmbWRhc2g7IHN1Ym1pdHRlZCBpcyBub3QgY29uZmlybWVkLCBhbmQgdGhlIHBhZ2Ugc2F5cyB3aGljaCBpcyB3aGlj"
    "aC4gPGNvZGU+L3gvcm9zdGVyL2xpc3Q8L2NvZGU+IHNob3dzIHRoZSBpbmRlcGVuZGVudCBwbGF0Zm9ybXMgd2l0bmVzc2luZyBp"
    "dC48L3A+CiAgICA8cCBzdHlsZT0ibWFyZ2luLWJvdHRvbTowIj5BbGwgcHVibGljLCBhbGwgbmVlZCBubyBhY2NvdW50LCBhbGwg"
    "YW5zd2VyIHRvIGFueW9uZS4gVGhlIG9mZmxpbmUgdmVyaWZpZXIgcmVhY2hlcyBhIHZlcmRpY3Qgd2l0aCB0aGUgd2lmaSBvZmYu"
    "PC9wPgogIDwvZGl2Pgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImJsb2NrIj4KICA8ZGl2IGNsYXNzPSJibG9jay1udW0iPjA0ICZtZGFz"
    "aDsgVGhlIGVjb25vbWljczwvZGl2PgogIDxoMj5aZXJvIG1hcmdpbmFsIGNvc3QuIERpc3RyaWJ1dGlvbiBzY2FsZXMgd2l0aG91"
    "dCBoZWFkY291bnQuPC9oMj4KICA8cD5UaGUgc2FtZSBlbmdpbmUgc2VydmVzIG9uZSBjdXN0b21lciBvciB0ZW4gdGhvdXNhbmQg"
    "Jm1kYXNoOyBtYXJnaW5hbCBjb3N0IHBlciBhZGRpdGlvbmFsIGRldmljZSBpcyBlZmZlY3RpdmVseSB6ZXJvLiBUaGF0IG1ha2Vz"
    "IGRpc3RyaWJ1dGlvbiwgbm90IGVuZ2luZWVyaW5nLCB0aGUgZW50aXJlIGdyb3d0aCBsZXZlciwgYW5kIGl0IG1ha2VzIGEgcmVz"
    "ZWxsZXIgY2hhbm5lbCBwdXJlIG1hcmdpbiByYXRoZXIgdGhhbiBhIGNvc3QgbGluZS48L3A+CiAgPHA+PGI+NTBwIHBlciBhY3Rp"
    "dmUgZGV2aWNlIHBlciBtb250aDwvYj4sIG1ldGVyZWQgb24gcmVhbCB1c2FnZS4gUGFydG5lcnMgZW1iZWRkaW5nIHRoZSBwbGF0"
    "Zm9ybSBzZXQgdGhlaXIgb3duIGN1c3RvbWVyIHByaWNlIGFuZCBrZWVwIGV2ZXJ5dGhpbmcgYWJvdmUgdGhlIHBsYXRmb3JtIGZl"
    "ZS4gVGhlIHdpdG5lc3MgbmV0d29yayBzdGF5cyBmcmVlIGFuZCBvcGVuIGJ5IGRlc2lnbiAmbWRhc2g7IGl0IGlzIHRoZSBtZWNo"
    "YW5pc20gdGhhdCBtYWtlcyB0aGUgZXZpZGVuY2UgY3JlZGlibGUsIGFuZCBjaGFyZ2luZyBmb3IgaXQgd291bGQgd2Vha2VuIHRo"
    "ZSB0aGluZyBiZWluZyBzb2xkLjwvcD4KICA8cD5UaGUgcm91dGUgdG8gbWFya2V0IGlzIHRoZSBwbGF0Zm9ybXMsIG5vdCBvbmUg"
    "Y3VzdG9tZXIgYXQgYSB0aW1lLiBPdGhlciBjb21wbGlhbmNlIHBsYXRmb3JtcyBhbHJlYWR5IGhvbGQgcmVsYXRpb25zaGlwcyB3"
    "aXRoIHRoZSBleGFjdCBidXllcnMgd2hvIG5lZWQgdGhpcyBhbmQgYXJlIHVuaWZvcm1seSB3ZWFrIG9uIGV2aWRlbmNlLiBUaGUg"
    "ZW5naW5lIHNpdHMgdW5kZXJuZWF0aCB0aGVpciBwcm9kdWN0IGFzIHRoZSBldmlkZW5jZSBsYXllciB0aGV5IGNhbid0IGJ1aWxk"
    "IHRoZW1zZWx2ZXMuIEZpdmUgZm91bmRpbmcgc2VhdHM7IGZvdXIgYWxyZWFkeSB0YWtlbi48L3A+CjwvZGl2PgoKPGRpdiBjbGFz"
    "cz0iYmxvY2siPgogIDxkaXYgY2xhc3M9ImJsb2NrLW51bSI+MDUgJm1kYXNoOyBUaGUgYXNrPC9kaXY+CiAgPGgyPk9uZSBvcGVy"
    "YXRpbmcgcGFydG5lci4gMzAlIG9mIHRoZSBidXNpbmVzcy48L2gyPgogIDxkaXYgY2xhc3M9ImFzay1ib3giPgogICAgPGRpdiBj"
    "bGFzcz0iYXNrLWxhYmVsIj5PZmZlcmVkPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJhc2stYW1vdW50Ij4zMCUgZm9yIHRoZSByaWdo"
    "dDxicj5vcGVyYXRpbmcgcGFydG5lcjwvZGl2PgogICAgPHA+QnVpbHQgYW5kIHJ1biBhdCBuZWFyLXplcm8gZml4ZWQgY29zdCwg"
    "bGl2ZSBhbmQgcHJvdmVuLiBFdmVyeXRoaW5nIHRoZSBoYXJkIG1vbmV5IHVzdWFsbHkgZnVuZHMgaXMgYWxyZWFkeSBkb25lLiBU"
    "aGUgcGFydG5lciB3aG8gY2FuIG9wZW4gcmVndWxhdGVkIGVudGVycHJpc2UgYW5kIGdvdmVybm1lbnQgJm1kYXNoOyA8Yj5kZWZl"
    "bmNlLCBoZWFsdGhjYXJlLCB0ZWxlY29tbXVuaWNhdGlvbnM8L2I+ICZtZGFzaDsgdGFrZXMgYSBzdWJzdGFudGlhbCBzdGFrZSBp"
    "biBhIHBsYXRmb3JtIHRoYXQgaXMgcmVhZHkgdG8gc2NhbGUgdGhlIGRheSB0aGV5IHdhbGsgaW4uPC9wPgogICAgPGRpdiBjbGFz"
    "cz0idXNlLW9mLWZ1bmRzIj4KICAgICAgPGRpdiBjbGFzcz0idWYtcm93Ij48c3Bhbj5SZWd1bGF0ZWQgZW50ZXJwcmlzZSAmYW1w"
    "OyBnb3Zlcm5tZW50IGNoYW5uZWwgYWNjZXNzPC9zcGFuPjxzcGFuIGNsYXNzPSJ1Zi1wY3QiPmNvcmU8L3NwYW4+PC9kaXY+CiAg"
    "ICAgIDxkaXYgY2xhc3M9InVmLXJvdyI+PHNwYW4+UmVzZWxsZXIgLyBNU1AgZGlzdHJpYnV0aW9uIGF0IHNjYWxlPC9zcGFuPjxz"
    "cGFuIGNsYXNzPSJ1Zi1wY3QiPmNvcmU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InVmLXJvdyI+PHNwYW4+RXh0ZXJu"
    "YWwgc2VjdXJpdHkgYXVkaXQgJmFtcDsgbGVnYWwgcmV2aWV3IG9mIGNsYWltczwvc3Bhbj48c3BhbiBjbGFzcz0idWYtcGN0Ij5m"
    "dW5kPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJ1Zi1yb3ciPjxzcGFuPkluZnJhc3RydWN0dXJlIGhhcmRlbmluZyBm"
    "b3IgZW50ZXJwcmlzZSBsb2FkPC9zcGFuPjxzcGFuIGNsYXNzPSJ1Zi1wY3QiPmZ1bmQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4K"
    "ICA8L2Rpdj4KICA8cCBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij5UaGVzZSBhcmUgc2VjdG9ycyB3aGVyZSBldmlkZW5jZSBvYmxp"
    "Z2F0aW9ucyBhcmUgaGFyZGVzdCwgcHJvY3VyZW1lbnQgcnVucyBlaWdodGVlbiBtb250aHMsIGFuZCBhIGZvdW5kZXIgYWxvbmUg"
    "ZG9lcyBub3QgZ2V0IGluIHRoZSByb29tLiBUaGUgZWNvbm9taWNzIHN1aXQgZXhhY3RseSB0aGF0OiBoaWdoLXZhbHVlLCBsb25n"
    "LWN5Y2xlLCBhbmQgc2VydmVkIGJ5IGFuIGVuZ2luZSB0aGF0IGNvc3RzIG5vdGhpbmcgbW9yZSB0byBydW4gYXQgYSB0aG91c2Fu"
    "ZCBjdXN0b21lcnMgdGhhbiBhdCBvbmUuPC9wPgo8L2Rpdj4KCjwvZGl2PgoKPGRpdiBjbGFzcz0iY29udGFjdC1ibG9jayB3cmFw"
    "Ij4KICA8ZGl2IGNsYXNzPSJjb250YWN0LWNhcmQiPgogICAgPGgzPlRhbGsgdG8gdGhlIGZvdW5kZXIgZGlyZWN0bHk8L2gzPgog"
    "ICAgPHA+VGhlIGZ1bGwgdGVjaG5pY2FsIGRlbW9uc3RyYXRpb24gdGFrZXMgZmlmdGVlbiBtaW51dGVzLCBhbmQgZXZlcnkgY2xh"
    "aW0gb24gdGhpcyBwYWdlIGNhbiBiZSB2ZXJpZmllZCBsaXZlIGR1cmluZyBpdC48L3A+CiAgICA8ZGl2IGNsYXNzPSJjb250YWN0"
    "LWxpbmtzIj4KICAgICAgPGEgaHJlZj0ibWFpbHRvOmp1c3RyaWdodGRlY29yYXRvcnNAZ21haWwuY29tIj5qdXN0cmlnaHRkZWNv"
    "cmF0b3JzQGdtYWlsLmNvbTwvYT4KICAgICAgPGEgaHJlZj0iaHR0cHM6Ly9zZWJiaS5wcm8iPnNlYmJpLnBybzwvYT4KICAgICAg"
    "PGEgaHJlZj0iaHR0cHM6Ly9zZWJiaS5wcm8vbWFwIj5zZWJiaS5wcm8vbWFwICZtZGFzaDsgdGhlIHN5c3RlbSwgbWFwcGVkPC9h"
    "PgogICAgICA8YSBocmVmPSJodHRwczovL3NlYmJpLnByby93aGl0ZXBhcGVyIj5zZWJiaS5wcm8vd2hpdGVwYXBlcjwvYT4KICAg"
    "IDwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjxmb290ZXIgY2xhc3M9IndyYXAiPgogIDxwPkp1c3RpbiBBbnRvbnkgRG9ic29uICZt"
    "aWRkb3Q7IE1vbm9wIENvbnRlbnQgJm1pZGRvdDsgQmx5dGgsIE5vcnRodW1iZXJsYW5kLCBVSzxicj4KICBUaGlzIGRvY3VtZW50"
    "IGlzIGEgc3VtbWFyeSBmb3IgaW5mb3JtYXRpb24gYW5kIGRvZXMgbm90IGNvbnN0aXR1dGUgYW4gb2ZmZXIgb2Ygc2VjdXJpdGll"
    "cy4gQWxsIGZpZ3VyZXMgc2hvdWxkIGJlIGluZGVwZW5kZW50bHkgdmVyaWZpZWQgYmVmb3JlIGFueSBpbnZlc3RtZW50IGRlY2lz"
    "aW9uLiBSZWd1bGF0b3J5IGRhdGVzIGFyZSBzdGF0ZWQgYXMgYW1lbmRlZCBieSB0aGUgQUkgT21uaWJ1cyBhbmQgYXJlIHN1Ympl"
    "Y3QgdG8gY2hhbmdlLjwvcD4KPC9mb290ZXI+Cgo8c2NyaXB0PgogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdkb2MtZGF0ZScp"
    "LnRleHRDb250ZW50ID0gbmV3IERhdGUoKS50b0xvY2FsZURhdGVTdHJpbmcoJ2VuLUdCJyx7ZGF5OidudW1lcmljJyxtb250aDon"
    "bG9uZycseWVhcjonbnVtZXJpYyd9KTsKICB2YXIgZGVhZGxpbmUgPSBuZXcgRGF0ZSgnMjAyNy0xMi0wMlQwMDowMDowMFonKTsK"
    "ICB2YXIgbm93ID0gbmV3IERhdGUoKTsKICB2YXIgZGF5cyA9IE1hdGgubWF4KDAsIE1hdGguY2VpbCgoZGVhZGxpbmUgLSBub3cp"
    "IC8gKDEwMDAqNjAqNjAqMjQpKSk7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NvdW50ZG93bi1kYXlzJykudGV4dENvbnRl"
    "bnQgPSBkYXlzLnRvTG9jYWxlU3RyaW5nKCkgKyAnIGRheXMnOwo8L3NjcmlwdD4KCjwvYm9keT4KPC9odG1sPgo="
)

_HTML = base64.b64decode("".join(_B64.split())).decode("utf-8")
_patched = False


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _install_page(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_investor_patched", False):
        _patched = True
        return True
    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == PAGE_PATH:
            body = _HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._investor_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    if action == "spec":
        return ({
            "module": "investor",
            "version": VERSION,
            "serves": PAGE_PATH,
            "public": [["GET", "status"], ["GET", "spec"]],
            "note": "Hit /x/investor/status once after each deploy to arm " + PAGE_PATH + ".",
        }, 200)
    return ({
        "module": "investor",
        "version": VERSION,
        "serves": PAGE_PATH,
        "armed": armed,
        "page_bytes": len(_HTML),
    }, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```
