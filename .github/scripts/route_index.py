#!/usr/bin/env python3
"""
route_index.py - the developers page route index, generated from the modules.

Reads every file in modules/, pulls its version, its public routes (from
PUBLIC) and its keyed routes (from its own docstring), and writes the table
between the ROUTE-INDEX markers in developers.html.

    python3 .github/scripts/route_index.py          rewrite the table
    python3 .github/scripts/route_index.py --check  exit 1 if the table is stale

checks.yml runs --check on every push, so a new module that nobody documented
shows up as a warning instead of silently missing from the docs.
"""
import ast
import html
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MOD = os.path.join(ROOT, "modules")
PAGE = os.path.join(ROOT, "developers.html")
START, END = "<!-- ROUTE-INDEX:START -->", "<!-- ROUTE-INDEX:END -->"
HOST = "https://sebbi.pro"

# (group, plain-English purpose). Modules not listed fall back to their
# own docstring's first line, so a new module is never invisible.
ABOUT = {
    # decisions and evidence
    "demo": ("Decisions and evidence", "The Proving Ground. Run a live decision with no key, sealed into the production chain."),
    "dossier": ("Decisions and evidence", "Machine-proof report. Everything about one sealed block: decision, account, end user, IP and request, integrity and time proofs."),
    "counterfactual": ("Decisions and evidence", "What would have changed the verdict, computed by inverting the real scoring function."),
    "rulebind": ("Decisions and evidence", "Proves the ruleset version was hashed into the decision itself, without disclosing the rules."),
    "replay": ("Decisions and evidence", "Determinism as a black box: send the same inputs later and the verdict must not move."),
    "packs": ("Decisions and evidence", "Signal Packs library. Write, validate, publish and fork for free; running one is keyed."),
    "pack": ("Decisions and evidence", "Evidence pack for a period. Re-verifies every block in range and seals the pack itself."),
    "fingerprint": ("Decisions and evidence", "Fires a fixed battery at any scoring endpoint to measure whether it runs this function."),
    "savings": ("Decisions and evidence", "Cost model behind /savings, with a sealed copy of any result."),
    "tokensaver": ("Decisions and evidence", "Token saver platform side: published weights and rules, aggregate stats, receipt checks."),
    # the chain
    "walk": ("The chain", "The whole chain, genesis to tip, readable and re-verifiable by anyone."),
    "blocks": ("The chain", "Paged reads of the chain for operator tools."),
    "genesis": ("The chain", "Chain identity: which chain this is, where it started, how to check it."),
    "sebbi_engine": ("The chain", "Live chain state, verifiable."),
    "stats": ("The chain", "Live figures behind the Proving Ground charts."),
    "complete": ("The chain", "Inclusion, absence and completeness proofs against committed period roots."),
    "consistency": ("The chain", "RFC 6962 consistency proofs: the log only ever grew."),
    "ots": ("The chain", "OpenTimestamps proofs served raw, confirmed or pending, upgraded hourly."),
    "heartbeat": ("The chain", "Public random beacons sealed into the chain: a floor and a ceiling on every block's time."),
    "archive": ("The chain", "One self-proving archive file a day: every public block with its source text and a verifier."),
    "custody": ("The chain", "Where independent copies of the archive are held, proven and counted."),
    "held": ("The chain", "The tips sebbi.pro holds for other chains."),
    "disclosure": ("The chain", "The chain reset, put on the record inside the chain."),
    # authority and agents
    "continuity": ("Authority and agents", "Authority continuity. Grants derived back to a named human at the instant of execution, with signed portable proofs."),
    "witnessed": ("Authority and agents", "What an outside party had already seen, and when, for any grant or record."),
    "passport": ("Authority and agents", "Agent Passport. Signed, single-use permission for one AI agent action, redeemed once and sealed. Also an MCP endpoint."),
    "lineage": ("Authority and agents", "Provenance across organisations: trace, impact and receipts."),
    "ratchet": ("Authority and agents", "Time only runs one way per actor: out-of-order actions are refused and the refusals published."),
    "noexec": ("Authority and agents", "The NO-EXEC blind bundle: real objects attached to claims they may not support, for external testing."),
    # oversight and notaries
    "oversight": ("Oversight and notaries", "Commit-before-reveal human review: the reviewer's call is sealed before the machine's verdict is shown."),
    "capture": ("Oversight and notaries", "One-button review capture for an operator's own screen, with server-measured dwell and browser-safe tokens."),
    "dsr": ("Oversight and notaries", "Data subject request lifecycle: received, assessed, extended, completed, with the deadline fixed at receipt."),
    "reconcile": ("Oversight and notaries", "Reconciliation: sample chosen from the live tip, sealed before data is requested, checked against the operator's system."),
    "declare": ("Oversight and notaries", "Declarations: publish the rules your decisions must always meet; every record is tested against them."),
    "conformance": ("Oversight and notaries", "Probes with known-wrong verdicts and network-breadth reporting, to catch rubber stamping and thin networks."),
    "sortition": ("Oversight and notaries", "Selection by lot from a public beacon: the operator stops choosing who gets audited."),
    # witness network
    "witness": ("Witness network", "Mutual witnessing: our tip, peers' tips, attestations and observation history."),
    "mutual": ("Witness network", "The outbound half: pulling peers' tips and pushing ours on a schedule."),
    "roster": ("Witness network", "The canonical network list, machine-readable."),
    "peer": ("Witness network", "Signed peer submission with a shared secret."),
    "signed": ("Witness network", "Ed25519 peer submission with a key we never hold."),
    "bind": ("Witness network", "Name binding for peers: claims, conflicts and revocation."),
    "praxis": ("Witness network", "Outbound submitter for the PRAXIS external witness (chain 4)."),
    "standard": ("Witness network", "The Ordering Test discovery document for this domain."),
    "standing": ("Witness network", "Temporal Standing Test runner and its evidence."),
    "network": ("Witness network", "Serves the public witness network page at /witness."),
    # public registers and standards
    "integrity": ("Registers and standards", "AI Integrity Declaration: the L0 to L4 standard, a public checker and a sealed register of verdicts."),
    "register": ("Registers and standards", "The Safe AI Registry, with inclusion, absence and consistency proofs."),
    "grade": ("Registers and standards", "Public transparency-file scanner and grade badges."),
    "publish": ("Registers and standards", "Seals the exact bytes a URL served at the moment it was fetched."),
    "codebase": ("Registers and standards", "Dated evidence of what code you held, and when. File contents never leave."),
    "plugin": ("Registers and standards", "Public proof log for legacy systems: send a hash, get an append-only receipt (/p/)."),
    "machine": ("Registers and standards", "The machine: ask in a web address, get checkable data back."),
    "prove": ("Registers and standards", "Every public proof route on one page (/prove) and as an index (/prove.json)."),
    "auditbridge": ("Registers and standards", "The chain answering inside Excel and Google Sheets, for auditors."),
    # billing
    "wallet": ("Billing", "Metering gate: quotes, charges, ledger and device counts."),
    "meter": ("Billing", "The 50p per device per month meter."),
    # operations
    "arm": ("Operations", "Arms every module after a deploy. Railway's healthcheck calls it, so deploys arm themselves."),
    "armall": ("Operations", "Arms every page module in one request."),
    "warmup": ("Operations", "Arms every page module and reports what is armed."),
    "spec": ("Operations", "Live API specification built from the running modules."),
    "selfcheck": ("Operations", "The conformance runner page at /self-check."),
    "verifier": ("Operations", "Hands out the offline authority verifier at /verify-authority.py."),
    # site pages and features (served pages, not APIs)
    "agentroom": ("Site pages", "The Agent Room at /room: AI agents collect passports and pass the gate, live."),
    "binddesk": ("Site pages", "Phone-friendly buttons for the signed lane."),
    "console": ("Site pages", "The operator console at /console."),
    "packconsole": ("Site pages", "The evidence pack page at /pack."),
    "peerconsole": ("Site pages", "The peer credential page at /peers."),
    "lineagedesk": ("Site pages", "The lineage desk at /lineage-desk."),
    "passportpage": ("Site pages", "The Agent Passport page at /passport and the Passport Kit downloads."),
    "startpage": ("Site pages", "Start here at /start: the customer front door."),
    "toolspage": ("Site pages", "The free tools at /tools and their files."),
    "map": ("Site pages", "The layer map at /map."),
    "investor": ("Site pages", "The investor and partner page at /investor-prospectus."),
    "homelink": ("Site pages", "Adds the homepage shortcut buttons."),
    "pwa": ("Site pages", "Makes sebbi.pro installable as an app on the home screen."),
    "roundlyverify": ("Site pages", "Serves the Roundly domain-verification file."),
    "sound": ("Site pages", "Background music and button sounds across the site."),
    "studio": ("Site pages", "Monop Studio at /create: video teasers with a pay-to-unlock lock."),
    "credits": ("Site pages", "Monop Studio credits: top-ups, unlocks and creator earnings (/c/)."),
    "creditspage": ("Site pages", "The viewer credit page at /credits."),
    "earnpage": ("Site pages", "The creator earnings and withdrawal page at /earn."),
    "cinema": ("Site pages", "The sebbi.pro Cinema at /cinema."),
    "cinemafeed": ("Site pages", "The video feed behind the Cinema."),
    "marquee": ("Site pages", "Creator submissions for the Cinema's 10p wing."),
    "game": ("Site pages", "Deep Run, the sebbi.pro game at /game, with a shared leaderboard."),
}
GROUPS = ["Decisions and evidence", "The chain", "Authority and agents", "Oversight and notaries",
          "Witness network", "Registers and standards", "Billing", "Operations", "Site pages"]


def public_actions(src):
    m = re.search(r"^PUBLIC\s*=\s*(.+?)(?:\n\S|\Z)", src, re.M | re.S)
    if not m:
        return []
    block = m.group(1)
    acts = re.findall(r'\(\s*"(GET|POST)"\s*,\s*"([^"]*)"\s*\)', block)
    comp = re.search(r'\(\s*"(GET|POST)"\s*,\s*\w+\s*\)\s*for\s+\w+\s+in\s*\(([^)]*)\)', block, re.S)
    if comp:
        acts += [(comp.group(1), a) for a in re.findall(r'"([^"]+)"', comp.group(2))]
    return acts


def catalogue():
    rows = []
    for f in sorted(os.listdir(MOD)):
        if not f.endswith(".py") or f in ("__init__.py", "router.py"):
            continue
        name = f[:-3]
        src = open(os.path.join(MOD, f), encoding="utf-8", errors="ignore").read()
        try:
            doc = ast.get_docstring(ast.parse(src)) or ""
        except SyntaxError:
            doc = ""
        ver = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M)
        pub = public_actions(src)
        gets = {a for m, a in pub if m == "GET"}
        posts = {a for m, a in pub if m == "POST" and a not in gets}
        pub_paths = sorted({"/x/%s/%s" % (name, a) if a else "/x/%s/" % name for a in gets})
        pub_posts = sorted({"/x/%s/%s" % (name, a) for a in posts if a})
        doc_paths = set(re.findall(r'(?:GET|POST)\s+(?:https://sebbi\.pro)?(/x/%s/[\w\-]*)' % re.escape(name), doc))
        keyed = sorted(p for p in doc_paths if p not in pub_paths and p.rstrip("/") != "/x/" + name)
        group, about = ABOUT.get(name, ("Site pages", next((l.strip() for l in doc.splitlines() if l.strip()), name)))
        about = re.sub(r"^modules/\S+\s*(v[\d.]+)?\s*[-–—]*\s*", "", about) or name
        rows.append({"name": name, "version": ver.group(1) if ver else "", "group": group,
                     "about": about, "public": pub_paths, "public_post": pub_posts,
                     "keyed": [k for k in keyed if k not in pub_posts]})
    return rows


def render(rows):
    out = [START, '<h2 id="routes">Route index <span class="badge b-open">generated from the code</span></h2>',
           '<p>Every module running on sebbi.pro, its version, and its routes. Generated from the modules themselves, '
           'so it cannot drift from what is deployed. <b>Public</b> routes need no key. <b>Keyed</b> routes take '
           '<code>Authorization: Bearer YOUR_KEY</code>. Every module also answers <code>/x/&lt;module&gt;/spec</code> '
           'or <code>/x/&lt;module&gt;/status</code> with its own description.</p>']
    for g in GROUPS:
        items = [r for r in rows if r["group"] == g]
        if not items:
            continue
        out.append('<h3>%s</h3>' % html.escape(g))
        out.append('<table class="routes"><thead><tr><th>Module</th><th>What it does</th><th>Routes</th></tr></thead><tbody>')
        for r in items:
            links = []
            for p in r["public"]:
                links.append('<a href="%s%s">%s</a>' % (HOST, html.escape(p), html.escape(p)))
            for p in r["public_post"]:
                links.append('<span>POST %s</span>' % html.escape(p))
            for p in r["keyed"]:
                links.append('<span class="kd">%s</span>' % html.escape(p))
            out.append('<tr><td><code>%s</code><br><small>v%s</small></td><td>%s</td><td>%s</td></tr>' % (
                html.escape(r["name"]), html.escape(r["version"] or "?"), html.escape(r["about"]),
                "<br>".join(links) or "<small>page only</small>"))
        out.append("</tbody></table>")
    out.append('<p class="small">Links are public GET routes; some need a parameter and say which when opened bare. POST routes are public but take a JSON body. Grey routes are keyed. %d modules.</p>' % len(rows))
    out.append(END)
    return "\n".join(out)


def main():
    page = open(PAGE, encoding="utf-8").read()
    block = render(catalogue())
    if START not in page:
        print("markers missing from developers.html")
        return 1
    new = page[:page.index(START)] + block + page[page.index(END) + len(END):]
    if "--check" in sys.argv:
        if new != page:
            print("developers.html route index is out of date. Run: python3 .github/scripts/route_index.py")
            return 1
        print("route index up to date")
        return 0
    open(PAGE, "w", encoding="utf-8").write(new)
    print("route index written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
