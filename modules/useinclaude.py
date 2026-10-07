"""
modules/useinclaude.py  v1.0.0  -  "use these tools right inside Claude" banner

Adds one prominent, accurate banner to the top of the /connect page making it
unmistakable that every sebbi.pro tool runs inside Claude (and other AI
assistants). It is injected as the page is served - connect.py is NOT edited.

Wording is deliberately safe for a compliance product:
  - TRUE:  "runs inside Claude" (the connector works - proven live)
  - TRUE:  "published on the official Model Context Protocol registry"
  - NOT claimed: any Anthropic endorsement, approval or directory listing.

Injected only on:  https://sebbi.pro/connect
Mirrors the proven social_meta buffer pattern. Idempotent.

Arm with everything:  https://sebbi.pro/x/arm/status
See it:               https://sebbi.pro/connect
"""

import io
import sys

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

SITE = "https://sebbi.pro"
TARGET = "/connect"
MARK = b"id=\"use-in-claude\""
ANCHOR = b'<section class="ai"'

_state = {"patched": False, "injected": 0, "last_error": None}
_patched = False

BANNER = ("""
<section id="use-in-claude" aria-label="Use these tools inside Claude">
<style>
#use-in-claude{margin:26px 0 8px;border:1px solid var(--gold,#c9a84c);border-radius:18px;
background:linear-gradient(150deg,rgba(201,168,76,.14),rgba(13,20,38,1) 58%);padding:26px 24px;
font-family:var(--sans,'IBM Plex Sans',system-ui,sans-serif);color:var(--parch,#efe6cc)}
#use-in-claude .ey{font-family:var(--mono,'IBM Plex Mono',monospace);font-size:12px;letter-spacing:.22em;
text-transform:uppercase;color:var(--gold,#c9a84c);display:flex;align-items:center;gap:10px}
#use-in-claude .ey i{display:inline-block;width:26px;height:1px;background:var(--gold,#c9a84c)}
#use-in-claude h2{font-family:var(--serif,'Newsreader',Georgia,serif);font-weight:500;
font-size:clamp(26px,4vw,40px);line-height:1.08;color:#fff;margin:12px 0 10px}
#use-in-claude p{color:rgba(239,230,204,.72);font-size:15.5px;line-height:1.6;max-width:62ch;margin:0 0 10px}
#use-in-claude .chips{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 6px}
#use-in-claude .chips span{border:1px solid rgba(201,168,76,.3);border-radius:999px;padding:7px 13px;
font-size:13.5px;color:#fff;background:rgba(10,15,30,.5)}
#use-in-claude .add{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:18px;
border-top:1px solid rgba(201,168,76,.2);padding-top:18px}
#use-in-claude .add code{font-family:var(--mono,'IBM Plex Mono',monospace);font-size:clamp(15px,2.4vw,19px);
color:#fff;word-break:break-all}
#use-in-claude .add a{display:inline-block;background:var(--gold,#c9a84c);color:#0a0f1e;border-radius:999px;
padding:11px 20px;font-weight:600;font-size:14.5px;text-decoration:none}
#use-in-claude .add a:hover{background:var(--pale,#f0d78a)}
#use-in-claude .reg{font-size:13px;color:rgba(239,230,204,.55);margin-top:14px}
#use-in-claude .reg a{color:var(--pale,#f0d78a)}
</style>
<div class="ey"><i></i>Works inside Claude</div>
<h2>Use these tools right inside Claude.</h2>
<p>Add sebbi.pro to Claude once and every one of its tools is there in the chat. Claude can open your
account, score and seal a decision, notarise a file against Bitcoin, prove a human typed something and
pull a machine-proof report &mdash; all without you leaving the conversation. Just ask it:
&ldquo;set me up on sebbi.pro&rdquo;.</p>
<div class="chips">
 <span>Open your account</span><span>Score &amp; seal a decision</span><span>Notarise into Bitcoin</span>
 <span>Prove a human typed it</span><span>Machine-proof report</span><span>Build your own rules</span>
</div>
<div class="add">
 <code>""" + SITE + """/mcp</code>
 <a href="https://claude.ai/settings/connectors" rel="noopener">Add it to Claude &rarr;</a>
 <span style="font-size:13.5px;color:rgba(239,230,204,.6)">Settings &rarr; Connectors &rarr; Add custom connector</span>
</div>
<p class="reg">Also works in ChatGPT, Cursor, VS Code and Claude Code &mdash; see below. sebbi.pro is
published on the official <a href="https://modelcontextprotocol.io" rel="noopener">Model Context
Protocol</a> registry, so assistants can find it.</p>
</section>
""").encode("utf-8")


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "Handler"):
        m = sys.modules.get("server")
    return m


def _inject(raw):
    head, sep, body = raw.partition(b"\r\n\r\n")
    if not sep:
        return None
    lines = head.split(b"\r\n")
    if not lines or b" 200" not in lines[0]:
        return None
    lower = head.lower()
    if b"text/html" not in lower or b"content-encoding" in lower or b"chunked" in lower:
        return None
    if MARK in body:
        return None
    at = body.find(ANCHOR)
    if at < 0:
        at = body.rfind(b"</body>")
    if at < 0:
        return None
    new_body = body[:at] + BANNER + body[at:]
    out = []
    for ln in lines:
        if ln.lower().startswith(b"content-length:"):
            ln = b"Content-Length: " + str(len(new_body)).encode()
        out.append(ln)
    return b"\r\n".join(out) + b"\r\n\r\n" + new_body


def _install():
    global _patched
    if _patched:
        return True
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_useinclaude_patched", False):
        _patched = True
        return True
    orig = H.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path != TARGET:
            return orig(self)
        real = self.wfile
        buf = io.BytesIO()
        self.wfile = buf
        try:
            orig(self)
            if hasattr(self, "_headers_buffer") and self._headers_buffer:
                self.flush_headers()
        finally:
            self.wfile = real
        raw = buf.getvalue()
        try:
            changed = _inject(raw)
        except Exception as e:
            _state["last_error"] = "inject: %s" % str(e)[:160]
            changed = None
        if changed is not None:
            _state["injected"] += 1
        real.write(changed if changed is not None else raw)

    H.do_GET = do_GET
    H._useinclaude_patched = True
    _patched = True
    _state["patched"] = True
    return True


def handle(method, action, data, api_key, ctx):
    try:
        _state["patched"] = _install()
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:160]
    if action == "spec":
        return {"module": "useinclaude", "version": VERSION, "page": SITE + TARGET,
                "claim": "runs inside Claude; published on the official MCP registry (no Anthropic endorsement claimed)"}, 200
    return ({"module": "useinclaude", "version": VERSION, "armed": _state["patched"],
             "page": SITE + TARGET, "injected": _state["injected"],
             "last_error": _state["last_error"]}, 200)
