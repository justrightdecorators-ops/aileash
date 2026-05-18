LANDING = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash | AI Governance Infrastructure</title>

<style>
*{
    margin:0;
    padding:0;
    box-sizing:border-box;
}

body{
    background:#070707;
    color:#f2f2f2;
    font-family:Arial,Helvetica,sans-serif;
    line-height:1.7;
}

a{
    color:#00ff99;
    text-decoration:none;
}

nav{
    width:100%;
    padding:1.2rem 2rem;
    border-bottom:1px solid #1f1f1f;
    display:flex;
    justify-content:space-between;
    align-items:center;
    position:sticky;
    top:0;
    background:#070707;
    z-index:999;
}

.logo{
    font-size:1.4rem;
    font-weight:700;
    letter-spacing:2px;
}

.logo span{
    color:#00ff99;
}

.nav-right{
    color:#ffaa00;
    font-size:.9rem;
}

.hero{
    max-width:1200px;
    margin:auto;
    padding:7rem 2rem 5rem 2rem;
}

.badge{
    display:inline-block;
    padding:.45rem 1rem;
    border:1px solid #00ff99;
    color:#00ff99;
    margin-bottom:2rem;
    font-size:.85rem;
    letter-spacing:1px;
}

.hero h1{
    font-size:4rem;
    line-height:1.1;
    margin-bottom:1.5rem;
    max-width:850px;
}

.hero h1 span{
    color:#00ff99;
}

.sub{
    max-width:760px;
    color:#b8b8b8;
    font-size:1.15rem;
    margin-bottom:3rem;
}

.cta-grid{
    display:grid;
    grid-template-columns:1fr 380px;
    gap:2rem;
    align-items:start;
}

.panel{
    background:#111111;
    border:1px solid #232323;
    border-radius:8px;
    padding:2rem;
}

.panel h3{
    margin-bottom:1rem;
    color:#00ff99;
}

.panel p{
    color:#bcbcbc;
}

.price{
    font-size:3rem;
    color:#00ff99;
    font-weight:700;
}

.price span{
    font-size:1rem;
    color:#888;
}

.features{
    list-style:none;
    margin-top:1.5rem;
}

.features li{
    padding:.55rem 0;
    border-bottom:1px solid #1f1f1f;
    color:#d0d0d0;
}

.features li:last-child{
    border-bottom:none;
}

.form-group{
    margin-top:1rem;
}

.form-group label{
    display:block;
    margin-bottom:.4rem;
    font-size:.85rem;
    color:#9c9c9c;
}

.form-group input{
    width:100%;
    background:#070707;
    border:1px solid #2a2a2a;
    color:white;
    padding:.9rem;
    border-radius:4px;
    font-size:1rem;
}

.form-group input:focus{
    outline:none;
    border-color:#00ff99;
}

.btn{
    width:100%;
    margin-top:1.5rem;
    background:#00ff99;
    color:#050505;
    border:none;
    padding:1rem;
    font-size:1rem;
    font-weight:700;
    cursor:pointer;
    border-radius:4px;
}

.btn:hover{
    background:#00cc77;
}

.section{
    max-width:1200px;
    margin:auto;
    padding:5rem 2rem;
}

.section-title{
    font-size:2.2rem;
    margin-bottom:1.5rem;
}

.section-title span{
    color:#00ff99;
}

.section-sub{
    color:#a8a8a8;
    max-width:760px;
    margin-bottom:3rem;
}

.grid{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
    gap:1.5rem;
}

.card{
    background:#111111;
    border:1px solid #1f1f1f;
    border-radius:8px;
    padding:1.8rem;
}

.card h3{
    margin-bottom:1rem;
    color:#00ff99;
}

.card p{
    color:#bcbcbc;
    font-size:.96rem;
}

.code{
    background:#050505;
    border:1px solid #222;
    border-radius:8px;
    padding:1.5rem;
    overflow:auto;
    color:#00ff99;
    font-family:monospace;
    margin-top:2rem;
    font-size:.95rem;
}

.stats{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
    gap:1rem;
    margin-top:2rem;
}

.stat{
    background:#111111;
    border:1px solid #1f1f1f;
    padding:2rem;
    border-radius:8px;
    text-align:center;
}

.stat h2{
    color:#00ff99;
    font-size:2.2rem;
    margin-bottom:.5rem;
}

.stat p{
    color:#9d9d9d;
}

footer{
    border-top:1px solid #1f1f1f;
    margin-top:5rem;
    padding:3rem 2rem;
    text-align:center;
    color:#8d8d8d;
    font-size:.9rem;
}

.msg{
    margin-top:1rem;
    padding:1rem;
    border-radius:4px;
    display:none;
}

.msg-ok{
    background:rgba(0,255,153,.08);
    border:1px solid #00ff99;
    color:#00ff99;
}

.msg-err{
    background:rgba(255,70,70,.08);
    border:1px solid #ff4444;
    color:#ff6666;
}

@media(max-width:900px){

.hero h1{
    font-size:2.6rem;
}

.cta-grid{
    grid-template-columns:1fr;
}

}
</style>
</head>

<body>

<nav>
    <div class="logo">AI<span>Leash</span></div>
    <div class="nav-right">
        EU AI Act • ISO 42001 • UK & US AI Governance
    </div>
</nav>

<section class="hero">

    <div class="badge">
        GOVERNANCE INFRASTRUCTURE FOR AUTONOMOUS AI SYSTEMS
    </div>

    <h1>
        Govern every AI decision
        <span>in real time.</span>
    </h1>

    <p class="sub">
        AILeash adds policy enforcement, trust scoring, behavioural monitoring,
        and tamper-evident audit logging to AI systems and autonomous agents.
        Built for organizations preparing for the EU AI Act, ISO 42001,
        and emerging AI accountability requirements.
    </p>

    <div class="cta-grid">

        <div class="panel">

            <h3>Operational AI Governance</h3>

            <p>
                AILeash monitors and evaluates AI actions before execution using:
            </p>

            <ul class="features">
                <li>Behavioural anomaly scoring</li>
                <li>Dynamic trust decay engine</li>
                <li>Velocity and abuse detection</li>
                <li>Geographic deviation analysis</li>
                <li>Tamper-evident audit chain</li>
                <li>ALLOW / CHALLENGE / BLOCK enforcement</li>
                <li>Flask and FastAPI integration</li>
                <li>Single-file deployment architecture</li>
                <li>Zero external dependencies</li>
            </ul>

            <div class="code">
pip install aileash
            </div>

        </div>

        <div class="panel">

            <div class="price">
                $99 <span>/ month</span>
            </div>

            <ul class="features">
                <li>AI governance engine</li>
                <li>Immutable audit logging</li>
                <li>Real-time risk scoring</li>
                <li>API-first architecture</li>
                <li>Deploy in minutes</li>
                <li>Licence key activation</li>
            </ul>

            <div class="form-group">
                <label>Company Name</label>
                <input type="text" id="company" placeholder="Acme AI Ltd">
            </div>

            <div class="form-group">
                <label>Work Email</label>
                <input type="email" id="email" placeholder="cto@company.com">
            </div>

            <button class="btn" onclick="signup()">
                Activate AILeash
            </button>

            <div class="msg msg-ok" id="msg-ok"></div>
            <div class="msg msg-err" id="msg-err"></div>

        </div>

    </div>

</section>

<section class="section">

    <h2 class="section-title">
        Why <span>AI Governance</span> Matters
    </h2>

    <p class="section-sub">
        Most AI systems operate without governance infrastructure,
        audit visibility, or behavioural enforcement controls.
        As AI regulation accelerates globally, organizations require
        operational oversight and evidence generation for autonomous systems.
    </p>

    <div class="stats">

        <div class="stat">
            <h2>EU AI Act</h2>
            <p>Enforcement deadlines approaching across the European Union.</p>
        </div>

        <div class="stat">
            <h2>ISO 42001</h2>
            <p>AI management systems becoming enterprise requirements.</p>
        </div>

        <div class="stat">
            <h2>24/7</h2>
            <p>Continuous behavioural governance and audit monitoring.</p>
        </div>

        <div class="stat">
            <h2>ALLOW / BLOCK</h2>
            <p>Real-time enforcement before unsafe actions execute.</p>
        </div>

    </div>

</section>

<section class="section">

    <h2 class="section-title">
        Governance & <span>Compliance Alignment</span>
    </h2>

    <div class="grid">

        <div class="card">
            <h3>EU AI Act Article 9</h3>
            <p>
                Supports operational risk management workflows through
                behavioural scoring, trust evaluation, and policy-based
                enforcement decisions.
            </p>
        </div>

        <div class="card">
            <h3>EU AI Act Article 12</h3>
            <p>
                Generates tamper-evident audit records and governance
                evidence for monitoring and traceability operations.
            </p>
        </div>

        <div class="card">
            <h3>EU AI Act Article 14</h3>
            <p>
                Enables human oversight pathways through CHALLENGE
                and BLOCK governance escalation states.
            </p>
        </div>

        <div class="card">
            <h3>EU AI Act Article 15</h3>
            <p>
                Improves robustness and operational visibility using
                anomaly detection and behavioural enforcement logic.
            </p>
        </div>

        <div class="card">
            <h3>ISO/IEC 42001</h3>
            <p>
                Supports AI management system governance through
                monitoring, accountability, and audit traceability.
            </p>
        </div>

        <div class="card">
            <h3>UK & US Governance</h3>
            <p>
                Built to support evolving AI accountability, operational
                governance, and enterprise oversight requirements.
            </p>
        </div>

    </div>

</section>

<section class="section">

    <h2 class="section-title">
        How <span>AILeash</span> Works
    </h2>

    <div class="grid">

        <div class="card">
            <h3>01 — Capture</h3>
            <p>
                Monitor AI actions, autonomous agent events,
                API requests, and behavioural activity streams.
            </p>
        </div>

        <div class="card">
            <h3>02 — Score</h3>
            <p>
                Evaluate trust, anomaly signals, velocity patterns,
                geographic changes, and operational risk.
            </p>
        </div>

        <div class="card">
            <h3>03 — Enforce</h3>
            <p>
                Execute real-time ALLOW, CHALLENGE,
                or BLOCK governance decisions.
            </p>
        </div>

        <div class="card">
            <h3>04 — Audit</h3>
            <p>
                Write every governance decision into an immutable
                cryptographic audit chain for evidence and forensics.
            </p>
        </div>

    </div>

    <div class="code">
from aileash import govern

event = {
    "user_id": "user_123",
    "action": "wire_transfer",
    "amount": 1200,
    "country": "UK",
    "device_risk": 0.2,
    "anomaly": 0.1
}

result = govern(event)

print(result["decision"])
    </div>

</section>

<section class="section">

    <h2 class="section-title">
        Built For <span>AI Infrastructure Teams</span>
    </h2>

    <div class="grid">

        <div class="card">
            <h3>API-Driven AI Systems</h3>
            <p>
                Integrates into AI workflows, orchestration systems,
                and autonomous agent pipelines.
            </p>
        </div>

        <div class="card">
            <h3>Lightweight Deployment</h3>
            <p>
                Pure Python architecture with no external dependencies
                and self-hosted deployment capability.
            </p>
        </div>

        <div class="card">
            <h3>Operational Oversight</h3>
            <p>
                Create audit visibility and governance enforcement
                for enterprise AI operations.
            </p>
        </div>

    </div>

</section>

<footer>

    <p>
        AILeash by Monopcontent
    </p>

    <p style="margin-top:.5rem;">
        Governance infrastructure for autonomous AI systems.
    </p>

    <p style="margin-top:1rem;">
        https://sebbi.pro/monopcontent
    </p>

</footer>

<script>

function signup() {

    var company = document.getElementById("company").value.trim();
    var email = document.getElementById("email").value.trim();

    var ok = document.getElementById("msg-ok");
    var err = document.getElementById("msg-err");

    ok.style.display = "none";
    err.style.display = "none";

    if (!company || !email) {

        err.textContent = "Please enter company name and email.";
        err.style.display = "block";
        return;
    }

    fetch("/signup", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            company: company,
            email: email
        })
    })

    .then(function(r){
        return r.json();
    })

    .then(function(data){

        if (data.stripe_url) {

            window.location.href = data.stripe_url;
            return;
        }

        if (data.licence_key) {

            ok.textContent =
                "AILeash activated. Licence key issued.";

            ok.style.display = "block";
            return;
        }

        err.textContent =
            data.error || "Activation failed.";

        err.style.display = "block";
    })

    .catch(function(){

        err.textContent =
            "Connection error. Please try again.";

        err.style.display = "block";
    });
}

</script>

</body>
</html>
"""
