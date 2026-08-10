# Codebase — part 13 of 19

Contains:
- `human-oversight.html`
- `identity.html`


## `human-oversight.html`

115 lines, 13247 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Human Oversight Policy — Monop Content / AILeash</title>
<meta name="description" content="How human oversight is engineered into the AILeash platform: commit-before-reveal, the CHALLENGE flow, delegated authority tokens, conformance probes, and the sealed evidence trail behind every human intervention. Aligned to EU AI Act Article 14.">
<style>
  :root{--ink:#0a0f1e;--ink2:#111a30;--line:#232d4a;--gold:#c9a84c;--gold-dim:#8a7838;--ok:#7fe3b0;--text:#e8e8f0;--muted:#c2c8dc;--faint:#5a6178;--code-bg:#0b1226}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--ink);color:#fff;line-height:1.7;-webkit-font-smoothing:antialiased}
  .wrap{max-width:720px;margin:0 auto;padding:26px 20px 90px}
  a.back{color:var(--gold);text-decoration:none;font-size:13px;font-family:ui-monospace,Menlo,monospace;letter-spacing:.5px}
  .eyebrow{font-family:ui-monospace,Menlo,monospace;font-size:10.5px;letter-spacing:2px;text-transform:uppercase;color:var(--gold-dim);margin:22px 0 10px}
  h1{font-size:28px;font-weight:800;letter-spacing:-.5px;margin-bottom:10px;line-height:1.2}
  h1 span{color:var(--gold)}
  .meta{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--faint);margin-bottom:26px;line-height:1.9}
  h2{font-size:19px;font-weight:800;margin:40px 0 8px;letter-spacing:-.3px}
  h2 .n{color:var(--gold);font-family:ui-monospace,Menlo,monospace;font-size:13px;margin-right:8px}
  h3{font-size:15px;font-weight:700;margin:22px 0 6px;color:var(--gold)}
  p{font-size:14.5px;color:var(--muted);margin-bottom:13px}
  p b{color:#fff}
  ul{margin:0 0 14px 0;list-style:none}
  li{position:relative;padding-left:20px;margin-bottom:9px;font-size:14px;color:var(--muted)}
  li::before{content:'';position:absolute;left:0;top:9px;width:6px;height:6px;border-radius:50%;background:var(--gold)}
  li b{color:#fff}
  pre{background:var(--code-bg);border:1px solid var(--line);border-radius:10px;padding:15px;font-size:12.5px;color:var(--muted);overflow-x:auto;margin:14px 0;font-family:ui-monospace,Menlo,monospace;line-height:1.8}
  pre b{color:var(--ok);font-weight:400}
  .honest{border:1px solid rgba(201,168,76,.35);background:rgba(201,168,76,.05);border-radius:12px;padding:16px 20px;margin:16px 0;font-size:13.5px;color:var(--muted);line-height:1.75}
  .honest b{color:var(--gold)}
  hr{border:none;height:1px;background:linear-gradient(90deg,transparent,rgba(201,168,76,.25),transparent);margin:40px 0 0}
  footer{margin-top:30px;text-align:center;font-size:12px;color:var(--faint);font-family:ui-monospace,Menlo,monospace}
  footer a{color:var(--gold);text-decoration:none}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/">&larr; sebbi.pro</a>
  <div class="eyebrow">monop content · policy document · public</div>
  <h1>Human Oversight Policy<br><span>AILeash Platform</span></h1>
  <div class="meta">
    Document: MC-POL-003 · Version 2.0 · Effective 28 July 2026 · supersedes v1.0 (20 July 2026)<br>
    Owner: Justin Dobson, Founder, Monop Content · Review cycle: quarterly, and on any change to the challenge, authority, commitment or conformance mechanisms<br>
    Alignment: EU AI Act (Regulation 2024/1689) Article 14 · published at sebbi.pro/human-oversight
  </div>

  <h2><span class="n">1.</span>Position: oversight as engineering, not paperwork</h2>
  <p>"Human in the loop" fails in practice for three predictable reasons: the human is invoked too late or not at all; nobody can later prove the human who intervened was actually authorised to; and — least often admitted — nobody can show the human did anything more than agree with whatever the machine had already decided.</p>
  <p>This policy describes how the platform engineers all three away as far as they can be engineered, and states plainly where engineering stops.</p>

  <div class="honest"><b>What this policy does not claim.</b> No system can prove a person deliberated. That is an internal state and no amount of recording reaches it. Any vendor asserting proof of genuine human thought is describing something that does not exist. What follows is what <i>can</i> be proved: that a human was invoked, that they were authorised, that they committed before they knew the answer, how long they took, and how often they disagree.</div>

  <h2><span class="n">2.</span>When a human is brought in: the CHALLENGE band</h2>
  <p>The decision engine returns three verdicts. ALLOW and BLOCK are the clear cases. Between them sits a deliberate band — <b>CHALLENGE</b> — where the engine's judgement is that the event is neither safe enough to pass nor dangerous enough to refuse, and a human must decide.</p>
  <p>A CHALLENGE verdict is not advisory. The response includes a hosted resolution flow: a signed link the affected user or an authorised reviewer opens to confirm or deny the action, a status endpoint the customer's system polls, and an expiry after which the challenge lapses unresolved. Tokens are stateless and HMAC-signed; they cannot be forged or replayed after expiry.</p>
  <pre>event → engine → <b>CHALLENGE</b> → hosted confirm/deny (human)
       → resolution <b>sealed into the chain as its own block</b>
       → customer system reads the outcome and proceeds accordingly</pre>
  <p>The critical property: <b>the exception path is part of the evidence trail, not a gap in it.</b> Every human intervention — that it happened, when, and with what outcome — is sealed with the same tamper-evidence as the machine decisions around it.</p>

  <h2><span class="n">3.</span>Commit before reveal: proving the judgement was independent</h2>
  <p>An oversight record showing that a reviewer approved a decision the machine had already displayed to them proves very little. It is consistent with careful agreement and equally consistent with a rubber stamp. Until the two can be told apart, "human oversight" is an assertion.</p>
  <p>The platform separates them by controlling <b>order</b>. A case is opened with the material and the machine's verdict, and the verdict is returned to the caller as <i>withheld</i>. The reviewer sees the case, not the answer. Their own decision and their reasoning are sealed as a block. Only then is the machine verdict released.</p>
  <pre>open   → material sealed · machine verdict sealed but <b>withheld</b>
review → human sees the case, not the answer
commit → <b>human verdict and reasoning sealed</b>
reveal → machine verdict returned
result → the chain shows the human committed first</pre>
  <p>Because blocks cannot be reordered without breaking every block after them, the record establishes that the reviewer could not simply have agreed with an answer they had already seen. That is not proof of thought. It is proof of independence, which is the part Article 14 actually turns on.</p>

  <h3>Attention and divergence</h3>
  <ul>
    <li><b>Dwell time</b> — the interval between opening a case and committing to it is sealed with the decision. A sub-second approval sits in the record permanently, beside a two-minute one. One fast decision means nothing; four hundred consecutive fast decisions is a pattern that survives being explained away.</li>
    <li><b>Divergence rate</b> — agreement with the machine is recorded per reviewer over time. A reviewer who has never once disagreed across a meaningful sample is visible in the data. One who diverges sometimes is demonstrably exercising judgement.</li>
    <li><b>Reasoning</b> — a commitment with blank reasoning is refused outright. The reasoning is the part that gets examined later.</li>
  </ul>

  <h2><span class="n">4.</span>Who may oversee: delegated authority, sealed</h2>
  <p>Oversight only satisfies Article 14 if the human is competent and mandated — and if that mandate can be demonstrated afterwards. The platform makes the mandate a first-class object:</p>
  <ul>
    <li>A customer issues a <b>signed authority token</b> binding a named user identifier to a role, a maximum amount, and an expiry. The grant itself is sealed into the chain at the moment of issue — who was empowered, to what limit, until when, is a permanent record.</li>
    <li>Events carrying an authority token are verified deterministically. A token that is invalid, expired, bound to a different user, or below the amount at stake causes the verdict to <b>escalate</b> — an ALLOW becomes a CHALLENGE — with the specific reason (e.g. <i>authority_expired</i>, <i>authority_exceeds_limit</i>) sealed into the decision record.</li>
    <li>An approval made outside granted authority therefore cannot pass silently. It becomes a flagged, sealed, examinable event — visible to the customer's own audit and to any later review.</li>
  </ul>

  <h2><span class="n">5.</span>The overseer's information: explainability</h2>
  <p>A human cannot meaningfully oversee a verdict they cannot understand. Every verdict the engine returns carries its reasons in plain English — "velocity spike", "new country", "low trust", "authority exceeds limit" — not scores alone and never an unexplained refusal. The engine is deterministic: identical inputs always yield identical verdicts, so an overseer (or a court) re-examining a decision later sees exactly what the system saw and why it concluded what it did.</p>

  <h2><span class="n">6.</span>Override and the record of it</h2>
  <p>Ultimate control rests with the customer's humans, not with the engine. A customer may resolve any CHALLENGE in either direction, and may configure their own systems to overrule engine verdicts. The platform's role is not to remove human authority but to make its exercise <b>attributable and permanent</b>: the resolution, the resolver, and the timing are sealed. Oversight without a record is a claim; this is oversight with proof.</p>

  <h2><span class="n">7.</span>Conformance: testing the arrangement rather than trusting it</h2>
  <p>Section 3 has a dependency that must be stated openly. <b>The ordering guarantee holds only if the integrating system honours it.</b> If a platform displays the machine verdict to its own reviewers before opening the case, the sealed order proves nothing. The engine cannot see inside a customer's interface and does not pretend to.</p>
  <p>What it can do is test the arrangement from the outside, using the method substantive audit has always used — and specifically the approach set out publicly by <b>James Stokes of Red Flag AI Pro</b>: place a case with a known answer into the queue, unannounced, and see who catches it.</p>
  <ul>
    <li>A <b>probe</b> is a genuine oversight case whose machine verdict has been deliberately set to a known-wrong value. To the reviewer it is indistinguishable from any other case.</li>
    <li>Agreeing with the planted verdict means the case was not evaluated. That is a caught rubber stamp, sealed like any other event.</li>
    <li>If the interface is leaking the verdict early, a reviewer's agreement rate on probes will track their agreement rate on ordinary cases. If they are deciding blind, it will not. <b>The gap between those two figures is the conformance signal.</b></li>
  </ul>
  <p>A single probe establishes nothing about an individual. A catch rate across dozens is evidence about a process, and the process is what is under audit.</p>

  <h2><span class="n">8.</span>Oversight of the platform itself</h2>
  <p>Monop Content applies the same standard to its own operation. The Founder is the accountable human for the platform (see the Risk Management Policy, MC-POL-001). Platform-level changes deploy only through a version-controlled pipeline attributable to a named commit; the platform cannot alter its own sealed history, and its integrity is continuously checkable by anyone at the public verification endpoint — meaning the platform's overseer is, by design, also overseeable.</p>

  <div class="honest"><b>Honest limits, restated.</b> The platform routes borderline decisions to humans, proves who intervened with what mandate, and establishes that they committed before the answer was disclosed to them. It cannot make the human's judgement correct and does not claim to. A reviewer can leave a screen open, so dwell time is gameable by anyone deliberately gaming it. Authority tokens prove the grant, not the wisdom of granting it. Probes test a process, not a person — someone can catch a probe and rubber stamp the next hundred cases — and an operator who identifies probe cases controls their own interface. Customers remain responsible for staffing oversight roles with competent people; no software discharges that duty for them.</div>

  <hr>
  <footer>
    <p style="margin-top:20px"><a href="/">sebbi.pro</a> · <a href="/risk-policy">Risk Management Policy</a> · <a href="/data-protection">Data Protection Statement</a> · <a href="/whitepaper">Whitepaper</a> · <a href="/contact">Contact</a></p>
    <p style="margin-top:8px;color:var(--faint)">Monop Content · Blyth, Northumberland, UK · justin@monopcontent.com</p>
  </footer>
</div>
</body>
</html>

```


## `identity.html`

151 lines, 9171 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Identity Notary — sebbi.pro</title>
<style>
  :root{--ink:#0a0f1e;--ink2:#10182e;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--ink);color:#fff;font-family:system-ui,sans-serif;min-height:100vh;padding:24px}
  .wrap{max-width:560px;margin:0 auto}
  .brand{font-family:monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.35)}
  h1{font-family:Georgia,serif;font-size:26px;color:var(--gold);margin:14px 0 6px}
  .sub{font-size:13.5px;color:rgba(255,255,255,0.5);line-height:1.7;margin-bottom:22px}
  label{display:block;font-family:monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.45);margin:16px 0 6px}
  input{width:100%;background:var(--ink2);border:1px solid rgba(201,168,76,0.35);color:#fff;border-radius:8px;padding:13px;font-size:15px;outline:none}
  input:focus{border-color:var(--gold)}
  button{width:100%;margin-top:20px;background:var(--gold);color:var(--ink);border:none;border-radius:8px;padding:16px;font-size:16px;font-weight:800;cursor:pointer}
  button:disabled{opacity:0.5}
  #cert{display:none;margin-top:24px;background:var(--ink2);border:2px solid var(--gold);border-radius:12px;padding:28px;text-align:center}
  #cert .seal-ring{width:64px;height:64px;margin:0 auto 14px}
  #cert h2{font-family:Georgia,serif;font-size:22px;color:#fff;margin-bottom:4px}
  #cert .who{font-family:Georgia,serif;font-style:italic;font-size:18px;color:var(--gold);margin-bottom:14px}
  #cert .row{font-family:monospace;font-size:11px;color:rgba(255,255,255,0.6);line-height:2;word-break:break-all;text-align:left;background:rgba(0,0,0,0.3);border-radius:8px;padding:14px;margin-top:10px}
  #cert .row b{color:var(--ok)}
  #status{margin-top:14px;font-family:monospace;font-size:12px;line-height:1.8;word-break:break-all}
  .ok{color:var(--ok)}.err{color:var(--err)}
  .note{margin-top:22px;font-size:12px;color:rgba(255,255,255,0.35);line-height:1.8}
  .note b{color:var(--gold);font-weight:600}
  a{color:var(--gold)}
  .copybtn{background:var(--ink);color:var(--gold);border:1px solid rgba(201,168,76,0.4);margin-top:12px;padding:12px;font-size:13px;font-weight:600}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">sebbi.pro &middot; sovereign identity notary</div>
  <h1>Seal your identity into the chain.</h1>
  <div class="sub">Enter your details below. They are fingerprinted with SHA-256 <b>inside your own browser</b> — the details themselves never leave your device and are never stored. Only the fingerprint is sealed into the live audit chain, creating permanent, tamper-evident proof that this exact identity existed at this exact moment.</div>

  <label>Full name</label>
  <input id="nm" placeholder="Justin Antony Dobson">

  <label>Email</label>
  <input id="em" type="email" placeholder="you@example.com">

  <label>Organisation (optional)</label>
  <input id="org" placeholder="Monop Content">

  <label>Title (optional)</label>
  <input id="ttl" placeholder="Founder">

  <label>One-line bio (optional)</label>
  <input id="bio" placeholder="Building tamper-evident AI compliance from Blyth.">

  <button id="go" onclick="notarise()">Notarise this identity &rarr;</button>
  <div id="status"></div>

  <div id="cert">
    <svg class="seal-ring" viewBox="0 0 32 32"><circle cx="16" cy="16" r="13.5" fill="none" stroke="#c9a84c" stroke-width="2.6" stroke-dasharray="66 20" stroke-linecap="round" transform="rotate(-50 16 16)"/><circle cx="26.5" cy="7" r="3.1" fill="#c9a84c"/><circle cx="16" cy="16" r="3.4" fill="#0a0f1e"/></svg>
    <h2>Certificate of Notarised Identity</h2>
    <div class="who" id="cwho"></div>
    <div class="row" id="crow"></div>
    <canvas id="cardcanvas" width="1200" height="628" style="width:100%;border-radius:8px;margin-top:14px;border:1px solid rgba(201,168,76,0.4)"></canvas>
    <a id="carddl" class="copybtn" style="display:block;text-align:center;text-decoration:none" download="identity-card.png">Download identity card</a>
    <button class="copybtn" onclick="copyCert()">Copy certificate text</button>
  </div>

  <div class="note"><b>Verify any time:</b> re-enter the identical details on this page and the chain will return the same fingerprint, block and timestamp — proof nothing changed. One character different produces a completely different fingerprint. Powered by the same engine that seals AI decisions: <a href="/">free for 90 days &rarr;</a></div>
</div>

<script>
var lastCert="";
async function sha256hex(s){
  var buf=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map(function(b){return b.toString(16).padStart(2,"0");}).join("");
}
async function notarise(){
  var nm=document.getElementById("nm").value.trim();
  var em=document.getElementById("em").value.trim().toLowerCase();
  var org=document.getElementById("org").value.trim();
  var st=document.getElementById("status");
  var cert=document.getElementById("cert");
  cert.style.display="none";
  if(!nm||!em||em.indexOf("@")<0){st.innerHTML="<span class='err'>Name and a valid email are required.</span>";return;}
  var btn=document.getElementById("go");btn.disabled=true;
  st.innerHTML="Fingerprinting in your browser\u2026";
  try{
    var ttl=document.getElementById("ttl").value.trim();var bio=document.getElementById("bio").value.trim();var canonical="identity:v1|"+nm+"|"+em+"|"+org+"|"+ttl+"|"+bio;
    var fp=await sha256hex(canonical);
    st.innerHTML="Fingerprint "+fp.slice(0,20)+"\u2026<br>Sealing into the chain\u2026";
    var r=await fetch("/api/identity/seal",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({fingerprint:fp})});
    var d=await r.json();
    if(!d.sealed){st.innerHTML="<span class='err'>"+(d.error||"Sealing failed")+"</span>";btn.disabled=false;return;}
    var when=new Date((d.sealed_at||Date.now()/1000)*1000);
    document.getElementById("cwho").textContent=nm+(org?(" \u00b7 "+org):"");
    document.getElementById("crow").innerHTML=
      "Fingerprint <b>"+fp+"</b><br>"+
      "Sealed in block <b>#"+d.block_index+"</b> of the live sebbi.pro audit chain<br>"+
      "Seal <b>"+d.seal+"</b><br>"+
      "Timestamp <b>"+when.toLocaleString("en-GB")+"</b><br>"+
      "Chain verification: sebbi.pro/api/inclusion?hash="+d.seal;
    lastCert="CERTIFICATE OF NOTARISED IDENTITY \u2014 sebbi.pro\n"+
      nm+(org?(" \u00b7 "+org):"")+"\n"+
      "Fingerprint: "+fp+"\n"+
      "Block: #"+d.block_index+"\nSeal: "+d.seal+"\n"+
      "Timestamp: "+when.toLocaleString("en-GB")+"\n"+
      "Verify: sebbi.pro/api/inclusion?hash="+d.seal;
    cert.style.display="block";drawCard(nm,ttl,org,bio,fp,d);
    st.innerHTML="<span class='ok'>\u2713 Identity notarised. The details never left this device \u2014 only the fingerprint is in the chain.</span>";
  }catch(e){st.innerHTML="<span class='err'>Network error: "+e+"</span>";}
  btn.disabled=false;
}
function drawCard(nm,ttl,org,bio,fp,d){
  var c=document.getElementById("cardcanvas"),x=c.getContext("2d");
  var W=c.width,H=c.height;
  var g=x.createLinearGradient(0,0,W,H);g.addColorStop(0,"#0a0f1e");g.addColorStop(1,"#141d36");
  x.fillStyle=g;x.fillRect(0,0,W,H);
  x.strokeStyle="#c9a84c";x.lineWidth=6;x.strokeRect(14,14,W-28,H-28);
  x.strokeStyle="rgba(201,168,76,0.35)";x.lineWidth=1.5;x.setLineDash([6,5]);x.strokeRect(30,30,W-60,H-60);x.setLineDash([]);
  x.fillStyle="#c9a84c";x.font="600 22px monospace";x.textAlign="center";
  x.fillText("CERTIFICATE OF NOTARISED IDENTITY",W/2,86);
  x.fillStyle="#ffffff";x.font="900 64px Georgia";
  x.fillText(nm,W/2,180);
  x.fillStyle="#c9a84c";x.font="italic 600 30px Georgia";
  var sub=(ttl?ttl:"")+(ttl&&org?" \u00b7 ":"")+(org?org:"");
  if(sub)x.fillText(sub,W/2,226);
  if(bio){x.fillStyle="rgba(255,255,255,0.65)";x.font="26px Georgia";x.fillText(bio.slice(0,70),W/2,274);}
  /* seal ring */
  x.save();x.translate(W/2,360);x.strokeStyle="#c9a84c";x.lineWidth=7;x.setLineDash([52,16]);
  x.beginPath();x.arc(0,0,44,0,Math.PI*2);x.stroke();x.setLineDash([]);
  x.fillStyle="#c9a84c";x.beginPath();x.arc(30,-30,9,0,7);x.fill();
  x.fillStyle="#0a0f1e";x.beginPath();x.arc(0,0,11,0,7);x.fill();x.restore();
  x.fillStyle="#7fe3b0";x.font="600 21px monospace";
  x.fillText("FINGERPRINT "+fp.slice(0,40)+"\u2026",W/2,452);
  x.fillStyle="rgba(255,255,255,0.6)";x.font="600 21px monospace";
  x.fillText("SEALED IN BLOCK #"+d.block_index+" \u00b7 LIVE SEBBI.PRO AUDIT CHAIN",W/2,490);
  x.fillText(new Date(d.sealed_at*1000).toLocaleString("en-GB"),W/2,524);
  x.fillStyle="#c9a84c";x.font="600 20px monospace";
  x.fillText("verify: sebbi.pro/api/inclusion?hash="+d.seal.slice(0,24)+"\u2026",W/2,572);
  document.getElementById("carddl").href=c.toDataURL("image/png");
}
function copyCert(){
  navigator.clipboard.writeText(lastCert).then(function(){
    document.getElementById("status").innerHTML="<span class='ok'>Certificate copied.</span>";
  });
}
</script>
</body>
</html>

```
