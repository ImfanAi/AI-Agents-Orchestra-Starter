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
  - Structured logging with JSON support.
- **Control**
  - Cancel API to stop ongoing run.
- **Configuration Management**
  - Environment-based configuration with validation.
  - Comprehensive settings for all components.
  - Development and production configurations.
- **Security & Production Ready**
  - API key authentication.
  - Rate limiting and CORS protection.
  - Request logging and performance monitoring.
  - Security headers middleware.
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

# 4. Setup configuration
python dev.py setup  # Creates .env from .env.example

# 5. Run server (development mode)
python dev.py server
# or
uvicorn app.main:app --reload --port 8000

# 6. Health check
curl http://127.0.0.1:8000/health
```

---

## ⚙️ Configuration

Wand Orchestrator uses environment-based configuration with comprehensive validation.

### Configuration Files

- `.env.example` - Template with all available settings
- `.env` - Local development configuration
- `.env.production` - Production configuration template

### Quick Setup

```bash
# Create .env file from template
python dev.py setup

# Validate configuration
python dev.py validate

# View current configuration
python dev.py config
```

### Key Configuration Sections

#### Application Settings
```env
ENVIRONMENT=development
DEBUG=true
HOST=0.0.0.0
PORT=8000
```

#### Database Configuration
```env
DATABASE__URL=sqlite:///./wand.db
DATABASE__MAX_CONNECTIONS=10
```

#### Security Settings
```env
SECURITY__API_KEY=your-secret-api-key
SECURITY__CORS_ORIGINS=["http://localhost:3000"]
SECURITY__RATE_LIMIT_PER_MINUTE=60
```

#### Execution Engine
```env
EXECUTION__DEFAULT_TIMEOUT_SEC=30
EXECUTION__MAX_RETRIES=3
EXECUTION__DEFAULT_CONCURRENCY=5
```

#### Logging
```env
LOGGING__LEVEL=INFO
LOGGING__JSON_FORMAT=false
LOGGING__FILE_PATH=./logs/wand.log
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

### Authentication

Most endpoints require authentication via API key:

```bash
# Set API key in headers
curl -H "X-API-Key: your-api-key" http://127.0.0.1:8000/graphs

# Or use Authorization header
curl -H "Authorization: Bearer your-api-key" http://127.0.0.1:8000/graphs
```

### 1. Health
```http
GET /health
```

### 2. Swagger Docs
```
Swagger UI: http://127.0.0.1:8000/docs
```

### 3. Configuration (Admin)
```http
GET /config
GET /config/validate
```

### 4. Create Graph
```http
POST /graphs
Headers: X-API-Key: your-api-key
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

### 5. Run Graph
```http
POST /runs
Headers: X-API-Key: your-api-key
Body: { "graph_id": "g_1234abcd" }
```

Response:
```json
{ "run_id": "r_abcd5678" }
```

### 6. Check Run
```http
GET /runs/{run_id}
Headers: X-API-Key: your-api-key
```

### 7. Logs
```http
GET /runs/{run_id}/logs
Headers: X-API-Key: your-api-key
```

### 8. SSE Stream
```http
GET /runs/{run_id}/stream
Headers: X-API-Key: your-api-key
```
Events stream continuously while run is executing.

### 9. Cancel
```http
POST /runs/{run_id}/cancel
Headers: X-API-Key: your-api-key
```

---

## 🧩 Architecture

- **`core/`** — Interfaces, Configuration, Middleware, Logging
- **`plugins/`** — Sample tools & agents
- **`runtime/`** — DAG Executor (concurrency, retries, timeouts, conditional edges, optional nodes)
- **`storage.py`** — SQLite persistence (runs, events)
- **`main.py`** — FastAPI app, APIs, SSE stream, cancel

Execution flow:
```
GraphSpec → Executor → Agents/Tools
              │
              ├─ Concurrency & retries
              ├─ Events logged to memory & DB
              ├─ Structured logging & monitoring
              └─ SSE stream to clients
```

### Configuration Management

```
Environment Variables → WandConfig → Validation
                             │
                             ├─ Type safety with Pydantic
                             ├─ Nested configuration sections
                             ├─ Environment-specific defaults
                             └─ Runtime validation warnings
```

---

## 🧪 Testing

```bash
# Run tests
pytest -q

# Test with coverage
pytest --cov=app tests/

# Validate configuration
python dev.py validate
```

Example test (`tests/test_graph.py`):
```python
def test_pipeline():
    ...
    assert "outputs" in res and "analyze" in res["outputs"]
```

---

## � Development

### Development Utilities

```bash
# Setup development environment
python dev.py setup

# Run development server with auto-reload
python dev.py server

# Validate current configuration
python dev.py validate

# Show current configuration (non-sensitive)
python dev.py config
```

### Environment Management

- **Development**: Debug mode, console logging, SQLite database
- **Testing**: Minimal logging, in-memory database
- **Staging**: Production-like with debug features
- **Production**: Optimized logging, external database, security hardened

---

## �📌 Design Decisions

- **Configuration-First**: All settings configurable via environment variables with validation.

- **Registry Pattern**: Tools/Agents are dynamically pluggable via registries, enabling modular extension.

- **Async Executor**: DAG executor built with asyncio for efficient concurrency & cancel handling.

- **Persistence**: SQLite chosen for simplicity (zero-setup, file-based). Configurable for Postgres/other databases.

- **Security**: API key authentication, rate limiting, CORS protection, security headers.

- **Observability**: Structured logging, request tracing, performance monitoring, health checks.

- **Events**: In-memory + DB dual write, exposed via /logs and /stream.

---

## 📌 Configuration Highlights

### Validation & Type Safety
- Pydantic-based configuration with automatic validation
- Environment-specific validation rules
- Type coercion and bounds checking
- Comprehensive error messages

### Environment Support
- Development, testing, staging, production environments
- Environment-specific defaults and validation
- Configuration warnings for production readiness

### Nested Configuration
- Hierarchical configuration sections (database, security, logging, etc.)
- Environment variable mapping with `__` delimiter
- Individual component configuration isolation

### Runtime Configuration
- Configuration validation on startup
- Runtime configuration inspection via API
- Hot-reload capabilities in development

---

## 📌 Notes & Trade-offs

- **Authentication**: API key-based authentication with optional JWT support planned.

- **Rate Limiting**: Simple in-memory rate limiting. Redis-based distributed rate limiting available via configuration.

- **Configuration**: Environment-based with comprehensive validation. Runtime updates via API in development mode.

- **Isolation**: Implemented with in-process asyncio. Real OS-level sandbox (process/container per agent) configurable.

- **Retries**: Configurable exponential backoff with jitter and maximum delay limits.

- **Logging**: Structured logging with JSON support, file rotation, and performance monitoring.

- **Monitoring**: Built-in health checks, metrics collection, and distributed tracing support.

- **Database**: SQLite default with PostgreSQL/MySQL support via configuration.

---

## 📄 License

MIT (for demo/assessment use)
