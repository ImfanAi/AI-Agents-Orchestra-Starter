import anyio
from app.runtime.executor import Executor, GraphSpec, NodeSpec, EdgeSpec
from app.core.registry import ToolRegistry, AgentRegistry

def make_executor():
    return Executor(ToolRegistry(), AgentRegistry())

async def run_demo():
    ex = make_executor()
    g = GraphSpec(
        name="t",
        nodes=[
            NodeSpec(id="fetch", type="agent.fetch", params={"url": "https://example.com"}),
            NodeSpec(id="analyze", type="agent.analyze", params={})
        ],
        edges=[
            EdgeSpec(**{"from":"fetch", "to":"analyze", "map":{"text":"body"}})
        ],
        options={"concurrency":2, "default_timeout_sec":5, "max_retries":0},
        sinks=["analyze"]
    )
    events = []
    res = await ex.execute(g, events)
    assert "outputs" in res and "analyze" in res["outputs"]
    assert any("node.done fetch" in (ev.get("msg") or "") for ev in events)

def test_pipeline():
    anyio.run(run_demo)