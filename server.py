import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import aiosqlite

from config import DB_PATH, ADMIN_KEY, PRODUCT, VERSION
import auth
import billing
import engine
import memory
import risk_vectors

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key          TEXT PRIMARY KEY,
                email        TEXT UNIQUE NOT NULL,
                tier         TEXT DEFAULT 'free',
                usage_count  INTEGER DEFAULT 0,
                created_at   REAL NOT NULL,
                active       INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trust_scores (
                agent_id   TEXT PRIMARY KEY,
                score      REAL DEFAULT 0.5,
                total_reqs INTEGER DEFAULT 0,
                blocks     INTEGER DEFAULT 0,
                updated_at REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS velocity (
                agent_id TEXT NOT NULL,
                ts       REAL NOT NULL
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_vel ON velocity(agent_id, ts)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          REAL NOT NULL,
                api_key     TEXT NOT NULL,
                agent_id    TEXT NOT NULL,
                action      TEXT NOT NULL,
                score       REAL NOT NULL,
                decision    TEXT NOT NULL,
                amount      REAL,
                country     TEXT,
                anomaly     REAL,
                device_risk REAL,
                entry_hash  TEXT NOT NULL,
                prev_hash   TEXT NOT NULL
            )
        """)
        await db.commit()
    print(f"[{PRODUCT} Router] Engine Booted. ADMIN_KEY={ADMIN_KEY}")
    yield

app = FastAPI(title=PRODUCT, version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(engine.router)
app.include_router(memory.router)
app.include_router(risk_vectors.router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")
