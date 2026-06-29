"""搜尋與健康路由（docs/06 §3.3）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import get_store
from ..schemas import (
    ComponentHealth,
    HealthResponse,
    SearchItem,
    SearchResponse,
)
from ..store import HeatStore
from ...processing.dictionary import get_dictionary

router = APIRouter(prefix="/api/v1", tags=["meta"])


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, description="名稱 / 別名 / 代號"),
    store: HeatStore = Depends(get_store),
) -> SearchResponse:
    dictionary = get_dictionary("data/tickers.csv")
    needle = q.strip()
    items: list[SearchItem] = []
    for entry in dictionary.all():
        haystack = [entry.ticker, entry.name, *entry.aliases]
        if any(needle in h or h in needle for h in haystack):
            items.append(SearchItem(ticker=entry.ticker, name=entry.name,
                                    industry=entry.industry))
    return SearchResponse(query=q, items=items)


@router.get("/health", response_model=HealthResponse)
def health(store: HeatStore = Depends(get_store)) -> HealthResponse:
    components = [
        ComponentHealth(name=name, status=status, detail=detail)
        for name, status, detail in store.health_components()
    ]
    overall = "ok" if all(c.status == "ok" for c in components) else "degraded"
    return HealthResponse(status=overall, components=components)
