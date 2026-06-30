# 後端 API 容器（FastAPI）。適用 Render / Railway / Fly 等支援 Docker 的平台。
FROM python:3.12-slim

WORKDIR /app

# 先裝相依（利用快取），再放原始碼
COPY pyproject.toml README.md ./
COPY stock_heat ./stock_heat
COPY scripts ./scripts
COPY config ./config
COPY data ./data

RUN pip install --no-cache-dir -e .

# 預設：讀資料庫、跨源全開（唯讀 API）、自動掃描真實新聞（啟動即掃、每 30 分一次）
# 若要改回合成示範資料，設 STOCKHEAT_AUTO_SCAN=（空）並 STOCKHEAT_SEED_ON_START=1
ENV STOCKHEAT_USE_DB=1 \
    STOCKHEAT_CORS_ORIGINS=* \
    STOCKHEAT_AUTO_SCAN=1 \
    STOCKHEAT_SCAN_INTERVAL=1800 \
    STOCKHEAT_SEED_ON_START=1 \
    STOCKHEAT_DATABASE_URL=sqlite:////app/data/stock_heat.db

EXPOSE 8000

# 進入點於 Python 內讀 $PORT 啟動 uvicorn（不靠 shell 展開，相容 Railway 等平台）
CMD ["python", "-m", "stock_heat"]
