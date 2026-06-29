"""擷取器共同介面與資料模型。

所有來源（新聞、論壇、社群…）的 Collector 都實作 ``BaseCollector``，
產出統一的 ``RawDocument``，讓核心處理與計算邏輯與來源解耦。

對應設計文件 docs/03 §3。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RawDocument(BaseModel):
    """單篇原始內容，對應資料表 ``raw_documents``（docs/05 §3.2）。"""

    source: str = Field(..., description="來源代號，如 news.cnyes")
    source_type: str = Field(..., description="news | forum | trends | social")
    external_id: str = Field(..., description="來源內唯一 id，通常為正規化 URL")
    url: str
    title: str
    content: str = Field("", description="純文字內文")
    author: str | None = None
    published_at: datetime | None = Field(None, description="來源發布時間（UTC）")
    content_quality: str = Field("full", description="full | partial")
    raw_meta: dict = Field(default_factory=dict)


class CollectorRunResult(BaseModel):
    """單輪執行的統計，對應 ``collector_runs``（docs/05 §3.8）。"""

    source: str
    discovered: int = 0
    fetched: int = 0
    errors: int = 0
    documents: list[RawDocument] = Field(default_factory=list)

    @property
    def status(self) -> str:
        if self.errors and not self.fetched:
            return "failed"
        if self.errors:
            return "partial"
        return "ok"


class BaseCollector(ABC):
    """擷取器抽象基底。

    子類別須實作 :meth:`discover`（找出本輪要抓的 URL）與
    :meth:`fetch`（抓單篇並解析為 ``RawDocument``）。
    :meth:`run` 提供共同的逐篇執行與錯誤隔離。
    """

    source: str
    source_type: str
    default_interval: int = 300

    @abstractmethod
    def discover(self) -> list[str]:
        """回傳本輪要抓的文章 URL（已過濾掉看過的）。"""

    @abstractmethod
    def fetch(self, url: str) -> RawDocument:
        """抓取單篇並解析為 ``RawDocument``。"""

    def run(self) -> CollectorRunResult:
        """執行一輪：discover → 逐篇 fetch，單篇失敗不影響整輪。"""
        result = CollectorRunResult(source=self.source)
        try:
            urls = self.discover()
        except Exception:  # noqa: BLE001 — discover 失敗整輪結束
            logger.exception("[%s] discover failed", self.source)
            result.errors += 1
            return result

        result.discovered = len(urls)
        for url in urls:
            try:
                doc = self.fetch(url)
                result.documents.append(doc)
                result.fetched += 1
            except Exception:  # noqa: BLE001 — 單篇隔離
                logger.warning("[%s] fetch failed: %s", self.source, url, exc_info=True)
                result.errors += 1
        return result

    def iter_documents(self) -> Iterator[RawDocument]:
        yield from self.run().documents
