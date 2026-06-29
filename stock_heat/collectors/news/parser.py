"""RSS 與文章 HTML 解析（docs/03 §4.3–4.4）。

- ``parse_rss``：解析 RSS feed，回傳文章連結與基本 meta。
- ``parse_article``：以來源專屬 selector 擷取內文，失敗時退場到通用抽取。

解析失敗時保留標題與 meta，標記 content_quality="partial"，不丟棄。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import feedparser
from selectolax.parser import HTMLParser

_WS_RE = re.compile(r"[ \t　]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")

# 通用抽取時略過的雜訊節點
_NOISE_SELECTORS = (
    "script", "style", "noscript", "nav", "header", "footer", "aside",
    "form", "iframe", ".ad", ".ads", ".advertisement", ".related",
    ".share", ".social", ".breadcrumb",
)


class ParsedEntry:
    """RSS 條目的精簡表示。"""

    __slots__ = ("url", "title", "published_at", "summary")

    def __init__(self, url: str, title: str,
                 published_at: datetime | None, summary: str) -> None:
        self.url = url
        self.title = title
        self.published_at = published_at
        self.summary = summary


class ParsedArticle:
    __slots__ = ("title", "content", "author", "published_at", "quality")

    def __init__(self, title: str, content: str, author: str | None,
                 published_at: datetime | None, quality: str) -> None:
        self.title = title
        self.content = content
        self.author = author
        self.published_at = published_at
        self.quality = quality


def _struct_time_to_dt(st: object) -> datetime | None:
    if not st:
        return None
    try:
        import calendar
        return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return None


def parse_rss(content: str) -> list[ParsedEntry]:
    """解析 RSS/Atom 內容字串，回傳條目清單。"""
    feed = feedparser.parse(content)
    entries: list[ParsedEntry] = []
    for e in feed.entries:
        link = getattr(e, "link", "") or ""
        if not link:
            continue
        published = _struct_time_to_dt(
            getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
        )
        entries.append(ParsedEntry(
            url=link,
            title=(getattr(e, "title", "") or "").strip(),
            published_at=published,
            summary=(getattr(e, "summary", "") or "").strip(),
        ))
    return entries


def _clean_text(text: str) -> str:
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def _strip_noise(tree: HTMLParser) -> None:
    """移除廣告/導覽/頁尾等雜訊節點（就地修改 tree）。"""
    for sel in _NOISE_SELECTORS:
        for node in tree.css(sel):
            node.decompose()


def _extract_with_selector(tree: HTMLParser, selector: str) -> str:
    node = tree.css_first(selector)
    if node is None:
        return ""
    return _clean_text(node.text(separator="\n"))


def _extract_generic(tree: HTMLParser) -> str:
    """退場策略：取最長的 <article>/正文段落集合（雜訊已先移除）。"""
    # 優先 <article>，否則彙整所有 <p>
    article = tree.css_first("article")
    if article is not None:
        text = _clean_text(article.text(separator="\n"))
        if len(text) >= 80:
            return text
    paragraphs = [p.text(separator=" ").strip() for p in tree.css("p")]
    paragraphs = [p for p in paragraphs if len(p) >= 15]
    return _clean_text("\n".join(paragraphs))


def _extract_published(tree: HTMLParser) -> datetime | None:
    """從常見 meta/time 標籤抽取發布時間（ISO 8601）。"""
    candidates = (
        ("meta[property='article:published_time']", "content"),
        ("meta[name='article:published_time']", "content"),
        ("meta[property='og:article:published_time']", "content"),
        ("meta[itemprop='datePublished']", "content"),
        ("time[datetime]", "datetime"),
    )
    for sel, attr in candidates:
        node = tree.css_first(sel)
        if node is None:
            continue
        value = node.attributes.get(attr)
        if not value:
            continue
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt
    return None


def _extract_title(tree: HTMLParser, fallback: str) -> str:
    for sel in ("h1", "meta[property='og:title']", "title"):
        node = tree.css_first(sel)
        if node is None:
            continue
        value = node.attributes.get("content") if sel.startswith("meta") else node.text()
        if value and value.strip():
            return value.strip()
    return fallback


def parse_article(html: str, *, selector: str | None = None,
                  fallback_title: str = "") -> ParsedArticle:
    """從文章 HTML 擷取內文。

    首選來源專屬 selector；命中不足或無 selector 時退場到通用抽取。
    """
    tree = HTMLParser(html)
    title = _extract_title(tree, fallback_title)
    _strip_noise(tree)  # 兩條擷取路徑共用，確保 selector 命中時也去雜訊

    content = ""
    quality = "full"
    if selector:
        content = _extract_with_selector(tree, selector)
    if len(content) < 80:  # selector 失準或無 selector → 退場
        generic = _extract_generic(tree)
        if len(generic) > len(content):
            content = generic
            quality = "partial" if selector else quality

    if len(content) < 40:
        quality = "partial"

    author_node = tree.css_first("meta[name='author']")
    author = author_node.attributes.get("content") if author_node else None

    return ParsedArticle(
        title=title,
        content=content,
        author=author,
        published_at=_extract_published(tree),
        quality=quality,
    )
