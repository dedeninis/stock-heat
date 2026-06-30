"""部署內自動掃描真實新聞（docs/02 §5 的精簡版）。

在 API 服務「同一容器內」週期性執行真實擷取，讓儀表板資料持續更新——因為
SQLite 檔須由讀（API）與寫（擷取）共用同一行程/容器。

關鍵：擷取以**子行程**（`python -m scripts.collect_once`）執行，與 web 行程各自獨立、
真正平行，避免辨識的 CPU 運算因 GIL 卡住 async 事件迴圈（healthcheck 才不會逾時）。

以環境變數啟用：
- ``STOCKHEAT_AUTO_SCAN=1``：啟用自動掃描（啟動即先掃一次，之後週期重複）。
- ``STOCKHEAT_SCAN_INTERVAL``：間隔秒數，預設 1800（30 分）。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL = 1800
_stop = threading.Event()


def enabled() -> bool:
    return bool(os.environ.get("STOCKHEAT_AUTO_SCAN"))


def scan_interval() -> int:
    try:
        return max(60, int(os.environ.get("STOCKHEAT_SCAN_INTERVAL", _DEFAULT_INTERVAL)))
    except ValueError:
        return _DEFAULT_INTERVAL


def run_collect_once() -> None:
    """以子行程跑一次真實擷取＋溫度重算（不阻塞、不佔 web 行程 GIL）。"""
    logger.info("auto-scan: 啟動 collect_once 子行程…")
    # 強制 UTF-8 I/O：避免子行程在非 UTF-8 環境（如 Windows cp950）印中文時崩潰
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(  # noqa: S603 — 固定指令，無外部輸入
        [sys.executable, "-m", "scripts.collect_once"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, check=False,
    )
    if proc.returncode == 0:
        logger.info("auto-scan: 完成 — %s", (proc.stdout or "").strip().splitlines()[-1:])
    else:
        logger.warning("auto-scan: 子行程失敗 rc=%s err=%s",
                       proc.returncode, (proc.stderr or "")[-500:])


def _loop(interval: int, runner, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            runner()
        except Exception:  # noqa: BLE001 — 單輪失敗不終止循環
            logger.exception("auto-scan: 本輪發生例外")
        stop.wait(interval)


def start_autoscan(*, interval: int | None = None, runner=None,
                   stop: threading.Event | None = None) -> threading.Thread:
    """啟動背景掃描執行緒（daemon），立即先掃一次後依間隔重複。回傳該執行緒。"""
    thread = threading.Thread(
        target=_loop,
        args=(interval or scan_interval(), runner or run_collect_once, stop or _stop),
        name="auto-scan", daemon=True,
    )
    thread.start()
    return thread
