"""DB-backed HeatStore（讀取路徑）。

回傳與記憶體 store 相同的 ``TickerRecord`` / ``HeatPoint`` / ``StoredDoc`` 資料結構，
因此 API 路由完全不需改動即可由 in-memory 切換到資料庫（docs/02 §2.5 的接縫）。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..api.store import HeatPoint, StoredDoc, TickerRecord
from . import models as m
from .engine import database_url, get_engine, init_db


class SqlHeatStore:
    def __init__(self, url: str | None = None, *, doc_limit: int = 20) -> None:
        self._url = url or database_url()
        self._doc_limit = doc_limit
        init_db(self._url)

    def _session(self) -> Session:
        from sqlalchemy.orm import Session as _S
        return _S(bind=get_engine(self._url), expire_on_commit=False, future=True)

    def latest_date(self) -> date | None:
        with self._session() as s:
            return s.scalar(select(m.TickerHeatTimeseries.ts)
                            .order_by(m.TickerHeatTimeseries.ts.desc()).limit(1))

    def _surge_dates(self, s: Session, ticker: str) -> set[date]:
        rows = s.scalars(select(m.HeatEvent.detected_at)
                         .where(m.HeatEvent.ticker == ticker)).all()
        return {dt.date() for dt in rows}

    def _build_record(self, s: Session, ticker_row: m.Ticker) -> TickerRecord | None:
        points = [
            HeatPoint(ts=r.ts, heat_score=r.heat_score, sentiment=r.sentiment,
                      volume=r.volume, heat_velocity=r.heat_velocity)
            for r in s.scalars(
                select(m.TickerHeatTimeseries)
                .where(m.TickerHeatTimeseries.ticker == ticker_row.ticker,
                       m.TickerHeatTimeseries.granularity == "daily")
                .order_by(m.TickerHeatTimeseries.ts)).all()
        ]
        if not points:
            return None

        source_names = dict(s.execute(select(m.Source.id, m.Source.name)).all())
        doc_rows = s.execute(
            select(m.RawDocument, m.DocumentTickerMention)
            .join(m.ProcessedDocument, m.RawDocument.id == m.ProcessedDocument.raw_id)
            .join(m.DocumentTickerMention,
                  m.DocumentTickerMention.processed_id == m.ProcessedDocument.id)
            .where(m.DocumentTickerMention.ticker == ticker_row.ticker)
            .order_by(m.RawDocument.published_at.desc())
            .limit(self._doc_limit)
        ).all()
        documents = [
            StoredDoc(
                title=raw.title, source=raw.source,
                source_name=source_names.get(raw.source, raw.source),
                url=raw.url, published_at=raw.published_at,
                ticker_sentiment=mention.ticker_sentiment, confidence=mention.confidence,
            )
            for raw, mention in doc_rows
        ]

        latest_day = points[-1].ts
        is_surge = latest_day in self._surge_dates(s, ticker_row.ticker)
        return TickerRecord(
            ticker=ticker_row.ticker, name=ticker_row.name, industry=ticker_row.industry,
            points=points, documents=documents, is_surge=is_surge)

    def all_records(self) -> list[TickerRecord]:
        with self._session() as s:
            out = []
            for trow in s.scalars(select(m.Ticker)).all():
                rec = self._build_record(s, trow)
                if rec is not None:
                    out.append(rec)
            return out

    def get(self, ticker: str) -> TickerRecord | None:
        with self._session() as s:
            trow = s.get(m.Ticker, ticker)
            return self._build_record(s, trow) if trow else None

    def health_components(self) -> list[tuple[str, str, str | None]]:
        with self._session() as s:
            n_pts = s.scalar(select(m.TickerHeatTimeseries.ts)
                             .order_by(m.TickerHeatTimeseries.ts.desc()).limit(1))
        return [
            ("database", "ok", self._url.split("://", 1)[0]),
            ("data", "ok" if n_pts else "degraded", f"latest={n_pts}"),
        ]
