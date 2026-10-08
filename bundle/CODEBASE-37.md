# Codebase — part 37 of 54

Contains:
- `forever_verify.py`
- `gateway_proxy.py`
- `mcp_server.py`
- `meshwitness.py`
- `sebbi_agent.py`
- `sebbi_benchmark.py`


## `forever_verify.py`

685 lines, 27602 bytes

```python
#!/usr/bin/env python3
"""
forever_verify.py  v1.0.0  -  check a sebbi.pro Forever Proof against Bitcoin

    Download:  https://sebbi.pro/forever-verify.py
    Use:       python3 forever-verify.py proof.json
               python3 forever-verify.py proof.json --file contract.pdf
               python3 forever-verify.py proof.json --text essay.txt
               python3 forever-verify.py proof.json --node        (use your own Bitcoin node)

A Forever Proof is a small JSON file. It shows that one fingerprint existed
before a particular Bitcoin block was mined. This script checks every step
itself, with nothing but Python's standard library:

  1. the fingerprint is folded up its Merkle path to the batch root
  2. the root is the digest the OpenTimestamps proof starts from
  3. every operation in the OpenTimestamps proof is replayed
  4. the result is compared with the Merkle root of the Bitcoin block it
     names, fetched from two independent block explorers - or from your own
     Bitcoin node with --node, or typed in by hand with --merkle-root

Nothing here asks sebbi.pro anything. If sebbi.pro disappeared tomorrow this
file, the proof and the Bitcoin blockchain are all you need.

The same code runs inside sebbi.pro to build and read proofs, so what you run
is exactly what we run.
"""

import hashlib
import json
import subprocess
import sys
import unicodedata
import urllib.request

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# OpenTimestamps proof format
# ---------------------------------------------------------------------------

HEADER_MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
MAJOR_VERSION = 1

TAG_BITCOIN = bytes.fromhex("0588960d73d71901")
TAG_PENDING = bytes.fromhex("83dfe30d2ef90c8e")
TAG_LITECOIN = bytes.fromhex("06869a0d73d71b45")
TAG_ETHEREUM = bytes.fromhex("30fe8087b5c7ead7")

OP_SHA1, OP_RIPEMD160, OP_SHA256, OP_KECCAK256 = 0x02, 0x03, 0x08, 0x67
OP_APPEND, OP_PREPEND, OP_REVERSE, OP_HEXLIFY = 0xF0, 0xF1, 0xF2, 0xF3
UNARY = {OP_SHA1, OP_RIPEMD160, OP_SHA256, OP_KECCAK256, OP_REVERSE, OP_HEXLIFY}
BINARY = {OP_APPEND, OP_PREPEND}
OP_NAMES = {OP_SHA1: "sha1", OP_RIPEMD160: "ripemd160", OP_SHA256: "sha256", OP_KECCAK256: "keccak256",
            OP_APPEND: "append", OP_PREPEND: "prepend", OP_REVERSE: "reverse", OP_HEXLIFY: "hexlify"}

MAX_MSG = 4096
MAX_ARG = 4096
MAX_DEPTH = 256
MAX_PAYLOAD = 8192


class ProofError(ValueError):
    pass


class _Reader(object):
    def __init__(self, raw):
        self.raw = raw
        self.at = 0

    def take(self, n):
        if n < 0 or self.at + n > len(self.raw):
            raise ProofError("proof ends early")
        out = self.raw[self.at:self.at + n]
        self.at += n
        return out

    def byte(self):
        return self.take(1)[0]

    def varuint(self):
        value, shift = 0, 0
        while True:
            b = self.byte()
            value |= (b & 0x7F) << shift
            if not b & 0x80:
                return value
            shift += 7
            if shift > 63:
                raise ProofError("number too long")

    def varbytes(self, limit):
        n = self.varuint()
        if n > limit:
            raise ProofError("field too long")
        return self.take(n)

    def done(self):
        return self.at == len(self.raw)


def _w_varuint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _w_varbytes(b):
    return _w_varuint(len(b)) + b


def _ripemd160(msg):
    try:
        return hashlib.new("ripemd160", msg).digest()
    except Exception:
        return _ripemd160_pure(msg)


def apply_op(tag, arg, msg):
    if tag == OP_SHA256:
        return hashlib.sha256(msg).digest()
    if tag == OP_SHA1:
        return hashlib.sha1(msg).digest()
    if tag == OP_RIPEMD160:
        return _ripemd160(msg)
    if tag == OP_KECCAK256:
        return _keccak256(msg)
    if tag == OP_APPEND:
        out = msg + arg
    elif tag == OP_PREPEND:
        out = arg + msg
    elif tag == OP_REVERSE:
        out = msg[::-1]
    elif tag == OP_HEXLIFY:
        out = msg.hex().encode()
    else:
        raise ProofError("unknown operation 0x%02x" % tag)
    if len(out) > MAX_MSG:
        raise ProofError("message grew too long")
    return out


class Timestamp(object):
    """A commitment tree: a message, what it is attested by, and what it becomes."""

    def __init__(self, msg):
        self.msg = msg
        self.attestations = []   # (tag, payload) - payload is the raw attestation body
        self.ops = []            # ((tag, arg), Timestamp)

    # -- reading
    @classmethod
    def parse(cls, reader, msg, depth=0):
        if depth > MAX_DEPTH:
            raise ProofError("proof nested too deeply")
        ts = cls(msg)

        def item(tag):
            if tag == 0x00:
                atag = reader.take(8)
                payload = reader.varbytes(MAX_PAYLOAD)
                ts.attestations.append((atag, payload))
            elif tag in UNARY or tag in BINARY:
                arg = reader.varbytes(MAX_ARG) if tag in BINARY else b""
                if tag in BINARY and not arg:
                    raise ProofError("empty argument")
                child = cls.parse(reader, apply_op(tag, arg, msg), depth + 1)
                ts.ops.append(((tag, arg), child))
            else:
                raise ProofError("unknown tag 0x%02x" % tag)

        tag = reader.byte()
        while tag == 0xFF:
            item(reader.byte())
            tag = reader.byte()
        item(tag)
        return ts

    @classmethod
    def from_bytes(cls, raw, msg):
        r = _Reader(raw)
        ts = cls.parse(r, msg)
        if not r.done():
            raise ProofError("unexpected bytes after the proof")
        return ts

    # -- writing (the same canonical order as the reference client)
    def serialize(self):
        out = bytearray()
        atts = sorted(self.attestations)
        ops = sorted(self.ops, key=lambda o: o[0])
        if not atts and not ops:
            raise ProofError("empty timestamp")
        for tag, payload in atts[:-1]:
            out += b"\xff\x00" + tag + _w_varbytes(payload)
        if atts:
            out += (b"\xff\x00" if ops else b"\x00") + atts[-1][0] + _w_varbytes(atts[-1][1])
        for i, ((tag, arg), child) in enumerate(ops):
            if i < len(ops) - 1:
                out += b"\xff"
            out += bytes([tag]) + (_w_varbytes(arg) if tag in BINARY else b"")
            out += child.serialize()
        return bytes(out)

    # -- combining
    def merge(self, other):
        if other.msg != self.msg:
            raise ProofError("cannot merge timestamps of different messages")
        for a in other.attestations:
            if a not in self.attestations:
                self.attestations.append(a)
        for op, child in other.ops:
            for mine_op, mine_child in self.ops:
                if mine_op == op:
                    mine_child.merge(child)
                    break
            else:
                self.ops.append((op, child))

    # -- walking
    def walk(self, path=None):
        """Yield (msg, tag, payload, path) for every attestation in the tree."""
        path = path or []
        for tag, payload in self.attestations:
            yield self.msg, tag, payload, path
        for op, child in self.ops:
            for x in child.walk(path + [op]):
                yield x

    def nodes(self):
        yield self
        for _, child in self.ops:
            for n in child.nodes():
                yield n


def describe_attestation(tag, payload):
    try:
        r = _Reader(payload)
        if tag == TAG_BITCOIN:
            return {"kind": "bitcoin", "height": r.varuint()}
        if tag == TAG_PENDING:
            uri = r.varbytes(1000).decode("utf-8", "replace")
            return {"kind": "pending", "calendar": uri}
        if tag == TAG_LITECOIN:
            return {"kind": "litecoin", "height": r.varuint()}
        if tag == TAG_ETHEREUM:
            return {"kind": "ethereum", "height": r.varuint()}
    except ProofError:
        pass
    return {"kind": "unknown", "tag": tag.hex()}


def pending_payload(uri):
    return _w_varbytes(uri.encode("utf-8"))


def parse_detached(raw):
    """Read a .ots file. Returns (hash_op_tag, digest, Timestamp)."""
    r = _Reader(raw)
    if r.take(len(HEADER_MAGIC)) != HEADER_MAGIC:
        raise ProofError("not an OpenTimestamps proof")
    if r.varuint() != MAJOR_VERSION:
        raise ProofError("unsupported proof version")
    op = r.byte()
    size = {OP_SHA256: 32, OP_SHA1: 20, OP_RIPEMD160: 20, OP_KECCAK256: 32}.get(op)
    if size is None:
        raise ProofError("unsupported file hash")
    digest = r.take(size)
    ts = Timestamp.parse(r, digest)
    if not r.done():
        raise ProofError("unexpected bytes after the proof")
    return op, digest, ts


def serialize_detached(digest, ts, op=OP_SHA256):
    return HEADER_MAGIC + _w_varuint(MAJOR_VERSION) + bytes([op]) + digest + ts.serialize()


def summarise(ts):
    out = {"bitcoin": [], "pending": [], "other": []}
    for msg, tag, payload, _ in ts.walk():
        d = describe_attestation(tag, payload)
        if d["kind"] == "bitcoin":
            out["bitcoin"].append({"height": d["height"], "merkle_root": msg[::-1].hex()})
        elif d["kind"] == "pending":
            out["pending"].append(d["calendar"])
        else:
            out["other"].append(d)
    out["bitcoin"].sort(key=lambda b: b["height"])
    out["state"] = "confirmed" if out["bitcoin"] else ("pending" if out["pending"] else "unknown")
    return out


# ---------------------------------------------------------------------------
# RFC 6962 Merkle trees (the same tree sebbi.pro serves at /x/consistency/root)
# ---------------------------------------------------------------------------

def leaf_hash(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(b"\x00" + value).digest()


def node_hash(left, right):
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n):
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def merkle_root_of(leaf_hashes):
    """Root over already-hashed leaves, built bottom-up (no recursion limit)."""
    n = len(leaf_hashes)
    if n == 0:
        return hashlib.sha256(b"").digest()
    return _root_range(leaf_hashes, 0, n)


def _root_range(h, lo, hi):
    n = hi - lo
    if n == 1:
        return h[lo]
    k = _split(n)
    return node_hash(_root_range(h, lo, lo + k), _root_range(h, lo + k, hi))


def inclusion_path(leaf_hashes, index):
    """Audit path for one leaf, leaf upwards. Raw bytes list."""
    path = []
    lo, hi = 0, len(leaf_hashes)
    stack = []
    while hi - lo > 1:
        k = _split(hi - lo)
        if index < lo + k:
            stack.append(_root_range(leaf_hashes, lo + k, hi))
            hi = lo + k
        else:
            stack.append(_root_range(leaf_hashes, lo, lo + k))
            lo = lo + k
    while stack:
        path.append(stack.pop())
    return path


def root_from_path(leaf, index, size, path):
    """RFC 9162 section 2.1.3.2. Returns the root the path leads to, or None."""
    if index < 0 or index >= size:
        return None
    fn, sn, r = index, size - 1, leaf
    for p in path:
        if sn == 0:
            return None
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return r if sn == 0 else None


# ---------------------------------------------------------------------------
# what a fingerprint is, for each kind of proof
# ---------------------------------------------------------------------------

def human_text_hash(text):
    """The Human Keys fingerprint: NFC, \\n line endings, ends trimmed, SHA-256."""
    t = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def chain_block_hash(block):
    """The sebbi.pro chain hash of one block: SHA-256 of its JSON, keys sorted."""
    p = {"prev_hash": block["prev_hash"], "ts": block["ts"], "event": block["event"], "result": block["result"]}
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()


def notary_leaf(digest_hex):
    return "sebbi-notary/1|" + digest_hex.lower()


def humankeys_leaf(code, text_hash, verdict, sealed_at):
    return "sebbi-humankeys/1|%s|%s|%s|%d" % (code, text_hash, verdict, int(sealed_at))


# ---------------------------------------------------------------------------
# Bitcoin
# ---------------------------------------------------------------------------

EXPLORERS = ["https://mempool.space/api", "https://blockstream.info/api"]


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "forever-verify/" + VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def block_from_explorer(base, height):
    bhash = _get("%s/block-height/%d" % (base, height)).decode().strip()
    if len(bhash) != 64:
        raise ProofError("explorer gave no block hash")
    info = json.loads(_get("%s/block/%s" % (base, bhash)).decode())
    return {"source": base, "height": height, "hash": bhash,
            "merkle_root": str(info.get("merkle_root", "")).lower(), "time": info.get("timestamp")}


def block_from_node(height):
    bhash = subprocess.check_output(["bitcoin-cli", "getblockhash", str(height)], timeout=30).decode().strip()
    info = json.loads(subprocess.check_output(["bitcoin-cli", "getblockheader", bhash], timeout=30).decode())
    return {"source": "your own Bitcoin node", "height": height, "hash": bhash,
            "merkle_root": str(info.get("merkleroot", "")).lower(), "time": info.get("time")}


# ---------------------------------------------------------------------------
# checking a Forever Proof
# ---------------------------------------------------------------------------

def check(bundle, explorers=None, use_node=False, merkle_root=None, file_bytes=None, text=None, block=None):
    """Check every step of a Forever Proof. Returns a report; report["ok"] is the verdict."""
    steps = []

    def step(name, ok, detail):
        steps.append({"step": name, "ok": bool(ok), "detail": detail})
        return ok

    report = {"verifier": "forever_verify.py " + VERSION, "steps": steps, "ok": False}
    try:
        if bundle.get("format") != "sebbi-forever-proof/1":
            step("format", False, "this is not a sebbi.pro Forever Proof")
            return report
        subject = bundle.get("subject") or {}
        leaf = bundle.get("leaf")
        m = bundle.get("merkle") or {}
        kind = subject.get("kind")

        # 0. what you hold matches what was proven
        if kind == "hash" and file_bytes is not None:
            d = hashlib.sha256(file_bytes).hexdigest()
            if not step("your file", notary_leaf(d) == leaf,
                        "your file's SHA-256 is %s - %s" % (d, "it matches" if notary_leaf(d) == leaf else "it does NOT match")):
                return report
        if kind == "humankeys" and text is not None:
            th = human_text_hash(text)
            ok = th == subject.get("text_hash") and humankeys_leaf(subject.get("code"), th, subject.get("verdict"),
                                                                   subject.get("sealed_at", 0)) == leaf
            if not step("your text", ok, "your text's fingerprint is %s - %s" % (th, "it matches" if ok else "it does NOT match")):
                return report
        if kind == "humankeys":
            expect = humankeys_leaf(subject.get("code"), subject.get("text_hash"), subject.get("verdict"),
                                    subject.get("sealed_at", 0))
            if not step("Human Keys record", expect == leaf, "the code, fingerprint, verdict and time are what was anchored"):
                return report
        if kind == "hash" and leaf != notary_leaf(str(subject.get("digest", ""))):
            step("fingerprint", False, "the leaf does not match the fingerprint in the proof")
            return report
        if kind == "chain_block":
            if block is not None:
                h = chain_block_hash(block)
                if not step("your block", h == subject.get("audit_hash"),
                            "the block you supplied hashes to %s" % h):
                    return report
            if leaf != subject.get("audit_hash"):
                step("chain block", False, "the leaf is not the block's chain hash")
                return report

        # 1. leaf -> batch root
        lh = leaf_hash(leaf)
        root = root_from_path(lh, int(m.get("index", -1)), int(m.get("tree_size", 0)),
                              [bytes.fromhex(p) for p in m.get("path", [])])
        want_root = str(m.get("root", "")).lower()
        if not step("Merkle path", root is not None and root.hex() == want_root,
                    "fingerprint %d of %d folds up to root %s" % (int(m.get("index", -1)) + 1, int(m.get("tree_size", 0)), want_root)):
            return report

        # 2. root -> OpenTimestamps proof
        import base64
        raw = base64.b64decode((bundle.get("bitcoin") or {}).get("proof_ots_base64") or "")
        op, digest, ts = parse_detached(raw)
        if not step("OpenTimestamps proof", digest.hex() == want_root,
                    "the proof commits to exactly that root"):
            return report
        summary = summarise(ts)
        report["attestations"] = summary
        if not summary["bitcoin"]:
            step("Bitcoin", False, "the proof is still PENDING: a calendar has promised to put it into Bitcoin. "
                                   "This normally completes within a few hours. Download the proof again later.")
            report["pending"] = True
            return report

        # 3. the proof's result -> a real Bitcoin block
        for att in summary["bitcoin"]:
            h = att["height"]
            sources = []
            if merkle_root:
                sources.append({"source": "typed in by you", "height": h, "merkle_root": merkle_root.lower(), "time": None})
            elif use_node:
                sources.append(block_from_node(h))
            else:
                for base in (explorers or EXPLORERS):
                    try:
                        sources.append(block_from_explorer(base, h))
                    except Exception as e:
                        report.setdefault("notes", []).append("%s did not answer (%s)" % (base, str(e)[:80]))
            if not sources:
                step("Bitcoin block %d" % h, False, "no explorer could be reached - try --node or --merkle-root")
                continue
            agree = [s for s in sources if s["merkle_root"] == att["merkle_root"]]
            disagree = [s for s in sources if s["merkle_root"] != att["merkle_root"]]
            if agree and not disagree:
                when = agree[0].get("time")
                report["bitcoin_block"] = {"height": h, "hash": agree[0].get("hash"), "time": when,
                                           "checked_with": [s["source"] for s in agree]}
                step("Bitcoin block %d" % h, True,
                     "the proof ends at this block's Merkle root, confirmed by %s" % ", ".join(s["source"] for s in agree))
                report["ok"] = True
                report["existed_before_unix"] = when
                return report
            step("Bitcoin block %d" % h, False, "the block's Merkle root does not match the proof")
        return report
    except ProofError as e:
        step("proof", False, str(e))
        return report
    except Exception as e:
        step("proof", False, "could not read the proof: %s" % str(e)[:200])
        return report


# ---------------------------------------------------------------------------
# hash functions Python may not ship
# ---------------------------------------------------------------------------

def _keccak256(msg):
    """Keccak-256 (the original padding, as Ethereum and OpenTimestamps use it)."""
    RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B,
          0x0000000080000001, 0x8000000080008081, 0x8000000000008009, 0x000000000000008A, 0x0000000000000088,
          0x0000000080008009, 0x000000008000000A, 0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
          0x8000000000008003, 0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
          0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
    ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
    M = (1 << 64) - 1

    def rol(x, n):
        return ((x << n) | (x >> (64 - n))) & M if n else x

    rate = 136
    data = bytearray(msg) + b"\x01"
    while len(data) % rate:
        data.append(0)
    data[-1] |= 0x80
    s = [[0] * 5 for _ in range(5)]
    for off in range(0, len(data), rate):
        block = data[off:off + rate]
        for i in range(rate // 8):
            s[i % 5][i // 5] ^= int.from_bytes(block[i * 8:i * 8 + 8], "little")
        for rnd in range(24):
            c = [s[x][0] ^ s[x][1] ^ s[x][2] ^ s[x][3] ^ s[x][4] for x in range(5)]
            d = [c[(x - 1) % 5] ^ rol(c[(x + 1) % 5], 1) for x in range(5)]
            s = [[s[x][y] ^ d[x] for y in range(5)] for x in range(5)]
            b = [[0] * 5 for _ in range(5)]
            for x in range(5):
                for y in range(5):
                    b[y][(2 * x + 3 * y) % 5] = rol(s[x][y], ROT[x][y])
            s = [[b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
            s[0][0] ^= RC[rnd]
    out = b"".join(s[i % 5][i // 5].to_bytes(8, "little") for i in range(25))
    return out[:32]


def _ripemd160_pure(msg):
    def f(j, x, y, z):
        if j < 16:
            return x ^ y ^ z
        if j < 32:
            return (x & y) | (~x & z)
        if j < 48:
            return (x | ~y) ^ z
        if j < 64:
            return (x & z) | (y & ~z)
        return x ^ (y | ~z)

    def rol(x, n):
        x &= 0xFFFFFFFF
        return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF

    K1 = [0x00000000, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC, 0xA953FD4E]
    K2 = [0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x7A6D76E9, 0x00000000]
    R1 = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8,
          3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12, 1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2,
          4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13]
    R2 = [5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12, 6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2,
          15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13, 8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14,
          12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11]
    S1 = [11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8, 7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12,
          11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5, 11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12,
          9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6]
    S2 = [8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6, 9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11,
          9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5, 15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8,
          8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11]
    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
    data = bytearray(msg) + b"\x80"
    while len(data) % 64 != 56:
        data.append(0)
    data += (len(msg) * 8).to_bytes(8, "little")
    for off in range(0, len(data), 64):
        X = [int.from_bytes(data[off + 4 * i:off + 4 * i + 4], "little") for i in range(16)]
        a1, b1, c1, d1, e1 = h
        a2, b2, c2, d2, e2 = h
        for j in range(80):
            t = (rol(a1 + f(j, b1, c1, d1) + X[R1[j]] + K1[j // 16], S1[j]) + e1) & 0xFFFFFFFF
            a1, e1, d1, c1, b1 = e1, d1, rol(c1, 10), b1, t
            t = (rol(a2 + f(79 - j, b2, c2, d2) + X[R2[j]] + K2[j // 16], S2[j]) + e2) & 0xFFFFFFFF
            a2, e2, d2, c2, b2 = e2, d2, rol(c2, 10), b2, t
        t = (h[1] + c1 + d2) & 0xFFFFFFFF
        h[1] = (h[2] + d1 + e2) & 0xFFFFFFFF
        h[2] = (h[3] + e1 + a2) & 0xFFFFFFFF
        h[3] = (h[4] + a1 + b2) & 0xFFFFFFFF
        h[4] = (h[0] + b1 + c2) & 0xFFFFFFFF
        h[0] = t
    return b"".join(x.to_bytes(4, "little") for x in h)


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------

def _main(argv):
    import argparse
    p = argparse.ArgumentParser(description="Check a sebbi.pro Forever Proof against Bitcoin, with nothing from sebbi.pro.")
    p.add_argument("proof", help="the Forever Proof JSON file")
    p.add_argument("--file", help="the original file, to check it is the one that was proven")
    p.add_argument("--text", help="a text file holding the words of a Human Keys proof")
    p.add_argument("--block", help="a JSON file with the chain block (prev_hash, ts, event, result)")
    p.add_argument("--node", action="store_true", help="read the block from your own Bitcoin node (bitcoin-cli)")
    p.add_argument("--merkle-root", help="type the block's Merkle root in yourself")
    p.add_argument("--explorer", action="append", help="block explorer API base (Esplora style); may repeat")
    p.add_argument("--json", action="store_true", help="print the full report as JSON")
    a = p.parse_args(argv)

    with open(a.proof, "r", encoding="utf-8") as fh:
        bundle = json.load(fh)
    file_bytes = open(a.file, "rb").read() if a.file else None
    text = open(a.text, "r", encoding="utf-8").read() if a.text else None
    block = json.load(open(a.block, "r", encoding="utf-8")) if a.block else None
    rep = check(bundle, explorers=a.explorer, use_node=a.node, merkle_root=a.merkle_root,
                file_bytes=file_bytes, text=text, block=block)
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        print("sebbi.pro Forever Proof - checked by forever_verify.py %s\n" % VERSION)
        for s in rep["steps"]:
            print(("  PASS  " if s["ok"] else "  FAIL  ") + s["step"] + ": " + s["detail"])
        print()
        if rep["ok"]:
            import time
            b = rep["bitcoin_block"]
            when = time.strftime("%d %b %Y %H:%M UTC", time.gmtime(b["time"])) if b.get("time") else "the time of that block"
            print("VERIFIED. This existed before Bitcoin block %d (%s)." % (b["height"], when))
            print("Nothing from sebbi.pro was trusted to reach this answer.")
        elif rep.get("pending"):
            print("NOT YET IN BITCOIN. The proof is valid so far and waiting for its Bitcoin block.")
        else:
            print("NOT VERIFIED.")
    return 0 if rep["ok"] else (2 if rep.get("pending") else 1)


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))

```


## `gateway_proxy.py`

280 lines, 10922 bytes

```python
import asyncio
import ssl
import json
import hmac
import hashlib
import os
import time
import logging
import urllib.request
import urllib.error

# ============================================================
# AILEASH GATEWAY PROXY - real enforcement version
#
# How it's meant to be used:
#   Customer changes their AI SDK's base URL from
#     https://api.openai.com/v1
#   to
#     https://your-gateway-domain/openai/v1
#   (same for Anthropic under /anthropic/)
#
# Every request that arrives:
#   1. Gets scored by your real /api/govern endpoint (same
#      scoring + sealing logic as server.py - nothing duplicated).
#   2. If the decision is BLOCK, the request is rejected here.
#      The real OpenAI/Anthropic call is NEVER made. That's the
#      actual gate - not an email sent after the fact.
#   3. If ALLOW or CHALLENGE, the request is forwarded to the
#      real provider over a real TLS connection, and the real
#      response is streamed back untouched.
#
# This does NOT intercept traffic the customer sends directly
# to openai.com without going through this gateway. No proxy
# that doesn't install certificates on every device can do that
# for HTTPS traffic - that's a much bigger, separate product.
# This is the same integration pattern used by every commercial
# AI gateway (Cloudflare AI Gateway, Portkey, LiteLLM proxy, etc).
# ============================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GATEWAY] %(message)s")

PROXY_PORT = int(os.environ.get("GATEWAY_PORT", 8888))

# No fallback key. If this isn't set, refuse to start rather than
# run with a guessable signing key in production.
PROXY_SIGNING_KEY = os.environ.get("SEBBI_PROXY_SECRET", "").strip()
if not PROXY_SIGNING_KEY:
    raise SystemExit(
        "SEBBI_PROXY_SECRET is not set. Refusing to start - "
        "running with a default/fallback signing key is not safe. "
        "Set SEBBI_PROXY_SECRET in your environment (Railway variables) and restart."
    )
PROXY_SIGNING_KEY = PROXY_SIGNING_KEY.encode("utf-8")

# Where your real scoring/sealing engine lives. Point this at your
# own deployment - defaults to the live sebbi.pro API.
GOVERN_URL = os.environ.get("AILEASH_GOVERN_URL", "https://sebbi.pro/api/govern")

# Which real AI providers this gateway can forward to, and their
# real hostnames. Add more here if you support more providers.
PROVIDERS = {
    "openai": "api.openai.com",
    "anthropic": "api.anthropic.com",
}


def call_govern(ailleash_key: str, event: dict):
    """Call the real /api/govern endpoint and return (decision_json, http_status).
    This is a blocking network call - run it in a thread executor so it
    doesn't stall the async event loop."""
    body = json.dumps(event).encode("utf-8")
    req = urllib.request.Request(
        GOVERN_URL,
        data=body,
        headers={
            "Authorization": "Bearer " + ailleash_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {"decision": "BLOCK", "error": "govern_returned_unreadable_error"}, e.code
    except Exception as e:
        # Network failure, timeout, DNS issue, etc. Fail closed - if we
        # can't reach the compliance engine, we don't guess ALLOW.
        return {"decision": "BLOCK", "error": "govern_unreachable: " + str(e)}, 503


def parse_request(raw_head: bytes):
    """Parse the request line + headers from the raw bytes read up to \\r\\n\\r\\n."""
    text = raw_head.decode("utf-8", errors="ignore")
    lines = text.split("\r\n")
    request_line = lines[0]
    parts = request_line.split(" ")
    method = parts[0] if len(parts) > 0 else "GET"
    path = parts[1] if len(parts) > 1 else "/"
    headers = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    return method, path, headers


def build_forward_request(method, upstream_path, headers, body: bytes, upstream_host):
    """Rebuild the HTTP request to send to the real provider. Strips our
    own gateway-only headers and sets the correct Host."""
    drop = {"host", "x-sebbi-key", "x-sebbi-event", "content-length"}
    lines = [method + " " + upstream_path + " HTTP/1.1", "Host: " + upstream_host]
    for k, v in headers.items():
        if k in drop:
            continue
        lines.append(k + ": " + v)
    lines.append("Content-Length: " + str(len(body)))
    lines.append("Connection: close")
    head = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")
    return head + body


async def read_full_request(reader):
    """Read headers, then read exactly Content-Length bytes of body if present."""
    head = await reader.readuntil(b"\r\n\r\n")
    method, path, headers = parse_request(head)
    length = int(headers.get("content-length", "0") or "0")
    body = b""
    if length:
        body = await reader.readexactly(length)
    return method, path, headers, body


async def forward_to_provider(upstream_host, request_bytes: bytes):
    """Open a real TLS connection to the real provider and return the raw
    response bytes, unmodified."""
    ctx = ssl.create_default_context()
    reader, writer = await asyncio.open_connection(upstream_host, 443, ssl=ctx)
    try:
        writer.write(request_bytes)
        await writer.drain()
        response = await reader.read(-1)
        return response
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


def default_event(headers, device_id_fallback):
    """Build a sensible /api/govern event from what the customer sent,
    falling back to safe defaults for anything they didn't specify.
    Customers can override any field by sending an X-Sebbi-Event JSON header."""
    override = headers.get("x-sebbi-event")
    if override:
        try:
            ev = json.loads(override)
        except Exception:
            ev = {}
    else:
        ev = {}
    ev.setdefault("user_id", headers.get("x-sebbi-user", "gateway_anonymous"))
    ev.setdefault("action", "ai_request")
    ev.setdefault("amount", 0)
    ev.setdefault("country", headers.get("x-sebbi-country", "UK"))
    ev.setdefault("device_id", headers.get("x-sebbi-device", device_id_fallback))
    ev.setdefault("anomaly", 0)
    ev.setdefault("device_risk", 0)
    return ev


class ComplianceGatewayProxy:
    def __init__(self, host="0.0.0.0", port=PROXY_PORT):
        self.host = host
        self.port = port

    async def start(self):
        server = await asyncio.start_server(self.handle_client_traffic, self.host, self.port)
        logging.info("AILeash Gateway operational on :%s (real enforcement, real forwarding)", self.port)
        async with server:
            await server.serve_forever()

    async def handle_client_traffic(self, reader, writer):
        peer = writer.get_extra_info("peername")
        try:
            method, path, headers, body = await read_full_request(reader)
        except Exception as e:
            logging.warning("Bad request from %s: %s", peer, e)
            writer.close()
            return

        try:
            # Route: /openai/... or /anthropic/... selects the real provider.
            segments = path.strip("/").split("/", 1)
            provider_key = segments[0] if segments else ""
            upstream_path = "/" + segments[1] if len(segments) > 1 else "/"

            if provider_key not in PROVIDERS:
                self._reject(writer, 404, "unknown_provider",
                              "Path must start with /openai/ or /anthropic/")
                return

            ailleash_key = headers.get("x-sebbi-key", "")
            if not ailleash_key:
                self._reject(writer, 401, "missing_compliance_key",
                              "Include your AILeash API key in the X-Sebbi-Key header.")
                return

            device_id_fallback = str(peer[0]) if peer else "unknown_device"
            event = default_event(headers, device_id_fallback)

            loop = asyncio.get_event_loop()
            decision_json, status = await loop.run_in_executor(
                None, call_govern, ailleash_key, event
            )
            decision = decision_json.get("decision", "BLOCK")

            if status != 200 or decision == "BLOCK":
                logging.warning("[BLOCKED] %s -> %s (%s)", peer, provider_key, decision_json.get("reasons", decision_json.get("error", "")))
                self._reject(writer, 403, "compliance_block", None, decision_json)
                return

            # ALLOW or CHALLENGE both proceed - CHALLENGE just means the
            # customer's own code should show the user the verification
            # link included in decision_json. We don't invent enforcement
            # server.py doesn't have.
            upstream_host = PROVIDERS[provider_key]
            forward_bytes = build_forward_request(method, upstream_path, headers, body, upstream_host)

            real_response = await forward_to_provider(upstream_host, forward_bytes)

            tx_seal = hmac.new(PROXY_SIGNING_KEY, real_response[:2048], hashlib.sha256).hexdigest()
            logging.info("[ROUTED] %s -> %s decision=%s seal=%s", peer, provider_key, decision, tx_seal[:16])

            writer.write(real_response)
            await writer.drain()

        except Exception as e:
            logging.error("Proxy error for %s: %s", peer, e)
            try:
                self._reject(writer, 502, "gateway_error", str(e))
            except Exception:
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _reject(self, writer, code, reason, message=None, extra=None):
        payload = {"error": reason}
        if message:
            payload["message"] = message
        if extra:
            payload["compliance_decision"] = extra
        body = json.dumps(payload).encode("utf-8")
        status_text = {401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 502: "Bad Gateway"}.get(code, "Error")
        resp = (
            "HTTP/1.1 " + str(code) + " " + status_text + "\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: " + str(len(body)) + "\r\n"
            "Connection: close\r\n\r\n"
        ).encode("utf-8") + body
        writer.write(resp)


if __name__ == "__main__":
    gateway = ComplianceGatewayProxy()
    try:
        asyncio.run(gateway.start())
    except KeyboardInterrupt:
        logging.info("Gateway offline.")

```


## `mcp_server.py`

223 lines, 8924 bytes

```python
import os, subprocess, requests, hashlib, hmac, base64, uuid, re, json, time
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Live-MSP-Engine")

# --- LIVE EXECUTION TOOLS ---
@mcp.tool()
def run_cli_command(command: str) -> dict:
    """Run a local shell command on the host machine and return output."""
    res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    return {"exit_code": res.returncode, "stdout": res.stdout, "stderr": res.stderr}

@mcp.tool()
def call_api(url: str, method: str = "GET", payload: dict = None, headers: dict = None) -> dict:
    """Hit a real HTTP REST endpoint, microservice, or webhook."""
    r = requests.request(method, url, json=payload, headers=headers, timeout=15)
    return {"status": r.status_code, "response": r.text}

@mcp.tool()
def deploy_railway_service(service_id: str, api_token: str) -> dict:
    """Trigger a live container redeployment on Railway."""
    url = "https://backboard.railway.app/graphql/v2"
    q = "mutation($s: String!){serviceInstanceRedeploy(serviceId:$s)}"
    r = requests.post(url, json={"query": q, "variables": {"s": service_id}}, headers={"Authorization": f"Bearer {api_token}"})
    return {"status": r.status_code, "data": r.json()}

# --- UTILITY & SECURITY TOOLS ---
@mcp.tool()
def sec_hash_sha256(data: str) -> str:
    """Generate SHA-256 digest for input data."""
    return hashlib.sha256(data.encode()).hexdigest()

@mcp.tool()
def sec_hmac_sign(key: str, message: str) -> str:
    """Sign payload using HMAC-SHA256."""
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()

@mcp.tool()
def sec_hmac_verify(key: str, message: str, signature: str) -> bool:
    """Verify HMAC-SHA256 signature against payload."""
    expected = hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@mcp.tool()
def sec_verify_merkle_leaf(leaf: str, proof: List[str], root: str) -> bool:
    """Verify standard Merkle tree membership proof."""
    current = leaf
    for sibling in proof:
        combined = "".join(sorted([current, sibling]))
        current = hashlib.sha256(combined.encode()).hexdigest()
    return current == root

@mcp.tool()
def sec_base64_encode(payload: str) -> str:
    """Base64 encode standard string payload."""
    return base64.b64encode(payload.encode()).decode()

@mcp.tool()
def sec_base64_decode(encoded_str: str) -> str:
    """Base64 decode string back to original format."""
    return base64.b64decode(encoded_str.encode()).decode()

@mcp.tool()
def sec_generate_uuid_v4() -> str:
    """Generate cryptographically secure UUID v4 identifier."""
    return str(uuid.uuid4())

@mcp.tool()
def sec_mask_sensitive_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """Scrub sensitive keys from dictionary."""
    sensitive = {"token", "key", "password", "secret", "auth", "bearer"}
    return {k: ("***REDACTED***" if any(s in k.lower() for s in sensitive) else v) for k, v in data.items()}

@mcp.tool()
def data_flatten_dict(nested_dict: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """Flatten nested dictionary into single dot-notation key map."""
    items = []
    for k, v in nested_dict.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(data_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

@mcp.tool()
def data_csv_to_json(csv_text: str) -> List[Dict[str, str]]:
    """Convert raw CSV string content into JSON list of key-value maps."""
    import csv, io
    return [row for row in csv.DictReader(io.StringIO(csv_text.strip()))]

@mcp.tool()
def data_json_to_csv(json_list: List[Dict[str, Any]]) -> str:
    """Convert JSON list of dictionaries into formatted CSV string."""
    import csv, io
    if not json_list: return ""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=json_list[0].keys())
    writer.writeheader()
    writer.writerows(json_list)
    return out.getvalue()

@mcp.tool()
def data_calculate_array_stats(numbers: List[float]) -> Dict[str, float]:
    """Compute min, max, average, sum, and length of numerical array."""
    if not numbers: return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}
    return {"count": float(len(numbers)), "sum": float(sum(numbers)), "avg": float(sum(numbers)/len(numbers)), "min": float(min(numbers)), "max": float(max(numbers))}

@mcp.tool()
def data_human_readable_bytes(num_bytes: int) -> str:
    """Format raw byte integer into human-readable size string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(num_bytes) < 1024.0: return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"

@mcp.tool()
def data_slugify_string(text: str) -> str:
    """Convert text string into clean URL-friendly slug."""
    return re.sub(r'[\s_-]+', '-', re.sub(r'[^\w\s-]', '', text.lower().strip()))

@mcp.tool()
def data_deduplicate_list(lst: List[Any]) -> List[Any]:
    """Remove duplicate values while maintaining original order."""
    seen = set()
    return [x for x in lst if not (x in seen or seen.add(x))]

@mcp.tool()
def data_filter_nulls(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove keys with None or empty values from dictionary."""
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}

@mcp.tool()
def net_parse_url_params(url: str) -> Dict[str, List[str]]:
    """Parse URL target and extract query parameter dictionary."""
    from urllib.parse import parse_qs, urlparse
    return parse_qs(urlparse(url).query)

@mcp.tool()
def net_validate_ip(ip_address: str) -> Dict[str, Any]:
    """Validate IPv4 or IPv6 format compliance."""
    import ipaddress
    try:
        ip = ipaddress.ip_address(ip_address)
        return {"valid": True, "version": ip.version, "is_private": ip.is_private}
    except ValueError:
        return {"valid": False, "version": None, "is_private": False}

@mcp.tool()
def net_extract_domain(url: str) -> str:
    """Extract hostname domain from full target URL."""
    from urllib.parse import urlparse
    return urlparse(url).netloc

@mcp.tool()
def net_generate_curl(url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None) -> str:
    """Build equivalent cURL command string for debugging endpoints."""
    cmd = f"curl -X {method.upper()} \"{url}\""
    if headers:
        for k, v in headers.items(): cmd += f" -H \"{k}: {v}\""
    return cmd

@mcp.tool()
def net_strip_html_tags(html_content: str) -> str:
    """Strip all HTML tags returning clean text content."""
    return re.sub(r'<[^>]*>', '', html_content).strip()

@mcp.tool()
def net_extract_urls(text: str) -> List[str]:
    """Regex extract web links from text."""
    return re.findall(r'https?://[^\s<>"]+', text)

@mcp.tool()
def time_get_epoch() -> float:
    """Return current UTC epoch timestamp in seconds."""
    return time.time()

@mcp.tool()
def time_epoch_to_iso(epoch: float) -> str:
    """Convert epoch timestamp into ISO-8601 string."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()

@mcp.tool()
def time_iso_to_epoch(iso_str: str) -> float:
    """Convert ISO-8601 string to standard UTC epoch timestamp."""
    from datetime import datetime
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp()

@mcp.tool()
def time_format_duration(seconds: float) -> str:
    """Format total elapsed seconds into HH:MM:SS format."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

@mcp.tool()
def biz_calculate_vat(amount: float, rate: float = 0.20) -> Dict[str, float]:
    """Compute VAT/Tax addition and total billing amount."""
    tax = amount * rate
    return {"net": amount, "tax": round(tax, 2), "total": round(amount + tax, 2)}

@mcp.tool()
def biz_calculate_margin(cost: float, revenue: float) -> Dict[str, float]:
    """Calculate gross profit and profit margin percentage."""
    profit = revenue - cost
    return {"profit": round(profit, 2), "margin_pct": round((profit / revenue * 100) if revenue > 0 else 0.0, 2)}

@mcp.tool()
def biz_apply_discount(price: float, discount_pct: float) -> Dict[str, float]:
    """Apply percentage discount calculation to base price."""
    saved = price * (discount_pct / 100.0)
    return {"original": price, "saved": round(saved, 2), "final": round(price - saved, 2)}

@mcp.tool()
def biz_calculate_hourly_rate(total_project_cost: float, estimated_hours: float) -> float:
    """Calculate target hourly billing rate from fixed project value."""
    return round(total_project_cost / estimated_hours, 2) if estimated_hours > 0 else 0.0

if __name__ == "__main__":
    mcp.run()

```


## `meshwitness.py`

328 lines, 11605 bytes

```python
#!/usr/bin/env python3
"""
meshwitness.py  v1.0  -  witness everybody, not just whoever invited you

    Standard library only. One file. One cron line. No install.

WHAT PROBLEM THIS SOLVES
    Witnessing runs on your own machine, so your server only witnesses
    chains you have told it about. Most operators point at whoever
    introduced them and stop there. The result is a star: everybody
    connected to one node in the middle, and if that node goes down
    every chain loses its witness at the same moment.

    This reads the published roster and witnesses EVERY chain on it. A
    chain that joins tomorrow gets picked up on your next run with
    nothing to configure and no email from anyone.

WHAT IT DOES, EACH RUN
    1. Fetches the roster.
    2. For every chain with a tip URL, fetches their current tip.
    3. Seals that tip into YOUR chain, via your own seal endpoint.
    4. Pushes YOUR tip to their submit endpoint, so the witnessing is
       mutual rather than one-way.
    5. Prints a line per peer and exits non-zero if nothing worked.

    It never sends your data anywhere. A tip is a hash. That is the
    whole payload.

RUN IT
    export MESH_TIP_URL=https://yoursite.example/witness.json
    export MESH_SEAL_URL=https://yoursite.example/api/witness/seal
    export MESH_CHAIN=your-chain-name

    python3 meshwitness.py

    Cron, hourly, on a minute nobody else is using:
        23 * * * * /usr/bin/python3 /path/meshwitness.py >> /var/log/mesh.log 2>&1

    Check what it would do without doing it:
        python3 meshwitness.py --dry-run

CONFIGURATION
    MESH_TIP_URL    where YOUR current tip is served. required.
    MESH_SEAL_URL   your own endpoint that seals an observed tip.
                    optional -- omit it and this only pushes, which is
                    still useful but only half the exchange.
    MESH_CHAIN      your chain name as other nodes should record it.
    MESH_ROSTER     roster to read. defaults to sebbi.pro.
    MESH_SKIP       comma separated chain names to ignore.
    MESH_TIMEOUT    seconds per request. default 15.

IF YOUR STACK IS NOT PYTHON
    The whole protocol is four HTTP calls and no cryptography beyond a
    hash you already have. Read --explain for the exact requests and
    write it in whatever you use. Nothing here is privileged.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

VERSION = "1.0"

DEFAULT_ROSTER = "https://sebbi.pro/x/roster/list"
DEFAULT_TIMEOUT = 15.0
USER_AGENT = "meshwitness/%s" % VERSION


# ------------------------------------------------------------------ http

def _get(url, timeout):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except ValueError:
        return {"_raw": raw.strip()}


def _post(url, payload, timeout):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {"error": "http_%d" % e.code}


def _extract_tip(doc):
    """
    Find the tip hash in whatever shape a peer serves. Different nodes
    name it differently and that is not worth an argument.
    """
    if isinstance(doc, str):
        return doc.strip() or None
    if not isinstance(doc, dict):
        return None
    for k in ("tip", "head", "current_tip", "chain_tip", "root",
              "latest", "hash", "audit_hash", "seal"):
        v = doc.get(k)
        if isinstance(v, str) and len(v) >= 32:
            return v.strip()
        if isinstance(v, dict):
            inner = _extract_tip(v)
            if inner:
                return inner
    for k in ("chain", "witness", "data", "result"):
        v = doc.get(k)
        if isinstance(v, dict):
            inner = _extract_tip(v)
            if inner:
                return inner
    return None


# ------------------------------------------------------------------ core

class Mesh(object):

    def __init__(self, tip_url=None, seal_url=None, chain=None,
                 roster=None, skip=None, timeout=None, dry_run=False):
        self.tip_url = tip_url or os.environ.get("MESH_TIP_URL")
        self.seal_url = seal_url or os.environ.get("MESH_SEAL_URL")
        self.chain = chain or os.environ.get("MESH_CHAIN")
        self.roster = roster or os.environ.get("MESH_ROSTER", DEFAULT_ROSTER)
        self.timeout = float(timeout or os.environ.get("MESH_TIMEOUT",
                                                       DEFAULT_TIMEOUT))
        self.dry_run = dry_run
        raw_skip = skip or os.environ.get("MESH_SKIP", "")
        self.skip = set(s.strip().lower() for s in raw_skip.split(",") if s.strip())

    def check(self):
        problems = []
        if not self.tip_url:
            problems.append("MESH_TIP_URL is not set. Other nodes need "
                            "somewhere to fetch your tip from.")
        if not self.chain:
            problems.append("MESH_CHAIN is not set. Your submissions would "
                            "arrive unnamed.")
        if not self.seal_url:
            problems.append("MESH_SEAL_URL is not set, so this will push "
                            "your tip out but not seal theirs. That is "
                            "half the exchange. Not fatal.")
        return problems

    def my_tip(self):
        try:
            return _extract_tip(_get(self.tip_url, self.timeout))
        except Exception as e:
            print("  ! could not read own tip from %s: %s"
                  % (self.tip_url, str(e)[:90]))
            return None

    def fetch_roster(self):
        doc = _get(self.roster, self.timeout)
        peers = doc.get("peers") or []
        out = []
        for p in peers:
            name = (p.get("chain") or "").strip()
            url = p.get("tip_url")
            if not name or not url:
                continue
            if name.lower() == (self.chain or "").lower():
                continue                       # never witness yourself
            if name.lower() in self.skip:
                continue
            out.append({"chain": name, "tip_url": url,
                        "status": p.get("status"),
                        "submit": p.get("submit_to")})
        return out, doc

    def run(self):
        started = time.time()
        print("meshwitness %s  %s" % (VERSION, time.strftime("%Y-%m-%d %H:%M:%S")))

        for p in self.check():
            print("  ! " + p)

        mine = self.my_tip()
        if mine:
            print("  my tip: %s…" % mine[:16])
        else:
            print("  ! no tip of my own to push; will still seal theirs")

        try:
            peers, doc = self.fetch_roster()
        except Exception as e:
            print("  ! roster unreachable (%s): %s" % (self.roster, str(e)[:90]))
            return 1

        submit_to = doc.get("submit_to")
        print("  roster: %d chains, %d witnessable"
              % (doc.get("count", 0), doc.get("witnessable", 0)))

        if not peers:
            print("  nothing to witness yet.")
            return 0

        sealed = pushed = failed = 0

        for p in peers:
            name = p["chain"]
            line = "  %-28s" % name[:28]

            try:
                theirs = _extract_tip(_get(p["tip_url"], self.timeout))
            except Exception as e:
                print(line + "unreachable (%s)" % str(e)[:40])
                failed += 1
                continue

            if not theirs:
                print(line + "served no readable tip")
                failed += 1
                continue

            bits = ["tip %s…" % theirs[:12]]

            # seal theirs into mine
            if self.seal_url and not self.dry_run:
                try:
                    st, _ = _post(self.seal_url,
                                  {"chain": name, "tip": theirs,
                                   "url": p["tip_url"]}, self.timeout)
                    if 200 <= st < 300:
                        bits.append("sealed")
                        sealed += 1
                    else:
                        bits.append("seal HTTP %d" % st)
                except Exception as e:
                    bits.append("seal failed: %s" % str(e)[:30])
            elif self.dry_run:
                bits.append("would seal")

            # push mine to them
            target = p.get("submit") or submit_to
            if mine and target and not self.dry_run:
                try:
                    st, _ = _post(target,
                                  {"chain": self.chain, "tip": mine,
                                   "url": self.tip_url}, self.timeout)
                    if 200 <= st < 300:
                        bits.append("pushed")
                        pushed += 1
                    else:
                        bits.append("push HTTP %d" % st)
                except Exception as e:
                    bits.append("push failed: %s" % str(e)[:30])
            elif self.dry_run and mine:
                bits.append("would push")

            print(line + " · ".join(bits))

        print("  %d sealed, %d pushed, %d unreachable, %.1fs"
              % (sealed, pushed, failed, time.time() - started))

        if self.dry_run:
            return 0
        return 0 if (sealed or pushed) else 1


EXPLAIN = """
The protocol, so you can implement it in any language.

1. Read the roster
     GET https://sebbi.pro/x/roster/list
   -> {"peers":[{"chain":"...","tip_url":"...","witnessable":true}, ...],
       "submit_to":"https://sebbi.pro/x/witness/observe"}

2. For each peer with witnessable=true, read their tip
     GET <tip_url>
   The hash may be under "tip", "head", "root" or similar. It is a hex
   string, usually 64 characters. Nothing else in the document matters.

3. Seal it in your own chain
   Whatever your system does to record an observation. The point is that
   their tip is now inside your history at a time you did not choose,
   which is what makes your later statements about them checkable.

4. Push your own tip back
     POST <their submit endpoint>
     {"chain": "<your name>", "tip": "<your hex tip>",
      "url": "<where your tip is served>"}

   The url field is what binds your name to a host. Leave it out and
   your chain is listed but nobody can fetch from you.

Run it hourly. Pick a minute nobody else is on so the network is not
all talking at once.

No keys. No accounts. No payload but a hash. If your tip endpoint is a
static JSON file regenerated by a cron, that is a completely valid node.
"""


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])

    if "--explain" in argv:
        print(EXPLAIN.strip())
        return 0
    if "--version" in argv:
        print("meshwitness %s" % VERSION)
        return 0
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0

    dry = "--dry-run" in argv
    return Mesh(dry_run=dry).run()


if __name__ == "__main__":
    sys.exit(main())

```


## `sebbi_agent.py`

174 lines, 6317 bytes

```python
#!/usr/bin/env python3
"""
sebbi_agent.py  -  give any AI agent an Agent Passport in one line
==================================================================

    from sebbi_agent import needs_passport

    @needs_passport("payments.send", audience="shop.example.com",
                    grant="g_your_grant_id", params=["amount"])
    def pay(amount, passport=None):
        # passport is a signed token. Send it with the request:
        #   headers = {"Agent-Passport": passport}
        ...

    pay(amount=20)

Before the function runs, sebbi.pro traces the agent's authority back to the
human who granted it and issues a passport for exactly this action, at this
site, with these parameters. If sebbi.pro refuses, the function never runs and
PassportRefused is raised with the reasons and a link to the sealed refusal.

Fails closed: if sebbi.pro cannot be reached, the action does not happen.

Needs your sebbi.pro API key in the SEBBI_KEY environment variable.
Standard library only. One file. Python 3.8+.

Command line:
    python sebbi_agent.py request --grant G --action payments.send \\
        --audience shop.example.com --params '{"amount": 20}'
"""

import functools
import inspect
import json
import os
import sys
import threading
import urllib.error
import urllib.request

__version__ = "1.0.0"

BASE = os.environ.get("SEBBI_BASE", "https://sebbi.pro").rstrip("/")
HEADER = "Agent-Passport"
TIMEOUT = 10

_local = threading.local()


class PassportError(Exception):
    """Base class. The action did not happen."""


class PassportRefused(PassportError):
    """sebbi.pro evaluated the request and did not issue a passport."""

    def __init__(self, verdict, reasons, proof=None):
        self.verdict, self.reasons, self.proof = verdict, reasons, proof
        msg = "%s: %s" % (verdict, "; ".join(reasons) if reasons else "no reason given")
        if proof:
            msg += " (sealed refusal: %s)" % proof
        super().__init__(msg)


class PassportUnavailable(PassportError):
    """sebbi.pro could not be reached or answered with an error. Fails closed."""


def _post(path, body, key):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key,
                 "User-Agent": "sebbi-agent/" + __version__})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8"))
        except Exception:
            detail = {"error": "http_%d" % e.code}
        raise PassportUnavailable("sebbi.pro answered %d: %s" % (e.code, detail))
    except Exception as e:
        raise PassportUnavailable("could not reach sebbi.pro: %s" % e)


def request_passport(grant, action, audience, params=None, purpose_tag=None, key=None):
    """Ask sebbi.pro for a passport. Returns the token string or raises."""
    key = key or os.environ.get("SEBBI_KEY", "")
    if not key:
        raise PassportUnavailable("set SEBBI_KEY to your sebbi.pro API key")
    res = _post("/x/passport/issue", {"grant": grant, "action": action,
                                     "audience": audience, "params": params or {},
                                     "purpose_tag": purpose_tag}, key)
    if res.get("issued"):
        return res["passport"]
    if "verdict" in res:
        raise PassportRefused(res["verdict"], res.get("reasons", []),
                              res.get("proof_of_refusal"))
    raise PassportUnavailable("unexpected answer: %s" % res)


def current_passport():
    """The passport for the action currently running inside @needs_passport."""
    return getattr(_local, "token", None)


def headers(token=None):
    """HTTP headers to send with the action."""
    return {HEADER: token or current_passport() or ""}


def needs_passport(action, audience, grant=None, params=None, purpose_tag=None, key=None):
    """Decorator. The wrapped function runs only if a passport is issued.

    params: list of argument names whose values define the action, e.g.
            ["amount", "currency"]. The site must redeem with the same values,
            so a passport for 20 cannot be spent on 49.
    grant:  the grant id. Can also be passed at call time as grant=...
    The token is handed to the function as passport=... if it accepts that
    argument, and is always available through current_passport().
    """
    names = list(params or [])

    def wrap(fn):
        sig = inspect.signature(fn)
        takes_passport = "passport" in sig.parameters

        @functools.wraps(fn)
        def inner(*args, **kwargs):
            g = kwargs.pop("grant", None) if "grant" not in sig.parameters else kwargs.get("grant")
            g = g or grant or os.environ.get("SEBBI_GRANT")
            if not g:
                raise PassportUnavailable("no grant id: pass grant=... or set SEBBI_GRANT")
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            p = {n: bound.arguments[n] for n in names if n in bound.arguments}
            token = request_passport(g, action, audience, p, purpose_tag, key)
            if takes_passport:
                kwargs["passport"] = token
            _local.token = token
            try:
                return fn(*args, **kwargs)
            finally:
                _local.token = None
        return inner
    return wrap


def _cli(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="sebbi_agent")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("request")
    r.add_argument("--grant", required=True)
    r.add_argument("--action", required=True)
    r.add_argument("--audience", required=True)
    r.add_argument("--params", default="{}")
    r.add_argument("--purpose", default=None)
    a = ap.parse_args(argv)
    if a.cmd != "request":
        ap.print_help()
        return 2
    try:
        print(request_passport(a.grant, a.action, a.audience, json.loads(a.params), a.purpose))
        return 0
    except PassportError as e:
        print("REFUSED: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))

```


## `sebbi_benchmark.py`

271 lines, 10114 bytes

```python
#!/usr/bin/env python3
"""
sebbi_benchmark.py  -  an honest benchmark
==========================================

Everything this prints was measured on the machine running it, or is labelled
as an estimate. Nothing is typed in by hand to make a comparison look good.

    python3 sebbi_benchmark.py                  local measurements only
    python3 sebbi_benchmark.py --price 3.00     also show cost at YOUR price per 1M tokens
    python3 sebbi_benchmark.py --live           also time real calls to sebbi.pro

What it measures
  1. Exact-match cache      a repeated identical request is served locally,
                            so it sends nothing to the model.
  2. Secret redaction       emails and bearer tokens are masked before a prompt
                            leaves the machine. Wording is never changed.
  3. Signed receipts        each processed request gets an Ed25519 signature.
                            Only the holder of the private key can produce it;
                            anyone with the public key can check it. That is
                            what makes it non-repudiable. (HMAC cannot do this:
                            anyone holding the shared secret can forge it.)
  4. Live round trip        with --live, real timings to sebbi.pro, network included.

What it does NOT claim
  - Token counts are ESTIMATES (about 4 characters per token for English).
    Your provider's own count is the only exact figure.
  - No money is shown unless you give your own contract price with --price.
  - This is a demonstration of the techniques, not the sebbi.pro token saver
    itself, which runs as its own module and customer download.

Standard library only. Python 3.8+.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import statistics
import sys
import time
import urllib.request

# ---------------------------------------------------------------- Ed25519 (RFC 8032)
_Q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _Q - 2, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _inv(x):
    return pow(x, _Q - 2, _Q)


def _xrec(y):
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q:
        x = x * _I % _Q
    if x % 2:
        x = _Q - x
    return x


_BY = 4 * _inv(5) % _Q
_B = (_xrec(_BY), _BY, 1, _xrec(_BY) * _BY % _Q)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _Q
    b = (y1 + x1) * (y2 + x2) % _Q
    c = t1 * 2 * _D * t2 % _Q
    d = z1 * 2 * z2 % _Q
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _Q, g * h % _Q, f * g % _Q, e * h % _Q)


def _mul(p, n):
    r = (0, 1, 1, 0)
    while n:
        if n & 1:
            r = _add(r, p)
        p = _add(p, p)
        n >>= 1
    return r


def _enc(p):
    x, y, z, _ = p
    zi = _inv(z)
    x, y = x * zi % _Q, y * zi % _Q
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _dec(s):
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = _xrec(y)
    if (x & 1) != (s[31] >> 7):
        x = _Q - x
    return (x, y, 1, x * y % _Q)


def _h(m):
    return int.from_bytes(hashlib.sha512(m).digest(), "little")


def _secret_scalar(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def ed_public(seed):
    return _enc(_mul(_B, _secret_scalar(seed)[0]))


def ed_sign(seed, msg):
    a, prefix = _secret_scalar(seed)
    pk = _enc(_mul(_B, a))
    r = _h(prefix + msg) % _L
    R = _enc(_mul(_B, r))
    s = (r + _h(R + pk + msg) * a) % _L
    return R + s.to_bytes(32, "little")


def ed_verify(pk, msg, sig):
    try:
        R, A = _dec(sig[:32]), _dec(pk)
    except Exception:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _L:
        return False
    k = _h(sig[:32] + pk + msg) % _L
    return _enc(_mul(_B, s)) == _enc(_add(R, _mul(A, k)))


# ---------------------------------------------------------------- the demo engine
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")
KEYLIKE = re.compile(r"\b(sk|pk|rk)_(live|test)_[A-Za-z0-9]{8,}\b")


def est_tokens(text):
    """Estimate only: about 4 characters per token for English text."""
    return max(1, round(len(text) / 4))


class Engine:
    def __init__(self):
        self.cache = {}
        self.seed = secrets.token_bytes(32)
        self.public_key = ed_public(self.seed)

    def process(self, prompt):
        t0 = time.perf_counter()
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if digest in self.cache:
            return {"verdict": "CACHE_HIT", "sent_to_model": "", "request_hash": digest,
                    "ms": (time.perf_counter() - t0) * 1000, "receipt": self.cache[digest]["receipt"]}
        clean = BEARER.sub("Bearer [REDACTED]", prompt)
        clean = KEYLIKE.sub("[REDACTED_KEY]", clean)
        clean = EMAIL.sub("[REDACTED_EMAIL]", clean)
        body = json.dumps({"request": digest,
                           "sent": hashlib.sha256(clean.encode("utf-8")).hexdigest()},
                          sort_keys=True, separators=(",", ":")).encode()
        sig = ed_sign(self.seed, body)
        receipt = {"body": body.decode(), "signature": sig.hex()}
        self.cache[digest] = {"sent": clean, "receipt": receipt}
        return {"verdict": "PROCESSED", "sent_to_model": clean, "request_hash": digest,
                "ms": (time.perf_counter() - t0) * 1000, "receipt": receipt,
                "redactions": prompt != clean}


def timed(fn, n):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return statistics.median(times), times[max(0, int(len(times) * 0.95) - 1)]


def live(path):
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen("https://sebbi.pro" + path, timeout=15) as r:
            r.read()
            code = r.status
    except Exception as e:
        return None, str(e)[:60]
    return (time.perf_counter() - t0) * 1000, code


def main():
    ap = argparse.ArgumentParser(description="An honest sebbi.pro benchmark")
    ap.add_argument("--price", type=float, help="your contract price in USD per 1M input tokens")
    ap.add_argument("--live", action="store_true", help="also time real calls to sebbi.pro")
    ap.add_argument("--runs", type=int, default=50, help="repetitions per timing (default 50)")
    a = ap.parse_args()

    prompt = ("Please summarise this internal operations brief for our team. "
              "Review all the customer logs attached. "
              "Send the confirmation report to admin.ops@enterprise.com once finished. "
              "Authentication: Bearer sk_live_998877665544332211. "
              "Capture every detail without missing any historical transitions.")
    line = "=" * 64
    print(line + "\n  SEBBI.PRO HONEST BENCHMARK  ·  measured on this machine\n" + line)
    print("  Python %s · %s runs per timing\n" % (sys.version.split()[0], a.runs))

    eng = Engine()
    first = eng.process(prompt)
    print("[1] First request")
    print("    estimated tokens in prompt : ~%d (estimate)" % est_tokens(prompt))
    print("    secrets masked             : %s" % ("yes — email and bearer token" if first["redactions"] else "none found"))
    print("    wording changed            : no (only secrets are masked)")
    print("    sent to model              : %s" % first["sent_to_model"][:70] + "…")

    second = eng.process(prompt)
    print("\n[2] Identical request again")
    print("    verdict                    : %s" % second["verdict"])
    print("    sent to model              : nothing (served from local cache)")
    print("    tokens avoided             : ~%d (estimate; exact figure = your provider's count)" % est_tokens(first["sent_to_model"]))

    body = first["receipt"]["body"].encode()
    sig = bytes.fromhex(first["receipt"]["signature"])
    ok = ed_verify(eng.public_key, body, sig)
    forged = ed_verify(eng.public_key, body.replace(b'"request"', b'"requesT"'), sig)
    print("\n[3] Signed receipt (Ed25519)")
    print("    public key                 : %s…" % eng.public_key.hex()[:32])
    print("    receipt verifies           : %s" % ("YES" if ok else "NO"))
    print("    altered receipt verifies   : %s" % ("YES — PROBLEM" if forged else "NO (tampering detected)"))

    fresh = Engine()
    p_med, p_95 = timed(lambda: fresh.process(prompt + secrets.token_hex(4)), a.runs)
    c_med, c_95 = timed(lambda: eng.process(prompt), a.runs)
    v_med, v_95 = timed(lambda: ed_verify(eng.public_key, body, sig), max(10, a.runs // 5))
    print("\n[4] Measured timings (median / 95th percentile)")
    print("    new request, masked + signed : %.2f ms / %.2f ms" % (p_med, p_95))
    print("    cache hit                    : %.3f ms / %.3f ms" % (c_med, c_95))
    print("    receipt verification         : %.2f ms / %.2f ms" % (v_med, v_95))
    print("    (plain-Python signatures; a native Ed25519 library is faster)")

    if a.price is not None:
        cost = est_tokens(first["sent_to_model"]) * a.price / 1_000_000
        print("\n[5] At YOUR price of $%.2f per 1M input tokens" % a.price)
        print("    this prompt costs about    : $%.6f per call (estimate)" % cost)
        print("    each cache hit avoids      : about $%.6f (estimate)" % cost)

    if a.live:
        print("\n[6] Live round trips to sebbi.pro (network included)")
        for path in ("/x/witness/tip", "/x/continuity/pubkey", "/x/passport/spec"):
            ms, code = live(path)
            print("    %-24s : %s" % (path, ("%.0f ms (HTTP %s)" % (ms, code)) if ms else "failed: %s" % code))

    print("\n" + line)
    print("  Every figure above was measured here or is marked as an estimate.")
    print("  Check any of it: the code is this file, standard library only.")
    print(line)


if __name__ == "__main__":
    main()

```
