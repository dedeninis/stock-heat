"""FastAPI 應用進入點（docs/06 §1, §3）。

啟動：``uvicorn stock_heat.api.main:app --reload``
互動式文件：``/docs`` 與 ``/openapi.json``。

MVP 階段以記憶體示範資料供查（見 api/seed.py）；設 ``STOCKHEAT_USE_DB=1`` 改讀資料庫。

跨來源（CORS）：若前端（如 GitHub Pages）與此 API 不同源，以
``STOCKHEAT_CORS_ORIGINS`` 設定允許來源（逗號分隔），預設 ``*``（唯讀 API）。
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .routers import meta, rankings, tickers

logger = logging.getLogger(__name__)
_STATIC_DIR = Path(__file__).parent / "static"


def _cors_origins() -> list[str]:
    raw = os.environ.get("STOCKHEAT_CORS_ORIGINS", "*").strip()
    return ["*"] if raw in ("", "*") else [o.strip() for o in raw.split(",") if o.strip()]


def _maybe_seed() -> None:
    """部署便利：設 STOCKHEAT_SEED_ON_START=1 且資料庫尚無溫度資料時，灌入示範資料。

    用於免費託管（檔案系統重啟即清空）讓 Pages demo 有畫面；不影響本機開發。
    """
    if not os.environ.get("STOCKHEAT_SEED_ON_START"):
        return
    try:
        from ..db import models as m
        from ..db.engine import init_db, session_scope
        init_db()
        with session_scope() as s:
            has_data = s.query(m.TickerHeatTimeseries).first() is not None
        if not has_data:
            from scripts.seed_db import main as seed_main
            logger.info("STOCKHEAT_SEED_ON_START: 灌入示範資料…")
            seed_main()
    except Exception:  # noqa: BLE001 — 種子失敗不應擋住服務啟動
        logger.exception("seed-on-start failed")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _maybe_seed()
    yield


app = FastAPI(
    title="Stock Heat API",
    description="個股網路溫度系統 — 榜單、個股溫度時序與關聯新聞查詢。",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,   # 唯讀公開 API，不帶 cookie
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(rankings.router)
app.include_router(tickers.router)
app.include_router(meta.router)

# 單檔儀表板（docs/07）：與 API 同源，免 CORS。掛在 /app/。
app.mount("/app", StaticFiles(directory=str(_STATIC_DIR), html=True), name="dashboard")


@app.get("/", tags=["meta"])
def root() -> JSONResponse:
    return JSONResponse({
        "name": "stock-heat",
        "version": app.version,
        "docs": "/docs",
        "dashboard": "/app/",
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
