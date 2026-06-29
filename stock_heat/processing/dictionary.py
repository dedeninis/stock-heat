"""個股字典載入（docs/03 §5）。

從 ``data/tickers.csv`` 載入個股，提供代號、正式名與別名查詢。
別名欄位以 ``;`` 分隔（避免與 CSV 逗號衝突）。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class TickerEntry:
    ticker: str
    name: str
    aliases: tuple[str, ...]
    industry: str
    market: str

    @property
    def surface_forms(self) -> tuple[str, ...]:
        """所有可用於比對的文字（正式名 + 別名，去重）。"""
        forms = [self.name, *self.aliases]
        seen: set[str] = set()
        uniq: list[str] = []
        for f in forms:
            f = f.strip()
            if f and f not in seen:
                seen.add(f)
                uniq.append(f)
        return tuple(uniq)


@dataclass
class TickerDictionary:
    entries: dict[str, TickerEntry] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, ticker: str) -> TickerEntry | None:
        return self.entries.get(ticker)

    def all(self) -> list[TickerEntry]:
        return list(self.entries.values())


def load_ticker_dictionary(path: str | Path = "data/tickers.csv") -> TickerDictionary:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"找不到個股字典：{p}")
    entries: dict[str, TickerEntry] = {}
    with p.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            ticker = (row.get("ticker") or "").strip()
            if not ticker:
                continue
            aliases = tuple(
                a.strip() for a in (row.get("aliases") or "").split(";") if a.strip()
            )
            entries[ticker] = TickerEntry(
                ticker=ticker,
                name=(row.get("name") or "").strip(),
                aliases=aliases,
                industry=(row.get("industry") or "").strip(),
                market=(row.get("market") or "").strip(),
            )
    return TickerDictionary(entries=entries)


@lru_cache(maxsize=4)
def get_dictionary(path: str = "data/tickers.csv") -> TickerDictionary:
    """快取版載入器，避免重複讀檔。"""
    return load_ticker_dictionary(path)
