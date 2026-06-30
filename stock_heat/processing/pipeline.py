"""處理層 pipeline（docs/04 §2）。

RawDocument → 清洗 → 語言判定 → 個股辨識 → 標的層級情緒 → ProcessedDocument。

設計為可重入、無副作用：同一 RawDocument 多次處理結果一致（冪等），
便於演算法調整後對歷史資料重算（docs/04 §7）。
"""

from __future__ import annotations

import re

from ..collectors.base import RawDocument
from .dictionary import TickerDictionary, get_dictionary
from .sentiment import analyze_sentiment, analyze_ticker_sentiment
from .ticker_recognition import recognize_tickers
from .types import ProcessedDocument, TickerMention

PIPELINE_VERSION = "v0"

_CJK_RE = re.compile(r"[一-鿿]")
_WS_RE = re.compile(r"[ \t　]+")


def _clean(text: str) -> str:
    text = _WS_RE.sub(" ", text or "")
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def _detect_lang(text: str) -> str:
    return "zh" if _CJK_RE.search(text) else "other"


class ProcessingPipeline:
    def __init__(self, dictionary: TickerDictionary | None = None) -> None:
        self.dictionary = dictionary or get_dictionary()

    def _surfaces(self, ticker: str) -> list[str]:
        entry = self.dictionary.get(ticker)
        if entry is None:
            return [ticker]
        return [ticker, *entry.surface_forms]

    def process(self, raw: RawDocument) -> ProcessedDocument:
        text = _clean(f"{raw.title}\n{raw.content}")
        lang = _detect_lang(text)

        doc_sentiment = analyze_sentiment(text)

        # 股票專板（如 PTT Stock）整篇即股市語境，放寬辨識
        implicit = bool(raw.raw_meta.get("implicit_stock_context"))
        mentions: list[TickerMention] = []
        if lang == "zh":
            for rec in recognize_tickers(text, self.dictionary, implicit_context=implicit):
                t_sent = analyze_ticker_sentiment(
                    text, self._surfaces(rec.ticker), doc_fallback=doc_sentiment
                )
                mentions.append(TickerMention(
                    ticker=rec.ticker,
                    confidence=rec.confidence,
                    ticker_sentiment=t_sent,
                    positions=rec.positions,
                ))

        return ProcessedDocument(
            external_id=raw.external_id,
            source=raw.source,
            lang=lang,
            doc_sentiment=doc_sentiment,
            is_repost=False,  # 跨文件轉載判定在 dedup 階段（需 simhash 比對）
            mentions=mentions,
            pipeline_version=PIPELINE_VERSION,
        )


def process_document(
    raw: RawDocument, dictionary: TickerDictionary | None = None
) -> ProcessedDocument:
    """便捷函式：處理單篇 RawDocument。"""
    return ProcessingPipeline(dictionary).process(raw)
