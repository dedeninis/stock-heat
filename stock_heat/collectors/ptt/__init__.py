"""PTT 社群擷取模組（社群討論熱度）。"""

from __future__ import annotations

from pathlib import Path

import yaml

from .collector import PttCollector, PttSource, collect_ptt_board

__all__ = ["PttCollector", "PttSource", "collect_ptt_board", "load_ptt_sources"]


def load_ptt_sources(config_path: str | Path = "config/sources.yaml") -> list[PttSource]:
    """讀取設定檔 ``social:`` 區段，回傳啟用中的 PTT 來源。"""
    path = Path(config_path)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("social", []) or []
    sources = [PttSource(**item) for item in items]
    return [s for s in sources if s.enabled]
