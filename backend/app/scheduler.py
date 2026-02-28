import asyncio
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import config
from . import scraper


scheduler = AsyncIOScheduler()


def delete_old_screenshots() -> None:
    cutoff = date.today() - timedelta(days=config.RETENTION_DAYS)
    for png in config.SCREENSHOTS_DIR.glob("하이패스(*.png"):
        # Filename pattern: 하이패스(YYYY-MM-DD).png
        name = png.stem  # 하이패스(YYYY-MM-DD)
        try:
            date_part = name[4:-1]  # strip '하이패스(' and ')'
            file_date = date.fromisoformat(date_part)
            if file_date < cutoff:
                png.unlink()
        except Exception:
            continue


async def scheduled_capture() -> None:
    delete_old_screenshots()
    await scraper.capture_last_n_days(n=config.RETENTION_DAYS)


def start(schedule_hour: int) -> None:
    scheduler.add_job(
        scheduled_capture,
        trigger="cron",
        hour=schedule_hour,
        minute=0,
        id="daily_capture",
        replace_existing=True,
    )
    scheduler.start()


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
