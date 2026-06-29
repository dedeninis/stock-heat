"""排程器進入點（docs/02 §2.2, §5；docs/06 §5.1）。

依各新聞來源的 interval 定時擷取，每 15 分鐘做盤中溫度增量更新，
收盤後（台北時間 14:30）做日線定版計算。

執行：
    python -m stock_heat.scheduler
    STOCKHEAT_DATABASE_URL=... python -m stock_heat.scheduler
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.base import BaseScheduler

from .collectors.news.sources import load_news_sources
from .config import Settings
from .jobs import bootstrap, collect_source, recompute_today

logger = logging.getLogger(__name__)

# 收盤後日線重算（台北時間）；APScheduler 以系統時區或指定時區排程
_DAILY_HOUR = 14
_DAILY_MINUTE = 30
_INTRADAY_MINUTES = 15


def build_scheduler(
    settings: Settings | None = None,
    *,
    scheduler: BaseScheduler | None = None,
) -> BaseScheduler:
    """組裝排程器：每來源擷取 + 盤中重算 + 日線重算。不會自動 start。"""
    settings = settings or Settings()
    sched = scheduler or BlockingScheduler()
    url = getattr(settings, "database_url", None)

    for src in load_news_sources(settings.sources_path):
        sched.add_job(
            collect_source, "interval", seconds=src.interval, args=[src, url],
            id=f"collect:{src.id}", max_instances=1, coalesce=True,
            replace_existing=True,
        )

    sched.add_job(
        recompute_today, "interval", minutes=_INTRADAY_MINUTES, args=[url],
        id="recompute:intraday", max_instances=1, coalesce=True,
        replace_existing=True,
    )
    sched.add_job(
        recompute_today, "cron", hour=_DAILY_HOUR, minute=_DAILY_MINUTE, args=[url],
        id="recompute:daily", max_instances=1, coalesce=True,
        replace_existing=True,
    )
    return sched


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings()
    url = getattr(settings, "database_url", None)
    logger.info("bootstrapping database…")
    bootstrap(url, sources_path=settings.sources_path)

    sched = build_scheduler(settings)
    logger.info("scheduler starting with jobs: %s",
                [j.id for j in sched.get_jobs()])
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler stopped")


if __name__ == "__main__":
    main()
