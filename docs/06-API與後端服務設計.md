# 06 — API 與後端服務設計

> 個股網路溫度系統（Stock Heat）— 設計文件 6/7
> 版本：v0.1 ｜ 最後更新：2026-06-29
> 後端：FastAPI + Pydantic v2；資料層：SQLAlchemy 2.0 async + asyncpg。

## 1. 服務切分

| 服務 | 職責 | 執行型態 |
|------|------|----------|
| `api` | 對外 REST API | 常駐（uvicorn） |
| `scheduler` | 觸發各 Collector | 常駐（APScheduler） |
| `worker` | 處理層 pipeline + 溫度計算 | 常駐（消費佇列） |

三者共用同一 `stock_heat` package（models / config / db），以不同 entrypoint 啟動。

## 2. 專案結構

```
stock_heat/
  __init__.py
  config.py                # pydantic-settings
  db.py                    # async engine / session
  models/                  # SQLAlchemy ORM + Pydantic schemas
  collectors/
    base.py                # BaseCollector, RawDocument
    registry.py
    news/                  # ★ 財經新聞模組
      __init__.py
      collector.py
      sources.py           # 載入 config/sources.yaml
      parser.py            # RSS / HTML 解析 + fallback
      dedup.py             # URL 正規化 + SimHash
  processing/
    pipeline.py            # clean→dedup→tokenize→ner→sentiment
    ticker_recognition.py
    sentiment.py
  scoring/
    heat.py                # 溫度/情緒/velocity
  api/
    main.py                # FastAPI app
    routers/
      rankings.py
      tickers.py
      health.py
    deps.py
scripts/
  init_db.py
  import_tickers.py
  recompute.py
tests/
config/
  sources.yaml
  scoring.yaml
data/
  tickers.csv
```

## 3. REST API 規格

Base path：`/api/v1`。回應一律 JSON；錯誤用 `{ "error": { "code", "message" } }`。

### 3.1 榜單

`GET /api/v1/rankings/heat`
查當日溫度榜。
| Query | 預設 | 說明 |
|-------|------|------|
| date | 今日(TPE) | 查詢日期 |
| order | desc | desc=升溫榜 / asc=降溫榜 |
| limit | 50 | |
| sentiment | all | all/positive/negative |

回應：
```json
{
  "date": "2026-06-29",
  "items": [
    {"rank":1,"ticker":"2330","name":"台積電","heat_score":92.3,
     "sentiment":0.41,"heat_velocity":1.85,"volume":128}
  ]
}
```

`GET /api/v1/rankings/surging` — 異常升溫榜（來自 `heat_events`）。

### 3.2 個股

`GET /api/v1/tickers/{ticker}` — 個股當前摘要（最新溫度、情緒、近 7 日趨勢、熱詞）。

`GET /api/v1/tickers/{ticker}/timeseries`
| Query | 說明 |
|-------|------|
| from / to | 區間 |
| granularity | daily/intraday |

回應：時序陣列（ts, heat_score, sentiment, volume, heat_velocity）。

`GET /api/v1/tickers/{ticker}/documents`
近期關聯文件（標題、來源、URL、發布時間、ticker_sentiment、confidence）。**只回傳標題與來源連結，不全文轉載。**

### 3.3 搜尋與健康

`GET /api/v1/search?q=台積` — 以名稱/別名/代號找個股。
`GET /api/v1/health` — 服務健康（DB/Redis/各來源 last_success_at）。
`GET /metrics` — Prometheus 指標。

### 3.4 文件
FastAPI 自動產生 OpenAPI：`/docs`、`/openapi.json`。

## 4. 設定（config.py 重點）

```python
class Settings(BaseSettings):
    database_url: str          # postgresql+asyncpg://...
    redis_url: str
    sources_path: str = "config/sources.yaml"
    scoring_path: str = "config/scoring.yaml"
    request_timeout: float = 10.0
    user_agent: str = "StockHeatBot/0.1 (+contact)"
    model_config = SettingsConfigDict(env_prefix="STOCKHEAT_")
```

## 5. 背景工作流程

### 5.1 Scheduler
```python
for source in enabled_sources():
    scheduler.add_job(run_collector, "interval",
                      seconds=source.interval_sec, args=[source.id])
scheduler.add_job(compute_intraday_heat, "interval", minutes=15)
scheduler.add_job(compute_daily_heat, "cron", hour=14, minute=30)  # 收盤後(TPE)
```

### 5.2 Worker（消費佇列）
```python
async for raw in consume("ingest.raw"):
    processed = pipeline.process(raw)   # clean→dedup→ner→sentiment
    await save(processed)
```

## 6. 錯誤處理與韌性

- HTTP client 統一逾時、重試（tenacity，指數退避）。
- Collector 單篇失敗不影響整輪；整輪結果寫 `collector_runs`。
- DB 寫入用 upsert（`ON CONFLICT`）保證冪等，支援重跑。
- 佇列消費以 consumer group + ack，失敗訊息進 dead-letter。

## 7. 安全

- 對外 API：MVP 唯讀、可加 API key（header `X-API-Key`）。
- 不暴露原始全文端點；速率限制（slowapi）。
- Secrets 走環境變數，不入庫不入 repo。

## 8. 測試

- 單元：parser（餵固定 HTML/RSS fixture）、dedup（SimHash）、ticker_recognition、heat 公式。
- 整合：以 SQLite/臨時 PG + 假佇列跑 end-to-end 一篇新聞 → 溫度。
