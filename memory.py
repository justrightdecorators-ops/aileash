import hashlib
from fastapi import APIRouter, Header, HTTPException
import aiosqlite
from config import DB_PATH
import auth

router = APIRouter(tags=["Ledger System"])

@router.get("/audit/verify")
async def verify_ledger(x_api_key: str = Header(...)):
    await auth.get_key_record(x_api_key)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM audit_log WHERE api_key=? ORDER BY id ASC", (x_api_key,)) as cursor:
            rows = await cursor.fetchall()
            
    if not rows:
        return {"valid": True, "entries_checked": 0, "message": "Ledger state clean"}
        
    prev = "0" * 64
    for row in rows:
        raw = f"{row['ts']}{row['api_key']}{row['agent_id']}{row['action']}{row['score']}{row['decision']}{prev}"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        if expected != row["entry_hash"]:
            return {"valid": False, "broken_at_id": row["id"], "message": f"Verification sequence broken at entry ID {row['id']}"}
        prev = row["entry_hash"]
        
    return {"valid": True, "entries_checked": len(rows), "message": "SHA-256 validation chain complete"}

@router.get("/audit/chain")
async def audit_chain(limit: int = 50, x_api_key: str = Header(...)):
    await auth.get_key_record(x_api_key)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM audit_log WHERE api_key=? ORDER BY id DESC LIMIT ?", (x_api_key, limit)) as cursor:
            rows = await cursor.fetchall()
    return {"total": len(rows), "entries": [dict(r) for r in rows]}
  
