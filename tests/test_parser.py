from stock_heat.collectors.news.parser import parse_article, parse_rss

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>TW Stock</title>
  <item>
    <title>台積電法說會釋出樂觀展望</title>
    <link>https://news.example.com/news/id/1001?utm_source=rss</link>
    <pubDate>Mon, 29 Jun 2026 01:00:00 GMT</pubDate>
    <description>外資調升目標價</description>
  </item>
  <item>
    <title>聯發科新晶片發表</title>
    <link>https://news.example.com/news/id/1002</link>
    <pubDate>Mon, 29 Jun 2026 02:00:00 GMT</pubDate>
  </item>
</channel></rss>"""

ARTICLE = """<html><head><title>台積電法說會釋出樂觀展望 - 範例新聞</title>
<meta name="author" content="記者王小明"></head>
<body>
  <nav>導覽列雜訊</nav>
  <main><article>
    <h1>台積電法說會釋出樂觀展望</h1>
    <p>台積電今日召開法說會，管理層對下半年展望表示樂觀，預期先進製程需求強勁。</p>
    <p>外資隨即調升目標價，盤中股價一度走高超過百分之二，帶動電子權值股表現。</p>
    <div class="ad">廣告區塊應被移除</div>
  </article></main>
  <footer>頁尾雜訊</footer>
</body></html>"""


def test_parse_rss_returns_entries_with_links():
    entries = parse_rss(RSS)
    assert len(entries) == 2
    assert entries[0].url == "https://news.example.com/news/id/1001?utm_source=rss"
    assert entries[0].title == "台積電法說會釋出樂觀展望"
    assert entries[0].published_at is not None


def test_parse_article_with_selector_extracts_clean_body():
    art = parse_article(ARTICLE, selector="main article", fallback_title="")
    assert art.title == "台積電法說會釋出樂觀展望"
    assert "管理層對下半年展望表示樂觀" in art.content
    assert "廣告區塊" not in art.content
    assert "導覽列雜訊" not in art.content
    assert art.author == "記者王小明"
    assert art.quality == "full"


def test_parse_article_fallback_when_selector_misses():
    art = parse_article(ARTICLE, selector="div.does-not-exist", fallback_title="備援標題")
    # selector 命中不足 → 退場到通用抽取，仍取得內文，標記為 partial
    assert "管理層對下半年展望表示樂觀" in art.content
    assert art.quality == "partial"
