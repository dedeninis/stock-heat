// 儀表板 API 基底設定。
// 同源服務（uvicorn 提供 /app/）時留空字串即可，走相對路徑。
// 跨源部署（如 GitHub Pages 前端 + 另外部署的後端）時，
// 由 Pages 工作流以後端網址覆寫此檔，例如：
//   window.STOCK_HEAT_API_BASE = "https://stock-heat-api.onrender.com";
window.STOCK_HEAT_API_BASE = window.STOCK_HEAT_API_BASE || "";
