# Codebase — part 27 of 32

Contains:
- `pay-check.html`
- `registry.html`
- `report-threat.html`
- `requirements.txt`


## `pay-check.html`

159 lines, 11880 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Payment Notary — verify before you pay — sebbi.pro</title>
<style>
  :root{--ink:#0a0f1e;--ink2:#10182e;--input:#131e36;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80;--muted:#94a3b8;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--ink);color:#f8fafc;font-family:system-ui,sans-serif;min-height:100vh;padding:26px 16px}
  .container{max-width:1100px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:28px}
  @media(max-width:850px){.container{grid-template-columns:1fr}}
  header{grid-column:1/-1;border-bottom:1px solid rgba(201,168,76,0.2);padding-bottom:16px}
  .brand{font-family:monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.35)}
  h1{font-family:Georgia,serif;font-size:28px;color:var(--gold);margin:8px 0 6px}
  .tagline{color:var(--muted);font-size:13.5px;line-height:1.6;max-width:660px}
  .panel{background:var(--ink2);border:1px solid rgba(201,168,76,0.25);border-radius:12px;padding:24px;display:flex;flex-direction:column;gap:14px}
  h2{font-size:12px;font-family:monospace;text-transform:uppercase;letter-spacing:2px;color:var(--gold);border-bottom:1px dashed rgba(201,168,76,0.2);padding-bottom:8px}
  label{display:block;font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:2px;color:var(--muted);margin-bottom:5px}
  input{width:100%;background:var(--input);border:1px solid rgba(201,168,76,0.3);color:#fff;border-radius:8px;padding:12px;font-size:15px;outline:none;font-family:inherit}
  input:focus{border-color:var(--gold);box-shadow:0 0 8px rgba(201,168,76,0.2)}
  button{width:100%;background:var(--gold);color:var(--ink);border:none;border-radius:8px;padding:15px;font-size:14px;font-weight:800;cursor:pointer;text-transform:uppercase;letter-spacing:1px}
  button:disabled{opacity:0.5}
  #sealres{display:none;margin-top:6px;padding:14px;border-radius:8px;background:rgba(127,227,176,0.08);border:1px solid rgba(127,227,176,0.4);font-family:monospace;font-size:11.5px;line-height:1.9;word-break:break-all}
  #sealres b{color:var(--ok)}
  #sealres .code{font-size:17px;color:var(--gold);font-weight:700}
  #checkres{display:none;margin-top:6px;padding:18px;border-radius:10px;font-size:13.5px;line-height:1.8}
  #checkres.good{display:block;background:rgba(127,227,176,0.08);border:2px solid var(--ok)}
  #checkres.bad{display:block;background:rgba(255,138,128,0.1);border:3px solid var(--err)}
  #checkres .big{font-weight:900;font-size:17px;margin-bottom:6px}
  #checkres.good .big{color:var(--ok)}
  #checkres.bad .big{color:var(--err)}
  #checkres .mono{font-family:monospace;font-size:11px;color:var(--muted);word-break:break-all;line-height:1.9}
  .note{font-size:11px;color:rgba(255,255,255,0.35);line-height:1.7}
  .warnbox{background:rgba(255,138,128,0.06);border:1px solid rgba(255,138,128,0.3);border-radius:8px;padding:12px;font-size:12px;color:#f1b9b3;line-height:1.7}
  a{color:var(--gold)}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">sebbi.pro &middot; payment notary</div>
    <h1>Never pay a switched invoice again.</h1>
    <div class="tagline">Invoice fraud costs the UK &pound;450m a year: criminals intercept a real invoice and switch the bank details. Since October 2024, UK banks must reimburse victims up to &pound;85,000 &mdash; <b>unless the payer failed to take reasonable care.</b> The Payment Notary is how both sides prove care: the business seals its true details once, every invoice carries a short code, and every check you run is itself sealed into the chain &mdash; a timestamped <b style="color:var(--gold)">Verification Receipt</b> proving you checked before you paid. If the details don't match the sealed original &mdash; <b style="color:var(--err)">you don't pay, and your receipt proves you caught it.</b></div>
  </header>

  <!-- LEFT: business seals details -->
  <div class="panel">
    <h2>For businesses &middot; seal your payment details</h2>
    <div><label>Business name</label><input id="biz" placeholder="JustRight Decorators Ltd"></div>
    <div><label>Sort code</label><input id="sort" inputmode="numeric" placeholder="12-34-56"></div>
    <div><label>Account number</label><input id="acct" inputmode="numeric" placeholder="12345678"></div>
    <button id="go" onclick="sealPay()">Seal these details &mdash; free &rarr;</button>
    <div id="sealres"></div>
    <div class="note">Fingerprinted with SHA-256 in your own browser. Your full sort code and account number are <b style="color:var(--gold)">never sent to us and never stored</b> &mdash; only the fingerprint plus a masked display (last digits) so customers can eyeball a match. Print the code on every invoice, email footer and quote.</div>
  </div>

  <!-- RIGHT: customer checks before paying -->
  <div class="panel">
    <h2>Before you pay &middot; check the invoice</h2>
    <div><label>Verification code from the invoice</label><input id="q" placeholder="e.g. 7be4d1c29a03"></div>
    <div><label>Sort code shown on the invoice</label><input id="csort" inputmode="numeric" placeholder="12-34-56"></div>
    <div><label>Account number shown on the invoice</label><input id="cacct" inputmode="numeric" placeholder="12345678"></div>
    <div><label>Business name on the invoice</label><input id="cbiz" placeholder="JustRight Decorators Ltd"></div>
    <button onclick="checkPay()">Check before I pay &rarr;</button>
    <div id="checkres"></div>
    <div class="warnbox">If the check fails, <b>do not send the payment.</b> Phone the business on a number you already know &mdash; not one from the invoice &mdash; and confirm the details by voice. Report suspected fraud to Action Fraud on 0300 123 2040.</div>
  </div>
</div>

<script>
async function sha256hex(s){
  var buf=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map(function(b){return b.toString(16).padStart(2,"0");}).join("");
}
function receiptHtml(rc){
  if(!rc)return "";
  var when=new Date(rc.checked_at*1000).toLocaleString("en-GB");
  return "<div style='margin-top:14px;padding:12px;border:1px dashed rgba(201,168,76,0.5);border-radius:8px;background:rgba(201,168,76,0.06)'>"
    +"<b style='color:var(--gold)'>\u26D3 YOUR VERIFICATION RECEIPT \u2014 keep this</b><br>"
    +"<span class='mono'>Checked: "+when+" \u00b7 result: "+rc.result+"<br>Sealed in block #"+rc.block_index+"<br>Receipt seal: "+rc.seal+"<br>Verify any time: sebbi.pro/api/inclusion?hash="+rc.seal+"</span><br>"
    +"<span style='font-size:11px;color:var(--muted);line-height:1.6'>This receipt is tamper-evident proof that you verified the payee\u2019s details before paying \u2014 the kind of evidence banks consider when assessing reimbursement claims under the 2024 mandatory reimbursement rules. Screenshot it or save the seal.</span></div>";
}
function normSort(s){return (s||"").replace(/[^0-9]/g,"");}
function normAcct(s){return (s||"").replace(/[^0-9]/g,"");}
function canonicalPay(biz,sort,acct){
  return "payment:v1|"+biz.trim().toLowerCase()+"|"+normSort(sort)+"|"+normAcct(acct);
}
async function sealPay(){
  var biz=document.getElementById("biz").value.trim();
  var sort=document.getElementById("sort").value;
  var acct=document.getElementById("acct").value;
  var res=document.getElementById("sealres");
  if(!biz||normSort(sort).length!==6||normAcct(acct).length<7){
    res.style.display="block";res.innerHTML="<span style='color:var(--err)'>Business name, 6-digit sort code and account number required.</span>";return;
  }
  var btn=document.getElementById("go");btn.disabled=true;btn.textContent="Sealing\u2026";
  try{
    var fp=await sha256hex(canonicalPay(biz,sort,acct));
    var ns=normSort(sort),na=normAcct(acct);
    var display={business:biz,sort_masked:"**-**-"+ns.slice(4),account_masked:"****"+na.slice(-4)};
    var r=await fetch("/api/payment/seal",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({fingerprint:fp,display:display})});
    var d=await r.json();
    if(!d.sealed){res.style.display="block";res.innerHTML="<span style='color:var(--err)'>"+(d.error||"Sealing failed")+"</span>";btn.disabled=false;btn.textContent="Seal these details \u2014 free \u2192";return;}
    var when=new Date(d.sealed_at*1000).toLocaleString("en-GB");
    res.style.display="block";
    res.innerHTML=(d.already_registered?"<b>Already sealed.</b> These exact details were registered earlier.<br>":"<b>\u2713 SEALED.</b> Your true payment details are now locked in the chain.<br>")
      +"Registered: "+when+" \u00b7 block #"+d.block_index+"<br><br>"
      +"<b>Print this on every invoice:</b><br>"
      +"\u26D3 Verify our bank details before paying:<br>sebbi.pro/pay-check \u00b7 code <span class='code'>"+d.code+"</span>";
    btn.textContent="Sealed \u2713";
  }catch(e){res.style.display="block";res.innerHTML="<span style='color:var(--err)'>Network error: "+e+"</span>";btn.disabled=false;btn.textContent="Seal these details \u2014 free \u2192";}
}
async function checkPay(){
  var code=document.getElementById("q").value.trim().toLowerCase().replace(/[^0-9a-f]/g,"");
  var biz=document.getElementById("cbiz").value.trim();
  var sort=document.getElementById("csort").value;
  var acct=document.getElementById("cacct").value;
  var out=document.getElementById("checkres");
  if(code.length<12){out.className="bad";out.innerHTML="<div class='big'>Enter the 12-character code from the invoice.</div>";return;}
  if(!biz||normSort(sort).length!==6||normAcct(acct).length<7){
    out.className="bad";out.innerHTML="<div class='big'>Enter the business name, sort code and account number exactly as shown on the invoice.</div>";return;
  }
  out.className="";out.style.display="block";out.innerHTML="Checking the chain\u2026";
  try{
    var fp=await sha256hex(canonicalPay(biz,sort,acct));
    var r=await fetch("/api/payment/check?code="+code+"&fp="+fp);
    var d=await r.json();
    if(!d.found){
      out.className="bad";
      out.innerHTML="<div class='big'>\u2717 NO SEAL FOUND \u2014 DO NOT PAY</div>No business has sealed payment details under this code. Either the code is mistyped \u2014 or the invoice is fraudulent. Phone the business on a number you already know before sending anything."
        +receiptHtml(d.receipt);
      return;
    }
    if(d.match){
      var when=new Date(d.registered_at*1000).toLocaleString("en-GB");
      var disp=d.display||{};
      out.className="good";
      out.innerHTML="<div class='big'>\u2713 DETAILS MATCH THE SEALED ORIGINAL</div>"
        +"The details on this invoice are identical to the ones <b>"+(disp.business||"this business")+"</b> sealed on "+when+" (block #"+d.block_index+").<br>"
        +"<span class='mono'>Sealed record: "+(disp.business||"")+" \u00b7 "+(disp.sort_masked||"")+" \u00b7 "+(disp.account_masked||"")+"</span><br>"
        +"Safe to proceed \u2014 nothing has been switched."
        +receiptHtml(d.receipt);
    }else{
      var disp2=d.display||{};
      out.className="bad";
      out.innerHTML="<div class='big'>\u26A0\uFE0F DETAILS DO NOT MATCH \u2014 DO NOT PAY</div>"
        +"A seal exists under this code, but the details on your invoice are <b>different from the sealed original</b>. This is exactly what invoice fraud looks like \u2014 the bank details may have been switched.<br>"
        +"<span class='mono'>Sealed original: "+(disp2.business||"")+" \u00b7 "+(disp2.sort_masked||"")+" \u00b7 "+(disp2.account_masked||"")+"</span><br>"
        +"Phone the business on a number you already know. Report to Action Fraud: 0300 123 2040."
        +receiptHtml(d.receipt);
    }
  }catch(e){out.className="bad";out.innerHTML="<div class='big'>Network error</div>"+e;}
}
</script>
</body>
</html>

```


## `registry.html`

533 lines, 29846 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Safe AI Registry — a registry you don't have to trust</title>
<meta name="description" content="The register that publishes proofs about its own behaviour. Absence proofs, RFC 6962 append-only proofs, sealed revocations. Checkable against its own operator.">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#04040a;
  --surface:#08080f;
  --surface2:#0d0d18;
  --border:#141428;
  --border2:#1e1e38;
  --gold:#c9a84c;
  --gold2:#e8c96a;
  --green:#00e5a0;
  --red:#ff3d5a;
  --blue:#4d9fff;
  --purple:#8b5cf6;
  --text:#e8e8f8;
  --muted:#4a4a6a;
  --muted2:#6a6a8a;
  --mono:'IBM Plex Mono',monospace;
  --sans:'IBM Plex Sans',sans-serif;
}

html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--sans);min-height:100vh}

nav{position:fixed;top:0;left:0;right:0;z-index:100;height:52px;display:flex;align-items:center;justify-content:space-between;padding:0 32px;background:rgba(4,4,10,0.9);backdrop-filter:blur(16px);border-bottom:1px solid var(--border)}
.nav-logo{font-family:var(--mono);font-size:13px;color:var(--gold);text-decoration:none}
.nav-links{display:flex;gap:20px;align-items:center}
.nav-links a{font-family:var(--mono);font-size:11px;color:var(--muted2);text-decoration:none;transition:color .2s}.nav-links a:hover{color:var(--text)}
.nav-cta{color:var(--gold)!important}

.hero{padding:100px 32px 60px;max-width:1000px;margin:0 auto;text-align:center}
.eyebrow{font-family:var(--mono);font-size:10px;color:var(--green);letter-spacing:0.2em;text-transform:uppercase;margin-bottom:20px;display:flex;align-items:center;justify-content:center;gap:10px}
.eyebrow::before,.eyebrow::after{content:'';width:24px;height:1px;background:var(--green);opacity:0.5}

h1{font-size:clamp(32px,5vw,56px);font-weight:700;letter-spacing:-0.03em;line-height:1.05;margin-bottom:16px}
h1 span{color:var(--gold)}
.hero-sub{font-size:16px;color:var(--muted2);line-height:1.7;max-width:620px;margin:0 auto 40px;font-weight:300}

/* STATS */
.stats-row{display:flex;justify-content:center;gap:48px;margin-bottom:48px;flex-wrap:wrap}
.stat-item{text-align:center}
.stat-n{font-family:var(--mono);font-size:36px;color:var(--gold);font-weight:700;line-height:1}
.stat-l{font-size:11px;color:var(--muted2);margin-top:4px;text-transform:uppercase;letter-spacing:0.1em}

/* LIVE TICKER */
.ticker-wrap{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 20px;display:flex;align-items:center;gap:12px;max-width:640px;margin:0 auto 48px;overflow:hidden}
.ticker-dot{width:8px;height:8px;background:var(--green);border-radius:50%;animation:pulse 2s infinite;flex-shrink:0}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.5;transform:scale(0.8)}}
.ticker-text{font-family:var(--mono);font-size:11px;color:var(--green);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* MAIN */
.main{max-width:1000px;margin:0 auto;padding:0 32px 80px}

.section-title{font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:0.1em;text-transform:uppercase;margin-bottom:14px}

/* SEARCH */
.search-wrap{margin-bottom:32px;position:relative}
.search-input{width:100%;background:var(--surface);border:1px solid var(--border2);color:var(--text);padding:14px 20px 14px 48px;font-size:14px;font-family:var(--sans);border-radius:8px;outline:none;transition:border-color .2s}
.search-input:focus{border-color:var(--gold)}
.search-icon{position:absolute;left:16px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:16px}

/* FILTER TABS */
.filter-tabs{display:flex;gap:8px;margin-bottom:24px;flex-wrap:wrap}
.filter-tab{font-family:var(--mono);font-size:11px;padding:6px 14px;border-radius:20px;border:1px solid var(--border);color:var(--muted2);cursor:pointer;transition:all .2s;background:none}
.filter-tab.active{background:rgba(201,168,76,0.1);border-color:var(--gold);color:var(--gold)}
.filter-tab:hover{border-color:var(--muted2);color:var(--text)}

/* REGISTRY TABLE */
.registry-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:32px}
.registry-header{padding:14px 20px;background:var(--surface2);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.registry-header-title{font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:0.1em;text-transform:uppercase}
.registry-count{font-family:var(--mono);font-size:11px;color:var(--muted)}

.reg-table{width:100%;border-collapse:collapse}
.reg-table th{padding:10px 16px;text-align:left;font-family:var(--mono);font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:0.1em;border-bottom:1px solid var(--border);background:rgba(0,0,0,0.2)}
.reg-table td{padding:14px 16px;border-bottom:1px solid rgba(255,255,255,0.03);vertical-align:middle}
.reg-table tr:last-child td{border-bottom:none}
.reg-table tr:hover td{background:rgba(255,255,255,0.01)}

.domain-cell{font-family:var(--mono);font-size:13px;color:var(--text);display:flex;align-items:center;gap:8px}
.domain-verified{width:16px;height:16px;background:var(--green);border-radius:50%;display:flex;align-items:center;justify-content:center;color:#000;font-size:9px;font-weight:700;flex-shrink:0}
.domain-unverified{width:16px;height:16px;background:var(--gold);border-radius:50%;display:flex;align-items:center;justify-content:center;color:#000;font-size:9px;font-weight:700;flex-shrink:0}
.domain-gone{width:16px;height:16px;background:var(--muted);border-radius:50%;display:flex;align-items:center;justify-content:center;color:#000;font-size:9px;font-weight:700;flex-shrink:0}

.status-badge{font-family:var(--mono);font-size:9px;padding:3px 8px;border-radius:3px;font-weight:600;letter-spacing:0.05em;cursor:help}
.status-verified{background:rgba(0,229,160,0.12);color:var(--green);border:1px solid rgba(0,229,160,0.2)}
.status-self{background:rgba(201,168,76,0.12);color:var(--gold);border:1px solid rgba(201,168,76,0.2)}
.status-pending{background:rgba(74,74,106,0.2);color:var(--muted2);border:1px solid var(--border)}
.status-bad{background:rgba(255,61,90,0.1);color:var(--red);border:1px solid rgba(255,61,90,0.2)}

.reg-flags{display:flex;gap:4px;flex-wrap:wrap}
.reg-flag{font-family:var(--mono);font-size:9px;color:var(--blue);background:rgba(77,159,255,0.08);border:1px solid rgba(77,159,255,0.15);padding:1px 5px;border-radius:2px}
.reg-flag-bad{color:var(--red);background:rgba(255,61,90,0.07);border-color:rgba(255,61,90,0.15)}

.hash-cell{font-family:var(--mono);font-size:10px;color:var(--muted);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* PROOF DESK */
.proof-section{background:var(--surface);border:1px solid var(--border2);border-radius:12px;padding:28px;margin-bottom:32px}
.proof-section h2{font-size:22px;font-weight:700;letter-spacing:-0.02em;margin-bottom:8px}
.proof-lead{font-size:14px;color:var(--muted2);line-height:1.7;margin-bottom:20px}
.proof-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.proof-input{flex:1;min-width:180px;background:rgba(0,0,0,0.35);border:1px solid var(--border2);color:var(--text);padding:11px 14px;font-size:13px;font-family:var(--mono);border-radius:6px;outline:none}
.proof-input:focus{border-color:var(--gold)}
.proof-btn{background:rgba(201,168,76,0.12);border:1px solid var(--gold);color:var(--gold);padding:11px 18px;font-size:12px;font-family:var(--mono);border-radius:6px;cursor:pointer;transition:all .2s;white-space:nowrap}
.proof-btn:hover{background:rgba(201,168,76,0.2)}
.proof-out{background:#000;border:1px solid var(--border);border-radius:6px;padding:14px;font-family:var(--mono);font-size:11px;color:var(--muted2);line-height:1.6;white-space:pre-wrap;word-break:break-all;max-height:320px;overflow:auto;display:none}
.proof-out.show{display:block}
.proof-verdict{font-family:var(--mono);font-size:12px;font-weight:700;margin-bottom:10px;display:block}
.verdict-absent{color:var(--green)}
.verdict-present{color:var(--gold)}
.verdict-err{color:var(--red)}

/* APPLY SECTION */
.apply-section{background:linear-gradient(135deg,rgba(0,229,160,0.06),rgba(0,229,160,0.01));border:1px solid rgba(0,229,160,0.15);border-radius:12px;padding:36px;text-align:center;margin-bottom:32px}
.apply-section h2{font-size:24px;font-weight:700;letter-spacing:-0.02em;margin-bottom:8px}
.apply-section p{font-size:14px;color:var(--muted2);line-height:1.7;max-width:520px;margin:0 auto 24px}

.apply-form{max-width:520px;margin:0 auto;text-align:left}
.apply-step{font-family:var(--mono);font-size:10px;color:var(--green);letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px}
.apply-input{width:100%;background:rgba(0,0,0,0.3);border:1px solid rgba(0,229,160,0.2);color:var(--text);padding:12px 16px;font-size:14px;font-family:var(--mono);border-radius:6px;outline:none;margin-bottom:10px;transition:border-color .2s}
.apply-input:focus{border-color:var(--green)}
.apply-input::placeholder{color:var(--muted)}
.apply-btn{width:100%;background:linear-gradient(135deg,var(--green),#00b87d);color:#000;border:none;padding:13px;font-size:14px;font-weight:700;font-family:var(--sans);border-radius:6px;cursor:pointer;transition:all .2s}
.apply-btn:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(0,229,160,0.2)}
.apply-btn:disabled{opacity:.4;cursor:not-allowed;transform:none;box-shadow:none}
.apply-panel{display:none;margin-top:18px;padding-top:18px;border-top:1px solid rgba(0,229,160,0.15)}
.apply-panel.show{display:block}
.token-box{background:#000;border:1px solid rgba(0,229,160,0.25);border-radius:6px;padding:12px;font-family:var(--mono);font-size:11px;color:var(--green);word-break:break-all;margin-bottom:10px}
.apply-note{font-family:var(--mono);font-size:11px;color:var(--muted2);line-height:1.7;margin-bottom:12px}
.apply-result{font-family:var(--mono);font-size:11px;line-height:1.6;white-space:pre-wrap;word-break:break-all;color:var(--muted2);margin-top:10px;display:none}
.apply-result.show{display:block}

/* WHAT VERIFIED MEANS */
.verified-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:32px}
.verified-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px}
.verified-card-icon{font-size:20px;margin-bottom:10px}
.verified-card-title{font-size:13px;font-weight:600;margin-bottom:6px}
.verified-card-desc{font-size:12px;color:var(--muted2);line-height:1.6}

/* NOT SECTION */
.not-card{background:var(--surface2);border:1px solid var(--border2);border-radius:10px;padding:24px;margin-bottom:32px}
.not-card h3{font-size:14px;font-weight:600;margin-bottom:12px}
.not-card ul{list-style:none}
.not-card li{font-size:12px;color:var(--muted2);line-height:1.7;padding-left:18px;position:relative;margin-bottom:6px}
.not-card li::before{content:'—';position:absolute;left:0;color:var(--muted)}

.footnote{font-family:var(--mono);font-size:10px;color:var(--muted);line-height:1.8;text-align:center}
.footnote a{color:var(--muted2);text-decoration:none;border-bottom:1px solid var(--border2)}
.footnote a:hover{color:var(--gold)}

@media(max-width:700px){
  nav{padding:0 16px}
  .hero{padding:80px 16px 40px}
  .main{padding:0 16px 60px}
  .verified-grid{grid-template-columns:1fr}
  .stats-row{gap:24px}
  .proof-section{padding:20px}
  .apply-section{padding:24px 18px}
  .reg-table th:nth-child(4),.reg-table td:nth-child(4){display:none}
  .reg-table th:nth-child(5),.reg-table td:nth-child(5){display:none}
}
</style>
</head>
<body>

<nav>
  <a href="/" class="nav-logo">sebbi.pro</a>
  <div class="nav-links">
    <a href="/ai-standard">ai.txt Standard</a>
    <a href="/x/register/spec">Spec</a>
    <a href="/#signup" class="nav-cta">Get API Key →</a>
  </div>
</nav>

<div class="hero">
  <div class="eyebrow">Safe AI Registry</div>
  <h1>A registry you<br><span>don't have to trust.</span></h1>
  <p class="hero-sub">Every other registry is a database its operator can edit. Entries get back-dated, listings get quietly dropped, and you have to take the registrar's word for all of it. This one publishes proofs about its own behaviour — including proof of what it hasn't done.</p>

  <div class="stats-row">
    <div class="stat-item"><div class="stat-n" id="stat-listed">—</div><div class="stat-l">Listed Domains</div></div>
    <div class="stat-item"><div class="stat-n" id="stat-passed">—</div><div class="stat-l">Checks Passed</div></div>
    <div class="stat-item"><div class="stat-n" id="stat-events">—</div><div class="stat-l">Register Events</div></div>
    <div class="stat-item"><div class="stat-n" id="stat-suite">OAAS-1.0</div><div class="stat-l">Standard Version</div></div>
  </div>

  <div class="ticker-wrap">
    <div class="ticker-dot"></div>
    <div class="ticker-text" id="ticker-text">Loading register state…</div>
  </div>
</div>

<div class="main">

  <!-- WHAT THIS DOES THAT NOTHING ELSE DOES -->
  <div class="section-title">// What this register proves about itself</div>
  <div class="verified-grid">
    <div class="verified-card">
      <div class="verified-card-icon">🚫</div>
      <div class="verified-card-title">Proof of absence</div>
      <div class="verified-card-desc">Ask whether a domain was listed on a given date and get a cryptographic answer, not a lookup. Two adjacent leaves with consecutive indices in a sorted tree sealed at that date — nothing can sit between them. A false claim of past certification is disproved by arithmetic.</div>
    </div>
    <div class="verified-card">
      <div class="verified-card-icon">⛓️</div>
      <div class="verified-card-title">Append-only, provably</div>
      <div class="verified-card-desc">An RFC 6962 consistency proof shows the register at any past size is a prefix of the register now. No entry has been inserted behind an earlier position — including by the operator. It verifies with any standard Certificate Transparency verifier, not one of ours.</div>
    </div>
    <div class="verified-card">
      <div class="verified-card-icon">📌</div>
      <div class="verified-card-title">Revocations stay readable</div>
      <div class="verified-card-desc">A delisted entry is not deleted. The revocation is sealed with its reason and the full history stays public. Listed from one date, revoked on another, and why — permanently. No badge scheme does this, because quietly dropping customers is the point of a badge.</div>
    </div>
    <div class="verified-card">
      <div class="verified-card-icon">🔑</div>
      <div class="verified-card-title">Nobody is listed by us</div>
      <div class="verified-card-desc">A domain lists itself by serving a one-time token at its own address. The operator cannot add you, and cannot claim you asked. Domain control is proved the same way withdrawal is proved.</div>
    </div>
  </div>

  <!-- PROOF DESK -->
  <div class="proof-section" id="proofs">
    <h2>Check the register against itself.</h2>
    <p class="proof-lead">No account, no key. Type any domain — one that is listed, one that never was, one that was removed. The answer comes back as a proof you can recompute yourself.</p>

    <div class="proof-row">
      <input class="proof-input" id="absence-domain" placeholder="example.com" spellcheck="false">
      <input class="proof-input" id="absence-date" placeholder="2026-01-01 (optional)" spellcheck="false" style="max-width:200px">
      <button class="proof-btn" onclick="runAbsence()">Prove listed or not →</button>
    </div>
    <div class="proof-out" id="absence-out"></div>

    <div style="height:18px"></div>

    <div class="proof-row">
      <input class="proof-input" id="cons-first" placeholder="tree size you already hold" spellcheck="false">
      <button class="proof-btn" onclick="runConsistency()">Prove append-only →</button>
    </div>
    <div class="proof-out" id="cons-out"></div>
  </div>

  <!-- SEARCH -->
  <div class="search-wrap">
    <span class="search-icon">🔍</span>
    <input class="search-input" type="text" id="search-input" placeholder="Search the register..." oninput="renderRegistry()">
  </div>

  <!-- FILTER TABS -->
  <div class="filter-tabs">
    <button class="filter-tab active" onclick="setFilter('all',this)">All</button>
    <button class="filter-tab" onclick="setFilter('checks-passed',this)">Checks passed</button>
    <button class="filter-tab" onclick="setFilter('checks-failed',this)">Checks failed</button>
    <button class="filter-tab" onclick="setFilter('stale',this)">Stale</button>
    <button class="filter-tab" onclick="setFilter('gone',this)">Withdrawn / revoked</button>
  </div>

  <!-- REGISTRY TABLE -->
  <div class="registry-card">
    <div class="registry-header">
      <div class="registry-header-title">// Register</div>
      <div class="registry-count" id="registry-count">loading…</div>
    </div>
    <div style="overflow-x:auto">
      <table class="reg-table">
        <thead>
          <tr>
            <th>Domain</th>
            <th>Status</th>
            <th>Failing checks</th>
            <th>Last checked</th>
            <th>Listed since</th>
          </tr>
        </thead>
        <tbody id="registry-tbody">
          <tr><td colspan="5" style="padding:32px;text-align:center;color:var(--muted);font-family:var(--mono);font-size:12px">Loading register…</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- WHAT THIS IS NOT -->
  <div class="not-card">
    <h3>What a listing is not</h3>
    <ul>
      <li>Not a certification. Nobody has been certified by anyone.</li>
      <li>Not a statement that any law applies to a listed domain, or that a listed domain satisfies it. Whether a regulation applies to an organisation is a question for that organisation's own advisers.</li>
      <li>Not an audit. No third party has audited this register or any domain on it.</li>
      <li>Not a claim about anything a domain did not seal. A check observes what a URL served at a moment in time.</li>
      <li>Being listed and being sealed are separate things, and neither is consent to the other.</li>
    </ul>
  </div>

  <!-- APPLY -->
  <div class="apply-section" id="join">
    <h2>List your own domain.</h2>
    <p>Two steps, no account, no approval queue. You prove you control the domain and the register runs its checks in the open. Free.</p>
    <div class="apply-form">
      <div class="apply-step">Step 1 — request a token</div>
      <input class="apply-input" type="text" id="apply-domain" placeholder="yourdomain.com" spellcheck="false">
      <button class="apply-btn" onclick="getChallenge()" id="challenge-btn">Request token →</button>

      <div class="apply-panel" id="apply-panel">
        <div class="apply-step">Step 2 — serve it, then claim</div>
        <div class="token-box" id="token-box"></div>
        <div class="apply-note" id="token-note"></div>
        <button class="apply-btn" onclick="doClaim()" id="claim-btn">I've served it — claim my listing →</button>
      </div>
      <div class="apply-result" id="apply-result"></div>
    </div>
  </div>

  <div class="footnote">
    Suite <span id="foot-suite">—</span> · every route on this page is public and unauthenticated ·
    <a href="/x/register/spec">spec</a> ·
    <a href="/x/register/list">raw list</a> ·
    <a href="/x/register/checkpoints">checkpoints</a> ·
    <a href="/x/register/roots">live roots</a> ·
    <a href="/x/register/sealcheck">seal check</a>
  </div>

</div>

<script>
var REG = { entries: [], filter: 'all', token: null, domain: null };

function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }

function shortDate(iso){ return iso ? String(iso).slice(0,10) : '—'; }

// ---------------------------------------------------------------- load
function loadRegister(){
  fetch('/x/register/list').then(function(r){ return r.json(); }).then(function(d){
    REG.entries = d.entries || [];
    var passed = REG.entries.filter(function(e){ return e.status === 'checks-passed'; }).length;
    var live = REG.entries.filter(function(e){
      return ['unverified','checks-passed','checks-failed','stale'].indexOf(e.status) >= 0; }).length;
    document.getElementById('stat-listed').textContent = live;
    document.getElementById('stat-passed').textContent = passed;
    document.getElementById('foot-suite').textContent = d.suite_version || '—';

    var cp = d.latest_checkpoint;
    if (cp) {
      document.getElementById('stat-events').textContent = cp.tree_size;
      document.getElementById('ticker-text').textContent =
        'Register live · ' + live + ' listed · ' + cp.tree_size + ' sealed events · checkpoint ' +
        shortDate(cp.at) + ' · event root ' + String(cp.event_root).slice(0,16) + '…';
      if (!document.getElementById('cons-first').value) {
        document.getElementById('cons-first').value = Math.max(1, cp.tree_size - 1);
      }
    } else {
      document.getElementById('stat-events').textContent = '0';
      document.getElementById('ticker-text').textContent =
        'Register live · no checkpoint sealed yet · absence proofs available once the first checkpoint is sealed';
    }
    renderRegistry();
  }).catch(function(){
    document.getElementById('ticker-text').textContent = 'Register unreachable — try /x/register/list directly';
    document.getElementById('registry-tbody').innerHTML =
      '<tr><td colspan="5" style="padding:32px;text-align:center;color:var(--red);font-family:var(--mono);font-size:12px">Could not reach /x/register/list</td></tr>';
    document.getElementById('registry-count').textContent = '—';
  });
}

// ---------------------------------------------------------------- table
function setFilter(f, btn){
  REG.filter = f;
  var tabs = document.querySelectorAll('.filter-tab');
  for (var i=0;i<tabs.length;i++) tabs[i].classList.remove('active');
  btn.classList.add('active');
  renderRegistry();
}

function renderRegistry(){
  var search = (document.getElementById('search-input').value || '').toLowerCase();
  var f = REG.filter;
  var rows = REG.entries.filter(function(e){
    if (search && e.domain.indexOf(search) < 0) return false;
    if (f === 'all') return true;
    if (f === 'gone') return e.status === 'withdrawn' || e.status === 'revoked';
    return e.status === f;
  });

  document.getElementById('registry-count').textContent =
    rows.length + ' entr' + (rows.length === 1 ? 'y' : 'ies');

  var tbody = document.getElementById('registry-tbody');
  if (!rows.length){
    tbody.innerHTML = '<tr><td colspan="5" style="padding:32px;text-align:center;color:var(--muted);font-family:var(--mono);font-size:12px">Nothing matches this filter. You can still prove a domain\'s absence above.</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map(function(e){
    var cls = 'status-pending', icon = 'domain-unverified', ic = '~';
    if (e.status === 'checks-passed'){ cls='status-verified'; icon='domain-verified'; ic='✓'; }
    else if (e.status === 'checks-failed'){ cls='status-bad'; icon='domain-unverified'; ic='!'; }
    else if (e.status === 'withdrawn' || e.status === 'revoked'){ cls='status-pending'; icon='domain-gone'; ic='×'; }

    var failed = (e.failed_checks || []);
    var flags = failed.length
      ? failed.map(function(x){ return '<span class="reg-flag reg-flag-bad">'+esc(x)+'</span>'; }).join('')
      : (e.status === 'checks-passed' ? '<span class="reg-flag">all checks passed</span>' : '<span class="reg-flag">—</span>');
    if (e.reason) flags += '<span class="reg-flag reg-flag-bad">'+esc(e.reason)+'</span>';

    return '<tr>'
      + '<td><div class="domain-cell"><div class="'+icon+'">'+ic+'</div>'
      +   '<a href="/x/register/entry?domain='+encodeURIComponent(e.domain)+'" style="color:inherit;text-decoration:none">'+esc(e.domain)+'</a></div></td>'
      + '<td><span class="status-badge '+cls+'" title="'+esc(e.status_means||'')+'">'+esc(e.status.toUpperCase())+'</span></td>'
      + '<td><div class="reg-flags">'+flags+'</div></td>'
      + '<td class="hash-cell">'+shortDate(e.last_checked)+'</td>'
      + '<td style="font-family:var(--mono);font-size:11px;color:var(--muted)">'+shortDate(e.first_listed)+'</td>'
      + '</tr>';
  }).join('');
}

// ---------------------------------------------------------------- proofs
function runAbsence(){
  var d = (document.getElementById('absence-domain').value || '').trim().toLowerCase();
  var at = (document.getElementById('absence-date').value || '').trim();
  var out = document.getElementById('absence-out');
  if (!d){ out.className='proof-out show'; out.innerHTML='<span class="proof-verdict verdict-err">Enter a domain.</span>'; return; }

  out.className = 'proof-out show';
  out.textContent = 'Checking…';

  var url = '/x/register/absence?domain=' + encodeURIComponent(d) + (at ? '&at=' + encodeURIComponent(at) : '');
  fetch(url).then(function(r){ return r.json(); }).then(function(j){
    if (j.error){
      out.innerHTML = '<span class="proof-verdict verdict-err">' + esc(j.error) + '</span>'
        + esc(JSON.stringify(j, null, 2));
      return;
    }
    var head = j.present
      ? '<span class="proof-verdict verdict-present">LISTED at the checkpoint shown — inclusion proof below</span>'
      : '<span class="proof-verdict verdict-absent">NOT LISTED — absence proof below</span>';
    out.innerHTML = head + esc(j.proves || '') + '\n\n' + esc(JSON.stringify(j, null, 2));
  }).catch(function(){
    out.innerHTML = '<span class="proof-verdict verdict-err">Request failed.</span>';
  });
}

function runConsistency(){
  var first = (document.getElementById('cons-first').value || '').trim();
  var out = document.getElementById('cons-out');
  if (!first){ out.className='proof-out show'; out.innerHTML='<span class="proof-verdict verdict-err">Enter a tree size.</span>'; return; }
  out.className = 'proof-out show';
  out.textContent = 'Building proof…';
  fetch('/x/register/consistency?first=' + encodeURIComponent(first)).then(function(r){ return r.json(); }).then(function(j){
    if (j.error){
      out.innerHTML = '<span class="proof-verdict verdict-err">' + esc(j.error) + '</span>' + esc(JSON.stringify(j,null,2));
      return;
    }
    out.innerHTML = '<span class="proof-verdict verdict-absent">APPEND-ONLY PROOF</span>'
      + esc(j.proves || '') + '\n\n' + esc(JSON.stringify(j, null, 2));
  }).catch(function(){
    out.innerHTML = '<span class="proof-verdict verdict-err">Request failed.</span>';
  });
}

// ---------------------------------------------------------------- join
function getChallenge(){
  var d = (document.getElementById('apply-domain').value || '').trim().toLowerCase();
  var res = document.getElementById('apply-result');
  if (!d){ res.className='apply-result show'; res.textContent='Enter a domain.'; return; }

  var btn = document.getElementById('challenge-btn');
  btn.disabled = true; btn.textContent = 'Requesting…';

  fetch('/x/register/challenge', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({domain: d})
  }).then(function(r){ return r.json(); }).then(function(j){
    btn.disabled = false; btn.textContent = 'Request token →';
    if (j.error){
      res.className='apply-result show';
      res.textContent = j.error + (j.detail ? '\n\n' + j.detail : '') + '\n\n' + JSON.stringify(j, null, 2);
      return;
    }
    REG.token = j.token; REG.domain = j.domain;
    document.getElementById('token-box').textContent = j.token;
    document.getElementById('token-note').innerHTML =
      'Serve that exact string at <strong>https://' + esc(j.domain) + '/.well-known/aileash-register.txt</strong><br>'
      + 'or add the line <strong>Register-Token: ' + esc(j.token) + '</strong> to <strong>https://' + esc(j.domain) + '/ai.txt</strong><br><br>'
      + 'Expires ' + esc(j.expires_at) + '. Only the token\'s digest is sealed, never the token itself.';
    document.getElementById('apply-panel').classList.add('show');
    res.className = 'apply-result';
  }).catch(function(){
    btn.disabled = false; btn.textContent = 'Request token →';
    res.className='apply-result show'; res.textContent = 'Request failed.';
  });
}

function doClaim(){
  var res = document.getElementById('apply-result');
  var btn = document.getElementById('claim-btn');
  if (!REG.domain){ res.className='apply-result show'; res.textContent='Request a token first.'; return; }
  btn.disabled = true; btn.textContent = 'Fetching your token and running checks…';

  fetch('/x/register/claim', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({domain: REG.domain})
  }).then(function(r){ return r.json(); }).then(function(j){
    btn.disabled = false; btn.textContent = "I've served it — claim my listing →";
    res.className = 'apply-result show';
    if (!j.ok){
      res.textContent = (j.error || 'Claim refused') + '\n\n' + JSON.stringify(j, null, 2);
      return;
    }
    res.textContent = 'Listed as ' + j.status + '.\n' + (j.status_means || '')
      + '\n\nSealed: ' + (j.sealed && j.sealed.audit_hash ? j.sealed.audit_hash : '—')
      + '\n\n' + JSON.stringify(j.checks, null, 2);
    loadRegister();
  }).catch(function(){
    btn.disabled = false; btn.textContent = "I've served it — claim my listing →";
    res.className='apply-result show'; res.textContent = 'Request failed.';
  });
}

loadRegister();
</script>

</body>
</html>

```


## `report-threat.html`

272 lines, 14806 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash Guardian &mdash; Report a Threat</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0f1e;color:#fff;min-height:100vh;padding:24px;max-width:600px;margin:0 auto}
.logo{font-size:22px;font-weight:900;text-align:center;margin-bottom:4px}.logo span{color:#c9a84c}
.sub{font-family:monospace;font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;text-align:center;margin-bottom:8px}

.nav-links{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-bottom:28px}
.nav-links a{font-family:monospace;font-size:10px;color:rgba(255,255,255,0.4);text-decoration:none;padding:5px 10px;border:1px solid rgba(255,255,255,0.1);border-radius:4px;letter-spacing:1px;text-transform:uppercase;transition:all .2s}
.nav-links a:hover{color:#c9a84c;border-color:rgba(201,168,76,0.4)}

.intro{background:rgba(201,168,76,0.06);border:1px solid rgba(201,168,76,0.2);border-radius:8px;padding:18px;margin-bottom:20px;font-size:13px;color:rgba(255,255,255,0.7);line-height:1.75}
.intro strong{color:#c9a84c;display:block;margin-bottom:6px;font-size:14px}

.card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:20px;margin-bottom:16px}
.card-title{font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:4px}
.card-desc{font-size:12px;color:rgba(255,255,255,0.4);margin-bottom:14px;line-height:1.6}

.field{margin-bottom:12px}
.field label{display:block;font-family:monospace;font-size:10px;color:rgba(255,255,255,0.4);letter-spacing:1px;text-transform:uppercase;margin-bottom:6px}
.field input,.field textarea,.field select{width:100%;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.12);color:#fff;padding:12px 14px;font-size:14px;border-radius:6px;outline:none;font-family:inherit;transition:border-color .2s}
.field input:focus,.field textarea:focus,.field select:focus{border-color:rgba(201,168,76,0.5)}
.field textarea{height:100px;resize:vertical}
.field input::placeholder,.field textarea::placeholder{color:rgba(255,255,255,0.25)}
.field select option{background:#0a0f1e}

.evidence-label{font-family:monospace;font-size:9px;color:#ff6b6b;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px;margin-top:10px}
.evidence-box{background:rgba(0,0,0,0.3);border:1px solid rgba(255,107,107,0.2);border-radius:6px;padding:12px;font-family:monospace;font-size:11px;color:rgba(255,255,255,0.6);line-height:1.8;word-break:break-all;margin-bottom:4px}

.severity{display:inline-block;padding:4px 12px;border-radius:4px;font-family:monospace;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin:10px 0}
.sev-critical{background:rgba(204,0,0,0.2);border:1px solid rgba(204,0,0,0.4);color:#ff6b6b}
.sev-high{background:rgba(201,168,76,0.2);border:1px solid rgba(201,168,76,0.4);color:#c9a84c}

.steps{margin-bottom:0}
.step{display:flex;gap:12px;align-items:flex-start;margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid rgba(255,255,255,0.06)}
.step:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0}
.step-n{background:#c9a84c;color:#0a0f1e;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:12px;flex-shrink:0;margin-top:2px}
.step-text{font-size:13px;color:rgba(255,255,255,0.6);line-height:1.65}
.step-text strong{color:#fff;display:block;margin-bottom:3px;font-size:14px}
.step-text a{color:#c9a84c;text-decoration:none}

.btn{width:100%;padding:15px;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;margin-bottom:10px;font-family:inherit;transition:all .2s;text-align:center;text-decoration:none;display:block}
.btn-red{background:#cc0000;color:#fff}.btn-red:hover{background:#aa0000}
.btn-blue{background:#1a4fa0;color:#fff}.btn-blue:hover{background:#153d80}
.btn-purple{background:#6b21a8;color:#fff}.btn-purple:hover{background:#581c87}
.btn-ghost{background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.6);border:1px solid rgba(255,255,255,0.12)}.btn-ghost:hover{color:#fff;border-color:rgba(255,255,255,0.3)}

.msg{display:none;padding:14px;border-radius:6px;font-family:monospace;font-size:12px;margin-bottom:12px;line-height:1.7}
.msg.show{display:block}
.msg-ok{background:rgba(0,135,90,0.15);border:1px solid rgba(0,135,90,0.3);color:#00ff88}
.msg-err{background:rgba(204,0,0,0.15);border:1px solid rgba(204,0,0,0.3);color:#ff6b6b}

.divider{height:1px;background:rgba(255,255,255,0.06);margin:20px 0}
.footer-note{font-family:monospace;font-size:10px;color:rgba(255,255,255,0.2);text-align:center;margin-top:24px;line-height:1.8}
</style>
</head>
<body>

<div class="logo">AILeash <span>Guardian</span></div>
<div class="sub">Threat Reporting &amp; Evidence Preservation</div>

<div class="nav-links">
  <a href="/">Home</a>
  <a href="/certificate">Certificate</a>
  <a href="/registry">Safe AI Registry</a>
  <a href="/admin">Admin</a>
  <a href="/scan">AI Scanner</a>
</div>

<div class="intro">
  <strong>What is this page for?</strong>
  If AILeash Guardian has detected a threat — grooming behaviour, suspicious contact, or any harmful activity involving a child — this page lets you preserve the evidence and report it to the right authorities. Fill in your details below, copy the evidence package, and follow the steps to report. The SHA-256 audit hash is cryptographically sealed and admissible in UK courts.
</div>

<div class="card">
  <div class="card-title">Evidence Package</div>
  <div class="card-desc">This evidence was automatically captured and sealed by AILeash Guardian. Do not edit it.</div>
  <div class="evidence-label">SHA-256 Audit Hash</div>
  <div class="evidence-box" id="ev-hash">Loading...</div>
  <div class="evidence-label">Incident Record</div>
  <div class="evidence-box" id="ev-record">Loading...</div>
  <div id="ev-severity"></div>
</div>

<div class="card">
  <div class="card-title">Your Details</div>
  <div class="card-desc">This information is sent securely to AILeash and to the relevant authority when you submit your report.</div>
  <div class="field"><label>Your Full Name</label><input type="text" id="reporter-name" placeholder="e.g. Jane Smith"></div>
  <div class="field"><label>Your Email Address</label><input type="email" id="reporter-email" placeholder="your@email.com"></div>
  <div class="field"><label>Your Phone Number</label><input type="tel" id="reporter-phone" placeholder="+44 7700 000000"></div>
  <div class="field"><label>Child's Approximate Age</label>
    <select id="child-age">
      <option value="">Select age group</option>
      <option>Under 5</option>
      <option>5 to 7</option>
      <option>8 to 10</option>
      <option>11 to 13</option>
      <option>14 to 16</option>
      <option>17</option>
    </select>
  </div>
  <div class="field"><label>Additional Details</label><textarea id="extra-details" placeholder="Describe anything else relevant to this incident. Include dates, times, platform names, usernames, or any other context that might help investigators."></textarea></div>
</div>

<div class="card">
  <div class="card-title">How to Report</div>
  <div class="card-desc">Follow these steps in order. Start with Step 1 immediately. If a child is in immediate danger, call 999 first.</div>
  <div class="steps">
    <div class="step">
      <div class="step-n">1</div>
      <div class="step-text">
        <strong>Action Fraud &mdash; UK's National Fraud Reporting Centre</strong>
        Call <strong>0300 123 2040</strong> or visit <a href="https://www.actionfraud.police.uk" target="_blank">actionfraud.police.uk</a>. Give them the SHA-256 hash above. They will issue a crime reference number — keep it safe.
      </div>
    </div>
    <div class="step">
      <div class="step-n">2</div>
      <div class="step-text">
        <strong>CEOP &mdash; Child Exploitation and Online Protection</strong>
        For grooming or child sexual exploitation, report directly at <a href="https://www.ceop.police.uk/safety-centre/" target="_blank">ceop.police.uk/safety-centre</a>. Available 24 hours a day, 7 days a week. CEOP works directly with police to investigate and arrest offenders.
      </div>
    </div>
    <div class="step">
      <div class="step-n">3</div>
      <div class="step-text">
        <strong>Internet Watch Foundation &mdash; For Illegal Images</strong>
        If the incident involved child sexual abuse material, report it at <a href="https://report.iwf.org.uk" target="_blank">report.iwf.org.uk</a>. The IWF works with police to remove content and prosecute offenders globally.
      </div>
    </div>
    <div class="step">
      <div class="step-n">4</div>
      <div class="step-text">
        <strong>Local Police</strong>
        For immediate danger call <strong>999</strong>. For non-emergency situations call <strong>101</strong>. Provide the SHA-256 hash and your crime reference number from Action Fraud.
      </div>
    </div>
  </div>
</div>

<div class="msg msg-ok" id="msg-ok"></div>
<div class="msg msg-err" id="msg-err"></div>

<button class="btn btn-ghost" onclick="copyEvidence()">Copy Full Evidence Package to Clipboard</button>
<a href="https://www.actionfraud.police.uk/reporting-fraud-and-cyber-crime" target="_blank" class="btn btn-blue">Report to Action Fraud &rarr;</a>
<a href="https://www.ceop.police.uk/safety-centre/" target="_blank" class="btn btn-purple">Report to CEOP &rarr;</a>
<button class="btn btn-red" onclick="submitReport()">Submit to AILeash &mdash; Preserve Evidence Permanently &rarr;</button>

<div class="footer-note">
  AILeash Guardian &middot; Monop Content &middot; Blyth, Northumberland<br>
  justrightdecorators@gmail.com &middot; 07908 269428<br>
  Evidence sealed with SHA-256 &middot; Admissible in UK courts
</div>

<script>
var incidentData = {};

function init() {
  var params = new URLSearchParams(window.location.search);
  var hash    = params.get('hash')    || localStorage.getItem('last_block_hash')    || 'NOT PROVIDED';
  var score   = params.get('score')   || localStorage.getItem('last_score')         || 'N/A';
  var reasons = params.get('reasons') || localStorage.getItem('last_reasons')       || 'N/A';
  var ts      = params.get('ts')      || new Date().toISOString();
  var device  = localStorage.getItem('guardian_device') || 'Unknown Device';
  var apiKey  = localStorage.getItem('guardian_key')    || '';

  incidentData = { hash:hash, score:score, reasons:reasons, ts:ts, device:device, apiKey:apiKey };

  document.getElementById('ev-hash').textContent = hash;
  document.getElementById('ev-record').textContent = ts + ' | ' + device + ' | score: ' + score + ' | signals: ' + reasons;

  var sev = parseFloat(score) >= 0.9 ? 'CRITICAL' : 'HIGH';
  document.getElementById('ev-severity').innerHTML = '<span class="severity ' + (sev==='CRITICAL'?'sev-critical':'sev-high') + '">' + sev + ' SEVERITY</span>';
}

function buildPackage() {
  var name  = document.getElementById('reporter-name').value.trim();
  var email = document.getElementById('reporter-email').value.trim();
  var phone = document.getElementById('reporter-phone').value.trim();
  var age   = document.getElementById('child-age').value;
  var extra = document.getElementById('extra-details').value.trim();
  return [
    'AILEASH GUARDIAN — LAW ENFORCEMENT EVIDENCE PACKAGE',
    '=====================================================',
    'Generated: ' + new Date().toISOString(),
    '',
    'EVIDENCE HASH (SHA-256):',
    incidentData.hash,
    '',
    'INCIDENT RECORD:',
    incidentData.ts + ' | Device: ' + incidentData.device,
    'Risk Score: ' + incidentData.score,
    'Threat Signals: ' + incidentData.reasons,
    '',
    'REPORTER DETAILS:',
    'Name:  ' + (name  || 'Not provided'),
    'Email: ' + (email || 'Not provided'),
    'Phone: ' + (phone || 'Not provided'),
    'Child age group: ' + (age || 'Not provided'),
    '',
    'ADDITIONAL DETAILS:',
    extra || 'None provided',
    '',
    'REPORTING CONTACTS:',
    'Action Fraud: 0300 123 2040 | actionfraud.police.uk',
    'CEOP: ceop.police.uk/safety-centre',
    'IWF: report.iwf.org.uk',
    'Emergency: 999 | Non-emergency: 101',
    '',
    'This evidence package was generated by AILeash Guardian.',
    'The SHA-256 audit hash is cryptographically sealed and',
    'admissible as evidence in UK courts.',
    'sebbi.pro | justrightdecorators@gmail.com | 07908 269428'
  ].join('\n');
}

function copyEvidence() {
  navigator.clipboard.writeText(buildPackage()).then(function() {
    var btn = document.querySelectorAll('.btn-ghost')[0];
    btn.textContent = 'Copied \u2713';
    setTimeout(function(){ btn.textContent = 'Copy Full Evidence Package to Clipboard'; }, 2500);
  });
}

async function submitReport() {
  var ok  = document.getElementById('msg-ok');
  var err = document.getElementById('msg-err');
  ok.classList.remove('show'); err.classList.remove('show');
  var email = document.getElementById('reporter-email').value.trim();
  if (!email || !email.includes('@')) {
    err.textContent = 'Please enter your email address before submitting.';
    err.classList.add('show'); return;
  }
  try {
    var r = await fetch('https://sebbi.pro/report-threat', {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+incidentData.apiKey},
      body: JSON.stringify({
        hash: incidentData.hash, score: incidentData.score,
        reasons: incidentData.reasons, device: incidentData.device,
        ts: incidentData.ts,
        reporter_name:  document.getElementById('reporter-name').value.trim(),
        reporter_email: email,
        reporter_phone: document.getElementById('reporter-phone').value.trim(),
        child_age:      document.getElementById('child-age').value,
        extra_details:  document.getElementById('extra-details').value.trim(),
        evidence_package: buildPackage()
      })
    });
    var d = await r.json();
    if (d.ok) {
      ok.textContent = 'Report submitted. Reference: ' + (d.reference || 'AIDX-' + Date.now()) + '. Evidence is permanently preserved. Justin has been notified.';
      ok.classList.add('show');
    } else {
      err.textContent = 'Submission failed. Copy the evidence package above and report to Action Fraud directly on 0300 123 2040.';
      err.classList.add('show');
    }
  } catch(e) {
    err.textContent = 'Cannot reach server. Copy the evidence package and call Action Fraud: 0300 123 2040.';
    err.classList.add('show');
  }
}

init();
</script>
</body>
</html>

```


## `requirements.txt`

2 lines, 22 bytes

```text
opentimestamps-client

```
