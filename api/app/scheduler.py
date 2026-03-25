"""APScheduler setup for periodic tasks.

Run as: python -m app.scheduler
"""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

scheduler = BlockingScheduler()


@scheduler.scheduled_job("cron", hour=6, minute=0, id="daily_scrape")
def daily_scrape() -> None:
    """Placeholder for daily match scraping.

    Replace the body with actual scraping logic once the scraper is wired up.
    Example:
        from app.services.scraper import scrape_recent_matches
        scrape_recent_matches(days_back=2)
    """
    logger.info("daily_scrape triggered at %s (placeholder — no-op)", datetime.utcnow())


@scheduler.scheduled_job("cron", day_of_week="sun", hour=7, minute=0, id="weekly_retrain")
def weekly_retrain() -> None:
    """Placeholder for weekly model retraining.

    Replace the body with actual training logic once ready.
    Example:
        from app.ml.train import train_and_save
        train_and_save()
    """
    logger.info("weekly_retrain triggered at %s (placeholder — no-op)", datetime.utcnow())


def main() -> None:
    logger.info("Starting VLR Predict scheduler...")
    logger.info("Registered jobs: %s", [j.id for j in scheduler.get_jobs()])
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
