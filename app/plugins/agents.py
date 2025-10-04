from __future__ import annotations
import asyncio
from app.core.interfaces import Agent, ToolLocator
from app.core.schemas import FetchOut, AnalyzeIn, AnalyzeOut, ChartIn, ChartOut

class FetchAgent(Agent):
    name = "agent.fetch"
    input_schema = {}
    output_schema = FetchOut.model_json_schema()["properties"]
    required_tools = {"http_fetcher"}

    async def run(self, context: dict, tools: ToolLocator, params: dict) -> dict:
        fetcher = tools.get("http_fetcher")
        res = await fetcher.invoke(url=params["url"])
        return FetchOut(body=res["body"], status=res["status"]).model_dump()
    
class AnalyzeAgent(Agent):
    name = "agent.analyze"
    input_schema = AnalyzeIn.model_json_schema()["properties"]
    output_schema = AnalyzeOut.model_json_schema()["properties"]
    required_tools = set()

    async def run(self, context: dict, tools: ToolLocator, params: dict) -> dict:
        text = AnalyzeIn(**{"text": context.get("text", "")}).text
        await asyncio.sleep(0.02)
        return AnalyzeOut(insights=[len(text), text.count("AI"), 42]).model_dump()
    
class ChartAgent(Agent):
    name = "agent.chart"
    input_schema = ChartIn.model_json_schema()["properties"]
    output_schema = ChartOut.model_json_schema()["properties"]
    required_tools = {"chart_generator"}

    async def run(self, context: dict, tools: ToolLocator, params: dict) -> dict:
        chart = tools.get("chart_generator")
        inp = ChartIn(series=context.get("series", []))
        res = await chart.invoke(series=inp.series, spec=params.get("spec", {}))
        return ChartOut(chart_url=res["chart_url"], points=res["points"]).model_dump()