"""PTT Stock 板擷取器（社群討論熱度，docs/03 §1）。

從 PTT 看板列表取得文章，解析主文與**互動量（推/噓/回應數）**，產出
``RawDocument(source_type="social")``，其 ``raw_meta`` 帶：
- ``engagement``：推＋噓＋→ 留言總數（社群熱度的關鍵訊號，計入溫度公式）。
- ``implicit_stock_context``：True → 處理層放寬個股辨識（整板皆股市語境）。

合規：PTT Stock 板為公開、非 18+ 看板；低頻率、低量、可識別 UA、設 over18 cookie；
連線偶有重置，故 fetcher 帶重試與退避。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from selectolax.parser import HTMLParser

from ..base import BaseCollector, CollectorRunResult, RawDocument
from ..news.dedup import normalize_url, simhash

logger = logging.getLogger(__name__)

Fetcher = Callable[[str], str]
SeenPredicate = Callable[[str], bool]

_TPE = timezone(timedelta(hours=8))
# 略過的看板分類（公告、置底工具文等非討論內容）
_SKIP_PREFIX = ("[公告]", "[協尋]", "[情報] 板規", "Fw:")


class PttSource(BaseModel):
    id: str
    name: str
    board: str = "Stock"
    base_url: str = "https://www.ptt.cc"
    weight: float = 0.7
    interval: int = 900
    enabled: bool = True
    max_per_run: int = 6
    implicit_stock_context: bool = True


def _default_fetcher(timeout: float = 15.0,
                     user_agent: str = "Mozilla/5.0 (compatible; StockHeatBot/0.1; +contact)"
                     ) -> Fetcher:
    import httpx
    from tenacity import retry, stop_after_attempt, wait_exponential

    client = httpx.Client(
        timeout=timeout, headers={"User-Agent": user_agent},
        cookies={"over18": "1"}, follow_redirects=True)

    @retry(stop=stop_after_attempt(4),
           wait=wait_exponential(multiplier=1, max=10), reraise=True)
    def fetch(url: str) -> str:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text

    return fetch


def parse_list(html: str, base_url: str) -> list[str]:
    """解析看板列表頁，回傳文章絕對網址（略過公告／已刪文）。"""
    tree = HTMLParser(html)
    urls: list[str] = []
    for ent in tree.css("div.r-ent"):
        a = ent.css_first("div.title a")
        if a is None:  # 已刪除的文章只有純文字、無連結
            continue
        title = a.text(strip=True)
        if title.startswith(_SKIP_PREFIX):
            continue
        href = a.attributes.get("href", "")
        if href:
            urls.append(base_url + href)
    return urls


def _parse_date(value: str) -> datetime | None:
    try:
        dt = datetime.strptime(value.strip(), "%a %b %d %H:%M:%S %Y")
        return dt.replace(tzinfo=_TPE).astimezone(timezone.utc)
    except ValueError:
        return None


class _Article:
    __slots__ = ("title", "author", "content", "published_at", "engagement",
                 "pushes", "boos")

    def __init__(self, title, author, content, published_at, engagement, pushes, boos):
        self.title = title
        self.author = author
        self.content = content
        self.published_at = published_at
        self.engagement = engagement
        self.pushes = pushes
        self.boos = boos


def parse_article(html: str) -> _Article:
    tree = HTMLParser(html)
    metas = [m.text(strip=True)
             for m in tree.css("div.article-metaline span.article-meta-value")]
    author = metas[0] if len(metas) > 0 else ""
    title = metas[1] if len(metas) > 1 else ""
    published_at = _parse_date(metas[2]) if len(metas) > 2 else None

    # 互動量：推/噓/→ 留言
    pushes = boos = neutral = 0
    for p in tree.css("div.push span.push-tag"):
        tag = p.text(strip=True)
        if tag.startswith("推"):
            pushes += 1
        elif tag.startswith("噓"):
            boos += 1
        else:
            neutral += 1
    engagement = pushes + boos + neutral

    # 主文：#main-content 去掉 meta 與留言
    main = tree.css_first("#main-content")
    content = ""
    if main is not None:
        for sel in ("div.article-metaline", "div.article-metaline-right",
                    "div.push", "span.f2"):
            for n in main.css(sel):
                n.decompose()
        content = re.sub(r"\n{3,}", "\n\n", main.text(separator="\n")).strip()

    return _Article(title, author, content, published_at, engagement, pushes, boos)


class PttCollector(BaseCollector):
    source_type = "social"

    def __init__(
        self,
        source: PttSource,
        *,
        fetcher: Fetcher | None = None,
        seen: SeenPredicate | None = None,
        mark_seen: Callable[[str], None] | None = None,
    ) -> None:
        self.config = source
        self.source = source.id
        self.default_interval = source.interval
        self._fetch_text = fetcher or _default_fetcher()
        self._seen = seen or (lambda _u: False)
        self._mark_seen = mark_seen or (lambda _u: None)

    def _index_url(self) -> str:
        return f"{self.config.base_url}/bbs/{self.config.board}/index.html"

    def discover(self) -> list[str]:
        try:
            html = self._fetch_text(self._index_url())
        except Exception:  # noqa: BLE001
            logger.warning("[%s] 無法取得看板列表", self.source, exc_info=True)
            return []
        links: Iterable[str] = parse_list(html, self.config.base_url)
        urls: list[str] = []
        seen_in_run: set[str] = set()
        for link in links:
            norm = normalize_url(link)
            if norm in seen_in_run or self._seen(norm):
                continue
            seen_in_run.add(norm)
            urls.append(link)
            if len(urls) >= self.config.max_per_run:
                break
        return urls

    def fetch(self, url: str) -> RawDocument:
        html = self._fetch_text(url)
        art = parse_article(html)
        norm = normalize_url(url)
        self._mark_seen(norm)
        return RawDocument(
            source=self.source,
            source_type=self.source_type,
            external_id=norm,
            url=url,
            title=art.title,
            content=art.content,
            author=art.author,
            published_at=art.published_at or datetime.now(timezone.utc),
            content_quality="full" if art.content else "partial",
            raw_meta={
                "weight": self.config.weight,
                "simhash": simhash(art.title + "\n" + art.content),
                "engagement": art.engagement,
                "pushes": art.pushes,
                "boos": art.boos,
                "implicit_stock_context": self.config.implicit_stock_context,
            },
        )


def collect_ptt_board(
    source: PttSource,
    *,
    fetcher: Fetcher | None = None,
    seen: SeenPredicate | None = None,
) -> CollectorRunResult:
    return PttCollector(source, fetcher=fetcher, seen=seen).run()
