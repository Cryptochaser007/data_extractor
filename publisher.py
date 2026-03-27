"""
publisher.py — Publishes normalised job dicts to WordPress via REST API.

Supports:
  • Standard "post" post type
  • WP Job Manager "job_listing" post type (with _job_* meta fields)
  • Custom post types

Authentication: WordPress Application Passwords (WP 5.6+)
  Generate at: WP Admin → Users → Your Profile → Application Passwords
"""

import logging
import requests
from base64   import b64encode
from typing   import Dict, Any, Optional

logger = logging.getLogger("publisher")


class WordPressPublisher:
    def __init__(self, cfg):
        self.cfg      = cfg
        self.base_url = cfg.WP_BASE_URL.rstrip("/")
        self.session  = requests.Session()
        self.session.headers.update({
            "User-Agent":    cfg.USER_AGENT,
            "Content-Type":  "application/json",
            "Authorization": self._basic_auth(cfg.WP_USERNAME, cfg.WP_APP_PASSWORD),
        })
        self._category_id: Optional[int] = None

    @staticmethod
    def _basic_auth(username: str, password: str) -> str:
        token = b64encode(f"{username}:{password}".encode()).decode()
        return f"Basic {token}"

    # ── Category lookup / create ──────────────────────────────

    def _get_or_create_category(self, slug: str) -> Optional[int]:
        """Returns WP category ID, creating it if it doesn't exist."""
        if self._category_id:
            return self._category_id

        endpoint = f"{self.base_url}/wp-json/wp/v2/categories"
        try:
            resp = self.session.get(endpoint, params={"slug": slug}, timeout=10)
            resp.raise_for_status()
            cats = resp.json()
            if cats:
                self._category_id = cats[0]["id"]
                return self._category_id

            # Create it
            resp = self.session.post(endpoint, json={"name": slug.replace("-", " ").title(), "slug": slug}, timeout=10)
            resp.raise_for_status()
            self._category_id = resp.json()["id"]
            logger.info(f"Created WP category '{slug}' → id {self._category_id}")
            return self._category_id
        except Exception as e:
            logger.warning(f"Category lookup failed: {e}")
            return None

    # ── Tag lookup / create ───────────────────────────────────

    def _get_or_create_tags(self, tag_names: list) -> list:
        """Returns list of WP tag IDs."""
        tag_ids = []
        endpoint = f"{self.base_url}/wp-json/wp/v2/tags"
        for name in tag_names:
            if not name:
                continue
            try:
                slug = name.lower().replace(" ", "-")
                resp = self.session.get(endpoint, params={"slug": slug}, timeout=8)
                resp.raise_for_status()
                existing = resp.json()
                if existing:
                    tag_ids.append(existing[0]["id"])
                    continue
                resp = self.session.post(endpoint, json={"name": name, "slug": slug}, timeout=8)
                resp.raise_for_status()
                tag_ids.append(resp.json()["id"])
            except Exception as e:
                logger.debug(f"Tag '{name}' skipped: {e}")
        return tag_ids

    # ── Meta fields for WP Job Manager ───────────────────────

    def _job_manager_meta(self, job: Dict) -> Dict:
        """
        WP Job Manager stores job details as post meta.
        https://wpjobmanager.com/document/the-job-listing-post-type/
        """
        return {
            "_job_location":     job.get("location", "All India"),
            "_job_expires":      job.get("last_date", ""),
            "_company_name":     job.get("organisation", ""),
            "_company_website":  job.get("source_url", ""),
            "_job_salary":       "",   # not available from RSS
            "_filled":           0,
            "_featured":         0,
            "_job_source":       job.get("source", ""),
        }

    # ── Build WP post payload ─────────────────────────────────

    def _build_payload(self, job: Dict, cat_id: Optional[int], tag_ids: list) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "title":   job["title"],
            "content": job["content_html"],
            "excerpt": job["excerpt"],
            "status":  self.cfg.WP_POST_STATUS,
            "slug":    job["slug"],
            "tags":    tag_ids,
            "meta": {
                "source_url":    job["source_url"],
                "source_name":   job["source"],
                "scraped_at":    job["scraped_at"],
                "pipeline_guid": job["guid"],
            },
        }

        if cat_id:
            payload["categories"] = [cat_id]

        # WP Job Manager extra fields
        if self.cfg.WP_POST_TYPE == "job_listing":
            payload["meta"].update(self._job_manager_meta(job))

        return payload

    # ── Publish ───────────────────────────────────────────────

    def publish(self, job: Dict[str, Any]) -> int:
        """
        Creates a new WP post. Returns the WordPress post ID.
        Raises on HTTP errors.
        """
        endpoint = f"{self.base_url}/wp-json/wp/v2/{self.cfg.WP_POST_TYPE}s"

        cat_id  = self._get_or_create_category(self.cfg.WP_CATEGORY)
        tag_ids = self._get_or_create_tags(job.get("tags", []))
        payload = self._build_payload(job, cat_id, tag_ids)

        resp = self.session.post(endpoint, json=payload, timeout=15)

        if resp.status_code == 401:
            raise PermissionError("WP auth failed — check WP_USERNAME and WP_APP_PASSWORD")
        if resp.status_code == 404:
            raise ValueError(f"Endpoint not found: {endpoint} — check WP_POST_TYPE")

        resp.raise_for_status()
        post_id = resp.json().get("id")
        if not post_id:
            raise ValueError(f"No post ID in WP response: {resp.text[:200]}")

        return int(post_id)

    def test_connection(self) -> bool:
        """Quick connectivity + auth test."""
        try:
            resp = self.session.get(
                f"{self.base_url}/wp-json/wp/v2/users/me", timeout=8
            )
            if resp.status_code == 200:
                user = resp.json().get("name", "?")
                logger.info(f"WP connection OK — authenticated as '{user}'")
                return True
            logger.error(f"WP connection failed: HTTP {resp.status_code}")
            return False
        except Exception as e:
            logger.error(f"WP connection error: {e}")
            return False
