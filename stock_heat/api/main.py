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
    """部署便利：設 STOCKHEAT_SEED_ON_START=1 且資料庫尚無溫度資料時，灌入輕量示範資料。

    用輕量直寫（不跑辨識管線）→ 毫秒級、不佔 CPU，故不會因 GIL 阻塞事件迴圈而拖垮
    healthcheck。用於免費託管（重啟即清空）讓 demo 有畫面；不影響本機開發。
    真實資料請用 `python -m scripts.collect_once`。
    """
    if not os.environ.get("STOCKHEAT_SEED_ON_START"):
        return
    try:
        from ..db import models as m
        from ..db.demo_seed import seed_demo_db
        from ..db.engine import init_db, session_scope
        init_db()
        with session_scope() as s:
            has_data = s.query(m.TickerHeatTimeseries).first() is not None
        if not has_data:
            logger.info("STOCKHEAT_SEED_ON_START: 灌入輕量示範資料…")
            seed_demo_db()
    except Exception:  # noqa: BLE001 — 種子失敗不應擋住服務啟動
        logger.exception("seed-on-start failed")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    from ..autoscan import enabled as autoscan_enabled
    from ..autoscan import start_autoscan

    if autoscan_enabled():
        # 自動掃描真實新聞：子行程週期擷取，啟動即先掃一次（不阻塞、不佔 GIL）。
        logger.info("啟用自動掃描真實新聞（STOCKHEAT_AUTO_SCAN）")
        start_autoscan()
    else:
        # 否則灌輕量合成示範資料，毫秒級、不影響 healthcheck。
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
