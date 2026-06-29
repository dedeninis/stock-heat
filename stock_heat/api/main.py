"""FastAPI 應用進入點（docs/06 §1, §3）。

啟動：``uvicorn stock_heat.api.main:app --reload``
互動式文件：``/docs`` 與 ``/openapi.json``。

MVP 階段以記憶體示範資料供查（見 api/seed.py）；之後換 DB 版只需替換 store。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .routers import meta, rankings, tickers

app = FastAPI(
    title="Stock Heat API",
    description="個股網路溫度系統 — 榜單、個股溫度時序與關聯新聞查詢。",
    version="0.1.0",
)

app.include_router(rankings.router)
app.include_router(tickers.router)
app.include_router(meta.router)


@app.get("/", tags=["meta"])
def root() -> JSONResponse:
    return JSONResponse({
        "name": "stock-heat",
        "version": app.version,
        "docs": "/docs",
        "endpoints": [
            "/api/v1/rankings/heat",
            "/api/v1/rankings/surging",
            "/api/v1/tickers/{ticker}",
            "/api/v1/tickers/{ticker}/timeseries",
            "/api/v1/tickers/{ticker}/documents",
            "/api/v1/search?q=",
            "/api/v1/health",
        ],
    })
