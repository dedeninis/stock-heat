"""個股辨識與消歧（docs/04 §3）。

規則（分數可疊加）：
1. 代號精確匹配（4 碼），鄰近有股市上下文 → 0.6，否則 0.4。
2. 正式名匹配 → 0.5。
3. 別名/簡稱匹配 → 0.3。
4. 消歧：以「最長匹配優先」處理重疊（例：「中華電信」整段歸 2412，
   不會讓其中的「中華」誤判到 2204）。
5. 門檻：confidence ≥ 0.5 才建立 mention。

辨識本身不依賴外部斷詞器，採字典比對，便於離線測試與穩定性。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .dictionary import TickerDictionary, get_dictionary

# 股市上下文詞：用於確認代號（非一般數字）與短名稱（非同名常用詞）確為個股
_STOCK_CONTEXT = (
    "股", "個股", "代號", "股價", "收盤", "開盤", "盤中", "漲", "跌",
    "漲停", "跌停", "大漲", "大跌", "走高", "走低", "重挫", "勁揚", "飆",
    "買", "賣", "買超", "賣超", "投資", "持股", "成交", "目標價", "法說",
    "外資", "投信", "自營", "法人", "上市", "上櫃", "掛牌", "營收", "獲利",
    "財報", "除權", "除息", "董事會", "類股", "概念股", "權值", "盤勢",
)
_CONTEXT_WINDOW = 14
# 同名常用詞風險高的短名稱長度門檻：≤ 此值的名稱／別名需有股市上下文才足額計分
_SHORT_NAME_LEN = 2
_SHORT_NAME_DISCOUNT = 0.6

_SCORE_CODE_WITH_CONTEXT = 0.6
_SCORE_CODE_BARE = 0.4
_SCORE_NAME = 0.5
_SCORE_ALIAS = 0.3

_CONFIDENCE_THRESHOLD = 0.5
_CODE_RE = re.compile(r"\d{4}")


@dataclass
class _Match:
    ticker: str
    start: int
    end: int
    score: float
    kind: str  # code | name | alias

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class RecognizedTicker:
    ticker: str
    confidence: float
    positions: list[int]


def _has_stock_context(text: str, start: int, end: int) -> bool:
    lo = max(0, start - _CONTEXT_WINDOW)
    hi = min(len(text), end + _CONTEXT_WINDOW)
    window = text[lo:hi]
    return any(c in window for c in _STOCK_CONTEXT)


def _collect_matches(text: str, dictionary: TickerDictionary) -> list[_Match]:
    matches: list[_Match] = []

    # 代號：只認字典裡有的 4 碼，且避免落在更長數字串中（如價格 12330）
    for m in _CODE_RE.finditer(text):
        code = m.group()
        entry = dictionary.get(code)
        if entry is None:
            continue
        before = text[m.start() - 1] if m.start() > 0 else ""
        after = text[m.end()] if m.end() < len(text) else ""
        if before.isdigit() or after.isdigit():
            continue
        score = (_SCORE_CODE_WITH_CONTEXT
                 if _has_stock_context(text, m.start(), m.end())
                 else _SCORE_CODE_BARE)
        matches.append(_Match(code, m.start(), m.end(), score, "code"))

    # 名稱與別名：逐一掃描所有出現位置
    for entry in dictionary.all():
        surfaces = [(entry.name, _SCORE_NAME, "name")]
        surfaces += [(a, _SCORE_ALIAS, "alias") for a in entry.aliases]
        for surface, score, kind in surfaces:
            if not surface:
                continue
            length = len(surface)
            start = text.find(surface)
            while start != -1:
                eff = score
                # 短名稱（如「世界」「全國」）易與一般用詞同形 →
                # 缺乏鄰近股市上下文時打折，須有代號/重複/上下文等佐證才足額
                if length <= _SHORT_NAME_LEN and not _has_stock_context(
                        text, start, start + length):
                    eff = round(score * _SHORT_NAME_DISCOUNT, 3)
                matches.append(_Match(entry.ticker, start, start + length, eff, kind))
                start = text.find(surface, start + 1)
    return matches


def _resolve_overlaps(matches: list[_Match]) -> list[_Match]:
    """跨個股的最長匹配優先消歧。

    較長的 surface 勝出，並抑制與之重疊、且**屬於不同個股**的較短匹配
    （例：「中華電信」整段歸 2412，內含的「中華」不再誤判到 2204）。
    同一個股的重疊匹配則保留（名稱 + 別名互相強化信心）。
    """
    ordered = sorted(matches, key=lambda m: (m.length, m.score), reverse=True)
    accepted: list[_Match] = []
    for m in ordered:
        conflict = any(
            a.ticker != m.ticker and m.start < a.end and a.start < m.end
            for a in accepted
        )
        if conflict:
            continue
        accepted.append(m)
    return accepted


def recognize_tickers(
    text: str, dictionary: TickerDictionary | None = None
) -> list[RecognizedTicker]:
    """從文字辨識被提及的個股，回傳通過信心門檻者。"""
    dictionary = dictionary or get_dictionary()
    if not text:
        return []

    accepted = _resolve_overlaps(_collect_matches(text, dictionary))

    by_ticker: dict[str, list[_Match]] = {}
    for m in accepted:
        by_ticker.setdefault(m.ticker, []).append(m)

    results: list[RecognizedTicker] = []
    for ticker, ms in by_ticker.items():
        base = max(m.score for m in ms)
        bonus = min(0.3, 0.1 * (len(ms) - 1))  # 多次/多型態提及加成
        confidence = round(min(1.0, base + bonus), 3)
        if confidence < _CONFIDENCE_THRESHOLD:
            continue
        positions = sorted({m.start for m in ms})
        results.append(RecognizedTicker(ticker, confidence, positions))

    results.sort(key=lambda r: r.confidence, reverse=True)
    return results
