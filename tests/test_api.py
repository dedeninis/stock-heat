import pytest
from fastapi.testclient import TestClient

from stock_heat.api.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_root_lists_endpoints(client):
    body = client.get("/").json()
    assert body["name"] == "stock-heat"
    assert "/api/v1/rankings/heat" in body["endpoints"]


def test_openapi_available(client):
    assert client.get("/openapi.json").status_code == 200


def test_heat_ranking_sorted_desc(client):
    r = client.get("/api/v1/rankings/heat")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0
    scores = [i["heat_score"] for i in items]
    assert scores == sorted(scores, reverse=True)
    assert items[0]["rank"] == 1


def test_heat_ranking_order_asc(client):
    items = client.get("/api/v1/rankings/heat", params={"order": "asc"}).json()["items"]
    scores = [i["heat_score"] for i in items]
    assert scores == sorted(scores)


def test_heat_ranking_limit(client):
    items = client.get("/api/v1/rankings/heat", params={"limit": 2}).json()["items"]
    assert len(items) == 2


def test_heat_ranking_sentiment_filter(client):
    items = client.get(
        "/api/v1/rankings/heat", params={"sentiment": "negative"}
    ).json()["items"]
    assert all(i["sentiment"] < 0 for i in items)


def test_heat_ranking_invalid_order_422(client):
    assert client.get("/api/v1/rankings/heat", params={"order": "sideways"}).status_code == 422


def test_surging_contains_surge_ticker(client):
    items = client.get("/api/v1/rankings/surging").json()["items"]
    assert "2603" in [i["ticker"] for i in items]
    assert all("heat_velocity" in i for i in items)


def test_ticker_summary(client):
    body = client.get("/api/v1/tickers/2330").json()
    assert body["ticker"] == "2330"
    assert body["name"] == "台積電"
    assert len(body["trend_7d"]) == 7
    assert "heat_score" in body


def test_ticker_summary_404(client):
    r = client.get("/api/v1/tickers/9999")
    assert r.status_code == 404


def test_timeseries_full_and_filtered(client):
    full = client.get("/api/v1/tickers/2330/timeseries").json()["points"]
    assert len(full) == 14
    filtered = client.get(
        "/api/v1/tickers/2330/timeseries", params={"from": "2026-06-27"}
    ).json()["points"]
    assert len(filtered) == 3
    assert all(p["ts"] >= "2026-06-27" for p in filtered)


def test_documents_only_links_no_fulltext(client):
    items = client.get("/api/v1/tickers/2330/documents").json()["items"]
    assert len(items) >= 1
    for d in items:
        assert d["url"].startswith("https://")
        assert "content" not in d  # 不全文轉載，只給標題與來源連結
        assert "title" in d and "source_name" in d


def test_search_by_alias_and_code(client):
    assert "2330" in [i["ticker"] for i in
                      client.get("/api/v1/search", params={"q": "台積"}).json()["items"]]
    assert "2330" in [i["ticker"] for i in
                      client.get("/api/v1/search", params={"q": "2330"}).json()["items"]]


def test_search_requires_query(client):
    assert client.get("/api/v1/search").status_code == 422


def test_health_ok(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert any(c["name"] == "store" for c in body["components"])
