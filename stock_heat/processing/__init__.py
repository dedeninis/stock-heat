"""處理層：清洗 → 個股辨識 → 情緒分析（docs/04 §2–4）。"""

from .pipeline import ProcessingPipeline, process_document
from .types import ProcessedDocument, TickerMention

__all__ = [
    "ProcessingPipeline",
    "process_document",
    "ProcessedDocument",
    "TickerMention",
]
