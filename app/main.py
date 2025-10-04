from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncio, uuid, time, logging, sys
from typing import Dict, List

from app.core.registry import ToolRegistry, AgentRegistry
from app.runtime.executor import Executor, GraphSpec, NodeSpec, EdgeSpec
from app.storage import init_db, save_run, append_event, load_events
from contextlib import asynccontextmanager


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("wand")


# ----------------------- Lifespan (startup/shutdown) ------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await init_db()
    yield

app = FastAPI(
    title="Wand Orchestrator (MVP)",
    version="1.0.0",
    description=(
        "DAG-based multi-agent orchestration layer.\n\n"
        "- Concurrency / Retries / Timeouts\n"
        "- Pluggable Tools & Agents\n"
        "- SSE streaming and cancellation\n"
        "- (Demo) Authentication disabled for Swagger"
    ),
    contact={"name": "Maksim", "url": "https://github.com/mcnic"},
    license_info={"name": "MIT"},
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

class CreateGraphReq(BaseModel):
    name: str
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    options: dict | None = None

GRAPHS: dict[str, GraphSpec] = {}
RUNS: dict[str, dict] = {}
EVENTS: dict[str, list] = {}

tool_registry = ToolRegistry()
agent_registry = AgentRegistry()
executor = Executor(tool_registry, agent_registry)

class RunCtrl:
    def __init__(self):
        self.cancel_event = asyncio.Event()
        self.queue: asyncio.Queue = asyncio.Queue()

RUN_CTRLS: Dict[str, RunCtrl] = {}

# ---------- API Schemas ----------
class CreateGraphReq(BaseModel):
    name: str = Field(..., example="demo")
    nodes: List[NodeSpec]
    edges: List[EdgeSpec]
    options: dict | None = Field(default=None, example={"concurrency": 2, "default_timeout_sec": 10, "max_retries": 1})
    sinks: List[str] = Field(default_factory=list)

class CreateGraphResp(BaseModel):
    graph_id: str = Field(..., example="g_ab12cd34")

class CreateRunReq(BaseModel):
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
    return {"ok": True}

@app.post(
    "/graphs",
    response_model=CreateGraphResp,
    tags=["graphs"],
    summary="Create (register) an execution graph"
)
def create_graph(req: CreateGraphReq):
    gid = f"g_{uuid.uuid4().hex[:8]}"
    spec = GraphSpec(
        name=req.name, 
        nodes=req.nodes, 
        edges=req.edges, 
        options=req.options or {}
    )
    GRAPHS[gid] = spec
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
async def create_run(req: CreateRunReq):
    if req.graph_id not in GRAPHS:
        raise HTTPException(404, "graph not found")
    rid = f"r_{uuid.uuid4().hex[:8]}"
    RUNS[rid] = {"status": "PENDING", "result": None, "error": None}
    EVENTS[rid] = []
    logger.info(f"Run created: {rid} for graph={req.graph_id}")
    RUN_CTRLS[rid] = RunCtrl()
    await save_run(rid, GRAPHS[req.graph_id].name, "PENDING", None, None)
    asyncio.create_task(_run_background(rid, GRAPHS[req.graph_id], EVENTS[rid], RUN_CTRLS[rid]))
    return {"run_id": rid}

async def _run_background(run_id: str, graph: GraphSpec, events: list, ctrl: RunCtrl):
    logger.info(f"Run {run_id} started")
    RUNS[run_id]["status"] = "RUNNING"
    await save_run(run_id, graph.name, "RUNNING", None, None)

    async def on_event(evt: dict):
        await ctrl.queue.put(evt)
        await append_event(run_id, evt)

    try:
        result = await executor.execute(
            graph, 
            events,
            cancel_event=ctrl.cancel_event,
            on_event=on_event
        )
        RUNS[run_id]["status"] = "SUCCESS"
        RUNS[run_id]["result"] = result
        await save_run(run_id, graph.name, "SUCCESS", result, None)
        await ctrl.queue.put({"ts": time.time(), "lvl": "info", "msg": "run.success"})
    except asyncio.CancelledError:
        RUNS[run_id]["status"] = "CANCELLED"
        RUNS[run_id]["error"] = "cancelled"
        await save_run(run_id, graph.name, "CANCELLED", None, "cancelled")
        await ctrl.queue.put({"ts": time.time(), "lvl": "warn", "msg": "run.cancelled"})
    except Exception as e:
        RUNS[run_id]["status"] = "FAILED"
        RUNS[run_id]["error"] = str(e)
        await save_run(run_id, graph.name, "FAILED", None, str(e))
        await ctrl.queue.put({"ts": time.time(), "lvl": "error", "msg": f"run.failed: {e}"})
    finally:
        await ctrl.queue.put({"eof": True})

@app.get(
    "/runs/{run_id}",
    response_model=RunState,
    tags=["runs"],
    summary="Get run event log",
)
def get_run(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(404, "run not found")
    return RUNS[run_id]

@app.get(
    "/runs/{run_id}/logs",
    response_model=List[EventLog],
    tags=["run"],
    summary="SSE stream of run events",
)
async def get_logs(run_id: str):
    if run_id not in EVENTS:
        raise HTTPException(404, "run not found")
    return await load_events(run_id)

@app.get("/runs/{run_id}/stream")
async def stream(run_id: str):
    if run_id not in RUN_CTRLS:
        raise HTTPException(404, "run not found")
    
    async def event_gen():
        q = RUN_CTRLS[run_id].queue
        yield f"data: { {'msg':'stream.start'} }\n\n"
        while True:
            evt = await q.get()
            if evt.get("eof"):
                yield f"data: { {'msg':'stream.end'} }"
                break
            yield f"data: {evt}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")

@app.post(
    "/runs/{run_id}/cancel",
    tags=["run"],
    summary="Cancel a running execution"
)
async def cancel_run(run_id: str):
    if run_id not in RUN_CTRLS:
        raise HTTPException(404, "run not found")
    RUN_CTRLS[run_id].cancel_event.set()
    return {"ok": True}
