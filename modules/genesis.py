"""
Chain identity - /x/genesis/<action>

WHY THIS EXISTS
---------------
A receipt that does not say which chain state it belongs to is ambiguous the
moment a chain is ever reset, and this one was: on 7 September 2026, during
registry work, the chain was reset. Receipts issued before that date belong to
a state that does not continue forward. Nothing in those receipts says so, and
a peer holding one has no way to discover it from the receipt itself.

Philip Pinol (PRAXIS / ThePraesidium.ai) independently verified block 846 of
the prior state. That verification was sound for the state it was performed
against. It is not continuous with the chain running now, and saying so is
this module's job.

WHAT IT DOES
------------
Publishes the genesis hash of the current chain state and a short stable
identifier derived from it, so any party can pin their own records to a named
state rather than to a block number that may refer to two different things.

    chain_id = first 16 characters of the genesis block's audit hash

Deliberately a slice rather than a computation. Anyone can confirm the
identifier against the genesis hash by eye, in the response that carries both,
without running anything.

WHY IT IS A SEPARATE MODULE
---------------------------
Read-only, by construction. It opens the same database as the sealing code and
never writes to it: no inserts, no schema changes, no seal calls. A fault here
returns a 500 on this route and the chain carries on sealing, because the
module that seals does not import this one and does not know it exists.

That is not tidiness. Editing a file that writes an append-only chain in order
to add a reporting route is how the 7 September reset happened.

WHAT IT DOES NOT CLAIM
----------------------
- It does not assert when the reset occurred. It reports the sealed timestamp
  of block 1 as the database holds it, and states the reset date separately as
  a claim by the operator. If the two disagree, the disagreement is visible in
  the response rather than resolved quietly here.
- A chain_id identifies a state. It says nothing about whether the records in
  that state are true, complete, or externally anchored. Check /x/ots/status
  for anchoring and /api/verify-chain for internal validity.
- Two different deployments could in principle produce the same 16-character
  identifier. The full genesis hash is returned alongside it and is what
  should be pinned where collision matters.

    GET /x/genesis/chain    genesis hash, chain_id, height, current tip
    GET /x/genesis/status   is this module loaded and can it read the chain
    GET /x/genesis/spec     what the identifier is and how to pin it
"""

from datetime import datetime, timezone

VERSION = "1.0.0"

# Length of the genesis hash used as the chain identifier. Sixteen hex
# characters is 64 bits - long enough that two states will not collide by
# accident, short enough to quote in an email without wrapping.
CHAIN_ID_LEN = 16

# Routes that need no API key. A third party must be able to establish which
# chain state a receipt belongs to without holding an account, or the receipt
# is only checkable by customers.
PUBLIC = {("GET", "chain"), ("GET", "status"), ("GET", "spec")}

# ----------------------------------------------------------------------
# everything a reader sees
# ----------------------------------------------------------------------

RESET_RECORD = {
    "occurred": "2026-09-07",
    "reason": "chain reset during registry work",
    "effect": (
        "Receipts, block indexes and audit hashes issued before this date "
        "belong to a prior chain state. That state does not continue forward "
        "into the chain running now. A block index from before the reset and "
        "a block index from after it are not comparable and do not refer to "
        "the same sequence."),
    "prior_verification": (
        "Block 846 of the prior state was independently verified by Philip "
        "Pinol (PRAXIS / ThePraesidium.ai). That verification was sound for "
        "the state it was performed against. It is not evidence about the "
        "current state, and neither party describes it as continuous with it."),
    "what_was_not_lost": (
        "The prior state's records were sealed under the rules in force at "
        "the time and were valid under them. What changed is that the "
        "sequence does not extend. Nothing here claims the earlier records "
        "were wrong."),
    "disclosed_because": (
        "A peer holding a pre-reset receipt cannot discover any of this from "
        "the receipt itself. Published rather than left for someone to find "
        "when their records fail to reconcile."),
}

VOCABULARY = {
    "chain_id": (
        "A short stable identifier for one chain state, being the first %d "
        "characters of that state's genesis block hash. Pin your records to "
        "this rather than to a block index. If a chain is ever reset, the "
        "chain_id changes and the mismatch is visible immediately; a block "
        "index silently refers to a different thing." % CHAIN_ID_LEN),
    "genesis_hash": (
        "The audit hash of block 1 of the current chain state. This is the "
        "value to pin where a 16-character identifier is not enough. It does "
        "not change for the life of the state."),
    "genesis_sealed_at": (
        "The timestamp stored against block 1, as the database holds it. It "
        "is this deployment's own clock at the moment that block was written "
        "and is not evidence of when anything happened. The external "
        "timestamp proofs at /x/ots/status are the answer to that question."),
    "height": (
        "How many blocks the current state holds. Counts from block 1 of this "
        "state, not from the beginning of any prior state."),
    "current_tip": (
        "The audit hash of the most recent block. Changes constantly. "
        "Included so one call establishes the whole identity of the state; "
        "/x/witness/tip is the route to poll."),
}


def _iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _first_block(ctx):
    """Block 1 of the current state. Read-only."""
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT audit_hash,ts,id FROM audit_log ORDER BY id ASC LIMIT 1"
        ).fetchone()


def _last_block(ctx):
    """Current tip. Read-only. Same query witness.py uses, deliberately."""
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT audit_hash,ts,id FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()


def _chain(ctx):
    first = _first_block(ctx)
    if not first:
        return {"error": "no_genesis",
                "message": ("The audit chain holds no blocks, so there is no "
                            "genesis to report. This is an empty chain rather "
                            "than a fault."),
                "genesis_version": VERSION}, 404

    genesis_hash = str(first[0])
    chain_id = genesis_hash[:CHAIN_ID_LEN]
    last = _last_block(ctx)

    out = {
        "chain_id": chain_id,
        "genesis_hash": genesis_hash,
        "genesis_block_index": first[2],
        "genesis_sealed_at": _iso(first[1]),
        "height": last[2] if last else first[2],
        "current_tip": last[0] if last else genesis_hash,
        "current_sealed_at": _iso(last[1]) if last else _iso(first[1]),
        "genesis_version": VERSION,
        "reset_record": RESET_RECORD,
        "vocabulary": VOCABULARY,
        "how_to_pin": (
            "Record chain_id alongside every receipt you hold from this "
            "deployment. When you later check a receipt, read this route "
            "first: if chain_id has changed, your receipt belongs to a state "
            "that no longer continues and no block index in it is comparable "
            "to a current one."),
        "verify_the_identifier": (
            "chain_id is the first %d characters of genesis_hash. Both are in "
            "this response. Check it by eye - nothing needs to be run."
            % CHAIN_ID_LEN),
        "this_does_not_establish": (
            "That the records in this state are true, complete, or externally "
            "anchored. /api/verify-chain checks the chain end to end. "
            "/x/ots/status shows the state of each external timestamp proof."),
    }

    # State rather than assert. If the sealed timestamp of block 1 predates
    # the reset date, the two disagree and the reader should see that here
    # rather than be told a tidy story.
    sealed = out["genesis_sealed_at"]
    if sealed and sealed[:10] != RESET_RECORD["occurred"]:
        out["date_note"] = (
            "The sealed timestamp of block 1 (%s) is not the reset date "
            "stated in reset_record (%s). Both values are reported as they "
            "are. Reconcile them against the external timestamp proofs rather "
            "than against either party's account."
            % (sealed[:10], RESET_RECORD["occurred"]))

    return out, 200


def _status(ctx):
    """Arming route. Says whether this module loaded and can read the chain."""
    readable = False
    detail = None
    try:
        readable = _first_block(ctx) is not None
        if not readable:
            detail = "chain is readable and holds no blocks"
    except Exception as exc:
        detail = "could not read the audit chain (%s)" % type(exc).__name__

    return {"module": "genesis",
            "version": VERSION,
            "chain_readable": readable,
            "detail": detail,
            "writes": "none - this module never writes to the database",
            "routes": sorted(a for _m, a in PUBLIC),
            "genesis_version": VERSION}, 200


def _spec():
    return {"module": "genesis",
            "genesis_version": VERSION,
            "purpose": (
                "Publishes which chain state this deployment is running, so a "
                "receipt can be pinned to a named state rather than to a "
                "block index that may refer to two different sequences."),
            "chain_id_rule": (
                "The first %d characters of the genesis block's audit hash. "
                "Not a hash of a hash, not a derived key - a slice, so it can "
                "be checked by eye against the genesis hash returned beside "
                "it." % CHAIN_ID_LEN),
            "routes": {
                "GET /x/genesis/chain": "chain_id, genesis hash, height, tip",
                "GET /x/genesis/status": "module loaded, chain readable",
                "GET /x/genesis/spec": "this document",
            },
            "vocabulary": VOCABULARY,
            "reset_record": RESET_RECORD,
            "read_only": (
                "This module performs no writes of any kind. It opens the "
                "same database the sealing code uses and issues two SELECT "
                "statements. A fault here cannot affect the chain."),
            "related": {
                "/x/witness/tip": "current tip, for peers to record",
                "/api/verify-chain": "checks this chain end to end",
                "/x/ots/status": "state of each external timestamp proof",
            }}, 200


def handle(method, action, data, api_key, ctx):
    if method == "GET":
        if action == "chain":
            return _chain(ctx)
        if action == "status":
            return _status(ctx)
        if action == "spec":
            return _spec()
    return {"error": "unknown_action", "action": action,
            "routes": sorted(a for _m, a in PUBLIC)}, 404
