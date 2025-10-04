import aiosqlite
import json
from typing import Any, List, Dict

DB_PATH = "./wand.db"

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

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        for stmt in CREATE_SQL.strip().split(";"):
            s = stmt.strip()
            if s:
                await db.execute(s)
        await db.commit()

async def save_run(run_id: str, graph_name: str, status: str, result: Dict|None, error: str|None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO runs(id, graph_name, status, result_json, error) VALUES (?,?,?,?,?)",
            (run_id, graph_name, status, json.dumps(result or {}), error)
        )
        await db.commit()

async def append_event(run_id: str, evt: Dict[str, Any]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO events(run_id, ts, lvl, msg, payload_json) VALUES (?,?,?,?,?)",
            (run_id, evt.get("ts"), evt.get("lvl"), evt.get("msg"), json.dumps(evt))
        )
        await db.commit()

async def load_events(run_id: str) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT payload_json FROM events WHERE run_id=? ORDER BY id ASC", (run_id,))
        rows = await cur.fetchall()
    return [json.loads(r[0]) for r in rows]
