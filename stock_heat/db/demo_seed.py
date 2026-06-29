"""輕量示範資料：直接把合成資料寫入 DB（不跑擷取/辨識管線）。

用於部署 demo 的 seed-on-start：毫秒級完成、不佔 CPU，
故不會因 GIL 阻塞 async 事件迴圈而拖垮 healthcheck。

與 api/seed.py 的記憶體示範資料同源，因此 DB 版與記憶體版畫面一致。
真實資料請用 `python -m scripts.collect_once`（擷取真新聞）或 `scripts.seed_db`。
"""

from __future__ import annotations

from datetime import datetime, time

from ..api.seed import build_demo_store
from . import models as m
from .engine import init_db, session_scope


def seed_demo_db(url: str | None = None) -> int:
    """寫入合成個股/溫度時序/文件/升溫事件，回傳寫入的個股數。"""
    init_db(url)
    store = build_demo_store()
    sources = {"news.cnyes": "鉅亨網", "news.cna": "中央社"}

    with session_scope(url) as s:
        for sid, name in sources.items():
            if s.get(m.Source, sid) is None:
                s.add(m.Source(id=sid, name=name, source_type="news", weight=1.0))

        for rec in store.all_records():
            if s.get(m.Ticker, rec.ticker) is None:
                s.add(m.Ticker(ticker=rec.ticker, name=rec.name,
                               industry=rec.industry, aliases=[]))

            for p in rec.points:
                key = (rec.ticker, p.ts, "daily")
                if s.get(m.TickerHeatTimeseries, key) is None:
                    s.add(m.TickerHeatTimeseries(
                        ticker=rec.ticker, ts=p.ts, granularity="daily",
                        volume=p.volume, heat_score=p.heat_score,
                        sentiment=p.sentiment, heat_velocity=p.heat_velocity))

            for d in rec.documents:
                exists = s.query(m.RawDocument.id).filter_by(
                    source=d.source, external_id=d.url).first()
                if exists:
                    continue
                raw = m.RawDocument(
                    source=d.source, source_type="news", external_id=d.url,
                    url=d.url, title=d.title, content="", published_at=d.published_at)
                s.add(raw)
                s.flush()
                proc = m.ProcessedDocument(raw_id=raw.id, doc_sentiment=d.ticker_sentiment)
                s.add(proc)
                s.flush()
                s.add(m.DocumentTickerMention(
                    processed_id=proc.id, ticker=rec.ticker,
                    confidence=d.confidence, ticker_sentiment=d.ticker_sentiment))

            if rec.is_surge and rec.points:
                last = rec.points[-1]
                s.add(m.HeatEvent(
                    ticker=rec.ticker, detected_at=datetime.combine(last.ts, time()),
                    velocity=last.heat_velocity, heat_score=last.heat_score))

    return len(store.all_records())
