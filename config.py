"""
config.py — All pipeline settings in one place.
Copy .env.example to .env and fill in your values.
"""

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # ── Database ──────────────────────────────────────────────
    DB_PATH: str = os.getenv("DB_PATH", "govjobs.db")

    # ── WordPress ─────────────────────────────────────────────
    WP_BASE_URL: str   = os.getenv("WP_BASE_URL", "https://yoursite.com")
    WP_USERNAME: str   = os.getenv("WP_USERNAME", "")
    # Generate via WP Admin → Users → Application Passwords
    WP_APP_PASSWORD: str = os.getenv("WP_APP_PASSWORD", "")
    # Post type — use "job_listing" for WP Job Manager, "post" for standard
    WP_POST_TYPE: str  = os.getenv("WP_POST_TYPE", "job_listing")
    # Default post status: "publish" or "pending" (for manual review)
    WP_POST_STATUS: str = os.getenv("WP_POST_STATUS", "publish")
    # Category slug to auto-assign (optional)
    WP_CATEGORY: str   = os.getenv("WP_CATEGORY", "government-jobs")

    # ── data.gov.in ───────────────────────────────────────────
    DATAGOVIN_API_KEY: str = os.getenv("DATAGOVIN_API_KEY", "")

    # ── Fetcher toggles ───────────────────────────────────────
    ENABLE_UPSC: bool         = os.getenv("ENABLE_UPSC", "true").lower() == "true"
    ENABLE_SSC: bool          = os.getenv("ENABLE_SSC", "true").lower() == "true"
    ENABLE_EMPLOYMENT_NEWS: bool = os.getenv("ENABLE_EMPLOYMENT_NEWS", "true").lower() == "true"
    ENABLE_DATAGOVIN: bool    = os.getenv("ENABLE_DATAGOVIN", "true").lower() == "true"
    ENABLE_NCS: bool          = os.getenv("ENABLE_NCS", "true").lower() == "true"
    ENABLE_RAILWAYS: bool     = os.getenv("ENABLE_RAILWAYS", "true").lower() == "true"

    # ── Crawl behaviour ───────────────────────────────────────
    REQUEST_TIMEOUT: int  = int(os.getenv("REQUEST_TIMEOUT", "15"))
    DEFAULT_DELAY: float  = float(os.getenv("DEFAULT_DELAY", "2.0"))
    USER_AGENT: str       = "GovJobsBotIN/1.0 (+https://yoursite.com/bot)"

    # ── RSS feed URLs ─────────────────────────────────────────
    UPSC_RSS: str              = "https://upsc.gov.in/rss.xml"
    SSC_RSS: str               = "https://ssc.gov.in/rss"
    EMPLOYMENT_NEWS_RSS: str   = "https://www.employmentnews.gov.in/rss.aspx"
    NCS_RSS: str               = "https://www.ncs.gov.in/rss.xml"

    # Multiple RRB zones
    RAILWAY_RSS_FEEDS: List[str] = field(default_factory=lambda: [
        "https://www.rrbchennai.gov.in/rss.xml",
        "https://www.rrbmumbai.gov.in/rss.xml",
        "https://www.rrbald.gov.in/rss.xml",
        "https://www.rrbbhopal.gov.in/rss.xml",
        "https://www.rrbkolkata.gov.in/rss.xml",
    ])

    # ── data.gov.in dataset resource IDs (employment-related) ─
    DATAGOVIN_RESOURCES: List[dict] = field(default_factory=lambda: [
        {"id": "9b468b65-6c00-46de-8e18-00c60e4a7b13", "label": "Central Govt Vacancies"},
        {"id": "6176d714-d65f-4f15-a56e-9e7ed1beebb3", "label": "Employment Exchange Data"},
    ])
