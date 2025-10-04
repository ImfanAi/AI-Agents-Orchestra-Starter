from __future__ import annotations
from typing import Protocol, Any, Mapping

class Tool(Protocol):
    name: str
    async def invoke(self, **kwargs: Any) -> Any: ...

class ToolLocator(Protocol):
    def has(self, name: str) -> bool: ...
    def get(self, name: str) -> Tool: ...
    
class Agent(Protocol):
    name: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    required_tools: set[str]
    async def run(self, context: dict, tools: ToolLocator, params: dict) -> dict: ...

def _validate_keys(
        data: Mapping[str, Any], 
        schema: Mapping[str, Any], 
        *,
        where: str,
        agent_name: str
    ) -> None:
    missing = [k for k in schema.keys() if k not in data]
    if missing:
        raise ValueError(f"[{agent_name}] {where} missing keys: {missing}")