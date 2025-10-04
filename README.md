# Wand Orchestrator — Multi-Agent Task Solver

A reference backend for **multi-agent orchestration**, built with **FastAPI + asyncio**.  
Implements DAG-based agent execution with concurrency, retries, timeouts, pluggable tools, and SSE streaming.

---

## ✨ Features

- **Agent Orchestration (DAG)**
  - Agents run in isolation, can pass results via edges.
  - Concurrency, retries, backoff, timeouts supported.
- **Pluggable Tools & Agents**
  - Tools: HTTP fetcher, chart generator (mock).
  - Agents: Fetch → Analyze → Chart pipeline.
- **Execution Graph API**
  - Define nodes/edges → create graphs → run asynchronously.
- **Observability**
  - Logs per run, persisted to SQLite (`wand.db`).
  - SSE stream for real-time events & progress %.
- **Control**
  - Cancel API to stop ongoing run.
- **Production Ready Add-ons**
  - `.env` config (API key, DB URL, SSE queue size).
  - API Key auth via `X-API-Key` header.
  - Dockerized, lightweight, non-root runtime.

---

## 🛠️ Requirements

- Python 3.11+
- (optional) Docker / Docker Compose

---

## 🚀 Quick Start (Local)

```bash
# 1. Clone & enter project
cd wand

# 2. Setup venv
python -m venv .venv
.venv\Scripts\activate   # Windows
# or
source .venv/bin/activate  # Linux/Mac

# 3. Install deps
pip install -r requirements.txt

# 4. Run server
uvicorn app.main:app --reload --port 8000

# 5. Health check
curl http://127.0.0.1:8000/health
```

---

## 🐳 Run with Docker

```bash
# 1. Build image
docker build -t wand-orchestrator .

# 2. Run container
docker run --rm -p 8000:8000 --env-file .env --name wand-orch wand-orchestrator
```

---

## 📡 API Usage

### 1. Health
```http
GET /health
```

### 2. Swagger Docs
```
Swagger UI: http://127.0.0.1:8000/docs
```

### 3. Create Graph
```http
POST /graphs
Body:
{
  "name": "demo",
  "nodes": [
    { "id": "fetch", "type": "agent.fetch", "params": { "url": "https://example.com" } },
    { "id": "analyze", "type": "agent.analyze", "params": {} },
    { "id": "chart", "type": "agent.chart", "params": { "spec": {"kind":"line"} } }
  ],
  "edges": [
    { "from": "fetch", "to": "analyze", "map": { "text": "body" } },
    { "from": "analyze", "to": "chart", "map": { "series": "insights" } }
  ],
  "options": { "concurrency": 2, "default_timeout_sec": 10, "max_retries": 1 },
  "sinks": ["chart"]
}
```

Response:
```json
{ "graph_id": "g_1234abcd" }
```

### 4. Run Graph
```http
POST /runs
Body: { "graph_id": "g_1234abcd" }
```

Response:
```json
{ "run_id": "r_abcd5678" }
```

### 5. Check Run
```http
GET /runs/{run_id}
```

### 6. Logs
```http
GET /runs/{run_id}/logs
```

### 7. SSE Stream
```http
GET /runs/{run_id}/stream
```
Events stream continuously while run is executing.

### 8. Cancel
```http
POST /runs/{run_id}/cancel
```

---

## 🧩 Architecture

- **`core/`** — Interfaces (Agent, Tool) + Registries
- **`plugins/`** — Sample tools & agents
- **`runtime/`** — DAG Executor (concurrency, retries, timeouts, conditional edges, optional nodes)
- **`storage.py`** — SQLite persistence (runs, events)
- **`main.py`** — FastAPI app, APIs, SSE stream, cancel
- **`config.py`** — Environment config loader

Execution flow:
```
GraphSpec → Executor → Agents/Tools
              │
              ├─ Concurrency & retries
              ├─ Events logged to memory & DB
              └─ SSE stream to clients
```

---

## 🧪 Testing

```bash
pytest -q
```

Example test (`tests/test_graph.py`):
```python
def test_pipeline():
    ...
    assert "outputs" in res and "analyze" in res["outputs"]
```

---

## 📌 Design Decisions

- **Registry Pattern**: Tools/Agents are dynamically pluggable via registries, enabling modular extension.

- **Async Executor**: DAG executor built with asyncio for efficient concurrency & cancel handling.

- **Persistence**: SQLite chosen for simplicity (zero-setup, file-based). Suitable for demo, swappable for Postgres/Kafka in production.

- **Events**: In-memory + DB dual write, exposed via /logs and /stream.

---

## 📌 Notes & Trade-offs

- **Isolation**: Implemented with in-process asyncio. Real OS-level sandbox (process/container per agent) left out for time.

- **Retries**: Exponential backoff implemented simply, capped at 2s, no jitter/randomization.

- **Dynamic Plugin Loading**: Registry is code-level only. Runtime upload/register APIs not included due to security/time.

- **Schema Validation**: Pydantic schemas used selectively. Full schema registry skipped to save time.

- **Orchestrator Scope**: Single-node execution only. No distributed workers/queue due to 24h constraint.

---

## 📄 License

MIT (for demo/assessment use)
