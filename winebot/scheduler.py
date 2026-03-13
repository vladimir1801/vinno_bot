from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

def setup_scheduler(*, bot, tz: str, hour: int, minute: int, job_coro, job_args: list, job_id: str = "daily_wine"):
    scheduler = AsyncIOScheduler(timezone=pytz.timezone(tz))
    scheduler.add_job(
        job_coro,
        CronTrigger(hour=hour, minute=minute),
        args=job_args,
        id=job_id,
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
