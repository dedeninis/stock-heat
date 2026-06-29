"""API 相依注入。

``get_store`` 提供 ``HeatStore``：
- 若設定環境變數 ``STOCKHEAT_DATABASE_URL``（或 ``STOCKHEAT_USE_DB=1``）→ 用 DB-backed store。
- 否則回傳記憶體示範資料（MVP 預設）。
測試或其他實作可用 FastAPI 的 dependency_overrides 替換。
"""

from __future__ import annotations

import os
from functools import lru_cache

from .seed import build_demo_store
from .store import HeatStore


def _use_db() -> bool:
    return bool(os.environ.get("STOCKHEAT_DATABASE_URL") or
                os.environ.get("STOCKHEAT_USE_DB"))


@lru_cache(maxsize=1)
def _store_singleton() -> HeatStore:
    if _use_db():
        from ..db.repository import SqlHeatStore
        return SqlHeatStore()
    return build_demo_store()


def get_store() -> HeatStore:
    return _store_singleton()
