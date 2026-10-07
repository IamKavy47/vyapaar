"""Optional background jobs (APScheduler — deliberately not Celery)."""
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config.settings import settings
from app.database import mongo as m
from app.services import demand_engine, email_service, search_service
from app.services.location_service import location_of
from app.utils.logging import get_logger

logger = get_logger(__name__)
_scheduler: Optional[AsyncIOScheduler] = None


async def expire_requests_job() -> None:
    try:
        count = await search_service.expire_stale_requests()
        if count:
            logger.info("expired %d stale request(s)", count)
    except Exception as exc:
        logger.warning("expire job failed: %s", exc.__class__.__name__)


async def daily_demand_report_job() -> None:
    """Emails each shopkeeper their local demand summary. Opt-in via .env."""
    if not email_service.is_enabled():
        return
    sent = 0
    async for shop in m.shops().find({"is_active": True}):
        user = await m.users().find_one({"_id": shop["user_id"]})
        if not user or not user.get("email"):
            continue
        location = location_of(shop)
        rows = (await demand_engine.nearby_demand(location[0], location[1], radius_meters=2000)
                if location else await demand_engine.top_products(merchant_id=shop["_id"]))
        if not rows:
            continue
        text = demand_engine.format_demand_report(rows, title="YOUR LOCAL DEMAND REPORT")
        if await email_service.send_demand_report(user["email"], shop.get("shop_name", ""), text):
            sent += 1
    logger.info("daily demand report sent to %d merchant(s)", sent)


def start_scheduler() -> Optional[AsyncIOScheduler]:
    global _scheduler
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(expire_requests_job, IntervalTrigger(minutes=10), id="expire_requests")
    if settings.ENABLE_SCHEDULED_REPORTS:
        scheduler.add_job(
            daily_demand_report_job,
            CronTrigger(hour=settings.DEMAND_REPORT_HOUR, minute=0),
            id="daily_demand_report",
        )
        logger.info("Daily demand email scheduled for %02d:00 IST", settings.DEMAND_REPORT_HOUR)
    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler started")
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
