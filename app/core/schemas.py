from pydantic import BaseModel, Field
from typing import List, Dict, Any

class FetchOut(BaseModel):
    body: str
    status: int

class AnalyzeIn(BaseModel):
    text: str

class AnalyzeOut(BaseModel):
    insights: List[int]

class ChartIn(BaseModel):
    series: List[int] = Field(default_factory=list)

class ChartOut(BaseModel):
    chart_url: str
    points: int