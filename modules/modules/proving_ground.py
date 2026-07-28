"""
AILeash Proving Ground

Public verification interface for deterministic AI governance.

Provides:
- live decision demonstrations
- counterfactual explanations
- audit receipts
- replay verification

Route:
 /x/proving_ground/<action>
"""

import json
import time
import hashlib

from datetime import datetime, timezone


VERSION = "1.0.0"


PUBLIC = {
    ("GET", "health")
}


_ready = False



def _setup(ctx):

    global _ready

    if _ready:
        return


    with ctx["lock"]:

        ctx["conn"].execute(
            """
            CREATE TABLE IF NOT EXISTS proving_runs
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key TEXT,
                created REAL,
                verdict TEXT,
                score REAL,
                payload TEXT,
                block_index INTEGER
            )
            """
        )


        ctx["conn"].commit()


    _ready = True




def _iso(ts):

    if not ts:
        return None

    return datetime.fromtimestamp(
        ts,
        timezone.utc
    ).isoformat()
# ---------------------------------------------------------
# INPUT NORMALISATION
# ---------------------------------------------------------

def _clamp(value, low=0.0, high=1.0):

    return max(
        low,
        min(high, value)
    )



def _number(data, key, default=0):

    try:

        return float(
            data.get(key, default)
        )

    except Exception:

        return default



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




# ---------------------------------------------------------
# AILeash SCORING BRIDGE
# ---------------------------------------------------------

def _get_score(signals):

    """
    Uses AILeash engine if available.

    Falls back to local deterministic calculation
    only if engine import is unavailable.
    """


    try:

        from engine import compute_score


        result = compute_score(
            signals,
            "governance"
        )


        if isinstance(result, dict):

            return round(
                float(
                    result.get("score",0)
                ),
                4
            )


        return round(
            float(result),
            4
        )


    except Exception:

        import math


        score = 0


        score += (
            (1-signals["trust"])
            *
            0.30
        )


        score += (
            min(
                signals["v60"]/20,
                1
            )
            *
            0.15
        )


        score += (
            min(
                signals["v5m"]/50,
                1
            )
            *
            0.10
        )


        score += (
            min(
                signals["v1h"]/200,
                1
            )
            *
            0.10
        )


        score += (
            min(
                math.log1p(
                    signals["amount"]
                )
                /
                math.log1p(10000),
                1
            )
            *
            0.15
        )


        score += (
            signals["device_risk"]
            *
            0.10
        )


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
            max(
                0,
                min(
                    1,
                    score
                )
            ),
            4
        )




def _verdict(score):

    if score < 0.35:

        return "ALLOW"


    if score < 0.70:

        return "CHALLENGE"


    return "BLOCK"
# ---------------------------------------------------------
# CONTRIBUTION MAP
# ---------------------------------------------------------

def _contributions(s):

    import math


    return {

        "trust":
            (1-s["trust"]) * 0.30,


        "v60":
            min(s["v60"]/20,1) * 0.15,


        "v5m":
            min(s["v5m"]/50,1) * 0.10,


        "v1h":
            min(s["v1h"]/200,1) * 0.10,


        "amount":
            min(
                math.log1p(s["amount"])
                /
                math.log1p(10000),
                1
            )
            *
            0.15,


        "device_risk":
            s["device_risk"] * 0.10,


        "anomaly":
            s["anomaly"] * 0.10,


        "country_shift":
            0.10 if s["country_shift"] else 0,


        "unsafe_country":
            0.10 if s["unsafe_country"] else 0
    }





# ---------------------------------------------------------
# COUNTERFACTUAL ANALYSIS
# ---------------------------------------------------------

def _counterfactual(signals):


    score = _get_score(signals)

    verdict = _verdict(score)



    if verdict == "BLOCK":

        target = "CHALLENGE"

        threshold = 0.70


    elif verdict == "CHALLENGE":

        target = "ALLOW"

        threshold = 0.35


    else:

        return {

            "score": score,

            "verdict": verdict,

            "message":
                "Already allowed. No lower decision exists."

        }




    contributions = _contributions(
        signals
    )


    required = (
        score
        -
        threshold
        +
        0.0001
    )



    possible = []



    for factor,value in contributions.items():


        if value <= 0:

            continue



        if value >= required:


            possible.append(

                {

                    "factor":
                        factor,


                    "removed_risk_needed":
                        round(
                            required,
                            4
                        ),


                    "current_contribution":
                        round(
                            value,
                            4
                        )

                }

            )



    best = None


    if possible:

        best = sorted(

            possible,

            key=lambda x:
                x["current_contribution"]

        )[0]



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
            ". The decision could have changed to "

            +
            target

            +
            " if the "

            +
            best["factor"]

            +
            " risk contribution had been reduced enough, all else unchanged."

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
            ". No single factor could have changed the outcome alone."

        )



    return {


        "score":

            score,


        "verdict":

            verdict,


        "target_verdict":

            target,


        "threshold":

            threshold,


        "counterfactual":

            best,


        "recourse_statement":

            statement

    }





# ---------------------------------------------------------
# AUDIT SEAL
# ---------------------------------------------------------

def _seal(ctx, api_key, result, signals):


    timestamp = time.time()



    event = {

        "action":
            "proving_ground",


        "signals":
            signals,


        "timestamp":
            timestamp

    }



    receipt = {

        "decision":
            "PROVING_SEALED",


        "engine_version":
            VERSION,


        "score":
            result.get("score"),


        "verdict":
            result.get("verdict"),


        "counterfactual":
            result.get("recourse_statement")

    }



    try:

        h, block,
# ---------------------------------------------------------
# STORE PROVING RUN
# ---------------------------------------------------------

def _store(ctx, api_key, result, signals):


    with ctx["lock"]:

        cur = ctx["conn"].execute(

            """
            INSERT INTO proving_runs
            (
                api_key,
                created,
                verdict,
                score,
                payload,
                block_index
            )
            VALUES (?,?,?,?,?,?)
            """,

            (

                api_key,

                time.time(),

                result.get("verdict"),

                result.get("score"),

                json.dumps(signals),

                result.get("block_index")

            )

        )


        ctx["conn"].commit()


        return cur.lastrowid





# ---------------------------------------------------------
# RUN LIVE PROVING DECISION
# ---------------------------------------------------------

def _run(ctx, api_key, data):


    signals = _normalise(
        data
    )


    result = _counterfactual(
        signals
    )


    receipt = _seal(
        ctx,
        api_key,
        result,
        signals
    )


    result.update(
        receipt
    )


    result["inputs_used"] = signals



    run_id = _store(

        ctx,

        api_key,

        result,

        signals

    )


    result["run_id"] = run_id



    result["verification"] = {

        "deterministic":

            True,


        "message":

            "Recalculate the published arithmetic using the same inputs."

    }



    return result,200





# ---------------------------------------------------------
# VERIFY A STORED RUN
# ---------------------------------------------------------

def _verify(ctx, api_key, data):


    try:

        run_id = int(
            data.get("run_id")
        )

    except Exception:

        return {

            "error":
                "run_id_required"

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



    stored_score = row[0]

    stored_verdict = row[1]

    signals = json.loads(
        row[2]
    )


    recalculated_score = _get_score(
        signals
    )


    recalculated_verdict = _verdict(
        recalculated_score
    )



    return {


        "verified":

            (

                round(
                    float(stored_score),
                    4
                )

                ==

                round(
                    recalculated_score,
                    4
                )

                and

                stored_verdict
                ==
                recalculated_verdict

            ),



        "stored_score":

            stored_score,


        "recalculated_score":

            recalculated_score,


        "stored_verdict":

            stored_verdict,


        "recalculated_verdict":

            recalculated_verdict,


        "created":

            _iso(row[3])

    },200





# ---------------------------------------------------------
# HEALTH
# ---------------------------------------------------------

def _health():

    return {


        "module":

            "AILeash Proving Ground",


        "version":

            VERSION,


        "status":

            "online"

    },200





# ---------------------------------------------------------
# STATS
# ---------------------------------------------------------

def _stats(ctx, api_key):


    with ctx["lock"]:

        total = ctx["conn"].execute(

            """
            SELECT COUNT(*)
            FROM proving_runs
            WHERE api_key=?
            """,

            (api_key,)

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



    return {


        "total_runs":

            total,


        "blocked":

            blocks,


        "module":

            "proving_ground"


    },200
# ---------------------------------------------------------
# PROBING MONITOR
# ---------------------------------------------------------

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

            abs(score - 0.35) < 0.02

            or

            abs(score - 0.70) < 0.02

        ):

            near_boundary += 1



    response = {


        "requests_24h":

            total,


        "near_boundary_requests":

            near_boundary,


        "monitoring":

            "active"

    }



    if total >= 50:

        response["warning"] = (

            "High counterfactual activity detected. "
            "Possible systematic boundary mapping."
        )


    return response,200





# ---------------------------------------------------------
# MODULE ROUTER
# ---------------------------------------------------------

def handle(method, action, data, api_key, ctx):


    _setup(ctx)



    if method == "POST":


        if action == "run":

            return _run(

                ctx,

                api_key,

                data

            )



    if method == "GET":


        if action == "health":

            return _health()



        if action == "verify":

            return _verify(

                ctx,

                api_key,

                data

            )



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



    return {


        "error":

            "unknown_action",


        "available":

            [

                "POST /x/proving_ground/run",

                "GET /x/proving_ground/health",

                "GET /x/proving_ground/verify",

                "GET /x/proving_ground/stats",

                "GET /x/proving_ground/probing"

            ]

    },404




def _hash(data):

    raw = json.dumps(
        data,
        sort_keys=True
    ).encode()

    return hashlib.sha256(raw).hexdigest()
