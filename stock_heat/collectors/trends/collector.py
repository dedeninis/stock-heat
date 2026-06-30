"""Google Trends 搜尋熱度（docs/03 §1，source_type=trends）。

與新聞/社群不同：Trends 不是「文件」，而是**每檔一個搜尋興趣指數（0–100）**。
因此不走 RawDocument→mention，而是直接產生「趨勢訊號」併入溫度計算（不計情緒）。

限制：Google Trends 限流兇、每次至多 ~5 詞、無法查全市場 → 僅查**當日熱門前 N 檔**加值。
pytrends 為選配相依（不入核心/Docker），缺少時優雅降級。
``InterestFetcher`` 可注入，便於離線測試。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

#: terms -> {term: 0-100}
InterestFetcher = Callable[[list[str]], dict[str, int]]

_BATCH = 5  # Google Trends 每次查詢上限


def pytrends_fetcher(
    *, hl: str = "zh-TW", geo: str = "TW", timeframe: str = "now 7-d",
    pause: float = 1.0,
) -> InterestFetcher:
    """以 pytrends 建立 interest fetcher（延後 import；未安裝時拋出清楚訊息）。"""
    try:
        from pytrends.request import TrendReq
    except ImportError as e:  # pragma: no cover - 視環境
        raise RuntimeError("需要選配相依 pytrends：pip install pytrends") from e

    def fetch(terms: list[str]) -> dict[str, int]:
        if not terms:
            return {}
        pt = TrendReq(hl=hl, tz=-480)
        pt.build_payload(terms, timeframe=timeframe, geo=geo)
        df = pt.interest_over_time()
        time.sleep(pause)  # 禮貌性間隔，降低 429
        if df is None or df.empty:
            return {t: 0 for t in terms}
        return {t: int(df[t].iloc[-1]) for t in terms if t in df.columns}

    return fetch


def fetch_ticker_interest(
    tickers: list[tuple[str, str]],
    *,
    fetcher: InterestFetcher | None = None,
) -> dict[str, int]:
    """查詢一組 (ticker, name) 的搜尋興趣，回傳 {ticker: 0-100}。

    以公司名查詢（比代號更貼近搜尋行為）。單批失敗只略過該批，不中斷整體。
    """
    fetcher = fetcher or pytrends_fetcher()
    result: dict[str, int] = {}
    for i in range(0, len(tickers), _BATCH):
        chunk = tickers[i:i + _BATCH]
        name_to_ticker = {name: tk for tk, name in chunk}
        try:
            interest = fetcher(list(name_to_ticker))
        except Exception:  # noqa: BLE001 — 單批失敗不影響其他批
            logger.warning("trends: 批次查詢失敗 %s", list(name_to_ticker), exc_info=True)
            continue
        for name, value in interest.items():
            if name in name_to_ticker:
                result[name_to_ticker[name]] = int(value)
    return result
