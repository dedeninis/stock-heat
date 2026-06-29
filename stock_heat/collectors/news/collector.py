"""財經新聞擷取器（docs/03 §4）。

職責：從多個新聞來源的 RSS / 列表頁取得最新文章 URL，過濾看過的，
抓取文章頁解析出標題/內文/時間/來源，產出 ``RawDocument(source_type="news")``。

本模組**不做**個股辨識（交由處理層統一處理，docs/03 §4.6）。

設計重點：
- HTTP 抓取與 seen 判定皆可注入，便於離線測試與抽換實作。
- 單篇失敗不影響整輪（繼承自 BaseCollector.run）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Protocol

from ..base import BaseCollector, CollectorRunResult, RawDocument
from .dedup import normalize_url, simhash
from .parser import parse_article, parse_rss
from .sources import NewsSource, load_news_sources

logger = logging.getLogger(__name__)

#: (url) -> html/xml text
Fetcher = Callable[[str], str]
#: (normalized_url) -> 是否已抓過
SeenPredicate = Callable[[str], bool]


class _Marker(Protocol):
    def __call__(self, normalized_url: str) -> None: ...


def _default_fetcher(timeout: float = 10.0,
                     user_agent: str = "StockHeatBot/0.1 (+contact)") -> Fetcher:
    """以 httpx 建立帶重試的 fetcher（延後 import，方便離線測試）。"""
    import httpx
    from tenacity import retry, stop_after_attempt, wait_exponential

    client = httpx.Client(timeout=timeout, headers={"User-Agent": user_agent},
                          follow_redirects=True)

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=0.5, max=8), reraise=True)
    def fetch(url: str) -> str:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text

    return fetch


class NewsCollector(BaseCollector):
    source_type = "news"

    def __init__(
        self,
        source: NewsSource,
        *,
        fetcher: Fetcher | None = None,
        seen: SeenPredicate | None = None,
        mark_seen: _Marker | None = None,
    ) -> None:
        self.config = source
        self.source = source.id
        self.default_interval = source.interval
        self._fetch_text = fetcher or _default_fetcher()
        self._seen = seen or (lambda _u: False)
        self._mark_seen = mark_seen or (lambda _u: None)
        # discover 期間自 RSS 取得的發布時間，供 fetch 補上（文章頁常缺日期）
        self._pub_dates: dict[str, object] = {}

    # ------------------------------------------------------------------ discover
    def discover(self) -> list[str]:
        feed_url = self.config.rss or self.config.list_url
        assert feed_url  # NewsSource 已保證至少一個
        try:
            raw = self._fetch_text(feed_url)
        except Exception:  # noqa: BLE001
            logger.warning("[%s] 無法取得列表/RSS：%s", self.source, feed_url, exc_info=True)
            return []

        if self.config.rss:
            entries = parse_rss(raw)
            for e in entries:
                if e.published_at is not None:
                    self._pub_dates[normalize_url(e.url)] = e.published_at
            links: Iterable[str] = (e.url for e in entries)
        else:
            # 列表頁：交由 parser 的通用連結抽取（此處先取 RSS 路徑為主）
            from selectolax.parser import HTMLParser
            tree = HTMLParser(raw)
            links = [a.attributes.get("href", "") for a in tree.css("a")
                     if a.attributes.get("href")]

        urls: list[str] = []
        seen_in_run: set[str] = set()
        for link in links:
            if not link:
                continue
            norm = normalize_url(link)
            if norm in seen_in_run or self._seen(norm):
                continue
            seen_in_run.add(norm)
            urls.append(link)
            if len(urls) >= self.config.max_per_run:
                break
        return urls

    # --------------------------------------------------------------------- fetch
    def fetch(self, url: str) -> RawDocument:
        html = self._fetch_text(url)
        article = parse_article(
            html, selector=self.config.article_selector, fallback_title=""
        )
        norm = normalize_url(url)
        self._mark_seen(norm)
        # 文章頁常缺發布時間，退回 discover 階段自 RSS 取得的日期
        published_at = article.published_at or self._pub_dates.get(norm)
        return RawDocument(
            source=self.source,
            source_type=self.source_type,
            external_id=norm,
            url=url,
            title=article.title,
            content=article.content,
            author=article.author,
            published_at=published_at,
            content_quality=article.quality,
            raw_meta={
                "weight": self.config.weight,
                "simhash": simhash(article.title + "\n" + article.content),
            },
        )


def collect_all_news(
    config_path: str = "config/sources.yaml",
    *,
    fetcher: Fetcher | None = None,
    seen: SeenPredicate | None = None,
    mark_seen: _Marker | None = None,
) -> list[CollectorRunResult]:
    """對設定檔內所有啟用的新聞來源各跑一輪，回傳結果清單。"""
    results: list[CollectorRunResult] = []
    for src in load_news_sources(config_path):
        collector = NewsCollector(src, fetcher=fetcher, seen=seen, mark_seen=mark_seen)
        results.append(collector.run())
    return results
