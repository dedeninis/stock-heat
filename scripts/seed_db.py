"""以真實 pipeline 產生並寫入示範資料庫。

對數檔個股、數天範圍合成財經新聞，逐篇經 擷取→處理→溫度 寫入 DB，
並對每一日重算溫度。產出可供 DB-backed 儀表板查詢的累積資料。

用法：
    python -m scripts.seed_db                 # 預設 SQLite stock_heat.db、近 12 天
    STOCKHEAT_DATABASE_URL=... python -m scripts.seed_db
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone

from stock_heat.collectors.base import RawDocument
from stock_heat.collectors.news.dedup import simhash
from stock_heat.db.engine import init_db, session_scope
from stock_heat.db.ingest import ingest_documents, recompute_heat_for_day, seed_reference
from stock_heat.processing.dictionary import get_dictionary

DAYS = 12
TODAY = date(2026, 6, 29)

SOURCES = {
    "news.cnyes": ("鉅亨網", "news", 1.0),
    "news.cna": ("中央社", "news", 0.9),
}

# ticker -> (每日基準篇數, 多/空傾向, 標題模板)
PROFILE = {
    "2330": (3, "pos", ["{n}法說會看好 外資調升目標價", "{n}AI需求強勁 獲利創高",
                        "{n}先進製程滿載 法人看好"]),
    "2454": (2, "pos", ["{n}新晶片發表 營收成長動能強", "{n}車用晶片出貨亮眼"]),
    "2317": (2, "pos", ["{n}電動車布局受惠 集團營收回升", "{n}伺服器訂單強勁"]),
    "2603": (2, "neg", ["{n}運價下滑 遭外資賣超股價走低", "{n}獲利前景下修 法人示警"]),
    "2412": (1, "neu", ["{n}5G用戶成長 營收穩健"]),
    "1301": (1, "neg", ["{n}石化價差收斂 獲利下滑"]),
}

POS_BODY = "{n}（{t}）今日表現亮眼，管理層樂觀看好後市，外資買超，盤中股價大漲走高。"
NEG_BODY = "{n}（{t}）受利空衝擊，營運下滑遭外資賣超，獲利下修，盤中股價走低重挫。"
NEU_BODY = "{n}（{t}）今日召開法人說明會，營收維持穩健，市場關注後續展望。"


def _body(mood: str, name: str, ticker: str) -> str:
    tpl = {"pos": POS_BODY, "neg": NEG_BODY, "neu": NEU_BODY}[mood]
    return tpl.format(n=name, t=ticker)


def generate_documents() -> list[RawDocument]:
    rng = random.Random(42)
    dictionary = get_dictionary("data/tickers.csv")
    src_ids = list(SOURCES)
    docs: list[RawDocument] = []
    for d in range(DAYS):
        day = TODAY - timedelta(days=DAYS - 1 - d)
        for ticker, (base_n, mood, titles) in PROFILE.items():
            name = dictionary.get(ticker).name
            n = max(0, base_n + rng.randint(-1, 1))
            for j in range(n):
                title = titles[j % len(titles)].format(n=name)
                src = src_ids[j % len(src_ids)]
                published = datetime.combine(
                    day, time(rng.randint(8, 18), rng.randint(0, 59)), tzinfo=timezone.utc)
                body = _body(mood, name, ticker)
                docs.append(RawDocument(
                    source=src, source_type="news",
                    external_id=f"{src}-{ticker}-{day.isoformat()}-{j}",
                    url=f"https://news.example.com/{ticker}/{day.isoformat()}/{j}",
                    title=title, content=body, published_at=published,
                    raw_meta={"weight": SOURCES[src][2],
                              "simhash": simhash(title + body)},
                ))
    return docs


def main() -> None:
    init_db()
    docs = generate_documents()
    dictionary = get_dictionary("data/tickers.csv")
    with session_scope() as session:
        seed_reference(session, dictionary,
                       {sid: (n, t, w) for sid, (n, t, w) in SOURCES.items()})
        inserted = ingest_documents(session, docs, dictionary)
        updated = 0
        for d in range(DAYS):
            day = TODAY - timedelta(days=DAYS - 1 - d)
            updated += recompute_heat_for_day(session, day)
    print(f"產生新聞 {len(docs)} 篇，寫入 {inserted} 篇，"
          f"計算 {DAYS} 天溫度（共 {updated} 個股·日）。")
    print("啟動：STOCKHEAT_USE_DB=1 uvicorn stock_heat.api.main:app  →  /app/")


if __name__ == "__main__":
    main()
