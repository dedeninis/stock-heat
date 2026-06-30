# 部署指南 — 前端上 GitHub Pages + 後端另外部署

儀表板是純靜態頁，可放 GitHub Pages；但它要呼叫的 FastAPI 後端**無法**跑在 Pages 上
（Pages 只服務靜態檔），所以後端要部署到別的平台，再讓 Pages 前端指向它。

```
[GitHub Pages]  index.html + config.js  ──fetch──▶  [Railway]  FastAPI /api/v1
   公開靜態前端                                       後端 API（已開 CORS）
```

> ⚠️ Pages 網站與後端 API **都會公開可存取**。資料為台股聲量、非敏感，但請自行確認可公開。
> （repo 已設為 public，故 Pages 免付費即可用。）

---

## 步驟 1 — 部署後端到 Railway

1. 到 <https://railway.app> 用 GitHub 登入，授權存取 `stock-heat` repo。
2. **New Project → Deploy from GitHub repo →** 選 `stock-heat`。
   Railway 會自動偵測根目錄 `Dockerfile`（並讀 `railway.toml` 的健康檢查設定）開始建置。
3. 建置完成後，到該服務 **Settings → Networking → Generate Domain**，
   取得公開網址，例如 `https://stock-heat-production.up.railway.app`。
4. 驗證：開 `https://<你的網址>/api/v1/health` 應回 `{"status": ...}`，
   或直接看 `https://<你的網址>/app/`（後端自帶的儀表板，同源版）。

環境變數：`Dockerfile` 已內建合理預設（`STOCKHEAT_USE_DB=1`、`STOCKHEAT_SEED_ON_START=1`、
`STOCKHEAT_CORS_ORIGINS=*`），通常不必另設。要收緊 CORS，可在 Railway 的
**Variables** 把 `STOCKHEAT_CORS_ORIGINS` 設為 `https://<你的帳號>.github.io`。

> Railway 免費額度用量計費；容器檔案系統重啟即清空，已設 `STOCKHEAT_SEED_ON_START=1`
> 讓畫面有示範資料。要真實／持久資料見「步驟 4」。

### 本機先驗證容器（選用）
```bash
docker build -t stock-heat .
docker run -p 8000:8000 stock-heat
# 開 http://localhost:8000/app/
```

---

## 步驟 2 — 設定 GitHub Pages 與後端網址

1. repo → Settings → **Pages** → Build and deployment → Source 選 **GitHub Actions**。
   （repo 已是 public，免付費即可用。）
2. repo → Settings → Secrets and variables → **Actions** → **Variables** → New repository variable：
   - Name：`API_BASE`
   - Value：步驟 1 的後端網址（例 `https://stock-heat-api.onrender.com`，**結尾不要斜線**）

---

## 步驟 3 — 發布前端

repo → Actions → **Deploy dashboard to Pages** → **Run workflow**。
完成後 Pages 網址通常是 `https://<你的帳號>.github.io/stock-heat/`。

工作流會把 `stock_heat/api/static/index.html` 連同一份注入 `API_BASE` 的 `config.js`
發佈到 Pages；前端即會去打你的後端 API。

---

## 步驟 4 — 真實新聞（預設已自動掃描）

後端**預設開啟自動掃描**（`Dockerfile` 內 `STOCKHEAT_AUTO_SCAN=1`）：
- 啟動即先掃一次、之後每 30 分鐘（`STOCKHEAT_SCAN_INTERVAL` 秒）自動擷取
  鉅亨網/中央社/自由時報真新聞 → 處理 → 算溫度 → 寫入同一 DB。
- 擷取以**子行程**執行（不阻塞 API、不佔事件迴圈），web 服務全程可回應。
- 部署後首輪掃描約需數十秒；完成前儀表板顯示「無資料」，完成後即為真實榜單。

調整：
- 改頻率：Railway **Variables** 設 `STOCKHEAT_SCAN_INTERVAL`（秒）。
- 關閉自動掃描、改回合成示範資料：設 `STOCKHEAT_AUTO_SCAN=`（空）。
- 手動立即掃一次：該服務 **⋮ → Shell** 執行 `python -m scripts.collect_once`。

Google Trends 搜尋熱度（選配）：
- 設 `STOCKHEAT_AUTO_TRENDS=1` 並安裝選配相依 `pip install pytrends` 後，每輪會查當日
  熱門股的搜尋興趣，計入溫度並顯示於「搜尋趨勢」組成。
- ⚠️ Google Trends 對**資料中心 IP（含 Railway）限流兇**，雲端常 429 → 預設關閉；
  本機或住宅 IP 可正常運作（已驗證）。失敗時自動略過，不影響新聞/社群。

持久保存：容器重啟會清空 SQLite（重啟後自動掃描會再補上）。要長期累積，
可掛 Railway **Volume** 到 `/app/data`，或新增 **PostgreSQL** 並把
`STOCKHEAT_DATABASE_URL` 設為其連線字串（模型不變，docs/05）。

---

## 疑難排解

| 症狀 | 處理 |
|------|------|
| Pages 開了但榜單載入失敗 | `API_BASE` 變數沒設或設錯；重設後重跑 workflow |
| 瀏覽器 console 顯示 CORS 錯誤 | 後端 `STOCKHEAT_CORS_ORIGINS` 設為 `*` 或你的 Pages 網址 |
| 後端 `/health` 連不上 | 服務還在喚醒（免費方案冷啟動）或部署失敗，看平台日誌 |
| 榜單是固定示範股 | 後端未跑 `collect_once`，顯示的是 seed 示範資料 |
| Actions 部署步驟失敗 | Pages 未設為「GitHub Actions」來源，或私有 repo 無 Pages 權限 |

本機開發不受影響：`config.js` 預設空字串、走相對路徑，
`uvicorn stock_heat.api.main:app` → `http://127.0.0.1:8000/app/` 照常運作。
