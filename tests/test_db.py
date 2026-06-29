from datetime import date, datetime, timezone

import pytest

from stock_heat.collectors.base import RawDocument
from stock_heat.db import models as m
from stock_heat.db.engine import get_engine, init_db, session_scope
from stock_heat.db.ingest import ingest_documents, recompute_heat_for_day, seed_reference
from stock_heat.db.repository import SqlHeatStore
from stock_heat.processing.dictionary import get_dictionary

DICT = get_dictionary("data/tickers.csv")


@pytest.fixture()
def db_url(tmp_path):
    path = (tmp_path / "test.db").as_posix()
    return f"sqlite:///{path}"


def _raw(ext, title, body, published):
    return RawDocument(
        source="news.cnyes", source_type="news", external_id=ext,
        url=f"https://news.example.com/{ext}", title=title, content=body,
        published_at=published, raw_meta={"simhash": 123456789, "weight": 1.0},
    )


def _seed(url, docs):
    init_db(url)
    with session_scope(url) as s:
        seed_reference(s, DICT, {"news.cnyes": ("鉅亨網", "news", 1.0)})
        inserted = ingest_documents(s, docs, DICT)
    return inserted


def test_init_db_creates_tables(db_url):
    init_db(db_url)
    insp = __import__("sqlalchemy").inspect(get_engine(db_url))
    names = set(insp.get_table_names())
    assert {"tickers", "raw_documents", "processed_documents",
            "document_ticker_mentions", "ticker_heat_timeseries"}.issubset(names)


def test_ingest_writes_raw_processed_mentions(db_url):
    pub = datetime(2026, 6, 29, 9, tzinfo=timezone.utc)
    docs = [_raw("a1", "台積電法說會看好 外資調升目標價",
                 "台積電（2330）法說會樂觀，外資買超，股價大漲。", pub)]
    inserted = _seed(db_url, docs)
    assert inserted == 1
    with session_scope(db_url) as s:
        assert s.query(m.RawDocument).count() == 1
        assert s.query(m.ProcessedDocument).count() == 1
        mentions = s.query(m.DocumentTickerMention).all()
        assert any(x.ticker == "2330" for x in mentions)


def test_ingest_is_idempotent(db_url):
    pub = datetime(2026, 6, 29, 9, tzinfo=timezone.utc)
    docs = [_raw("a1", "台積電走高", "台積電股價大漲，外資看好。", pub)]
    assert _seed(db_url, docs) == 1
    with session_scope(db_url) as s:
        again = ingest_documents(s, docs, DICT)
    assert again == 0


def test_recompute_heat_writes_timeseries(db_url):
    pub = datetime(2026, 6, 29, 9, tzinfo=timezone.utc)
    docs = [
        _raw("a1", "台積電法說會看好", "台積電（2330）樂觀，外資買超，股價大漲。", pub),
        _raw("a2", "台積電AI需求強勁", "台積電獲利創高，先進製程滿載。", pub),
        _raw("b1", "長榮運價下滑", "長榮（2603）遭外資賣超，股價走低。", pub),
    ]
    _seed(db_url, docs)
    with session_scope(db_url) as s:
        n = recompute_heat_for_day(s, date(2026, 6, 29))
    assert n >= 2
    with session_scope(db_url) as s:
        rows = s.query(m.TickerHeatTimeseries).all()
        scores = {r.ticker: r.heat_score for r in rows}
    assert "2330" in scores and scores["2330"] > 0
    # 台積電兩篇 > 長榮一篇 → 溫度較高
    assert scores["2330"] > scores["2603"]


def test_sql_store_reads_back(db_url):
    pub = datetime(2026, 6, 29, 9, tzinfo=timezone.utc)
    docs = [_raw("a1", "台積電法說會看好",
                 "台積電（2330）樂觀，外資買超，股價大漲。", pub)]
    _seed(db_url, docs)
    with session_scope(db_url) as s:
        recompute_heat_for_day(s, date(2026, 6, 29))

    store = SqlHeatStore(db_url)
    assert store.latest_date() == date(2026, 6, 29)
    rec = store.get("2330")
    assert rec is not None
    assert rec.name == "台積電"
    assert rec.latest.heat_score > 0
    assert len(rec.documents) == 1
    assert any(c[0] == "database" for c in store.health_components())


def test_api_against_db_store(db_url):
    from fastapi.testclient import TestClient

    from stock_heat.api.deps import get_store
    from stock_heat.api.main import app

    pub = datetime(2026, 6, 29, 9, tzinfo=timezone.utc)
    docs = [
        _raw("a1", "台積電法說會看好", "台積電（2330）樂觀，外資買超，股價大漲。", pub),
        _raw("b1", "長榮運價下滑", "長榮（2603）遭外資賣超，股價走低。", pub),
    ]
    _seed(db_url, docs)
    with session_scope(db_url) as s:
        recompute_heat_for_day(s, date(2026, 6, 29))

    store = SqlHeatStore(db_url)
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        items = client.get("/api/v1/rankings/heat").json()["items"]
        assert "2330" in [i["ticker"] for i in items]
        summary = client.get("/api/v1/tickers/2330").json()
        assert summary["name"] == "台積電"
        assert client.get("/api/v1/health").json()["status"] in ("ok", "degraded")
    finally:
        app.dependency_overrides.clear()
