# Codebase — part 6 of 49

Contains:
- `modules/connect.py`
- `modules/consistency.py`


## `modules/connect.py`

823 lines, 60047 bytes

```python
"""
modules/connect.py  v1.1.0  -  plug your AI in, build your own rules

    Pages:  https://sebbi.pro/connect   hook any AI up to sebbi.pro
            https://sebbi.pro/build     build a Signal Pack, rule by rule
    Arm:    https://sebbi.pro/x/arm/status

/connect
    Leads with the AI-assistant route: add https://sebbi.pro/mcp to Claude,
    ChatGPT, Cursor, VS Code or Claude Code and the assistant does the setup
    (served by modules/mcp.py). Then the manual route:
    get a key (or paste one), pick how you build - Python, Node, cURL, an
    OpenAI or Anthropic app, LangChain, Lovable, Bolt, Replit, Cursor, v0,
    Zapier, Make, n8n - and get the exact snippet or prompt with your key
    in it. Then fire a real decision from the page and watch it land in the
    chain, with links to its block and its machine-proof report.

/build
    A Signal Pack builder that speaks English. Every signal is explained in
    plain words, every rule is shown as the sentence it means, and the pack
    is checked against the real validator as you type. A test bench runs
    the rules in the browser so you can see what a request would get before
    you publish. Publishing seals it into the library at /packs.html.

HOMEPAGE
    Adds a strip above the homepage footer: the AI Business feature and the
    new tools. Done the same way as the brand module - the page is rewritten
    as it is served; index.html is not edited.

No existing file is changed. Everything here talks to routes that already
exist: /signup, /api/govern, /x/packs/validate, /x/packs/publish.
"""

import sys
import threading

VERSION = "1.1.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

FEATURE_ARTICLE = "https://aibusiness.vc/startups/sebbi-aileash-justin-dobson-seal-every-ai-decision"
FEATURE_EXPERT = "https://aibusiness.vc/experts/justin-dobson"

_state = {"pages": False, "strip": False, "injected": 0, "last_error": None}
_lock = threading.Lock()


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "Handler"):
        m = sys.modules.get("server")
    return m


def _send(h, body, ctype="text/html; charset=utf-8"):
    b = body.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(b)))
    h.send_header("Cache-Control", "public, max-age=120")
    h.end_headers()
    h.wfile.write(b)


# ---------------------------------------------------------------------
# homepage strip, injected as the page is served
# ---------------------------------------------------------------------

STRIP = """
<section class="sbx" aria-label="Featured and new">
<style>
.sbx{background:#0a0f1e;border-top:1px solid rgba(201,168,76,.25);border-bottom:1px solid rgba(201,168,76,.25);padding:56px 16px;color:#fff;font-family:'IBM Plex Sans',system-ui,sans-serif}
.sbx *{box-sizing:border-box}
.sbx-in{max-width:1080px;margin:0 auto;display:grid;grid-template-columns:1fr 1.35fr;gap:48px;align-items:start}
@media(max-width:820px){.sbx-in{grid-template-columns:1fr;gap:34px}}
.sbx-feat a{color:inherit;text-decoration:none}
.sbx-feat .src{font-size:13px;color:#c9a84c;margin-bottom:12px;display:flex;gap:10px;align-items:center}
.sbx-feat .src i{display:inline-block;width:26px;height:1px;background:#c9a84c}
.sbx-feat h3{font-family:'Newsreader',Georgia,serif;font-weight:500;font-size:clamp(26px,3.4vw,36px);line-height:1.12;margin:0 0 14px;color:#fff}
.sbx-feat p{color:rgba(255,255,255,.66);font-size:15px;line-height:1.6;margin:0 0 18px;max-width:46ch}
.sbx-feat .lk{display:inline-block;margin-right:18px;color:#f0d78a;font-size:14px;border-bottom:1px solid rgba(240,215,138,.4);padding-bottom:2px}
.sbx-tools{display:grid;grid-template-columns:1fr 1fr;border:1px solid rgba(201,168,76,.22);border-radius:14px;overflow:hidden}
@media(max-width:520px){.sbx-tools{grid-template-columns:1fr}}
.sbx-tools a{display:block;padding:22px 22px 24px;color:#fff;text-decoration:none;background:#0d1426;border-right:1px solid rgba(201,168,76,.14);border-bottom:1px solid rgba(201,168,76,.14);transition:background .2s}
.sbx-tools a:hover,.sbx-tools a:focus-visible{background:#131d36;outline:none}
.sbx-tools a:focus-visible{box-shadow:inset 0 0 0 2px #c9a84c}
.sbx-tools b{display:block;font-family:'Newsreader',Georgia,serif;font-weight:500;font-size:21px;margin-bottom:6px}
.sbx-tools span{display:block;color:rgba(255,255,255,.6);font-size:14px;line-height:1.5}
.sbx-tools em{display:block;font-style:normal;color:#c9a84c;font-size:13px;margin-top:12px}
</style>
<div class="sbx-in">
 <div class="sbx-feat">
  <div class="src"><i></i>Featured on AI Business</div>
  <h3><a href="__ARTICLE__">sebbi.pro on AI Business: seal every AI decision</a></h3>
  <p>AI Business put sebbi.pro through an independent review before featuring it, and lists its founder among its AI experts.</p>
  <a class="lk" href="__ARTICLE__">Read the feature</a><a class="lk" href="__EXPERT__">On the experts page</a>
 </div>
 <div class="sbx-tools">
  <a href="https://sebbi.pro/connect"><b>Connect your AI</b><span>Pick how you build, copy one snippet, and watch your first decision land in the chain.</span><em>Takes about a minute</em></a>
  <a href="https://sebbi.pro/build"><b>Build your own rules</b><span>Write the rules your AI has to follow in plain English, test them, and publish.</span><em>Free to build and publish</em></a>
  <a href="https://sebbi.pro/keys"><b>Prove a human typed it</b><span>Type it live and get a sealed code that proves a person wrote it, not a machine.</span><em>50p a month, unlimited</em></a>
  <a href="https://sebbi.pro/dossier"><b>The machine-proof report</b><span>Every detail of one AI decision, proven unchanged, ready for the auditor.</span><em>Included with your key</em></a>
 </div>
</div>
</section>
""".replace("__ARTICLE__", FEATURE_ARTICLE).replace("__EXPERT__", FEATURE_EXPERT)

STRIP_B = STRIP.encode("utf-8")


class _Out(object):
    def __init__(self, real):
        self.real, self.buf, self.mode = real, bytearray(), None

    def write(self, data):
        if self.mode == "pass":
            return self.real.write(data)
        self.buf += data
        if self.mode is None:
            end = self.buf.find(b"\r\n\r\n")
            if end < 0:
                if len(self.buf) > 65536:
                    self._go_pass()
                return len(data)
            head = bytes(self.buf[:end]).lower()
            if b"content-type: text/html" in head and b"content-encoding" not in head:
                self.mode = "html"
            else:
                self._go_pass()
        return len(data)

    def _go_pass(self):
        self.mode = "pass"
        if self.buf:
            self.real.write(bytes(self.buf))
        self.buf = bytearray()

    def flush(self):
        if self.mode == "pass":
            try:
                self.real.flush()
            except Exception:
                pass

    @property
    def closed(self):
        return getattr(self.real, "closed", False)

    def __getattr__(self, name):
        return getattr(self.real, name)

    def finish(self, inject):
        if self.mode == "pass" or not self.buf:
            return
        raw = bytes(self.buf)
        self.buf = bytearray()
        end = raw.find(b"\r\n\r\n")
        if not inject or self.mode != "html" or end < 0:
            self.real.write(raw)
            return
        head, body = raw[:end], raw[end + 4:]
        at = body.find(b"<footer")
        if at < 0:
            at = body.rfind(b"</body>")
        if at < 0 or b'class="sbx"' in body:
            self.real.write(raw)
            return
        body = body[:at] + STRIP_B + body[at:]
        lines = [l for l in head.split(b"\r\n") if not l.lower().startswith(b"content-length:")]
        lines.append(b"Content-Length: " + str(len(body)).encode())
        self.real.write(b"\r\n".join(lines) + b"\r\n\r\n" + body)
        _state["injected"] += 1
        try:
            self.real.flush()
        except Exception:
            pass


def _install_strip():
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_connect_strip", False):
        return True
    original = H.handle_one_request

    def handle_one_request(self):
        real = self.wfile
        out = _Out(real)
        self.wfile = out
        try:
            original(self)
        finally:
            self.wfile = real
            try:
                path = (getattr(self, "path", "") or "").split("?")[0]
                out.finish(path in ("/", "/index.html") and getattr(self, "command", "") == "GET")
            except Exception as e:
                _state["last_error"] = str(e)[:200]
                try:
                    if out.buf:
                        real.write(bytes(out.buf))
                except Exception:
                    pass

    H.handle_one_request = handle_one_request
    H._connect_strip = True
    return True


def _install_pages():
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_connect_pages", False):
        return True
    orig = H.do_GET

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/")
        if p == "/connect":
            return _send(self, CONNECT_PAGE)
        if p == "/build":
            return _send(self, BUILD_PAGE)
        return orig(self)

    H.do_GET = do_GET
    H._connect_pages = True
    return True


def arm():
    with _lock:
        _state["pages"] = _install_pages()
        _state["strip"] = _install_strip()


def handle(method, action, data, api_key, ctx):
    try:
        arm()
    except Exception as e:
        _state["last_error"] = "arm: %s" % e
    if action == "spec":
        return {"module": "connect", "version": VERSION,
                "pages": {"connect": "https://sebbi.pro/connect", "build": "https://sebbi.pro/build"},
                "homepage_strip": "AI Business feature and the new tools, added above the homepage footer as it is served",
                "uses": ["/signup", "/api/govern", "/x/packs/validate", "/x/packs/publish"]}, 200
    return {"module": "connect", "version": VERSION, "armed": _state["pages"] and _state["strip"],
            "pages": ["https://sebbi.pro/connect", "https://sebbi.pro/build"],
            "homepage_strip_served": _state["injected"], "last_error": _state["last_error"]}, 200


# ---------------------------------------------------------------------
# shared look
# ---------------------------------------------------------------------

HEAD = r"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--ink:#0a0f1e;--deep:#0d1426;--raise:#131d36;--gold:#c9a84c;--pale:#f0d78a;--parch:#efe6cc;--live:#5fd3c4;--warn:#f0b35a;--stop:#ff8a80;
--mut:rgba(239,230,204,.62);--line:rgba(201,168,76,.2);--serif:'Newsreader',Georgia,serif;--sans:'IBM Plex Sans',system-ui,sans-serif;--mono:'IBM Plex Mono',ui-monospace,monospace}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--ink);color:var(--parch);font-family:var(--sans);font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased;padding-bottom:env(safe-area-inset-bottom,0)}
a{color:var(--pale)}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.top{border-bottom:1px solid var(--line)}
.top .in{max-width:1120px;margin:0 auto;padding:15px 16px;display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.brand{font-family:var(--serif);font-size:19px;color:#fff;text-decoration:none}.brand b{color:var(--gold);font-weight:500}
.nav a{color:var(--mut);text-decoration:none;font-size:14px;margin-left:18px}.nav a:hover{color:#fff}.nav a.on{color:var(--pale)}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px}
h1{font-family:var(--serif);font-weight:400;font-size:clamp(40px,7.4vw,84px);line-height:.98;letter-spacing:-.015em;color:#fff}
h2{font-family:var(--serif);font-weight:500;font-size:clamp(26px,3.6vw,38px);line-height:1.1;color:#fff}
h3{font-family:var(--serif);font-weight:500;font-size:22px;color:#fff}
.lede{font-size:clamp(17px,2vw,19px);color:var(--mut);max-width:58ch;margin-top:18px}
.step{display:grid;grid-template-columns:64px 1fr;gap:20px;padding:46px 0;border-top:1px solid var(--line)}
@media(max-width:640px){.step{grid-template-columns:1fr;gap:10px;padding:34px 0}}
.num{font-family:var(--serif);font-size:44px;line-height:1;color:var(--gold)}
.step p.hint{color:var(--mut);font-size:15px;margin-top:6px;max-width:62ch}
input,select,textarea{width:100%;background:var(--deep);border:1px solid var(--line);border-radius:8px;color:#fff;padding:12px 13px;font-family:var(--sans);font-size:15px}
textarea{font-family:var(--mono);font-size:13px;resize:vertical}
input:focus,select:focus,textarea:focus{border-color:var(--gold);outline:none}
label.f{display:block;font-size:13px;color:var(--mut);margin:14px 0 6px}
.row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}@media(max-width:700px){.row{grid-template-columns:1fr}}
.btn{display:inline-block;background:var(--gold);color:var(--ink);border:0;border-radius:999px;padding:13px 22px;font-family:var(--sans);font-size:15px;font-weight:600;cursor:pointer;text-decoration:none}
.btn:hover{background:var(--pale)}.btn.ghost{background:transparent;color:var(--pale);border:1px solid rgba(240,215,138,.45)}.btn[disabled]{opacity:.45;cursor:default}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;align-items:center}
.msg{font-size:14px;margin-top:12px;min-height:1.2em}.msg.ok{color:var(--live)}.msg.err{color:var(--stop)}
pre{background:#070b17;border:1px solid var(--line);border-radius:10px;padding:16px;overflow:auto;font-family:var(--mono);font-size:12.5px;line-height:1.65;color:#d9d2bc;white-space:pre}
.foot{border-top:1px solid var(--line);margin-top:40px;padding:26px 0;color:var(--mut);font-size:14px}
.foot a{color:var(--pale);text-decoration:none;margin-right:16px}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>"""

NAV = r"""<div class="top"><div class="in"><a class="brand" href="https://sebbi.pro/">sebbi<b>.pro</b></a>
<nav class="nav"><a href="https://sebbi.pro/connect" class="__C">Connect</a><a href="https://sebbi.pro/build" class="__B">Build</a><a href="https://sebbi.pro/keys">Human Keys</a><a href="https://sebbi.pro/developers">Developers</a></nav></div></div>"""

FOOT = r"""<div class="wrap foot">Monop Content &nbsp; <a href="https://sebbi.pro/developers">Developers</a><a href="https://sebbi.pro/packs.html">Pack library</a><a href="https://sebbi.pro/dossier">Machine-proof report</a><a href="__ARTICLE__">Featured on AI Business</a></div>""".replace("__ARTICLE__", FEATURE_ARTICLE)


# ---------------------------------------------------------------------
# /connect
# ---------------------------------------------------------------------

CONNECT_PAGE = HEAD + r"""
<title>Connect your AI · sebbi.pro</title>
<meta name="description" content="Plug any AI into sebbi.pro in about a minute. Pick how you build, copy one snippet, and watch your first decision get scored and sealed.">
<style>
.hero{padding:64px 0 40px}
.wire{margin-top:44px;border:1px solid var(--line);border-radius:18px;background:radial-gradient(120% 140% at 0% 0%,rgba(201,168,76,.08),transparent 60%),var(--deep);padding:26px}
.wire-row{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;align-items:center;gap:0}
@media(max-width:720px){.wire-row{grid-template-columns:1fr;gap:6px}.wire-row .line{height:34px;width:2px;margin:0 auto}}
.node{border:1px solid var(--line);border-radius:12px;padding:14px 16px;background:var(--ink);min-height:92px}
.node small{display:block;font-size:12.5px;color:var(--mut)}
.node strong{display:block;font-family:var(--serif);font-weight:500;font-size:21px;color:#fff;margin-top:2px}
.node .v{font-family:var(--mono);font-size:12.5px;color:var(--mut);margin-top:6px;word-break:break-all}
.line{height:2px;width:64px;background:rgba(201,168,76,.18);position:relative;overflow:hidden}
.line i{position:absolute;inset:0;background:linear-gradient(90deg,transparent,var(--pale),transparent);transform:translateX(-100%)}
.wire.go .line i{animation:pulse .9s ease-out forwards}
.wire.go .l2 i{animation-delay:.45s}
@media(max-width:720px){.line i{background:linear-gradient(180deg,transparent,var(--pale),transparent);transform:translateY(-100%)}.wire.go .line i{animation-name:pulsev}}
@keyframes pulse{to{transform:translateX(100%)}}@keyframes pulsev{to{transform:translateY(100%)}}
.node.lit{border-color:var(--gold);box-shadow:0 0 0 1px rgba(201,168,76,.35),0 0 40px rgba(201,168,76,.12)}
.verdict-ALLOW{color:var(--live)!important}.verdict-CHALLENGE{color:var(--warn)!important}.verdict-BLOCK{color:var(--stop)!important}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin-top:16px}
.tab{background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:999px;padding:8px 15px;font-size:14px;cursor:pointer;font-family:var(--sans)}
.tab.on{background:var(--raise);color:#fff;border-color:var(--gold)}
.stack{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}
.stack button{background:var(--deep);border:1px solid var(--line);color:var(--parch);border-radius:10px;padding:10px 14px;font-size:14.5px;cursor:pointer;font-family:var(--sans)}
.stack button:hover{border-color:rgba(201,168,76,.5)}
.stack button.on{background:var(--parch);color:var(--ink);border-color:var(--parch)}
.group{font-size:13px;color:var(--mut);margin:20px 0 -6px}
.snip{margin-top:20px}
.snip .how{color:var(--mut);font-size:15px;margin-bottom:12px;max-width:64ch}
.snip .tool{display:inline-block;margin:0 0 12px;font-size:14px}
.keyline{font-family:var(--mono);font-size:13px;color:var(--live);margin-top:10px;word-break:break-all}
.next{display:grid;grid-template-columns:repeat(3,1fr);gap:0;border:1px solid var(--line);border-radius:14px;overflow:hidden;margin-top:18px}
@media(max-width:760px){.next{grid-template-columns:1fr}}
.next a{display:block;padding:20px;text-decoration:none;color:var(--parch);border-right:1px solid var(--line);background:var(--deep)}
.next a:last-child{border-right:0}.next a:hover{background:var(--raise)}
.next b{display:block;font-family:var(--serif);font-weight:500;font-size:20px;color:#fff;margin-bottom:4px}.next span{font-size:14px;color:var(--mut)}

.ai{padding:10px 0 46px}
.mcp{margin-top:20px;border:1px solid var(--gold);border-radius:18px;padding:22px;background:linear-gradient(160deg,rgba(201,168,76,.10),rgba(13,20,38,1) 55%)}
.mcp-url{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.mcp-url span{font-family:var(--mono);font-size:clamp(17px,2.6vw,24px);color:#fff;word-break:break-all}
.mcp-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:20px;border-top:1px solid var(--line)}
@media(max-width:760px){.mcp-grid{grid-template-columns:1fr}}
.mcp-grid div{padding:14px 14px 14px 0;border-bottom:1px solid var(--line)}
.mcp-grid b{display:block;font-family:var(--serif);font-weight:500;font-size:19px;color:#fff;margin-bottom:4px}
.mcp-grid span{font-size:14px;color:var(--mut)}
.mcp-grid code{font-family:var(--mono);font-size:12px;color:var(--live);word-break:break-all}
.mcp-grid .btn{padding:9px 16px;font-size:14px;margin-top:2px}
</style></head><body>
""" + NAV.replace("__C", "on").replace("__B", "") + r"""
<div class="wrap">
<section class="hero">
<h1>Plug your AI into<br>sebbi.pro.</h1>
<p class="lede">Every decision your AI makes, scored in under 30 milliseconds and sealed into a chain nobody can quietly edit. Pick how you build, copy one snippet, and watch your first decision land. Or <a href="#ai">let your AI assistant do the whole thing</a>.</p>
<div class="wire" id="wire" aria-live="polite">
 <div class="wire-row">
  <div class="node" id="n1"><small>Your AI</small><strong id="n1t">Waiting for a decision</strong><div class="v" id="n1v">refund · £120 · customer-42</div></div>
  <div class="line l1"><i></i></div>
  <div class="node" id="n2"><small>sebbi.pro scores it</small><strong id="n2t">Nine signals</strong><div class="v" id="n2v">trust, velocity, amount, device…</div></div>
  <div class="line l2"><i></i></div>
  <div class="node" id="n3"><small>Sealed into the chain</small><strong id="n3t">Block —</strong><div class="v" id="n3v">anyone can check it</div></div>
 </div>
 <div class="btns"><button class="btn" id="fire">Fire a test decision</button><span class="msg" id="fmsg">Add your key in step one first.</span></div>
 <div class="btns" id="after" style="display:none"><a class="btn ghost" id="lblock" href="#">Open the block</a><a class="btn ghost" id="lrep" href="#">Machine-proof report</a></div>
</div>
</section>

<section class="ai" id="ai">
<h2>Or let your AI do all of it.</h2>
<p class="hint">Add sebbi.pro to your AI assistant once. Then just ask it: "set me up on sebbi.pro". It reads the products, advises on the right setup for how you build, shows you the terms, opens your account, writes the code or the prompt, fires your first decision, builds your rules and sets up billing, all in the conversation.</p>
<div class="mcp">
 <div class="mcp-url"><span id="murl">https://sebbi.pro/mcp</span><button class="btn" id="mcopy">Copy connector link</button></div>
 <div class="mcp-grid">
  <div><b>Claude</b><span>Open <a href="https://claude.ai/settings/connectors" rel="noopener">Settings, then Connectors</a>, choose Add custom connector and paste the link.</span></div>
  <div><b>ChatGPT</b><span>Add a custom connector in Settings and paste the link.</span></div>
  <div><b>Cursor</b><span><a class="btn ghost" href="cursor://anysphere.cursor-deeplink/mcp/install?name=sebbi&config=eyJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8vbWNwIn0=">Add to Cursor</a></span></div>
  <div><b>VS Code</b><span><a class="btn ghost" href="vscode:mcp/install?%7B%22name%22%3A%20%22sebbi%22%2C%20%22type%22%3A%20%22http%22%2C%20%22url%22%3A%20%22https%3A//sebbi.pro/mcp%22%7D">Add to VS Code</a></span></div>
  <div><b>Claude Code</b><span><code id="ccmd">claude mcp add --transport http sebbi https://sebbi.pro/mcp</code></span></div>
  <div><b>Anything else</b><span>Any assistant that takes an MCP server link works with the same address.</span></div>
 </div>
 <p class="hint" style="margin-top:14px">Same terms as signing up here: free for 90 days, then 50p per device per month. Your assistant shows you the terms before anything is opened, and your agreement is sealed with a receipt.</p>
</div>
</section>

<section class="step"><div class="num">1</div><div>
<h2>Your key</h2>
<p class="hint">Free for 90 days, no card. After that 50p per device per month, counted on the real devices that used it.</p>
<div class="tabs"><button class="tab on" data-t="new">Get a free key</button><button class="tab" data-t="have">I have a key</button></div>
<div id="t-new">
 <div class="row"><div><label class="f" for="nm">Your name</label><input id="nm" autocomplete="name"></div>
 <div><label class="f" for="em">Work email</label><input id="em" type="email" autocomplete="email"></div>
 <div><label class="f" for="org">Company</label><input id="org" autocomplete="organization"></div></div>
 <div class="btns"><button class="btn" id="getkey">Get my key</button></div>
</div>
<div id="t-have" style="display:none">
 <label class="f" for="pk">API key</label><input id="pk" placeholder="al_live_…" autocomplete="off">
 <div class="btns"><button class="btn" id="usekey">Use this key</button></div>
</div>
<div class="msg" id="kmsg"></div><div class="keyline" id="kline"></div>
</div></section>

<section class="step"><div class="num">2</div><div>
<h2>How do you build?</h2>
<p class="hint">Your key is written into every snippet for you. Keep it out of code you share; each tool below says where secrets go.</p>
<div class="group">Code</div>
<div class="stack" data-g="code"><button data-s="python">Python</button><button data-s="node">Node.js</button><button data-s="curl">cURL</button><button data-s="openai">OpenAI app</button><button data-s="anthropic">Anthropic app</button><button data-s="langchain">LangChain</button></div>
<div class="group">AI app builders</div>
<div class="stack" data-g="ai"><button data-s="lovable">Lovable</button><button data-s="bolt">Bolt</button><button data-s="replit">Replit</button><button data-s="cursor">Cursor</button><button data-s="v0">v0</button></div>
<div class="group">No-code automation</div>
<div class="stack" data-g="nc"><button data-s="zapier">Zapier</button><button data-s="make">Make</button><button data-s="n8n">n8n</button></div>
<div class="snip" id="snip"></div>
</div></section>

<section class="step"><div class="num">3</div><div>
<h2>Watch it land</h2>
<p class="hint">Scroll back up and fire a test decision. It is a real call with your key: scored by the live engine, sealed into the production chain, and checkable by anyone at the block it returns.</p>
<div class="btns"><a class="btn ghost" href="#wire">Back to the wire</a></div>
</div></section>

<section class="step"><div class="num">4</div><div>
<h2>Then make it yours</h2>
<div class="next">
 <a href="https://sebbi.pro/build"><b>Build your own rules</b><span>Plain-English rules your AI has to follow, tested and published.</span></a>
 <a href="https://sebbi.pro/keys"><b>Prove a human signed off</b><span>Reviewers type their reason live; a sealed code proves a person wrote it.</span></a>
 <a href="https://sebbi.pro/dossier"><b>Pull the full report</b><span>Every detail of any decision, proven unchanged, in one document.</span></a>
</div>
</div></section>
</div>
""" + FOOT + r"""
<script>
(function(){
const $=s=>document.querySelector(s),$$=s=>Array.from(document.querySelectorAll(s));
let KEY='';try{KEY=sessionStorage.getItem('sebbi.key')||''}catch(e){}
function setKey(k){KEY=k;try{sessionStorage.setItem('sebbi.key',k)}catch(e){}
 $('#kline').textContent='Key ready: '+k.slice(0,10)+'…'+k.slice(-4);$('#fmsg').textContent='Ready. Fire it.';$('#fmsg').className='msg';if(cur)show(cur)}
if(KEY)setKey(KEY);
$$('.tab').forEach(b=>b.onclick=()=>{$$('.tab').forEach(x=>x.classList.toggle('on',x===b));$('#t-new').style.display=b.dataset.t==='new'?'':'none';$('#t-have').style.display=b.dataset.t==='have'?'':'none'});
function kmsg(t,c){const m=$('#kmsg');m.textContent=t;m.className='msg '+(c||'')}
$('#usekey').onclick=()=>{const k=$('#pk').value.trim();if(k.length<16){kmsg('That does not look like a full key.','err');return}setKey(k);kmsg('Using your key.','ok')};
$('#getkey').onclick=async()=>{const em=$('#em').value.trim();if(!em||em.indexOf('@')<1){kmsg('Add your work email.','err');return}
 const b=$('#getkey');b.disabled=true;kmsg('Creating your key…');
 try{const r=await fetch('/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('#nm').value.trim(),email:em,org:$('#org').value.trim(),product:'aileash',devices:1})});
  const d=await r.json();if(!r.ok||!d.api_key){kmsg(d.message||d.error||'Could not create a key.','err');b.disabled=false;return}
  setKey(d.api_key);kmsg('Your key is ready and on its way to your inbox with the install guide. Keep it safe.','ok');
  $('#kline').innerHTML='Your key: <b style="color:#fff">'+d.api_key+'</b>'}catch(e){kmsg('Could not reach sebbi.pro.','err');b.disabled=false}};
const K=()=>KEY||'YOUR_API_KEY';
const EV='{"user_id": "customer-42", "action": "refund", "amount": 120, "country": "UK", "device_id": "web-7f3a", "anomaly": 0.1, "device_risk": 0.05}';
const PROMPT=t=>'Before any important action in this app happens (a payment, refund, account change, approval or anything an AI decides), send it to sebbi.pro to be scored and sealed.\n\n'+
 '1. Store this secret as SEBBI_API_KEY: '+K()+'\n'+
 '2. Create a server-side function that POSTs JSON to https://sebbi.pro/api/govern with the header "Authorization: Bearer <SEBBI_API_KEY>" and these fields: user_id (the user\'s id), action (what is happening, e.g. "refund"), amount (number, 0 if none), country (2-letter code), device_id (a stable id for the device or session), anomaly (0 to 1, use 0 if unknown), device_risk (0 to 1, use 0 if unknown).\n'+
 '3. Read "decision" from the reply. ALLOW: carry on. CHALLENGE: ask the user to confirm or send it to a person. BLOCK: stop the action and show "This action needs review".\n'+
 '4. Save "audit_hash" and "block_index" from the reply next to the record, so every decision can be proven later.\n'+
 '5. Never expose the key in the browser; call sebbi.pro only from the server or an edge function.';
const S={
 python:{how:'Standard library only, nothing to install. Call it before your code acts on a decision.',code:()=>`import json, urllib.request

def sebbi(event):
    req = urllib.request.Request(
        "https://sebbi.pro/api/govern",
        data=json.dumps(event).encode(),
        headers={"Authorization": "Bearer ${K()}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=5))

verdict = sebbi(${EV})

if verdict["decision"] == "BLOCK":
    raise PermissionError("blocked for review")
print(verdict["decision"], verdict["block_index"])   # sealed, checkable by anyone`},
 node:{how:'Works in Node 18+, Deno, Bun and edge functions. Keep the key in an environment variable.',code:()=>`const res = await fetch("https://sebbi.pro/api/govern", {
  method: "POST",
  headers: { Authorization: "Bearer ${K()}", "Content-Type": "application/json" },
  body: JSON.stringify(${EV})
});
const verdict = await res.json();

if (verdict.decision === "BLOCK") throw new Error("blocked for review");
console.log(verdict.decision, verdict.block_index); // sealed into the chain`},
 curl:{how:'The whole protocol in one command.',code:()=>`curl -s https://sebbi.pro/api/govern \\
  -H "Authorization: Bearer ${K()}" \\
  -H "Content-Type: application/json" \\
  -d '${EV}'`},
 openai:{how:'Check every action the model chooses before your code carries it out.',code:()=>`from openai import OpenAI
import json, urllib.request

client = OpenAI()

def sebbi(event):
    req = urllib.request.Request("https://sebbi.pro/api/govern", data=json.dumps(event).encode(),
        headers={"Authorization": "Bearer ${K()}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=5))

reply = client.chat.completions.create(model="gpt-4o", messages=messages, tools=tools)
for call in reply.choices[0].message.tool_calls or []:
    args = json.loads(call.function.arguments)
    verdict = sebbi({"user_id": user_id, "action": call.function.name,
                     "amount": args.get("amount", 0), "country": "UK",
                     "device_id": session_id, "anomaly": 0, "device_risk": 0})
    if verdict["decision"] == "ALLOW":
        run_tool(call, args)
    else:
        hold_for_review(call, verdict)   # CHALLENGE or BLOCK, with the sealed block`},
 anthropic:{how:'Gate every tool Claude asks to use, and keep the sealed receipt with the result.',code:()=>`import anthropic, json, urllib.request

client = anthropic.Anthropic()

def sebbi(event):
    req = urllib.request.Request("https://sebbi.pro/api/govern", data=json.dumps(event).encode(),
        headers={"Authorization": "Bearer ${K()}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=5))

msg = client.messages.create(model="claude-sonnet-4-5", max_tokens=1024, tools=tools, messages=messages)
for block in msg.content:
    if block.type == "tool_use":
        verdict = sebbi({"user_id": user_id, "action": block.name,
                         "amount": block.input.get("amount", 0), "country": "UK",
                         "device_id": session_id, "anomaly": 0, "device_risk": 0})
        if verdict["decision"] == "ALLOW":
            result = run_tool(block)
        else:
            result = {"held": verdict["decision"], "block": verdict["block_index"]}`},
 langchain:{how:'Wrap any tool so it only runs once sebbi.pro allows it.',code:()=>`import json, urllib.request
from langchain_core.tools import tool

def sebbi(event):
    req = urllib.request.Request("https://sebbi.pro/api/govern", data=json.dumps(event).encode(),
        headers={"Authorization": "Bearer ${K()}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=5))

@tool
def issue_refund(customer_id: str, amount: float) -> str:
    '''Refund a customer.'''
    verdict = sebbi({"user_id": customer_id, "action": "refund", "amount": amount,
                     "country": "UK", "device_id": "agent-1", "anomaly": 0, "device_risk": 0})
    if verdict["decision"] != "ALLOW":
        return f"Held for review ({verdict['decision']}, block {verdict['block_index']})"
    return do_refund(customer_id, amount)`},
 lovable:{tool:['Open Lovable','https://lovable.dev'],how:'Paste this into the Lovable chat. It builds the edge function, stores the key as a secret and wires every important action through sebbi.pro.',code:()=>PROMPT('Lovable')},
 bolt:{tool:['Open Bolt','https://bolt.new'],how:'Paste this into Bolt. It adds the server route and wires your actions through it.',code:()=>PROMPT('Bolt')},
 replit:{tool:['Open Replit','https://replit.com'],how:'Paste this into Replit Agent. Put the key in Replit Secrets as SEBBI_API_KEY.',code:()=>PROMPT('Replit')},
 cursor:{tool:['Open Cursor','https://cursor.com'],how:'Paste this into Cursor chat with your project open. Add the key to your .env file.',code:()=>PROMPT('Cursor')},
 v0:{tool:['Open v0','https://v0.dev'],how:'Paste this into v0. It adds a server action that calls sebbi.pro.',code:()=>PROMPT('v0')},
 zapier:{tool:['Open Zapier','https://zapier.com'],how:'Add a "Webhooks by Zapier" step, choose Custom Request, and fill it in like this. Add a Filter after it so the Zap only continues when the decision is ALLOW.',code:()=>`Method:   POST
URL:      https://sebbi.pro/api/govern
Data pass-through: no
Data:     ${EV}
Headers:
  Authorization   Bearer ${K()}
  Content-Type    application/json

Next step:  Filter  ->  Only continue if  decision  (Text) Exactly matches  ALLOW`},
 make:{tool:['Open Make','https://www.make.com'],how:'Add the HTTP module "Make a request", then a filter on the next route.',code:()=>`URL:            https://sebbi.pro/api/govern
Method:         POST
Headers:        Authorization = Bearer ${K()}
                Content-Type  = application/json
Body type:      Raw  (JSON)
Request content: ${EV}
Parse response: Yes

Filter on the next route:  decision  Equal to  ALLOW`},
 n8n:{tool:['Open n8n','https://n8n.io'],how:'Add an HTTP Request node, then an IF node on the decision.',code:()=>`Method:          POST
URL:             https://sebbi.pro/api/govern
Authentication:  Generic Credential Type -> Header Auth
                 Name:  Authorization
                 Value: Bearer ${K()}
Send Body:       JSON
Body:            ${EV}

IF node:  {{ $json.decision }}  is equal to  ALLOW`}
};
let cur=null;
function esc(t){return t.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function show(k){cur=k;$$('.stack button').forEach(b=>b.classList.toggle('on',b.dataset.s===k));const s=S[k];
 $('#snip').innerHTML='<p class="how">'+s.how+'</p>'+(s.tool?'<a class="tool" href="'+s.tool[1]+'" rel="noopener">'+s.tool[0]+'</a>':'')+'<pre id="code">'+esc(s.code())+'</pre><div class="btns"><button class="btn ghost" id="copy">Copy</button></div>';
 $('#copy').onclick=()=>{navigator.clipboard.writeText(s.code());$('#copy').textContent='Copied'}}
$$('.stack button').forEach(b=>b.onclick=()=>show(b.dataset.s));show('python');
$('#mcopy').onclick=()=>{navigator.clipboard.writeText('https://sebbi.pro/mcp');$('#mcopy').textContent='Copied'};
$('#fire').onclick=async()=>{if(!KEY){$('#fmsg').textContent='Add your key in step one first.';$('#fmsg').className='msg err';document.querySelector('#t-new').scrollIntoView({behavior:'smooth'});return}
 const w=$('#wire'),f=$('#fire');f.disabled=true;w.classList.remove('go');void w.offsetWidth;['n1','n2','n3'].forEach(n=>$('#'+n).classList.remove('lit'));
 $('#n1t').textContent='Refund, £120';$('#n1').classList.add('lit');$('#fmsg').textContent='Sending…';$('#fmsg').className='msg';
 const amt=[40,120,480,2200][Math.floor(Math.random()*4)];$('#n1t').textContent='Refund, £'+amt;$('#n1v').textContent='refund · £'+amt+' · customer-42';
 try{const t0=performance.now();const r=await fetch('/api/govern',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+KEY},
   body:JSON.stringify({user_id:'customer-42',action:'refund',amount:amt,country:'UK',device_id:'sebbi-connect-test',anomaly:0.1,device_risk:0.05})});
  const d=await r.json();const ms=Math.round(performance.now()-t0);
  if(!r.ok){$('#fmsg').textContent=d.message||d.error||('Error '+r.status);$('#fmsg').className='msg err';f.disabled=false;return}
  w.classList.add('go');
  setTimeout(()=>{$('#n2').classList.add('lit');$('#n2t').innerHTML='<span class="verdict-'+d.decision+'">'+d.decision+'</span> · score '+d.score;$('#n2v').textContent=(d.reasons&&d.reasons.length?d.reasons.join(', '):'no risk reasons')+' · '+ms+' ms round trip'},450);
  setTimeout(()=>{$('#n3').classList.add('lit');$('#n3t').textContent='Block '+d.block_index;$('#n3v').textContent=(d.audit_hash||'').slice(0,24)+'…';
   $('#fmsg').textContent='Sealed. That decision is now permanent and checkable by anyone.';$('#fmsg').className='msg ok';
   $('#lblock').href='https://sebbi.pro/x/walk/block?index='+d.block_index;$('#lrep').href='https://sebbi.pro/dossier?block='+d.block_index;$('#after').style.display='flex';f.disabled=false;f.textContent='Fire another'},950);
 }catch(e){$('#fmsg').textContent='Could not reach sebbi.pro.';$('#fmsg').className='msg err';f.disabled=false}};
})();
</script></body></html>"""


# ---------------------------------------------------------------------
# /build
# ---------------------------------------------------------------------

BUILD_PAGE = HEAD + r"""
<title>Build your own rules · sebbi.pro</title>
<meta name="description" content="Write the rules your AI has to follow, in plain English. Test them against a sample request, then publish them to the sebbi.pro pack library, sealed and dated.">
<style>
.hero{padding:60px 0 26px}
.sentence{margin-top:30px;font-family:var(--serif);font-size:clamp(26px,3.8vw,44px);line-height:1.2;color:#fff;min-height:2.4em;max-width:30ch}
.sentence .k{color:var(--pale);border-bottom:1px solid rgba(240,215,138,.35)}
.sentence .then-allow{color:var(--live)}.sentence .then-downgrade{color:#9fc6ff}.sentence .then-challenge{color:var(--warn)}.sentence .then-block{color:var(--stop)}
.cols{display:grid;grid-template-columns:1.25fr 1fr;gap:28px;margin-top:34px;align-items:start}
@media(max-width:900px){.cols{grid-template-columns:1fr}}
.panel{border:1px solid var(--line);border-radius:16px;background:var(--deep);padding:22px}
.panel+.panel{margin-top:18px}
.sticky{position:sticky;top:14px}
@media(max-width:900px){.sticky{position:static}}
.tpl{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.tpl button{background:transparent;border:1px solid var(--line);color:var(--parch);border-radius:999px;padding:8px 14px;font-size:14px;cursor:pointer}
.tpl button:hover{border-color:var(--gold)}
.rule{border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:14px;background:var(--ink)}
.rule.sel{border-color:var(--gold)}
.rule-h{display:flex;justify-content:space-between;align-items:center;gap:10px}
.rule-h b{font-family:var(--serif);font-weight:500;font-size:19px;color:#fff}
.ic{background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:8px;width:34px;height:34px;cursor:pointer;font-size:15px}
.ic:hover{color:#fff;border-color:var(--gold)}
.cond{display:grid;grid-template-columns:1.4fr 1fr 1fr 34px;gap:8px;margin-top:10px;align-items:center}
@media(max-width:560px){.cond{grid-template-columns:1fr 1fr;}.cond .vbox{grid-column:1/2}.cond .ic{grid-column:2/3;justify-self:end}}
.meaning{font-size:13px;color:var(--mut);margin-top:4px;grid-column:1/-1}
.join{display:flex;gap:6px;margin-top:12px;font-size:14px;color:var(--mut);align-items:center}
.join button{background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:999px;padding:5px 12px;cursor:pointer;font-size:13px}
.join button.on{background:var(--raise);color:#fff;border-color:var(--gold)}
.verdicts{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:12px}
@media(max-width:560px){.verdicts{grid-template-columns:1fr 1fr}}
.verdicts button{background:var(--deep);border:1px solid var(--line);color:var(--parch);border-radius:10px;padding:10px 8px;cursor:pointer;font-size:13.5px;text-align:left}
.verdicts button small{display:block;color:var(--mut);font-size:11.5px;margin-top:2px;line-height:1.35}
.verdicts button.on{border-color:var(--gold);background:var(--raise);color:#fff}
.add{margin-top:10px;background:transparent;border:1px dashed var(--line);color:var(--pale);border-radius:10px;padding:10px;width:100%;cursor:pointer;font-size:14px}
.add:hover{border-color:var(--gold)}
.stat{display:flex;gap:10px;align-items:center;font-size:14px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--mut);flex:none}.dot.ok{background:var(--live)}.dot.err{background:var(--stop)}
.bench label{display:flex;justify-content:space-between;font-size:13.5px;color:var(--mut);margin-top:12px}
.bench label b{color:#fff;font-weight:500;font-family:var(--mono);font-size:12.5px}
input[type=range]{padding:0;border:0;background:transparent;accent-color:var(--gold);height:28px}
.outcome{font-family:var(--serif);font-size:24px;color:#fff;margin-top:14px;line-height:1.25}
.outcome small{display:block;font-family:var(--sans);font-size:14px;color:var(--mut);margin-top:6px}
details summary{cursor:pointer;color:var(--pale);font-size:14px;margin-top:14px}
.check{display:flex;gap:8px;align-items:center;font-size:14px;color:var(--parch);margin-top:12px}
.check input{width:auto}
</style></head><body>
""" + NAV.replace("__C", "").replace("__B", "on") + r"""
<div class="wrap">
<section class="hero">
<h1>Write the rules<br>your AI must follow.</h1>
<p class="lede">No code. Pick what to watch, say when it matters and what should happen, and the rule is written out as the sentence it means. Test it, then publish it: sealed, dated and yours.</p>
<div class="sentence" id="sentence" aria-live="polite"></div>
</section>

<div class="cols">
<div>
 <div class="panel">
  <h3>Start from</h3>
  <div class="tpl"><button data-t="runaway">Stop runaway agents</button><button data-t="budget">Guard the budget</button><button data-t="unattended">Careful when nobody's watching</button><button data-t="blank">A blank pack</button></div>
 </div>
 <div class="panel">
  <h3>Your rules</h3>
  <p class="hint" style="color:var(--mut);font-size:14.5px;margin-top:4px">Rules are checked from the top. The first one that matches decides. A pack can only make the engine stricter, never looser.</p>
  <div id="rules"></div>
  <button class="add" id="addrule">Add a rule</button>
  <label class="f" for="def">When no rule matches</label>
  <select id="def"><option value="allow">Let it through</option><option value="downgrade">Use the cheaper model</option><option value="challenge">Hold it for a person</option><option value="block">Block it</option></select>
 </div>
 <div class="panel">
  <h3>About the pack</h3>
  <div class="row" style="grid-template-columns:1fr 1fr"><div><label class="f" for="pn">Pack name</label><input id="pn" maxlength="80"></div><div><label class="f" for="pa">Your name or company</label><input id="pa" maxlength="80"></div></div>
  <div class="row" style="grid-template-columns:1fr 1fr"><div><label class="f" for="pv">Industry</label><select id="pv"></select></div><div><label class="f" for="pver">Version</label><input id="pver" value="1.0.0"></div></div>
  <label class="f" for="ps">One line a buyer would understand</label><input id="ps" maxlength="240">
 </div>
</div>

<div class="sticky">
 <div class="panel">
  <div class="stat"><span class="dot" id="vdot"></span><span id="vtext">Checking your pack…</span></div>
  <div class="btns"><button class="btn" id="pub" disabled>Publish to the library</button></div>
  <div class="msg" id="pmsg"></div>
 </div>
 <div class="panel bench">
  <h3>Try it on a request</h3>
  <p style="color:var(--mut);font-size:14px;margin-top:4px">Move the sliders to describe a request. The answer updates as you go.</p>
  <div id="bench"></div>
  <div class="check"><input type="checkbox" id="b_unattended"><label for="b_unattended">Nobody is watching this system</label></div>
  <div class="check"><input type="checkbox" id="b_deterministic" checked><label for="b_deterministic">The same question always gets the same answer</label></div>
  <div class="outcome" id="outcome"></div>
 </div>
 <div class="panel">
  <h3>What you're publishing</h3>
  <details><summary>See the pack as data</summary><pre id="json" style="margin-top:10px;max-height:340px"></pre></details>
 </div>
</div>
</div>
</div>
""" + FOOT + r"""
<script>
(function(){
const $=s=>document.querySelector(s);
const F={
 loop:{name:'the same request repeating',kind:'signal',hint:'0 means never seen before; 1 means the identical request keeps coming back — an agent going round in circles.'},
 burst:{name:'requests in the last minute',kind:'signal',hint:'How hard the last sixty seconds were. Near 1 is a burst — often a script or a stuck loop.'},
 grind:{name:'requests in the last hour',kind:'signal',hint:'Steady volume over the hour. Near 1 means it has been running flat out.'},
 exposure:{name:'spend against the budget left',kind:'signal',hint:'The worst this request could cost, compared with what is left in the budget. Near 1 means it could eat the lot.'},
 size:{name:'how big the prompt is',kind:'signal',hint:'Prompt length on a curve. Near 1 is a very large prompt.'},
 ask:{name:'how long an answer it may write',kind:'signal',hint:'The output ceiling the caller allowed. Near 1 is a very long answer.'},
 depth:{name:'how long the conversation is',kind:'signal',hint:'Turns in the thread. Near 1 means the whole history is re-sent every time.'},
 tools:{name:'how many tools are attached',kind:'signal',hint:'Tool definitions sent with the request. Near 1 is a lot of them.'},
 novelty:{name:'how unfamiliar the request is',kind:'signal',hint:'1 means this shape of request has never been seen before.'},
 score:{name:'the engine\'s overall risk score',kind:'signal',hint:'The engine\'s own 0-to-1 score from all nine signals.'},
 loop_count:{name:'times the same request was sent',kind:'count',max:20,hint:'A plain count of identical requests in a row.'},
 burst_count:{name:'requests this minute',kind:'count',max:200,hint:'A plain count over the last sixty seconds.'},
 grind_count:{name:'requests this hour',kind:'count',max:3000,hint:'A plain count over the last hour.'},
 turns:{name:'conversation turns',kind:'count',max:100,hint:'Messages in the thread so far.'},
 tool_count:{name:'tools attached',kind:'count',max:40,hint:'Number of tool definitions sent.'},
 max_tokens:{name:'answer length allowed (tokens)',kind:'count',max:32000,hint:'The output ceiling, in tokens.'},
 chars:{name:'prompt length (characters)',kind:'count',max:200000,hint:'Characters in the prompt.'},
 unattended:{name:'nobody is watching',kind:'flag',hint:'The caller said no human is supervising this system.'},
 deterministic:{name:'the answer is repeatable',kind:'flag',hint:'Temperature is zero, so the same question gets the same answer.'}
};
const OPS={'>=':'is at least','>':'is above','<=':'is at most','<':'is below','==':'is exactly'};
const V={allow:['Let it through','send it to the model as asked'],downgrade:['Use the cheaper model','small and simple enough for a cheaper model'],challenge:['Hold it for a person','wait for a human before spending'],block:['Block it','refuse; it never reaches the model']};
const VERB={allow:'let it through',downgrade:'switch to the cheaper model',challenge:'hold it for a person',block:'block it'};
const VERTS=['general','coding','support','legal','medical','finance','retail','ecommerce','education','research','translation','moderation','sales','recruitment','logistics','gaming','media','security','insurance','property','public-sector'];
$('#pv').innerHTML=VERTS.map(v=>'<option>'+v+'</option>').join('');
const T={
 runaway:{name:'Stop runaway agents',summary:'Catches AI agents stuck in loops before they run up the bill.',def:'allow',rules:[
  {join:'and',conds:[{f:'loop_count',op:'>=',v:3},{f:'unattended',op:'is',v:true}],then:'block',why:'An unattended agent sending the same request three times is stuck. Stop it before it spends more.'},
  {join:'and',conds:[{f:'loop_count',op:'>=',v:3}],then:'challenge',why:'The same request three times usually means a loop. A person should look before it continues.'},
  {join:'or',conds:[{f:'burst',op:'>=',v:0.8}],then:'challenge',why:'A sudden burst of requests looks like a script out of control.'}]},
 budget:{name:'Guard the budget',summary:'Holds expensive requests for a person and moves simple ones to a cheaper model.',def:'allow',rules:[
  {join:'and',conds:[{f:'exposure',op:'>=',v:0.7}],then:'challenge',why:'This one request could use most of what is left in the budget.'},
  {join:'and',conds:[{f:'size',op:'<',v:0.2},{f:'tools',op:'==',v:0},{f:'deterministic',op:'is',v:true}],then:'downgrade',why:'Short, simple, repeatable requests do not need the most expensive model.'}]},
 unattended:{name:'Careful when nobody\'s watching',summary:'Stricter rules for AI that runs without a person supervising it.',def:'allow',rules:[
  {join:'and',conds:[{f:'unattended',op:'is',v:true},{f:'score',op:'>=',v:0.6}],then:'block',why:'High risk with nobody watching: refuse rather than hope.'},
  {join:'and',conds:[{f:'unattended',op:'is',v:true},{f:'novelty',op:'>=',v:0.8}],then:'challenge',why:'Something it has never seen before, and no one supervising. A person should see it first.'}]},
 blank:{name:'',summary:'',def:'allow',rules:[{join:'and',conds:[{f:'loop',op:'>=',v:0.6}],then:'challenge',why:''}]}
};
let P=JSON.parse(JSON.stringify(T.runaway)),sel=0;
function fmtv(f,v){const d=F[f];if(d.kind==='flag')return v?'yes':'no';return d.kind==='signal'?Number(v).toFixed(2):String(v)}
function condText(c){const d=F[c.f];if(d.kind==='flag')return (c.v?'':'not ')+'<span class="k">'+d.name+'</span>';
 return '<span class="k">'+d.name+'</span> '+OPS[c.op]+' <span class="k">'+fmtv(c.f,c.v)+'</span>'}
function ruleSentence(r){if(!r)return'';const parts=r.conds.map(condText);
 return 'If '+parts.join(r.join==='and'?', and ':', or ')+', <span class="then-'+r.then+'">'+VERB[r.then]+'</span>'+(r.why?' — '+r.why.replace(/[<>]/g,'').replace(/\.$/,'')+'.':'.')}
function expr(c){const d=F[c.f];if(d.kind==='flag')return (c.v?'':'not ')+c.f;return c.f+' '+c.op+' '+(d.kind==='signal'?Number(c.v).toFixed(2).replace(/0+$/,'').replace(/\.$/,''):Math.round(c.v))}
function manifest(){return{name:$('#pn').value.trim(),author:$('#pa').value.trim(),version:$('#pver').value.trim()||'1.0.0',vertical:$('#pv').value,summary:$('#ps').value.trim(),
 rules:P.rules.map(r=>({when:r.conds.map(expr).join(' '+r.join+' '),then:r.then,why:r.why.trim()})),default:$('#def').value}}
function fieldOptions(cur){const g={signal:'Signals, 0 to 1',count:'Counts',flag:'Yes or no'};let h='';
 ['signal','count','flag'].forEach(k=>{h+='<optgroup label="'+g[k]+'">';Object.keys(F).filter(f=>F[f].kind===k).forEach(f=>{h+='<option value="'+f+'"'+(f===cur?' selected':'')+'>'+F[f].name+'</option>'});h+='</optgroup>'});return h}
function renderRules(){const box=$('#rules');box.innerHTML='';
 P.rules.forEach((r,i)=>{const el=document.createElement('div');el.className='rule'+(i===sel?' sel':'');
  let h='<div class="rule-h"><b>Rule '+(i+1)+'</b><span><button class="ic" data-a="up" title="Move up" aria-label="Move rule up">↑</button> <button class="ic" data-a="down" title="Move down" aria-label="Move rule down">↓</button> <button class="ic" data-a="del" title="Remove rule" aria-label="Remove rule">×</button></span></div>';
  r.conds.forEach((c,j)=>{const d=F[c.f];let op,val;
   if(d.kind==='flag'){op='<select data-c="'+j+'" data-k="v"><option value="1"'+(c.v?' selected':'')+'>is true</option><option value="0"'+(!c.v?' selected':'')+'>is not</option></select>';val='<span></span>'}
   else{op='<select data-c="'+j+'" data-k="op">'+Object.keys(OPS).map(o=>'<option value="'+o+'"'+(o===c.op?' selected':'')+'>'+OPS[o]+'</option>').join('')+'</select>';
    val=d.kind==='signal'?'<div class="vbox"><input type="number" min="0" max="1" step="0.05" data-c="'+j+'" data-k="v" value="'+c.v+'"></div>':'<div class="vbox"><input type="number" min="0" max="'+d.max+'" step="1" data-c="'+j+'" data-k="v" value="'+c.v+'"></div>'}
   h+='<div class="cond"><select data-c="'+j+'" data-k="f">'+fieldOptions(c.f)+'</select>'+op+val+'<button class="ic" data-a="delc" data-c="'+j+'" aria-label="Remove condition">×</button><div class="meaning">'+d.hint+'</div></div>'});
  h+='<div class="join"><button data-a="addc">Add a condition</button>'+(r.conds.length>1?'<span>Match</span><button data-a="and" class="'+(r.join==='and'?'on':'')+'">all of them</button><button data-a="or" class="'+(r.join==='or'?'on':'')+'">any of them</button>':'')+'</div>';
  h+='<div class="verdicts">'+Object.keys(V).map(v=>'<button data-a="then" data-v="'+v+'" class="'+(r.then===v?'on':'')+'">'+V[v][0]+'<small>'+V[v][1]+'</small></button>').join('')+'</div>';
  h+='<label class="f">Why — shown with every decision this rule makes</label><input data-k="why" value="'+(r.why||'').replace(/"/g,'&quot;')+'" maxlength="300" placeholder="In plain words, why this rule exists">';
  el.innerHTML=h;
  el.addEventListener('focusin',()=>{if(sel!==i){sel=i;document.querySelectorAll('.rule').forEach((x,k)=>x.classList.toggle('sel',k===i));update(false)}});
  el.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;const a=b.dataset.a;sel=i;
   if(a==='up'&&i>0){[P.rules[i-1],P.rules[i]]=[P.rules[i],P.rules[i-1]];sel=i-1}
   else if(a==='down'&&i<P.rules.length-1){[P.rules[i+1],P.rules[i]]=[P.rules[i],P.rules[i+1]];sel=i+1}
   else if(a==='del'){P.rules.splice(i,1);if(!P.rules.length)P.rules.push({join:'and',conds:[{f:'loop',op:'>=',v:0.6}],then:'challenge',why:''});sel=Math.max(0,i-1)}
   else if(a==='addc'){r.conds.push({f:'burst',op:'>=',v:0.8})}
   else if(a==='delc'){if(r.conds.length>1)r.conds.splice(+b.dataset.c,1)}
   else if(a==='and'||a==='or'){r.join=a}
   else if(a==='then'){r.then=b.dataset.v}
   else return;renderRules();update(true)});
  el.addEventListener('input',e=>{const t=e.target;if(t.dataset.k==='why'){r.why=t.value;update(true);return}
   const j=t.dataset.c;if(j===undefined)return;const c=r.conds[+j];
   if(t.dataset.k==='f'){c.f=t.value;const d=F[c.f];c.v=d.kind==='flag'?true:(d.kind==='signal'?0.6:Math.min(3,d.max));c.op='>=';renderRules()}
   else if(t.dataset.k==='op'){c.op=t.value}
   else if(t.dataset.k==='v'){c.v=F[c.f].kind==='flag'?t.value==='1':Number(t.value)}
   update(true)});
  box.appendChild(el)})}
// bench
const BENCH=['loop','burst','exposure','score','novelty','loop_count','tool_count','turns'];
let B={loop:0.1,burst:0.2,exposure:0.3,score:0.3,novelty:0.4,loop_count:1,tool_count:2,turns:4,size:0.3,ask:0.3,depth:0.2,tools:0.2,grind:0.2,burst_count:3,grind_count:40,max_tokens:1000,chars:4000};
function benchFields(){const used=new Set(BENCH);P.rules.forEach(r=>r.conds.forEach(c=>{if(F[c.f].kind!=='flag')used.add(c.f)}));return Array.from(used)}
function renderBench(){$('#bench').innerHTML=benchFields().map(f=>{const d=F[f],mx=d.kind==='signal'?1:d.max,st=d.kind==='signal'?0.01:1;
 return '<label for="b_'+f+'">'+d.name+'<b id="bv_'+f+'">'+fmtv(f,B[f]||0)+'</b></label><input type="range" id="b_'+f+'" data-f="'+f+'" min="0" max="'+mx+'" step="'+st+'" value="'+(B[f]||0)+'">'}).join('');
 document.querySelectorAll('#bench input').forEach(i=>i.oninput=()=>{B[i.dataset.f]=Number(i.value);$('#bv_'+i.dataset.f).textContent=fmtv(i.dataset.f,B[i.dataset.f]);evaluate()})}
$('#b_unattended').onchange=evaluate;$('#b_deterministic').onchange=evaluate;
function holds(c){const d=F[c.f];if(d.kind==='flag'){const x=$('#b_'+c.f).checked;return c.v?x:!x}
 const x=B[c.f]||0,v=Number(c.v);return c.op==='>='?x>=v:c.op==='>'?x>v:c.op==='<='?x<=v:c.op==='<'?x<v:x===v}
function evaluate(){let hit=-1;for(let i=0;i<P.rules.length;i++){const r=P.rules[i];const ok=r.join==='and'?r.conds.every(holds):r.conds.some(holds);if(ok){hit=i;break}}
 const v=hit>=0?P.rules[hit].then:$('#def').value;
 $('#outcome').innerHTML='<span class="then-'+v+'" style="color:'+({allow:'var(--live)',downgrade:'#9fc6ff',challenge:'var(--warn)',block:'var(--stop)'}[v])+'">'+V[v][0]+'</span>'+
  '<small>'+(hit>=0?'Rule '+(hit+1)+' decided it'+(P.rules[hit].why?': '+P.rules[hit].why.replace(/[<>]/g,''):'.'):'No rule matched, so the default decided.')+'</small>'}
// validation
let vt=null;
function update(changed){$('#sentence').innerHTML=ruleSentence(P.rules[sel]);const m=manifest();$('#json').textContent=JSON.stringify(m,null,2);renderBenchIfNeeded();evaluate();
 if(changed!==false){clearTimeout(vt);vt=setTimeout(validate,450)}}
let lastBench='';function renderBenchIfNeeded(){const k=benchFields().join(',');if(k!==lastBench){lastBench=k;renderBench()}}
async function validate(){const m=manifest();
 const local=!m.name?'Give the pack a name.':!m.author?'Add your name or company as the author.':m.rules.some(r=>!r.why)?'Every rule needs a why — it is shown with every decision.':null;
 if(local){$('#vdot').className='dot err';$('#vtext').textContent=local;$('#pub').disabled=true;return}
 try{const r=await fetch('/x/packs/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pack:m})});const d=await r.json();
  const ok=r.ok&&d.ok!==false&&!d.error;$('#vdot').className='dot '+(ok?'ok':'err');$('#vtext').textContent=ok?'Ready to publish. The engine has checked every rule.':(d.detail||d.error||'The engine could not read this pack.');$('#pub').disabled=!ok}
 catch(e){$('#vdot').className='dot err';$('#vtext').textContent='Could not reach sebbi.pro to check the pack.';$('#pub').disabled=true}}
$('#pub').onclick=async()=>{const b=$('#pub');b.disabled=true;const pm=$('#pmsg');pm.textContent='Publishing…';pm.className='msg';
 try{const r=await fetch('/x/packs/publish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pack:manifest()})});const d=await r.json();
  if(!r.ok||d.ok===false){pm.textContent=d.detail||d.error||'Could not publish.';pm.className='msg err';b.disabled=false;return}
  const id=d.pack_id||d.id||(d.pack&&d.pack.id)||'';
  pm.innerHTML='Published and sealed'+(d.block_index?' in block '+d.block_index:'')+'. '+(id?'<a href="https://sebbi.pro/x/packs/get?id='+encodeURIComponent(id)+'">See your pack</a> · ':'')+'<a href="https://sebbi.pro/packs.html">Open the library</a>';pm.className='msg ok'}
 catch(e){pm.textContent='Could not reach sebbi.pro.';pm.className='msg err';b.disabled=false}};
function load(t){P=JSON.parse(JSON.stringify(T[t]));sel=0;$('#pn').value=P.name;$('#ps').value=P.summary;$('#def').value=P.def;renderRules();update(true)}
document.querySelectorAll('.tpl button').forEach(b=>b.onclick=()=>load(b.dataset.t));
['#pn','#pa','#pv','#pver','#ps','#def'].forEach(s=>$(s).addEventListener('input',()=>update(true)));
$('#addrule').onclick=()=>{P.rules.push({join:'and',conds:[{f:'exposure',op:'>=',v:0.7}],then:'challenge',why:''});sel=P.rules.length-1;renderRules();update(true);document.querySelectorAll('.rule')[sel].scrollIntoView({behavior:'smooth',block:'center'})};
load('runaway');
})();
</script></body></html>"""

```


## `modules/consistency.py`

461 lines, 19146 bytes

```python
#!/usr/bin/env python3
"""
modules/consistency.py  -  proving we have never run two histories
==================================================================

THE ATTACK NOTHING ELSE HERE STOPS
----------------------------------
Mutual witnessing means several parties hold hashes of our chain. What
none of them can currently check is whether they are all holding hashes of
the SAME chain.

Nothing in the design so far stops an operator running two histories in
parallel. Serve chain A to one witness, chain B to an auditor. Both get a
valid-looking tip. Both anchor it. Both verify perfectly against the copy
they were given. Neither can tell, because there is no way to ask the
question that would expose it:

    is the tip you are holding actually an ancestor of my current head?

That is the split-view attack. Witnessing does not stop it. Anchoring does
not stop it - two forks can both be anchored. It is the last place an
operator can lie, and it is the one nobody in compliance has closed,
because the defence came out of Certificate Transparency and has not
crossed over.

WHAT THIS DOES
--------------
Builds an ordered Merkle tree over the audit chain and answers one
question for anybody, forever, without our cooperation:

    GET /x/consistency/ancestor?tip=<any tip we ever served>

If that tip is on our chain, we return its position and a proof, against
our current head, that it is still there and still in the same place. If
it is not on our chain, we say so - and the party holding it knows they
were served a history we no longer stand behind.

Every witness can check every tip they have ever held, automatically, on a
timer, for as long as they keep the tips. Which means we cannot show two
faces to the network: the moment any holder of any old tip checks it, a
fork stops being hidden and becomes provable arithmetic.

APPEND-ONLY, PROVED RATHER THAN ASSERTED
----------------------------------------
    GET /x/consistency/proof?first=21&second=48

Proves the log at size 21 is a PREFIX of the log at size 48. Not that both
exist - that the second was reached from the first by appending only, with
nothing inserted, removed or reordered in between. That is the actual
meaning of "append-only", and until now it has been a claim rather than
something a stranger could check.

WHY THE MATHS IS BORROWED, NOT INVENTED
---------------------------------------
The tree here follows RFC 6962 - Certificate Transparency - deliberately,
including its leaf and node prefixes and its split at the largest power of
two. Anyone who has implemented a CT verifier can point it at this and it
will work. Inventing a bespoke tree would mean nobody could check us
without writing new code first, which is the opposite of the point.

Note this tree is ORDERED, unlike the sorted tree in modules/complete.py.
The two answer different questions. Sorted proves what is absent. Ordered
proves nothing was reordered. They are not interchangeable and both are
needed.

HONEST LIMITS
-------------
  - This proves our published chain is internally append-only and that a
    given tip belongs to it. It says nothing about whether an entry should
    have been written in the first place.
  - A fork is only DETECTED if someone actually checks a tip they were
    given. The network has to do its half. That is why the route is public
    and needs no account - so checking costs nothing and can be automated.
  - If nobody ever holds an old tip of ours, there is nothing to check us
    against. Detection scales with how many witnesses keep history, which
    is another reason breadth matters more than depth.
  - Recomputation is O(n) hashing over the chain. Cached per size. On a
    very large log a checkpoint-based approach would be better; that is
    written down rather than hidden.

    GET  /x/consistency/root         current size and root      (public)
    GET  /x/consistency/ancestor     is this tip on our chain    (public)
    GET  /x/consistency/proof        prefix proof between sizes  (public)
    GET  /x/consistency/spec         the exact hashing rules     (public)
    POST /x/consistency/verify       check a proof we gave out   (public)
    POST /x/consistency/checkpoint   seal the current root       (keyed)
"""

import hashlib
import re
import threading
import time
from datetime import datetime, timezone

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# All the read routes are open. A consistency check you need an account to
# run is worthless - the party most likely to want it is the one who has
# stopped trusting us.
PUBLIC = {("GET", "root"), ("GET", "ancestor"), ("GET", "proof"),
          ("GET", "spec"), ("POST", "verify")}

# RFC 6962 domain separation. Leaf and internal hashes must never be
# confusable or an internal node can be passed off as a leaf.
LEAF_BYTE = b"\x00"
NODE_BYTE = b"\x01"

MAX_LEAVES = 500000

_ready = False
_cache = {"size": -1, "leaves": [], "root": None, "built": 0}
_cache_lock = threading.Lock()


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS consistency_checkpoint("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,tree_size INTEGER,"
                  "root TEXT,taken REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cons_size "
                  "ON consistency_checkpoint(tree_size)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ----------------------------------------------------------------------
# RFC 6962 tree
# ----------------------------------------------------------------------

def _leaf(value):
    return hashlib.sha256(LEAF_BYTE + value.encode("utf-8")).digest()


def _node(left, right):
    return hashlib.sha256(NODE_BYTE + left + right).digest()


def _split(n):
    """Largest power of two strictly less than n. RFC 6962 splits here."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def _mth(leaves):
    """Merkle Tree Hash over an ordered slice. Returns raw bytes."""
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return _leaf(leaves[0])
    k = _split(n)
    return _node(_mth(leaves[:k]), _mth(leaves[k:]))


def _inclusion(index, leaves):
    """Audit path for leaf at index within this slice. Raw bytes list."""
    n = len(leaves)
    if n <= 1:
        return []
    k = _split(n)
    if index < k:
        return _inclusion(index, leaves[:k]) + [_mth(leaves[k:])]
    return _inclusion(index - k, leaves[k:]) + [_mth(leaves[:k])]


def _subproof(m, leaves, is_root):
    n = len(leaves)
    if m == n:
        return [] if is_root else [_mth(leaves)]
    k = _split(n)
    if m <= k:
        return _subproof(m, leaves[:k], is_root) + [_mth(leaves[k:])]
    return _subproof(m - k, leaves[k:], False) + [_mth(leaves[:k])]


def _consistency(m, leaves):
    """Proof that the tree of the first m leaves is a prefix of this one."""
    if m <= 0 or m > len(leaves):
        return None
    if m == len(leaves):
        return []
    return _subproof(m, leaves, True)


def _hexed(nodes):
    return [n.hex() for n in nodes]


# ----------------------------------------------------------------------
# reading the chain
# ----------------------------------------------------------------------

def _load(ctx):
    """Every audit hash in order, cached until the chain grows.

    Order is the point here - this is not the sorted tree from
    modules/complete.py and the two must never be confused.
    """
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT COUNT(*) FROM audit_log").fetchone()
    size = int(row[0]) if row else 0

    with _cache_lock:
        if _cache["size"] == size and _cache["root"] is not None:
            return _cache["leaves"], _cache["root"], size, None

    if size > MAX_LEAVES:
        return None, None, size, "chain holds %d entries, above the %d cap for live recomputation" % (size, MAX_LEAVES)

    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT audit_hash FROM audit_log ORDER BY id ASC").fetchall()
    leaves = [str(r[0]) for r in rows if r[0]]
    root = _mth(leaves)

    with _cache_lock:
        _cache["size"] = len(leaves)
        _cache["leaves"] = leaves
        _cache["root"] = root
        _cache["built"] = time.time()

    return leaves, root, len(leaves), None


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _root(ctx):
    leaves, root, size, why = _load(ctx)
    if why:
        return {"error": "too_large", "message": why, "tree_size": size}, 503
    return {"tree_size": size, "root": root.hex(), "consistency_version": VERSION,
            "algorithm": "RFC 6962 Merkle Tree Hash over audit hashes in write order",
            "note": "Record this alongside any tip you hold. Later you can ask us to prove the "
                    "log you saw is a prefix of the log we serve today.",
            "check": "/x/consistency/proof?first=<your size>&second=%d" % size,
            "spec": "/x/consistency/spec"}, 200


def _ancestor(ctx, data):
    tip = str(data.get("tip", "")).strip().lower()
    if not tip:
        return {"error": "tip_required",
                "message": "Any tip we ever served you. We will prove whether it is still on "
                           "the chain we serve now."}, 400

    leaves, root, size, why = _load(ctx)
    if why:
        return {"error": "too_large", "message": why, "tree_size": size}, 503

    try:
        index = leaves.index(tip)
    except ValueError:
        return {"on_chain": False, "tip": tip, "tree_size": size, "root": root.hex(),
                "what_this_means": "This tip is not in the chain we serve. Either it was never "
                                   "ours, or it belongs to a history we are no longer publishing. "
                                   "If we gave you this tip, that is a fork and you now have "
                                   "evidence of it.",
                "keep_this": "This response, the tip, and whatever we originally sent you with "
                             "it. Together they are the record of the discrepancy.",
                "consistency_version": VERSION}, 409

    path = _inclusion(index, leaves)
    return {"on_chain": True, "tip": tip, "leaf_index": index, "height": index + 1,
            "tree_size": size, "root": root.hex(),
            "inclusion_proof": _hexed(path),
            "consistency_version": VERSION,
            "what_this_proves": "This tip sits at position %d of a chain of %d, and the current "
                                "root recomputes from it. It has not been moved, removed or "
                                "reordered since we gave it to you." % (index, size),
            "verify_yourself": "/x/consistency/spec has the rules. Recompute upward from the "
                               "leaf and compare with the root above.",
            "prefix_proof": "/x/consistency/proof?first=%d&second=%d" % (index + 1, size)}, 200


def _proof(ctx, data):
    try:
        first = int(data.get("first", 0))
        second = int(data.get("second", 0) or 0)
    except (TypeError, ValueError):
        return {"error": "bad_sizes", "message": "first and second are tree sizes, as integers"}, 400

    leaves, root, size, why = _load(ctx)
    if why:
        return {"error": "too_large", "message": why, "tree_size": size}, 503
    if not second:
        second = size
    if first < 1 or first > second or second > size:
        return {"error": "bad_range",
                "message": "Need 1 <= first <= second <= %d" % size,
                "tree_size": size}, 400

    older = leaves[:first]
    newer = leaves[:second]
    proof = _consistency(first, newer)
    if proof is None:
        return {"error": "no_proof", "message": "could not build a proof for that range"}, 400

    return {"first": first, "second": second,
            "first_root": _mth(older).hex(),
            "second_root": _mth(newer).hex(),
            "consistency_proof": _hexed(proof),
            "consistency_version": VERSION,
            "what_this_proves": "The log at size %d is a prefix of the log at size %d. Nothing "
                                "was inserted, removed or reordered between them - only "
                                "appended. That is what append-only actually means, and this is "
                                "it demonstrated rather than asserted." % (first, second),
            "algorithm": "RFC 6962 section 2.1.2",
            "spec": "/x/consistency/spec"}, 200


def _verify(data):
    """Recompute an inclusion proof. Convenience only - anyone relying on
    us to check our own proof has not checked anything."""
    leaf_value = str(data.get("leaf", data.get("tip", ""))).strip().lower()
    index = data.get("index", data.get("leaf_index"))
    size = data.get("tree_size")
    root = str(data.get("root", "")).strip().lower()
    proof = data.get("inclusion_proof", data.get("proof"))

    if not leaf_value or not HEX64.match(root) or not isinstance(proof, list):
        return {"error": "leaf_root_and_proof_required"}, 400
    try:
        index = int(index)
        size = int(size)
    except (TypeError, ValueError):
        return {"error": "index_and_tree_size_required"}, 400
    if index < 0 or size <= 0 or index >= size:
        return {"error": "index_out_of_range"}, 400

    current = _leaf(leaf_value)
    node_index, last_index = index, size - 1
    try:
        for step in proof:
            sibling = bytes.fromhex(str(step))
            if node_index % 2 == 1 or node_index == last_index:
                if node_index % 2 == 1:
                    current = _node(sibling, current)
                else:
                    current = _node(sibling, current)
                while node_index % 2 == 0 and node_index != 0:
                    node_index //= 2
                    last_index //= 2
            else:
                current = _node(current, sibling)
            node_index //= 2
            last_index //= 2
    except Exception as exc:
        return {"error": "bad_proof", "message": str(exc)[:200]}, 400

    return {"valid": current.hex() == root,
            "computed_root": current.hex(), "given_root": root,
            "note": "Recomputed from the leaf upward using RFC 6962 audit path rules."}, 200


def _checkpoint(ctx, api_key):
    """Seal the current size and root into the chain itself.

    A checkpoint is our own signature on 'this is what the log looked like
    at this moment'. Once anchored, publishing a different history for that
    size contradicts something we already sealed and externally timestamped.
    """
    leaves, root, size, why = _load(ctx)
    if why:
        return {"error": "too_large", "message": why, "tree_size": size}, 503

    now = time.time()
    root_hex = root.hex()
    ev = {"user_id": "cons:%d" % size, "action": "consistency_checkpoint", "amount": 0,
          "country": "UK", "device_id": "consistency", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CHECKPOINT_SEALED", "score": 0, "consistency_version": VERSION,
           "tree_size": size, "root": root_hex,
           "detail": "size=%d;root=%s" % (size, root_hex)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO consistency_checkpoint(api_key,tree_size,root,taken,"
                            "audit_hash,block_index) VALUES(?,?,?,?,?,?)",
                            (api_key, size, root_hex, now, audit_hash, block_index))
        ctx["conn"].commit()

    return {"tree_size": size, "root": root_hex, "taken_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "what_this_does": "Commits our own view of the log at this size, inside the log, "
                              "where it gets anchored with everything else. Serving a different "
                              "history for this size now contradicts a sealed, timestamped "
                              "record of our own making.",
            "note": "The checkpoint itself becomes an entry, so the next size is larger. That is "
                    "expected and does not affect the proof for this one."}, 200


def _spec():
    return {
        "consistency_version": VERSION,
        "based_on": "RFC 6962 (Certificate Transparency), deliberately unmodified so existing "
                    "verifiers work against this without new code",
        "leaves": "the audit_hash of every chain entry, in write order (id ascending), as "
                  "lowercase hex strings encoded UTF-8",
        "empty_root": hashlib.sha256(b"").hexdigest(),
        "leaf_hash": "sha256(0x00 || leaf_value_utf8)",
        "node_hash": "sha256(0x01 || left || right)",
        "split": "for n > 1 leaves, split at k = the largest power of two strictly less than n",
        "inclusion": "RFC 6962 section 2.1.1 audit path",
        "consistency": "RFC 6962 section 2.1.2 - proves the tree at size m is a prefix of the "
                       "tree at size n",
        "ordered_not_sorted": "This tree is in write order. /x/complete uses a SORTED tree, "
                              "which answers a different question (absence). Do not confuse the "
                              "two - the roots will not match and are not meant to.",
        "how_to_catch_us": "Keep every tip and root we ever hand you. Ask /x/consistency/ancestor "
                           "about the old ones on a timer. If one ever comes back on_chain false, "
                           "or a prefix proof fails to verify, we have served two histories and "
                           "you can prove it without our help.",
        "why_published": "Because a log nobody can check is a log you are being asked to trust.",
    }, 200


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec()
        if action == "root":
            return _root(ctx)
        if action == "ancestor":
            return _ancestor(ctx, data)
        if action == "proof":
            return _proof(ctx, data)

    if method == "POST":
        if action == "verify":
            return _verify(data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "checkpoint":
            return _checkpoint(ctx, api_key)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "root", "ancestor", "proof"],
            "POST": ["verify", "checkpoint"]}, 404

```
