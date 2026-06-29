"""從證交所（TWSE）/ 櫃買中心（TPEx）官方 ISIN 清單匯入完整個股字典。

來源：https://isin.twse.com.tw/isin/C_public.jsp  （strMode=2 上市、strMode=4 上櫃）
僅取**普通股**（CFICode 以 ES 開頭），排除 ETF、權證、特別股、TDR 等。
保留 data/tickers.csv 既有的人工別名（暱稱／英文名），其餘以官方名稱填入。

用法：
    python -m scripts.import_tickers              # 寫入 data/tickers.csv
    python -m scripts.import_tickers --dry-run    # 只印統計不寫檔
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser

TICKERS_CSV = Path("data/tickers.csv")
_BASE = "https://isin.twse.com.tw/isin/C_public.jsp?strMode="
_MARKETS = {"2": "TWSE", "4": "TPEx"}
_HEADERS = {"User-Agent": "StockHeatBot/0.1 (+contact)"}


def _load_curated_aliases() -> dict[str, str]:
    """讀取既有 csv 的別名欄，保留人工維護的暱稱。"""
    aliases: dict[str, str] = {}
    if not TICKERS_CSV.exists():
        return aliases
    with TICKERS_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            t = (row.get("ticker") or "").strip()
            a = (row.get("aliases") or "").strip()
            if t and a:
                aliases[t] = a
    return aliases


def _fetch_market(mode: str) -> list[tuple[str, str, str, str]]:
    """回傳 [(ticker, name, industry, market)]，僅普通股。"""
    resp = httpx.get(_BASE + mode, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.content.decode("ms950", errors="replace")
    market = _MARKETS[mode]
    out: list[tuple[str, str, str, str]] = []
    for tr in HTMLParser(html).css("tr"):
        cells = [c.text(strip=True) for c in tr.css("td")]
        if len(cells) < 6:
            continue
        cfi = cells[5].strip()
        if not cfi.startswith("ES"):  # 僅普通股
            continue
        head = cells[0].replace("　", " ").split()
        if len(head) < 2 or not head[0].isdigit():
            continue
        ticker, name = head[0], " ".join(head[1:])
        industry = cells[4].strip()
        out.append((ticker, name, industry, market))
    return out


def main(dry_run: bool = False) -> None:
    curated = _load_curated_aliases()
    rows: list[tuple[str, str, str, str]] = []
    for mode in _MARKETS:
        market_rows = _fetch_market(mode)
        print(f"{_MARKETS[mode]}: {len(market_rows)} 檔普通股")
        rows.extend(market_rows)

    rows.sort(key=lambda r: r[0])
    print(f"合計 {len(rows)} 檔；保留人工別名 {len(curated)} 檔")

    if dry_run:
        return

    TICKERS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with TICKERS_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "name", "aliases", "industry", "market"])
        for ticker, name, industry, market in rows:
            w.writerow([ticker, name, curated.get(ticker, ""), industry, market])
    print(f"已寫入 {TICKERS_CSV}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
