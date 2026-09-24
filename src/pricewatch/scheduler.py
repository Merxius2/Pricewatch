from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pricewatch.config import get_settings
from pricewatch.db.database import SessionLocal
from pricewatch.db.models import TrackedItem
from pricewatch.services.price_checker import PriceChecker

logger = logging.getLogger(__name__)

_last_run_at: datetime | None = None


def get_last_run_at() -> datetime | None:
    return _last_run_at


class PriceWatchScheduler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.scheduler = AsyncIOScheduler()
        self.checker = PriceChecker(self.settings)

    def start(self) -> None:
        interval = max(self.settings.check_interval_minutes, 5)
        self.scheduler.add_job(
            self.run_due_checks,
            trigger=IntervalTrigger(minutes=interval),
            id="price_checks",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.start()
        logger.info("Scheduler started; global interval=%s minutes", interval)

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    async def run_due_checks(self) -> None:
        global _last_run_at
        _last_run_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db = SessionLocal()
        try:
            items = db.query(TrackedItem).filter(TrackedItem.enabled.is_(True)).all()
            due_items = [item for item in items if self._is_due(item)]
            logger.info("Running price checks for %s due item(s)", len(due_items))
            for item in due_items:
                result = await self.checker.check_item(db, item)
                if result.success:
                    logger.info(
                        "Checked item %s (%s): price=%s alert=%s",
                        item.id,
                        item.name,
                        result.price,
                        result.alert_triggered,
                    )
                else:
                    logger.warning("Check failed for item %s (%s): %s", item.id, item.name, result.error)
        finally:
            db.close()

    def _is_due(self, item: TrackedItem) -> bool:
        interval = item.check_interval_minutes or self.settings.check_interval_minutes
        interval = max(interval, 5)
        if item.last_checked_at is None:
            return True
        due_at = item.last_checked_at + timedelta(minutes=interval)
        return datetime.now(timezone.utc).replace(tzinfo=None) >= due_at
