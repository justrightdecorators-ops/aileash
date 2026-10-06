"""
modules/answers.py  v1.0.0  -  plain answers to the questions people ask, and the AI guide

    Arm:      https://sebbi.pro/x/arm/status
    Answers:  https://sebbi.pro/answers
    Standard: https://sebbi.pro/standard/forever-proof
    AI guide: https://sebbi.pro/llms.txt

When someone asks Google, ChatGPT, Claude or a forum "how do I prove what my
AI decided?", the answer that gets quoted is the clearest page that answers
exactly that question. These pages do that: one question per page, the
answer in the first two sentences, then how it works and where to do it,
with schema.org FAQ markup search engines and AI tools read.

Also serves /llms.txt (the guide AI tools read - the file existed but no
route served it), the open Forever Proof standard, and a sitemap for these
pages at /sitemap-answers.xml.

Adds pages only. Reads nothing from the chain and writes nothing anywhere.
"""

import json
import os
import sys
import threading

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "")}
SITE = "https://sebbi.pro"
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_state = {"pages": False, "served": 0, "last_error": None}
_lock = threading.Lock()


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


# ---------------------------------------------------------------------------
# the answers. "a" is the direct answer (first thing read and quoted),
# "how" the steps, "do" the places to act, "more" extra paragraphs.
# ---------------------------------------------------------------------------

ANSWERS = [
    {"slug": "prove-an-ai-decision-to-a-regulator",
     "q": "How do I prove an AI decision to a regulator?",
     "a": "Seal each decision at the moment it is made into a tamper-evident record that the regulator can check themselves, without relying on your word or your vendor's database. sebbi.pro does this: every AI decision is scored, sealed into a hash chain, witnessed by independent chains and committed to Bitcoin every hour, and any single decision can be checked against Bitcoin in a browser at sebbi.pro/forever.",
     "how": ["Send the decision to sebbi.pro as it happens (one API call, or connect your AI assistant at sebbi.pro/mcp).",
             "It is scored ALLOW, CHALLENGE or BLOCK in under 30 ms and sealed into the chain with a numbered receipt.",
             "Every hour the whole chain is folded into one Merkle root and written into Bitcoin.",
             "When asked, hand the regulator the block number or the Forever Proof file. They check it themselves at sebbi.pro/forever, or offline with one Python file."],
     "more": ["A report produced by the company being audited is a claim. A record the regulator can check against a public blockchain nobody controls is evidence. For a single decision you can also give the full machine-proof report: the decision, who sent it, where it came from, and every integrity and time proof (sebbi.pro/dossier)."],
     "do": [("Check a decision against Bitcoin", "/forever"), ("Connect your AI", "/connect"), ("Machine-proof report", "/dossier")]},

    {"slug": "tamper-proof-ai-audit-logs",
     "q": "How do I make AI audit logs tamper-proof?",
     "a": "Chain every log entry to the one before it with a cryptographic hash, have independent parties hold copies, number entries so gaps show, and anchor the chain to Bitcoin so even the operator cannot rewrite history. sebbi.pro provides all of these layers for every AI decision it seals.",
     "how": ["Hash chain: each record includes the hash of the previous one. Change any record and every record after it breaks.",
             "Unpredictable time: each seal carries public drand randomness, which nobody can know in advance, so records cannot be backdated.",
             "Witnesses: independent peer chains on the witness network hold and vouch for copies of the chain.",
             "Receipts: each customer's decisions are numbered in order with no gaps, so a missing record proves itself missing.",
             "Bitcoin: every hour the chain's Merkle root is committed to Bitcoin through OpenTimestamps."],
     "more": ["A log in an ordinary database is only as trustworthy as whoever has write access to it. These layers mean a record cannot be faked before it happened, changed afterwards, quietly deleted, or lost if the operator disappears. The chain can be re-verified by anyone at sebbi.pro/api/verify-chain."],
     "do": [("Verify the live chain", "/api/verify-chain"), ("Forever Proof", "/forever"), ("Developers", "/developers")]},

    {"slug": "eu-ai-act-record-keeping",
     "q": "What records does the EU AI Act require for high-risk AI?",
     "a": "The EU AI Act requires high-risk AI systems to automatically record events (logs) over their lifetime (Article 12), requires providers to keep those logs for at least six months (Article 19), and requires deployers to keep the logs under their control for at least six months (Article 26). sebbi.pro records every decision automatically, seals it so it cannot be altered, and keeps it provable long after six months through Bitcoin anchoring.",
     "how": ["Article 12: logs must allow events relevant to risk, post-market monitoring and operational monitoring to be recorded automatically.",
             "Article 19 and Article 26(6): automatically generated logs kept for at least six months, longer where other law requires.",
             "Article 14: human oversight, so a person can understand, override or stop the system. sebbi.pro's CHALLENGE verdict routes a decision to a human.",
             "Article 86: people affected by certain high-risk decisions can ask for an explanation, which needs a record of what was decided and why."],
     "more": ["Application dates and details can change through EU implementing acts and amendments, so check the current text for your system. This page is a plain summary, not legal advice. The free EU AI Act scanner at sebbi.pro/scan gives a quick first view of where you stand."],
     "do": [("Free EU AI Act scanner", "/scan"), ("Start sealing decisions", "/connect"), ("Whitepaper", "/whitepaper")]},

    {"slug": "timestamp-a-file-in-bitcoin",
     "q": "How do I timestamp a file in Bitcoin?",
     "a": "Fingerprint the file with SHA-256 and commit that fingerprint to Bitcoin through the OpenTimestamps calendars. The easiest way is the free Bitcoin Notary at sebbi.pro/bitcoin: drop the file in, it is fingerprinted on your own device, and you get a receipt that confirms in a Bitcoin block, normally within a few hours.",
     "how": ["Open sebbi.pro/bitcoin and drop in one or more files, or paste text or a fingerprint.",
             "Your browser computes the SHA-256. The file itself never leaves your device.",
             "Every few minutes all fingerprints are folded into one Merkle tree, and its root is sent to Bitcoin.",
             "Your receipt page shows when it lands in a Bitcoin block, and gives you a Forever Proof anyone can check."],
     "more": ["Companies and tools can do the same by API: POST the fingerprints to sebbi.pro/x/notary/stamp. Without a key there is a daily limit of 500 per visitor; with an API key it is 100,000 a day. AI assistants connected at sebbi.pro/mcp can call sebbi_notarize directly."],
     "do": [("Bitcoin Notary", "/bitcoin"), ("Notary spec", "/x/notary/spec"), ("Discovery document", "/.well-known/sebbi-notary.json")]},

    {"slug": "what-is-a-forever-proof",
     "q": "What is a Forever Proof?",
     "a": "A Forever Proof is a small file that proves a fingerprint existed before a specific Bitcoin block was mined. It holds the fingerprint, its Merkle path to a batch root, and the OpenTimestamps proof linking that root to Bitcoin, so anyone can check it against the Bitcoin blockchain without sebbi.pro.",
     "how": ["The fingerprint (a sebbi.pro decision, a notarised file or a Human Keys proof) is a leaf in a Merkle tree.",
             "The path of sibling hashes folds the leaf up to the tree's root.",
             "The OpenTimestamps proof replays the operations from that root to a Bitcoin block's Merkle root.",
             "A verifier compares the result with the real block, fetched from independent explorers or your own node."],
     "more": ["The format is open (sebbi-forever-proof/1) and free to implement. Because the proof is a file the holder keeps, it still works if sebbi.pro is offline, in a dispute with them, or gone."],
     "do": [("Check a proof", "/forever"), ("The open standard", "/standard/forever-proof"), ("Download the verifier", "/forever-verify.py")]},

    {"slug": "verify-without-trusting-the-vendor",
     "q": "How do I check a proof without trusting the company that made it?",
     "a": "Check it against a public record the company does not control. Every sebbi.pro proof can be checked against Bitcoin in your own browser at sebbi.pro/forever, or offline with forever-verify.py, a single Python file that needs nothing installed and can use your own Bitcoin node.",
     "how": ["Get the Forever Proof file (from the receipt page, the company you are checking, or sebbi.pro/forever).",
             "Run python3 forever-verify.py proof.json, or drop it on sebbi.pro/forever where the checking runs in your browser.",
             "The verifier replays every step and fetches the Bitcoin block from two independent explorers, or from your node with --node.",
             "VERIFIED means the record existed before that block. Nothing from sebbi.pro was trusted to reach that answer."],
     "more": ["Add --file to check that the original file is the one that was proven, --text for a Human Keys text, or --block for the decision itself if you are its owner."],
     "do": [("Verify in your browser", "/forever"), ("Download forever-verify.py", "/forever-verify.py")]},

    {"slug": "prove-a-human-wrote-it",
     "q": "How do I prove a human wrote something, not an AI?",
     "a": "Type it on Human Keys at sebbi.pro/keys. The page measures how you type — the rhythm, corrections and pauses — never what you type, seals the result with a fingerprint of the text, and gives you a code anyone can check. The proof is signed by a key on your own phone and dated by Bitcoin, so the original can always show it came first.",
     "how": ["Type on sebbi.pro/keys. The text stays on your device; only its fingerprint is sent.",
             "The typing rhythm is scored on the server against a challenge that cannot be prepared in advance.",
             "You get a code like HK-7Q2M-X9KD and a check page others can open and paste the text into.",
             "The proof joins the next Bitcoin batch, and you can prove ownership with your phone's key."],
     "more": ["50p a month for unlimited proofs. Checking a proof is always free."],
     "do": [("Human Keys", "/keys"), ("Check a proof", "/k/")]},

    {"slug": "prove-nothing-was-deleted",
     "q": "How do I prove a record was not deleted?",
     "a": "Number every record in order with no gaps, and publish consistency proofs that show today's log contains yesterday's. On sebbi.pro every customer's decisions get sequence numbers with no gaps, so holding receipts 41 and 43 proves 42 is missing, and the RFC 6962 consistency root lets anyone prove the log they saw earlier is still part of the log served now.",
     "how": ["Each sealed decision gets a block number and a per-customer sequence number, issued together.",
             "Sequence numbers have no gaps by construction.",
             "The consistency root at sebbi.pro/x/consistency/root covers every record in order, and the same root is committed to Bitcoin hourly.",
             "Independent witness chains hold copies, so removing a record means fooling all of them."],
     "do": [("Consistency root", "/x/consistency/root"), ("Forever Proof", "/forever")]},

    {"slug": "audit-trail-for-ai-agents",
     "q": "How do I give an AI agent an audit trail?",
     "a": "Have the agent send each action to sebbi.pro before it acts, and keep the sealed receipt. Agents can do it themselves through the MCP connector at sebbi.pro/mcp, and an Agent Passport gives one signed, single-use permission for a single action that can be checked offline.",
     "how": ["Connect the agent's assistant at sebbi.pro/mcp, or call the API from the agent's code.",
             "Each action is scored ALLOW, CHALLENGE or BLOCK before it runs, and sealed.",
             "High-risk actions can require an Agent Passport: a signed permission for that one action.",
             "Every action then has a receipt that outlives the agent, the model and the vendor, provable against Bitcoin."],
     "do": [("Connect your AI", "/connect"), ("Agent Passport", "/passport"), ("Build your own rules", "/build")]},

    {"slug": "govern-every-openai-call",
     "q": "How do I govern every OpenAI or Anthropic call without changing my code?",
     "a": "Change one line: point your app's OpenAI or Anthropic base URL at the sebbi.pro gateway. Every call is then scored before it leaves, stopped if it should be, sealed into a tamper-evident chain, and answered with an AI-Decision-Receipt header anyone can check against Bitcoin.",
     "how": ["Get your private gateway URL at sebbi.pro/gateway (or ask your AI assistant connected at sebbi.pro/mcp to set it up).",
             "Set it as base_url in the OpenAI or Anthropic SDK. Your provider key stays in your app and passes straight through.",
             "Each request is fingerprinted, scored ALLOW, CHALLENGE or BLOCK, and sealed. BLOCK never reaches the provider.",
             "Answers stream back token by token with an AI-Decision-Receipt header; request and response fingerprints are timestamped in Bitcoin."],
     "more": ["Prompts, answers and provider keys are never stored, only their fingerprints. The receipt header is an open standard any system can emit."],
     "do": [("Set up the gateway", "/gateway"), ("The receipt standard", "/standard/ai-decision-receipt")]},

    {"slug": "prove-code-existed-on-a-date",
     "q": "How do I prove my code existed on a date?",
     "a": "Fingerprint every file and timestamp the fingerprints in Bitcoin, then re-seal whenever a file changes. Drop your files on the Bitcoin Notary at sebbi.pro/bitcoin, or send the output of sha256sum to the notary API. sebbi.pro does this for its own code: every file is timestamped in Bitcoin at sebbi.pro/bitcoin/code.",
     "how": ["Fingerprint each file (your browser does it on sebbi.pro/bitcoin, or run sha256sum).",
             "Send the fingerprints to the notary. Only fingerprints are sent, so private code stays private.",
             "Keep the receipts. Each one confirms in a Bitcoin block within hours.",
             "Later, anyone with a copy of a file can drop it on 'Check a file' to see the date it was first sealed."],
     "do": [("Bitcoin Notary", "/bitcoin"), ("Our code in Bitcoin", "/bitcoin/code")]},
]
BY_SLUG = {a["slug"]: a for a in ANSWERS}


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_CSS = """<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,500;1,6..72,500&family=IBM+Plex+Sans:wght@400;500&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--ink:#0a0f1e;--ink2:#10182e;--gold:#c9a84c;--gold2:#f0d78a;--btc:#f7931a;--mut:rgba(255,255,255,.66);--line:rgba(201,168,76,.22)}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--ink);color:#fff;font-family:'IBM Plex Sans',system-ui,sans-serif;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:0 16px}
header{border-bottom:1px solid var(--line);padding:14px 0}header .wrap{display:flex;justify-content:space-between;align-items:baseline}
.brand{font-family:'IBM Plex Mono',monospace;font-size:13px;color:#fff;text-decoration:none}.brand b{color:var(--gold);font-weight:500}
header nav a{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--mut);text-decoration:none;margin-left:14px}
.crumb{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--gold);letter-spacing:.06em;margin:38px 0 12px}.crumb a{color:var(--gold);text-decoration:none}
h1{font-family:'Newsreader',Georgia,serif;font-weight:500;font-size:clamp(32px,6.4vw,50px);line-height:1.08;margin-bottom:18px}
.answer{font-size:18.5px;color:#fff;border-left:3px solid var(--btc);padding:4px 0 4px 16px;margin-bottom:26px}
h2{font-family:'Newsreader',Georgia,serif;font-weight:500;font-size:25px;margin:28px 0 10px}
ol{padding-left:22px}ol li{margin:8px 0;color:var(--mut);font-size:16px}ol li::marker{color:var(--gold);font-family:'IBM Plex Mono',monospace}
p.more{color:var(--mut);font-size:16px;margin:10px 0}
.do{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}
.do a{background:var(--gold);color:var(--ink);border-radius:8px;padding:12px 16px;font-family:'IBM Plex Mono',monospace;font-size:13.5px;text-decoration:none}
.do a+a{background:transparent;color:var(--gold);border:1px solid var(--gold)}
.rel{border-top:1px solid var(--line);margin-top:34px;padding-top:8px}.rel a{display:block;color:var(--gold2);text-decoration:none;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:15.5px}
.list a{display:block;background:var(--ink2);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:10px 0;color:#fff;text-decoration:none}
.list a b{display:block;font-family:'Newsreader',Georgia,serif;font-weight:500;font-size:21px;line-height:1.25;margin-bottom:4px}.list a span{color:var(--mut);font-size:14px}
pre{background:#060a15;border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:14px;font-family:'IBM Plex Mono',monospace;font-size:12.5px;overflow-x:auto;color:#e6e6e6;margin:10px 0}
code{font-family:'IBM Plex Mono',monospace;font-size:13.5px;color:var(--gold2)}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:14px}td,th{text-align:left;vertical-align:top;padding:9px 6px;border-bottom:1px solid rgba(255,255,255,.07)}th{color:var(--mut);font-weight:500}td:first-child{font-family:'IBM Plex Mono',monospace;color:var(--gold2);white-space:nowrap}
footer{border-top:1px solid var(--line);margin-top:40px;padding:22px 0 30px;font-size:12.5px;color:var(--mut)}footer a{color:var(--gold);text-decoration:none;margin-right:14px}
</style>"""

_HEADER = """<header><div class="wrap"><a class="brand" href="/">sebbi<b>.pro</b></a><nav><a href="/answers">Answers</a><a href="/forever">Forever Proof</a><a href="/bitcoin">Notary</a></nav></div></header>"""
_FOOTER = """<footer><div class="wrap"><a href="/answers">Answers</a><a href="/standard/forever-proof">Forever Proof standard</a><a href="/llms.txt">llms.txt</a><a href="/terms">Terms</a><p style="margin-top:12px">&copy; 2026 Monop Content &middot; sebbi.pro</p></div></footer>"""


def _head(title, desc, path, ld):
    return ('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>%s</title><meta name="description" content="%s">'
            '<link rel="canonical" href="%s%s">'
            '<meta property="og:title" content="%s"><meta property="og:description" content="%s">'
            '<meta property="og:type" content="article"><meta property="og:url" content="%s%s">'
            '<script type="application/ld+json">%s</script>%s</head><body>'
            % (_esc(title), _esc(desc), SITE, path, _esc(title), _esc(desc), SITE, path,
               json.dumps(ld).replace("</", "<\\/"), _CSS))


def _short(text, n=155):
    t = text.split(". ")[0]
    return (t if len(t) <= n else t[:n - 1].rsplit(" ", 1)[0] + "…").rstrip(".") + "."


def answer_page(a):
    path = "/answers/" + a["slug"]
    full = a["a"] + " " + " ".join(a.get("more", []))
    ld = [{"@context": "https://schema.org", "@type": "FAQPage",
           "mainEntity": [{"@type": "Question", "name": a["q"],
                           "acceptedAnswer": {"@type": "Answer", "text": full}}]},
          {"@context": "https://schema.org", "@type": "BreadcrumbList",
           "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Answers", "item": SITE + "/answers"},
                               {"@type": "ListItem", "position": 2, "name": a["q"], "item": SITE + path}]}]
    if a.get("how"):
        ld.append({"@context": "https://schema.org", "@type": "HowTo", "name": a["q"],
                   "step": [{"@type": "HowToStep", "position": i + 1, "text": s} for i, s in enumerate(a["how"])]})
    h = [_head(a["q"] + " — sebbi.pro", _short(a["a"]), path, ld), _HEADER, '<main class="wrap">',
         '<div class="crumb"><a href="/answers">ANSWERS</a></div>',
         "<h1>%s</h1>" % _esc(a["q"]), '<p class="answer">%s</p>' % _esc(a["a"])]
    if a.get("how"):
        h.append("<h2>How it works</h2><ol>%s</ol>" % "".join("<li>%s</li>" % _esc(s) for s in a["how"]))
    for m in a.get("more", []):
        h.append('<p class="more">%s</p>' % _esc(m))
    if a.get("do"):
        h.append('<div class="do">%s</div>' % "".join('<a href="%s">%s</a>' % (_esc(u), _esc(t)) for t, u in a["do"]))
    rel = [b for b in ANSWERS if b["slug"] != a["slug"]][:5]
    h.append('<div class="rel"><h2>Related questions</h2>%s</div>' %
             "".join('<a href="/answers/%s">%s</a>' % (b["slug"], _esc(b["q"])) for b in rel))
    h.append("</main>" + _FOOTER + "</body></html>")
    return "".join(h)


def index_page():
    ld = {"@context": "https://schema.org", "@type": "FAQPage",
          "mainEntity": [{"@type": "Question", "name": a["q"],
                          "acceptedAnswer": {"@type": "Answer", "text": a["a"]}} for a in ANSWERS]}
    h = [_head("Answers: proving AI decisions, Bitcoin timestamps and human authorship — sebbi.pro",
               "Plain answers to how to prove an AI decision, keep tamper-proof AI audit logs, meet EU AI Act record-keeping, timestamp files in Bitcoin and prove a human wrote something.",
               "/answers", ld), _HEADER, '<main class="wrap">', '<div class="crumb">ANSWERS</div>',
         "<h1>Straight answers about proving what AI did</h1>",
         '<p class="answer">How to prove an AI decision, keep logs nobody can alter, meet the EU AI Act, timestamp anything in Bitcoin, and prove a human wrote it. Each answer says exactly how, and where to do it.</p>',
         '<div class="list">']
    for a in ANSWERS:
        h.append('<a href="/answers/%s"><b>%s</b><span>%s</span></a>' % (a["slug"], _esc(a["q"]), _esc(_short(a["a"], 140))))
    h.append('<a href="/standard/forever-proof"><b>The Forever Proof standard</b><span>The open proof format anyone can implement.</span></a>')
    h.append("</div></main>" + _FOOTER + "</body></html>")
    return "".join(h)


EXAMPLE_BUNDLE = """{
  "format": "sebbi-forever-proof/1",
  "subject": { "kind": "hash", "code": "NT-7Q2M-X9KD", "digest": "<sha256 of the file>" },
  "leaf": "sebbi-notary/1|<sha256 of the file>",
  "merkle": {
    "algorithm": "RFC 6962 SHA-256 (leaf 0x00, node 0x01)",
    "index": 41, "tree_size": 300,
    "path": ["<hex>", "<hex>", "..."],
    "root": "<hex>"
  },
  "bitcoin": { "state": "confirmed", "heights": [917204], "proof_ots_base64": "<OpenTimestamps proof of the root>" }
}"""


def standard_page():
    ld = {"@context": "https://schema.org", "@type": "TechArticle",
          "headline": "Forever Proof (sebbi-forever-proof/1) - an open format for proving a fingerprint existed before a Bitcoin block",
          "author": {"@type": "Organization", "name": "Monop Content"}, "url": SITE + "/standard/forever-proof",
          "isAccessibleForFree": True}
    rows = [("format", "Always <code>sebbi-forever-proof/1</code>."),
            ("subject", "What is being proven. <code>kind</code> is <code>hash</code> (a notarised fingerprint), <code>humankeys</code> (a Human Keys proof) or <code>chain_block</code> (a block on a sebbi.pro chain), with the fields for that kind."),
            ("leaf", "The exact UTF-8 string placed in the tree. <code>hash</code>: <code>sebbi-notary/1|&lt;digest&gt;</code>. <code>humankeys</code>: <code>sebbi-humankeys/1|&lt;code&gt;|&lt;text_hash&gt;|&lt;verdict&gt;|&lt;sealed_at&gt;</code>. <code>chain_block</code>: the block's audit hash."),
            ("merkle", "<code>index</code>, <code>tree_size</code>, <code>path</code> (sibling hashes, leaf upwards, hex) and <code>root</code>. RFC 6962: leaf hash = SHA-256(0x00 &#8214; leaf), node = SHA-256(0x01 &#8214; left &#8214; right). Verified with the RFC 9162 §2.1.3.2 algorithm."),
            ("bitcoin", "<code>proof_ots_base64</code>: a standard OpenTimestamps detached proof whose file digest is the Merkle root. <code>state</code> is <code>pending</code> until a Bitcoin attestation is present.")]
    steps = ["Recompute the leaf from what you hold (the file's SHA-256, the Human Keys text fingerprint, or the chain block) and compare with <code>leaf</code>.",
             "Hash the leaf and fold it up <code>path</code> to the root. It must equal <code>merkle.root</code>.",
             "Decode the OpenTimestamps proof. Its file digest must equal the root.",
             "Replay every operation in the proof. For each Bitcoin attestation, the resulting message, byte-reversed, must equal that block's Merkle root as reported by independent sources or your own node.",
             "The subject existed before that block's time."]
    h = [_head("Forever Proof standard (sebbi-forever-proof/1) — sebbi.pro",
               "An open, free-to-implement format for proving a fingerprint existed before a Bitcoin block: leaf, RFC 6962 Merkle path and an OpenTimestamps proof.",
               "/standard/forever-proof", ld), _HEADER, '<main class="wrap">',
         '<div class="crumb">OPEN STANDARD · VERSION 1</div>',
         "<h1>Forever Proof</h1>",
         '<p class="answer">A small JSON document that proves a fingerprint existed before a specific Bitcoin block was mined, checkable by anyone with no help from whoever issued it. The format is open: anyone may produce or verify Forever Proofs, with no permission or fee.</p>',
         "<h2>The document</h2><pre>%s</pre>" % _esc(EXAMPLE_BUNDLE),
         "<h2>Fields</h2><table><tbody>%s</tbody></table>" % "".join("<tr><td>%s</td><td>%s</td></tr>" % r for r in rows),
         "<h2>Verifying</h2><ol>%s</ol>" % "".join("<li>%s</li>" % s for s in steps),
         '<p class="more">Built on two existing open standards: RFC 6962 Merkle trees (as used by Certificate Transparency) and OpenTimestamps. Nothing proprietary sits between the subject and Bitcoin.</p>',
         "<h2>Reference implementations</h2>",
         '<p class="more">Python, standard library only: <a href="/forever-verify.py" style="color:var(--gold2)">forever-verify.py</a>. In-browser JavaScript: the verifier on <a href="/forever" style="color:var(--gold2)">sebbi.pro/forever</a> (view source). Proofs are issued by <a href="/x/notary/spec" style="color:var(--gold2)">the sebbi.pro notary</a>.</p>',
         '<div class="do"><a href="/forever-verify.py">Download the verifier</a><a href="/forever">Verify in your browser</a></div>',
         "</main>" + _FOOTER + "</body></html>"]
    return "".join(h)


def sitemap():
    urls = [SITE + "/answers", SITE + "/standard/forever-proof", SITE + "/forever", SITE + "/bitcoin",
            SITE + "/bitcoin/code", SITE + "/gateway", SITE + "/standard/ai-decision-receipt"] + [SITE + "/answers/" + a["slug"] for a in ANSWERS]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
            "".join("  <url><loc>%s</loc><changefreq>weekly</changefreq></url>\n" % u for u in urls) + "</urlset>\n")


def _llms():
    try:
        with open(os.path.join(ROOT, "llms.txt"), "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None


def _send(h, body, ctype):
    if isinstance(body, str):
        body = body.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "public, max-age=300")
    h.end_headers()
    if getattr(h, "command", "GET") != "HEAD":
        h.wfile.write(body)
    _state["served"] += 1


def _install_pages():
    if _state["pages"]:
        return True
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_answers_pages", False):
        _state["pages"] = True
        return True
    orig = H.do_GET

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/") or "/"
        try:
            if p == "/answers":
                return _send(self, index_page(), "text/html; charset=utf-8")
            if p.startswith("/answers/") and p[9:] in BY_SLUG:
                return _send(self, answer_page(BY_SLUG[p[9:]]), "text/html; charset=utf-8")
            if p == "/standard/forever-proof":
                return _send(self, standard_page(), "text/html; charset=utf-8")
            if p == "/sitemap-answers.xml":
                return _send(self, sitemap(), "application/xml; charset=utf-8")
            if p == "/llms.txt":
                body = _llms()
                if body:
                    return _send(self, body, "text/plain; charset=utf-8")
        except Exception as e:
            _state["last_error"] = str(e)[:200]
        return orig(self)

    H.do_GET = do_GET
    H._answers_pages = True
    _state["pages"] = True
    return True


def handle(method, action, data, api_key, ctx):
    with _lock:
        try:
            _install_pages()
        except Exception as e:
            _state["last_error"] = str(e)[:200]
    if action == "spec":
        return {"module": "answers", "version": VERSION,
                "pages": [SITE + "/answers"] + [SITE + "/answers/" + a["slug"] for a in ANSWERS],
                "standard": SITE + "/standard/forever-proof", "llms_txt": SITE + "/llms.txt",
                "sitemap": SITE + "/sitemap-answers.xml"}, 200
    return {"module": "answers", "version": VERSION, "armed": _state["pages"], "answers": len(ANSWERS),
            "index": SITE + "/answers", "llms_txt": SITE + "/llms.txt", "llms_txt_present": bool(_llms()),
            "sitemap": SITE + "/sitemap-answers.xml", "served": _state["served"],
            "last_error": _state["last_error"]}, 200
