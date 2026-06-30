"""排程任務函式（docs/02 §5）。

把「擷取 → 處理 → 溫度 → 持久化」包成可被排程器或 CLI 觸發的函式。
HTTP 抓取以 ``fetcher`` 注入，方便離線測試；正式執行使用預設 httpx fetcher。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from .collectors.base import BaseCollector
from .collectors.news import NewsCollector
from .collectors.news.collector import Fetcher
from .collectors.news.sources import load_news_sources
from .collectors.ptt import PttCollector, load_ptt_sources
from .db import models as m
from .db.engine import init_db, session_scope
from .db.ingest import ingest_documents, recompute_heat_for_day, seed_reference
from .processing.dictionary import TickerDictionary, get_dictionary
from .scoring import ScoringConfig, load_scoring_config

logger = logging.getLogger(__name__)


def bootstrap(
    url: str | None = None,
    *,
    sources_path: str = "config/sources.yaml",
    tickers_path: str = "data/tickers.csv",
) -> None:
    """建立綱要並 upsert 個股與來源主檔（啟動時呼叫一次）。"""
    init_db(url)
    dictionary = get_dictionary(tickers_path)
    sources: dict[str, tuple[str, str, float]] = {
        s.id: (s.name, "news", s.weight) for s in load_news_sources(sources_path)
    }
    for s in load_ptt_sources(sources_path):
        sources[s.id] = (s.name, "social", s.weight)
    with session_scope(url) as session:
        seed_reference(session, dictionary, sources)


def _run_and_ingest(
    src_id: str,
    build_collector,
    url: str | None,
    dictionary: TickerDictionary,
) -> int:
    """共用：載入 seen-set → 建 collector → 跑一輪 → 寫入並記錄 collector_runs。"""
    with session_scope(url) as session:
        seen_ids = set(session.scalars(
            select(m.RawDocument.external_id).where(m.RawDocument.source == src_id)
        ).all())

    collector: BaseCollector = build_collector(lambda n: n in seen_ids)
    run = collector.run()

    with session_scope(url) as session:
        inserted = ingest_documents(session, run.documents, dictionary)
        session.add(m.CollectorRun(
            source=src_id, finished_at=datetime.now(timezone.utc),
            discovered=run.discovered, fetched=run.fetched, errors=run.errors,
            status=run.status,
        ))
        if run.fetched and not run.errors:
            source_row = session.get(m.Source, src_id)
            if source_row is not None:
                source_row.last_success_at = datetime.now(timezone.utc)

    logger.info("[%s] discovered=%d fetched=%d inserted=%d errors=%d",
                src_id, run.discovered, run.fetched, inserted, run.errors)
    return inserted


def collect_source(
    src,
    url: str | None = None,
    *,
    fetcher: Fetcher | None = None,
    dictionary: TickerDictionary | None = None,
) -> int:
    """對單一新聞來源跑一輪。回傳新寫入篇數。"""
    dictionary = dictionary or get_dictionary("data/tickers.csv")
    return _run_and_ingest(
        src.id, lambda seen: NewsCollector(src, fetcher=fetcher, seen=seen),
        url, dictionary)


def collect_ptt(
    src,
    url: str | None = None,
    *,
    fetcher: Fetcher | None = None,
    dictionary: TickerDictionary | None = None,
) -> int:
    """對單一 PTT 看板來源跑一輪。回傳新寫入篇數。"""
    dictionary = dictionary or get_dictionary("data/tickers.csv")
    return _run_and_ingest(
        src.id, lambda seen: PttCollector(src, fetcher=fetcher, seen=seen),
        url, dictionary)


def collect_and_ingest(
    url: str | None = None,
    *,
    sources_path: str = "config/sources.yaml",
    fetcher: Fetcher | None = None,
    dictionary: TickerDictionary | None = None,
) -> int:
    """對所有啟用的新聞 + 社群來源各跑一輪，回傳本輪新寫入的文件總數。"""
    dictionary = dictionary or get_dictionary("data/tickers.csv")
    total = sum(
        collect_source(src, url, fetcher=fetcher, dictionary=dictionary)
        for src in load_news_sources(sources_path)
    )
    total += sum(
        collect_ptt(src, url, dictionary=dictionary)  # PTT 用自帶 fetcher（cookie/retry）
        for src in load_ptt_sources(sources_path)
    )
    return total


def collect_trends(
    url: str | None = None,
    *,
    day: date | None = None,
    top_n: int = 20,
    window_hours: int = 48,
    fetcher=None,
    tickers_path: str = "data/tickers.csv",
) -> int:
    """查詢當日最熱門前 N 檔的 Google 搜尋興趣，upsert 到 ticker_trends。回傳寫入檔數。

    僅查「已在新聞/社群活躍」的個股（避免同名詞噪音、且符合 Trends 查詢量限制）。
    """
    from sqlalchemy import func

    from .collectors.trends import fetch_ticker_interest
    target = day or datetime.now(timezone.utc).date()
    start = datetime.combine(target, datetime.min.time()) - timedelta(hours=window_hours)
    dictionary = get_dictionary(tickers_path)

    with session_scope(url) as session:
        rows = session.execute(
            select(m.DocumentTickerMention.ticker, func.count().label("c"))
            .join(m.ProcessedDocument,
                  m.DocumentTickerMention.processed_id == m.ProcessedDocument.id)
            .join(m.RawDocument, m.ProcessedDocument.raw_id == m.RawDocument.id)
            .where(m.RawDocument.published_at >= start)
            .group_by(m.DocumentTickerMention.ticker)
            .order_by(func.count().desc()).limit(top_n)
        ).all()
    hot = [(tk, e.name) for tk, _ in rows if (e := dictionary.get(tk))]
    if not hot:
        return 0

    interest = fetch_ticker_interest(hot, fetcher=fetcher)

    written = 0
    with session_scope(url) as session:
        for ticker, value in interest.items():
            row = session.get(m.TickerTrend, (ticker, target))
            if row is None:
                row = m.TickerTrend(ticker=ticker, ts=target)
                session.add(row)
            row.interest = int(value)
            written += 1
    logger.info("trends: 寫入 %d 檔搜尋興趣（%s）", written, target)
    return written


def recompute_today(
    url: str | None = None,
    *,
    day: date | None = None,
    config: ScoringConfig | None = None,
    scoring_path: str = "config/scoring.yaml",
) -> int:
    """重算指定日（預設今日 UTC）的各個股溫度，回傳更新個股數。"""
    target = day or datetime.now(timezone.utc).date()
    cfg = config or load_scoring_config(scoring_path)
    with session_scope(url) as session:
        n = recompute_heat_for_day(session, target, config=cfg)
    logger.info("recompute %s -> %d tickers", target, n)
    return n
