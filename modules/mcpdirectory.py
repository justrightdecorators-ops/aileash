"""
modules/mcpdirectory.py  v1.0.0
Make the sebbi.pro MCP connector pass the Anthropic Connectors Directory review.

The directory portal reads the connector's tools and refuses any that lack a
`title` and a `readOnlyHint` or `destructiveHint` annotation. The existing
tools in mcp.py (and the ones other modules add, like spendgate) only carry
name / description / inputSchema.

This module adds those annotations WITHOUT touching mcp.py or any other file.
It wraps mcp._rpc so that every `tools/list` response has each tool stamped
with a title and the right read/write hint at serve time - so it covers tools
added by any module, in any arm order, now or later.

Nothing is removed or changed: only the three annotation fields are added to
each tool, and only if they are missing. Re-arming is safe (idempotent).

Arm with everything else:  https://sebbi.pro/x/arm/status
Status on its own:         https://sebbi.pro/x/mcpdirectory/status
"""

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

# Explicit, human-friendly titles + read/write nature for the tools we know.
# (title, read_only)   read_only True  -> readOnlyHint True
#                      read_only False -> readOnlyHint False (a write; none are destructive)
KNOWN = {
    "sebbi_overview":          ("Overview of sebbi.pro", True),
    "sebbi_terms":             ("Read the terms", True),
    "sebbi_create_account":    ("Create an account", False),
    "sebbi_setup_advice":      ("Setup advice for your stack", True),
    "sebbi_test_decision":     ("Score and seal a test decision", False),
    "sebbi_pack_reference":    ("Signal Pack reference", True),
    "sebbi_check_pack":        ("Check a Signal Pack", True),
    "sebbi_publish_pack":      ("Publish a Signal Pack", False),
    "sebbi_list_packs":        ("List Signal Packs", True),
    "sebbi_decision_report":   ("Machine-proof decision report", True),
    "sebbi_check_human_proof": ("Check a Human Key", True),
    "sebbi_billing_link":      ("Get a billing link", False),
    "sebbi_verify_chain":      ("Verify the chain", True),
    "sebbi_spend_policy":      ("Set or read a spend policy", False),
    "sebbi_spend_request":     ("Request a spend sign-off", False),
    "sebbi_spend_verify":      ("Verify a spend token", True),
}

# Words that mean a tool only reads, used to classify any tool not in KNOWN.
_READ_WORDS = ("overview", "terms", "advice", "reference", "check", "list",
               "report", "verify", "status", "spec", "pubkey", "get", "read",
               "lookup", "search", "view", "show")
_WRITE_WORDS = ("create", "publish", "seal", "request", "submit", "account",
                "billing", "pay", "spend", "write", "add", "update", "set",
                "delete", "remove", "send")


def _pretty(name):
    s = name.replace("sebbi_", "").replace("_", " ").strip()
    return (s[:1].upper() + s[1:]) if s else name


def _infer_read_only(name):
    n = name.lower()
    for w in _WRITE_WORDS:
        if w in n:
            return False
    for w in _READ_WORDS:
        if w in n:
            return True
    return False  # unknown -> treat as a write so we never claim read-only wrongly


def _annotate(tool):
    try:
        name = tool.get("name", "")
    except Exception:
        return
    if not name:
        return
    title, read_only = KNOWN.get(name, (None, None))
    if title is None:
        title = _pretty(name)
    if read_only is None:
        read_only = _infer_read_only(name)
    # top-level title (some clients read it here)
    if not tool.get("title"):
        tool["title"] = title
    ann = tool.get("annotations")
    if not isinstance(ann, dict):
        ann = {}
        tool["annotations"] = ann
    ann.setdefault("title", title)
    if "readOnlyHint" not in ann and "destructiveHint" not in ann:
        ann["readOnlyHint"] = bool(read_only)
        # none of these tools delete or overwrite user data
        ann["destructiveHint"] = False
        if not read_only:
            ann["idempotentHint"] = False
        ann["openWorldHint"] = True


def _mcp():
    try:
        from modules import mcp as M
    except Exception:
        import mcp as M
    return M


def _install():
    M = _mcp()
    # annotate whatever is present right now (covers the common case)
    try:
        for t in getattr(M, "TOOLS", []):
            _annotate(t)
    except Exception:
        pass
    if getattr(M, "_directory_wrapped", False):
        return True
    orig_rpc = getattr(M, "_rpc", None)
    if not callable(orig_rpc):
        return False

    def _rpc(msg, ip, session):
        r = orig_rpc(msg, ip, session)
        try:
            if isinstance(msg, dict) and msg.get("method") == "tools/list" \
               and isinstance(r, dict):
                for t in r.get("result", {}).get("tools", []):
                    _annotate(t)
        except Exception:
            pass
        return r

    M._rpc = _rpc
    M._directory_wrapped = True
    return True


def handle(method, action, data, api_key, ctx):
    ok = False
    err = None
    try:
        ok = _install()
    except Exception as e:
        err = str(e)[:160]
    if action == "spec":
        return {"module": "mcpdirectory", "version": VERSION,
                "what": "Adds directory-required title + read/write hints to every MCP tool at serve time.",
                "known_tools": sorted(KNOWN.keys())}, 200
    return ({"module": "mcpdirectory", "version": VERSION, "armed": bool(ok),
             "wrapped": bool(getattr(_mcp(), "_directory_wrapped", False)),
             "last_error": err}, 200)
