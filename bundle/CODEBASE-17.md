# Codebase — part 17 of 22

Contains:
- `index.html`


## `index.html`

1946 lines, 158149 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="google-site-verification" content="mM_hYELAWL0vrzIvAnKRBlUnN1kM-H656cmjMrFT-3U">
<title>AILeash &mdash; Every AI decision, sealed.</title>
<meta name="description" content="AI governance, fraud alerting and child-safety tools on one tamper-evident engine. Built to support EU AI Act Articles 9, 12, 13 and 14, the Online Safety Act, the ICO Children's Code and the DSA. Free for 90 days, then 50p per device per month.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600;1,9..144,900&family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
--ink:#0a0f1e;          /* deep navy - the vault */
--ink2:#10182e;
--paper:#f6f3ec;        /* ledger paper */
--line:#e3ddcf;         /* ledger rule */
--gold:#c9a84c;         /* the seal */
--allow:#1a9e6e;        /* decision colours - used ONLY for decisions */
--challenge:#c07a1d;
--block:#c8362b;
--mutei:rgba(255,255,255,0.45);
--mutep:#6b6353;
--disp:'Fraunces',Georgia,serif;
--body:'Space Grotesk',system-ui,sans-serif;
--mono:'IBM Plex Mono',monospace;
}
html{scroll-behavior:smooth}
body{background:var(--paper);color:var(--ink);font-family:var(--body);overflow-x:hidden}
::selection{background:var(--gold);color:var(--ink)}

/* ---------- nav ---------- */
nav{position:fixed;top:0;left:0;right:0;z-index:200;background:var(--ink);height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid rgba(201,168,76,0.25)}
.logo{font-family:var(--disp);font-weight:900;font-size:20px;color:#fff;letter-spacing:-0.02em}
.logo b{color:var(--gold);font-weight:900}
.nvl{display:flex;gap:20px;align-items:center}
.nvl a{color:var(--mutei);text-decoration:none;font-size:13px;font-weight:500;transition:color .2s}
.nvl a:hover{color:#fff}
.nvl a:focus-visible,.bgold:focus-visible,.bghost:focus-visible,.pbtn:focus-visible,.gobtn:focus-visible,.tab:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.ncta{background:var(--gold);color:var(--ink)!important;padding:9px 16px;border-radius:3px;font-weight:700!important}

/* ---------- the visit ledger rail (signature) ---------- */
#rail{position:fixed;left:0;top:64px;bottom:0;width:210px;background:var(--ink);z-index:150;padding:22px 16px;border-right:1px solid rgba(201,168,76,0.2);display:flex;flex-direction:column;overflow:hidden}
.rail-t{font-family:var(--mono);font-size:9px;letter-spacing:2.5px;text-transform:uppercase;color:var(--gold);margin-bottom:4px}
.rail-s{font-family:var(--mono);font-size:8.5px;color:var(--mutei);line-height:1.6;margin-bottom:14px}
#chain{flex:1;overflow:hidden;position:relative}
#chain::before{content:'';position:absolute;left:7px;top:0;bottom:0;width:1px;background:rgba(201,168,76,0.25)}
.blk{position:relative;padding:0 0 14px 22px;opacity:0;transform:translateY(6px);transition:opacity .5s,transform .5s}
.blk.on{opacity:1;transform:none}
.blk::before{content:'';position:absolute;left:3px;top:3px;width:9px;height:9px;border-radius:50%;background:var(--ink);border:2px solid var(--gold)}
.blk.on::before{background:var(--gold)}
.blk-n{font-family:var(--mono);font-size:9px;color:#fff;font-weight:600}
.blk-h{font-family:var(--mono);font-size:8.5px;color:var(--gold);word-break:break-all;line-height:1.5}
.rail-foot{font-family:var(--mono);font-size:8.5px;color:var(--mutei);line-height:1.6;padding-top:10px;border-top:1px solid rgba(255,255,255,0.08)}
.rail-foot b{color:#7fe3b0;font-weight:600}

/* mobile: rail collapses to a live chip */
#chip{display:none;position:fixed;bottom:14px;left:14px;right:14px;z-index:150;background:var(--ink);border:1px solid rgba(201,168,76,0.4);border-radius:6px;padding:9px 13px;font-family:var(--mono);font-size:9.5px;color:var(--gold);box-shadow:0 6px 24px rgba(10,15,30,0.35)}
#chip .ch{color:#7fe3b0;word-break:break-all}

/* ---------- page shell ---------- */
main{margin-left:210px;padding-top:64px}
section{position:relative;border-bottom:1px solid var(--line)}
.wrap{max-width:1040px;margin:0 auto;padding:84px 48px}

/* ledger entry header on every section */
.entry{display:flex;align-items:baseline;gap:14px;margin-bottom:8px;font-family:var(--mono);font-size:10px;letter-spacing:2px;text-transform:uppercase}
.entry .no{color:var(--ink);font-weight:600}
.entry .rule{flex:1;height:1px;background:var(--line);align-self:center}
.entry .sealed{color:var(--mutep);letter-spacing:0;text-transform:none;font-size:9.5px}
.entry .sealed b{color:var(--gold);font-weight:600}

h1{font-family:var(--disp);font-weight:900;font-size:clamp(44px,5.4vw,76px);line-height:0.98;letter-spacing:-0.025em}
h1 i{font-style:italic;color:var(--gold)}
h2{font-family:var(--disp);font-weight:900;font-size:clamp(30px,3.4vw,46px);line-height:1.02;letter-spacing:-0.02em;margin-bottom:14px}
h2 i{font-style:italic;color:var(--gold)}
.lead{font-size:16px;line-height:1.75;color:var(--mutep);max-width:640px}
.lead b{color:var(--ink);font-weight:700}

/* ---------- hero (dark) ---------- */
#hero{background:var(--ink);color:#fff;border-bottom:none}
#hero .wrap{padding:96px 48px 72px}
#hero .lead{color:var(--mutei)}
#hero .lead b{color:#fff}
.deadline{display:inline-flex;gap:10px;align-items:center;flex-wrap:wrap;font-family:var(--mono);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#ffb4ad;border:1px solid rgba(200,54,43,0.5);padding:7px 13px;border-radius:3px;margin-bottom:28px}
.deadline b{color:#fff}
.hseal{margin-top:22px;font-family:var(--mono);font-size:11px;color:var(--gold);min-height:18px}
.hseal .hh{color:#7fe3b0;word-break:break-all}
.hbtns{display:flex;gap:12px;flex-wrap:wrap;margin-top:34px}
.bgold{background:var(--gold);color:var(--ink);padding:15px 26px;border:none;border-radius:3px;font-family:var(--body);font-weight:700;font-size:14px;text-decoration:none;display:inline-block;transition:transform .15s,background .15s;cursor:pointer}
.bgold:hover{background:#dbbd63;transform:translateY(-2px)}
.bghost{background:transparent;color:var(--mutei);padding:15px 26px;border:1px solid rgba(255,255,255,0.2);border-radius:3px;font-weight:600;font-size:14px;text-decoration:none;display:inline-block;transition:all .15s}
.bghost:hover{color:#fff;border-color:rgba(255,255,255,0.55)}

/* live decision strip */
.ticker{background:var(--ink2);border-top:1px solid rgba(201,168,76,0.2);overflow:hidden;padding:11px 0;white-space:nowrap}
.tk{display:inline-block;animation:tk 38s linear infinite;font-family:var(--mono);font-size:10.5px}
.tk span{margin:0 26px;color:var(--mutei)}
.tk .A{color:var(--allow)}.tk .C{color:var(--challenge)}.tk .B{color:var(--block)}
@keyframes tk{from{transform:translateX(0)}to{transform:translateX(-50%)}}

/* ---------- how ---------- */
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin-top:40px}
.st{background:var(--paper);padding:30px 26px}
.st .k{font-family:var(--mono);font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--gold);font-weight:600;margin-bottom:12px}
.st h3{font-family:var(--disp);font-weight:900;font-size:21px;margin-bottom:10px;letter-spacing:-0.01em}
.st p{font-size:13.5px;color:var(--mutep);line-height:1.7}
.st p b{color:var(--ink)}

/* ---------- products (ledger rows, not cards) ---------- */
.prod{display:grid;grid-template-columns:200px 1fr 200px;gap:36px;padding:38px 0;border-top:1px solid var(--line);align-items:start}
.prod:first-of-type{border-top:none}
.pn{font-family:var(--disp);font-weight:900;font-size:26px;letter-spacing:-0.015em;line-height:1.05}
.pn small{display:block;font-family:var(--mono);font-weight:400;font-size:9.5px;letter-spacing:2px;text-transform:uppercase;color:var(--mutep);margin-top:8px}
.pd{font-size:14px;line-height:1.75;color:var(--mutep)}
.pd b{color:var(--ink)}
.pf{margin-top:14px;font-family:var(--mono);font-size:11px;line-height:2.1;color:var(--ink)}
.pf em{font-style:normal;color:var(--gold);margin-right:8px}
.pp{text-align:right}
.pp .amt{font-family:var(--disp);font-weight:900;font-size:40px;line-height:1}
.pp .per{font-family:var(--mono);font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--mutep);margin:6px 0 16px}
.pbtn{display:inline-block;background:var(--ink);color:#fff;padding:11px 18px;border-radius:3px;font-size:13px;font-weight:700;text-decoration:none;transition:background .15s}
.pbtn:hover{background:#232c47}
.pbtn.free{background:var(--allow)}
.guardian-note{font-family:var(--mono);font-size:9.5px;color:var(--allow);margin-top:8px}

/* ---------- signal packs ---------- */
#packs{background:#fbf9f4}
.corepack{margin-top:36px;border:1px solid var(--line);border-left:3px solid var(--ink);background:#fff;padding:26px 28px}
.corepack .k{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--mutep);margin-bottom:12px}
.sigs{display:flex;flex-wrap:wrap;gap:8px}
.sig{font-family:var(--mono);font-size:10.5px;border:1px solid var(--line);background:var(--paper);padding:6px 11px;border-radius:3px;color:var(--ink)}
.packrow{display:grid;grid-template-columns:220px 1fr;gap:32px;padding:30px 0;border-top:1px solid var(--line);align-items:start}
.packn{font-family:var(--disp);font-weight:900;font-size:22px;line-height:1.1;letter-spacing:-0.015em}
.packn small{display:block;font-family:var(--mono);font-weight:400;font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--mutep);margin-top:7px}
.packd{font-size:14px;line-height:1.75;color:var(--mutep)}
.packd b{color:var(--ink)}
.packsig{margin-top:12px;display:flex;flex-wrap:wrap;gap:7px}
.packsig span{font-family:var(--mono);font-size:10px;color:var(--mutep);border:1px dashed var(--line);padding:4px 9px;border-radius:3px}
.sealnote{margin-top:34px;border:1px dashed var(--gold);border-radius:5px;background:rgba(201,168,76,0.07);padding:22px 24px}
.sealnote h3{font-family:var(--disp);font-weight:900;font-size:21px;margin-bottom:10px}
.sealnote p{font-size:14px;line-height:1.75;color:var(--mutep)}
.sealnote p b{color:var(--ink)}
.sealnote .ex{font-family:var(--mono);font-size:11px;line-height:2;color:var(--ink);margin-top:14px;background:#fff;border:1px solid var(--line);border-radius:4px;padding:14px}
.sealnote .ex em{font-style:normal;color:var(--gold);margin-right:8px}

/* ---------- calculator (dark) ---------- */
#margin{background:var(--ink);color:#fff}
#margin .entry .no{color:#fff}
#margin .entry .rule{background:rgba(255,255,255,0.12)}
#margin .lead{color:var(--mutei)}
.cwrap{margin-top:36px;border:1px solid rgba(201,168,76,0.3);border-radius:6px;padding:34px;background:var(--ink2)}
.crow{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:26px}
.clab{font-family:var(--mono);font-size:9.5px;letter-spacing:2px;text-transform:uppercase;color:var(--mutei);margin-bottom:10px}
.cin{display:flex;align-items:center;gap:10px}
.cin .pd2{font-family:var(--disp);font-size:26px;color:var(--gold);font-weight:900}
input.ci,select.ci{background:rgba(255,255,255,0.07);border:1px solid rgba(201,168,76,0.35);color:#fff;font-family:var(--mono);font-size:17px;padding:12px 15px;border-radius:4px;outline:none;width:100%}
input.ci:focus,select.ci:focus{border-color:var(--gold)}
select.ci option{background:var(--ink)}
.cres{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:rgba(255,255,255,0.08);border-radius:4px;overflow:hidden}
.cr2{background:rgba(255,255,255,0.03);padding:22px;text-align:center}
.cr2 .l{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--mutei);margin-bottom:10px}
.cr2 .v{font-family:var(--disp);font-weight:900;font-size:30px}
.v-you{color:#7fe3b0}.v-user{color:var(--gold)}.v-we{color:rgba(255,255,255,0.35)}
.cr2 .s{font-family:var(--mono);font-size:8.5px;color:var(--mutei);margin-top:6px}

/* ---------- referral ---------- */
.refrow{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin-top:36px}
.rf{background:var(--paper);padding:28px 24px}
.rf h3{font-family:var(--disp);font-weight:900;font-size:19px;margin-bottom:8px}
.rf p{font-size:13px;color:var(--mutep);line-height:1.7}
.rf .big{font-family:var(--disp);font-weight:900;font-size:34px;color:var(--gold);margin-top:12px}
.rf .bl{font-family:var(--mono);font-size:8.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--mutep)}

/* ---------- law ---------- */
.laws{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:36px}
.law{border:1px solid var(--line);border-left:3px solid var(--ink);padding:24px;background:#fbf9f4}
.law .act{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--mutep);margin-bottom:10px}
.law .plain{font-family:var(--disp);font-weight:600;font-style:italic;font-size:17px;line-height:1.45;margin-bottom:10px}
.law p{font-size:13px;color:var(--mutep);line-height:1.7}
.law ul{list-style:none;margin-top:12px}
.law li{font-family:var(--mono);font-size:11px;line-height:2;color:var(--ink)}
.law li::before{content:'\2713\00a0\00a0';color:var(--allow);font-weight:700}
.timeline{margin-top:30px;border:1px solid var(--line);background:#fff}
.tlrow{display:grid;grid-template-columns:170px 1fr;gap:0;border-top:1px solid var(--line)}
.tlrow:first-child{border-top:none;background:var(--ink)}
.tlrow:first-child .tld,.tlrow:first-child .tlw{color:#fff;font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase}
.tld{padding:14px 18px;font-family:var(--mono);font-size:11.5px;font-weight:600;color:var(--ink);border-right:1px solid var(--line)}
.tlw{padding:14px 18px;font-size:13.5px;line-height:1.7;color:var(--mutep)}
.tlw b{color:var(--ink)}
.tlrow.now .tld{color:var(--block)}
@media(max-width:760px){
.tlrow{grid-template-columns:1fr}
.tld{border-right:none;padding-bottom:0}
}

/* ---------- coverage map ---------- */
#coverage{background:var(--paper)}
.covrow{display:grid;grid-template-columns:230px 1fr 1fr;gap:0;border:1px solid var(--line);border-top:none;align-items:stretch;background:#fff}
.covrow.head{border-top:1px solid var(--line);background:var(--ink)}
.covrow.head .cc{color:#fff;font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;padding:12px 18px}
.covrow.head .cc b{color:var(--gold)}
.cc{padding:18px;border-left:1px solid var(--line);font-size:13px;line-height:1.7}
.cc:first-child{border-left:none}
.cov-art{font-family:var(--mono);font-size:11px;font-weight:600;color:var(--ink);line-height:1.6}
.cov-art small{display:block;font-weight:400;font-size:9.5px;letter-spacing:1px;text-transform:uppercase;color:var(--mutep);margin-top:4px}
.cov-req{color:var(--mutep)}
.cov-req b{color:var(--ink)}
.cov-how{font-family:var(--mono);font-size:11px;color:var(--ink);line-height:1.9}
.cov-how em{font-style:normal;color:var(--allow);margin-right:7px;font-weight:600}
.cov-note{margin-top:22px;border:1px dashed var(--gold);border-radius:5px;background:rgba(201,168,76,0.06);padding:16px 20px;font-family:var(--mono);font-size:11px;line-height:1.9;color:var(--mutep)}
.cov-note b{color:var(--ink)}
@media(max-width:900px){
.covrow{grid-template-columns:1fr}
.cc{border-left:none;border-top:1px solid var(--line)}
.covrow.head{display:none}
}

/* ---------- the outside clock: anchoring ---------- */
#anchor{background:var(--ink2);color:#fff}
#anchor .entry .no{color:#fff}
#anchor .entry .rule{background:rgba(255,255,255,0.12)}
#anchor .entry .sealed{color:rgba(255,255,255,0.4)}
#anchor .lead{color:var(--mutei)}
#anchor .lead b{color:#fff}
.anchorgrid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.1);margin-top:38px}
.ag{background:var(--ink2);padding:28px 26px}
.ag .k{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--gold);margin-bottom:12px}
.ag h3{font-family:var(--disp);font-weight:900;font-size:20px;margin-bottom:10px;color:#fff;letter-spacing:-0.01em}
.ag p{font-size:13.5px;line-height:1.75;color:var(--mutei)}
.ag p b{color:#fff}
.anchorline{margin-top:38px;border:1px solid rgba(201,168,76,0.3);border-radius:6px;background:rgba(0,0,0,0.25);padding:24px 26px;font-family:var(--mono);font-size:11.5px;line-height:2.1;color:var(--mutei);word-break:break-all}
.anchorline em{font-style:normal;color:var(--gold);margin-right:10px}
.anchorline .g{color:#7fe3b0}
.anchorstraight{margin-top:26px;border-left:3px solid var(--gold);padding:6px 0 6px 20px;font-size:14px;line-height:1.75;color:var(--mutei);max-width:680px}
.anchorstraight b{color:#fff}

/* ---------- code block (SDK section) ---------- */
.codeblk{margin-top:26px;background:var(--ink);border-radius:6px;padding:22px 24px;font-family:var(--mono);font-size:12.5px;line-height:1.9;color:#e7e2d4;overflow-x:auto}
.codeblk .c{color:var(--mutei)}
.codeblk .g{color:var(--gold)}
.codeblk .k{color:#7fe3b0}
.codeblk b{color:#fff;font-weight:600}
.oneline{font-family:var(--mono);font-size:clamp(14px,2.3vw,21px);color:var(--gold);background:var(--ink);border-radius:6px;padding:20px 24px;margin-top:26px;overflow-x:auto;white-space:nowrap}

/* ---------- dark section variant used by Sebdog ---------- */
#onprem{background:var(--ink);color:#fff}
#onprem .entry .no{color:#fff}
#onprem .entry .rule{background:rgba(255,255,255,0.12)}
#onprem .entry .sealed{color:rgba(255,255,255,0.4)}
#onprem .lead{color:var(--mutei)}
#onprem .lead b{color:#fff}
#onprem .anchorgrid{background:rgba(255,255,255,0.1);border-color:rgba(255,255,255,0.1)}
#onprem .ag{background:var(--ink)}

/* ---------- lane table (three ways to submit) ---------- */
.lanes{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin-top:34px}
.lane{background:var(--paper);padding:26px 24px}
.lane .k{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--gold);font-weight:600;margin-bottom:10px}
.lane h3{font-family:var(--disp);font-weight:900;font-size:19px;margin-bottom:10px;letter-spacing:-0.01em}
.lane p{font-size:13px;color:var(--mutep);line-height:1.7}
.lane p b{color:var(--ink)}
.lane .no{display:block;margin-top:10px;font-family:var(--mono);font-size:11px;line-height:1.8;color:var(--block)}
.lane .yes{display:block;margin-top:8px;font-family:var(--mono);font-size:11px;line-height:1.8;color:var(--allow)}
@media(max-width:900px){.lanes{grid-template-columns:1fr}}

/* ---------- evidence pack ---------- */
#evidence{background:var(--ink2);color:#fff}
#evidence .entry .no{color:#fff}
#evidence .entry .rule{background:rgba(255,255,255,0.12)}
#evidence .entry .sealed{color:rgba(255,255,255,0.4)}
#evidence .lead{color:var(--mutei)}
#evidence .lead b{color:#fff}
#evidence h2{color:#fff}
.packrow{display:grid;grid-template-columns:170px 1fr;gap:26px;padding:22px 0;border-top:1px solid rgba(255,255,255,0.1);align-items:start}
.packrow:first-of-type{border-top:none}
.packrow .t{font-family:var(--mono);font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--gold);padding-top:3px}
.packrow .b{font-size:14px;line-height:1.75;color:var(--mutei)}
.packrow .b b{color:#fff}
@media(max-width:760px){.packrow{grid-template-columns:1fr;gap:8px}}

/* ---------- install ---------- */
.inst{counter-reset:s;margin-top:34px}
.instep{position:relative;padding:0 0 26px 54px;border-left:1px solid var(--line);margin-left:15px}
.instep:last-child{border-left-color:transparent;padding-bottom:0}
.instep::before{counter-increment:s;content:counter(s);position:absolute;left:-15px;top:-2px;width:30px;height:30px;border-radius:50%;background:var(--ink);color:var(--gold);font-family:var(--mono);font-size:13px;font-weight:600;display:flex;align-items:center;justify-content:center}
.instep h3{font-family:var(--disp);font-weight:900;font-size:21px;margin-bottom:8px;letter-spacing:-0.01em}
.instep p{font-size:14px;line-height:1.75;color:var(--mutep);max-width:620px}
.instep p b{color:var(--ink)}
.instep .cmd{margin-top:12px;background:var(--ink);border-radius:5px;padding:14px 18px;font-family:var(--mono);font-size:12.5px;line-height:1.9;color:#e7e2d4;overflow-x:auto}
.instep .cmd .g{color:var(--gold)}
.instep .cmd .c{color:rgba(255,255,255,0.35)}
.instep .cmd .k{color:#7fe3b0}
@media(max-width:760px){.anchorgrid{grid-template-columns:1fr}}

/* ---------- verify moment ---------- */
#verify{background:var(--ink);color:#fff;text-align:center}
#verify .wrap{padding:76px 48px}
#verify .lead{margin:0 auto;color:var(--mutei)}
#vbtn{margin-top:30px}
#vout{margin-top:26px;font-family:var(--mono);font-size:11px;line-height:2;color:var(--mutei);min-height:24px;max-width:620px;margin-left:auto;margin-right:auto;text-align:left;word-break:break-all}
#vout .ok{color:#7fe3b0}#vout .h{color:var(--gold)}

/* ---------- signup ---------- */
#signup .wrap{max-width:640px}
.tabs{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--ink);border-radius:4px;overflow:hidden;margin:28px 0 22px}
.tab{padding:11px 4px;font-family:var(--mono);font-size:9.5px;letter-spacing:1.5px;text-transform:uppercase;font-weight:600;background:var(--paper);color:var(--mutep);border:none;cursor:pointer;transition:all .15s}
.tab.on{background:var(--ink);color:var(--gold)}
.fr{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.f{margin-bottom:14px}
.f label{display:block;font-family:var(--mono);font-size:9.5px;letter-spacing:2px;text-transform:uppercase;color:var(--mutep);margin-bottom:7px}
.f input,.f select{width:100%;background:#fff;border:1px solid var(--line);color:var(--ink);padding:13px 14px;font-size:14px;font-family:var(--body);border-radius:4px;outline:none;transition:border-color .15s}
.f input:focus,.f select:focus{border-color:var(--ink)}
.refin{width:100%;background:#fff;border:1px dashed var(--gold);border-radius:4px;padding:13px 14px;font-family:var(--mono);font-size:13px;color:var(--ink);outline:none;margin-bottom:14px}
.gobtn{width:100%;background:var(--gold);color:var(--ink);border:none;border-radius:4px;padding:16px;font-family:var(--body);font-size:15px;font-weight:700;cursor:pointer;transition:background .15s}
.gobtn:hover{background:#dbbd63}
.gobtn:disabled{opacity:0.6;cursor:default}
.merr,.mok{display:none;margin-top:12px;font-family:var(--mono);font-size:11px;padding:11px 13px;border-radius:4px}
.merr{color:var(--block);background:#fdeeec;border:1px solid #f3cbc6}
.mok{color:var(--allow);background:#e9f7f0;border:1px solid #bfe6d4}
.merr.show,.mok.show{display:block}
.keybox{display:none;margin-top:20px;background:var(--ink);border-radius:6px;padding:24px}
.keybox.show{display:block}
.kl{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--gold);margin-bottom:8px}
.kv{font-family:var(--mono);font-size:11.5px;color:#7fe3b0;word-break:break-all;background:rgba(0,0,0,0.35);padding:12px;border-radius:4px}
.refbox{margin-top:14px;border:1px dashed rgba(201,168,76,0.5);border-radius:4px;padding:14px}
.refbox .c{font-family:var(--mono);font-size:18px;color:var(--gold);font-weight:600}
.refbox p{font-size:12px;color:var(--mutei);margin-top:6px;line-height:1.6}
.usage{margin-top:14px;font-family:var(--mono);font-size:10.5px;line-height:2;color:rgba(255,255,255,0.35);background:rgba(0,0,0,0.25);padding:12px;border-radius:4px}
.usage em{font-style:normal;color:#8fbcff}

/* ---------- footer ---------- */
footer{background:var(--ink);color:var(--mutei);padding:52px 48px 40px;margin-left:0}
.fin{max-width:1040px;margin:0 auto;display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:40px}
.fin h4{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--gold);margin-bottom:12px}
.fin a{display:block;color:var(--mutei);text-decoration:none;font-size:12.5px;margin-bottom:7px;transition:color .15s}
.fin a:hover{color:#fff}
.fdesc{font-size:12.5px;line-height:1.8}
.fbot{max-width:1040px;margin:32px auto 0;padding-top:18px;border-top:1px solid rgba(255,255,255,0.08);display:flex;justify-content:space-between;gap:12px;font-family:var(--mono);font-size:9.5px;color:rgba(255,255,255,0.25)}

@media(prefers-reduced-motion:reduce){
.tk{animation:none}
.blk{transition:none}
html{scroll-behavior:auto}
.rise{animation:none!important;opacity:1!important;transform:none!important}
}

/* ---------- the patrol: robot walks its robot dog on a leash ---------- */
#patrol-strip{position:relative;height:118px;overflow:hidden;border-top:1px solid rgba(201,168,76,0.15)}
#patrol-strip::after{content:'';position:absolute;left:0;right:0;bottom:26px;height:1px;background:linear-gradient(90deg,transparent,rgba(201,168,76,0.35) 12%,rgba(201,168,76,0.35) 88%,transparent)}
.patrol{position:absolute;bottom:24px;left:0;animation:patrolmove 34s linear infinite}
.patrol-flip{animation:patrolflip 34s steps(1) infinite;transform-origin:center}
@keyframes patrolmove{0%{transform:translateX(-170px)}50%{transform:translateX(100vw)}100%{transform:translateX(-170px)}}
@keyframes patrolflip{0%{transform:scaleX(1)}50%{transform:scaleX(-1)}100%{transform:scaleX(1)}}
.leg{transform-origin:top center;animation:step .62s ease-in-out infinite alternate}
.leg.b{animation-delay:.31s}
@keyframes step{from{transform:rotate(14deg)}to{transform:rotate(-14deg)}}
.dogleg{transform-origin:top center;animation:step .38s ease-in-out infinite alternate}
.dogleg.b{animation-delay:.19s}
.tailwag{transform-origin:bottom left;animation:wag .5s ease-in-out infinite alternate}
@keyframes wag{from{transform:rotate(-12deg)}to{transform:rotate(16deg)}}
.bob{animation:bob .62s ease-in-out infinite alternate}
@keyframes bob{from{transform:translateY(0)}to{transform:translateY(-1.6px)}}
.blinky{animation:blink 3.4s steps(1) infinite}
@keyframes blink{0%,92%{opacity:1}93%,97%{opacity:0.15}98%{opacity:1}}
.patrol-cap{position:absolute;bottom:6px;width:100%;text-align:center;font-family:var(--mono);font-size:9px;letter-spacing:2.5px;text-transform:uppercase;color:rgba(255,255,255,0.3)}
@media(prefers-reduced-motion:reduce){
.patrol{animation:none;left:50%;transform:translateX(-50%)}
.patrol-flip,.leg,.dogleg,.tailwag,.bob,.blinky{animation:none}
}

/* ---------- visitor seal stamp ---------- */
.vstamp{display:inline-flex;align-items:center;gap:12px;margin-top:20px;border:1px dashed rgba(201,168,76,0.5);border-radius:5px;padding:11px 16px;background:rgba(201,168,76,0.06)}
.vstamp svg{flex-shrink:0}
.vstamp .vn{font-family:var(--disp);font-weight:900;font-size:20px;color:var(--gold);line-height:1}
.vstamp .vl{font-family:var(--mono);font-size:8.5px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.4);margin-top:3px}
.vstamp .vh{font-family:var(--mono);font-size:9px;color:#7fe3b0;margin-top:3px;word-break:break-all}

/* orchestrated hero entrance */
.rise{opacity:0;transform:translateY(14px);animation:rise .7s cubic-bezier(.2,.7,.2,1) forwards}
.d1{animation-delay:.05s}.d2{animation-delay:.22s}.d3{animation-delay:.4s}.d4{animation-delay:.58s}
@keyframes rise{to{opacity:1;transform:none}}

@media(max-width:1120px){
.prod{grid-template-columns:1fr;gap:16px}
.pp{text-align:left}
.packrow{grid-template-columns:1fr;gap:14px}
}
@media(max-width:900px){
#rail{display:none}
#chip{display:block}
main{margin-left:0}
.wrap,#hero .wrap,#verify .wrap{padding:56px 20px}
.nvl a:not(.ncta){display:none}
.steps,.refrow,.laws,.crow,.cres,.fr,.tabs{grid-template-columns:1fr}
footer{padding:40px 20px}
.fin{grid-template-columns:1fr}
.fbot{flex-direction:column;gap:6px}
}


/* ---------- the proving ground ---------- */
.pgtabs{display:flex;gap:0;margin:34px auto 0;max-width:520px;border:1px solid rgba(201,168,76,0.4);border-radius:4px;overflow:hidden}
.pgtab{flex:1;padding:13px 10px;background:transparent;color:var(--mutei);border:none;cursor:pointer;font-family:var(--mono);font-size:10.5px;letter-spacing:1.5px;text-transform:uppercase;transition:background .15s,color .15s}
.pgtab.on{background:var(--gold);color:var(--ink);font-weight:600}
.pgtab:not(.on):hover{color:#fff}
.pgpanel{margin-top:30px;text-align:left}
.pgpanel.hide{display:none}
.pglead{font-size:14.5px;line-height:1.75;color:var(--mutei);max-width:640px;margin:0 auto 14px}
.pglead b{color:#fff}

.pgform{display:grid;grid-template-columns:1fr 1fr;gap:22px 30px;max-width:760px;margin:0 auto}
.pgf label{display:flex;justify-content:space-between;align-items:baseline;gap:10px;font-family:var(--mono);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--mutei);margin-bottom:9px}
.pgv{font-family:var(--disp);font-weight:900;font-size:19px;color:var(--gold);letter-spacing:-0.01em;text-transform:none}
.pghint{display:block;font-size:11.5px;color:rgba(255,255,255,0.32);margin-top:7px;line-height:1.5}
.pgf input[type=range]{width:100%;-webkit-appearance:none;appearance:none;height:2px;background:rgba(255,255,255,0.18);border-radius:2px;outline:none}
.pgf input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;border-radius:50%;background:var(--gold);cursor:pointer;border:3px solid var(--ink)}
.pgf input[type=range]::-moz-range-thumb{width:16px;height:16px;border-radius:50%;background:var(--gold);cursor:pointer;border:3px solid var(--ink)}
.pgf input[type=range]:focus-visible{outline:2px solid var(--gold);outline-offset:4px}
.pgf select{width:100%;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.18);color:#fff;padding:10px 12px;border-radius:4px;font-family:var(--body);font-size:14px;outline:none}
.pgf select:focus{border-color:var(--gold)}
.pgf select option{background:var(--ink)}
.pgcheck{display:flex!important;align-items:center;gap:9px;margin-top:14px;font-family:var(--body)!important;font-size:12.5px!important;letter-spacing:0!important;text-transform:none!important;color:var(--mutei);cursor:pointer;justify-content:flex-start!important}
.pgcheck input{accent-color:var(--gold);width:15px;height:15px}

.pgactions{display:flex;flex-direction:column;align-items:center;gap:11px;margin-top:32px}
.pgnote{font-family:var(--mono);font-size:10px;letter-spacing:1px;color:rgba(255,255,255,0.3)}

.pgresult{max-width:760px;margin:30px auto 0;text-align:left}
.pgverdictcard{border:1px solid rgba(255,255,255,0.14);border-radius:6px;background:rgba(0,0,0,0.28);overflow:hidden}
.pgvhead{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;padding:24px 26px;border-bottom:1px solid rgba(255,255,255,0.1)}
.pgvword{font-family:var(--disp);font-weight:900;font-size:44px;line-height:1;letter-spacing:-0.02em}
.pgvword.ALLOW{color:var(--allow)}.pgvword.CHALLENGE{color:var(--challenge)}.pgvword.BLOCK{color:var(--block)}
.pgvscore{font-family:var(--mono);font-size:13px;color:var(--mutei)}
.pgvscore b{color:#fff}
.pgvreasons{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}
.pgvreasons span{font-family:var(--mono);font-size:10px;border:1px solid rgba(255,255,255,0.2);border-radius:3px;padding:4px 9px;color:var(--mutei)}
.pgrow{padding:20px 26px;border-bottom:1px solid rgba(255,255,255,0.08)}
.pgrow:last-child{border-bottom:none}
.pgrlbl{font-family:var(--mono);font-size:9.5px;letter-spacing:2px;text-transform:uppercase;color:var(--gold);margin-bottom:9px}
.pgrbody{font-size:14px;line-height:1.75;color:var(--mutei)}
.pgrbody b{color:#fff}
.pgmono{font-family:var(--mono);font-size:11.5px;line-height:2;color:var(--mutei);word-break:break-all}
.pgmono a{color:#7fe3b0;text-decoration:none;border-bottom:1px solid rgba(127,227,176,0.3)}
.pgmono a:hover{border-bottom-color:#7fe3b0}
.pgmono em{font-style:normal;color:var(--gold);margin-right:8px}
.pgcf{border-left:3px solid var(--gold);padding-left:18px}
.pgcf .big{font-family:var(--disp);font-weight:900;font-size:20px;line-height:1.35;color:#fff;letter-spacing:-0.01em}
.pgsteps{list-style:none;margin-top:4px}
.pgsteps li{position:relative;padding-left:20px;font-size:13.5px;line-height:1.7;color:var(--mutei);margin-bottom:6px}
.pgsteps li::before{content:'';position:absolute;left:0;top:9px;width:5px;height:5px;border-radius:50%;background:var(--gold)}
.pgerr{border:1px solid rgba(200,54,43,0.5);background:rgba(200,54,43,0.08);border-radius:6px;padding:16px 20px;font-size:13.5px;color:#ffb4ad;line-height:1.7}

.pgcase{max-width:640px;margin:26px auto 0}
.pgcase.hide{display:none}
.pgclockbar{display:flex;align-items:baseline;justify-content:space-between;border:1px solid rgba(201,168,76,0.35);border-radius:5px 5px 0 0;background:rgba(201,168,76,0.07);padding:12px 20px}
.pgclocklbl{font-family:var(--mono);font-size:9.5px;letter-spacing:2px;text-transform:uppercase;color:var(--gold)}
.pgclock{font-family:var(--disp);font-weight:900;font-size:26px;color:#fff;letter-spacing:-0.01em;font-variant-numeric:tabular-nums}
.pgmaterial{border:1px solid rgba(255,255,255,0.14);border-top:none;background:rgba(0,0,0,0.28);padding:6px 20px 14px}
.pgmrow{display:flex;justify-content:space-between;gap:16px;padding:11px 0;border-bottom:1px solid rgba(255,255,255,0.07);font-size:13.5px}
.pgmrow:last-child{border-bottom:none}
.pgmk{color:var(--mutei)}
.pgmv{font-family:var(--mono);font-size:12.5px;color:#fff;text-align:right}
.pgverdicts{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:18px}
.pgvbtn{padding:15px 8px;border-radius:4px;border:1px solid;background:transparent;cursor:pointer;font-family:var(--body);font-size:13.5px;font-weight:700;transition:background .15s,color .15s}
.pgvbtn.allow{color:var(--allow);border-color:rgba(26,158,110,0.5)}
.pgvbtn.allow:hover{background:var(--allow);color:var(--ink)}
.pgvbtn.chal{color:var(--challenge);border-color:rgba(192,122,29,0.5)}
.pgvbtn.chal:hover{background:var(--challenge);color:var(--ink)}
.pgvbtn.block{color:var(--block);border-color:rgba(200,54,43,0.5)}
.pgvbtn.block:hover{background:var(--block);color:#fff}

.pgcompare{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:rgba(255,255,255,0.12);border:1px solid rgba(255,255,255,0.12);border-radius:6px;overflow:hidden}
.pgc{background:rgba(0,0,0,0.3);padding:22px}
.pgclbl{font-family:var(--mono);font-size:9.5px;letter-spacing:2px;text-transform:uppercase;color:var(--mutei);margin-bottom:10px}
.pgcval{font-family:var(--disp);font-weight:900;font-size:30px;line-height:1;letter-spacing:-0.02em}
.pgflag{margin-top:18px;border:1px dashed rgba(201,168,76,0.5);background:rgba(201,168,76,0.07);border-radius:5px;padding:16px 20px;font-size:13.5px;line-height:1.7;color:var(--mutei)}
.pgflag b{color:var(--gold)}
.pgfoot{max-width:700px;margin:38px auto 0;font-size:12.5px;line-height:1.8;color:rgba(255,255,255,0.32);text-align:center}
.pgfoot a{color:var(--gold);text-decoration:none}

@media(max-width:760px){
.pgform{grid-template-columns:1fr;gap:20px}
.pgvhead{padding:20px}
.pgvreasons{margin-left:0;width:100%}
.pgcompare{grid-template-columns:1fr}
.pgverdicts{grid-template-columns:1fr}
.pgtabs{max-width:100%}
}
@media(prefers-reduced-motion:reduce){.pgtab,.pgvbtn{transition:none}}


/* ---------- live figures ---------- */
.pgcharts{max-width:1000px;margin:44px auto 0;border-top:1px solid rgba(255,255,255,0.1);padding-top:30px}
.pgchead{display:flex;align-items:baseline;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:20px}
.pgclbl2{font-family:var(--mono);font-size:10px;letter-spacing:2.5px;text-transform:uppercase;color:var(--gold)}
.pgcsub{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.3)}
.pgcgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.1);border-radius:6px;overflow:hidden}
.pgcard{background:rgba(0,0,0,0.28);padding:20px 22px 18px}
.pgctitle{font-family:var(--mono);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--mutei);margin-bottom:14px;display:flex;justify-content:space-between;gap:10px}
.pgctitle span{font-family:var(--disp);font-weight:900;font-size:17px;color:#fff;letter-spacing:-0.01em;text-transform:none}
.pgcbody{height:90px}
.pgcbody svg{width:100%;height:100%;display:block;overflow:visible}
.pgcfoot{font-size:11.5px;line-height:1.6;color:rgba(255,255,255,0.34);margin-top:12px}
.pgcempty{font-family:var(--mono);font-size:10.5px;color:rgba(255,255,255,0.28)}
@media(max-width:900px){.pgcgrid{grid-template-columns:1fr}}

</style>
</head>
<body>

<nav>
<a class="logo" href="/" style="text-decoration:none;display:flex;align-items:center;gap:10px">
<svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
<circle cx="16" cy="16" r="13.5" fill="none" stroke="#c9a84c" stroke-width="2.6" stroke-dasharray="66 20" stroke-linecap="round" transform="rotate(-50 16 16)"/>
<circle cx="26.5" cy="7" r="3.1" fill="#c9a84c"/>
<circle cx="16" cy="16" r="3.4" fill="#f6f3ec"/>
</svg>
<span style="display:flex;flex-direction:column;line-height:1">
<span style="font-family:var(--disp);font-weight:900;font-size:19px;color:#fff;letter-spacing:-0.02em">AI<b style="color:var(--gold)">Leash</b></span>
<span style="font-family:var(--mono);font-size:7.5px;letter-spacing:2.5px;text-transform:uppercase;color:rgba(255,255,255,0.4);margin-top:3px">by Monop Content</span>
</span>
</a>
<div class="nvl">
<a href="#products">Products</a>
<a href="#packs">Signal Packs</a>
<a href="#oversight">Oversight</a>
<a href="#authority">Authority</a>
<a href="/savings">Savings</a>
<a href="#anchor">Anchoring</a>
<a href="#network">Network</a>
<a href="#conformance">Conformance</a>
<a href="#how">How it works</a>
<a href="#coverage">Coverage</a>
<a href="#sdk">One line</a>
<a href="#install">Install</a>
<a href="#onprem">Sebdog</a>
<a href="#law">The law</a>
<a href="/scan">Free scanner</a>
<a href="/reseller">Partners</a>
<a href="/whitepaper">Whitepaper</a>
<a href="/developers">Developers</a>
<a href="#signup" class="ncta">Get API key &middot; 90 days free</a>
</div>
</nav>

<!-- SIGNATURE: the visit ledger. Real SHA-256, runs only in this browser. -->
<aside id="rail" aria-label="Live demo: this visit as an audit chain">
<div class="rail-t">This visit, sealed</div>
<div class="rail-s">A live demo of our engine. Each section you read becomes a real SHA-256 block, chained in your browser. Nothing is sent anywhere.</div>
<div id="chain"></div>
<div class="rail-foot">tip <b id="tip">GENESIS</b></div>
</aside>
<div id="chip">Visit chain &middot; <span id="chipn">0 blocks</span> &middot; tip <span class="ch" id="chiptip">GENESIS</span></div>

<main>

<section id="hero">
<div class="wrap">
<div class="deadline rise d1">EU AI Act &middot; transparency duties live <b>2 Aug 2026</b> &middot; high-risk duties <b>2 Dec 2027</b> &middot; fines to 3% of global turnover</div>
<p class="rise d1" style="font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.45);margin-bottom:18px"><b style="color:var(--gold);font-weight:600">Monop Content</b> presents AILeash &mdash; a compliance API for platforms running AI. Governance, child safety and fraud alerts on one tamper-evident engine</p>
<h1 class="rise d2">Every AI decision.<br><i>Sealed. Provable. Yours.</i></h1>
<p class="lead rise d3" style="margin-top:26px"><b style="color:var(--gold)">The compliance layer you build on top of.</b> You put sebbi.pro underneath your app; it scores every AI decision in under 30ms &mdash; <b>ALLOW, CHALLENGE or BLOCK</b> &mdash; and seals each one into a SHA-256 chain nobody can quietly edit. Not a hacker. Not an employee. <b>Not even us</b> &mdash; the chain is timestamped through OpenTimestamps into Bitcoin, so the clock sits outside our control, and other platforms witness our chain so we cannot rebuild it either. Built to support <b>EU AI Act Articles 9, 12, 13 and 14</b>, the Online Safety Act, the ICO Children's Code and the DSA. When a regulator asks what your AI decided and why, you answer in one API call. <b>Free for 90 days. Then 50p per device. No tiers, no sales calls.</b></p>
<div class="hseal" id="hseal" aria-live="polite"></div>
<div class="vstamp" id="vstamp" style="display:none">
<svg width="34" height="34" viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="13.5" fill="none" stroke="#c9a84c" stroke-width="2.6" stroke-dasharray="66 20" stroke-linecap="round" transform="rotate(-50 16 16)"/><circle cx="26.5" cy="7" r="3.1" fill="#c9a84c"/><circle cx="16" cy="16" r="3.4" fill="#0a0f1e"/></svg>
<span><span class="vn" id="vnum"></span><span class="vl" style="display:block">Sealed visitor of sebbi.pro</span><span class="vh" id="vhash" style="display:block"></span></span>
</div>
<div class="hbtns rise d4">
<a href="#how" class="bgold">See how it works &darr;</a>
<a href="#signup" class="bghost">Get API key &middot; 90 days free</a>
<a href="/scan" class="bghost">Free AI Act scanner</a>
</div>
</div>

<div id="patrol-strip" aria-hidden="true">
<div class="patrol"><div class="patrol-flip">
<svg width="150" height="86" viewBox="0 0 150 86">
<g class="bob">
<line x1="26" y1="8" x2="26" y2="16" stroke="#c9a84c" stroke-width="2"/>
<circle cx="26" cy="6" r="2.6" fill="#c9a84c" class="blinky"/>
<rect x="15" y="15" width="22" height="17" rx="4" fill="#1c2742" stroke="#c9a84c" stroke-width="1.6"/>
<rect x="19" y="21" width="14" height="5" rx="2.5" fill="#7fe3b0" class="blinky"/>
<rect x="12" y="34" width="28" height="26" rx="5" fill="#141d36" stroke="#c9a84c" stroke-width="1.6"/>
<circle cx="26" cy="44" r="3.6" fill="none" stroke="#c9a84c" stroke-width="1.4"/>
<circle cx="26" cy="44" r="1.3" fill="#c9a84c"/>
<path d="M40 40 Q50 42 56 46" stroke="#c9a84c" stroke-width="3.4" fill="none" stroke-linecap="round"/>
<circle cx="57" cy="46.5" r="2.6" fill="#c9a84c"/>
</g>
<g class="leg"><rect x="17" y="59" width="6.5" height="17" rx="3" fill="#1c2742" stroke="#c9a84c" stroke-width="1.3"/><rect x="14.5" y="73" width="11" height="4.5" rx="2" fill="#c9a84c"/></g>
<g class="leg b"><rect x="28.5" y="59" width="6.5" height="17" rx="3" fill="#1c2742" stroke="#c9a84c" stroke-width="1.3"/><rect x="26" y="73" width="11" height="4.5" rx="2" fill="#c9a84c"/></g>
<path d="M57 47 Q78 62 100 53" stroke="#c9a84c" stroke-width="1.8" fill="none" stroke-dasharray="4 3" stroke-linecap="round"/>
<g class="bob" style="animation-delay:.2s">
<circle cx="100" cy="53" r="2.2" fill="#c9a84c"/>
<rect x="98" y="55" width="30" height="14" rx="5" fill="#141d36" stroke="#c9a84c" stroke-width="1.5"/>
<rect x="122" y="45" width="15" height="13" rx="4" fill="#1c2742" stroke="#c9a84c" stroke-width="1.5"/>
<rect x="126" y="49" width="7" height="3.4" rx="1.7" fill="#7fe3b0" class="blinky"/>
<rect x="136" y="51" width="6" height="5" rx="2" fill="#c9a84c"/>
<path d="M124 45 L121 38 L128 43 Z" fill="#c9a84c"/>
<g class="tailwag"><path d="M98 57 Q90 50 88 43" stroke="#c9a84c" stroke-width="2.6" fill="none" stroke-linecap="round"/><circle cx="88" cy="42" r="2" fill="#7fe3b0" class="blinky"/></g>
</g>
<g class="dogleg"><rect x="101" y="68" width="5" height="10" rx="2.4" fill="#1c2742" stroke="#c9a84c" stroke-width="1.2"/></g>
<g class="dogleg b"><rect x="109" y="68" width="5" height="10" rx="2.4" fill="#1c2742" stroke="#c9a84c" stroke-width="1.2"/></g>
<g class="dogleg b"><rect x="117" y="68" width="5" height="10" rx="2.4" fill="#1c2742" stroke="#c9a84c" stroke-width="1.2"/></g>
<g class="dogleg"><rect x="124" y="68" width="5" height="10" rx="2.4" fill="#1c2742" stroke="#c9a84c" stroke-width="1.2"/></g>
</svg>
</div></div>
<div class="patrol-cap">Your AI. On a lead. &mdash; Monop Content, Blyth</div>
</div>

<div class="ticker" aria-hidden="true"><div class="tk" id="tk"></div></div>
</section>

<section id="how">
<div class="wrap">
<div class="entry"><span class="no">Block 001 &middot; How it works</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>Three steps. <i>That is it.</i></h2>
<p class="lead">What normally costs &pound;50,000 a year in compliance tooling, free for 90 days and then 50p per device.</p>
<div class="steps">
<div class="st"><div class="k">Step one</div><h3>Get a free key</h3><p>Sign up below. No card, no contract. <b>Everything free for 90 days</b> &mdash; the full engine against your real traffic, plus a step-by-step installation guide straight to your inbox.</p></div>
<div class="st"><div class="k">Step two</div><h3>Send us the event</h3><p>Each time a user acts, your platform posts the details. We score it across 9 signals in <b>under 30ms</b> and return ALLOW, CHALLENGE or BLOCK &mdash; sealed into the chain before you get the reply.</p></div>
<div class="st"><div class="k">Step three</div><h3>You set the price</h3><p>Charge your users what you like. After your 90 free days, <b>we take 50p per device per month</b> &mdash; metered on the real devices that used your key. Everything above it is yours, every month.</p></div>
</div>
</div>
</section>

<section id="sdk">
<div class="wrap">
<div class="entry"><span class="no">Block 002 &middot; One line of code</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>Add one line. <i>Never think about it again.</i></h2>
<p class="lead">The slowest part of any compliance tool is wiring it in. So we removed that part. Put one line above a function and every call it makes from then on is fingerprinted and sealed &mdash; automatically, forever, with nothing else to remember.</p>

<div class="oneline">@witness()<br>def approve_loan(application):</div>

<div class="steps" style="margin-top:34px">
<div class="st"><div class="k">What leaves</div><h3>A hash. Nothing else.</h3><p>The inputs and the result are hashed <b>on your machine</b>. The hash goes out; the data does not. Not in debug mode, not in an error, not ever &mdash; there is no code in the file that could send it. It's one short file and your engineer can read the whole thing over a coffee and confirm that, which is a better answer than a promise from us.</p></div>
<div class="st"><div class="k">What it costs</div><h3>A tenth of a millisecond</h3><p>Measured, not estimated: <b>0.098ms</b> added to each call. The network part happens on a background thread, so your code never waits for us. If we go down your application doesn't slow down, doesn't error and doesn't care &mdash; records queue on your own disk and go out when we're back.</p></div>
<div class="st"><div class="k">What you get back</div><h3>A receipt, per call</h3><p>Each call gets its position in the chain and the tip it was sealed under. Hand those two values to an auditor and they can check it without asking you for anything. <b>No dependencies to install</b> &mdash; it's a single file using nothing but the Python standard library, which is the only kind of thing a bank's security team approves quickly.</p></div>
</div>

<div class="sealnote">
<h3>What a receipt proves, and what it doesn't</h3>
<p><b>It proves</b> that this exact input and this exact output existed at or before the moment they were sealed, and that neither has changed since.</p>
<p style="margin-top:10px"><b>It does not prove the decision was right.</b> Wrong answers seal exactly as cleanly as right ones. <b>It does not prove your records are complete</b> &mdash; it seals what you decorated, and it cannot know about the call you didn't. <b>It does not prove your model behaved</b>; it fingerprints what went in and what came out, not the reasoning in between.</p>
<p style="margin-top:10px">Those three sentences are in the file's own documentation, at the top, where a buyer's engineer will read them first. <b>Anyone selling you the opposite of them is selling something that does not exist.</b></p>
</div>
</div>
</section>

<section id="products">
<div class="wrap">
<div class="entry"><span class="no">Block 003 &middot; Products</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>Five products. <i>One engine.</i></h2>
<p class="lead" style="margin-bottom:14px">The same 9-signal engine and audit chain underneath all of them. Pick one or take the lot. Every one is free for your first 90 days. Four run on our infrastructure; <b>Sebdog runs on yours.</b></p>

<div class="prod">
<div class="pn">AILeash<small>AI governance</small></div>
<div>
<p class="pd"><b>Who it's for:</b> any company whose AI makes decisions about people &mdash; banks approving loans, insurers pricing policies, fintechs blocking payments, marketplaces banning accounts. <b>What it does:</b> every decision your AI makes gets scored, explained in plain English, and locked into a record that nobody can quietly change. The EU AI Act says you must keep this proof. When the regulator knocks, <b>you hand it over &mdash; block by block.</b></p>
<div class="pf"><em>&#10003;</em>9 signals scored per event, verdict in under 30ms<br><em>&#10003;</em>Tamper-evident SHA-256 chain &mdash; alterations are detectable, by anyone<br><em>&#10003;</em>Built for EU AI Act Articles 9, 12, 13 and 14<br><em>&#10003;</em>Free for 90 days, no card to start</div>
</div>
<div class="pp"><div class="amt">50p</div><div class="per">after 90 free days &middot; per device &middot; per month</div><a class="pbtn" href="#signup" onclick="setProduct('aileash')">Get AILeash key &rarr;</a></div>
</div>

<div class="prod">
<div class="pn">SonicBoom<small>Compliance layer</small></div>
<div>
<p class="pd"><b>Who it's for:</b> companies already running AI on AWS, Azure, Google Cloud, OpenAI or Anthropic who need compliance without slowing anything down. <b>What it does:</b> one line of code adds a full audit record to every AI call. Powered by our <b>Sebdog engine</b> &mdash; the same core that runs AILeash &mdash; scoring in <b>28ms</b>, so fast your users never notice it's there.</p>
<div class="pf"><em>&#10003;</em>One line of code &mdash; nothing else in your stack changes<br><em>&#10003;</em>Works alongside AWS, Azure, Google Cloud, OpenAI, Anthropic<br><em>&#10003;</em>SHA-256 audit chain on every call, automatically<br><em>&#10003;</em>28ms median decision time, measured on our own traffic</div>
</div>
<div class="pp"><div class="amt">50p</div><div class="per">after 90 free days &middot; per device &middot; per month</div><a class="pbtn" href="/sonicboom">About SonicBoom &rarr;</a></div>
</div>

<div class="prod">
<div class="pn">Sentinel<small>Fraud &amp; anomaly alerts</small></div>
<div>
<p class="pd"><b>Who it's for:</b> online shops, payment companies, marketplaces &mdash; anyone who loses money to fraud. <b>What it does:</b> watches every event on your platform. When something looks wrong &mdash; 500 messages in a minute, a login from a strange country, a pattern that smells like fraud &mdash; Sentinel <b>emails you an alert with the sealed evidence attached.</b> You catch it while it's happening, not after the money's gone.</p>
<div class="pf"><em>&#10003;</em>Real-time scoring, alerts the moment thresholds trip<br><em>&#10003;</em>Velocity signals catch burst attacks, takeovers and bots<br><em>&#10003;</em>Every alert backed by its own tamper-evident chain entry<br><em>&#10003;</em>Same one API call, same 90 free days</div>
</div>
<div class="pp"><div class="amt">50p</div><div class="per">after 90 free days &middot; per device &middot; per month</div><a class="pbtn" href="#signup" onclick="setProduct('sentinel')">Get Sentinel key &rarr;</a></div>
</div>

<div class="prod">
<div class="pn">Guardian<small>Child safety for platforms &middot; Online Safety Act</small></div>
<div>
<p class="pd"><b>Who it's for:</b> consoles, games and social apps with young users. The <b>Online Safety Act</b> makes you responsible for keeping children safe, with substantial fines if you don't. <b>What it does:</b> you get an API key and build Guardian into your own app. Your young users get a Help button and grooming-pattern flagging inside YOUR app; you get a <b>tamper-proof record proving your duty of care</b> &mdash; the exact evidence Ofcom asks for.</p>
<div class="pf"><em>&#10003;</em>Flags known grooming and manipulation patterns &mdash; never falsely tells a child a message is "safe"<br><em>&#10003;</em>Every safety event sealed to the audit chain &mdash; provable to a regulator on demand<br><em>&#10003;</em>Message content never stored, only a fingerprint &mdash; privacy by design<br><em>&#10003;</em>CEOP, Childline and 999 one tap away for every child, always</div>
<div class="guardian-note">You get the API key and build Guardian into your own app &mdash; your design, our safety engine underneath. Free for 90 days, then 50p per device. The families on your platform never pay.</div>
</div>
<div class="pp"><div class="amt">50p</div><div class="per">after 90 free days &middot; families never pay</div><a class="pbtn" href="/guardian-parent">Learn about Guardian &rarr;</a></div>
</div>

</div>

<div class="prod">
<div class="pn">Sebdog<small>The engine, on your hardware</small></div>
<div>
<p class="pd"><b>Who it's for:</b> hospitals, councils, defence suppliers, banks &mdash; anyone whose answer to &ldquo;where does our data go?&rdquo; has to be <b>nowhere.</b> <b>What it does:</b> the same engine, running inside your building on your own machine. Decisions, events and the audit chain never leave your disk. There is no phone home: the licence is checked locally with a signature, so it runs on a box with the network cable pulled out. And you can prove that with a packet capture rather than taking our word for it.</p>
<div class="pf"><em>&#10003;</em>One Python file, no dependencies to install, runs on a laptop or a rack<br><em>&#10003;</em>Zero outbound connections &mdash; verify it yourself with tcpdump<br><em>&#10003;</em>Your chain witnessed by outside operators &mdash; only a hash leaves, and only if you switch it on<br><em>&#10003;</em>Daily backups, sealed into the chain, so restoring an old one is visible</div>
</div>
<div class="pp"><div class="amt">50p</div><div class="per">after 90 free days &middot; per device &middot; per month</div><a class="pbtn" href="#onprem">How Sebdog works &rarr;</a></div>
</div>

</section>

<section id="onprem">
<div class="wrap">
<div class="entry"><span class="no">Block 004 &middot; On your own hardware</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2 style="color:#fff">The data never leaves. <i>The proof still does.</i></h2>
<p class="lead">Every compliance vendor asks you to send them your data. That is a straight trade: you get an audit trail, they get your records. For a hospital, a council or a defence supplier that trade is simply not available, so those organisations end up with nothing but a spreadsheet.</p>
<p class="lead" style="margin-top:16px"><b>Sebdog is the same engine running inside your building.</b> Your decisions, your events and your hash chain sit on your disk and never move. We cannot read them. We cannot subpoena them out of our own systems, because they were never in our systems.</p>
<p class="lead" style="margin-top:16px">Which leaves the obvious problem, and it is the one everybody skips: <b>a hash chain on your own server proves nothing against you.</b> You own the file. You own the keys. You can rebuild it forward, re-sign it and renumber it, and nobody outside can tell. An audit trail the owner can silently rewrite is a diary, not evidence.</p>

<div class="anchorgrid">
<div class="ag"><div class="k">How that gets fixed</div><h3>Somebody else holds your history</h3><p>Sebdog publishes its current chain head &mdash; 64 characters, no data in it &mdash; and independent operators fetch it <b>on their own schedule</b> and seal it into their own chains. From that moment your past sits inside records you do not control. Rewriting it would mean persuading all of them to rewrite theirs in step.</p></div>
<div class="ag"><div class="k">Why fetching matters</div><h3>You can't choose the moment</h3><p>A timestamp is something you go and get. A peer polling you is something that happens <b>whether you want it to or not</b>. That difference is the whole point: you cannot cherry-pick which of your events get covered, because a chain head commits to every block behind it.</p></div>
<div class="ag"><div class="k">What crosses the wire</div><h3>One hash, and only if you enable it</h3><p>Witnessing is off until you turn it on, and when it is on the entire payload is a hash. <b>It cannot be reversed</b> and it reveals nothing but that your chain exists and has moved. If you never enable it, Sebdog makes no outbound connection at all.</p></div>
<div class="ag"><div class="k">How you know that's true</div><h3>Read it, or watch it</h3><p>It is one file of plain Python with no dependencies. Your engineer can read every line, or run it behind a packet capture and watch it stay silent. <b>We are not asking to be trusted on this</b> &mdash; a claim you can check in an afternoon is worth more than a certification.</p></div>
</div>

<div class="anchorline">
<em>licence</em>signed by us, verified on your machine with a public key &mdash; <span class="g">works with the network unplugged</span><br>
<em>chain</em>SHA-256, every block linked to the one before it, on your disk only<br>
<em>verify</em>one call rewalks and rehashes <b>every block</b> from genesis &mdash; not a summary, the actual arithmetic<br>
<em>backups</em>daily, last seven kept, and each one sealed into the chain &mdash; <span class="g">so quietly restoring an older database shows up</span><br>
<em>witness</em>your head published for peers to seal; theirs sealed into yours. Off by default
</div>

<div class="anchorstraight">
<b>The honest limit.</b> None of this proves your decisions were correct, and none of it proves your records are complete &mdash; Sebdog seals what you send it and cannot know about what you didn't. What it removes is the ability to change the story afterwards. That is a smaller claim than the industry makes and it is the one that survives an auditor.
</div>

<div style="margin-top:26px"><a class="bgold" href="#signup" onclick="setProduct('sebdog')">Get Sebdog &middot; 90 days free &rarr;</a></div>
</div>
</section>

<section id="packs">
<div class="wrap">
<div class="entry"><span class="no">Block 005 &middot; Signal Packs</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>Nine signals as standard. <i>Then add your own.</i></h2>
<p class="lead">Every event is scored against the nine core signals below. A <b>Signal Pack</b> loads extra signals on top, tuned to one kind of risk &mdash; and the pack itself is sealed into the chain, so the rules that were running at the moment of a decision are part of the record, not a memory.</p>

<div class="corepack">
<div class="k">The core nine &mdash; always on, in every product</div>
<div class="sigs">
<span class="sig">trust</span>
<span class="sig">velocity &middot; 60s</span>
<span class="sig">velocity &middot; 5m</span>
<span class="sig">velocity &middot; 1h</span>
<span class="sig">amount</span>
<span class="sig">device risk</span>
<span class="sig">anomaly</span>
<span class="sig">country shift</span>
<span class="sig">unsafe country</span>
</div>
</div>

<div class="packrow">
<div class="packn">Payments &amp; fraud<small>Pack</small></div>
<div>
<p class="packd">For checkouts, transfers and payment platforms. Sharpens the money signals &mdash; sudden value jumps, new beneficiaries, card testing patterns and burst behaviour that a flat rule set misses. <b>Pairs with Sentinel.</b></p>
<div class="packsig"><span>value jump</span><span>new beneficiary</span><span>card testing</span><span>burst velocity</span></div>
</div>
</div>

<div class="packrow">
<div class="packn">Child safety<small>Pack</small></div>
<div>
<p class="packd">For games, consoles and social apps with young users. Adds grooming and manipulation pattern signals, age-context weighting, and contact-escalation detection. <b>Content is never stored &mdash; only a fingerprint.</b> Pairs with Guardian.</p>
<div class="packsig"><span>grooming pattern</span><span>contact escalation</span><span>age context</span><span>off-platform pull</span></div>
</div>
</div>

<div class="packrow">
<div class="packn">Lending &amp; onboarding<small>Pack</small></div>
<div>
<p class="packd">For credit, insurance and account opening &mdash; the decisions the EU AI Act treats most seriously. Adds identity-consistency and document signals, and forces a <b>CHALLENGE</b> pathway wherever a decision would materially affect a person's access to a service.</p>
<div class="packsig"><span>identity consistency</span><span>document risk</span><span>affordability shift</span><span>oversight trigger</span></div>
</div>
</div>

<div class="packrow">
<div class="packn">Marketplace integrity<small>Pack</small></div>
<div>
<p class="packd">For marketplaces and platforms managing seller and account abuse. Adds account-age, listing-behaviour and coordinated-activity signals, so bans and suspensions carry evidence rather than a support note.</p>
<div class="packsig"><span>account age</span><span>listing anomaly</span><span>coordinated activity</span><span>reinstatement history</span></div>
</div>
</div>

<div class="packrow">
<div class="packn">Build your own<small>Custom pack</small></div>
<div>
<p class="packd">Your risk is not everyone's risk. Define your own signals, set the weights and thresholds, and run them on the same deterministic engine. Same inputs give the same outputs, every time &mdash; <b>no drift, no retraining, nothing to explain away.</b></p>
<div style="margin-top:16px"><a class="pbtn" href="/signal-packs">Build a Signal Pack &rarr;</a></div>
</div>
</div>

<div class="sealnote">
<h3>The part that matters at audit</h3>
<p>Anyone can log a decision. The hard question, eighteen months later, is <b>which rules were live when that decision was made</b> &mdash; and most systems answer it with a changelog somebody could have edited.</p>
<p style="margin-top:12px">Every pack has a version hash. When a decision is sealed, the pack hash is sealed with it. Change a weight, change a threshold, add a signal, and the pack gets a new hash and a new block in the chain. <b>Rule changes become auditable events, never silent edits</b> &mdash; and any decision can be traced back to the exact rule set that produced it.</p>
<div class="ex"><em>decision</em>seal 9f3c&hellip; &middot; verdict CHALLENGE &middot; score 0.41<br><em>pack</em>payments-fraud &middot; v4 &middot; hash 7ab1&hellip;<br><em>meaning</em>this verdict, under these exact rules, at this exact time &mdash; provable by anyone</div>
</div>

</div>
</section>

<section id="margin">
<div class="wrap">
<div class="entry"><span class="no" style="color:#fff">Block 006 &middot; Your margin</span><span class="rule"></span><span class="sealed" data-seal style="color:rgba(255,255,255,0.4)"></span></div>
<h2 style="color:#fff">You set the price. <i>You keep the rest.</i></h2>
<p class="lead">Your first 90 days are free. After that we take 50p per device per month. Everything above it is yours &mdash; every month, for as long as they stay.</p>
<div class="cwrap">
<div class="crow">
<div><div class="clab">You charge per device per month</div><div class="cin"><span class="pd2">&pound;</span><input class="ci" type="number" id="charge" value="1.99" min="0.51" step="0.01" oninput="calc()" aria-label="Price you charge per device per month"></div></div>
<div><div class="clab">Number of devices</div><input class="ci" id="devices" type="number" min="1" step="1" value="1000" placeholder="Type any number, e.g. 8000000" oninput="calc()" aria-label="Number of devices"></div>
</div>
<div style="font-size:12px;color:#8a90a6;margin-top:6px">Working out what it saves you rather than what it pays you? <a href="/savings" style="color:var(--gold)">sebbi.pro/savings</a> runs the arithmetic on your own figures &mdash; ingestion, log storage, monitoring, compliance pipeline, engineering time &mdash; and says so in red if a proof layer costs you more than what you already run.<br><br>Type your exact device count. You are only ever billed for the real number of unique devices that actually use your key &mdash; not the number you type here.</div>
<div class="cres">
<div class="cr2"><div class="l">User pays</div><div class="v v-user" id="r-user">&pound;1.99</div><div class="s">per device per month</div></div>
<div class="cr2"><div class="l">You keep</div><div class="v v-you" id="r-you">&pound;1,490</div><div class="s">per month</div></div>
<div class="cr2"><div class="l">We take</div><div class="v v-we" id="r-we">&pound;500</div><div class="s">per month &middot; after trial</div></div>
</div>
</div>
</div>
</section>

<section id="referral">
<div class="wrap">
<div class="entry"><span class="no">Block 007 &middot; Referrals</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>Tell a friend. <i>Earn forever.</i></h2>
<p class="lead">Your signup comes with a referral code. Every device that signs up with it pays you 10p a month, for as long as it stays. No cap, no expiry.</p>
<div class="refrow">
<div class="rf"><h3>Get your code</h3><p>Issued the moment you sign up. It looks like REF-JOHN-1234 and it's yours permanently.</p></div>
<div class="rf"><h3>Share it anywhere</h3><p>A colleague, a dev group, a call centre. Anyone who signs up with your code is linked to you for good.</p><div class="big">10p</div><div class="bl">per device &middot; per month &middot; forever</div></div>
<div class="rf"><h3>Collect monthly</h3><p>Ten referrals running 1,000 devices each is &pound;1,000 a month &mdash; and it renews itself.</p></div>
</div>
</div>
</section>

<section id="notary-promo">
<div class="wrap">
<div class="entry"><span class="no">Block 008 &middot; Identity</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>Seal your profile <i>before someone clones it.</i></h2>
<p class="lead">AI can now copy a face, a voice and a bio in minutes. The <b>Sovereign Profile Notary</b> locks your public identity &mdash; name, bio, links &mdash; into the same tamper-evident chain that seals AI decisions, with an official timestamp. You get a short verification code for your LinkedIn bio; anyone can check it in seconds. If an impersonator changes even one letter of your profile, the check fails in public. <b>Free, takes 60 seconds, and your details never leave your browser unless you choose to publish them.</b></p>
<p class="lead" style="margin-top:18px"><b>And for businesses: the Payment Notary.</b> Invoice fraud costs UK businesses hundreds of millions a year &mdash; criminals intercept real invoices and switch the bank details. Seal your true details once, print a short code on every invoice, and every customer can verify in 10 seconds before paying. Switched details fail the check &mdash; <b>the fraud dies before the money moves.</b></p>
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:26px">
<a href="/notary" class="bgold">Seal my profile &mdash; free &rarr;</a>
<a href="/pay-check" class="bgold">Payment Notary &mdash; free &rarr;</a>
<a href="/notary" class="pbtn">Check a code &rarr;</a>
</div>
</div>
</section>

<section id="law">
<div class="wrap">
<div class="entry"><span class="no">Block 009 &middot; The law</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>What the law <i>actually requires.</i></h2>
<p class="lead">Most compliance advice tells you what the text says. This is what it means for your platform in practice &mdash; including the dates that moved.</p>

<div class="timeline">
<div class="tlrow"><div class="tld">Date</div><div class="tlw">What lands</div></div>
<div class="tlrow now"><div class="tld">2 Aug 2026</div><div class="tlw"><b>Transparency duties apply.</b> Tell people when they are dealing with an AI system. Mark AI-generated or manipulated content so a machine can read it. Disclose deepfakes to the people who see them. The Commission's enforcement powers over general-purpose models start the same day.</div></div>
<div class="tlrow"><div class="tld">2 Dec 2026</div><div class="tlw"><b>Content-marking grace period ends</b> &mdash; shortened from six months to three by the AI Omnibus. Also the date the prohibition on AI-generated non-consensual intimate imagery and CSAM takes effect.</div></div>
<div class="tlrow"><div class="tld">2 Dec 2027</div><div class="tlw"><b>High-risk duties apply to stand-alone systems</b> &mdash; Articles 9, 12, 13 and 14. Delayed from August 2026, but the evidence they require is <b>historical</b>: you cannot seal decisions you never recorded.</div></div>
<div class="tlrow"><div class="tld">2 Aug 2028</div><div class="tlw"><b>High-risk duties apply to AI embedded in products.</b></div></div>
</div>

<div class="laws">
<div class="law"><div class="act">EU AI Act 2024/1689 &middot; as amended by the AI Omnibus</div>
<div class="plain">&ldquo;If your AI makes decisions that affect people, you will need permanent, tamper-evident proof of every one.&rdquo;</div>
<p>Fines reach 3% of global annual turnover or &euro;15m &mdash; whichever is higher, per violation. The high-risk deadline moved to December 2027. The record you hand over then has to cover the years before it.</p>
<ul><li>Art. 9 &mdash; continuous risk management</li><li>Art. 12 &mdash; tamper-evident record keeping</li><li>Art. 13 &mdash; plain-language explanations</li><li>Art. 14 &mdash; human override pathway</li></ul></div>

<div class="law"><div class="act">Online Safety Act 2023 &middot; UK &middot; in force now</div>
<div class="plain">&ldquo;If users can talk to each other on your platform, you are legally responsible for protecting them &mdash; today.&rdquo;</div>
<p>Ofcom is already investigating platforms. The ICO fined TikTok &pound;12.7m for Children's Code violations.</p>
<ul><li>Documented risk assessment on demand</li><li>Moderation with an evidence trail</li><li>Age-appropriate design for child users</li><li>Ofcom-ready audit trails</li></ul></div>

<div class="law"><div class="act">ICO Children's Code &middot; UK &middot; in force now</div>
<div class="plain">&ldquo;If under-18s can reach your platform &mdash; even unintentionally &mdash; the Children's Code applies to you.&rdquo;</div>
<p>The ICO can and does act against platforms that expose children to harmful automated decisions without protection.</p>
<ul><li>Best interests of the child by default</li><li>Data minimisation for child users</li><li>No profiling of children</li><li>Human oversight of automated decisions</li></ul></div>

<div class="law"><div class="act">Digital Services Act &middot; EU 2022/2065</div>
<div class="plain">&ldquo;Show how your algorithmic systems work &mdash; and prove you've mitigated the risks they create.&rdquo;</div>
<p>Very Large Online Platforms carry the heaviest duties, but systemic risk assessment reaches smaller platforms too.</p>
<ul><li>Systemic risk assessment with evidence</li><li>Algorithmic transparency reports</li><li>Minor-protection evidence packages</li><li>Regulator-ready submissions</li></ul></div>
</div>
</div>
</section>

<section id="coverage">
<div class="wrap">
<div class="entry"><span class="no">Block 010 &middot; Coverage map</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>Article by article. <i>Feature by feature.</i></h2>
<p class="lead" style="margin-bottom:36px">The law names its requirements. Here is the exact engine feature built to answer each one &mdash; taken directly from the regulation map sealed inside the engine itself. No hand-waving: requirement on the left, mechanism on the right.</p>

<div class="covrow head"><div class="cc">Requirement</div><div class="cc">What the law <b>demands</b></div><div class="cc">How the engine <b>answers it</b></div></div>

<div class="covrow">
<div class="cc cov-art">EU AI Act &middot; Article 9<small>Risk management system</small></div>
<div class="cc cov-req">A <b>continuous, iterative risk management process</b> running across the AI system's whole lifecycle &mdash; risks identified, estimated and mitigated, not assessed once and filed away.</div>
<div class="cc cov-how"><em>&#10003;</em>Continuous per-event risk scoring &mdash; every single decision, not a quarterly review<br><em>&#10003;</em>9 weighted core signals, plus any Signal Pack you load on top<br><em>&#10003;</em>Fully deterministic &mdash; identical inputs give identical outputs, forever</div>
</div>

<div class="covrow">
<div class="cc cov-art">EU AI Act &middot; Article 12<small>Record keeping &amp; logging</small></div>
<div class="cc cov-req">Automatic recording of events over the system's lifetime, with logs that ensure a level of <b>traceability appropriate to the system's risk</b> &mdash; records a regulator can rely on.</div>
<div class="cc cov-how"><em>&#10003;</em>Every decision sealed into a SHA-256 hash chain at the moment it's made<br><em>&#10003;</em>Gapless per-key receipt sequence &mdash; a missing record is mathematically provable, not arguable<br><em>&#10003;</em>Public verification endpoint &mdash; anyone can re-check the whole chain, any time</div>
</div>

<div class="covrow">
<div class="cc cov-art">EU AI Act &middot; Article 13<small>Transparency</small></div>
<div class="cc cov-req">AI systems must be <b>sufficiently transparent</b> that the people deploying them can interpret the output and use it appropriately &mdash; no black-box verdicts.</div>
<div class="cc cov-how"><em>&#10003;</em>Plain-language reason codes on every decision &mdash; velocity_spike, high_amount, country_shift, low_trust<br><em>&#10003;</em>Determinism proved by public challenge, not by a published listing &mdash; send any inputs, keep the fingerprint, send them again next year; the verdict must not move under an unchanged code fingerprint<br><em>&#10003;</em>Score, verdict, reasons and active pack version returned together in the same reply</div>
</div>

<div class="covrow">
<div class="cc cov-art">EU AI Act &middot; Article 14<small>Human oversight</small></div>
<div class="cc cov-req">High-risk AI must be designed so that <b>natural persons can effectively oversee it</b> &mdash; able to intervene, override or interrupt the system's decisions.</div>
<div class="cc cov-how"><em>&#10003;</em>The CHALLENGE verdict &mdash; a built-in pathway that stops the action and asks a human<br><em>&#10003;</em><b>Commit-before-reveal</b> &mdash; the reviewer's own call is sealed before the machine's verdict is shown to them<br><em>&#10003;</em>Dwell time and divergence rate recorded per reviewer &mdash; rubber stamping becomes visible in the data<br><em>&#10003;</em>BLOCK verdicts trigger a real-time email alert with the sealed evidence attached</div>
</div>

<div class="covrow">
<div class="cc cov-art">Online Safety Act 2023<small>UK &middot; in force</small></div>
<div class="cc cov-req">Platforms where users interact carry a <b>duty of care</b> &mdash; illegal-content risk assessments, protections for children, and evidence of moderation Ofcom can inspect.</div>
<div class="cc cov-how"><em>&#10003;</em>Guardian flags known grooming and manipulation patterns in real time<br><em>&#10003;</em>Every safety event sealed to the chain &mdash; a moderation evidence trail, not a policy PDF<br><em>&#10003;</em>CEOP, Childline and 999 one tap away for every child, always</div>
</div>

<div class="covrow">
<div class="cc cov-art">ICO Children's Code<small>UK &middot; in force</small></div>
<div class="cc cov-req">Services likely to be accessed by under-18s must put the <b>child's best interests first</b>: data minimisation, no profiling of children, human oversight of automated decisions.</div>
<div class="cc cov-how"><em>&#10003;</em>Deterministic scoring &mdash; no behavioural profiling of children, ever<br><em>&#10003;</em>Message content never stored &mdash; only a fingerprint; privacy by design<br><em>&#10003;</em>Full audit trail of every automated decision touching a young user</div>
</div>

<div class="covrow">
<div class="cc cov-art">Digital Services Act<small>EU 2022/2065</small></div>
<div class="cc cov-req">Platforms must <b>assess and mitigate systemic risks</b> created by their algorithmic systems &mdash; and show the evidence, not just describe the intention.</div>
<div class="cc cov-how"><em>&#10003;</em>Sealed, per-decision evidence of how algorithmic systems actually behaved<br><em>&#10003;</em>Chain records ready to attach to a systemic risk assessment or transparency report<br><em>&#10003;</em>Verifiable by the regulator directly &mdash; not just by you</div>
</div>

<div class="cov-note"><b>One more thing the engine does that most don't:</b> the regulation map above is itself sealed into the audit chain, alongside the version hash of every Signal Pack in use. Whenever coverage is updated to match new guidance, that change becomes a sealed, timestamped block &mdash; regulatory updates are auditable events, never silent edits. And to be straight with you: this table is a design mapping of engine features to legal obligations, built to support these requirements &mdash; it is not a certification, because no software alone can be one. Your lawyers stay in the loop; our chain gives them the evidence.</div>
</div>
</section>

<section id="oversight">
<div class="wrap">
<div class="entry"><span class="no">Block 011 &middot; Human oversight</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>Nobody can prove a person <i>thought about it.</i></h2>
<p class="lead">We will say the thing the rest of this market avoids. <b>You cannot prove genuine human oversight happened.</b> Thinking is an internal state and no amount of logging reaches it. Any vendor telling you they have solved that is selling you something that does not exist.</p>
<p class="lead" style="margin-top:16px"><b>But rubber stamping is not an internal state.</b> It is a pattern &mdash; and patterns leave marks, if you record the right things in the right order at the time. That part is solvable, and this is how.</p>

<div class="steps" style="margin-top:40px">
<div class="st"><div class="k">One &middot; Order</div><h3>Commit before reveal</h3><p>The case goes to the reviewer <b>without the machine's verdict</b>. Their own call and their reasoning are sealed first. Only then is the verdict revealed. Two blocks, in that order, in a chain that cannot be reordered &mdash; so nobody can have simply agreed with an answer they had already seen.</p></div>
<div class="st"><div class="k">Two &middot; Attention</div><h3>The clock is on the record</h3><p>The gap between opening a case and committing to it is sealed with the decision. A <b>0.8 second approval</b> sits in the record permanently, next to a two minute one. Not proof of thought &mdash; but four hundred sub-second calls is not something anyone explains away.</p></div>
<div class="st"><div class="k">Three &middot; Independence</div><h3>Divergence is measurable</h3><p>A reviewer who has <b>never once disagreed</b> with the machine is visible in the data. One who diverges sometimes is demonstrably exercising judgement. Agreement rate, median dwell and the proportion of sub-two-second calls, per reviewer, all sealed.</p></div>
</div>

<div class="sealnote" style="margin-top:34px">
<h3>What an auditor actually gets</h3>
<p>Not an assertion that oversight happened. <b>A dataset they can test</b> &mdash; and one a rubber stamper cannot hide inside. The reviewer's judgement, sealed before the answer was known. The time they took. How often they diverged. All of it in the same chain as the decision itself, anchored outside our reach.</p>
<div class="ex"><em>opened</em>case OVS-3A05 &middot; material sha256 7e63&hellip; &middot; verdict withheld<br><em>committed</em>reviewer CHALLENGE &middot; dwell 74.2s &middot; reasoning sealed<br><em>revealed</em>machine said BLOCK &middot; reviewer diverged<br><em>meaning</em>this person decided before they knew &mdash; provable by the order of the blocks</div>
<p style="margin-top:14px"><b>And the honest limit, because you will find it anyway:</b> a reviewer can leave a screen open, and dwell time is gameable by anyone deliberately gaming it. If a platform shows its own staff the verdict before calling us, the ordering guarantee is worth nothing. That constraint is documented in the code, not buried &mdash; the guarantee is only ever as good as the integration honouring it.</p>
</div>
</div>
</section>

<section id="anchor">
<div class="wrap">
<div class="entry"><span class="no" style="color:#fff">Block 012 &middot; The outside clock</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2 style="color:#fff">Pinned from both sides. <i>Before and after the fact.</i></h2>
<p class="lead">A hash chain proves nothing was altered after the fact. On its own it does not prove <b>when</b> the chain was built &mdash; because in principle whoever runs the system could rebuild the whole thing and date it however they liked. Every vendor promising you an immutable audit trail has this hole in it. Most don't mention it.</p>
<p class="lead" style="margin-top:16px"><b>So we moved the clock outside our own building.</b> At regular intervals the current tip of the chain is submitted to <b>OpenTimestamps</b>, which aggregates it with thousands of unrelated timestamps into a single Merkle root and commits that root to the <b>Bitcoin blockchain</b>. Several independent calendar servers do this in parallel, so no single one of them can fail, disappear or lie without the others contradicting it. From that moment the timestamp is not ours to move, not ours to re-issue, and not ours to quietly correct. Rewriting a sealed record would mean rewriting Bitcoin.</p>
<p class="lead" style="margin-top:16px"><b>Said precisely, because a reviewer found us saying it loosely.</b> Anchoring is a property of an individual proof, not of the chain. Submitting a tip to OpenTimestamps is not the same as that proof being confirmed in a Bitcoin block &mdash; confirmation takes hours, and until it lands the proof is <b>pending</b>. So a tip is either covered by a confirmed proof or it is not, and we will not describe the chain as anchored while a proof covering it is still waiting.</p>
<p class="lead" style="margin-top:16px"><b>Check the real state at <a href="/x/ots/status" style="color:var(--gold)">/x/ots/status</a></b> &mdash; it lists every proof, which are confirmed and which are pending, and returns the raw .ots file so you can verify it against Bitcoin without us. We publish that route because it is the one that can show us waiting.</p>

<div class="anchorgrid">
<div class="ag"><div class="k">What it proves</div><h3>This record existed, then</h3><p>Once a proof confirms, the chain state it covers is fixed in a public ledger you can check without asking us for anything. <b>Existence and integrity, evidenced by a third party</b> &mdash; not asserted by the vendor who produced the record. Before it confirms, the proof is pending and says so.</p></div>
<div class="ag"><div class="k">Why it matters at audit</div><h3>Backdating stops being possible</h3><p>The usual challenge to any audit trail is "you could have written this last week." An anchored chain answers it with arithmetic instead of an assurance. <b>The regulator verifies it themselves.</b></p></div>
<div class="ag"><div class="k">What you do</div><h3>Nothing to set up</h3><p>Tips are submitted for anchoring automatically, underneath every product. No wallet, no crypto, no tokens, no volatility, <b>nothing for you to hold or buy</b> &mdash; Bitcoin is used purely as a clock nobody owns. You never touch it.</p></div>
<div class="ag"><div class="k">What you get</div><h3>A reference anyone can check</h3><p>Each anchor returns the chain tip it sealed and the transaction that carries it. Hand those two values to an auditor, a court or a customer and <b>they can verify it without your help.</b></p></div>
</div>

<div class="anchorline">
<em>tip</em>the live chain state at the moment of anchoring<br>
<em>stamp</em>submitted to OpenTimestamps &middot; aggregated into a Merkle root &middot; root committed to Bitcoin &mdash; hours, not seconds<br>
<em>calendars</em>several independent servers stamp it &mdash; the count is returned with every anchor<br>
<em>check</em><span class="g">/api/anchor-status</span> &mdash; live, no key needed, no permission needed<br>
<em>state</em>a proof is <b>pending</b> until it lands in a block, then <span class="g">confirmed</span>. Both states are published. Pending is not hidden<br>
<em>result</em>once confirmed, that record cannot have been created later than that block. <span class="g">Verifiable by anyone, forever, without us.</span>
</div>

<div class="anchorstraight">
<b>Straight with you, because someone will ask:</b> no record verifies the truth of its own inputs &mdash; not a ledger, not a court transcript, not a bank's books. That is what recording is, and any vendor claiming to have solved it is selling something that does not exist. What <i>can</i> be proved is the decision itself, from both sides. <b>Before:</b> the input is sealed at the moment of capture, so it cannot be swapped afterwards to justify the verdict. <b>After:</b> the scoring is deterministic and the pack version is sealed alongside it, so anyone can re-run that input and get the identical verdict &mdash; it cannot be re-explained later either. The only thing outside the seal is whether the world matched the data at the instant it was captured. Everything after that instant is arithmetic, <b>and the story cannot be corrected in hindsight.</b>
</div>
</div>
</section>

<section id="network">
<div class="wrap">
<div class="entry"><span class="no">Block 013 &middot; The witness network</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>One chain can be rebuilt. <i>Ten cannot.</i></h2>
<p class="lead">A confirmed anchor stops us backdating anything older than it. Good &mdash; and still not the end of it. <b>So platforms witness each other.</b></p>
<p class="lead" style="margin-top:16px"><b>This is running, not planned.</b> Four chains are live and exchanging tips right now, one of them unattended and hourly since the first of August with several hundred observations behind it. The list is public and machine-readable at <a href="/x/roster/list" style="color:var(--gold)">/x/roster/list</a> &mdash; no key, no account, no permission. Peers run a single file on a cron line; there is nothing to install and no code of ours inside their stack.</p>
<p class="lead" style="margin-top:16px">Each platform periodically hands its current chain tip to its peers, and each peer seals that tip into <b>its own chain</b>. From that moment your history sits inside chains you do not control &mdash; chains that are themselves anchored externally. To rewrite your own past you would now need every peer who witnessed you to rewrite theirs in step and re-anchor all of it. That stops being a technical exercise and becomes a conspiracy, <b>and it gets harder with every platform that joins.</b></p>

<div class="anchorgrid" style="background:var(--line);border-color:var(--line)">
<div class="ag" style="background:#fbf9f4"><div class="k" style="color:var(--mutep)">What it takes</div><h3 style="color:var(--ink)">One request an hour</h3><p style="color:var(--mutep)">A chain tip is 64 characters. Recording one is a single sealed block. Ten platforms exchanging tips every hour is a few hundred blocks a day <b style="color:var(--ink)">between all of them.</b> The engineering was never the hard part.</p></div>
<div class="ag" style="background:#fbf9f4"><div class="k" style="color:var(--mutep)">Who runs it</div><h3 style="color:var(--ink)">No single authority</h3><p style="color:var(--mutep)">Every platform keeps its own product, its own customers and its own pricing. No participant is the arbiter, <b style="color:var(--ink)">including us</b> &mdash; which is the only reason the record means anything. You cannot buy an integrity property, you can only participate in one.</p></div>
<div class="ag" style="background:#fbf9f4"><div class="k" style="color:var(--mutep)">Who can check</div><h3 style="color:var(--ink)">Anyone</h3><p style="color:var(--mutep)">Ask whether we witnessed a given tip, and when, and you get a straight answer with the block it was sealed in. <b style="color:var(--ink)">The network is queryable by third parties</b>, not just described in marketing.</p></div>
<div class="ag" style="background:#fbf9f4"><div class="k" style="color:var(--mutep)">Who goes quiet</div><h3 style="color:var(--ink)">Visibly</h3><p style="color:var(--mutep)">Peers who stop publishing show as current, then stale, then silent. Those words measure <b style="color:var(--ink)">time since we last saw them and nothing else</b> &mdash; they are not a claim about anyone's uptime, and a peer who pushes manually will read silent while working perfectly.</p></div>
</div>


<h3 style="font-family:var(--disp);font-weight:900;font-size:26px;margin-top:44px;letter-spacing:-0.015em">Three ways to submit. <i style="font-style:italic;color:var(--gold)">Each says a different thing.</i></h3>
<p class="lead" style="margin-top:10px">A peer chooses the lane. Every lane is free, and the record says which one was used, so nobody's submission is described as stronger than it was.</p>

<div class="lanes">
<div class="lane"><div class="k">Lane one &middot; Open</div><h3>Anyone can submit</h3><p>No account, no key. Hand us a name and a tip and it is sealed. Deliberately open, because a verification network with a signup form is a customer list. <b>Everything submitted is sealed, including nonsense</b>, because the record is of what arrived.</p><span class="no">Does not prove who sent it</span></div>
<div class="lane"><div class="k">Lane two &middot; Shared secret</div><h3>Bound to a secret</h3><p>An HMAC signature over the submission, using a secret both sides hold. <b>Stated exactly, because a reviewer asked us to:</b> this closes third-party submission under your name. It does <b>not</b> close submission by us under your name, because we hold the same secret.</p><span class="no">Does not exclude the operator</span></div>
<div class="lane"><div class="k">Lane three &middot; Your own key</div><h3>Bound to a key we don't have</h3><p>You generate an Ed25519 keypair and keep the private half. <b>We store only the public half</b>, so we can check your signature and can never produce one. Rotation has to be signed by the key it replaces, so we cannot swap your key either.</p><span class="yes">Excludes us. Arithmetic, not a promise</span></div>
</div>

<div class="cov-note" style="margin-top:24px"><b>Why lane three exists:</b> two independent reviewers arrived at the same gap in the same week &mdash; a shared secret cannot exclude the party holding it. The fix isn't a policy or a pledge, it's a key we mathematically do not have. It's public at <span style="font-family:var(--mono)">/x/signed/spec</span>, and the verification route is open to anyone, because <b>a verification lane only account holders can check is not a verification lane.</b></div>

<div class="sealnote" style="margin-top:34px">
<h3>Five founding seats. Four taken.</h3>
<p><b>Joining is free and stays free, at any seat, forever.</b> Witnessing is free. Every public verification route is free. The protocol code does not check whether anyone has paid, and it never will &mdash; an integrity property you can be cut off from is not one.</p>
<p style="margin-top:12px">The first five chains are the founding cohort: <b>a say in the specification</b> the rest of the market ends up adopting, and an equal share of whatever the network ever earns. Four seats are filled. The fifth is open and being held for the right chain rather than the next one available.</p>
<p style="margin-top:12px">Chain six onward joins free and is witnessed free, with no founding terms &mdash; the spec will already be written by then. <b>Five is not a marketing number.</b> It is how many integrations one person can support properly while getting this right.</p>
<p style="margin-top:12px"><b>The honest limits, stated up front:</b> witnessing proves a tip existed at a time &mdash; it says nothing about whether the records behind it are true. Two platforms witnessing only each other prove very little; the strength comes from breadth, and a thin network is reported as thin. Nobody can be forced to keep publishing, and no design fixes that. Being listed on the roster is not partnership, endorsement or validation &mdash; it means a party submitted a tip. Those are properties of the design, not flaws we are hiding.</p>
<div style="margin-top:20px"><a class="pbtn" href="/contact">Ask about the fifth seat &rarr;</a></div>
</div>
</div>
</section>

<section id="notaries">
<div class="wrap">
<div class="entry"><span class="no">Block 014 &middot; The notaries</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>Sealing the things <i>that get argued about.</i></h2>
<p class="lead">The engine seals decisions. These seal the processes around them &mdash; the parts that turn into a dispute eighteen months later, when everyone's memory has conveniently improved. Each one writes into the <b>same chain</b>, so the same verification and the same anchor cover all of it.</p>

<div class="prod" style="border-top:none">
<div class="pn">Data subject requests<small>Notary</small></div>
<div>
<p class="pd">Someone asks you to delete their data. Three things must be provable later: <b>that you received it, that you actually considered it, and that you answered inside the legal deadline.</b> Almost nobody can prove any of it &mdash; they have an email thread. This seals the whole lifecycle: received, assessed with the reasoning, extended, completed. The calendar-month deadline is fixed at receipt, and an extension is its own sealed block, so it cannot be applied retrospectively to cover a missed date.</p>
<div class="pf"><em>&#10003;</em>The chain never holds the person's identity &mdash; the identifier is fingerprinted on arrival<br><em>&#10003;</em>Which answers the obvious objection: an append-only chain does not conflict with the right to erasure<br><em>&#10003;</em>The personal data is deleted in your systems as normal; what remains is a seal resolving to nothing<br><em>&#10003;</em>Overdue requests are one call away, not a spreadsheet nobody opened</div>
</div>
<div class="pp"><div class="amt">&#8212;</div><div class="per">included &middot; every plan</div></div>
</div>

<div class="prod">
<div class="pn">Reconciliation<small>Notary</small></div>
<div>
<p class="pd">A sealed chain proves records were not altered afterwards. It does <b>not</b> prove they were true when written &mdash; and an operator who seals fiction on time has a tamper-evident chain of fiction. Everyone honest knows this. Almost nobody says it. So we do what auditors actually do: take the sealed claim, go to the operator's own live system, and check whether the two agree.</p>
<div class="pf"><em>&#10003;</em>The sample is chosen from the live chain tip &mdash; unpredictable in advance, unchangeable afterwards<br><em>&#10003;</em>The selection is sealed <b>before</b> any data is requested, so the flattering records cannot be cherry-picked<br><em>&#10003;</em>Mismatches are sealed exactly as permanently as matches<br><em>&#10003;</em>A run that was planned and never submitted stays visible forever as an abandoned test</div>
</div>
<div class="pp"><div class="amt">&#8212;</div><div class="per">included &middot; every plan</div></div>
</div>

<div class="prod">
<div class="pn">Declarations<small>Notary</small></div>
<div>
<p class="pd">You publish a file saying what must always be true of your decisions &mdash; <b>"payments over &pound;10,000 are never auto-approved", "every decision carries reasons"</b> &mdash; and every record is tested against it. The obvious objection is that you wrote your own rules. Two things answer it: <b>the rules are sealed before the records they judge</b>, so a standard cannot be retrofitted to an outcome; and every version is kept, so loosening your own standard becomes a dated, permanent, public act instead of a quiet edit.</p>
<div class="pf"><em>&#10003;</em>Declaration hashed, versioned and sealed on publication<br><em>&#10003;</em>Violations of your own published rules sealed with the same permanence as passes<br><em>&#10003;</em>Full version history &mdash; the March standard stays readable in September<br><em>&#10003;</em>Weak rules prove weak things, which is exactly why the declaration itself is published</div>
</div>
<div class="pp"><div class="amt">&#8212;</div><div class="per">included &middot; every plan</div></div>
</div>

<div class="cov-note" style="margin-top:30px"><b>Why these sit on one engine and not four products:</b> every notary writes into the same chain as the decisions themselves. One verification endpoint covers all of it. One anchor covers all of it. Add a capability and it inherits the integrity properties of everything already there &mdash; <b>no separate log to reconcile, no second thing to trust.</b></div>
</div>
</section>

<section id="evidence">
<div class="wrap">
<div class="entry"><span class="no">Block 015 &middot; The evidence pack</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>The thing you actually <i>hand to the auditor.</i></h2>
<p class="lead">Everything above produces a chain. A chain is not a deliverable. When a regulator, an insurer, a court or an enterprise customer asks you to prove it, you need <b>one file you can send them</b> &mdash; and it has to survive being read by someone whose job is to find the hole in it.</p>
<p class="lead" style="margin-top:16px">So the pack does not summarise the chain. <b>It re-verifies it.</b> Every block is rewalked and rehashed from genesis at the moment the pack is built. A report tells you what a system claims about itself; this recomputes the arithmetic and fails loudly if it doesn't come out. Those are not the same product, and only one of them is worth anything in a dispute.</p>

<div style="margin-top:38px">
<div class="packrow"><div class="t">Re-verified</div><div class="b">Every block rehashed and relinked from the first one. <b>Not a count, not a status field</b> &mdash; the actual chain arithmetic, run again, in front of you.</div></div>
<div class="packrow"><div class="t">Gapless</div><div class="b">Each key's records carry a sequence number issued at the moment of sealing, and the pack checks that sequence is <b>unbroken</b>. Tampering is one problem; quietly not recording something is the other one, and it is the one nobody else checks. A missing number is a missing record, and it cannot be hidden by deleting the block.</div></div>
<div class="packrow"><div class="t">Witnessed</div><div class="b">A snapshot of who was watching &mdash; which independent operators had sealed your chain head, and when they last did it. <b>Internal integrity is the easy half.</b> This is the half that shows somebody outside your building was holding your history.</div></div>
<div class="packrow"><div class="t">Self-sealing</div><div class="b">The pack hashes itself and seals that digest back into the chain. So the document you hand over is <b>itself in the record</b> &mdash; you cannot produce a flattering pack, send it, and later deny producing it.</div></div>
<div class="packrow"><div class="t">Unbroken since</div><div class="b">A date the chain has been continuously verifiable from. It costs nothing to start and it <b>compounds every day you keep going</b>. Two years of it is not something a competitor can buy, build or catch up on.</div></div>
<div class="packrow"><div class="t">Stated limits</div><div class="b">The pack carries its own list of what it does <b>not</b> prove, printed inside the document rather than in our marketing. An auditor who finds the caveats already written down stops looking for the ones you hid.</div></div>
</div>

<div style="margin-top:34px;display:flex;gap:12px;flex-wrap:wrap">
<a class="bgold" href="/pack">Build your evidence pack &rarr;</a>
<a class="bghost" href="/x/pack/spec">Read the spec &rarr;</a>
</div>

<div class="anchorstraight">
<b>Why this is the part that gets bought.</b> Nobody purchases a hash chain. They purchase the twenty minutes on a Friday when the request lands and the answer is a file rather than a fortnight. Everything else on this page exists to make that file worth reading.
</div>
</div>
</section>

<section id="conformance">
<div class="wrap">
<div class="entry"><span class="no">Block 016 &middot; Conformance</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>The instrument that would <i>catch us failing.</i></h2>
<p class="lead">Three things on this page have a soft edge, and we would rather name them than wait for you to find them. <b>Oversight sealing only works if the platform using it doesn't show reviewers the verdict early. Witnessing only means something with breadth. A declaration is only as strong as the rules in it.</b></p>
<p class="lead" style="margin-top:16px">None of those can be fixed by arithmetic. All three can be <b>measured</b> &mdash; and a weakness somebody is measuring is a very different thing from one nobody is.</p>

<div class="steps" style="margin-top:40px">
<div class="st"><div class="k">One &middot; Probes</div><h3>A case with a known answer</h3><p>A probe is a real case with the machine's verdict <b>deliberately set wrong</b>. The reviewer cannot tell it apart from any other. Agree with it and you didn't evaluate it. And if someone's probe agreement matches their normal agreement, that is consistent with the verdict being visible before they committed &mdash; which is how you test an integration you cannot see inside.</p></div>
<div class="st"><div class="k">Two &middot; Breadth</div><h3>Thin networks say so</h3><p>Fewer than three live peers reports as <b>weak</b>. A single peer carries an explicit warning that two parties witnessing only each other can still collude. It doesn't stop a thin network &mdash; it stops one being presented as a thick one.</p></div>
<div class="st"><div class="k">Three &middot; Strength</div><h3>Rules that never fire</h3><p>Every rule is run against real records and reported on individually. One that has never constrained a single record is named in the output as <b>decoration, not a standard.</b> You can still publish a weak declaration. You can't publish one quietly.</p></div>
</div>

<div class="sealnote" style="margin-top:34px">
<h3>Why build the thing that could embarrass us</h3>
<p>Because "trust our design" is what everyone else says, and it is worth nothing. <b>An evidence layer that cannot detect its own failure modes is just a nicer-looking promise.</b> Ours reports a rubber stamper who caught none of eight deliberately wrong verdicts. It reports our own rules when they constrain nothing. It reports our witness network as weak when it is.</p>
<p style="margin-top:12px">The probe method is not ours &mdash; it comes from a point <b>James Stokes of Red Flag AI Pro</b> made publicly about slipping a known error into a review queue and seeing who catches it. It was the right idea and it is credited in our whitepaper.</p>
<p style="margin-top:12px"><b>And its own limits:</b> a probe tests a process, not a person &mdash; someone can catch one and rubber stamp the next hundred. An operator who works out which cases are probes controls their own screens. None of this is enforcement. It makes the alternative visible, which is the most an evidence layer can honestly claim to do.</p>
</div>
</div>
</section>

<section id="verify">
<div class="wrap">
<div class="entry"><span class="no" style="color:#fff">Block 017 &middot; The Proving Ground</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2 style="color:#fff">Don't take any of it <i>on trust.</i></h2>
<p class="lead">Everything above this line is a claim. Below it is the live engine &mdash; no account, no email, no key. Send it a case and it scores it, seals it into the production chain, tells you exactly what would have changed the answer, and hands you the block number so you can check the lot yourself at endpoints that have never heard of you.</p>

<div class="pgtabs">
<button class="pgtab on" id="pgt-run" onclick="pgTab('run')">1 &middot; Run a decision</button>
<button class="pgtab" id="pgt-rev" onclick="pgTab('rev')">2 &middot; Take the review yourself</button>
</div>

<!-- ============ 1. RUN A DECISION ============ -->
<div class="pgpanel" id="pgp-run">
  <div class="pgform">
    <div class="pgf">
      <label for="pg-trust">Trust history <span class="pgv" id="pg-trust-v">0.28</span></label>
      <input type="range" id="pg-trust" min="0" max="1" step="0.01" value="0.28" oninput="pgSync()">
      <span class="pghint">How this user has behaved before. 1.00 is spotless.</span>
    </div>
    <div class="pgf">
      <label for="pg-amount">Amount <span class="pgv">&pound;<span id="pg-amount-v">4200</span></span></label>
      <input type="range" id="pg-amount" min="0" max="10000" step="50" value="4200" oninput="pgSync()">
      <span class="pghint">Log-scaled, so the first pound counts far more than the ten-thousandth.</span>
    </div>
    <div class="pgf">
      <label for="pg-v60">Actions in the last 60 seconds <span class="pgv" id="pg-v60-v">14</span></label>
      <input type="range" id="pg-v60" min="0" max="40" step="1" value="14" oninput="pgSync()">
      <span class="pghint">Bursts are what automated attacks look like.</span>
    </div>
    <div class="pgf">
      <label for="pg-v5m">Actions in the last 5 minutes <span class="pgv" id="pg-v5m-v">22</span></label>
      <input type="range" id="pg-v5m" min="0" max="100" step="1" value="22" oninput="pgSync()">
      <span class="pghint">Independent of the others. Move one thing at a time and the counterfactual is exact.</span>
    </div>
    <div class="pgf">
      <label for="pg-v1h">Actions in the last hour <span class="pgv" id="pg-v1h-v">60</span></label>
      <input type="range" id="pg-v1h" min="0" max="400" step="5" value="60" oninput="pgSync()">
      <span class="pghint">The slowest window, and the least weighted.</span>
    </div>
    <div class="pgf">
      <label for="pg-dev">Device risk <span class="pgv" id="pg-dev-v">0.35</span></label>
      <input type="range" id="pg-dev" min="0" max="1" step="0.01" value="0.35" oninput="pgSync()">
      <span class="pghint">Your own device signal, if you have one. Zero if not.</span>
    </div>
    <div class="pgf">
      <label for="pg-anom">Behavioural anomaly <span class="pgv" id="pg-anom-v">0.40</span></label>
      <input type="range" id="pg-anom" min="0" max="1" step="0.01" value="0.40" oninput="pgSync()">
      <span class="pghint">Your own anomaly signal. Zero if not.</span>
    </div>
    <div class="pgf">
      <label for="pg-country">Country</label>
      <select id="pg-country" onchange="pgSync()">
        <option>UK</option><option>US</option><option>DE</option><option>FR</option>
        <option>IE</option><option>NL</option><option>SE</option>
        <option value="XX">Somewhere off the safe list</option>
      </select>
      <label class="pgcheck"><input type="checkbox" id="pg-shift" checked> Country changed since their last action</label>
    </div>
  </div>

  <div class="pgactions">
    <button class="bgold" id="pg-run-btn" onclick="pgRun()">Run it through the live engine &rarr;</button>
    <span class="pgnote">Real engine. Real chain. Nothing about you is recorded.</span>
  </div>

  <div id="pg-result" class="pgresult" aria-live="polite"></div>
</div>

<!-- ============ 2. TAKE THE REVIEW ============ -->
<div class="pgpanel hide" id="pgp-rev">
  <p class="pglead">Article 14 says a human must be able to oversee the machine. Everyone claims it. Almost nobody can show the difference between a reviewer who decided and one who agreed with an answer already on their screen.</p>
  <p class="pglead"><b>So here is the case without the answer.</b> Your verdict gets sealed first. Ours is revealed after. The chain fixes that order permanently &mdash; and the clock is running.</p>

  <div class="pgactions" id="pg-rev-start">
    <button class="bgold" onclick="pgReview()">Give me a case &rarr;</button>
    <span class="pgnote">You commit once. That is rather the point.</span>
  </div>

  <div id="pg-case" class="pgcase hide">
    <div class="pgclockbar">
      <span class="pgclocklbl">Time on this case</span>
      <span class="pgclock" id="pg-clock">0.0s</span>
    </div>
    <div id="pg-material" class="pgmaterial"></div>
    <div class="pgverdicts">
      <button class="pgvbtn allow" onclick="pgCommit('allow')">Allow it</button>
      <button class="pgvbtn chal" onclick="pgCommit('challenge')">Send to a human</button>
      <button class="pgvbtn block" onclick="pgCommit('block')">Block it</button>
    </div>
    <p class="pgnote" style="text-align:center;margin-top:14px">The engine has already decided. You will not see it until you have.</p>
  </div>

  <div id="pg-rev-result" class="pgresult" aria-live="polite"></div>
</div>

<div class="pgcharts" id="pg-charts">
  <div class="pgchead">
    <span class="pgclbl2">Live figures</span>
    <span class="pgcsub" id="pgc-gen">loading&hellip;</span>
  </div>
  <div class="pgcgrid">
    <div class="pgcard">
      <div class="pgctitle">Chain growth <span id="pgc-h">&mdash;</span></div>
      <div class="pgcbody"><svg id="pgc-chain" viewBox="0 0 300 90" preserveAspectRatio="none" role="img" aria-label="Blocks sealed per hour over the last 24 hours"></svg></div>
      <div class="pgcfoot">Blocks sealed per hour, last 24 hours. Every source, one sequence.</div>
    </div>
    <div class="pgcard">
      <div class="pgctitle">Where decisions land <span id="pgc-n">&mdash;</span></div>
      <div class="pgcbody"><svg id="pgc-hist" viewBox="0 0 300 90" preserveAspectRatio="none" role="img" aria-label="Distribution of decision scores with thresholds marked"></svg></div>
      <div class="pgcfoot">Public scores across the range. The two lines are 0.35 and 0.70 &mdash; not chosen after the fact.</div>
    </div>
    <div class="pgcard">
      <div class="pgctitle">How long reviewers took <span id="pgc-r">&mdash;</span></div>
      <div class="pgcbody"><svg id="pgc-dwell" viewBox="0 0 300 90" preserveAspectRatio="none" role="img" aria-label="Distribution of reviewer dwell times"></svg></div>
      <div class="pgcfoot" id="pgc-dwellfoot">Time between seeing a case and committing to a verdict.</div>
    </div>
  </div>
</div>

<p class="pgfoot">Every case run here becomes a genuine block in the production chain, covered by the same external timestamp as every customer decision. Public endpoints are rate limited, and the arithmetic is published in the <a href="/whitepaper">whitepaper</a> if you would rather check it than run it.</p>

<div class="pgcharts" style="margin-top:44px">
<div class="pgchead">
  <span class="pgclbl2">The ordering test &mdash; ten claims, published about ourselves</span>
  <span class="pgcsub">every one of these is open, unauthenticated, and testable right now</span>
</div>

<p class="pglead" style="margin:0 auto 20px">We publish a conformance document listing ten checks, each carrying <b>two separate flags</b>: we built this, and &mdash; separately &mdash; you can verify it without an account. Those are different claims, and most of this market blurs them into one. Then we run a checker against our own document that refuses to mark generously: <b>reachable is not verified.</b></p>

<div class="anchorline" style="margin-top:0">
<em>the document</em><a href="/.well-known/ordering-test.json" class="g" style="color:#7fe3b0;text-decoration:none">/.well-known/ordering-test.json</a> &mdash; the ten claims, and which are publicly demonstrable<br>
<em>the checker</em><a href="/self-check" class="g" style="color:#7fe3b0;text-decoration:none">/self-check</a> &mdash; runs all ten in your own browser and grades us without mercy<br>
<em>the console</em><a href="/console" class="g" style="color:#7fe3b0;text-decoration:none">/console</a> &mdash; grant authority, delegate it, exercise it, and watch the boundary hold (needs a key)
</div>

<div class="pgcgrid" style="margin-top:22px">
<div class="pgcard">
<div class="pgctitle">Prove a record is <span>not there</span></div>
<div class="pgcfoot" style="margin-top:0">A hash chain proves inclusion. Almost nobody does exclusion. Ask for any value at all and get back the two adjacent leaves with consecutive indices &mdash; nothing can sit between them, against a root committed before you asked.</div>
<div class="pgmono" style="margin-top:12px">
<em>periods</em><a href="/x/complete/periods">/x/complete/periods</a><br>
<em>absence</em><a href="/x/complete/prove?period=2026-07&amp;value=8">/x/complete/prove?period=&amp;value=</a><br>
<em>rules</em><a href="/x/complete/spec">/x/complete/spec</a>
</div>
</div>

<div class="pgcard">
<div class="pgctitle">Prove the log <span>only ever grew</span></div>
<div class="pgcfoot" style="margin-top:0">RFC 6962 consistency proofs, deliberately unmodified, so existing Certificate Transparency verifiers work against them without new code. Hand back any tip we ever served and we prove it is still on the chain we serve today.</div>
<div class="pgmono" style="margin-top:12px">
<em>tip</em><a href="/x/consistency/root">/x/consistency/root</a><br>
<em>prefix</em><a href="/x/consistency/proof">/x/consistency/proof?first=&amp;second=</a><br>
<em>ancestry</em><a href="/x/consistency/ancestor">/x/consistency/ancestor?tip=</a>
</div>
</div>

<div class="pgcard">
<div class="pgctitle">Prove the clock is <span>not ours</span></div>
<div class="pgcfoot" style="margin-top:0">The chain tip goes to OpenTimestamps and into Bitcoin, and other platforms witness our chain so we cannot rebuild it either. The anchored tip is provably on <i>this</i> log, not a substituted one.</div>
<div class="pgmono" style="margin-top:12px">
<em>anchor</em><a href="/api/anchor-status">/api/anchor-status</a><br>
<em>peers</em><a href="/x/witness/peers">/x/witness/peers</a><br>
<em>our tip</em><a href="/x/witness/tip">/x/witness/tip</a>
</div>
</div>

<div class="pgcard">
<div class="pgctitle">Prove the rules <span>were bound in</span></div>
<div class="pgcfoot" style="margin-top:0">The ruleset version is a component of the digest sealed with the decision, not a field beside it. The response hands back the exact string that was hashed &mdash; SHA-256 it yourself and confirm. No scoring logic is disclosed at any point.</div>
<div class="pgmono" style="margin-top:12px">
<em>packs</em><a href="/x/rulebind/packs">/x/rulebind/packs</a><br>
<em>prove</em>/x/rulebind/prove <span style="color:rgba(255,255,255,0.3)">(POST)</span>
</div>
</div>

<div class="pgcard">
<div class="pgctitle">Prove it is <span>deterministic</span></div>
<div class="pgcfoot" style="margin-top:0">Send any inputs you like. Keep the fingerprint. Send the identical inputs next month from anywhere. If the verdict ever moves under an unchanged code fingerprint, the engine is not deterministic and you hold the proof.</div>
<div class="pgmono" style="margin-top:12px">
<em>rules</em><a href="/x/replay/spec">/x/replay/spec</a><br>
<em>fingerprint</em><a href="/x/replay/fingerprint">/x/replay/fingerprint</a><br>
<em>challenge</em>/x/replay/challenge <span style="color:rgba(255,255,255,0.3)">(POST)</span>
</div>
</div>

<div class="pgcard">
<div class="pgctitle">Prove the agent <span>was entitled</span></div>
<div class="pgcfoot" style="margin-top:0">Every authority decision, traced to the human who granted it, with the person who accepted the risk named separately. Export one as a signed bundle and check it on your own machine with a script that never contacts us.</div>
<div class="pgmono" style="margin-top:12px">
<em>decisions</em><a href="/x/continuity/decisions">/x/continuity/decisions</a><br>
<em>proof</em><a href="/x/continuity/proof">/x/continuity/proof?evaluation=</a><br>
<em>checker</em><a href="/verify-authority.py">/verify-authority.py</a>
</div>
</div>
</div>

<p class="pgfoot" style="margin-top:26px">At the last run: <b style="color:#7fe3b0">eight verified, zero failed, two still amber.</b> The two are reported as not yet demonstrable by an outside party, and they stay that way until they genuinely are &mdash; because a conformance document whose author scores full marks on the day he publishes it is a marketing page.</p>
</div>
</div>
</section>



<section id="authority">
<div class="wrap">
<div class="entry"><span class="no">Block 018 &middot; Authority</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>Authority, derived. <i>Not assumed.</i></h2>
<p class="lead">Everything above proves what your AI <b>did</b>. This proves it was <b>entitled to</b>. An agent takes an action; it got its authority from another agent, which got it from a system, which got it from a person. Nothing in the standard governance stack can show the authority used at the end derives from the authority granted at the start. Permissions answer one hop. Audit logs describe the aftermath. <b>Neither derives anything.</b></p>

<div class="steps" style="margin-top:40px">
<div class="st"><div class="k">One &middot; Derivation</div><h3>Every hop, back to a human</h3><p>Every grant points at a parent and terminates at a named human principal. Scope, limits, purpose and validity <b>must narrow at every hop</b> &mdash; a child can inherit authority or reduce it, never widen it. A grant with no parent and no human issuer is not a root, it is an orphan, and it is refused.</p></div>
<div class="st"><div class="k">Two &middot; At execution</div><h3>Re-derived, not trusted</h3><p>The whole chain is re-derived at the <b>instant of execution</b>, not trusted from the instant of issue &mdash; because the interesting failures are never at the last hop. A parent revoked three hops up kills a child credential that is still technically valid, instantly, without anyone having to go and find it.</p></div>
<div class="st"><div class="k">Three &middot; Accountability</div><h3>Who accepted the risk</h3><p>Every lineage names a person who accepts the risk of that authority <b>existing</b> &mdash; separately from who granted it and who exercises it. An issuer says you may. A subject acts. Neither is a person putting their name to the capability being switched on, and <b>that is the name an incident needs.</b></p></div>
</div>

<div class="sealnote" style="margin-top:34px">
<h3>And the proof leaves the building</h3>
<p>Export any authority decision and it comes back as a <b>signed bundle</b> carrying the entire authority path exactly as it stood at that instant, the parameters it was judged against, every digest, and an Ed25519 signature. Then check it somewhere else &mdash; with a script that has no dependencies, makes no network calls, and does not phone home, because a verification tool that reports back to the party being verified is not a verification tool.</p>
<div class="ex"><em>get it</em>curl -sO https://sebbi.pro/verify-authority.py<br><em>run it</em>curl -s "https://sebbi.pro/x/continuity/proof?evaluation=&lt;id&gt;" | python3 verify-authority.py -<br><em>it checks</em>the signature &middot; every digest recomputed &middot; the whole derivation re-run from the published rules<br><em>then</em>it reaches its own verdict &mdash; and says so if that verdict disagrees with ours</div>
<p style="margin-top:14px"><b>And when authority cannot be derived, you do not get BLOCK.</b> You get a proof of the refusal &mdash; which grant, which invariant, at which hop &mdash; and the verifier independently reproduces that failure in the same place. An agent that can prove it was <i>not</i> authorised is a different kind of object to one that was simply denied.</p>
<p style="margin-top:14px"><b>The honest limits, as everywhere else on this page:</b> this proves authority was derivable from a human grant. It does not prove the human should have granted it, or that the parameters describe something that really happened. Grants are authenticated by sealing rather than per-issuer signatures, so an outside party verifies them through the chain rather than entirely offline. And the risk half of a composed verdict cannot be re-derived without the scoring engine &mdash; which the bundle states plainly rather than glosses over.</p>
</div>

<div class="cov-note" style="margin-top:26px;font-family:var(--mono);font-size:11px;line-height:2">
<em style="font-style:normal;color:var(--gold);margin-right:8px">the rules</em><a href="/x/continuity/spec">/x/continuity/spec</a> &mdash; enough to reimplement the evaluator and disagree with us<br>
<em style="font-style:normal;color:var(--gold);margin-right:8px">the decisions</em><a href="/x/continuity/decisions">/x/continuity/decisions</a> &mdash; real sealed evaluations, blocks listed beside allows<br>
<em style="font-style:normal;color:var(--gold);margin-right:8px">the path</em><a href="/x/continuity/trace">/x/continuity/trace?grant=</a> &mdash; every hop, root first, with who accepted the risk<br>
<em style="font-style:normal;color:var(--gold);margin-right:8px">the proof</em><a href="/x/continuity/proof">/x/continuity/proof?evaluation=</a> &mdash; the signed, portable bundle<br>
<em style="font-style:normal;color:var(--gold);margin-right:8px">the key</em><a href="/x/continuity/pubkey">/x/continuity/pubkey</a> &mdash; Ed25519, RFC 8032, verifiable with any standard library<br>
<em style="font-style:normal;color:var(--gold);margin-right:8px">the checker</em><a href="/verify-authority.py">/verify-authority.py</a> &mdash; one file, no dependencies, no network
</div>

<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:26px">
<a href="/self-check" class="bgold">Run every check we publish &rarr;</a>
<a href="/whitepaper" class="pbtn">Read the whitepaper &rarr;</a>
<a href="/developers" class="pbtn">Developer docs &rarr;</a>
</div>
</div>
</section>

<section id="install">
<div class="wrap">
<div class="entry"><span class="no">Block 019 &middot; Install</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>Five minutes. <i>Start to sealed.</i></h2>
<p class="lead">No build step, no container, no dependencies to install, nothing added to your requirements file. If your organisation reviews new libraries before they go near production, this is one readable file rather than a supply chain.</p>

<div class="inst">

<div class="instep">
<h3>Get your key</h3>
<p>Fill in the form below. The key, your referral code and the install guide arrive instantly. <b>No card, nothing to cancel</b> &mdash; free for 90 days.</p>
</div>

<div class="instep">
<h3>Drop in one file</h3>
<p>Download <b>sebbi_sdk.py</b> and put it next to your code. Standard library only, so there is nothing to install and nothing new in your dependency tree.</p>
<div class="cmd"><span class="c"># check it works before you wire it in</span><br>python3 sebbi_sdk.py <span class="g">--selftest</span></div>
</div>

<div class="instep">
<h3>Set two values</h3>
<p>Your key, and the name your records belong to. Environment variables, so nothing sensitive goes near your repository.</p>
<div class="cmd">SEBBI_API_KEY=<span class="g">al_live_your_key</span><br>SEBBI_CHAIN=<span class="g">yourcompany.com</span><br><span class="c"># recommended: keeps records safe if we're unreachable</span><br>SEBBI_SPOOL=<span class="g">/var/spool/sebbi</span></div>
</div>

<div class="instep">
<h3>Add the line</h3>
<p>Above any function whose decisions you need to prove. <b>That is the integration.</b> Nothing else in your code changes.</p>
<div class="cmd"><span class="k">from</span> sebbi_sdk <span class="k">import</span> witness<br><br><span class="g">@witness()</span><br><span class="k">def</span> approve_loan(application):<br>&nbsp;&nbsp;&nbsp;&nbsp;<span class="c"># unchanged</span><br>&nbsp;&nbsp;&nbsp;&nbsp;<span class="k">return</span> decision</div>
</div>

<div class="instep">
<h3>Check it landed</h3>
<p>Every call now carries a receipt with its position in the chain. Print one, or read the counters, and you are done.</p>
<div class="cmd"><span class="k">from</span> sebbi_sdk <span class="k">import</span> receipt_for, stats<br><br>result = approve_loan(app)<br><span class="k">print</span>(receipt_for(result))&nbsp;&nbsp;<span class="c"># position + chain tip</span><br><span class="k">print</span>(stats())&nbsp;&nbsp;<span class="c"># sent, sealed, dropped</span></div>
</div>

</div>

<div class="sealnote">
<h3>Not on Python?</h3>
<p>The whole protocol is a hash and one HTTP call, and it is published in full &mdash; run <b>python3 sebbi_sdk.py --explain</b> and you get the exact canonical form, the request shape and the rules. It ports in an hour to anything. <b>Nothing about it is privileged</b>, and we would rather you wrote your own than waited on us.</p>
<p style="margin-top:12px"><b>Running Sebdog instead?</b> Then there is no SDK and no key in your code at all &mdash; the engine runs on your hardware and your application talks to it over your own network. <a href="#onprem" style="color:var(--gold)">How that works &rarr;</a></p>
</div>
</div>
</section>

<section id="signup">
<div class="wrap">
<div class="entry"><span class="no">Block 020 &middot; Start</span><span class="rule"></span><span class="sealed" data-seal></span></div>
<h2>AILeash API key. <i>90 days free.</i></h2>
<p class="lead">Pick a product, add your name and email. Key, referral code and a step-by-step installation guide arrive instantly &mdash; everything free for 90 days, no card. When the trial ends you'll be directed to a secure Stripe payment reflecting only the real devices that used your key.</p>

<div class="tabs">
<button class="tab on" id="tab-aileash" onclick="setProduct('aileash')">AILeash</button>
<button class="tab" id="tab-sonicboom" onclick="setProduct('sonicboom')">SonicBoom</button>
<button class="tab" id="tab-sentinel" onclick="setProduct('sentinel')">Sentinel</button>
<button class="tab" id="tab-guardian" onclick="setProduct('guardian')">Guardian</button>
<button class="tab" id="tab-sebdog" onclick="setProduct('sebdog')">Sebdog</button>
</div>

<div class="fr">
<div class="f"><label for="fn">First name</label><input type="text" id="fn" placeholder="Justin"></div>
<div class="f"><label for="ln">Last name</label><input type="text" id="ln" placeholder="Smith"></div>
</div>
<div class="f"><label for="em">Email address</label><input type="email" id="em" placeholder="you@company.com"></div>
<div class="f"><label for="ph">Phone number</label><input type="tel" id="ph" placeholder="+44 7700 000000"></div>
<div class="f"><label for="org">Platform or company name</label><input type="text" id="org" placeholder="e.g. GameZone / My Platform"></div>
<div class="f"><label for="dv">Estimated devices</label><input id="dv" type="number" min="1" step="1" value="1000" placeholder="Type any number, e.g. 8000000"></div>
<input class="refin" type="text" id="ref-code" placeholder="Referral code (optional) &mdash; e.g. REF-JOHN-1234" aria-label="Referral code, optional">
<button class="gobtn" id="go-btn" onclick="doSignup()">Get AILeash API key &middot; 90 days free &rarr;</button>
<div class="merr" id="msg-err"></div>
<div class="mok" id="msg-ok"></div>

<div class="keybox" id="key-box">
<div class="kl">Your API key &mdash; save it now</div>
<div class="kv" id="key-val"></div>
<div class="refbox" id="ref-box"><div class="kl">Your referral code</div><div class="c" id="ref-code-display"></div><p>Share it with anyone. Every device they sign up pays you 10p a month, for as long as it stays.</p></div>
<div class="usage"><em>POST</em> https://sebbi.pro/api/govern<br>Authorization: Bearer <em id="key-prev">YOUR_KEY</em><br><span style="color:rgba(255,255,255,0.22)">Free for 90 days &middot; 50p per device after the trial &middot; billed via Stripe on real devices only</span></div>
<div id="shieldbox" style="display:none;margin-top:14px;border:1px dashed rgba(201,168,76,0.5);border-radius:4px;padding:14px">
<div class="kl">Your shield &mdash; live-verified, put it on your site</div>
<div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap;margin-top:8px">
<img id="shieldimg" src="" alt="AILeash shield" width="95" style="flex-shrink:0">
<div style="flex:1;min-width:200px">
<p style="font-size:12px;color:rgba(255,255,255,0.45);line-height:1.6;margin-bottom:8px">This badge is drawn live by our server. It shows gold and your company name only while your account is active &mdash; copied or faked, it renders grey UNVERIFIED.</p>
<div class="kv" id="shieldcode" style="font-size:9.5px"></div>
</div>
</div>
</div>
</div>
</div>
</section>

</main>

<footer>
<div class="fin">
<div>
<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
<svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="13.5" fill="none" stroke="#c9a84c" stroke-width="2.6" stroke-dasharray="66 20" stroke-linecap="round" transform="rotate(-50 16 16)"/><circle cx="26.5" cy="7" r="3.1" fill="#c9a84c"/><circle cx="16" cy="16" r="3.4" fill="#0a0f1e"/></svg>
<span style="font-family:var(--disp);font-weight:900;font-size:19px;color:#fff">AI<b style="color:var(--gold)">Leash</b></span>
</div>
<div style="font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.25);margin-bottom:12px">Monop Content &middot; Blyth, Northumberland, UK</div>
<p class="fdesc">Five AI compliance and safety products on one tamper-evident engine, extended by Signal Packs, authority continuity with exportable proof, human-oversight sealing, mutual witnessing and the DSR, reconciliation and declaration notaries. Built to support EU AI Act Articles 9, 12, 13 and 14, the Online Safety Act, the ICO Children's Code and the DSA. Free for 90 days, then 50p per device per month. You keep the rest.</p>
</div>
<div><h4>Products</h4><a href="#products">AILeash</a><a href="/sonicboom">SonicBoom</a><a href="/sentinel">Sentinel</a><a href="/guardian-parent">Guardian</a><a href="#onprem">Sebdog &middot; on your hardware</a></div>
<div><h4>Tools</h4><a href="/pack">Evidence pack &middot; build and seal one</a><a href="#evidence">Evidence pack &middot; what it proves</a><a href="/savings">Savings &middot; what a proof layer costs against what you run now</a><a href="#authority">Authority &middot; proof an agent was entitled to act</a><a href="/self-check">Self check &middot; run every claim we publish</a><a href="/verify-authority.py">Offline verifier &middot; check a proof without us</a><a href="#oversight">Human oversight &middot; commit before reveal</a><a href="#sdk">SDK &middot; one line of code</a><a href="/witness">Witness network &middot; the live peer list</a><a href="/x/roster/list">Roster &middot; raw, no key needed</a><a href="/x/ots/status">Anchor status &middot; confirmed and pending</a><a href="/x/signed/spec">Signed submission &middot; your key, not ours</a><a href="#network">Witness network &middot; founding cohort</a><a href="#notaries">Notaries &middot; DSR, reconciliation, declarations</a><a href="#conformance">Conformance &middot; probes and breadth</a><a href="/signal-packs">Signal Packs &middot; build your own risk packs</a><a href="/pay-check">Payment Notary &middot; beat invoice fraud</a><a href="/notary">Profile Notary &middot; seal your identity</a><a href="/seal">Seal a post &middot; free, no account</a><a href="/verify">Verify a sealed post</a><a href="/brain">Brain &middot; instruction governance</a><a href="/scan">AI Act scanner</a><a href="/reseller">Partner programme</a><a href="/report-threat">Report a threat</a><a href="/compliance-assistant">AI assistant</a></div>
<div><h4>Resources</h4><a href="/developers">Developers</a><a href="#install">Install in 5 minutes</a><a href="/whitepaper">Whitepaper</a><a href="/contact">Contact</a><a href="#signup">Get API key</a><a href="/referrals">My referrals</a></div>
</div>
<div class="fbot"><span>&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, UK</span><span>EU AI Act Art. 9 &middot; 12 &middot; 13 &middot; 14 &middot; Online Safety Act &middot; ICO Children's Code &middot; DSA</span></div>
</footer>

<script>
/* ================= platform JS (same endpoints) ================= */
var AP='aileash';
function setProduct(p){
AP=p;
['aileash','sonicboom','sentinel','guardian','sebdog'].forEach(function(t){var el=document.getElementById('tab-'+t);if(el)el.className='tab';});
var el=document.getElementById('tab-'+p);if(el)el.className='tab on';
var btn=document.getElementById('go-btn');
var labels={aileash:'Get AILeash API key \u00b7 90 days free \u2192',sonicboom:'Get SonicBoom plugin \u00b7 90 days free \u2192',sentinel:'Get Sentinel API key \u00b7 90 days free \u2192',guardian:'Get Guardian key \u00b7 free for families \u2192',sebdog:'Get Sebdog \u00b7 runs on your hardware \u2192'};
btn.textContent=labels[p];
}

function calc(){
var charge=parseFloat(document.getElementById('charge').value)||0;
var devices=parseInt(document.getElementById('devices').value)||0;
document.getElementById('r-user').textContent='\u00a3'+charge.toFixed(2);
document.getElementById('r-you').textContent='\u00a3'+Math.max(0,(charge-0.50)*devices).toLocaleString('en-GB',{maximumFractionDigits:0});
document.getElementById('r-we').textContent='\u00a3'+(0.50*devices).toLocaleString('en-GB',{maximumFractionDigits:0});
}
calc();

async function doSignup(){
var fn=document.getElementById('fn').value.trim(),ln=document.getElementById('ln').value.trim();
var em=document.getElementById('em').value.trim(),ph=document.getElementById('ph').value.trim();
var org=document.getElementById('org').value.trim();
var dv=parseInt(document.getElementById('dv').value)||1;
var rc=document.getElementById('ref-code').value.trim();
var err=document.getElementById('msg-err'),ok=document.getElementById('msg-ok'),kb=document.getElementById('key-box'),btn=document.getElementById('go-btn');
err.classList.remove('show');ok.classList.remove('show');kb.classList.remove('show');
if(!em||!em.includes('@')){err.textContent='Enter a valid email address to get your key.';err.classList.add('show');return;}
if(!org){err.textContent='Enter your platform or company name.';err.classList.add('show');return;}
var orig=btn.textContent;btn.textContent='Creating key\u2026';btn.disabled=true;
try{
var r=await fetch('/signup',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({email:em,phone:ph,name:fn+' '+ln,org:org,org_type:AP,product:AP,devices:dv,ref_code:rc})});
var d=await r.json();
if(d.api_key){
document.getElementById('key-val').textContent=d.api_key;
document.getElementById('key-prev').textContent=d.api_key.slice(0,20)+'...';
if(d.ref_code){document.getElementById('ref-code-display').textContent=d.ref_code;}
if(d.badge_url){
document.getElementById('shieldimg').src=d.badge_url;
document.getElementById('shieldcode').textContent='<a href="https://sebbi.pro"><img src="'+d.badge_url+'" alt="AI governance sealed by AILeash" width="95"></a>';
document.getElementById('shieldbox').style.display='block';
}
kb.classList.add('show');
ok.textContent='Key created. Everything is free for 90 days \u2014 your installation guide is on its way to your inbox. Billing only begins after the trial, on real devices only.';ok.classList.add('show');
btn.textContent='Key created \u2713';
sealBlock('signup completed');
}else{err.textContent=d.error||'Something went wrong. Email justrightdecorators@gmail.com';err.classList.add('show');btn.textContent=orig;btn.disabled=false;}
}catch(e){err.textContent='Cannot reach the server. Email justrightdecorators@gmail.com';err.classList.add('show');btn.textContent=orig;btn.disabled=false;}
}

/* ================= SIGNATURE: the visit ledger =================
Real SHA-256 via Web Crypto. Chained exactly like the platform:
hash(prev_hash + timestamp + event). Client-side only - no network. */
var visitChain=[];
var chainTip='GENESIS';
var sealedSections={};
var CRYPTO_OK=!!(window.crypto&&crypto.subtle&&window.TextEncoder);
if(!CRYPTO_OK){
var _r=document.getElementById('rail'),_c=document.getElementById('chip');
if(_r)_r.style.display='none';if(_c)_c.style.display='none';
var _v=document.getElementById('verify');if(_v)_v.style.display='none';
document.querySelectorAll('main').forEach(function(m){m.style.marginLeft='0';});
}

async function sha256hex(s){
var buf=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s));
return Array.from(new Uint8Array(buf)).map(function(b){return b.toString(16).padStart(2,'0');}).join('');
}

async function sealBlock(eventName){
if(!CRYPTO_OK)return 'unavailable';
var ts=Date.now();
var prev=chainTip;
var hash=await sha256hex(prev+'|'+ts+'|'+eventName);
chainTip=hash;
var n=visitChain.length+1;
visitChain.push({n:n,event:eventName,ts:ts,prev:prev,hash:hash});
renderBlock(n,eventName,hash);
return hash;
}

function renderBlock(n,eventName,hash){
var chain=document.getElementById('chain');
var d=document.createElement('div');d.className='blk';
d.innerHTML='<div class="blk-n">'+String(n).padStart(3,'0')+' &middot; '+eventName+'</div><div class="blk-h">'+hash.slice(0,16)+'&hellip;</div>';
chain.appendChild(d);
requestAnimationFrame(function(){requestAnimationFrame(function(){d.classList.add('on');});});
while(chain.children.length>9){chain.removeChild(chain.firstChild);}
document.getElementById('tip').textContent=hash.slice(0,12)+'\u2026';
var chipn=document.getElementById('chipn'),chiptip=document.getElementById('chiptip');
if(chipn){chipn.textContent=visitChain.length+' block'+(visitChain.length===1?'':'s');chiptip.textContent=hash.slice(0,12)+'\u2026';}
}

async function verifyVisit(){
var out=document.getElementById('vout');
out.innerHTML='verifying '+visitChain.length+' blocks\u2026';
var prev='GENESIS';
for(var i=0;i<visitChain.length;i++){
var b=visitChain[i];
var re=await sha256hex(b.prev+'|'+b.ts+'|'+b.event);
if(re!==b.hash||b.prev!==prev){
out.innerHTML='CHAIN BROKEN at block '+b.n+' \u2014 tampering detected.';return;
}
prev=b.hash;
}
var lines=['<span class="ok">\u2713 CHAIN INTACT \u2014 '+visitChain.length+' blocks re-hashed and verified, genesis to tip.</span>'];
visitChain.slice(-4).forEach(function(b){lines.push(String(b.n).padStart(3,'0')+' '+b.event+' <span class="h">'+b.hash.slice(0,20)+'\u2026</span>');});
lines.push('tip <span class="h">'+chainTip.slice(0,32)+'\u2026</span>');
lines.push('<span style="color:rgba(255,255,255,0.3)">Computed entirely in your browser. This is the same verification your auditors run against sebbi.pro/api/verify-chain.</span>');
out.innerHTML=lines.join('<br>');
sealBlock('chain verified by visitor');
}

async function tamperDemo(){
var out=document.getElementById('vout');
if(visitChain.length<2){out.innerHTML='Read a little more of the page first \u2014 you need at least two blocks to tamper with.';return;}
var target=visitChain[1];
var original=target.event;
out.innerHTML='You just changed block 002 from <span class="h">\u201c'+original+'\u201d</span> to <span class="h">\u201cnothing happened here\u201d</span>\u2026<br>re-verifying the chain\u2026';
target.event='nothing happened here';
await new Promise(function(r){setTimeout(r,900);});
var prev='GENESIS',broken=-1;
for(var i=0;i<visitChain.length;i++){
var b=visitChain[i];
var re=await sha256hex(b.prev+'|'+b.ts+'|'+b.event);
if(re!==b.hash||b.prev!==prev){broken=b.n;break;}
prev=b.hash;
}
target.event=original;
out.innerHTML='You just changed block 002 to <span class="h">\u201cnothing happened here\u201d</span> and re-verified.<br>'
+'<span style="color:#ff9d94">\u2717 CHAIN BROKEN at block '+String(broken).padStart(3,'0')+' \u2014 the stored hash no longer matches the content. Tampering detected instantly.</span><br>'
+'<span class="ok">Block restored. \u2713 Chain intact again.</span><br>'
+'<span style="color:rgba(255,255,255,0.3)">That is the whole product. Edit one record \u2014 even one character \u2014 and every verification from that block forward fails. There is no quiet way to rewrite history.</span>';
sealBlock('tampering attempt detected');
}

/* Wake the page modules.
   /self-check, /console and the discovery document are served by runtime
   patches that only install once their module has been touched, so after a
   deploy they 404 until somebody pokes an /x/ route. Poking it here means a
   visitor never sees that, and it costs one request. */
// Every page here is served by a runtime patch that only installs once its
// module has been touched, so after a deploy they 404 until somebody pokes an
// /x/ route. Touching console arms its siblings too; the rest are belt and
// braces so no visitor ever lands on a dead link.
['/x/console/status','/x/savings/status','/x/selfcheck/status',
 '/x/standard/status','/x/verifier/status','/x/network/status']
  .forEach(function(u){ fetch(u).catch(function(){}); });

/* seal the hero headline on load */
(async function(){
if(!CRYPTO_OK)return;
var vn=null;
try{
var r=await fetch('/api/visits');var d=await r.json();
if(d&&d.visits)vn=d.visits;
}catch(e){}
var ev=vn?('visitor \u2116 '+vn.toLocaleString('en-GB')+' arrived'):'visit opened';
var h=await sealBlock(ev);
var el=document.getElementById('hseal');
el.innerHTML='This headline was just sealed: <span class="hh">'+h.slice(0,24)+'\u2026</span> \u2014 watch the chain grow as you read \u2192';
if(vn){
document.getElementById('vnum').textContent='\u2116 '+vn.toLocaleString('en-GB');
document.getElementById('vhash').textContent='seal '+h.slice(0,24)+'\u2026';
document.getElementById('vstamp').style.display='inline-flex';
}
})();

/* seal each section when it enters view */
var names={how:'read: how it works',products:'read: products',packs:'read: signal packs',margin:'used: margin section',referral:'read: referrals','notary-promo':'read: profile notary',law:'read: the law',coverage:'read: coverage map',oversight:'read: human oversight',authority:'read: authority continuity',anchor:'read: external anchoring',network:'read: witness network',notaries:'read: the notaries',conformance:'read: conformance testing',verify:'reached: the proving ground',signup:'reached: signup'};
var io=new IntersectionObserver(function(entries){
entries.forEach(function(e){
if(e.isIntersecting&&!sealedSections[e.target.id]){
sealedSections[e.target.id]=true;
sealBlock(names[e.target.id]||('read: '+e.target.id)).then(function(h){
var s=e.target.querySelector('[data-seal]');
if(s)s.innerHTML='sealed <b>'+h.slice(0,10)+'\u2026</b>';
});
}
});
},{threshold:0.25});
Object.keys(names).forEach(function(id){var el=document.getElementById(id);if(el)io.observe(el);});

/* calculator interaction gets its own block, once */
var calcSealed=false;
document.getElementById('charge').addEventListener('input',function(){
if(!calcSealed){calcSealed=true;sealBlock('calculated a margin');}
});

/* decision ticker - demo data, labelled by the engine's real reason codes */
(function(){
var users=['u_7f2','u_c19','u_a04','u_e88','u_31b','u_9d5','u_f47','u_206'];
var acts=['payment','login','message','transfer','api_call','checkout'];
var outs=[['ALLOW','A',0.12,0.34],['ALLOW','A',0.05,0.3],['CHALLENGE','C',0.38,0.65],['ALLOW','A',0.1,0.33],['BLOCK','B',0.72,0.94],['ALLOW','A',0.08,0.3],['CHALLENGE','C',0.4,0.68]];
var items=[];
for(var i=0;i<18;i++){
var o=outs[Math.floor(Math.random()*outs.length)];
var sc=(o[2]+Math.random()*(o[3]-o[2])).toFixed(2);
items.push('<span>'+users[i%users.length]+' &middot; '+acts[i%acts.length]+' &rarr; <b class="'+o[1]+'">'+o[0]+'</b> '+sc+' &middot; sealed</span>');
}
var half=items.join('');
document.getElementById('tk').innerHTML=half+half;
})();

</script>
<script>
/* Proving Ground - its own block, so a failure here cannot take the page
   script with it, and a failure there cannot stop this running. */
/* ---------- the proving ground ---------- */
function pgTab(which){
  var run=which==='run';
  document.getElementById('pgt-run').className='pgtab'+(run?' on':'');
  document.getElementById('pgt-rev').className='pgtab'+(run?'':' on');
  document.getElementById('pgp-run').className='pgpanel'+(run?'':' hide');
  document.getElementById('pgp-rev').className='pgpanel'+(run?' hide':'');
}

function pgSync(){
  document.getElementById('pg-trust-v').textContent=parseFloat(document.getElementById('pg-trust').value).toFixed(2);
  document.getElementById('pg-amount-v').textContent=parseInt(document.getElementById('pg-amount').value).toLocaleString('en-GB');
  document.getElementById('pg-v60-v').textContent=document.getElementById('pg-v60').value;
  document.getElementById('pg-v5m-v').textContent=document.getElementById('pg-v5m').value;
  document.getElementById('pg-v1h-v').textContent=document.getElementById('pg-v1h').value;
  document.getElementById('pg-dev-v').textContent=parseFloat(document.getElementById('pg-dev').value).toFixed(2);
  document.getElementById('pg-anom-v').textContent=parseFloat(document.getElementById('pg-anom').value).toFixed(2);
}

function pgReveal(el){
  try{ if(el&&el.scrollIntoView){el.scrollIntoView({behavior:'smooth',block:'start'});} }catch(e){}
}

function pgEsc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}

function pgFail(el,msg){
  var box=document.getElementById(el);
  if(box){box.innerHTML='<div class="pgerr">'+pgEsc(msg)+'</div>';pgReveal(box);}
}

async function pgPost(path,body){
  var r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  var d=await r.json();
  return {status:r.status,data:d};
}

/* ---- 1. run a decision ---- */
async function pgRun(){
  var btn=document.getElementById('pg-run-btn');
  var out=document.getElementById('pg-result');
  var label=btn.textContent;
  btn.disabled=true;btn.textContent='Scoring and sealing\u2026';
  out.innerHTML='';
  var payload={
    trust:parseFloat(document.getElementById('pg-trust').value),
    amount:parseFloat(document.getElementById('pg-amount').value),
    v60:parseFloat(document.getElementById('pg-v60').value),
    v5m:parseFloat(document.getElementById('pg-v5m').value),
    v1h:parseFloat(document.getElementById('pg-v1h').value),
    device_risk:parseFloat(document.getElementById('pg-dev').value),
    anomaly:parseFloat(document.getElementById('pg-anom').value),
    country:document.getElementById('pg-country').value,
    country_shift:document.getElementById('pg-shift').checked,
    action:'payment'
  };
  try{
    var res=await pgPost('/x/demo/govern',payload);
    if(res.status===429){pgFail('pg-result','That is the rate limit doing its job \u2014 public endpoints are capped per visitor. Give it a minute and try again.');btn.disabled=false;btn.textContent=label;return;}
    var d=res.data;
    if(!d||!d.decision){pgFail('pg-result','The engine did not return a decision. '+(d&&d.error?d.error:'Try again shortly.'));btn.disabled=false;btn.textContent=label;return;}

    var reasons=(d.reasons||[]).map(function(x){return '<span>'+pgEsc(x)+'</span>';}).join('');
    var cf=d.counterfactual_statement||'';
    var steps=(d.what_just_happened||[]).map(function(x){return '<li>'+pgEsc(x)+'</li>';}).join('');
    var v=d.verify||{};

    out.innerHTML=
      '<div class="pgverdictcard">'
      +'<div class="pgvhead">'
        +'<span class="pgvword '+pgEsc(d.decision)+'">'+pgEsc(d.decision)+'</span>'
        +'<span class="pgvscore">score <b>'+pgEsc(d.score)+'</b> &middot; thresholds 0.35 / 0.70</span>'
        +'<span class="pgvreasons">'+(reasons||'<span>no risk signals tripped</span>')+'</span>'
      +'</div>'
      +'<div class="pgrow"><div class="pgrlbl">What would have changed it</div>'
        +'<div class="pgcf"><div class="big">'+pgEsc(cf.charAt(0).toUpperCase()+cf.slice(1))+'</div>'
        +'<div class="pgrbody" style="margin-top:10px">Computed by running the scoring function backwards, not estimated. Change that one slider to the stated value and run it again \u2014 you will get the verdict it promises.</div></div></div>'
      +'<div class="pgrow"><div class="pgrlbl">Sealed into the live chain</div>'
        +'<div class="pgmono">'
        +'<em>block</em>'+pgEsc(d.block_index)+'<br>'
        +'<em>hash</em>'+pgEsc(d.audit_hash)+'<br>'
        +'<em>check this block</em><a href="'+pgEsc(v.this_block||'#')+'" target="_blank" rel="noopener">'+pgEsc(v.this_block||'')+'</a><br>'
        +'<em>check the chain</em><a href="'+pgEsc(v.whole_chain||'/api/verify-chain')+'" target="_blank" rel="noopener">/api/verify-chain</a><br>'
        +'<em>check the clock</em><a href="'+pgEsc(v.external_anchor||'/api/anchor-status')+'" target="_blank" rel="noopener">/api/anchor-status</a>'
        +'</div></div>'
      +'<div class="pgrow"><div class="pgrlbl">What just happened</div><ul class="pgsteps">'+steps+'</ul></div>'
      +'</div>';
    pgReveal(out);
    if(typeof sealBlock==='function'){sealBlock('ran a live decision');}
  }catch(e){
    pgFail('pg-result','Could not reach the engine. That is a real failure, not a staged one \u2014 try again in a moment.');
  }
  btn.disabled=false;btn.textContent=label;
}

/* ---- 2. take the review ---- */
var pgCase=null,pgTimer=null,pgStart=0;

function pgTick(){
  var s=(Date.now()-pgStart)/1000;
  document.getElementById('pg-clock').textContent=s.toFixed(1)+'s';
}

async function pgReview(){
  var out=document.getElementById('pg-rev-result');
  out.innerHTML='';
  var seeds=[
    {amount:9400,v60:18,v5m:29,v1h:77,trust:0.25,device_risk:0.4,anomaly:0.55,country:'XX',country_shift:true},
    {amount:180,v60:3,v5m:5,v1h:14,trust:0.62,device_risk:0.15,anomaly:0.2,country:'UK',country_shift:false},
    {amount:2600,v60:11,v5m:19,v1h:52,trust:0.41,device_risk:0.55,anomaly:0.35,country:'DE',country_shift:true},
    {amount:640,v60:6,v5m:9,v1h:24,trust:0.34,device_risk:0.25,anomaly:0.62,country:'US',country_shift:false}
  ];
  var seed=seeds[Math.floor(Math.random()*seeds.length)];
  try{
    var res=await pgPost('/x/demo/review',seed);
    if(res.status===429){pgFail('pg-rev-result','Rate limit reached \u2014 public endpoints are capped per visitor. A minute will clear it.');return;}
    var d=res.data;
    if(!d||!d.case_id){pgFail('pg-rev-result','Could not open a case. '+(d&&d.error?d.error:''));return;}
    pgCase=d.case_id;
    var m=d.material||{};
    var pretty={action:'Action',amount:'Amount',country:'Country','60_second_velocity':'Actions in last 60s','5_minute_velocity':'Actions in last 5 min',device_risk:'Device risk',behavioural_anomaly:'Behavioural anomaly',country_changed:'Country changed',trust_history:'Trust history'};
    var rows='';
    Object.keys(m).forEach(function(k){
      var val=m[k];
      if(k==='amount'){val='\u00a3'+Number(val).toLocaleString('en-GB');}
      if(typeof val==='boolean'){val=val?'yes':'no';}
      rows+='<div class="pgmrow"><span class="pgmk">'+pgEsc(pretty[k]||k)+'</span><span class="pgmv">'+pgEsc(val)+'</span></div>';
    });
    document.getElementById('pg-material').innerHTML=rows;
    document.getElementById('pg-case').className='pgcase';
    document.getElementById('pg-rev-start').style.display='none';
    pgReveal(document.getElementById('pg-case'));
    pgStart=Date.now();
    document.getElementById('pg-clock').textContent='0.0s';
    if(pgTimer){clearInterval(pgTimer);}
    pgTimer=setInterval(pgTick,100);
  }catch(e){
    pgFail('pg-rev-result','Could not reach the engine. Try again in a moment.');
  }
}

async function pgCommit(v){
  if(!pgCase){return;}
  if(pgTimer){clearInterval(pgTimer);pgTimer=null;}
  var out=document.getElementById('pg-rev-result');
  document.getElementById('pg-case').className='pgcase hide';
  out.innerHTML='<div class="pgmono" style="text-align:center">sealing your verdict\u2026</div>';
  try{
    var res=await pgPost('/x/demo/commit',{case_id:pgCase,verdict:v});
    var d=res.data;
    if(!d||!d.your_verdict){pgFail('pg-rev-result','Could not seal that. '+(d&&d.error?d.error:''));return;}
    var agree=d.agreed;
    var flag=d.flag?'<div class="pgflag"><b>Flagged:</b> '+pgEsc(d.flag)+'</div>':'';
    var steps=(d.what_just_happened||[]).map(function(x){return '<li>'+pgEsc(x)+'</li>';}).join('');
    out.innerHTML=
      '<div class="pgcompare">'
       +'<div class="pgc"><div class="pgclbl">You said</div><div class="pgcval '+pgEsc(d.your_verdict)+'" style="color:'+(d.your_verdict==='ALLOW'?'var(--allow)':d.your_verdict==='BLOCK'?'var(--block)':'var(--challenge)')+'">'+pgEsc(d.your_verdict)+'</div></div>'
       +'<div class="pgc"><div class="pgclbl">The engine said</div><div class="pgcval" style="color:'+(d.machine_verdict==='ALLOW'?'var(--allow)':d.machine_verdict==='BLOCK'?'var(--block)':'var(--challenge)')+'">'+pgEsc(d.machine_verdict)+'</div><div class="pgmono" style="margin-top:8px">score '+pgEsc(d.machine_score)+'</div></div>'
      +'</div>'
      +'<div class="pgverdictcard" style="margin-top:18px">'
      +'<div class="pgrow"><div class="pgrlbl">'+(agree?'You agreed':'You diverged')+'</div><div class="pgrbody">'+pgEsc(d.note||'')+'</div></div>'
      +'<div class="pgrow"><div class="pgrlbl">Time on the case</div><div class="pgrbody"><b>'+pgEsc(d.dwell_seconds)+' seconds</b>, sealed with your verdict. On a live deployment this sits in the reviewer\u2019s record permanently, and a pattern of very fast decisions is visible to an auditor whether or not anyone is watching at the time.</div>'+flag+'</div>'
      +'<div class="pgrow"><div class="pgrlbl">The order, fixed</div><ul class="pgsteps">'+steps+'</ul>'
        +'<div class="pgmono" style="margin-top:10px"><em>your block</em>'+pgEsc(d.block_index)+'<br><em>hash</em>'+pgEsc(d.audit_hash)+'<br><em>verify</em><a href="/api/verify-chain" target="_blank" rel="noopener">/api/verify-chain</a></div></div>'
      +'</div>'
      +'<div class="pgactions"><button class="bghost" onclick="pgAgain()">Take another case</button></div>';
    pgReveal(out);
    if(typeof sealBlock==='function'){sealBlock('took the review challenge');}
  }catch(e){
    pgFail('pg-rev-result','Could not reach the engine. Try again in a moment.');
  }
  pgCase=null;
}

function pgAgain(){
  document.getElementById('pg-rev-result').innerHTML='';
  document.getElementById('pg-rev-start').style.display='';
  pgReview();
}

/* ---------- live figures ---------- */
function pgSvg(id){var e=document.getElementById(id);if(e)e.innerHTML='';return e;}
function pgEl(tag,attrs,text){
  var n=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for(var k in attrs){n.setAttribute(k,attrs[k]);}
  if(text!=null){n.textContent=text;}
  return n;
}
function pgBars(svg,vals,colourFor,labels){
  if(!svg)return;
  var n=vals.length,max=Math.max.apply(null,vals.concat([1]));
  var w=300/n, pad=w*0.18;
  for(var i=0;i<n;i++){
    var h=vals[i]?Math.max(2,(vals[i]/max)*72):1;
    svg.appendChild(pgEl('rect',{x:(i*w+pad).toFixed(2),y:(78-h).toFixed(2),
      width:(w-pad*2).toFixed(2),height:h.toFixed(2),rx:1,
      fill:colourFor?colourFor(i):'#c9a84c','fill-opacity':vals[i]?0.85:0.25}));
  }
  svg.appendChild(pgEl('line',{x1:0,y1:79,x2:300,y2:79,stroke:'rgba(255,255,255,0.18)','stroke-width':1}));
  if(labels){
    labels.forEach(function(l){
      svg.appendChild(pgEl('text',{x:l.x,y:89,fill:'rgba(255,255,255,0.3)','font-size':7.5,
        'font-family':'IBM Plex Mono, monospace','text-anchor':l.anchor||'middle'},l.t));
    });
  }
}
function pgEmpty(svg,msg){
  if(!svg)return;
  svg.appendChild(pgEl('text',{x:150,y:44,fill:'rgba(255,255,255,0.28)','font-size':9,
    'font-family':'IBM Plex Mono, monospace','text-anchor':'middle'},msg));
}
async function pgCharts(){
  try{
    var r=await fetch('/x/stats');
    if(!r.ok)return;
    var d=await r.json();

    var c=d.chain||{};
    document.getElementById('pgc-h').textContent=(c.height||0).toLocaleString('en-GB')+' blocks';
    document.getElementById('pgc-gen').textContent='read live from /x/stats \u00b7 no account needed';
    var cs=pgSvg('pgc-chain');
    if(c.blocks_last_24h){
      pgBars(cs,c.last_24h||[],function(){return '#c9a84c';},
        [{x:4,t:'24h ago',anchor:'start'},{x:296,t:'now',anchor:'end'}]);
    }else{ pgEmpty(cs,'no blocks in the last 24 hours'); }

    var p=d.public_decisions||{};
    document.getElementById('pgc-n').textContent=(p.decisions||0)+' scored';
    var hs=pgSvg('pgc-hist');
    if(p.decisions){
      pgBars(hs,p.score_histogram||[],function(i){
        return i<3?'#1a9e6e':(i<7?'#c07a1d':'#c8362b');
      },[{x:4,t:'0.0',anchor:'start'},{x:150,t:'score',anchor:'middle'},{x:296,t:'1.0',anchor:'end'}]);
      [[0.35,'#c07a1d'],[0.70,'#c8362b']].forEach(function(t){
        var x=t[0]*300;
        hs.appendChild(pgEl('line',{x1:x,y1:2,x2:x,y2:79,stroke:t[1],'stroke-width':1,'stroke-dasharray':'3 3','stroke-opacity':0.8}));
      });
    }else{ pgEmpty(hs,'nobody has run a decision yet'); }

    var o=d.public_reviews||{};
    document.getElementById('pgc-r').textContent=(o.reviews||0)+' reviews';
    var ds=pgSvg('pgc-dwell');
    if(o.reviews){
      pgBars(ds,o.dwell_histogram||[],function(i){return i===0?'#c8362b':'#c9a84c';},
        [{x:4,t:'fast',anchor:'start'},{x:296,t:'slow',anchor:'end'}]);
      if(o.under_2_seconds){
        document.getElementById('pgc-dwellfoot').innerHTML=
          '<b style="color:#ff9d94">'+o.under_2_seconds_pct+'% committed in under two seconds.</b> '
          +'On a real deployment that pattern sits in the reviewer\u2019s record permanently.';
      }
    }else{ pgEmpty(ds,'nobody has taken a review case yet'); }
  }catch(e){}
}

try{pgSync();}catch(e){if(window.console)console.error('proving ground init:',e);}
try{pgCharts();}catch(e){}
</script>

</body>
</html>

```
