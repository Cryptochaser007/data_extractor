"""
scheduler.py — Keeps the pipeline running on a schedule.
Uses APScheduler (pip install apscheduler).

Usage:
    python scheduler.py          # starts the scheduler (blocking)
    python scheduler.py --once   # run once and exit (same as main.py)

Alternatively, use system cron:
    0 6 * * *  /usr/bin/python3 /path/to/pipeline/main.py >> /var/log/govjobs.log 2>&1
"""

import argparse
import logging
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron       import CronTrigger
from main import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scheduler")

# ── Schedule configuration ────────────────────────────────────
# Default: run every day at 06:00 and 18:00 IST (UTC+5:30 → 00:30 and 12:30 UTC)
# Adjust cron expressions to your preference.

SCHEDULES = [
    CronTrigger(hour=0, minute=30, timezone="UTC"),   # 06:00 IST
    CronTrigger(hour=12, minute=30, timezone="UTC"),  # 18:00 IST
]


def start_scheduler():
    scheduler = BlockingScheduler(timezone="UTC")

    for trigger in SCHEDULES:
        scheduler.add_job(
            func=run,
            trigger=trigger,
            kwargs={"dry_run": False},
            name="govjobs_pipeline",
            misfire_grace_time=3600,   # if server was down, run within 1hr of missed time
            coalesce=True,             # don't stack multiple missed runs
        )

    logger.info("Scheduler started. Next runs:")
    for job in scheduler.get_jobs():
        logger.info(f"  {job.name} — next: {job.next_run_time}")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run pipeline once and exit")
    args = parser.parse_args()

    if args.once:
        run(dry_run=False)
    else:
        start_scheduler()
