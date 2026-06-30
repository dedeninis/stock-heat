from datetime import date, datetime, timezone

import pytest

from stock_heat.collectors.base import RawDocument
from stock_heat.collectors.trends import fetch_ticker_interest
from stock_heat.db import models as m
from stock_heat.db.engine import session_scope
from stock_heat.db.ingest import ingest_documents, recompute_heat_for_day
from stock_heat.jobs import bootstrap, collect_trends
from stock_heat.processing.dictionary import get_dictionary
from stock_heat.scoring import MentionSignal, compute_heat_scores

NOW = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
DICT = get_dictionary("data/tickers.csv")


def fake_fetcher(values: dict[str, int]):
    def fetch(terms):
        return {t: values.get(t, 0) for t in terms}
    return fetch


@pytest.fixture()
def db_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'trends.db').as_posix()}"


def test_fetch_ticker_interest_maps_back_to_ticker():
    tickers = [("2330", "台積電"), ("2454", "聯發科")]
    out = fetch_ticker_interest(tickers, fetcher=fake_fetcher({"台積電": 80, "聯發科": 20}))
    assert out == {"2330": 80, "2454": 20}


def test_fetch_batches_over_five():
    tickers = [(str(i), f"n{i}") for i in range(7)]
    seen = []

    def fetch(terms):
        seen.append(len(terms))
        return {t: 10 for t in terms}

    fetch_ticker_interest(tickers, fetcher=fetch)
    assert seen == [5, 2]


def test_trends_signal_adds_heat_not_sentiment():
    def sig(**kw):
        base = dict(ticker="2330", source="news.a", source_weight=1.0, confidence=0.8,
                    sentiment=0.6, published_at=NOW)
        base.update(kw)
        return MentionSignal(**base)

    news = sig()
    trend = sig(source="trends.google", sentiment=0.0, contributes_sentiment=False,
                source_weight=0.8)
    only_news = compute_heat_scores([news], reference_time=NOW)[0]
    with_trend = compute_heat_scores([news, trend], reference_time=NOW)[0]

    assert with_trend.raw_heat > only_news.raw_heat
    assert with_trend.sentiment == only_news.sentiment
    assert "trends.google" in with_trend.source_breakdown


def _raw(ext, title, body, pub):
    return RawDocument(source="news.cnyes", source_type="news", external_id=ext,
                       url=f"https://x/{ext}", title=title, content=body, published_at=pub)


def test_collect_trends_and_recompute_integration(db_url):
    bootstrap(db_url)
    pub = datetime(2026, 6, 30, 9, tzinfo=timezone.utc)
    with session_scope(db_url) as s:
        ingest_documents(s, [
            _raw("a", "台積電法說會看好", "台積電（2330）樂觀，外資買超，股價大漲。", pub),
        ], DICT)

    # 注入假的搜尋興趣
    n = collect_trends(db_url, day=date(2026, 6, 30),
                       fetcher=fake_fetcher({"台積電": 90}))
    assert n == 1
    with session_scope(db_url) as s:
        tr = s.get(m.TickerTrend, ("2330", date(2026, 6, 30)))
        assert tr is not None and tr.interest == 90

    with session_scope(db_url) as s:
        recompute_heat_for_day(s, date(2026, 6, 30))
        row = s.get(m.TickerHeatTimeseries, ("2330", date(2026, 6, 30), "daily"))
        assert row is not None
        assert "trends.google" in (row.source_breakdown or {})
