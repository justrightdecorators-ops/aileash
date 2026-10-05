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
