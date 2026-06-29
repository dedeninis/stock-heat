"""溫度演算法參數（docs/04 §7）。

從 ``config/scoring.yaml`` 載入；缺檔時使用設計文件的預設值，
讓計算層在無設定檔的測試情境也能運作。
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class HeatParams(BaseModel):
    half_life_hours: float = 24.0
    novelty_alpha: float = 0.5
    repost_weight: float = 1.0
    normalize_percentile: float = 99.0
    min_confidence: float = 0.5

    @property
    def decay_lambda(self) -> float:
        """λ = ln2 / 半衰期。"""
        return math.log(2) / self.half_life_hours


class VelocityParams(BaseModel):
    baseline_days: int = 7
    epsilon: float = 1.0


class AnomalyParams(BaseModel):
    lookback_days: int = 30
    sigma: float = 2.0


class ScoringConfig(BaseModel):
    heat: HeatParams = Field(default_factory=HeatParams)
    velocity: VelocityParams = Field(default_factory=VelocityParams)
    anomaly: AnomalyParams = Field(default_factory=AnomalyParams)


def load_scoring_config(path: str | Path = "config/scoring.yaml") -> ScoringConfig:
    p = Path(path)
    if not p.exists():
        return ScoringConfig()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return ScoringConfig(**data)
