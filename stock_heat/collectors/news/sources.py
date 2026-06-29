"""新聞來源設定載入（docs/03 §4.2）。

從 ``config/sources.yaml`` 的 ``news`` 區段載入來源清單，
缺欄位給合理預設，讓 selector / RSS 等以「可設定」為原則，避免寫死。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class NewsSource(BaseModel):
    id: str
    name: str
    rss: str | None = None
    list_url: str | None = None
    article_selector: str | None = Field(
        None, description="內文容器 CSS selector；缺省時退場用通用抽取"
    )
    weight: float = 1.0
    interval: int = 300
    enabled: bool = True
    max_per_run: int = 50

    def model_post_init(self, _ctx: object) -> None:
        if not self.rss and not self.list_url:
            raise ValueError(f"news source {self.id!r} 需提供 rss 或 list_url 其一")


def load_news_sources(config_path: str | Path = "config/sources.yaml") -> list[NewsSource]:
    """讀取設定檔並回傳啟用中的新聞來源。"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"找不到來源設定檔：{path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_sources = data.get("news", []) or []
    sources = [NewsSource(**item) for item in raw_sources]
    return [s for s in sources if s.enabled]
