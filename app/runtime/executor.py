from __future__ import annotations
from typing import List, Dict, Optional, Callable, Awaitable
from pydantic import BaseModel, Field
import asyncio, time

from app.core.registry import ToolRegistry, AgentRegistry
from app.core.interfaces import _validate_keys as _check_keys
from app.core.config import get_config
from app.core.logging_utils import get_logger, log_agent_execution, log_performance

EventSink = Callable[[dict], Awaitable[None]]

def _validate_graph(graph: GraphSpec) -> None:
    node_ids = {n.id for n in graph.nodes}
    if len(node_ids) != len(graph.nodes):
        raise ValueError("Duplicate node.id detected")
    
    for e in graph.edges:
        if e.from_ not in node_ids:
            raise ValueError(f"Edge.from references unknown node: {e.from_}")
        if e.to not in node_ids:
            raise ValueError(f"Edge.to references unknown node: {e.to}")

    indeg = {n.id: 0 for n in graph.nodes}
    children = {n.id: [] for n in graph.nodes}
    for e in graph.edges:
        indeg[e.to] += 1
        children[e.from_].append(e.to)

    q = [nid for nid, d in indeg.items() if d == 0]
    visited = 0
    while q:
        nid = q.pop()
        visited += 1
        for c in children[nid]:
            indeg[c] -= 1
            if indeg[c] == 0:
                q.append(c)
    
    if visited != len(graph.nodes):
        raise ValueError("Cycle detected in graph (DAG only)")
    
def _eval_cond(cond: dict, ctx: dict) -> bool:
    if not cond:
        return True
    var = cond.get("var")
    op = cond.get("op")
    val = cond.get("value")
    left = ctx.get(var)

    try:
        if op == "==":  return left == val
        if op == "!=":  return left != val
        if op == ">":   return left > val
        if op == ">=":  return left >= val
        if op == "<":   return left < val
        if op == "<=":  return left <= val
        if op == "contains":    return (isinstance(left, (str, list)) and (val in left))
        return False
    except Exception:
        return False

class NodeSpec(BaseModel):
    id: str
    type: str
    params: dict = Field(default_factory=dict)
    timeout_sec: Optional[int] = None
    retries: Optional[int] = None
    optional: bool = False

class EdgeSpec(BaseModel):
    from_: str = Field(alias="from")
    to: str
    map: dict = Field(default_factory=dict)
    cond: dict | None = None

class GraphSpec(BaseModel):
    name: str
    nodes: List[NodeSpec]
    edges: List[EdgeSpec]
    options: dict = Field(default_factory=dict)
    sinks: list[str] = Field(default_factory=list)

class _ToolLocator:
    def __init__(self, tool_registry: ToolRegistry):
        self._reg = tool_registry
    
    def has(self, name: str) -> bool:
        return self._reg.has(name)
    
    def get(self, name: str):
        return self._reg.get(name)
    
class Executor:
    def __init__(self, tools: ToolRegistry, agents: AgentRegistry) -> None:
        self.tools = tools
        self.agents = agents
        self.config = get_config()
        self.logger = get_logger("wand.executor")
        self._bootstrap_plugins()

    def _bootstrap_plugins(self):
        from app.plugins.tools import HttpFetcher, ChartGenerator
        from app.plugins.agents import FetchAgent, AnalyzeAgent, ChartAgent
        
        for t in (HttpFetcher(), ChartGenerator()):
            if not self.tools.has(t.name):
                self.tools.register(t)
                self.logger.debug(f"Registered tool: {t.name}")
        
        for a in (FetchAgent(), AnalyzeAgent(), ChartAgent()):
            if not self.agents.has(a.name):
                self.agents.register(a)
                self.logger.debug(f"Registered agent: {a.name}")
        
        self.logger.info(f"Bootstrap complete - Tools: {len(self.tools._map)}, Agents: {len(self.agents._map)}")

    async def execute(
        self, 
        graph: GraphSpec, 
        events: list,
        *,
        cancel_event: asyncio.Event | None = None,
        on_event: EventSink | None = None
    ) -> dict:
        
        _validate_graph(graph)
        
        def _append(evt: dict):
            events.append(evt)

        async def _emit(evt: dict):
            _append(evt)
            if on_event:
                await on_event(evt)

        # Use configuration defaults, allow graph options to override
        timeout = int(graph.options.get("default_timeout_sec", self.config.execution.default_timeout_sec))
        retries = int(graph.options.get("max_retries", self.config.execution.max_retries))
        concurrency = min(
            int(graph.options.get("concurrency", self.config.execution.default_concurrency)),
            self.config.execution.max_concurrency
        )

        nodes = {n.id: n for n in graph.nodes}
        indeg = {n.id: 0 for n in graph.nodes}
        children: Dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for e in graph.edges:
            indeg[e.to] += 1
            children[e.from_].append(e.to)

        ready = [nid for nid, d in indeg.items() if d == 0]
        outputs: Dict[str, dict] = {}
        total_nodes = len(nodes)
        finished_nodes = 0

        locator = _ToolLocator(self.tools)
        sem = asyncio.Semaphore(concurrency)

        async def run_node(nid: str):
            nonlocal finished_nodes
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError("Run cancelled before node start")
            
            node = nodes[nid]
            agent = self.agents.get(node.type)
            start_time = time.time()

            for t in getattr(agent, "required_tools", set()):
                if not self.tools.has(t):
                    raise RuntimeError(f"node {nid} missing required tool: {t}")
                
            ctx = {}
            for e in graph.edges:
                if e.to == nid and e.from_ in outputs:
                    src = outputs[e.from_]
                    for dst_key, src_key in e.map.items():
                        ctx[dst_key] = src.get(src_key)
            
            _check_keys(ctx, getattr(agent, "input_schema", {}), where="input", agent_name=agent.name)

            attempt = 0
            while True:
                attempt += 1
                await _emit({"ts": time.time(), "lvl": "info", "msg": f"node.start {nid} attempt={attempt}"})
                log_agent_execution(
                    run_id=getattr(_emit, '_run_id', 'unknown'),
                    node_id=nid,
                    agent_type=agent.name,
                    status="starting",
                    attempt=attempt
                )

                try:
                    async with sem:
                        coro = agent.run(ctx, locator, node.params)
                        out = await asyncio.wait_for(coro, timeout=timeout)
                        _check_keys(out, getattr(agent, "output_schema", {}), where="output", agent_name=agent.name)
                    
                    outputs[nid] = out
                    finished_nodes += 1
                    progress = round(100 * finished_nodes / max(1, total_nodes))
                    duration_ms = (time.time() - start_time) * 1000
                    
                    await _emit({"ts": time.time(), "lvl": "info", "msg": f"node.done {nid}", "progress": progress})
                    log_agent_execution(
                        run_id=getattr(_emit, '_run_id', 'unknown'),
                        node_id=nid,
                        agent_type=agent.name,
                        status="completed",
                        duration_ms=duration_ms
                    )
                    break
                    
                except Exception as e:
                    if attempt <= retries:
                        backoff = min(
                            self.config.execution.retry_backoff_factor * (self.config.execution.retry_backoff_factor ** (attempt - 1)),
                            self.config.execution.retry_max_delay
                        )
                        await _emit({"ts": time.time(), "lvl": "warn", "msg": f"node.retry {nid}: {e}"})
                        log_agent_execution(
                            run_id=getattr(_emit, '_run_id', 'unknown'),
                            node_id=nid,
                            agent_type=agent.name,
                            status="retrying",
                            attempt=attempt,
                            error=str(e)
                        )
                        await asyncio.sleep(backoff)
                    else:
                        duration_ms = (time.time() - start_time) * 1000
                        if node.optional:
                            finished_nodes += 1
                            progress = round(100 * finished_nodes / max(1, total_nodes))
                            await _emit({"ts": time.time(), "lvl": "error", "msg": f"node.fail(optional) {nid}: {e}", "progress": progress})
                            log_agent_execution(
                                run_id=getattr(_emit, '_run_id', 'unknown'),
                                node_id=nid,
                                agent_type=agent.name,
                                status="failed_optional",
                                duration_ms=duration_ms,
                                error=str(e)
                            )
                        else:
                            await _emit({"ts": time.time(), "lvl": "error", "msg": f"node.fail {nid}: {e}"})
                            log_agent_execution(
                                run_id=getattr(_emit, '_run_id', 'unknown'),
                                node_id=nid,
                                agent_type=agent.name,
                                status="failed",
                                duration_ms=duration_ms,
                                error=str(e)
                            )
                            raise


            for c in children[nid]:
                edge_enabled = False
                for e in graph.edges:
                    if e.from_ == nid and e.to == c:
                        src = outputs.get(nid, {})
                        test_ctx = {dst_key: src.get(src_key) for dst_key, src_key in e.map.items()}
                        if _eval_cond(e.cond or {}, test_ctx):
                            edge_enabled = True
                            break

                if not edge_enabled:
                    continue

                indeg[c] -= 1
                if indeg[c] == 0:
                    ready.append(c)
        
        running: set[str] = set()
        tasks: Dict[str, asyncio.Task] = {}

        while ready or tasks:
            while ready:
                nid = ready.pop()
                if nid in running:
                    continue
                tasks[nid] = asyncio.create_task(run_node(nid))
                running.add(nid)

            if tasks:
                done, _ = await asyncio.wait(tasks.values(), return_when=asyncio.FIRST_COMPLETED)
                for d in done:
                    d.result()

                tasks = {k: v for k, v in tasks.items() if not v.done()}

        if graph.sinks:
            selected = {nid: outputs.get(nid) for nid in graph.sinks if nid in outputs}
            return {"outputs": selected, "sinks": graph.sinks}
        else:
            return {"outputs":outputs}