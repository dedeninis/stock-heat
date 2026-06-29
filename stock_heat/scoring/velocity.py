"""升溫率與異常偵測（docs/04 §6）。

- 升溫率 Velocity = (Heat_today - baseline) / (baseline + ε)，baseline 取近 N 日移動平均。
- 異常：Velocity 超過近期 Velocity 的 mean + σ·std 視為「升溫事件」。

純函式，輸入歷史序列即可，便於離線測試與重算。
"""

from __future__ import annotations

import statistics

from .config import AnomalyParams, ScoringConfig, VelocityParams


def heat_velocity(
    current_heat: float,
    history: list[float],
    *,
    params: VelocityParams | None = None,
) -> float:
    """以近 ``baseline_days`` 的移動平均為基準計算升溫率。

    ``history`` 為時間遞增的過往每日溫度（不含今日）。
    歷史不足時以現有資料平均；完全無歷史則回傳 0。
    """
    params = params or VelocityParams()
    if not history:
        return 0.0
    window = history[-params.baseline_days:]
    baseline = sum(window) / len(window)
    return round((current_heat - baseline) / (baseline + params.epsilon), 4)


def is_surge(
    current_velocity: float,
    velocity_history: list[float],
    *,
    params: AnomalyParams | None = None,
) -> bool:
    """判定當前升溫率是否為異常（超過 mean + σ·std）。"""
    params = params or AnomalyParams()
    window = velocity_history[-params.lookback_days:]
    if len(window) < 2:
        # 樣本不足時，採保守正向門檻避免誤報
        return current_velocity > 1.0
    mean = statistics.fmean(window)
    std = statistics.pstdev(window)
    threshold = mean + params.sigma * std
    return current_velocity > threshold


def surge_threshold(
    velocity_history: list[float],
    *,
    params: AnomalyParams | None = None,
) -> float:
    """回傳當前的異常門檻值（供 API/UI 顯示）。"""
    params = params or AnomalyParams()
    window = velocity_history[-params.lookback_days:]
    if len(window) < 2:
        return 1.0
    return statistics.fmean(window) + params.sigma * statistics.pstdev(window)


def annotate_velocity(
    ticker: str,
    current_heat: float,
    heat_history: list[float],
    velocity_history: list[float],
    *,
    config: ScoringConfig | None = None,
) -> dict[str, object]:
    """便捷封裝：一次算出升溫率與是否異常。"""
    cfg = config or ScoringConfig()
    v = heat_velocity(current_heat, heat_history, params=cfg.velocity)
    return {
        "ticker": ticker,
        "heat_velocity": v,
        "is_surge": is_surge(v, velocity_history, params=cfg.anomaly),
    }
