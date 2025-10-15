import aiosqlite
import json
from typing import Any, List, Dict
from pathlib import Path

from app.core.config import get_config
from app.core.logging_utils import get_logger

logger = get_logger("wand.storage")

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS runs(
  id TEXT PRIMARY KEY,
  graph_name TEXT,
  status TEXT,
  result_json TEXT,
  error TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT,
  ts REAL,
  lvl TEXT,
  msg TEXT,
  payload_json TEXT
);
"""

async def get_db_path() -> str:
    """Get database path from configuration."""
    config = get_config()
    db_url = config.get_database_url()
    
    if db_url.startswith("sqlite:///"):
        return db_url[10:]  # Remove "sqlite:///" prefix
    else:
        # For non-SQLite databases, we might need different handling
        # For now, fall back to default SQLite path
        logger.warning(f"Non-SQLite database URL configured: {db_url}, using default SQLite")
        return "./wand.db"


async def init_db():
    db_path = await get_db_path()
    logger.info(f"Initializing database at: {db_path}")
    
    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    async with aiosqlite.connect(db_path) as db:
        for stmt in CREATE_SQL.strip().split(";"):
            s = stmt.strip()
            if s:
                await db.execute(s)
        await db.commit()
    
    logger.info("Database initialized successfully")

async def save_run(run_id: str, graph_name: str, status: str, result: Dict|None, error: str|None):
    db_path = await get_db_path()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO runs(id, graph_name, status, result_json, error) VALUES (?,?,?,?,?)",
            (run_id, graph_name, status, json.dumps(result or {}), error)
        )
        await db.commit()
    
    logger.debug(f"Saved run {run_id} with status {status}")

async def append_event(run_id: str, evt: Dict[str, Any]):
    db_path = await get_db_path()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO events(run_id, ts, lvl, msg, payload_json) VALUES (?,?,?,?,?)",
            (run_id, evt.get("ts"), evt.get("lvl"), evt.get("msg"), json.dumps(evt))
        )
        await db.commit()

async def load_events(run_id: str) -> List[Dict[str, Any]]:
    db_path = await get_db_path()
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT payload_json FROM events WHERE run_id=? ORDER BY id ASC", (run_id,))
        rows = await cur.fetchall()
    return [json.loads(r[0]) for r in rows]
