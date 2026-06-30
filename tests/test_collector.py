import pytest

from stock_heat.collectors.news import NewsCollector, NewsSource, load_news_sources

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item><title>台積電法說會釋出樂觀展望</title>
    <link>https://news.example.com/news/id/1001?utm_source=rss</link>
    <pubDate>Mon, 29 Jun 2026 01:00:00 GMT</pubDate></item>
  <item><title>聯發科新晶片發表</title>
    <link>https://news.example.com/news/id/1002</link>
    <pubDate>Mon, 29 Jun 2026 02:00:00 GMT</pubDate></item>
</channel></rss>"""


def _article(title: str, body: str) -> str:
    return f"""<html><head><title>{title}</title></head><body><main><article>
      <h1>{title}</h1><p>{body}</p></article></main></body></html>"""


ARTICLES = {
    "https://news.example.com/news/id/1001?utm_source=rss":
        _article("台積電法說會釋出樂觀展望",
                 "台積電法說會管理層對下半年展望樂觀，外資調升目標價，盤中股價走高。"),
    "https://news.example.com/news/id/1002":
        _article("聯發科新晶片發表",
                 "聯發科發表新一代旗艦晶片，主打 AI 運算能力，預期帶動營收成長動能。"),
}


def make_fetcher(rss_url: str):
    def fetch(url: str) -> str:
        if url == rss_url:
            return RSS
        if url in ARTICLES:
            return ARTICLES[url]
        raise ValueError(f"unexpected url: {url}")
    return fetch


def make_source(**over) -> NewsSource:
    base = dict(id="news.test", name="測試來源", rss="https://news.example.com/rss",
                article_selector="main article", weight=1.0, interval=300)
    base.update(over)
    return NewsSource(**base)


def test_collector_end_to_end_produces_raw_documents():
    src = make_source()
    collector = NewsCollector(src, fetcher=make_fetcher(src.rss))
    result = collector.run()

    assert result.status == "ok"
    assert result.discovered == 2
    assert result.fetched == 2
    assert result.errors == 0

    doc = result.documents[0]
    assert doc.source == "news.test"
    assert doc.source_type == "news"
    # external_id 為正規化 URL（追蹤參數已移除）
    assert doc.external_id == "https://news.example.com/news/id/1001"
    assert "展望樂觀" in doc.content
    assert doc.raw_meta["simhash"] != 0


def test_collector_skips_seen_urls():
    src = make_source()
    seen_keys = {"https://news.example.com/news/id/1001"}
    collector = NewsCollector(
        src, fetcher=make_fetcher(src.rss), seen=lambda u: u in seen_keys,
    )
    result = collector.run()
    assert result.discovered == 1
    assert result.documents[0].external_id == "https://news.example.com/news/id/1002"


def test_collector_isolates_single_fetch_failure():
    src = make_source()
    base_fetch = make_fetcher(src.rss)

    def flaky(url: str) -> str:
        if url == "https://news.example.com/news/id/1002":
            raise RuntimeError("boom")
        return base_fetch(url)

    result = NewsCollector(src, fetcher=flaky).run()
    assert result.fetched == 1
    assert result.errors == 1
    assert result.status == "partial"


def test_mark_seen_called_after_fetch():
    src = make_source()
    marked: list[str] = []
    NewsCollector(src, fetcher=make_fetcher(src.rss),
                  mark_seen=marked.append).run()
    assert "https://news.example.com/news/id/1001" in marked
    assert len(marked) == 2


def test_load_news_sources_filters_disabled(tmp_path):
    cfg = tmp_path / "sources.yaml"
    cfg.write_text(
        "news:\n"
        "  - id: a\n    name: A\n    rss: https://a/rss\n    enabled: true\n"
        "  - id: b\n    name: B\n    rss: https://b/rss\n    enabled: false\n",
        encoding="utf-8",
    )
    sources = load_news_sources(cfg)
    assert [s.id for s in sources] == ["a"]


def test_news_source_requires_rss_or_list_url():
    with pytest.raises(ValueError):
        NewsSource(id="x", name="X")


RSS_WITH_SUMMARY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item><title>台積電獲外資調升</title>
    <link>https://news.example.com/a/9</link>
    <description>&lt;p&gt;台積電（2330）今日獲外資調升目標價，股價走高。&lt;/p&gt;</description>
    <pubDate>Mon, 29 Jun 2026 03:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_rss_summary_fallback_when_article_body_empty():
    src = make_source(rss="https://news.example.com/rss")

    def fetch(url: str) -> str:
        if url == src.rss:
            return RSS_WITH_SUMMARY
        # 文章頁無可用內文（模擬 JS 渲染 / selector 失效）
        return "<html><head><title>台積電獲外資調升</title></head><body></body></html>"

    result = NewsCollector(src, fetcher=fetch).run()
    assert result.fetched == 1
    doc = result.documents[0]
    # 內文應退回 RSS 摘要（HTML 已去標籤），且仍可辨識個股
    assert "台積電" in doc.content
    assert "2330" in doc.content
    assert doc.content_quality == "partial"
