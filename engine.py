import time
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
import aiosqlite
from config import DB_PATH, FREE_TIER_LIMIT
import auth
import risk_vectors

router = APIRouter(tags=["Engine UI"])

class GovernRequest(BaseModel):
    action: str
    amount: float = 0.0
    device_risk: float = 0.0
    anomaly: float = 0.0
    country: str = "US"
    agent_id: str = "default"

async def evaluate_velocity(agent_id: str) -> float:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO velocity VALUES (?, ?)", (agent_id, now))
        await db.commit()
        
        async with db.execute("SELECT COUNT(*) FROM velocity WHERE agent_id=? AND ts>?", (agent_id, now - 60)) as c:
            w1 = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM velocity WHERE agent_id=? AND ts>?", (agent_id, now - 300)) as c:
            w2 = (await c.fetchone())[0]
            
        await db.execute("DELETE FROM velocity WHERE agent_id=? AND ts<?", (agent_id, now - 3600))
        await db.commit()

    score = 0.0
    if w1 > 10: score += 0.4
    elif w1 > 5: score += 0.2
    if w2 > 30: score += 0.4
    elif w2 > 15: score += 0.2
    return min(1.0, score)

async def get_and_update_trust(agent_id: str, decision: str) -> float:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM trust_scores WHERE agent_id=?", (agent_id,)) as cursor:
            row = await cursor.fetchone()
        
        if row:
            current_score = row["score"]
            total = row["total_reqs"] + 1
            blocks = row["blocks"] + (1 if decision == "BLOCK" else 0)
            
            if decision == "ALLOW":
                new_score = min(1.0, current_score + 0.01)
            elif decision == "CHALLENGE":
                new_score = max(0.0, current_score - 0.05)
            else:
                new_score = max(0.0, current_score - 0.15)
                
            await db.execute(
                "UPDATE trust_scores SET score=?, total_reqs=?, blocks=?, updated_at=? WHERE agent_id=?",
                (new_score, total, blocks, now, agent_id)
            )
        else:
            new_score = 0.5
            await db.execute(
                "INSERT INTO trust_scores VALUES (?, 0.5, 1, ?, ?)",
                (agent_id, 1 if decision == "BLOCK" else 0, now)
            )
        await db.commit()
        return new_score

async def write_audit_chain(api_key: str, agent_id: str, action: str, score: float, decision: str, amount: float, country: str, anomaly: float, device_risk: float) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1") as cursor:
            last_row = await cursor.fetchone()
            prev_hash = last_row["entry_hash"] if last_row else "0" * 64
        
        now = time.time()
        raw_payload = f"{now}{api_key}{agent_id}{action}{score}{decision}{prev_hash}"
        entry_hash = hashlib.sha256(raw_payload.encode()).hexdigest()
        
        await db.execute("""
            INSERT INTO audit_log 
            (ts, api_key, agent_id, action, score, decision, amount, country, anomaly, device_risk, entry_hash, prev_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, api_key, agent_id, action, score, decision, amount, country, anomaly, device_risk, entry_hash, prev_hash))
        await db.commit()
        return entry_hash

@router.post("/govern")
async def govern(req: GovernRequest, x_api_key: str = Header(...)):
    record = await auth.get_key_record(x_api_key)
    if record["tier"] == "free" and record["usage_count"] >= FREE_TIER_LIMIT:
        raise HTTPException(status_code=402, detail="Request allotment exceeded. Upgrade at /checkout")
        
    await auth.increment_usage(x_api_key)
    velocity_factor = await evaluate_velocity(req.agent_id)
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT score FROM trust_scores WHERE agent_id=?", (req.agent_id,)) as c:
            t_row = await c.fetchone()
            current_trust = t_row["score"] if t_row else 0.5

    final_score = risk_vectors.calculate_risk(req.amount, req.device_risk, req.anomaly, req.country, current_trust, velocity_factor)
    
    if final_score < 0.30: decision = "ALLOW"
    elif final_score < 0.70: decision = "CHALLENGE"
    else: decision = "BLOCK"
    
    audit_hash = await write_audit_chain(x_api_key, req.agent_id, req.action, final_score, decision, req.amount, req.country, req.anomaly, req.device_risk)
    new_trust = await get_and_update_trust(req.agent_id, decision)
    
    return {
        "decision": decision,
        "score": final_score,
        "agent_id": req.agent_id,
        "trust_score": round(new_trust, 4),
        "audit_hash": audit_hash,
        "ts": datetime.now(timezone.utc).isoformat()
    }
