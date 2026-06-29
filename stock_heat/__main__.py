"""服務進入點：``python -m stock_heat``。

於 Python 內讀取 ``PORT`` 環境變數啟動 uvicorn，避免依賴容器 CMD 的 shell 展開
（部分平台如 Railway 執行 CMD 時不經 shell，``${PORT}`` 不會被展開）。
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "stock_heat.api.main:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
