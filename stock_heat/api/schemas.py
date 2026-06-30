"""API 回應模型（docs/06 §3）。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class RankingItem(BaseModel):
    rank: int
    ticker: str
    name: str
    heat_score: float
    sentiment: float
    heat_velocity: float
    volume: int


class RankingResponse(BaseModel):
    date: date
    order: str
    items: list[RankingItem]


class SurgeItem(BaseModel):
    ticker: str
    name: str
    heat_score: float
    heat_velocity: float
    detected_at: datetime
    top_terms: list[str] = []


class SurgeResponse(BaseModel):
    date: date
    items: list[SurgeItem]


class TrendPoint(BaseModel):
    ts: date
    heat_score: float


class SourceShare(BaseModel):
    type: str       # news | forum | social | trends | disclosure
    label: str      # 顯示名稱（新聞 / 論壇 / 社群…）
    pct: float      # 佔當前溫度的百分比


class TickerSummary(BaseModel):
    ticker: str
    name: str
    industry: str
    as_of: date
    heat_score: float
    sentiment: float
    heat_velocity: float
    volume: int
    is_surge: bool
    trend_7d: list[TrendPoint]
    source_breakdown: list[SourceShare] = []  # 溫度組成（依來源類型）


class TimeseriesPoint(BaseModel):
    ts: date
    heat_score: float
    sentiment: float
    volume: int
    heat_velocity: float


class TimeseriesResponse(BaseModel):
    ticker: str
    granularity: str
    points: list[TimeseriesPoint]


class DocumentItem(BaseModel):
    title: str
    source: str
    source_name: str
    url: str
    published_at: datetime
    ticker_sentiment: float
    confidence: float


class DocumentsResponse(BaseModel):
    ticker: str
    items: list[DocumentItem]


class SearchItem(BaseModel):
    ticker: str
    name: str
    industry: str


class SearchResponse(BaseModel):
    query: str
    items: list[SearchItem]


class ComponentHealth(BaseModel):
    name: str
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    components: list[ComponentHealth]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
