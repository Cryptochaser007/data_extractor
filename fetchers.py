"""
fetchers.py — One fetcher class per source, all returning raw dicts.
Each fetcher runs a robots.txt compliance check before hitting any page.
"""

import time
import hashlib
import logging
import urllib.robotparser
import urllib.parse
from typing import List, Dict, Any, Optional

import requests
import feedparser

logger = logging.getLogger("fetchers")


# ─────────────────────────────────────────────
# Compliance helper
# ─────────────────────────────────────────────

def check_robots(url: str, user_agent: str, timeout: int = 10) -> tuple[bool, float]:
    """
    Returns (is_allowed, crawl_delay_seconds).
    If robots.txt is unreachable, defaults to (True, 2.0) — conservative.
    """
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception as e:
        logger.warning(f"robots.txt unreachable for {parsed.netloc}: {e} — defaulting allowed")
        return True, 2.0

    allowed = rp.can_fetch(user_agent, url)
    delay   = rp.crawl_delay(user_agent) or rp.crawl_delay("*") or 2.0
    return allowed, float(delay)


def make_guid(source: str, link: str) -> str:
    """Stable unique ID — hashed from source + canonical link."""
    return hashlib.sha256(f"{source}|{link}".encode()).hexdigest()


# ─────────────────────────────────────────────
# Base RSS fetcher
# ─────────────────────────────────────────────

class RSSFetcher:
    def __init__(self, source_name: str, feed_url: str, cfg):
        self.source   = source_name
        self.url      = feed_url
        self.cfg      = cfg

    def fetch(self) -> List[Dict[str, Any]]:
        allowed, delay = check_robots(self.url, self.cfg.USER_AGENT, self.cfg.REQUEST_TIMEOUT)
        if not allowed:
            logger.warning(f"[{self.source}] Blocked by robots.txt — skipping {self.url}")
            return []

        logger.info(f"[{self.source}] Fetching RSS: {self.url}")
        time.sleep(delay)

        try:
            feed = feedparser.parse(
                self.url,
                agent=self.cfg.USER_AGENT,
                request_headers={"Accept": "application/rss+xml, application/xml, text/xml"},
            )
        except Exception as e:
            logger.error(f"[{self.source}] Feed parse error: {e}")
            return []

        if feed.bozo and not feed.entries:
            logger.warning(f"[{self.source}] Feed malformed or empty: {self.url}")
            return []

        entries = []
        for entry in feed.entries:
            link = entry.get("link") or entry.get("id") or self.url
            entries.append({
                "source":    self.source,
                "raw_title": entry.get("title", ""),
                "raw_link":  link,
                "raw_summary": entry.get("summary", "") or entry.get("description", ""),
                "raw_published": entry.get("published", "") or entry.get("updated", ""),
                "raw_tags":  [t.get("term", "") for t in entry.get("tags", [])],
                "guid":      make_guid(self.source, link),
            })

        logger.info(f"[{self.source}] Got {len(entries)} entries")
        return entries


# ─────────────────────────────────────────────
# data.gov.in REST API fetcher
# ─────────────────────────────────────────────

class DataGovInFetcher:
    BASE = "https://api.data.gov.in/resource"

    def __init__(self, cfg):
        self.cfg = cfg

    def _fetch_resource(self, resource_id: str, label: str) -> List[Dict]:
        if not self.cfg.DATAGOVIN_API_KEY:
            logger.warning("[data.gov.in] No API key set — skipping")
            return []

        params = {
            "api-key": self.cfg.DATAGOVIN_API_KEY,
            "format":  "json",
            "limit":   "100",
            "offset":  "0",
        }
        url = f"{self.BASE}/{resource_id}"
        logger.info(f"[data.gov.in] Fetching resource '{label}' ({resource_id})")

        try:
            resp = requests.get(
                url, params=params,
                timeout=self.cfg.REQUEST_TIMEOUT,
                headers={"User-Agent": self.cfg.USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[data.gov.in] Request failed for {resource_id}: {e}")
            return []

        records = data.get("records", [])
        entries = []
        for rec in records:
            # Field names vary by dataset — we pass the raw dict through
            link = rec.get("url") or rec.get("source_url") or f"{self.BASE}/{resource_id}"
            entries.append({
                "source":        f"data.gov.in/{label}",
                "raw_title":     rec.get("post_name") or rec.get("title") or rec.get("vacancy_name") or label,
                "raw_link":      link,
                "raw_summary":   str(rec),   # full record as fallback
                "raw_published": rec.get("last_date") or rec.get("date") or "",
                "raw_tags":      [rec.get("department", ""), rec.get("category", "")],
                "raw_record":    rec,         # keep full structured record
                "guid":          make_guid(f"data.gov.in/{label}", link + str(rec)),
            })

        logger.info(f"[data.gov.in] Got {len(entries)} records for '{label}'")
        return entries

    def fetch(self) -> List[Dict]:
        all_entries = []
        for resource in self.cfg.DATAGOVIN_RESOURCES:
            all_entries.extend(self._fetch_resource(resource["id"], resource["label"]))
            time.sleep(self.cfg.DEFAULT_DELAY)
        return all_entries


# ─────────────────────────────────────────────
# NCS Portal fetcher (structured vacancy search)
# ─────────────────────────────────────────────

class NCSFetcher:
    """
    NCS doesn't have a public API, but their vacancy search page
    returns JSON when hit with the right headers. We treat it as
    a compliance-checked structured scrape.
    """
    SEARCH_URL = "https://www.ncs.gov.in/NCS_JobSearch/SearchJob"

    def __init__(self, cfg):
        self.cfg = cfg

    def fetch(self) -> List[Dict]:
        allowed, delay = check_robots(self.SEARCH_URL, self.cfg.USER_AGENT, self.cfg.REQUEST_TIMEOUT)
        if not allowed:
            logger.warning("[NCS] Blocked by robots.txt — falling back to RSS")
            # Fall back to NCS RSS feed
            return RSSFetcher("NCS", self.cfg.NCS_RSS, self.cfg).fetch()

        logger.info("[NCS] Fetching vacancy search (government sector filter)")
        time.sleep(delay)

        payload = {
            "Keywords":     "",
            "JobCategory":  "Government",  # filter to govt jobs
            "PageNumber":   1,
            "PageSize":     50,
        }
        headers = {
            "User-Agent":   self.cfg.USER_AGENT,
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            resp = requests.post(
                self.SEARCH_URL, json=payload, headers=headers,
                timeout=self.cfg.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[NCS] Structured fetch failed ({e}), falling back to RSS")
            return RSSFetcher("NCS", self.cfg.NCS_RSS, self.cfg).fetch()

        jobs = data.get("Jobs") or data.get("jobs") or []
        entries = []
        for job in jobs:
            link = job.get("JobUrl") or job.get("url") or self.SEARCH_URL
            entries.append({
                "source":        "NCS",
                "raw_title":     job.get("JobTitle") or job.get("title", ""),
                "raw_link":      link,
                "raw_summary":   job.get("JobDescription") or job.get("description", ""),
                "raw_published": job.get("PostedDate") or job.get("posted_date", ""),
                "raw_tags":      [job.get("Department", ""), job.get("Category", "")],
                "raw_record":    job,
                "guid":          make_guid("NCS", link),
            })

        logger.info(f"[NCS] Got {len(entries)} entries")
        return entries


# ─────────────────────────────────────────────
# Orchestrator — runs all enabled fetchers
# ─────────────────────────────────────────────

class FetcherManager:
    def __init__(self, cfg):
        self.cfg = cfg

    def fetch_all(self) -> List[Dict]:
        all_entries: List[Dict] = []

        if self.cfg.ENABLE_UPSC:
            all_entries += RSSFetcher("UPSC", self.cfg.UPSC_RSS, self.cfg).fetch()

        if self.cfg.ENABLE_SSC:
            all_entries += RSSFetcher("SSC", self.cfg.SSC_RSS, self.cfg).fetch()

        if self.cfg.ENABLE_EMPLOYMENT_NEWS:
            all_entries += RSSFetcher("Employment News", self.cfg.EMPLOYMENT_NEWS_RSS, self.cfg).fetch()

        if self.cfg.ENABLE_NCS:
            all_entries += NCSFetcher(self.cfg).fetch()

        if self.cfg.ENABLE_DATAGOVIN:
            all_entries += DataGovInFetcher(self.cfg).fetch()

        if self.cfg.ENABLE_RAILWAYS:
            for feed_url in self.cfg.RAILWAY_RSS_FEEDS:
                zone = urllib.parse.urlparse(feed_url).netloc.replace("www.", "")
                all_entries += RSSFetcher(f"Railways/{zone}", feed_url, self.cfg).fetch()
                time.sleep(self.cfg.DEFAULT_DELAY)

        return all_entries
