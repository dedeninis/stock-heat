"""榜單路由（docs/06 §3.1）。"""

from __future__ import annotations

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query

from ..deps import get_store
from ..schemas import (
    RankingItem,
    RankingResponse,
    SurgeItem,
    SurgeResponse,
)
from ..store import HeatStore

router = APIRouter(prefix="/api/v1/rankings", tags=["rankings"])


def _passes_sentiment(value: float, sentiment: str) -> bool:
    if sentiment == "positive":
        return value > 0
    if sentiment == "negative":
        return value < 0
    return True


@router.get("/heat", response_model=RankingResponse)
def heat_ranking(
    store: HeatStore = Depends(get_store),
    day: date | None = Query(None, alias="date", description="查詢日期，預設最新"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    sentiment: str = Query("all", pattern="^(all|positive|negative)$"),
) -> RankingResponse:
    target = day or store.latest_date()
    if target is None:
        # 尚無資料（如部署後首輪掃描尚未完成）：回空清單而非 404，前端顯示「無資料」
        return RankingResponse(date=day or date.today(), order=order, items=[])

    rows = []
    for rec in store.all_records():
        p = rec.point_on(target)
        if p is None or not _passes_sentiment(p.sentiment, sentiment):
            continue
        rows.append((rec, p))

    rows.sort(key=lambda rp: rp[1].heat_score, reverse=(order == "desc"))
    items = [
        RankingItem(
            rank=i + 1, ticker=rec.ticker, name=rec.name,
            heat_score=p.heat_score, sentiment=p.sentiment,
            heat_velocity=p.heat_velocity, volume=p.volume,
        )
        for i, (rec, p) in enumerate(rows[:limit])
    ]
    return RankingResponse(date=target, order=order, items=items)


@router.get("/surging", response_model=SurgeResponse)
def surging_ranking(
    store: HeatStore = Depends(get_store),
    day: date | None = Query(None, alias="date"),
) -> SurgeResponse:
    target = day or store.latest_date()
    if target is None:
        return SurgeResponse(date=day or date.today(), items=[])

    items = []
    for rec in store.all_records():
        p = rec.point_on(target)
        if p is None or not rec.is_surge:
            continue
        items.append(SurgeItem(
            ticker=rec.ticker, name=rec.name, heat_score=p.heat_score,
            heat_velocity=p.heat_velocity,
            detected_at=datetime.combine(target, time(0, 0)),
            top_terms=[d.title for d in rec.documents[:2]],
        ))
    items.sort(key=lambda s: s.heat_velocity, reverse=True)
    return SurgeResponse(date=target, items=items)
