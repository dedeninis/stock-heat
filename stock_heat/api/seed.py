"""產生示範用的記憶體資料（MVP 無 DB 階段）。

用真實的 ``scoring.velocity`` 與 ``processing.sentiment`` 計算升溫率與文件情緒，
讓 API 回傳的數字具一致性；資料本身為確定性合成（固定亂數種子），方便測試。
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from ..processing.dictionary import get_dictionary
from ..processing.sentiment import analyze_sentiment
from ..scoring.velocity import heat_velocity, is_surge
from .store import HeatPoint, InMemoryHeatStore, StoredDoc, TickerRecord

TODAY = date(2026, 6, 29)
HISTORY_DAYS = 14

_SOURCES = {"news.cnyes": "鉅亨網", "news.cna": "中央社"}

# ticker -> (基準溫度, 每日趨勢, 情緒傾向, 是否今日異常升溫, 示範新聞標題)
_PROFILE: dict[str, tuple[float, float, float, bool, list[str]]] = {
    "2330": (70, 0.8, 0.5, False, [
        "台積電法說會看好 外資調升目標價",
        "台積電AI需求強勁 先進製程滿載獲利創高",
    ]),
    "2454": (45, 0.5, 0.4, False, [
        "聯發科新旗艦晶片發表 法人看好營收成長",
        "聯發科車用晶片出貨亮眼",
    ]),
    "2317": (40, 0.2, 0.2, False, [
        "鴻海電動車布局受惠 集團營收回升",
    ]),
    "2603": (25, 0.3, -0.6, True, [
        "長榮運價急漲市場關注 但獲利前景仍受下修疑慮",
        "長榮海運遭外資賣超 股價走低",
    ]),
    "2412": (30, 0.05, 0.1, False, [
        "中華電信5G用戶成長 營收穩健",
    ]),
    "1301": (20, -0.1, -0.2, False, [
        "台塑石化價差收斂 獲利下滑",
    ]),
}


def _heat_series(rng: random.Random, base: float, trend: float, surge: bool) -> list[float]:
    series = []
    for i in range(HISTORY_DAYS):
        val = base + trend * i + rng.uniform(-3, 3)
        series.append(max(0.0, min(100.0, val)))
    if surge:
        series[-1] = min(100.0, series[-1] + 48)  # 今日暴衝
    return [round(v, 2) for v in series]


def _build_record(ticker: str, profile: tuple) -> TickerRecord:
    base, trend, mood, surge, titles = profile
    rng = random.Random(hash(ticker) & 0xFFFF)
    dictionary = get_dictionary("data/tickers.csv")
    entry = dictionary.get(ticker)
    name = entry.name if entry else ticker
    industry = entry.industry if entry else ""

    heats = _heat_series(rng, base, trend, surge)
    points: list[HeatPoint] = []
    velocities: list[float] = []
    for i, h in enumerate(heats):
        day = TODAY - timedelta(days=HISTORY_DAYS - 1 - i)
        v = heat_velocity(h, heats[:i])
        velocities.append(v)
        sentiment = round(max(-1.0, min(1.0, mood + rng.uniform(-0.2, 0.2))), 3)
        volume = max(1, int(h / 6) + rng.randint(0, 3))
        # 合成溫度組成（示範資料皆為新聞來源）
        breakdown = {"news.cnyes": round(h * 0.6, 2), "news.cna": round(h * 0.4, 2)}
        points.append(HeatPoint(ts=day, heat_score=h, sentiment=sentiment,
                                volume=volume, heat_velocity=v,
                                source_breakdown=breakdown))

    surged = is_surge(velocities[-1], velocities[:-1])

    documents: list[StoredDoc] = []
    sources = list(_SOURCES.items())
    for j, title in enumerate(titles):
        src_id, src_name = sources[j % len(sources)]
        documents.append(StoredDoc(
            title=title,
            source=src_id,
            source_name=src_name,
            url=f"https://news.example.com/{ticker}/{j}",
            published_at=datetime.now(timezone.utc) - timedelta(hours=3 * (j + 1)),
            ticker_sentiment=analyze_sentiment(title),
            confidence=round(0.6 + 0.1 * (len(titles) - j), 3),
        ))

    return TickerRecord(ticker=ticker, name=name, industry=industry,
                        points=points, documents=documents, is_surge=surged)


def build_demo_store() -> InMemoryHeatStore:
    records = {t: _build_record(t, p) for t, p in _PROFILE.items()}
    return InMemoryHeatStore(records)
