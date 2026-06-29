"""資料存取抽象與記憶體實作。

``HeatStore`` 定義 API 需要的查詢介面；``InMemoryHeatStore`` 以記憶體資料實作，
之後可換成 DB 版（讀 ticker_heat_timeseries 等表，docs/05）而不動 API 路由。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass
class HeatPoint:
    ts: date
    heat_score: float
    sentiment: float
    volume: int
    heat_velocity: float


@dataclass
class StoredDoc:
    title: str
    source: str
    source_name: str
    url: str
    published_at: object  # datetime
    ticker_sentiment: float
    confidence: float


@dataclass
class TickerRecord:
    ticker: str
    name: str
    industry: str
    points: list[HeatPoint] = field(default_factory=list)  # 依日期遞增
    documents: list[StoredDoc] = field(default_factory=list)
    is_surge: bool = False

    def point_on(self, day: date) -> HeatPoint | None:
        for p in self.points:
            if p.ts == day:
                return p
        return None

    @property
    def latest(self) -> HeatPoint | None:
        return self.points[-1] if self.points else None


class HeatStore(Protocol):
    def latest_date(self) -> date | None: ...
    def all_records(self) -> list[TickerRecord]: ...
    def get(self, ticker: str) -> TickerRecord | None: ...
    def health_components(self) -> list[tuple[str, str, str | None]]: ...


class InMemoryHeatStore:
    def __init__(self, records: dict[str, TickerRecord]) -> None:
        self._records = records

    def latest_date(self) -> date | None:
        days = [p.ts for r in self._records.values() for p in r.points]
        return max(days) if days else None

    def all_records(self) -> list[TickerRecord]:
        return list(self._records.values())

    def get(self, ticker: str) -> TickerRecord | None:
        return self._records.get(ticker)

    def health_components(self) -> list[tuple[str, str, str | None]]:
        n = len(self._records)
        return [
            ("store", "ok", f"in-memory ({n} tickers)"),
            ("data", "ok" if n else "degraded",
             f"latest={self.latest_date()}"),
        ]
