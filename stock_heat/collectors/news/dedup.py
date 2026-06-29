"""URL 正規化與 SimHash 近似去重（docs/03 §4.5）。

- ``normalize_url``：去除追蹤參數、統一 scheme/host，產生穩定的 external_id。
- ``simhash`` / ``hamming_distance``：對 title+content 做 64-bit SimHash，
  漢明距離 ≤ 門檻視為重複（同一新聞被多家轉載時的判定基礎）。
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

#: 常見追蹤類 query 參數，正規化時移除
_TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|yclid|mc_|ref$|ref_|spm$)", re.IGNORECASE)

_TOKEN_RE = re.compile(r"[一-鿿]|[a-zA-Z0-9]+")


def normalize_url(url: str) -> str:
    """正規化 URL，作為去重與 ``external_id`` 的穩定鍵。"""
    parts = urlsplit(url.strip())
    # 統一 scheme 為 https：同一文章的 http/https 版本應去重為同一鍵
    scheme = "https"
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    # 移除追蹤參數，其餘排序以穩定化
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
            if not _TRACKING_PARAMS.match(k)]
    kept.sort()
    query = urlencode(kept)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, query, ""))


def url_key(url: str) -> str:
    """正規化 URL 的 sha1，給 Redis seen-set 用。"""
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()


def _tokens(text: str) -> list[str]:
    """粗略 token 化：中文逐字、英數成詞。用於 SimHash 特徵。"""
    return _TOKEN_RE.findall(text.lower())


def simhash(text: str, bits: int = 64) -> int:
    """計算文字的 SimHash 指紋。"""
    if not text:
        return 0
    vector = [0] * bits
    mask = (1 << bits) - 1
    for token in _tokens(text):
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) & mask
        for i in range(bits):
            vector[i] += 1 if (h >> i) & 1 else -1
    fingerprint = 0
    for i in range(bits):
        if vector[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """兩個指紋的漢明距離。"""
    return bin(a ^ b).count("1")


def is_near_duplicate(a: int, b: int, threshold: int = 3) -> bool:
    """SimHash 漢明距離 ≤ threshold 視為近似重複。"""
    return hamming_distance(a, b) <= threshold
