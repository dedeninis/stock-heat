"""處理層輸出的資料模型（對應 docs/05 §3.3 與 §3.5）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TickerMention(BaseModel):
    """文件對單一個股的關聯，對應 ``document_ticker_mentions``。"""

    ticker: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    ticker_sentiment: float | None = Field(None, ge=-1.0, le=1.0)
    positions: list[int] = Field(default_factory=list, description="命中起始位置")


class ProcessedDocument(BaseModel):
    """處理後的文件，對應 ``processed_documents`` + 其 mentions。"""

    external_id: str
    source: str
    lang: str = "zh"
    doc_sentiment: float = Field(0.0, ge=-1.0, le=1.0)
    is_repost: bool = False
    mentions: list[TickerMention] = Field(default_factory=list)
    pipeline_version: str = "v0"
