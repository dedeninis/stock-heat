"""網路溫度計算（docs/04 §5）。

對某時間視窗內、提及各個股的 mention 訊號，計算：
- 原始熱度 H_raw = Σ sw·conf·decay·(1 + α·novelty)
- 正規化溫度 Heat = 100·log(1+H_raw)/log(1+H_raw^p99)，clip 到 [0,100]
- 加權聚合情緒（以對溫度的貢獻為權重）

純函式、無 I/O，輸入 mention 訊號即可離線測試與重算。
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from .config import HeatParams, ScoringConfig


@dataclass(frozen=True)
class MentionSignal:
    """單一「個股×文件」訊號，由處理層 + 來源權重組成。"""

    ticker: str
    source: str
    source_weight: float
    confidence: float
    sentiment: float
    published_at: datetime
    is_repost: bool = False
    engagement: int = 0  # 互動量（推/讚/回應…）；新聞通常為 0


@dataclass
class TickerHeat:
    """單一個股在視窗內的溫度結果（對應 docs/05 §3.6）。"""

    ticker: str
    volume: int
    heat_score: float
    sentiment: float
    raw_heat: float
    source_breakdown: dict[str, float] = field(default_factory=dict)


def decay(age_hours: float, lam: float) -> float:
    """時間衰減 exp(-λ·Δt)，Δt 為距視窗參考時間的小時數（負值視為 0）。"""
    return math.exp(-lam * max(0.0, age_hours))


def _contribution(sig: MentionSignal, ref: datetime, params: HeatParams) -> float:
    age_hours = (ref - sig.published_at).total_seconds() / 3600.0
    novelty = 0.0 if sig.is_repost else 1.0
    # 互動量加成：推爆的社群貼文比乏人問津者更熱；取 log 壓縮、新聞 engagement=0 → 不受影響
    engagement_factor = 1.0 + params.engagement_beta * math.log1p(max(0, sig.engagement))
    return (sig.source_weight
            * sig.confidence
            * decay(age_hours, params.decay_lambda)
            * (1.0 + params.novelty_alpha * novelty)
            * engagement_factor)


def _percentile(values: list[float], pct: float) -> float:
    """線性插值百分位（pct 為 0–100）。空集合回傳 0。"""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    s = sorted(values)
    rank = (pct / 100.0) * (len(s) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return s[int(rank)]
    frac = rank - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def compute_heat_scores(
    signals: list[MentionSignal],
    *,
    reference_time: datetime,
    config: ScoringConfig | None = None,
) -> list[TickerHeat]:
    """對一批 mention 訊號計算各個股的溫度，依溫度由高到低排序。"""
    params = (config or ScoringConfig()).heat

    by_ticker: dict[str, list[MentionSignal]] = defaultdict(list)
    for sig in signals:
        if sig.confidence < params.min_confidence:
            continue
        by_ticker[sig.ticker].append(sig)

    # 第一輪：原始熱度與加權情緒
    raw_by_ticker: dict[str, float] = {}
    sent_by_ticker: dict[str, float] = {}
    breakdown_by_ticker: dict[str, dict[str, float]] = {}
    volume_by_ticker: dict[str, int] = {}

    for ticker, sigs in by_ticker.items():
        raw = 0.0
        sent_num = 0.0
        breakdown: dict[str, float] = defaultdict(float)
        for sig in sigs:
            c = _contribution(sig, reference_time, params)
            raw += c
            sent_num += c * sig.sentiment
            breakdown[sig.source] += c
        raw_by_ticker[ticker] = raw
        sent_by_ticker[ticker] = (sent_num / raw) if raw > 0 else 0.0
        breakdown_by_ticker[ticker] = {k: round(v, 4) for k, v in breakdown.items()}
        volume_by_ticker[ticker] = len(sigs)

    # 第二輪：以全市場 raw 分布的 p99 做正規化
    p99 = _percentile(list(raw_by_ticker.values()), params.normalize_percentile)
    denom = math.log1p(p99) if p99 > 0 else 0.0

    results: list[TickerHeat] = []
    for ticker, raw in raw_by_ticker.items():
        if denom > 0:
            heat = 100.0 * math.log1p(raw) / denom
            heat = max(0.0, min(100.0, heat))
        else:
            heat = 0.0
        results.append(TickerHeat(
            ticker=ticker,
            volume=volume_by_ticker[ticker],
            heat_score=round(heat, 2),
            sentiment=round(sent_by_ticker[ticker], 3),
            raw_heat=round(raw, 4),
            source_breakdown=breakdown_by_ticker[ticker],
        ))

    results.sort(key=lambda r: r.heat_score, reverse=True)
    return results
