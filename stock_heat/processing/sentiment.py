"""情緒分析 v0：金融情緒詞典 + 規則（docs/04 §4.1, §4.3）。

- 利多／利空詞典加權求和，再正規化到 -1 ~ +1。
- 否定詞反轉、程度副詞加權。
- 標的層級情緒：只取「提及該個股的子句」計算（§4.3）。

介面固定（``analyze_sentiment`` / ``analyze_ticker_sentiment``），
後續可替換為領域模型（FinBERT-zh）而不動上層。
"""

from __future__ import annotations

import re

# 利多詞 → 正權重
_POSITIVE: dict[str, float] = {
    "漲停": 1.5, "大漲": 1.2, "上漲": 0.8, "走高": 0.8, "勁揚": 1.0, "飆": 1.2,
    "創高": 1.2, "新高": 1.0, "看好": 1.0, "樂觀": 1.0, "調升": 1.0, "上修": 1.0,
    "成長": 0.7, "獲利": 0.7, "營收創高": 1.3, "目標價": 0.3, "利多": 1.0,
    "買超": 0.8, "強勁": 0.8, "回升": 0.7, "受惠": 0.7, "亮眼": 1.0, "突破": 0.7,
}

# 利空詞 → 負權重（以正值記，套用時取負）
_NEGATIVE: dict[str, float] = {
    "跌停": 1.5, "大跌": 1.2, "下跌": 0.8, "走低": 0.8, "重挫": 1.3, "崩": 1.3,
    "創低": 1.2, "新低": 1.0, "看壞": 1.0, "悲觀": 1.0, "調降": 1.0, "下修": 1.0,
    "衰退": 1.0, "虧損": 1.1, "利空": 1.0, "賣超": 0.8, "示警": 1.0, "疲弱": 0.8,
    "違約": 1.2, "下滑": 0.8, "減少": 0.6, "拖累": 0.8, "套牢": 0.9, "踩雷": 1.1,
}

# 否定詞：出現在情緒詞前方窗內 → 反轉極性
_NEGATIONS = ("不", "未", "沒", "無", "難以", "免", "毫無", "並非", "非")
_NEGATION_WINDOW = 4

# 程度副詞 → 放大係數
_INTENSIFIERS: dict[str, float] = {
    "大幅": 1.5, "顯著": 1.4, "急": 1.4, "猛": 1.4, "強勁": 1.3,
    "明顯": 1.3, "略": 0.6, "小幅": 0.6, "微": 0.6,
}
_INTENSIFIER_WINDOW = 4

_CLAUSE_SPLIT = re.compile(r"[。！？!?；;\n]+")
_NORM_DIVISOR = 3.0


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _term_weight(text: str, idx: int, base: float) -> float:
    """套用否定與程度副詞，回傳此詞的有效（帶號）權重。"""
    weight = base
    prefix = text[max(0, idx - _INTENSIFIER_WINDOW):idx]
    for adv, mult in _INTENSIFIERS.items():
        if adv in prefix:
            weight *= mult
            break
    neg_prefix = text[max(0, idx - _NEGATION_WINDOW):idx]
    if any(n in neg_prefix for n in _NEGATIONS):
        weight = -weight
    return weight


def _raw_score(text: str) -> tuple[float, int]:
    """回傳 (帶號權重總和, 命中詞數)。"""
    total = 0.0
    hits = 0
    for term, base in _POSITIVE.items():
        start = text.find(term)
        while start != -1:
            total += _term_weight(text, start, base)
            hits += 1
            start = text.find(term, start + len(term))
    for term, base in _NEGATIVE.items():
        start = text.find(term)
        while start != -1:
            total += _term_weight(text, start, -base)
            hits += 1
            start = text.find(term, start + len(term))
    return total, hits


def analyze_sentiment(text: str) -> float:
    """文件/文字層級情緒，範圍 -1 ~ +1。"""
    if not text:
        return 0.0
    total, hits = _raw_score(text)
    if hits == 0:
        return 0.0
    return round(_clamp(total / _NORM_DIVISOR), 3)


def split_clauses(text: str) -> list[str]:
    return [c for c in _CLAUSE_SPLIT.split(text) if c.strip()]


def analyze_ticker_sentiment(
    text: str, surfaces: list[str], *, doc_fallback: float = 0.0
) -> float:
    """標的層級情緒：只取提及該個股（任一 surface）的子句計算。

    若沒有任何子句明確提及該個股，退回文件層級情緒。
    """
    clauses = [c for c in split_clauses(text) if any(s and s in c for s in surfaces)]
    if not clauses:
        return doc_fallback
    total = 0.0
    hits = 0
    for c in clauses:
        t, h = _raw_score(c)
        total += t
        hits += h
    if hits == 0:
        return 0.0
    return round(_clamp(total / _NORM_DIVISOR), 3)
