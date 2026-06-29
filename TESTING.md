# 實際測試指南

親手把系統跑起來、看到真實結果的步驟。指令以 **PowerShell**（Windows）為主，
括號內附 **bash** 寫法。前置只需做一次。

> 設環境變數：PowerShell 用 `$env:NAME="value"`，bash 用 `export NAME=value`。

## 0. 前置（一次）

```powershell
cd "D:\Claude Code\Projects\stock-heat"
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # bash: source .venv/bin/activate
pip install -e ".[dev]"
```

## 1. 自動化測試（離線，最快確認沒壞）

```powershell
pytest -q          # 預期 84 passed, 2 skipped（2 個 live 測試預設略過）
ruff check .       # lint
```

全程離線、用 SQLite + 假 fetcher，不碰真實 DB 或網路，可隨時放心跑。

## 2. 真實來源測試（會連外，低量）

驗證中央社／自由時報／鉅亨網的 RSS 與內文 selector 真的能抓：

```powershell
$env:STOCKHEAT_LIVE_TEST=1
pytest tests/test_live_sources.py -v
Remove-Item Env:\STOCKHEAT_LIVE_TEST
```
bash：`STOCKHEAT_LIVE_TEST=1 pytest tests/test_live_sources.py -v`

## 3. 跑出真實溫度榜（一行）

實際連外抓今天的財經新聞 → 處理 → 算溫度 → 寫入 `stock_heat.db`：

```powershell
python -m scripts.collect_once
```
會印出本輪寫入篇數與**真實新聞算出的溫度榜**。常用選項：
- `--day 2026-06-29`　指定重算日期（預設今日 UTC）
- `--top 20`　　　　　列印前 N 名

> 榜單品質取決於當天有沒有新聞（視窗 48h），假日新聞少屬正常。

## 4. 看儀表板與 API

接續步驟 3 的同一個資料庫啟動 API（**務必設 `STOCKHEAT_USE_DB=1`，否則回的是記憶體示範資料**）：

```powershell
$env:STOCKHEAT_USE_DB=1
uvicorn stock_heat.api.main:app
```

- 儀表板：<http://127.0.0.1:8000/app/>
- API 文件（可直接試打）：<http://127.0.0.1:8000/docs>

只想先看畫面、不連外，可改用合成資料：`python -m scripts.seed_db` 再啟動 API。

## 5. 直接打 API（另開終端機）

```powershell
curl "http://127.0.0.1:8000/api/v1/rankings/heat"
curl "http://127.0.0.1:8000/api/v1/rankings/surging"
curl "http://127.0.0.1:8000/api/v1/tickers/2330"
curl "http://127.0.0.1:8000/api/v1/tickers/2330/timeseries"
curl "http://127.0.0.1:8000/api/v1/search?q=台積"
curl "http://127.0.0.1:8000/api/v1/health"
```

## 6. 持續自動運轉（排程器）

讓系統自己定時抓取與重算（兩個終端機）：

```powershell
# 終端 1
python -m stock_heat.scheduler

# 終端 2
$env:STOCKHEAT_USE_DB=1
uvicorn stock_heat.api.main:app
```

## 7. 驗證資料真的進了資料庫

```powershell
python -c "from stock_heat.db.engine import session_scope; from stock_heat.db import models as m; s=session_scope().__enter__(); print('raw',s.query(m.RawDocument).count(),'mentions',s.query(m.DocumentTickerMention).count(),'heat',s.query(m.TickerHeatTimeseries).count())"
```

## 常見問題

| 症狀 | 處理 |
|------|------|
| 儀表板顯示固定示範股 | API 沒設 `STOCKHEAT_USE_DB=1`，回的是記憶體資料 |
| 溫度榜很空 | 當天新聞少，或重算日期不對；試 `--day` 指定有新聞的日期 |
| 抓取某來源 0 篇 | 該站改版／RSS 變動；查 `config/sources.yaml` 與 `collector_runs` 表 |
| 某新聞抓不到內文 | selector 失效會自動退場到通用抽取；經濟日報為 JS 渲染、預設停用 |
| 個股辨識不到 | 二字名需鄰近股市上下文才足額計分（精準換召回，見 HANDOVER） |

## 合規提醒

`collect_once` 與排程器會實際連外抓公開 RSS 與文章頁，低量、可識別 UA。
**正式持續運轉前，請逐站確認 robots.txt 與內容授權。**
