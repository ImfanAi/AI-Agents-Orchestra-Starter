from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
import asyncio, uuid, time, logging, sys
from typing import Dict, List

from app.core.config import get_config, validate_startup_config
from app.core.logging_utils import setup_logging, log_config_on_startup, get_logger
from app.core.middleware import (
    RequestLoggingMiddleware, 
    RateLimitMiddleware, 
    SecurityHeadersMiddleware,
    auth_handler,
    get_authenticated_user
)
from app.core.exceptions import (
    WandException,
    ResourceNotFoundError,
    ValidationError,
    ExecutionError,
    ErrorResponse
)
from app.core.error_handlers import (
    ExceptionHandlingMiddleware,
    wand_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    generic_exception_handler,
    raise_not_found,
    raise_validation_error,
    convert_exceptions
)
from app.core.validation import ValidatedGraphRequest, ValidatedRunRequest
from app.core.registry import ToolRegistry, AgentRegistry
from app.runtime.executor import Executor, GraphSpec, NodeSpec, EdgeSpec
from app.storage import init_db, save_run, append_event, load_events
from contextlib import asynccontextmanager


# ----------------------- Lifespan (startup/shutdown) ------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    validate_startup_config()
    setup_logging()
    log_config_on_startup()
    await init_db()
    yield

# Get configuration
config = get_config()
logger = get_logger("wand.main")

app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description=(
        "DAG-based multi-agent orchestration layer.\n\n"
        "- Concurrency / Retries / Timeouts\n"
        "- Pluggable Tools & Agents\n"
        "- SSE streaming and cancellation\n"
        "- Configuration-driven setup\n"
        "- Enhanced error handling and validation\n"
        "- Authentication and rate limiting"
    ),
    contact={"name": "Maksim", "url": "https://github.com/mcnic"},
    license_info={"name": "MIT"},
    lifespan=lifespan,
    debug=config.debug
)

# Add exception handlers
app.add_exception_handler(WandException, wand_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Add middleware in correct order (last added = first executed)
app.add_middleware(ExceptionHandlingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.security.cors_origins,
    allow_credentials=config.security.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

# In-memory storage (would be replaced with proper database in production)
GRAPHS: dict[str, GraphSpec] = {}
RUNS: dict[str, dict] = {}
EVENTS: dict[str, list] = {}

# Initialize components
tool_registry = ToolRegistry()
agent_registry = AgentRegistry()
executor = Executor(tool_registry, agent_registry)

class RunCtrl:
    def __init__(self):
        self.cancel_event = asyncio.Event()
        self.queue: asyncio.Queue = asyncio.Queue()

RUN_CTRLS: Dict[str, RunCtrl] = {}

# ---------- API Schemas ----------
class CreateGraphResp(BaseModel):
    graph_id: str = Field(..., example="g_ab12cd34")

class CreateRunResp(BaseModel):
    run_id: str = Field(..., example="r_ef567890")

class RunState(BaseModel):
    status: str = Field(..., example="SUCCESS")
    result: dict | None = None
    error: str | None = None

class EventLog(BaseModel):
    ts: float | None = Field(None, example=time.time())
    lvl: str | None = Field(None, example="info")
    msg: str | None = Field(None, example="node.start analyze")
    progress: int | None = Field(None, example=66)

@app.get("/health", tags=["systems"], summary="Health Check")
def health():
    """Health check endpoint - no authentication required."""
    return {
        "ok": True, 
        "version": config.app_version,
        "environment": config.environment,
        "timestamp": time.time()
    }

@app.post(
    "/graphs",
    response_model=CreateGraphResp,
    tags=["graphs"],
    summary="Create (register) an execution graph"
)
def create_graph(req: ValidatedGraphRequest, user=Depends(get_authenticated_user)):
    """Create and register a new execution graph with enhanced validation."""
    with convert_exceptions("graph creation"):
        gid = f"g_{uuid.uuid4().hex[:8]}"
        
        # Convert validated request to GraphSpec
        spec = GraphSpec(
            name=req.name, 
            nodes=[NodeSpec(**node) for node in req.nodes], 
            edges=[EdgeSpec(**edge) for edge in req.edges], 
            options=req.options or {}
        )
        
        GRAPHS[gid] = spec
        logger.info(f"Graph created: {gid} - {req.name}")
        return {"graph_id": gid}

class CreateRunReq(BaseModel):
    graph_id: str
    input: dict | None = None

@app.post(
    "/runs",
    response_model=CreateRunResp,
    tags=["runs"],
    summary="Start a run for a given graph",
)
async def create_run(req: ValidatedRunRequest, user=Depends(get_authenticated_user)):
    """Start execution of a graph with enhanced validation."""
    with convert_exceptions("run creation"):
        if req.graph_id not in GRAPHS:
            raise_not_found("graph", req.graph_id)
        
        rid = f"r_{uuid.uuid4().hex[:8]}"
        RUNS[rid] = {"status": "PENDING", "result": None, "error": None}
        EVENTS[rid] = []
        logger.info(f"Run created: {rid} for graph={req.graph_id}")
        RUN_CTRLS[rid] = RunCtrl()
        await save_run(rid, GRAPHS[req.graph_id].name, "PENDING", None, None)
        
        # Add run_id to emit function for logging
        async def emit_with_run_id(evt: dict):
            await RUN_CTRLS[rid].queue.put(evt)
            await append_event(rid, evt)
        emit_with_run_id._run_id = rid
        
        asyncio.create_task(_run_background(rid, GRAPHS[req.graph_id], EVENTS[rid], RUN_CTRLS[rid], emit_with_run_id))
        return {"run_id": rid}

async def _run_background(run_id: str, graph: GraphSpec, events: list, ctrl: RunCtrl, on_event_func):
    """Background task for executing graph runs with enhanced error handling."""
    logger.info(f"Run {run_id} started")
    RUNS[run_id]["status"] = "RUNNING"
    await save_run(run_id, graph.name, "RUNNING", None, None)

    try:
        with convert_exceptions("graph execution"):
            result = await executor.execute(
                graph, 
                events,
                cancel_event=ctrl.cancel_event,
                on_event=on_event_func
            )
        RUNS[run_id]["status"] = "SUCCESS"
        RUNS[run_id]["result"] = result
        await save_run(run_id, graph.name, "SUCCESS", result, None)
        await ctrl.queue.put({"ts": time.time(), "lvl": "info", "msg": "run.success"})
        logger.info(f"Run {run_id} completed successfully")
    except asyncio.CancelledError:
        RUNS[run_id]["status"] = "CANCELLED"
        RUNS[run_id]["error"] = "cancelled"
        await save_run(run_id, graph.name, "CANCELLED", None, "cancelled")
        await ctrl.queue.put({"ts": time.time(), "lvl": "warn", "msg": "run.cancelled"})
        logger.warning(f"Run {run_id} was cancelled")
    except WandException as e:
        RUNS[run_id]["status"] = "FAILED"
        RUNS[run_id]["error"] = e.message
        await save_run(run_id, graph.name, "FAILED", None, e.message)
        await ctrl.queue.put({"ts": time.time(), "lvl": "error", "msg": f"run.failed: {e.message}"})
        logger.error(f"Run {run_id} failed: {e.message}")
    except Exception as e:
        RUNS[run_id]["status"] = "FAILED"
        RUNS[run_id]["error"] = str(e)
        await save_run(run_id, graph.name, "FAILED", None, str(e))
        await ctrl.queue.put({"ts": time.time(), "lvl": "error", "msg": f"run.failed: {e}"})
        logger.error(f"Run {run_id} failed: {e}")
    finally:
        await ctrl.queue.put({"eof": True})

@app.get(
    "/runs/{run_id}",
    response_model=RunState,
    tags=["runs"],
    summary="Get run status and result",
)
def get_run(run_id: str, user=Depends(get_authenticated_user)):
    """Get the current status and result of a run."""
    if run_id not in RUNS:
        raise_not_found("run", run_id)
    return RUNS[run_id]

@app.get(
    "/runs/{run_id}/logs",
    response_model=List[EventLog],
    tags=["runs"],
    summary="Get run event logs",
)
async def get_logs(run_id: str, user=Depends(get_authenticated_user)):
    """Get all logged events for a run."""
    if run_id not in EVENTS:
        raise_not_found("run", run_id)
    
    with convert_exceptions("log retrieval"):
        return await load_events(run_id)

@app.get("/runs/{run_id}/stream", tags=["runs"], summary="SSE stream of run events")
async def stream(run_id: str, user=Depends(get_authenticated_user)):
    """Stream run events in real-time via Server-Sent Events."""
    if run_id not in RUN_CTRLS:
        raise_not_found("run", run_id)
    
    async def event_gen():
        q = RUN_CTRLS[run_id].queue
        yield f"data: {{'msg':'stream.start', 'run_id':'{run_id}'}}\n\n"
        while True:
            evt = await q.get()
            if evt.get("eof"):
                yield f"data: {{'msg':'stream.end', 'run_id':'{run_id}'}}\n\n"
                break
            yield f"data: {evt}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")

@app.post(
    "/runs/{run_id}/cancel",
    tags=["runs"],
    summary="Cancel a running execution"
)
async def cancel_run(run_id: str, user=Depends(get_authenticated_user)):
    """Cancel an active run."""
    if run_id not in RUN_CTRLS:
        raise_not_found("run", run_id)
    
    RUN_CTRLS[run_id].cancel_event.set()
    logger.info(f"Run {run_id} cancellation requested")
    return {"ok": True, "message": f"Cancellation requested for run {run_id}"}

# Configuration endpoints
@app.get("/config", tags=["configuration"], summary="Get current configuration")
async def get_configuration(user=Depends(get_authenticated_user)):
    """Get current application configuration (excluding sensitive data)."""
    config_dict = config.to_dict()
    
    # Remove sensitive information
    if "security" in config_dict:
        config_dict["security"] = {
            k: ("***" if k in ["api_key", "jwt_secret"] else v)
            for k, v in config_dict["security"].items()
        }
    
    return {
        "configuration": config_dict,
        "warnings": config.validate_config(),
        "environment": config.environment,
        "is_production": config.is_production()
    }

@app.get("/config/validate", tags=["configuration"], summary="Validate current configuration")
async def validate_configuration(user=Depends(get_authenticated_user)):
    """Validate current configuration and return any issues."""
    warnings = config.validate_config()
    
    return {
        "valid": len(warnings) == 0,
        "warnings": warnings,
        "environment": config.environment
    }
