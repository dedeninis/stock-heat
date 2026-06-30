"""Ingestion 寫入路徑：擷取結果 → 處理 → 溫度 → 持久化（docs/02 §5）。

設計為冪等：同一篇 RawDocument（以 source+external_id 判定）重複餵入不會重算或重複寫入，
溫度計算可對任一日重跑（重算，docs/04 §7）。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..collectors.base import RawDocument as CollectedDoc
from ..processing.dictionary import TickerDictionary, get_dictionary
from ..processing.pipeline import ProcessingPipeline
from ..scoring import ScoringConfig, compute_heat_scores
from ..scoring.heat import MentionSignal
from ..scoring.velocity import heat_velocity, is_surge
from . import models as m


def seed_reference(
    session: Session,
    dictionary: TickerDictionary | None = None,
    sources: dict[str, tuple[str, str, float]] | None = None,
) -> None:
    """upsert 個股與來源主檔。sources: {id: (name, source_type, weight)}。"""
    dictionary = dictionary or get_dictionary("data/tickers.csv")
    for entry in dictionary.all():
        if session.get(m.Ticker, entry.ticker) is None:
            session.add(m.Ticker(
                ticker=entry.ticker, name=entry.name, aliases=list(entry.aliases),
                industry=entry.industry, market=entry.market))
    for sid, (name, stype, weight) in (sources or {}).items():
        if session.get(m.Source, sid) is None:
            session.add(m.Source(id=sid, name=name, source_type=stype, weight=weight))
    session.flush()


def ingest_documents(
    session: Session,
    raws: list[CollectedDoc],
    dictionary: TickerDictionary | None = None,
) -> int:
    """寫入原始文件並跑處理 pipeline，回傳新寫入的文件數（已存在者略過）。"""
    pipeline = ProcessingPipeline(dictionary or get_dictionary("data/tickers.csv"))
    inserted = 0
    for raw in raws:
        exists = session.scalar(
            select(m.RawDocument.id).where(
                m.RawDocument.source == raw.source,
                m.RawDocument.external_id == raw.external_id,
            )
        )
        if exists is not None:
            continue

        row = m.RawDocument(
            source=raw.source, source_type=raw.source_type, external_id=raw.external_id,
            url=raw.url, title=raw.title, content=raw.content, author=raw.author,
            published_at=raw.published_at,
            simhash=(str(sh) if (sh := raw.raw_meta.get("simhash")) is not None else None),
            content_quality=raw.content_quality,
            engagement=int(raw.raw_meta.get("engagement", 0) or 0),
            raw_meta=raw.raw_meta,
        )
        session.add(row)
        session.flush()  # 取得 row.id

        proc = pipeline.process(raw)
        pdoc = m.ProcessedDocument(
            raw_id=row.id, lang=proc.lang, doc_sentiment=proc.doc_sentiment,
            is_repost=proc.is_repost, pipeline_version=proc.pipeline_version,
        )
        session.add(pdoc)
        session.flush()
        for mention in proc.mentions:
            session.add(m.DocumentTickerMention(
                processed_id=pdoc.id, ticker=mention.ticker,
                confidence=mention.confidence,
                ticker_sentiment=mention.ticker_sentiment or 0.0,
                positions=mention.positions,
            ))
        inserted += 1
    session.flush()
    return inserted


def _signals_for_window(
    session: Session, reference: datetime, window_hours: int
) -> list[MentionSignal]:
    weights = dict(session.execute(select(m.Source.id, m.Source.weight)).all())
    start = reference - timedelta(hours=window_hours)
    rows = session.execute(
        select(m.DocumentTickerMention, m.RawDocument, m.ProcessedDocument)
        .join(m.ProcessedDocument,
              m.DocumentTickerMention.processed_id == m.ProcessedDocument.id)
        .join(m.RawDocument, m.ProcessedDocument.raw_id == m.RawDocument.id)
        .where(m.RawDocument.published_at.is_not(None),
               m.RawDocument.published_at >= start,
               m.RawDocument.published_at <= reference)
    ).all()
    signals: list[MentionSignal] = []
    for mention, raw, proc in rows:
        signals.append(MentionSignal(
            ticker=mention.ticker, source=raw.source,
            source_weight=weights.get(raw.source, 1.0),
            confidence=mention.confidence, sentiment=mention.ticker_sentiment,
            published_at=raw.published_at, is_repost=proc.is_repost,
            engagement=raw.engagement or 0,
        ))
    return signals


def recompute_heat_for_day(
    session: Session,
    day: date,
    *,
    config: ScoringConfig | None = None,
    window_hours: int = 48,
    granularity: str = "daily",
) -> int:
    """重算某日的各個股溫度並寫入時序，回傳更新的個股數。"""
    cfg = config or ScoringConfig()
    reference = datetime.combine(day, time(23, 59, 59))
    signals = _signals_for_window(session, reference, window_hours)
    scores = compute_heat_scores(signals, reference_time=reference, config=cfg)

    for th in scores:
        prior_heats = list(session.scalars(
            select(m.TickerHeatTimeseries.heat_score)
            .where(m.TickerHeatTimeseries.ticker == th.ticker,
                   m.TickerHeatTimeseries.granularity == granularity,
                   m.TickerHeatTimeseries.ts < day)
            .order_by(m.TickerHeatTimeseries.ts)
        ).all())
        prior_vels = list(session.scalars(
            select(m.TickerHeatTimeseries.heat_velocity)
            .where(m.TickerHeatTimeseries.ticker == th.ticker,
                   m.TickerHeatTimeseries.granularity == granularity,
                   m.TickerHeatTimeseries.ts < day)
            .order_by(m.TickerHeatTimeseries.ts)
        ).all())

        velocity = heat_velocity(th.heat_score, prior_heats, params=cfg.velocity)

        row = session.get(m.TickerHeatTimeseries, (th.ticker, day, granularity))
        if row is None:
            row = m.TickerHeatTimeseries(ticker=th.ticker, ts=day, granularity=granularity)
            session.add(row)
        row.volume = th.volume
        row.heat_score = th.heat_score
        row.sentiment = th.sentiment
        row.heat_velocity = velocity
        row.source_breakdown = th.source_breakdown
        row.scoring_version = "v0"

        if is_surge(velocity, prior_vels, params=cfg.anomaly):
            detected = datetime.combine(day, time(0, 0))
            already = session.scalar(
                select(m.HeatEvent.id).where(
                    m.HeatEvent.ticker == th.ticker,
                    m.HeatEvent.detected_at == detected)
            )
            if already is None:
                session.add(m.HeatEvent(
                    ticker=th.ticker, detected_at=detected, velocity=velocity,
                    heat_score=th.heat_score, top_terms=[], sample_doc_ids=[]))
    session.flush()
    return len(scores)
