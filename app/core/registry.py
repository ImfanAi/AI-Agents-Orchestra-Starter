from __future__ import annotations
from typing import Dict
from app.core.interfaces import Tool, Agent

class ToolRegistry:
    def __init__(self) -> None:
        self._map: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._map:
            raise KeyError(f"Tool already exists: {tool.name}")
        self._map[tool.name] = tool

    def has(self, name: str) -> bool:
        return name in self._map
    
    def get(self, name: str) -> Tool:
        if name not in self._map:
            raise KeyError(f"Tool not found: {name}")
        return self._map[name]
    
class AgentRegistry:
    def __init__(self) -> None:
        self._map: Dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if agent.name in self._map:
            raise KeyError(f"Agent already exist: {agent.name}")
        self._map[agent.name] = agent

    def has(self, name: str) -> bool:
        return name in self._map
    
    def get(self, name: str) -> Agent:
        if name not in self._map:
            raise KeyError(f"Agent not found: {name}")
        return self._map[name]