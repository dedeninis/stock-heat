import math
from datetime import datetime, timedelta, timezone

import pytest

from stock_heat.scoring import MentionSignal, ScoringConfig, compute_heat_scores, decay

NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


def sig(ticker, *, weight=1.0, conf=0.8, sent=0.0, age_h=0.0, repost=False, source="news.a"):
    return MentionSignal(
        ticker=ticker, source=source, source_weight=weight, confidence=conf,
        sentiment=sent, published_at=NOW - timedelta(hours=age_h), is_repost=repost,
    )


def test_decay_half_life():
    lam = math.log(2) / 24
    assert decay(0, lam) == pytest.approx(1.0)
    assert decay(24, lam) == pytest.approx(0.5, rel=1e-6)
    assert decay(-5, lam) == pytest.approx(1.0)  # 未來時間夾到 0


def test_more_mentions_higher_heat():
    signals = [sig("2330") for _ in range(5)] + [sig("2454")]
    res = {r.ticker: r for r in compute_heat_scores(signals, reference_time=NOW)}
    assert res["2330"].heat_score > res["2454"].heat_score
    assert res["2330"].volume == 5


def test_top_ticker_normalized_near_100():
    signals = [sig("2330") for _ in range(10)] + [sig("2454"), sig("2317")]
    res = compute_heat_scores(signals, reference_time=NOW)
    assert res[0].ticker == "2330"
    assert res[0].heat_score == pytest.approx(100.0, abs=1.0)


def test_repost_discounted_vs_original():
    original = compute_heat_scores([sig("2330")], reference_time=NOW)[0]
    repost = compute_heat_scores([sig("2330", repost=True)], reference_time=NOW)[0]
    # α=0.5：原創 contribution 1.5x、轉載 1.0x
    assert original.raw_heat == pytest.approx(repost.raw_heat * 1.5, rel=1e-6)


def test_time_decay_recent_beats_old():
    recent = compute_heat_scores([sig("2330", age_h=0)], reference_time=NOW)[0]
    old = compute_heat_scores([sig("2330", age_h=24)], reference_time=NOW)[0]
    assert recent.raw_heat == pytest.approx(old.raw_heat * 2, rel=1e-6)


def test_source_weight_matters():
    strong = compute_heat_scores([sig("2330", weight=1.0)], reference_time=NOW)[0]
    weak = compute_heat_scores([sig("2330", weight=0.5)], reference_time=NOW)[0]
    assert strong.raw_heat == pytest.approx(weak.raw_heat * 2, rel=1e-6)


def test_sentiment_contribution_weighted():
    # 兩則等權，情緒 +1 與 -1 → 聚合 ~0
    res = compute_heat_scores(
        [sig("2330", sent=1.0), sig("2330", sent=-1.0)], reference_time=NOW
    )[0]
    assert res.sentiment == pytest.approx(0.0, abs=1e-6)


def test_low_confidence_filtered_out():
    res = compute_heat_scores([sig("2330", conf=0.4)], reference_time=NOW)
    assert res == []  # 低於 min_confidence 0.5


def test_source_breakdown_recorded():
    signals = [sig("2330", source="news.a"), sig("2330", source="ptt.stock", weight=0.7)]
    res = compute_heat_scores(signals, reference_time=NOW)[0]
    assert set(res.source_breakdown.keys()) == {"news.a", "ptt.stock"}


def test_custom_config_min_confidence():
    cfg = ScoringConfig()
    cfg.heat.min_confidence = 0.9
    res = compute_heat_scores([sig("2330", conf=0.8)], reference_time=NOW, config=cfg)
    assert res == []
