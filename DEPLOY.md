# 部署指南 — 前端上 GitHub Pages + 後端另外部署

儀表板是純靜態頁，可放 GitHub Pages；但它要呼叫的 FastAPI 後端**無法**跑在 Pages 上
（Pages 只服務靜態檔），所以後端要部署到別的平台，再讓 Pages 前端指向它。

```
[GitHub Pages]  index.html + config.js  ──fetch──▶  [Render/Railway]  FastAPI /api/v1
   公開靜態前端                                          後端 API（已開 CORS）
```

> ⚠️ 兩者都會**公開**。Pages 網站公開可瀏覽；私有 repo 用 Pages 需要付費方案
> （Pro/Team）。資料為台股聲量、非敏感，但請自行確認可公開。

---

## 步驟 1 — 部署後端（擇一）

### 選項 A：Render（最簡單，有免費方案）
1. 到 <https://render.com> 用 GitHub 登入，授權存取 `stock-heat` repo。
2. New → Blueprint，選此 repo。Render 會讀根目錄的 `render.yaml` 自動建立服務。
3. 等部署完成，取得網址，例如 `https://stock-heat-api.onrender.com`。
4. 驗證：開 `https://stock-heat-api.onrender.com/api/v1/health` 應回 `{"status": ...}`。

> 免費方案閒置會休眠、磁碟重啟即清空；已設 `STOCKHEAT_SEED_ON_START=1`，
> 啟動且無資料時自動灌示範資料，確保畫面有東西。要真實資料見「步驟 4」。

### 選項 B：任何支援 Docker 的平台
根目錄已有 `Dockerfile`；建置並執行即可。平台會以 `$PORT` 指定埠。
需要的環境變數見 `render.yaml`（`STOCKHEAT_USE_DB`、`STOCKHEAT_CORS_ORIGINS`…）。

本機驗證容器：
```bash
docker build -t stock-heat .
docker run -p 8000:8000 stock-heat
# 開 http://localhost:8000/app/
```

---

## 步驟 2 — 設定 GitHub Pages 與後端網址

1. repo → Settings → **Pages** → Build and deployment → Source 選 **GitHub Actions**。
   （私有 repo 此功能需付費方案；或先將 repo 改為 public。）
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

## 步驟 4 —（選用）讓後端有真實資料

示範資料是合成的。要真實新聞溫度，在後端跑一次擷取：
- Render：Dashboard → 該服務 → **Shell**，執行 `python -m scripts.collect_once`。
- 或設定 Render **Cron Job** 定時跑 `python -m scripts.collect_once`，讓資料持續更新。
- 注意：免費方案無持久磁碟，重啟會清空；要長期保存請改用平台的 PostgreSQL，
  把 `STOCKHEAT_DATABASE_URL` 設為其連線字串（模型不變，docs/05）。

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
