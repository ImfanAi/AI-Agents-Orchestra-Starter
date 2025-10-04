from __future__ import annotations
import asyncio
import httpx
from app.core.interfaces import Tool

class HttpFetcher(Tool):
    name = "http_fetcher"
    async def invoke(self, url: str, method: str = "GET", **kwargs):
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.request(method, url, **kwargs)
            return {"status": r.status_code, "body": r.text}

class ChartGenerator(Tool):
    name = "chart_generator"
    async def invoke(self, series: list[float], spec: dict | None = None):
        await asyncio.sleep(0.05)
        return {"chart_url": "s3://mock/chart.png", "points": len(series)}
