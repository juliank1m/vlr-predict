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
    """Scrape recent VLR results and recompute Elo ratings."""
    logger.info("daily_scrape triggered at %s", datetime.utcnow())
    try:
        from app.services.scraper import scrape_recent_matches

        new_count = scrape_recent_matches(pages=5)
        logger.info("Scraped %d new matches.", new_count)

        if new_count > 0:
            from app.services.compute_elo import compute_all_elo

            logger.info("Recomputing Elo ratings...")
            compute_all_elo()
            logger.info("Elo recomputation complete.")
    except Exception:
        logger.exception("daily_scrape failed")


@scheduler.scheduled_job("cron", day_of_week="sun", hour=7, minute=0, id="weekly_retrain")
def weekly_retrain() -> None:
    """Retrain the prediction model on all available data."""
    logger.info("weekly_retrain triggered at %s", datetime.utcnow())
    try:
        from app.ml.train import train_and_save

        metadata = train_and_save()
        logger.info(
            "Model retrained: version=%s, rows=%d, test_accuracy=%.3f",
            metadata["model_version"],
            metadata["row_count"],
            metadata["test"]["full_model"]["accuracy"],
        )
    except Exception:
        logger.exception("weekly_retrain failed")


def main() -> None:
    logger.info("Starting VLR Predict scheduler...")
    logger.info("Registered jobs: %s", [j.id for j in scheduler.get_jobs()])
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
