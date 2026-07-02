import pytest
from fastapi.testclient import TestClient

from stock_heat.api import quote
from stock_heat.api.main import app

# MIS msgArray 首筆的精簡樣本（6224 聚鼎，收盤 77.20 昨收 70.20）
MIS_6224 = {"c": "6224", "n": "聚鼎", "z": "77.2000", "y": "70.2000",
            "o": "71.0000", "h": "78.0000", "l": "70.5000", "v": "5000", "t": "13:30:00"}
MIS_2330 = {"c": "2330", "n": "台積電", "z": "-", "y": "2370.0000",
            "o": "-", "h": "-", "l": "-", "v": "0", "t": "09:00:00"}


@pytest.fixture(autouse=True)
def _clear():
    quote.clear_cache()
    quote.set_override_fetcher(None)
    yield
    quote.clear_cache()
    quote.set_override_fetcher(None)


def test_channel_routing():
    assert quote._channel("2330", "TWSE") == "tse_2330.tw"
    assert quote._channel("6224", "TPEx") == "otc_6224.tw"


def test_get_quote_parses_change_and_pct():
    q = quote.get_quote("6224", "TWSE", fetcher=lambda ch: MIS_6224)
    assert q["available"] is True
    assert q["price"] == 77.2
    assert q["prev_close"] == 70.2
    assert q["change"] == 7.0
    assert q["change_pct"] == pytest.approx(9.97, abs=0.02)
    assert q["volume"] == 5000


def test_get_quote_no_trade_falls_back_to_prev_close():
    q = quote.get_quote("2330", "TWSE", fetcher=lambda ch: MIS_2330)
    assert q["price"] == 2370.0
    assert q["change"] == 0.0


def test_get_quote_graceful_when_fetch_fails():
    def boom(ch):
        raise RuntimeError("blocked")
    q = quote.get_quote("2330", "TWSE", fetcher=boom)
    assert q["available"] is False
    assert q["price"] is None


def test_get_quote_empty_when_no_row():
    q = quote.get_quote("9999", "TWSE", fetcher=lambda ch: {})
    assert q["available"] is False


def test_quote_endpoint_with_override():
    quote.set_override_fetcher(lambda ch: MIS_6224)
    client = TestClient(app)
    body = client.get("/api/v1/tickers/6224/quote").json()
    assert body["ticker"] == "6224"
    assert body["market"] == "TWSE"
    assert body["available"] is True
    assert body["price"] == 77.2
    assert body["chart_url"] == "https://www.wantgoo.com/stock/6224/technical-chart"


def test_quote_endpoint_degrades_gracefully():
    def boom(ch):
        raise RuntimeError("blocked")
    quote.set_override_fetcher(boom)
    client = TestClient(app)
    body = client.get("/api/v1/tickers/2330/quote").json()
    assert body["available"] is False
    assert body["chart_url"].endswith("/stock/2330/technical-chart")
