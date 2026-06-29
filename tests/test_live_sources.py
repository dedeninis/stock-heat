"""真實來源整合測試（需網路，預設略過）。

CI 與一般 `pytest` 不會跑此測試（保持離線可重現）。
手動驗證真實來源接線：

    STOCKHEAT_LIVE_TEST=1 pytest tests/test_live_sources.py -v
"""

from __future__ import annotations

import os

import pytest

from stock_heat.collectors.news import NewsCollector
from stock_heat.collectors.news.sources import load_news_sources

LIVE = os.environ.get("STOCKHEAT_LIVE_TEST")
pytestmark = pytest.mark.skipif(
    not LIVE, reason="設定 STOCKHEAT_LIVE_TEST=1 以執行真實來源測試")


def _enabled_sources():
    return [s for s in load_news_sources("config/sources.yaml") if s.enabled]


def test_configured_feeds_reachable_and_parse():
    sources = _enabled_sources()
    assert sources, "config/sources.yaml 至少要有一個啟用的新聞來源"
    for src in sources:
        src.max_per_run = 2  # 禮貌性低量
        collector = NewsCollector(src)  # 真實 httpx fetcher
        urls = collector.discover()
        assert urls, f"[{src.id}] RSS/列表無法取得任何文章連結"


def test_collector_produces_real_documents():
    src = _enabled_sources()[0]
    src.max_per_run = 2
    result = NewsCollector(src).run()
    assert result.fetched >= 1
    for doc in result.documents:
        assert doc.title.strip()
        assert doc.content.strip()
        assert doc.published_at is not None  # RSS 或 meta 應提供發布時間
