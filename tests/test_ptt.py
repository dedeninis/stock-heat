from stock_heat.collectors.ptt import PttCollector, PttSource
from stock_heat.collectors.ptt.collector import parse_article, parse_list

BASE = "https://www.ptt.cc"

LIST_HTML = """<div class="r-list-container">
  <div class="r-ent"><div class="nrec"><span class="hl f3">41</span></div>
    <div class="title"><a href="/bbs/Stock/M.1.A.1.html">[標的] 2330 台積電 多</a></div></div>
  <div class="r-ent"><div class="nrec"></div>
    <div class="title">(本文已被刪除)</div></div>
  <div class="r-ent"><div class="nrec"></div>
    <div class="title"><a href="/bbs/Stock/M.9.A.9.html">[公告] 板規</a></div></div>
  <div class="r-ent"><div class="nrec"><span class="hl f3">爆</span></div>
    <div class="title"><a href="/bbs/Stock/M.2.A.2.html">[新聞] 長榮運價</a></div></div>
</div>"""


def _article(title, body, pushes, boos, arrows):
    rows = ""
    rows += '<div class="push"><span class="push-tag">推 </span></div>' * pushes
    rows += '<div class="push"><span class="push-tag">噓 </span></div>' * boos
    rows += '<div class="push"><span class="push-tag">→ </span></div>' * arrows
    return f"""<div id="main-content">
  <div class="article-metaline"><span class="article-meta-tag">作者</span>
    <span class="article-meta-value">tester (測試)</span></div>
  <div class="article-metaline-right"><span class="article-meta-tag">看板</span>
    <span class="article-meta-value">Stock</span></div>
  <div class="article-metaline"><span class="article-meta-tag">標題</span>
    <span class="article-meta-value">{title}</span></div>
  <div class="article-metaline"><span class="article-meta-tag">時間</span>
    <span class="article-meta-value">Tue Jun 30 12:23:49 2026</span></div>
  {body}
  <span class="f2">※ 發信站: 批踢踢實業坊</span>
  {rows}
</div>"""


ARTS = {
    f"{BASE}/bbs/Stock/M.1.A.1.html":
        _article("[標的] 2330 台積電 多", "台積電今天法說會看好，這檔要噴了，上車！", 99, 30, 50),
    f"{BASE}/bbs/Stock/M.2.A.2.html":
        _article("[新聞] 長榮運價", "長榮運價下滑，住套房了，畢業。", 5, 40, 10),
}


def make_fetcher():
    def fetch(url):
        if url.endswith("/bbs/Stock/index.html"):
            return LIST_HTML
        return ARTS[url]
    return fetch


def test_parse_list_skips_deleted_and_announcements():
    urls = parse_list(LIST_HTML, BASE)
    assert urls == [f"{BASE}/bbs/Stock/M.1.A.1.html", f"{BASE}/bbs/Stock/M.2.A.2.html"]


def test_parse_article_extracts_engagement_and_body():
    art = parse_article(ARTS[f"{BASE}/bbs/Stock/M.1.A.1.html"])
    assert art.title == "[標的] 2330 台積電 多"
    assert art.author == "tester (測試)"
    assert art.engagement == 99 + 30 + 50
    assert art.pushes == 99 and art.boos == 30
    assert "法說會看好" in art.content
    assert "發信站" not in art.content   # f2 已移除
    assert art.published_at is not None and art.published_at.year == 2026


def test_ptt_collector_end_to_end():
    src = PttSource(id="social.ptt_stock", name="PTT Stock")
    result = PttCollector(src, fetcher=make_fetcher()).run()
    assert result.fetched == 2
    doc = next(d for d in result.documents if "M.1.A.1" in d.url)
    assert doc.source_type == "social"
    assert doc.raw_meta["engagement"] == 179
    assert doc.raw_meta["implicit_stock_context"] is True
    assert doc.published_at is not None


def test_ptt_doc_recognises_ticker_via_implicit_context():
    # 經處理層：股票專板放寬辨識，短代號/名稱即可辨識
    from stock_heat.processing import process_document
    from stock_heat.processing.dictionary import get_dictionary
    src = PttSource(id="social.ptt_stock", name="PTT Stock")
    docs = PttCollector(src, fetcher=make_fetcher()).run().documents
    d = next(x for x in docs if "M.1.A.1" in x.url)
    proc = process_document(d, get_dictionary("data/tickers.csv"))
    assert "2330" in {m.ticker for m in proc.mentions}
