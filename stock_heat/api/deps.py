"""API 相依注入。

``get_store`` 提供 ``HeatStore``；目前回傳記憶體示範資料的單例，
測試或 DB 版可用 FastAPI 的 dependency_overrides 替換。
"""

from __future__ import annotations

from functools import lru_cache

from .seed import build_demo_store
from .store import HeatStore


@lru_cache(maxsize=1)
def _store_singleton() -> HeatStore:
    return build_demo_store()


def get_store() -> HeatStore:
    return _store_singleton()
