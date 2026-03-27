"""
transform.py — Normalises raw fetcher output into a unified job schema.

Output schema (every job dict):
    guid            str     — stable dedup key
    source          str     — e.g. "UPSC", "SSC", "NCS"
    title           str     — cleaned job title
    slug            str     — WP-ready URL slug
    content_html    str     — HTML body for the WP post
    excerpt         str     — short plain-text summary
    organisation    str     — hiring body extracted from title/summary
    category        str     — e.g. "Engineering", "Administrative", "Teaching"
    location        str     — state/city if detectable
    last_date       str     — application deadline (ISO date string or "")
    source_url      str     — canonical link back to official notice
    published_at    str     — ISO datetime of original post
    scraped_at      str     — ISO datetime of this run
    tags            list    — list of tag strings for WP
"""

import re
import logging
from datetime import datetime
from typing import List, Dict, Any
from email.utils import parsedate_to_datetime

logger = logging.getLogger("transform")


# ─────────────────────────────────────────────
# Category inference (keyword → category map)
# ─────────────────────────────────────────────

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Engineering":      ["engineer", "technical", "jr engineer", "assistant engineer", "je ", "ae "],
    "Administrative":   ["clerk", "assistant", "officer", "ias", "ips", "ifs", "mts", "ldc", "udc", "secretariat"],
    "Defence":          ["army", "navy", "airforce", "military", "soldier", "constable", "police", "cisf", "crpf", "bsf"],
    "Teaching":         ["teacher", "professor", "lecturer", "principal", "tgt", "pgt", "kvs", "nvs", "ugc"],
    "Medical":          ["doctor", "nurse", "medical", "health", "pharmacist", "lab assistant", "ayush"],
    "Banking":          ["bank", "rbi", "nabard", "ibps", "sbi", "po", "clerk", "finance"],
    "Railways":         ["railway", "rrb", "rrb ntpc", "group d", "loco pilot", "station master"],
    "Research":         ["scientist", "research", "isro", "drdo", "csir", "barc"],
    "Judicial":         ["judiciary", "court", "judge", "legal", "law"],
    "Agriculture":      ["agriculture", "horticulture", "forest", "fci", "nafed"],
}

def infer_category(text: str) -> str:
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return "General"


# ─────────────────────────────────────────────
# Location extraction (state name scan)
# ─────────────────────────────────────────────

INDIAN_STATES = [
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "delhi", "jammu", "kashmir", "ladakh", "chandigarh", "puducherry",
]

def extract_location(text: str) -> str:
    text_lower = text.lower()
    for state in INDIAN_STATES:
        if state in text_lower:
            return state.title()
    return "All India"


# ─────────────────────────────────────────────
# Date parsing
# ─────────────────────────────────────────────

DATE_PATTERNS = [
    r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b",   # DD/MM/YYYY or DD-MM-YYYY
    r"\b(\d{4})-(\d{2})-(\d{2})\b",          # YYYY-MM-DD
]

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

def parse_date(raw: str) -> str:
    if not raw:
        return ""
    # Try RFC 2822 (RSS standard)
    try:
        dt = parsedate_to_datetime(raw)
        return dt.date().isoformat()
    except Exception:
        pass
    # Try ISO
    for pat in DATE_PATTERNS:
        m = re.search(pat, raw)
        if m:
            groups = m.groups()
            if len(groups[0]) == 4:   # YYYY-MM-DD
                return f"{groups[0]}-{groups[1]}-{groups[2]}"
            else:                      # DD/MM/YYYY
                return f"{groups[2]}-{groups[1]}-{groups[0]}"
    return ""

def extract_last_date(text: str) -> str:
    """Look for 'last date', 'closing date', 'apply by' patterns."""
    pattern = r"(?:last date|closing date|apply before|apply by)[:\s]+([^\n<.]{5,30})"
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return parse_date(m.group(1).strip())
    return ""


# ─────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────

def clean_html(raw: str) -> str:
    """Strip tags for excerpt; keep for content."""
    return re.sub(r"<[^>]+>", " ", raw).strip()

def make_slug(title: str, source: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title + "-" + source).lower())
    return slug.strip("-")[:80]

def build_content_html(job: Dict) -> str:
    """Build a clean HTML post body from available fields."""
    parts = []

    if job.get("organisation"):
        parts.append(f'<p><strong>Organisation:</strong> {job["organisation"]}</p>')
    if job.get("category"):
        parts.append(f'<p><strong>Category:</strong> {job["category"]}</p>')
    if job.get("location"):
        parts.append(f'<p><strong>Location:</strong> {job["location"]}</p>')
    if job.get("last_date"):
        parts.append(f'<p><strong>Last Date to Apply:</strong> {job["last_date"]}</p>')
    if job.get("source_url"):
        parts.append(
            f'<p><strong>Official Notice:</strong> '
            f'<a href="{job["source_url"]}" target="_blank" rel="noopener">'
            f'View on {job["source"]}</a></p>'
        )

    summary = job.get("_raw_summary", "")
    if summary:
        parts.append("<hr>")
        # If summary is already HTML keep it; else wrap in <p>
        if re.search(r"<[a-z]+", summary):
            parts.append(summary)
        else:
            parts.append(f"<p>{summary}</p>")

    return "\n".join(parts)


# ─────────────────────────────────────────────
# Main transform function
# ─────────────────────────────────────────────

def transform_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    title   = clean_html(raw.get("raw_title", "")).strip()
    summary = raw.get("raw_summary", "")
    combined_text = f"{title} {clean_html(summary)}"

    published_at = parse_date(raw.get("raw_published", ""))

    job = {
        "guid":         raw["guid"],
        "source":       raw["source"],
        "title":        title or raw["source"],
        "slug":         make_slug(title, raw["source"]),
        "excerpt":      clean_html(summary)[:300],
        "organisation": raw["source"].split("/")[0],   # refine below
        "category":     infer_category(combined_text),
        "location":     extract_location(combined_text),
        "last_date":    extract_last_date(combined_text),
        "source_url":   raw.get("raw_link", ""),
        "published_at": published_at,
        "scraped_at":   datetime.utcnow().isoformat(),
        "tags":         [t for t in raw.get("raw_tags", []) if t],
        "_raw_summary": summary,   # kept for content builder, dropped later
    }

    # Add inferred tags
    job["tags"] = list(set(
        [job["source"], job["category"], job["location"]]
        + job["tags"]
    ))

    job["content_html"] = build_content_html(job)
    del job["_raw_summary"]   # clean up internal field
    return job


def transform_entries(raw_entries: List[Dict]) -> List[Dict]:
    jobs = []
    skipped = 0
    for raw in raw_entries:
        try:
            job = transform_entry(raw)
            if not job["title"]:
                skipped += 1
                continue
            jobs.append(job)
        except Exception as e:
            logger.warning(f"Transform error for {raw.get('guid','?')}: {e}")
            skipped += 1

    logger.info(f"Transform complete: {len(jobs)} valid, {skipped} skipped")
    return jobs
