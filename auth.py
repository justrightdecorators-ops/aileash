import time
import secrets
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
import aiosqlite
from config import DB_PATH, FREE_TIER_LIMIT

router = APIRouter(tags=["Authentication"])

class SignupRequest(BaseModel):
    email: str

async def get_key_record(api_key: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM api_keys WHERE key=? AND active=1", (api_key,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Invalid API key configuration")
            return dict(row)

async def increment_usage(api_key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE api_keys SET usage_count = usage_count + 1 WHERE key=?", (api_key,))
        await db.commit()

@router.post("/signup")
async def signup(req: SignupRequest):
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email address required")
        
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key FROM api_keys WHERE email=?", (email,)) as cursor:
            existing = await cursor.fetchone()
            if existing:
                return {"message": "Key exists", "api_key": existing["key"], "tier": existing["tier"]}
        
        api_key = "al_" + secrets.token_urlsafe(32)
        await db.execute(
            "INSERT INTO api_keys (key, email, tier, usage_count, created_at, active) VALUES (?, ?, 'free', 0, ?, 1)",
            (api_key, email, time.time())
        )
        await db.commit()
        
    return {"message": "Success", "api_key": api_key, "tier": "free", "requests_remaining": FREE_TIER_LIMIT}
