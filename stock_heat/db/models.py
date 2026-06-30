"""SQLAlchemy ORM 模型（docs/05）。

SQLite 優先（MVP，可離線、零外部服務）；改用 PostgreSQL + TimescaleDB 時，
只需替換連線字串並把 ticker_heat_timeseries 轉為 hypertable，模型本身不變。

時序表的 ``ts`` 在 MVP 以日粒度存 ``Date``；granularity 欄位區分日線/盤中。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# BigInt 主鍵：在 SQLite 退化為 INTEGER 才能對應 ROWID 自動遞增
_PK = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    source_type: Mapped[str] = mapped_column(String(16))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_sec: Mapped[int] = mapped_column(Integer, default=300)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0)


class Ticker(Base):
    __tablename__ = "tickers"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    industry: Mapped[str] = mapped_column(String(64), default="")
    market: Mapped[str] = mapped_column(String(16), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RawDocument(Base):
    __tablename__ = "raw_documents"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_raw_source_extid"),)

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # 以字串存：SimHash 為 64-bit 無號值，超出 SQLite 有號 INTEGER 範圍
    simhash: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    content_quality: Mapped[str] = mapped_column(String(16), default="full")
    engagement: Mapped[int] = mapped_column(Integer, default=0)  # 互動量（社群推/讚/回應）
    raw_meta: Mapped[dict] = mapped_column(JSON, default=dict)

    processed: Mapped["ProcessedDocument | None"] = relationship(
        back_populates="raw", uselist=False)


class ProcessedDocument(Base):
    __tablename__ = "processed_documents"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    raw_id: Mapped[int] = mapped_column(
        ForeignKey("raw_documents.id"), unique=True, index=True)
    lang: Mapped[str] = mapped_column(String(8), default="zh")
    doc_sentiment: Mapped[float] = mapped_column(Float, default=0.0)
    is_repost: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    pipeline_version: Mapped[str] = mapped_column(String(16), default="v0")

    raw: Mapped[RawDocument] = relationship(back_populates="processed")
    mentions: Mapped[list["DocumentTickerMention"]] = relationship(
        back_populates="processed", cascade="all, delete-orphan")


class DocumentTickerMention(Base):
    __tablename__ = "document_ticker_mentions"
    __table_args__ = (
        UniqueConstraint("processed_id", "ticker", name="uq_mention_proc_ticker"),)

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    processed_id: Mapped[int] = mapped_column(
        ForeignKey("processed_documents.id"), index=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("tickers.ticker"), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    ticker_sentiment: Mapped[float] = mapped_column(Float, default=0.0)
    positions: Mapped[list] = mapped_column(JSON, default=list)

    processed: Mapped[ProcessedDocument] = relationship(back_populates="mentions")


class TickerHeatTimeseries(Base):
    __tablename__ = "ticker_heat_timeseries"

    ticker: Mapped[str] = mapped_column(
        ForeignKey("tickers.ticker"), primary_key=True)
    ts: Mapped[date] = mapped_column(Date, primary_key=True)
    granularity: Mapped[str] = mapped_column(String(16), primary_key=True, default="daily")
    volume: Mapped[int] = mapped_column(Integer, default=0)
    heat_score: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)
    heat_velocity: Mapped[float] = mapped_column(Float, default=0.0)
    source_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    scoring_version: Mapped[str] = mapped_column(String(16), default="v0")


class HeatEvent(Base):
    __tablename__ = "heat_events"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("tickers.ticker"), index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    velocity: Mapped[float] = mapped_column(Float)
    heat_score: Mapped[float] = mapped_column(Float)
    top_terms: Mapped[list] = mapped_column(JSON, default=list)
    sample_doc_ids: Mapped[list] = mapped_column(JSON, default=list)


class CollectorRun(Base):
    __tablename__ = "collector_runs"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    discovered: Mapped[int] = mapped_column(Integer, default=0)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error_detail: Mapped[dict] = mapped_column(JSON, default=dict)
