"""
modules/integrity.py  v1.0  -  the AI Integrity Declaration, served publicly

Serves the open standard that rates every AI deployment from L0_DIARY
(no checkable record) up to L4_OVERSIGHT_VERIFIED. Read-only. Seals nothing,
writes nothing, creates no tables. Every route is public.

Routes:
  https://sebbi.pro/x/integrity/status       what this is, and the links
  https://sebbi.pro/x/integrity/declaration  the standard itself, as JSON
  https://sebbi.pro/x/integrity/spec         same as status

Other organisations publish their own declaration at
/.well-known/ai-integrity.json on their own domain. sebbi.pro serves the
standard here because /.well-known routes live in server.py, which is not
edited.
"""

import hashlib
import json

VERSION = "1.0"
BASE = "https://sebbi.pro/x/integrity/"

PUBLIC = {("GET", "status"), ("GET", "declaration"), ("GET", "spec")}

DECLARATION = json.loads(r'''{
  "spec": "ai-integrity-declaration",
  "version": "1.0.0",
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
    "path": "/.well-known/ai-integrity.json",
    "rule": "Every AI deployment is rated. A deployment with no declaration at this path is rated L0_DIARY. Absence is itself the result.",
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
      "test": "Any discontinuity in the chain, or change of meaning, has a matching disclosure block.",
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
        "disclosure_block": ""
      }
    ]
  },
  "reference_implementation": {
    "name": "sebbi.pro",
    "walk": "https://sebbi.pro/x/walk/status",
    "method": "https://sebbi.pro/x/walk/spec",
    "genesis": "https://sebbi.pro/x/walk/genesis",
    "discontinuity_example": "https://sebbi.pro/x/walk/block?index=2013"
  }
}''')

_CANONICAL = json.dumps(DECLARATION, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False)
DECLARATION_SHA256 = hashlib.sha256(_CANONICAL.encode("utf-8")).hexdigest()


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
            "ordering_test": "https://sebbi.pro/.well-known/ordering-test.json",
            "walk": "https://sebbi.pro/x/walk/status",
        },
        "how_to_adopt": "Publish your own filled-in declaration_template at "
                        "/.well-known/ai-integrity.json on your own domain. "
                        "No declaration there is rated L0_DIARY.",
        "hash_note": "declaration_sha256 is SHA-256 of the declaration as "
                     "compact JSON with sorted keys, so anyone can confirm "
                     "the text they are reading is the text published.",
    }


def handle(method, action, data, api_key, ctx):
    if method == "GET" and action in ("status", "spec", ""):
        return _status(), 200
    if method == "GET" and action == "declaration":
        return DECLARATION, 200
    return {"ok": False, "error": "unknown_action",
            "get": sorted(a for m, a in PUBLIC if m == "GET"),
            "post": []}, 404
