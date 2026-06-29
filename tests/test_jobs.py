from datetime import date

import pytest

from stock_heat.collectors.news.sources import NewsSource
from stock_heat.db.repository import SqlHeatStore
from stock_heat.jobs import bootstrap, collect_source, recompute_today

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>台積電法說會看好 外資調升目標價</title>
<link>https://news.example.com/a/1</link><pubDate>Mon, 29 Jun 2026 01:00:00 GMT</pubDate></item>
<item><title>長榮運價下滑</title>
<link>https://news.example.com/a/2</link><pubDate>Mon, 29 Jun 2026 02:00:00 GMT</pubDate></item>
</channel></rss>"""


def _art(t, b):
    return f"<html><head><title>{t}</title></head><body><main><article><h1>{t}</h1><p>{b}</p></article></main></body></html>"


PAGES = {
    "https://news.example.com/a/1": _art(
        "台積電法說會看好", "台積電（2330）法說會樂觀，外資買超，股價大漲。"),
    "https://news.example.com/a/2": _art(
        "長榮運價下滑", "長榮（2603）遭外資賣超，股價走低。"),
}


def fetcher(u: str) -> str:
    return PAGES.get(u, RSS)


@pytest.fixture()
def db_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}"


def _source():
    return NewsSource(id="news.test", name="測試", rss="https://news.example.com/rss",
                      article_selector="main article", weight=1.0, interval=300)


def test_collect_source_ingests_and_dedupes(db_url):
    bootstrap(db_url)
    src = _source()
    ins1 = collect_source(src, db_url, fetcher=fetcher)
    assert ins1 == 2
    ins2 = collect_source(src, db_url, fetcher=fetcher)
    assert ins2 == 0  # 第二輪由 DB seen-set 去重


def test_collect_then_recompute_produces_heat(db_url):
    bootstrap(db_url)
    collect_source(_source(), db_url, fetcher=fetcher)
    n = recompute_today(db_url, day=date(2026, 6, 29))
    assert n == 2

    store = SqlHeatStore(db_url)
    by = {r.ticker: r for r in store.all_records()}
    assert "2330" in by and by["2330"].latest.heat_score > 0
    assert by["2603"].latest.sentiment < 0  # 長榮偏空


def test_collector_run_recorded(db_url):
    bootstrap(db_url)
    collect_source(_source(), db_url, fetcher=fetcher)
    from stock_heat.db import models as m
    from stock_heat.db.engine import session_scope
    with session_scope(db_url) as s:
        runs = s.query(m.CollectorRun).all()
        assert len(runs) == 1
        assert runs[0].fetched == 2
        assert runs[0].status == "ok"


def test_published_at_carried_from_rss(db_url):
    bootstrap(db_url)
    collect_source(_source(), db_url, fetcher=fetcher)
    from stock_heat.db import models as m
    from stock_heat.db.engine import session_scope
    with session_scope(db_url) as s:
        docs = s.query(m.RawDocument).all()
        assert all(d.published_at is not None for d in docs)


def test_build_scheduler_registers_jobs(tmp_path):
    from apscheduler.schedulers.background import BackgroundScheduler

    from stock_heat.config import Settings
    from stock_heat.scheduler import build_scheduler

    settings = Settings(database_url=f"sqlite:///{(tmp_path / 's.db').as_posix()}")
    sched = build_scheduler(settings, scheduler=BackgroundScheduler())
    ids = {j.id for j in sched.get_jobs()}
    assert "recompute:intraday" in ids
    assert "recompute:daily" in ids
    assert any(i.startswith("collect:") for i in ids)
