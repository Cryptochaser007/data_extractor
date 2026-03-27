"""
India Government Jobs Pipeline
================================
Fetches vacancies from UPSC, SSC, Employment News, data.gov.in,
NCS Portal and Railways RSS feeds, normalises them into a unified
schema, deduplicates against a local SQLite store, and publishes
new postings to WordPress via the REST API.

Run:
    python main.py                  # single run
    python main.py --dry-run        # fetch + transform, skip WP publish
"""

import argparse
import logging
import sys
from datetime import datetime

from config import Config
from fetchers import FetcherManager
from transform import transform_entries
from database import Database
from publisher import WordPressPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("pipeline")


def run(dry_run: bool = False):
    cfg = Config()
    db  = Database(cfg.DB_PATH)
    db.init()

    logger.info("=" * 60)
    logger.info(f"Pipeline started at {datetime.utcnow().isoformat()}Z")
    logger.info("=" * 60)

    # ── 1. FETCH ──────────────────────────────────────────────
    manager  = FetcherManager(cfg)
    raw_entries = manager.fetch_all()
    logger.info(f"Fetched {len(raw_entries)} raw entries from all sources")

    # ── 2. TRANSFORM ──────────────────────────────────────────
    jobs = transform_entries(raw_entries)
    logger.info(f"Transformed into {len(jobs)} structured job records")

    # ── 3. DEDUPLICATE ────────────────────────────────────────
    new_jobs = [j for j in jobs if not db.exists(j["guid"])]
    logger.info(f"{len(new_jobs)} new jobs (not yet in DB)")

    if not new_jobs:
        logger.info("Nothing new to publish. Pipeline complete.")
        return

    # ── 4. PUBLISH ────────────────────────────────────────────
    if dry_run:
        logger.info("[DRY RUN] Would publish these jobs:")
        for j in new_jobs:
            logger.info(f"  • {j['title']} [{j['source']}]")
    else:
        wp = WordPressPublisher(cfg)
        published, failed = 0, 0
        for job in new_jobs:
            try:
                post_id = wp.publish(job)
                db.mark_published(job["guid"], post_id)
                published += 1
                logger.info(f"Published WP#{post_id}: {job['title']}")
            except Exception as e:
                logger.error(f"Failed to publish '{job['title']}': {e}")
                failed += 1

        logger.info(f"Done — published: {published}, failed: {failed}")

    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
