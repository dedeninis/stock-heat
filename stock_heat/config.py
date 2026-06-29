"""應用設定（docs/06 §4）。

以環境變數 ``STOCKHEAT_*`` 覆寫；未設定時使用 SQLite 與專案內預設路徑，
讓系統可離線、零外部服務啟動。
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STOCKHEAT_", extra="ignore")

    database_url: str = "sqlite:///stock_heat.db"
    redis_url: str = "redis://localhost:6379/0"
    sources_path: str = "config/sources.yaml"
    scoring_path: str = "config/scoring.yaml"
    tickers_path: str = "data/tickers.csv"
    request_timeout: float = 10.0
    user_agent: str = "StockHeatBot/0.1 (+contact)"
