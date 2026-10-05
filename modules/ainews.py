"""
modules/ainews.py  v1.0.0  -  a live AI news ticker along the bottom of sebbi.pro

    Arm:   https://sebbi.pro/x/arm/status
    Feed:  https://sebbi.pro/x/ainews/feed

Every ten minutes the server reads the AI sections of major technology
publishers, keeps only stories that are about AI, and holds the newest few
dozen. Every page on the site then gets a slim ticker along the bottom:
headline and publisher, scrolling slowly, pausing when touched, each linking
to the publisher's own article. Headlines and links only - nothing is copied.

The page is rewritten as it is served, like the brand module; no page file
is edited. The homelink bubbles are lifted above the bar so nothing overlaps.
Visitors can close it; it stays closed for that visit. Operator screens,
full-screen experiences and legal pages are left alone.

Nothing shows until there is news to show, so a fresh deploy or a network
problem never puts an empty bar on the site.
"""

import html
import json
import os
import re
import sys
import threading
import time
import urllib.request
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "feed"), ("GET", "spec")}

FEEDS = [
    ("TechCrunch", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("MIT Technology Review", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("VentureBeat", "https://venturebeat.com/category/ai/feed/"),
    ("The Guardian", "https://www.theguardian.com/technology/artificialintelligence/rss"),
    ("Ars Technica", "https://arstechnica.com/ai/feed/"),
    ("Wired", "https://www.wired.com/feed/tag/ai/latest/rss"),
    ("BBC News", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
]
REFRESH = 600
MAX_AGE = 3 * 86400
MAX_ITEMS = 24

AI_RE = re.compile(r"(\bAI\b|\bA\.I\.|artificial intelligence|\bAGI\b|OpenAI|Anthropic|ChatGPT|\bGPT|Claude|Gemini|"
                   r"DeepMind|Mistral|\bLlama\b|\bLLMs?\b|large language model|machine learning|chatbot|Copilot|"
                   r"deepfake|neural net|generative|\bagentic\b|AI agent|xAI|Grok|Perplexity|Hugging Face|"
                   r"Nvidia|data cent(?:er|re)s? for AI|EU AI Act|superintelligence)", re.I)

SKIP = ("/admin", "/console", "/peers", "/pack", "/lineage-desk", "/bind-desk", "/cinema", "/game", "/room",
        "/create", "/v/", "/terms", "/data-protection", "/risk-policy", "/human-oversight", "/dossier/data",
        "/mcp", "/x/", "/api/", "/c/", "/p/")

_items = []
_state = {"installed": False, "thread": False, "last_run": None, "last_error": None, "sources_ok": 0, "served": 0}
_lock = threading.Lock()


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "Handler"):
        m = sys.modules.get("server")
    return m


def _text(el, *names):
    for n in names:
        x = el.find(n)
        if x is not None:
            if x.text and x.text.strip():
                return x.text.strip()
            if x.get("href"):
                return x.get("href").strip()
    return ""


def _when(s):
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).timestamp()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _parse(source, raw):
    out = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return out
    atom = "{http://www.w3.org/2005/Atom}"
    entries = root.findall(".//item") or root.findall(".//%sentry" % atom)
    for e in entries[:60]:
        title = _text(e, "title", atom + "title")
        link = _text(e, "link", atom + "link")
        if not link:
            for l in e.findall(atom + "link"):
                if l.get("rel", "alternate") == "alternate" and l.get("href"):
                    link = l.get("href")
                    break
        when = _when(_text(e, "pubDate", atom + "published", atom + "updated",
                           "{http://purl.org/dc/elements/1.1/}date"))
        title = html.unescape(re.sub(r"<[^>]+>", "", title or "")).strip()
        if not title or not link.startswith("http"):
            continue
        if not AI_RE.search(title):
            continue
        out.append({"title": title[:180], "link": link[:500], "source": source, "ts": when or 0})
    return out


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; sebbi.pro AI news ticker; +https://sebbi.pro)",
                                               "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.read(2 * 1024 * 1024)


def refresh():
    got, ok = [], 0
    local = os.environ.get("AINEWS_FEED_DIR")  # test copies read feeds from files; the live site never sets this
    for i, (source, url) in enumerate(FEEDS):
        try:
            if local:
                path = os.path.join(local, "feed_%d.xml" % i)
                if not os.path.exists(path):
                    continue
                with open(path, "rb") as f:
                    raw = f.read()
            else:
                raw = _fetch(url)
            got.extend(_parse(source, raw))
            ok += 1
        except Exception as e:
            _state["last_error"] = "%s: %s" % (source, str(e)[:120])
    now = time.time()
    seen, fresh = set(), []
    for it in sorted(got, key=lambda x: x["ts"], reverse=True):
        key = re.sub(r"\W+", "", it["title"].lower())[:80]
        if key in seen or it["link"] in seen:
            continue
        if it["ts"] and now - it["ts"] > MAX_AGE:
            continue
        seen.add(key)
        seen.add(it["link"])
        fresh.append(it)
    # keep the mix varied: no more than five from any one publisher
    per, picked = {}, []
    for it in fresh:
        if per.get(it["source"], 0) >= 5:
            continue
        per[it["source"]] = per.get(it["source"], 0) + 1
        picked.append(it)
        if len(picked) >= MAX_ITEMS:
            break
    with _lock:
        if picked:
            _items[:] = picked
        _state["last_run"] = now
        _state["sources_ok"] = ok
    return len(picked)


def _loop():
    while True:
        try:
            refresh()
        except Exception as e:
            _state["last_error"] = str(e)[:160]
        time.sleep(REFRESH)


def _ago(ts):
    if not ts:
        return ""
    m = int((time.time() - ts) / 60)
    if m < 60:
        return "%dm" % max(1, m)
    if m < 1440:
        return "%dh" % (m // 60)
    return "%dd" % (m // 1440)


def _bar():
    with _lock:
        items = list(_items)
    if len(items) < 3:
        return b""
    li = "".join('<a href="%s" target="_blank" rel="noopener"><i>%s</i>%s<em>%s</em></a>' % (
        html.escape(it["link"], quote=True), html.escape(it["source"]), html.escape(it["title"]),
        _ago(it["ts"])) for it in items)
    secs = max(60, len(items) * 7)
    return (BAR.replace("__ITEMS__", li).replace("__SECS__", str(secs))).encode("utf-8")


BAR = r"""<!--sebbi-ainews--><div id="sbn" role="region" aria-label="Live AI news">
<style>
html.sbn-on body{padding-bottom:calc(32px + env(safe-area-inset-bottom,0px))}
html.sbn-on #sebbi-homelink,html.sbn-on #sebbi-bubble,html.sbn-on #sebbi-tools,html.sbn-on #sebbi-toolbubble,
html.sbn-on #sebbi-studio,html.sbn-on #sebbi-studiobubble,html.sbn-on #sebbi-plug,html.sbn-on #sebbi-plugbubble{margin-bottom:34px}
#sbn{position:fixed;left:0;right:0;bottom:0;z-index:2147482990;height:calc(32px + env(safe-area-inset-bottom,0px));padding-bottom:env(safe-area-inset-bottom,0px);
background:rgba(8,12,24,.94);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-top:1px solid rgba(201,168,76,.28);
display:none;align-items:center;font:400 12.5px/1 'IBM Plex Sans',system-ui,sans-serif;color:#efe6cc}
html.sbn-on #sbn{display:flex}
#sbn .lab{flex:none;display:flex;align-items:center;gap:7px;padding:0 12px 0 14px;height:100%;color:#c9a84c;font-weight:500;letter-spacing:.02em;
border-right:1px solid rgba(201,168,76,.22);background:linear-gradient(90deg,rgba(201,168,76,.10),transparent)}
#sbn .dot{width:6px;height:6px;border-radius:50%;background:#e8b04b;box-shadow:0 0 0 0 rgba(232,176,75,.6);animation:sbnp 2.4s infinite}
@keyframes sbnp{0%{box-shadow:0 0 0 0 rgba(232,176,75,.55)}70%{box-shadow:0 0 0 7px rgba(232,176,75,0)}100%{box-shadow:0 0 0 0 rgba(232,176,75,0)}}
#sbn .win{flex:1;overflow:hidden;height:100%;-webkit-mask:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent);mask:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent)}
#sbn .run{display:flex;width:max-content;height:100%;align-items:center;animation:sbnr __SECS__s linear infinite}
#sbn .win:hover .run,#sbn .win:focus-within .run{animation-play-state:paused}
@keyframes sbnr{to{transform:translateX(-50%)}}
#sbn .run a{display:inline-flex;align-items:baseline;gap:8px;color:#efe6cc;text-decoration:none;padding:0 22px;white-space:nowrap;border-right:1px solid rgba(239,230,204,.10)}
#sbn .run a:hover,#sbn .run a:focus-visible{color:#fff;outline:none}
#sbn .run a:focus-visible{text-decoration:underline}
#sbn .run i{font-style:normal;color:#c9a84c;font-size:11.5px}
#sbn .run em{font-style:normal;color:rgba(239,230,204,.42);font-size:11px}
#sbn .x{flex:none;width:32px;height:100%;border:0;border-left:1px solid rgba(201,168,76,.18);background:transparent;color:rgba(239,230,204,.55);font-size:15px;cursor:pointer}
#sbn .x:hover{color:#fff}
@media(prefers-reduced-motion:reduce){#sbn .run{animation:none}#sbn .win{overflow-x:auto}}
@media(max-width:520px){#sbn .lab span{display:none}#sbn .lab{padding:0 10px}}
</style>
<div class="lab"><b class="dot" aria-hidden="true"></b><span>AI news</span></div>
<div class="win"><div class="run">__ITEMS____ITEMS__</div></div>
<button class="x" type="button" aria-label="Hide AI news">&times;</button>
<script>(function(){var d=document.documentElement,b=document.getElementById('sbn');var off=false;try{off=sessionStorage.getItem('sebbi.news.off')==='1'}catch(e){}
if(!off)d.classList.add('sbn-on');b.querySelector('.x').onclick=function(){d.classList.remove('sbn-on');try{sessionStorage.setItem('sebbi.news.off','1')}catch(e){}};
var r=b.querySelector('.run');var h=r.innerHTML;r.querySelectorAll('a').forEach(function(a,i){if(i>=r.children.length/2){a.setAttribute('tabindex','-1');a.setAttribute('aria-hidden','true')}});})();</script>
</div>"""


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
        elif len(self.buf) > 8 * 1024 * 1024:
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

    def finish(self, bar):
        if self.mode == "pass" or not self.buf:
            return
        raw = bytes(self.buf)
        self.buf = bytearray()
        end = raw.find(b"\r\n\r\n")
        if not bar or self.mode != "html" or end < 0 or not raw.startswith(b"HTTP/1.") or b" 200 " not in raw[:20]:
            self.real.write(raw)
            return
        head, body = raw[:end], raw[end + 4:]
        at = body.rfind(b"</body>")
        if at < 0 or b"<!--sebbi-ainews-->" in body:
            self.real.write(raw)
            return
        body = body[:at] + bar + body[at:]
        lines = [l for l in head.split(b"\r\n") if not l.lower().startswith(b"content-length:")]
        lines.append(b"Content-Length: " + str(len(body)).encode())
        self.real.write(b"\r\n".join(lines) + b"\r\n\r\n" + body)
        _state["served"] += 1
        try:
            self.real.flush()
        except Exception:
            pass


def _install():
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_ainews_patched", False):
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
                want = getattr(self, "command", "") == "GET" and not path.startswith(SKIP)
                out.finish(_bar() if want else b"")
            except Exception as e:
                _state["last_error"] = str(e)[:200]
                try:
                    if out.buf:
                        real.write(bytes(out.buf))
                except Exception:
                    pass

    H.handle_one_request = handle_one_request
    H._ainews_patched = True
    return True


def arm():
    with _lock:
        start = not _state["thread"]
        _state["thread"] = True
    _state["installed"] = _install()
    if start:
        threading.Thread(target=_loop, name="ainews", daemon=True).start()


def handle(method, action, data, api_key, ctx):
    try:
        arm()
    except Exception as e:
        _state["last_error"] = "arm: %s" % e
    with _lock:
        items = list(_items)
    if action == "feed":
        return {"stories": [dict(it, age=_ago(it["ts"]),
                                 published_utc=datetime.fromtimestamp(it["ts"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if it["ts"] else None)
                            for it in items],
                "count": len(items), "refreshes_every_seconds": REFRESH}, 200
    if action == "spec":
        return {"module": "ainews", "version": VERSION, "sources": [s for s, _u in FEEDS],
                "what": "A live AI-only news ticker along the bottom of every page. Headlines and links to the publisher.",
                "refreshes_every_seconds": REFRESH, "left_alone": list(SKIP)}, 200
    return {"module": "ainews", "version": VERSION, "armed": _state["installed"], "stories": len(items),
            "sources_reached": "%d of %d" % (_state["sources_ok"], len(FEEDS)),
            "last_refresh_utc": datetime.fromtimestamp(_state["last_run"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if _state["last_run"] else None,
            "pages_served_with_ticker": _state["served"], "last_error": _state["last_error"]}, 200
