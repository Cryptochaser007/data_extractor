"""
database.py — Lightweight SQLite store for deduplication and audit log.
Tracks every job guid so we never publish the same vacancy twice.
"""

import sqlite3
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("database")


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if not self._conn:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS published_jobs (
                guid            TEXT PRIMARY KEY,
                wp_post_id      INTEGER,
                source          TEXT,
                title           TEXT,
                source_url      TEXT,
                published_at    TEXT,
                scraped_at      TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at          TEXT,
                fetched_count   INTEGER,
                new_count       INTEGER,
                published_count INTEGER,
                failed_count    INTEGER
            );
        """)
        conn.commit()
        logger.info(f"Database initialised at {self.db_path}")

    def exists(self, guid: str) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM published_jobs WHERE guid = ?", (guid,)
        ).fetchone()
        return row is not None

    def mark_published(self, guid: str, wp_post_id: int,
                       source: str = "", title: str = "",
                       source_url: str = "", published_at: str = "",
                       scraped_at: str = ""):
        conn = self._get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO published_jobs
                (guid, wp_post_id, source, title, source_url, published_at, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (guid, wp_post_id, source, title, source_url,
              published_at, scraped_at or datetime.utcnow().isoformat()))
        conn.commit()

    def log_run(self, fetched: int, new: int, published: int, failed: int):
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO pipeline_runs
                (run_at, fetched_count, new_count, published_count, failed_count)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.utcnow().isoformat(), fetched, new, published, failed))
        conn.commit()

    def recent_published(self, limit: int = 20):
        conn = self._get_conn()
        return conn.execute(
            "SELECT * FROM published_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
