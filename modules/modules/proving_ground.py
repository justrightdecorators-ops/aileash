"""
AILeash Proving Ground
======================

Public verification environment for deterministic AI governance.

Purpose:
- Run real engine decisions
- Explain decisions
- Produce counterfactuals
- Verify reproducibility
- Seal demonstrations into audit chain

This module follows the AILeash module pattern:

handle(method, action, data, api_key, ctx)

Version:
1.0.0
"""

import json
import math
import time
import hashlib

from datetime import datetime, timezone


VERSION = "1.0.0"


# Verdict thresholds
ALLOW_MAX = 0.35
CHALLENGE_MAX = 0.70


# Log table protection
_ready = False


# ----------------------------------------------------------------------
# DATABASE SETUP
# ----------------------------------------------------------------------

def _setup(ctx):
    """
    Create proving ground storage.
    """

    global _ready

    if _ready:
        return

    with ctx["lock"]:

        ctx["conn"].execute("""
            CREATE TABLE IF NOT EXISTS proving_runs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key TEXT,
                created REAL,
                score REAL,
                verdict TEXT,
                block_index INTEGER,
                payload TEXT
            )
        """)


        ctx["conn"].execute("""
            CREATE TABLE IF NOT EXISTS proving_replays(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key TEXT,
                parent_id INTEGER,
                created REAL,
                score REAL,
                verdict TEXT,
                change_json TEXT
            )
        """)


        ctx["conn"].execute("""
            CREATE INDEX IF NOT EXISTS idx_proving_key
            ON proving_runs(api_key, created)
        """)


        ctx["conn"].commit()


    _ready = True



# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------

def _clamp(value, low=0.0, high=1.0):

    return max(low, min(high, value))



def _iso(ts):

    if not ts:
        return None

    return datetime.fromtimestamp(
        ts,
        tz=timezone.utc
    ).isoformat()



def _number(data, key, default=0):

    try:
        return float(
            data.get(key, default)
        )

    except (ValueError, TypeError):

        return default



# ----------------------------------------------------------------------
# INPUT NORMALISATION
# ----------------------------------------------------------------------

def _normalise(data):

    return {

        "trust":
            _clamp(
                _number(data, "trust", 0.5)
            ),


        "v60":
            max(
                0,
                _number(data, "v60")
            ),


        "v5m":
            max(
                0,
                _number(data, "v5m")
            ),


        "v1h":
            max(
                0,
                _number(data, "v1h")
            ),


        "amount":
            max(
                0,
                _number(data, "amount")
            ),


        "device_risk":
            _clamp(
                _number(data, "device_risk")
            ),


        "anomaly":
            _clamp(
                _number(data, "anomaly")
            ),


        "country_shift":
            bool(
                data.get("country_shift")
            ),


        "unsafe_country":
            bool(
                data.get("unsafe_country")
            )
    }



# ----------------------------------------------------------------------
# DETERMINISTIC SCORE ENGINE
# ----------------------------------------------------------------------

LN_CAP = math.log1p(10000)



def _score(signals):

    score = 0


    # Trust
    score += (
        (1 - signals["trust"])
        * 0.30
    )


    # Velocity
    score += (
        min(signals["v60"] / 20, 1)
        * 0.15
    )


    score += (
        min(signals["v5m"] / 50, 1)
        * 0.10
    )


    score += (
        min(signals["v1h"] / 200, 1)
        * 0.10
    )


    # Amount
    score += (
        min(
            math.log1p(signals["amount"])
            /
            LN_CAP,
            1
        )
        *
        0.15
    )


    # Device
    score += (
        signals["device_risk"]
        *
        0.10
    )


    # Behaviour
    score += (
        signals["anomaly"]
        *
        0.10
    )


    if signals["country_shift"]:

        score += 0.10



    if signals["unsafe_country"]:

        score += 0.10



    return round(
        _clamp(score),
        4
    )



def _verdict(score):

    if score < ALLOW_MAX:

        return "ALLOW"


    if score < CHALLENGE_MAX:

        return "CHALLENGE"


    return "BLOCK"



# ----------------------------------------------------------------------
# CONTRIBUTION BREAKDOWN
# ----------------------------------------------------------------------

def _contributions(signals):

    return {

        "trust":
            round(
                (1-signals["trust"])
                *
                0.30,
                4
            ),


        "v60":
            round(
                min(signals["v60"]/20,1)
                *
                0.15,
                4
            ),


        "v5m":
            round(
                min(signals["v5m"]/50,1)
                *
                0.10,
                4
            ),


        "v1h":
            round(
                min(signals["v1h"]/200,1)
                *
                0.10,
                4
            ),


        "amount":
            round(
                min(
                    math.log1p(signals["amount"])
                    /
                    LN_CAP,
                    1
                )
                *
                0.15,
                4
            ),


        "device_risk":
            round(
                signals["device_risk"]
                *
                0.10,
                4
            ),


        "anomaly":
            round(
                signals["anomaly"]
                *
                0.10,
                4
            ),


        "country_shift":
            0.10
            if signals["country_shift"]
            else 0,


        "unsafe_country":
            0.10
            if signals["unsafe_country"]
            else 0
    }
# ----------------------------------------------------------------------
# COUNTERFACTUAL INVERSION ENGINE
# ----------------------------------------------------------------------

def _invert_factor(name, target, signals):
    """
    Reverse one scoring component.

    Returns:
    {
        value,
        explanation
    }

    None means impossible with this factor alone.
    """


    if name == "trust":

        value = 1 - (target / 0.30)

        if value < 0 or value > 1:

            return None


        return {

            "value": round(value,4),

            "explanation":
                "trust of "
                + str(round(value,3))
                + " or higher (was "
                + str(round(signals["trust"],3))
                + ")"
        }



    if name == "v60":

        value = (
            target
            /
            0.15
        ) * 20


        return {

            "value": round(value,2),

            "explanation":
                "60 second velocity of "
                +
                str(round(value))
                +
                " or lower (was "
                +
                str(round(signals["v60"]))
                +
                ")"
        }



    if name == "v5m":

        value = (
            target
            /
            0.10
        ) * 50


        return {

            "value": round(value,2),

            "explanation":
                "5 minute velocity of "
                +
                str(round(value))
                +
                " or lower (was "
                +
                str(round(signals["v5m"]))
                +
                ")"
        }



    if name == "v1h":

        value = (
            target
            /
            0.10
        ) * 200


        return {

            "value": round(value,2),

            "explanation":
                "1 hour velocity of "
                +
                str(round(value))
                +
                " or lower (was "
                +
                str(round(signals["v1h"]))
                +
                ")"
        }



    if name == "amount":

        value = math.expm1(
            (
                target
                /
                0.15
            )
            *
            LN_CAP
        )


        if value < 0:

            return None


        return {

            "value": round(value,2),

            "explanation":
                "amount of £"
                +
                str(round(value,2))
                +
                " or less (was £"
                +
                str(round(signals["amount"],2))
                +
                ")"
        }



    if name == "device_risk":

        value = target / 0.10


        if value < 0 or value > 1:

            return None


        return {

            "value": round(value,4),

            "explanation":
                "device risk of "
                +
                str(round(value,3))
                +
                " or lower"
        }



    if name == "anomaly":

        value = target / 0.10


        if value < 0 or value > 1:

            return None


        return {

            "value": round(value,4),

            "explanation":
                "behaviour anomaly of "
                +
                str(round(value,3))
                +
                " or lower"
        }



    if name == "country_shift":

        if target < 0.10:

            return {

                "value": False,

                "explanation":
                    "no country change from previous event"
            }


    if name == "unsafe_country":

        if target < 0.10:

            return {

                "value": False,

                "explanation":
                    "no unsafe jurisdiction signal"
            }



    return None





def _analyse_counterfactual(signals, requested=None):

    score = _score(signals)

    verdict = _verdict(score)


    contributions = _contributions(signals)


    if requested:

        target_verdict = requested.upper()

    elif verdict == "BLOCK":

        target_verdict = "CHALLENGE"

    elif verdict == "CHALLENGE":

        target_verdict = "ALLOW"

    else:

        return {

            "score": score,

            "verdict": verdict,

            "message":
                "Already at lowest risk verdict."
        }



    threshold = (
        CHALLENGE_MAX
        if target_verdict == "CHALLENGE"
        else ALLOW_MAX
    )



    required_reduction = (
        score
        -
        threshold
        +
        0.0001
    )



    factors = []

    best = None



    for name, contribution in sorted(
        contributions.items(),
        key=lambda x:x[1],
        reverse=True
    ):


        result = {

            "factor": name,

            "current_contribution":
                contribution
        }



        new_contribution = (
            contribution
            -
            required_reduction
        )



        if new_contribution <= 0:

            result["possible"] = False

            result["reason"] = (
                "This factor alone cannot remove enough risk."
            )


        else:


            inverse = _invert_factor(
                name,
                new_contribution,
                signals
            )


            if inverse:


                result["possible"] = True

                result.update(inverse)



                if best is None:

                    best = result


            else:

                result["possible"] = False

                result["reason"] = (
                    "No valid value exists."
                )


        factors.append(result)



    if best:


        statement = (
            "This decision was "
            +
            verdict
            +
            " with a score of "
            +
            str(score)
            +
            ". The decision would have been "
            +
            target_verdict
            +
            " with "
            +
            best["explanation"]
            +
            ", all else unchanged."
        )


    else:


        statement = (
            "This decision was "
            +
            verdict
            +
            " with a score of "
            +
            str(score)
            +
            ". No single factor change could have reached "
            +
            target_verdict
        )



    return {

        "score": score,

        "verdict": verdict,

        "target_verdict": target_verdict,

        "threshold": threshold,

        "margin":
            round(
                score-threshold,
                4
            ),

        "factors": factors,

        "single_change":
            best,

        "recourse_statement":
            statement
    }



# ----------------------------------------------------------------------
# HASH RECEIPT
# ----------------------------------------------------------------------

def _receipt_hash(data):

    raw = json.dumps(
        data,
        sort_keys=True
    ).encode()


    return hashlib.sha256(
        raw
    ).hexdigest()
# ----------------------------------------------------------------------
# AUDIT SEALING
# ----------------------------------------------------------------------

def _seal_decision(ctx, api_key, result, signals):

    """
    Uses existing AILeash sealing function.

    Expected:
    ctx["seal"](event, result, timestamp, api_key)
    """


    timestamp = time.time()


    event = {

        "action":
            "proving_ground_decision",

        "device_id":
            "public_demo",

        "amount":
            signals.get("amount",0),

        "country":
            "UK",

        "signals":
            signals
    }



    payload = {

        "decision":
            "PROVING_GROUND_SEALED",

        "engine_version":
            VERSION,

        "score":
            result.get("score"),

        "verdict":
            result.get("verdict"),

        "counterfactual":
            result.get("recourse_statement"),

        "timestamp":
            timestamp
    }



    if "seal" in ctx:

        block_hash, block_id, seq = ctx["seal"](
            event,
            payload,
            timestamp,
            api_key
        )


    else:

        block_hash = _receipt_hash(payload)

        block_id = None

        seq = None



    return {

        "audit_hash":
            block_hash,

        "block_index":
            block_id,

        "receipt_sequence":
            seq
    }




# ----------------------------------------------------------------------
# STORE RUN
# ----------------------------------------------------------------------

def _store_run(
        ctx,
        api_key,
        result,
        block_index,
        payload):


    with ctx["lock"]:

        cur = ctx["conn"].execute(
            """
            INSERT INTO proving_runs
            (
                api_key,
                created,
                score,
                verdict,
                block_index,
                payload
            )
            VALUES
            (?,?,?,?,?,?)
            """,

            (
                api_key,

                time.time(),

                result.get("score"),

                result.get("verdict"),

                block_index,

                json.dumps(payload)
            )
        )


        ctx["conn"].commit()


        return cur.lastrowid





# ----------------------------------------------------------------------
# RUN LIVE PROVING TEST
# ----------------------------------------------------------------------

def _run_proving(ctx, api_key, data):


    signals = _normalise(data)


    result = _analyse_counterfactual(
        signals,
        data.get("target_verdict")
    )



    seal = _seal_decision(
        ctx,
        api_key,
        result,
        signals
    )



    result.update(seal)



    result["inputs_used"] = signals


    result["verification"] = {

        "recalculate":

            "Run the published scoring weights against inputs.",


        "deterministic":

            True,


        "engine_version":

            VERSION
    }



    run_id = _store_run(

        ctx,

        api_key,

        result,

        result.get("block_index"),

        signals
    )


    result["run_id"] = run_id



    result["receipt_hash"] = _receipt_hash(
        {
            "inputs":signals,

            "score":
                result.get("score"),

            "verdict":
                result.get("verdict"),

            "engine":
                VERSION
        }
    )



    return result, 200





# ----------------------------------------------------------------------
# VERIFY RECEIPT
# ----------------------------------------------------------------------

def _verify_run(ctx, api_key, run_id):


    try:

        run_id = int(run_id)

    except:

        return {

            "error":
                "invalid_run_id"

        },400



    with ctx["lock"]:

        row = ctx["conn"].execute(

            """
            SELECT
            score,
            verdict,
            payload,
            created
            FROM proving_runs
            WHERE id=?
            AND api_key=?
            """,

            (
                run_id,
                api_key
            )

        ).fetchone()



    if not row:

        return {

            "error":
                "unknown_run"

        },404



    score, verdict, payload, created = row



    inputs = json.loads(payload)



    signals = _normalise(inputs)



    recalculated = _score(
        signals
    )


    recalculated_verdict = _verdict(
        recalculated
    )



    return {


        "verified":

            (
                round(recalculated,4)
                ==
                round(float(score),4)

                and

                recalculated_verdict
                ==
                verdict
            ),


        "stored_score":

            score,


        "recalculated_score":

            recalculated,


        "stored_verdict":

            verdict,


        "
# ----------------------------------------------------------------------
# STATISTICS
# ----------------------------------------------------------------------

def _stats(ctx, api_key):

    now = time.time()


    with ctx["lock"]:

        total = ctx["conn"].execute(

            """
            SELECT COUNT(*)
            FROM proving_runs
            WHERE api_key=?
            """,

            (api_key,)

        ).fetchone()[0]



        last24 = ctx["conn"].execute(

            """
            SELECT COUNT(*)
            FROM proving_runs
            WHERE api_key=?
            AND created > ?
            """,

            (
                api_key,
                now - 86400
            )

        ).fetchone()[0]



        blocks = ctx["conn"].execute(

            """
            SELECT COUNT(*)
            FROM proving_runs
            WHERE api_key=?
            AND verdict='BLOCK'
            """,

            (api_key,)

        ).fetchone()[0]



        challenges = ctx["conn"].execute(

            """
            SELECT COUNT(*)
            FROM proving_runs
            WHERE api_key=?
            AND verdict='CHALLENGE'
            """,

            (api_key,)

        ).fetchone()[0]



        allows = ctx["conn"].execute(

            """
            SELECT COUNT(*)
            FROM proving_runs
            WHERE api_key=?
            AND verdict='ALLOW'
            """,

            (api_key,)

        ).fetchone()[0]



    return {


        "engine":

            "AILeash Proving Ground",


        "version":

            VERSION,


        "total_runs":

            total,


        "last_24_hours":

            last24,


        "verdicts":

            {

                "ALLOW":
                    allows,

                "CHALLENGE":
                    challenges,

                "BLOCK":
                    blocks
            },


        "status":

            "healthy"

    },200





# ----------------------------------------------------------------------
# PROBING DETECTION
# ----------------------------------------------------------------------

def _probing(ctx, api_key):


    cutoff = time.time() - 86400



    with ctx["lock"]:

        rows = ctx["conn"].execute(

            """
            SELECT score
            FROM proving_runs
            WHERE api_key=?
            AND created>?
            """,

            (
                api_key,
                cutoff
            )

        ).fetchall()



    total = len(rows)


    near_boundary = 0



    for row in rows:

        score = float(row[0])


        if (

            abs(score - ALLOW_MAX)
            < 0.02

            or

            abs(score - CHALLENGE_MAX)
            < 0.02

        ):

            near_boundary += 1



    response = {


        "requests_24h":

            total,


        "near_threshold":

            near_boundary,


        "monitoring":

            "active"


    }



    if total >= 50:

        response["flag"] = (

            "High counterfactual activity detected. "
            "Consistent with systematic boundary testing."
        )



    if near_boundary >= 10:

        response["boundary_warning"] = (

            "Multiple attempts close to decision thresholds."
        )



    return response,200





# ----------------------------------------------------------------------
# HEALTH
# ----------------------------------------------------------------------

def _health(ctx):


    return {


        "module":

            "proving_ground",


        "version":

            VERSION,


        "status":

            "online",


        "features":

            [

                "deterministic scoring",

                "counterfactual explanation",

                "decision replay",

                "audit receipts",

                "verification"

            ]

    },200





# ----------------------------------------------------------------------
# MAIN ROUTER
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):


    _setup(ctx)



    if method == "POST":


        if action == "run":

            return _run_proving(
                ctx,
                api_key,
                data
            )



        return {

            "error":
                "unknown_post_action"

        },404





    if method == "GET":


        if action == "stats":

            return _stats(
                ctx,
                api_key
            )



        if action == "probing":

            return _probing(
                ctx,
                api_key
            )



        if action == "health":

            return _health(
                ctx
            )



        if action == "verify":

            return _verify_run(

                ctx,

                api_key,

                data.get("run_id")
            )



        if action == "replay":

            changes = data.get(
                "changes",
                {}
            )


            return _replay(

                ctx,

                api_key,

                data.get("run_id"),

                changes
            )



    return {


        "error":

            "unknown_action",


        "available":

            [

                "POST run",

                "GET stats",

                "GET verify",

                "GET replay",

                "GET probing",

                "GET health"

            ]

    },404
# ----------------------------------------------------------------------
# PUBLIC PROVING GROUND HTML
# ----------------------------------------------------------------------

PROVING_HTML = r"""
<!DOCTYPE html>
<html>

<head>

<title>
AILeash Proving Ground
</title>


<style>

body {

    font-family: Arial, sans-serif;

    background:#0b1020;

    color:white;

    margin:0;

    padding:30px;

}


.card {

    background:#151d35;

    border-radius:12px;

    padding:20px;

    margin-bottom:20px;

}


h1 {

    color:#4fd1c5;

}


input {

    width:100%;

    padding:10px;

    margin:5px 0;

    border-radius:6px;

    border:0;

}


button {

    padding:12px 20px;

    background:#4fd1c5;

    border:0;

    border-radius:8px;

    cursor:pointer;

    font-weight:bold;

}


.result {

    white-space:pre-wrap;

    background:#080c18;

    padding:15px;

    border-radius:8px;

}


.good {

    color:#4fd1c5;

}


.warning {

    color:#f6ad55;

}


.bad {

    color:#fc8181;

}


</style>


</head>


<body>


<div class="card">


<h1>
AILeash Governance Proving Ground
</h1>


<p>
Create a real deterministic AI decision.
Change the inputs.
Replay the outcome.
Verify the mathematics.
</p>


</div>



<div class="card">


<h2>
Decision Inputs
</h2>


<label>
Trust
</label>

<input id="trust" value="0.28">



<label>
60 Second Velocity
</label>

<input id="v60" value="12">



<label>
5 Minute Velocity
</label>

<input id="v5m" value="20">



<label>
1 Hour Velocity
</label>

<input id="v1h" value="50">



<label>
Amount
</label>

<input id="amount" value="2500">



<label>
Device Risk
</label>

<input id="device_risk" value="0.2">



<label>
Anomaly
</label>

<input id="anomaly" value="0.3">


<br><br>


<button onclick="runDecision()">

Run Decision

</button>


</div>



<div class="card">


<h2>
Governance Receipt
</h2>


<div id="result" class="result">

Waiting for decision...

</div>


</div>




<script>


async function runDecision(){


let payload={


trust:

parseFloat(
document.getElementById("trust").value
),


v60:

parseFloat(
document.getElementById("v60").value
),


v5m:

parseFloat(
document.getElementById("v5m").value
),


v1h:

parseFloat(
document.getElementById("v1h").value
),


amount:

parseFloat(
document.getElementById("amount").value
),


device_risk:

parseFloat(
document.getElementById("device_risk").value
),


anomaly:

parseFloat(
document.getElementById("anomaly").value
)


};



let response =
await fetch(
"/x/proving/run",
{

method:"POST",

headers:
{

"Content-Type":
"application/json"

},

body:
JSON.stringify(payload)

}

);



let data =
await response.json();



document.getElementById(
"result"
).innerHTML =
JSON.stringify(
data,
null,
2
);



}



</script>


</body>

</html>
"""





# ----------------------------------------------------------------------
# HTML ACCESSOR
# ----------------------------------------------------------------------

def page():

    return PROVING_HTML
