from datetime import datetime, timezone

from stock_heat.collectors.base import RawDocument
from stock_heat.processing import process_document
from stock_heat.processing.dictionary import get_dictionary

DICT = get_dictionary("data/tickers.csv")


def _raw(title: str, content: str) -> RawDocument:
    return RawDocument(
        source="news.test",
        source_type="news",
        external_id="https://news.example.com/news/id/1",
        url="https://news.example.com/news/id/1",
        title=title,
        content=content,
        published_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
    )


def test_pipeline_end_to_end():
    raw = _raw(
        "台積電法說會釋出樂觀展望",
        "台積電今日召開法說會，管理層看好下半年，外資調升目標價，盤中股價大漲。",
    )
    proc = process_document(raw, DICT)

    assert proc.external_id == raw.external_id
    assert proc.lang == "zh"
    assert proc.doc_sentiment > 0
    assert proc.pipeline_version == "v0"

    tickers = {m.ticker: m for m in proc.mentions}
    assert "2330" in tickers
    assert tickers["2330"].confidence >= 0.5
    assert tickers["2330"].ticker_sentiment > 0


def test_pipeline_mixed_sentiment_per_ticker():
    raw = _raw(
        "盤勢分析",
        "台積電受惠AI需求走高，外資買超；長榮則因運價下滑遭賣超、股價大跌。",
    )
    proc = process_document(raw, DICT)
    by = {m.ticker: m.ticker_sentiment for m in proc.mentions}
    assert by["2330"] > 0
    assert by["2603"] < 0


def test_pipeline_is_idempotent():
    raw = _raw("台積電走高", "台積電股價大漲，外資看好。")
    a = process_document(raw, DICT)
    b = process_document(raw, DICT)
    assert a.model_dump() == b.model_dump()


def test_pipeline_non_chinese_skips_recognition():
    raw = _raw("Quarterly update", "The company reported solid revenue growth.")
    proc = process_document(raw, DICT)
    assert proc.lang == "other"
    assert proc.mentions == []
