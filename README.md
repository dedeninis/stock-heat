# Stock Heat — 個股網路溫度系統

[![CI](https://github.com/dedeninis/stock-heat/actions/workflows/ci.yml/badge.svg)](https://github.com/dedeninis/stock-heat/actions/workflows/ci.yml)

把分散在**新聞、論壇、社群、搜尋趨勢**上的討論熱度與情緒，量化成每檔個股每天（與盤中）的
**網路溫度分數（Heat Score, 0–100）** 與 **情緒分數（-1 ~ +1）**，協助觀察哪些個股正在「升溫」、情緒偏多還偏空。

> ⚠️ 本系統僅提供資訊指標，**不構成投資建議**。所有輸出皆附資料來源與計算依據。

## 文件

- **[交接與架構總覽（HANDOVER.md）](HANDOVER.md)** — 一頁掌握全貌、怎麼跑、設計接縫與待辦。
- **[實際測試指南（TESTING.md）](TESTING.md)** — 親手把系統跑起來、看到真實溫度榜的步驟。

### 設計文件

| # | 文件 |
|---|------|
| 01 | [系統概述與需求規格](docs/01-系統概述與需求規格.md) |
| 02 | [系統架構設計](docs/02-系統架構設計.md) |
| 03 | [資料來源與擷取設計](docs/03-資料來源與擷取設計.md)（含財經新聞模組規格） |
| 04 | [溫度演算法設計](docs/04-溫度演算法設計.md) |
| 05 | [資料庫設計](docs/05-資料庫設計.md) |
| 06 | [API 與後端服務設計](docs/06-API與後端服務設計.md) |
| 07 | [前端儀表板與部署維運](docs/07-前端儀表板與部署維運.md) |

## 技術棧

Python 3.11 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL + TimescaleDB · Redis · APScheduler · Next.js（前端）

## 開發狀態

- [x] 7 份系統設計文件
- [x] 財經新聞擷取模組（`stock_heat/collectors/news/`，含測試）
- [x] 處理層：個股辨識 + 情緒分析（`stock_heat/processing/`，含測試）
- [x] 溫度計算：Heat Score / 情緒聚合 / 升溫率與異常（`stock_heat/scoring/`，含測試）
- [x] REST API：FastAPI 榜單 / 個股 / 搜尋 / 健康（`stock_heat/api/`，含測試）
- [x] 前端儀表板：單檔 HTML/JS（`stock_heat/api/static/`，服務於 `/app`）
- [x] 資料庫落地：SQLAlchemy + SQLite（`stock_heat/db/`，含 ingestion 與 DB-backed store）
- [x] 排程自動化：APScheduler 定時擷取 + 重算（`stock_heat/jobs.py`、`stock_heat/scheduler.py`）

## 專案結構（規劃）

見 [docs/06](docs/06-API與後端服務設計.md) §2。核心 package 為 `stock_heat/`，財經新聞模組位於 `stock_heat/collectors/news/`。

## 快速開始（開發中）

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest

# 啟動 API（MVP 階段以記憶體示範資料供查）
uvicorn stock_heat.api.main:app --reload
# 互動式文件： http://127.0.0.1:8000/docs
```

## API 端點（v1）

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/rankings/heat` | 溫度榜（`date` / `order` / `limit` / `sentiment`） |
| GET | `/api/v1/rankings/surging` | 異常升溫榜 |
| GET | `/api/v1/tickers/{ticker}` | 個股摘要（含近 7 日趨勢） |
| GET | `/api/v1/tickers/{ticker}/timeseries` | 溫度時序（`from` / `to` / `granularity`） |
| GET | `/api/v1/tickers/{ticker}/documents` | 關聯新聞（只給標題與來源連結） |
| GET | `/api/v1/search?q=` | 以名稱／別名／代號搜尋個股 |
| GET | `/api/v1/health` | 服務健康 |

> 預設以記憶體示範資料（`stock_heat/api/seed.py`）。設定 `STOCKHEAT_USE_DB=1`
> 或 `STOCKHEAT_DATABASE_URL` 即改用資料庫；`HeatStore` 介面已抽象化，路由不需改動。

## 資料庫（SQLite 優先）

```bash
# 1) 以真實 pipeline（擷取→處理→溫度）產生並寫入示範資料庫
python -m scripts.seed_db

# 2) 啟動 API，改讀資料庫
STOCKHEAT_USE_DB=1 uvicorn stock_heat.api.main:app   # 然後開 /app/
```

- 綱要：`stock_heat/db/models.py`（docs/05 的 8 張表），MVP 以 `init_db` 的 `create_all`
  建立；正式環境改用 Alembic migration。
- 寫入：`stock_heat/db/ingest.py`（`ingest_documents` 冪等寫入 raw/processed/mentions；
  `recompute_heat_for_day` 重算每日溫度與升溫事件）。
- 讀取：`stock_heat/db/repository.py` 的 `SqlHeatStore`，回傳與記憶體 store 相同的資料結構。
- 切換 PostgreSQL + TimescaleDB：改 `STOCKHEAT_DATABASE_URL`，並把
  `ticker_heat_timeseries` 轉為 hypertable，模型不變。

## 排程自動化

讓系統自動運轉：依各來源 `interval` 定時擷取、每 15 分鐘盤中重算、收盤後日線重算。

```bash
python -m stock_heat.scheduler          # 啟動排程器（會持續執行）
```

- 任務函式：`stock_heat/jobs.py`
  - `collect_source` / `collect_and_ingest`：以 DB 既有 `external_id` 去重，寫入並記錄 `collector_runs`。
  - `recompute_today`：重算當日各個股溫度與升溫事件。
- 排程器：`stock_heat/scheduler.py`（APScheduler），`build_scheduler` 註冊三類任務。
- 三個進程可分開部署：`api`（uvicorn）、`scheduler`（本檔）、未來的 `worker`（佇列消費）。
