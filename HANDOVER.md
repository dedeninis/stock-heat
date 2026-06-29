# 交接與架構總覽 — Stock Heat（個股網路溫度系統）

> 一頁掌握全貌。深入細節見 [`docs/01`~`07`](docs/)。
> 最後更新：2026-06-29

## 1. 這是什麼

把分散在網路（新聞為主）上的個股討論，量化成每檔股票每天的 **網路溫度（Heat Score 0–100）**
與 **情緒（-1 ~ +1）**，輸出升溫榜、個股趨勢與相關新聞。**僅供資訊，不構成投資建議。**

## 2. 目前狀態

MVP 與基礎工程化**全部完成**，私有 repo [dedeninis/stock-heat](https://github.com/dedeninis/stock-heat)，9 個 commit，81 項測試，CI 綠燈。

| 模組 | 狀態 | 位置 |
|------|------|------|
| 財經新聞擷取 | ✅ | `stock_heat/collectors/news/` |
| 處理層（個股辨識 + 情緒） | ✅ | `stock_heat/processing/` |
| 溫度計算（Heat / 聚合 / 升溫率） | ✅ | `stock_heat/scoring/` |
| 資料庫（SQLite，可切 PostgreSQL） | ✅ | `stock_heat/db/` |
| REST API + 單檔儀表板 | ✅ | `stock_heat/api/` |
| 排程自動化（APScheduler） | ✅ | `stock_heat/jobs.py`、`scheduler.py` |
| CI（ruff + pytest，3.11/3.12） | ✅ | `.github/workflows/ci.yml` |

## 3. 資料流（一句話）

```
RSS/新聞頁 → [collectors] RawDocument → [processing] 清洗+個股辨識+情緒 → DB(raw/processed/mentions)
          → [scoring] 視窗聚合 Heat/Sentiment/Velocity → DB(ticker_heat_timeseries/heat_events)
          → [api] REST → [儀表板] 榜單 / 個股詳情
```
排程器（`scheduler.py`）定時觸發前兩段（擷取）與聚合段（重算）。

## 4. 怎麼跑起來

```bash
pip install -e ".[dev]"

# A) 純測試 / 開發
pytest                                   # 81 項
uvicorn stock_heat.api.main:app          # 記憶體示範資料，開 /app/ 看儀表板

# B) 真實資料庫（SQLite）
python -m scripts.seed_db                # 用真實 pipeline 灌 12 天示範資料
STOCKHEAT_USE_DB=1 uvicorn stock_heat.api.main:app   # /app/ 看累積資料

# C) 自動運轉
python -m stock_heat.scheduler           # 定時擷取 + 重算
```

主要進入點：`stock_heat.api.main:app`（API/UI）、`stock_heat.scheduler`（排程）、`scripts.seed_db`（種子）。

## 5. 設定與環境變數

| 項目 | 預設 | 說明 |
|------|------|------|
| `STOCKHEAT_DATABASE_URL` | `sqlite:///stock_heat.db` | 改成 PostgreSQL 連線字串即切換 |
| `STOCKHEAT_USE_DB` | （未設） | 設為 `1` 讓 API 讀 DB 而非記憶體示範資料 |
| `config/sources.yaml` | — | 新聞來源（RSS/selector/權重/頻率） |
| `config/scoring.yaml` | — | 溫度參數（半衰期、α、百分位、信心門檻…） |
| `data/tickers.csv` | — | 個股字典（代號/名稱/別名/產業） |

## 6. 關鍵設計決策與「接縫」

- **三層分離（raw / processed / derived）**：原文與衍生結果分存，調參後可對歷史**重算**不需重爬（`recompute_heat_for_day`）。
- **`HeatStore` 介面**（`api/store.py`）：記憶體版與 DB 版（`db/repository.py`）回傳相同結構，**API 路由零改動即可切換**。
- **可注入 fetcher**（`collectors/news`、`jobs`）：HTTP 抓取與 seen 判定皆可注入，全鏈路**離線可測**。
- **情緒 v0 為詞典規則**（`processing/sentiment.py`）：可解釋、可測；介面固定，未來換 FinBERT-zh 不動上層。
- **冪等寫入**：以 `source + external_id` 去重，排程重跑安全。
- **SQLite→PostgreSQL 平滑路徑**：模型不變，改連線字串 + 把 `ticker_heat_timeseries` 轉 hypertable。

## 7. 已知限制 / 待辦（皆非 MVP 必需）

1. **真實來源已接線並驗證**（2026-06-29）：中央社、自由時報財經、鉅亨網的 RSS/selector 已對真站台驗證可用，真實 collect→處理→溫度 跑通（見 `tests/test_live_sources.py`，需 `STOCKHEAT_LIVE_TEST=1`）。經濟日報（udn）內文為 JS 渲染、靜態抓取不完整，已停用，待改 headless。上線前仍請再確認各站 robots 與授權。
2. **`is_repost` 永遠 False**：轉載判定需跨文件 SimHash 比對（SimHash 已算好存於 `raw_documents.simhash`，待接）。
3. **綱要用 `create_all`**：正式環境應改 Alembic migration（docs/05 §6）。
4. **個股字典僅 15 檔示範**：上線需匯入完整上市櫃清單。
5. **情緒/辨識準確度**：v0 規則打底，未做領域模型與大規模評估。

## 8. 測試與品質

- `pytest`：81 項，全離線（SQLite + 假 fetcher），涵蓋去重、解析、辨識、情緒、溫度、API、DB、排程。
- `ruff check .`：lint 乾淨。
- CI：每次 push / PR 在 Python 3.11 與 3.12 跑 ruff + pytest。

## 9. 文件地圖

`docs/01` 需求 ｜ `02` 架構 ｜ `03` 資料來源與擷取 ｜ `04` 溫度演算法 ｜ `05` 資料庫 ｜ `06` API/後端 ｜ `07` 前端與部署維運。
