# Stock Heat — 個股網路溫度系統

把分散在**新聞、論壇、社群、搜尋趨勢**上的討論熱度與情緒，量化成每檔個股每天（與盤中）的
**網路溫度分數（Heat Score, 0–100）** 與 **情緒分數（-1 ~ +1）**，協助觀察哪些個股正在「升溫」、情緒偏多還偏空。

> ⚠️ 本系統僅提供資訊指標，**不構成投資建議**。所有輸出皆附資料來源與計算依據。

## 設計文件

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
- [ ] 溫度計算
- [ ] REST API
- [ ] 前端儀表板

## 專案結構（規劃）

見 [docs/06](docs/06-API與後端服務設計.md) §2。核心 package 為 `stock_heat/`，財經新聞模組位於 `stock_heat/collectors/news/`。

## 快速開始（開發中）

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```
