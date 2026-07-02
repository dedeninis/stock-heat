"""即時行情：代理證交所 MIS 報價（docs/07 §9 溫度×股價）。

瀏覽器不能直接打 MIS（無 CORS），故由後端代理：依個股市場路由 tse_/otc_、
帶 index.jsp cookie、短快取（降低對 MIS 的請求）。抓不到時回 available=False，
前端顯示「行情暫無」但仍提供技術線圖連結——不因行情失敗影響溫度儀表板。

⚠️ MIS 對資料中心 IP 可能限流；失敗即優雅降級。fetcher 可注入，便於離線測試。
"""

from __future__ import annotations

import time
from collections.abc import Callable

# channel（如 "tse_2330.tw"）-> MIS msgArray 首筆 dict（找不到回 {}）
QuoteFetcher = Callable[[str], dict]

_MIS = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 30.0  # 秒

_override_fetcher: QuoteFetcher | None = None
_default_singleton: QuoteFetcher | None = None


def _channel(ticker: str, market: str) -> str:
    prefix = "otc" if market.upper() in ("TPEX", "OTC") else "tse"
    return f"{prefix}_{ticker}.tw"


def _num(value: object) -> float | None:
    try:
        f = float(str(value))
        return f if f == f else None  # 過濾 NaN
    except (TypeError, ValueError):
        return None


def _build_default_fetcher() -> QuoteFetcher:
    import httpx
    client = httpx.Client(
        timeout=8.0,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://mis.twse.com.tw/stock/index.jsp"},
    )
    try:
        client.get("https://mis.twse.com.tw/stock/index.jsp")  # 取 cookie
    except Exception:  # noqa: BLE001
        pass

    def fetch(channel: str) -> dict:
        r = client.get(f"{_MIS}?ex_ch={channel}&json=1&delay=0")
        r.raise_for_status()
        arr = (r.json() or {}).get("msgArray") or []
        return arr[0] if arr and arr[0].get("c") else {}

    return fetch


def set_override_fetcher(fetcher: QuoteFetcher | None) -> None:
    """測試用：注入假 fetcher。"""
    global _override_fetcher
    _override_fetcher = fetcher


def clear_cache() -> None:
    _CACHE.clear()


def _active_fetcher() -> QuoteFetcher:
    global _default_singleton
    if _override_fetcher is not None:
        return _override_fetcher
    if _default_singleton is None:
        _default_singleton = _build_default_fetcher()
    return _default_singleton


def _parse(raw: dict) -> dict:
    """把 MIS 欄位轉成報價結果。z=成交 y=昨收 o/h/l=開高低 v=量 t=時間。"""
    prev = _num(raw.get("y"))
    price = _num(raw.get("z"))
    if price is None:  # 盤前/無成交 → 退回昨收
        price = prev
    change = (price - prev) if (price is not None and prev is not None) else None
    change_pct = (change / prev * 100) if (change is not None and prev) else None
    return {
        "available": price is not None,
        "price": price,
        "prev_close": prev,
        "change": round(change, 2) if change is not None else None,
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "open": _num(raw.get("o")),
        "high": _num(raw.get("h")),
        "low": _num(raw.get("l")),
        "volume": int(_num(raw.get("v")) or 0),
        "time": raw.get("t") or None,
    }


_EMPTY = {"available": False, "price": None, "prev_close": None, "change": None,
          "change_pct": None, "open": None, "high": None, "low": None,
          "volume": None, "time": None}


def get_quote(ticker: str, market: str, *, fetcher: QuoteFetcher | None = None) -> dict:
    """取得個股即時/收盤報價（含短快取）。失敗回 available=False。"""
    cached = _CACHE.get(ticker)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    fetch = fetcher or _active_fetcher()
    try:
        raw = fetch(_channel(ticker, market))
        result = _parse(raw) if raw else dict(_EMPTY)
    except Exception:  # noqa: BLE001 — MIS 失敗即降級
        result = dict(_EMPTY)

    _CACHE[ticker] = (time.time(), result)
    return result
