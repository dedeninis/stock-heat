"""個股路由（docs/06 §3.2）。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_store
from ..schemas import (
    DocumentItem,
    DocumentsResponse,
    TickerSummary,
    TimeseriesPoint,
    TimeseriesResponse,
    TrendPoint,
)
from ..store import HeatStore, TickerRecord

router = APIRouter(prefix="/api/v1/tickers", tags=["tickers"])


def _require(store: HeatStore, ticker: str) -> TickerRecord:
    rec = store.get(ticker)
    if rec is None:
        raise HTTPException(404, detail=f"找不到個股 {ticker}")
    return rec


@router.get("/{ticker}", response_model=TickerSummary)
def ticker_summary(ticker: str, store: HeatStore = Depends(get_store)) -> TickerSummary:
    rec = _require(store, ticker)
    latest = rec.latest
    if latest is None:
        raise HTTPException(404, detail=f"{ticker} 無溫度資料")
    trend = [TrendPoint(ts=p.ts, heat_score=p.heat_score) for p in rec.points[-7:]]
    return TickerSummary(
        ticker=rec.ticker, name=rec.name, industry=rec.industry,
        as_of=latest.ts, heat_score=latest.heat_score, sentiment=latest.sentiment,
        heat_velocity=latest.heat_velocity, volume=latest.volume,
        is_surge=rec.is_surge, trend_7d=trend,
    )


@router.get("/{ticker}/timeseries", response_model=TimeseriesResponse)
def ticker_timeseries(
    ticker: str,
    store: HeatStore = Depends(get_store),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    granularity: str = Query("daily", pattern="^(daily|intraday)$"),
) -> TimeseriesResponse:
    rec = _require(store, ticker)
    points = [
        TimeseriesPoint(ts=p.ts, heat_score=p.heat_score, sentiment=p.sentiment,
                        volume=p.volume, heat_velocity=p.heat_velocity)
        for p in rec.points
        if (date_from is None or p.ts >= date_from)
        and (date_to is None or p.ts <= date_to)
    ]
    return TimeseriesResponse(ticker=ticker, granularity=granularity, points=points)


@router.get("/{ticker}/documents", response_model=DocumentsResponse)
def ticker_documents(
    ticker: str,
    store: HeatStore = Depends(get_store),
    limit: int = Query(20, ge=1, le=100),
) -> DocumentsResponse:
    rec = _require(store, ticker)
    items = [
        DocumentItem(
            title=d.title, source=d.source, source_name=d.source_name, url=d.url,
            published_at=d.published_at, ticker_sentiment=d.ticker_sentiment,
            confidence=d.confidence,
        )
        for d in rec.documents[:limit]
    ]
    return DocumentsResponse(ticker=ticker, items=items)
