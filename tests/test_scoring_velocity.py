from stock_heat.scoring import annotate_velocity, heat_velocity, is_surge, surge_threshold


def test_velocity_positive_when_above_baseline():
    v = heat_velocity(80.0, [40.0, 42.0, 38.0, 41.0])
    assert v > 0


def test_velocity_negative_when_below_baseline():
    v = heat_velocity(20.0, [40.0, 42.0, 38.0, 41.0])
    assert v < 0


def test_velocity_no_history_zero():
    assert heat_velocity(50.0, []) == 0.0


def test_velocity_uses_baseline_window():
    # baseline_days 預設 7：只取最後 7 筆
    history = [100.0] * 30 + [10.0] * 7  # 近 7 日 = 10
    v = heat_velocity(10.0, history)
    assert v == 0.0  # current 等於近 7 日平均


def test_is_surge_detects_anomaly():
    history = [0.0, 0.1, -0.1, 0.05, 0.0, 0.02, -0.05, 0.0, 0.03, 0.01]
    assert is_surge(2.0, history)        # 遠高於 mean+2σ
    assert not is_surge(0.02, history)   # 在常態範圍內


def test_is_surge_insufficient_history_conservative():
    assert is_surge(1.5, [])         # > 1.0 門檻
    assert not is_surge(0.5, [])


def test_surge_threshold_value():
    history = [0.0] * 10
    assert surge_threshold(history) == 0.0  # mean=0,std=0


def test_annotate_velocity_bundle():
    out = annotate_velocity(
        "2330", current_heat=90.0,
        heat_history=[40.0, 41.0, 39.0],
        velocity_history=[0.0, 0.1, -0.1, 0.05, 0.0, 0.02],
    )
    assert out["ticker"] == "2330"
    assert out["heat_velocity"] > 0
    assert out["is_surge"] is True
