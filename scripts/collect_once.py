"""一次性：從真實新聞來源抓取 → 處理 → 計算溫度 → 寫入資料庫。

適合手動實測（不啟動常駐排程器）。會實際連外抓取 config/sources.yaml
中啟用的來源，低量、可識別 UA；請先確認各站 robots 與授權合規。

用法：
    python -m scripts.collect_once
    STOCKHEAT_DATABASE_URL=postgresql+psycopg://... python -m scripts.collect_once
    python -m scripts.collect_once --day 2026-06-29   # 指定重算日期（預設今日 UTC）
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

from stock_heat.db import models as m
from stock_heat.db.engine import database_url, session_scope
from stock_heat.db.repository import SqlHeatStore
from stock_heat.jobs import bootstrap, collect_and_ingest, recompute_today


def main() -> None:
    parser = argparse.ArgumentParser(description="一次性真實擷取 + 溫度計算")
    parser.add_argument("--day", help="重算日期 YYYY-MM-DD（預設今日 UTC）")
    parser.add_argument("--top", type=int, default=15, help="列印溫度榜前 N 名")
    args = parser.parse_args()

    target: date = (datetime.strptime(args.day, "%Y-%m-%d").date()
                    if args.day else datetime.now(timezone.utc).date())

    url = database_url()
    print(f"資料庫：{url}")
    bootstrap()
    print("從真實來源擷取中…（config/sources.yaml 啟用的來源）")
    inserted = collect_and_ingest()
    tickers = recompute_today(day=target)

    with session_scope() as s:
        raw = s.query(m.RawDocument).count()
        mentions = s.query(m.DocumentTickerMention).count()
    print(f"\n本輪新寫入 {inserted} 篇；DB 累計 raw={raw} mentions={mentions}；"
          f"{target} 計算 {tickers} 檔個股")

    store = SqlHeatStore()
    recs = sorted(store.all_records(),
                  key=lambda r: (r.latest.heat_score if r.latest else 0), reverse=True)
    print(f"\n=== 網路溫度榜（top {args.top}）===")
    for r in recs[:args.top]:
        p = r.latest
        if p is None:
            continue
        head = r.documents[0].title[:36] if r.documents else ""
        print(f"  {r.ticker} {r.name:6} 溫度={p.heat_score:5.1f} "
              f"情緒={p.sentiment:+.2f} 聲量={p.volume}  {head}")

    print("\n啟動 API 檢視：")
    print("  (PowerShell) $env:STOCKHEAT_USE_DB=1; uvicorn stock_heat.api.main:app")
    print("  → 儀表板 http://127.0.0.1:8000/app/")


if __name__ == "__main__":
    main()
