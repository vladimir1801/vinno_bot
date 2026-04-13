from __future__ import annotations

from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


def setup_scheduler(
    *,
    bot,
    tz: str,
    hour: int,
    minute: int,
    job_coro,
    job_args: list,
    job_id: str = "daily_wine",
):
    timezone = ZoneInfo(tz)
    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        job_coro,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
        args=job_args,
        id=job_id,
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    return scheduler
