"""
AILeash Proving Ground

Module:
modules/proving_ground.py

Purpose:
- Public verification playground
- Run deterministic AILeash decisions
- Produce sealed proof receipts
- Demonstrate counterfactual governance

Routes:
GET  /x/proving_ground/health
POST /x/proving_ground/run
GET  /x/proving_ground/stats
GET  /x/proving_ground/probing
"""

import json
import time
import hashlib

from datetime import datetime, timezone


VERSION = "1.0.0"


# Only health is public.
# All decision runs require API key.
PUBLIC = {
    ("GET", "health")
}


_ready = False



# ---------------------------------------------------------
# DATABASE SETUP
# ---------------------------------------------------------

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
                audit_hash TEXT
            )
            """
        )


        ctx["conn"].commit()


    _ready = True




# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def _iso(ts):

    if not ts:
        return None

    return datetime.fromtimestamp(
        ts,
        timezone.utc
    ).isoformat()



def _hash(data):

    raw = json.dumps(
        data,
        sort_keys=True
    ).encode()


    return hashlib.sha256(
        raw
    ).hexdigest()



def _clamp(value):

    return max(
        0.0,
        min(
            1.0,
            float(value)
        )

    )
# ---------------------------------------------------------
# INPUT NORMALISATION
# ---------------------------------------------------------

def _number(data, key, default=0):

    try:
        return float(
            data.get(key, default)
        )

    except (TypeError, ValueError):

        return default



def _normalise(data):

    return {

        "trust":
            _clamp(
                _number(
                    data,
                    "trust",
                    0.5
                )
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
                _number(
                    data,
                    "device_risk"
                )
            ),


        "anomaly":
            _clamp(
                _number(
                    data,
                    "anomaly"
                )
            ),


        "country_shift":

            bool(
                data.get(
                    "country_shift"
                )
            ),


        "unsafe_country":

            bool(
                data.get(
                    "unsafe_country"
                )
            )

    }





# ---------------------------------------------------------
# DETERMINISTIC SCORE
# ---------------------------------------------------------

def _score(signals):

    import math


    score = 0


    score += (
        (1 - signals["trust"])
        *
        0.30
    )


    score += (
        min(
            signals["v60"] / 20,
            1
        )
        *
        0.15
    )


    score += (
        min(
            signals["v5m"] / 50,
            1
        )
        *
        0.10
    )


    score += (
        min(
            signals["v1h"] / 200,
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
        _clamp(score),
        4
    )





def _verdict(score):

    if score < 0.35:

        return "ALLOW"


    if score < 0.70:

        return "CHALLENGE"


    return "BLOCK"
# ---------------------------------------------------------
# COUNTERFACTUAL EXPLANATION
# ---------------------------------------------------------

def _counterfactual(signals, score, verdict):


    if verdict == "ALLOW":

        return {

            "target_verdict": "NONE",

            "message":
                "Decision already reached the most permissive outcome."

        }



    if verdict == "BLOCK":

        target = "CHALLENGE"
        boundary = 0.70


    else:

        target = "ALLOW"
        boundary = 0.35



    gap = round(
        score - boundary,
        4
    )



    contributions = {


        "trust":
            round(
                (1-signals["trust"])
                *
                0.30,
                4
            ),


        "v60":
            round(
                min(
                    signals["v60"]/20,
                    1
                )
                *
                0.15,
                4
            ),


        "v5m":
            round(
                min(
                    signals["v5m"]/50,
                    1
                )
                *
                0.10,
                4
            ),


        "v1h":
            round(
                min(
                    signals["v1h"]/200,
                    1
                )
                *
                0.10,
                4
            ),


        "amount":
            round(
                min(
                    __import__("math").log1p(
                        signals["amount"]
                    )
                    /
                    __import__("math").log1p(10000),
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
            )

    }



    highest = max(
        contributions,
        key=contributions.get
    )



    return {


        "target_verdict":

            target,


        "boundary":

            boundary,


        "score_distance":

            gap,


        "highest_contributing_factor":

            highest,


        "contributions":

            contributions,


        "statement":

            (
                "This decision was "
                +
                verdict
                +
                " with score "
                +
                str(score)
                +
                ". The nearest alternative was "
                +
                target
                +
                ". The largest removable contribution came from "
                +
                highest
                +
                "."
            )

    }





# ---------------------------------------------------------
# AUDIT SEAL
# ---------------------------------------------------------

def _seal(ctx, api_key, signals, result):


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


        "version":

            VERSION,


        "score":

            result.get("score"),


        "verdict":

            result.get("verdict"),


        "counterfactual":

            result.get("counterfactual")

    }



    try:

        h, block, seq = ctx["seal"](

            event,

            receipt,

            timestamp,

            api_key

        )


        return {

            "audit_hash": h,

            "block_index": block,

            "receipt_sequence": seq

        }


    except Exception:


        return {

            "audit_hash":

                _hash(receipt)

        }
# ---------------------------------------------------------
# STORE RESULT
# ---------------------------------------------------------

def _store(ctx, api_key, result, signals):

    with ctx["lock"]:

        ctx["conn"].execute(

            """
            INSERT INTO proving_runs
            (
                api_key,
                created,
                verdict,
                score,
                payload,
                audit_hash
            )
            VALUES (?,?,?,?,?,?)
            """,

            (

                api_key,

                time.time(),

                result.get("verdict"),

                result.get("score"),

                json.dumps(signals),

                result.get("audit_hash")

            )

        )


        ctx["conn"].commit()





# ---------------------------------------------------------
# RUN PROVING GROUND TEST
# ---------------------------------------------------------

def _run(ctx, api_key, data):


    signals = _normalise(
        data
    )


    score = _score(
        signals
    )


    verdict = _verdict(
        score
    )


    result = {

        "score":

            score,


        "verdict":

            verdict

    }



    result["counterfactual"] = _counterfactual(

        signals,

        score,

        verdict

    )



    result.update(

        _seal(

            ctx,

            api_key,

            signals,

            result

        )

    )



    result["inputs_used"] = signals



    _store(

        ctx,

        api_key,

        result,

        signals

    )



    result["verification"] = {

        "deterministic":

            True,


        "message":

            "The same inputs always produce the same result."

    }



    return result, 200





# ---------------------------------------------------------
# VERIFY RESULT
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



    signals = json.loads(
        row[2]
    )



    recalculated = _score(
        signals
    )


    verdict = _verdict(
        recalculated
    )



    return {


        "verified":

            (

                round(
                    float(row[0]),
                    4
                )
                ==
                recalculated

                and

                row[1]
                ==
                verdict

            ),


        "stored_score":

            row[0],


        "
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



        blocked = ctx["conn"].execute(

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

            blocked,


        "module":

            "proving_ground"

    },200





# ---------------------------------------------------------
# PROBING MONITOR
# ---------------------------------------------------------

def _probing(ctx, api_key):

    with ctx["lock"]:

        count = ctx["conn"].execute(

            """
            SELECT COUNT(*)
            FROM proving_runs
            WHERE api_key=?
            AND created>?
            """,

            (

                api_key,

                time.time()-86400

            )

        ).fetchone()[0]



    return {


        "requests_24h":

            count,


        "monitoring":

            "active"

    },200





# ---------------------------------------------------------
# MODULE ROUTER
# ---------------------------------------------------------

def handle(method, action, data, api_key, ctx):


    _setup(ctx)



    if method == "GET":


        if action == "health":

            return _health()



        if action == "stats":

            return _stats(

                ctx,

                api_key

            )



        if action == "verify":

            return _verify(

                ctx,

                api_key,

                data

            )



        if action == "probing":

            return _probing(

                ctx,

                api_key

            )



    if method == "POST":


        if action == "run":

            return _run(

                ctx,

                api_key,

                data

            )



    return {


        "error":

            "unknown_action",


        "available":

            [

                "GET health",

                "POST run",

                "GET verify",

                "GET stats",

                "GET probing"

            ]

    },404
