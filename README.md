# India Government Jobs Pipeline → WordPress

End-to-end pipeline that pulls vacancies from official Indian government
sources, deduplicates them, and auto-publishes them to a WordPress job board.

---

## Architecture

```
[UPSC RSS] ──┐
[SSC RSS]  ──┤
[Emp.News] ──┼── FetcherManager ── transform.py ── Database (SQLite) ── WordPressPublisher
[NCS]      ──┤         │                                  │
[data.gov] ──┤   robots.txt check                  dedup by guid
[Railways] ──┘   per source
```

---

## Quick Start

### 1. Install dependencies

```bash
cd govjobs_pipeline
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your WordPress credentials and API keys
```

### 3. Set up WordPress Application Password

1. Log into WP Admin
2. Go to **Users → Your Profile**
3. Scroll to **Application Passwords**
4. Create a new password named "GovJobs Pipeline"
5. Copy the generated password into `.env` as `WP_APP_PASSWORD`

> If using **WP Job Manager** plugin, set `WP_POST_TYPE=job_listing`
> For a standard blog, set `WP_POST_TYPE=post`

### 4. Get a free data.gov.in API key

1. Register at https://data.gov.in/user/register
2. Go to My Account → API key
3. Add to `.env` as `DATAGOVIN_API_KEY`

### 5. Test the connection

```bash
python -c "
from config import Config
from publisher import WordPressPublisher
wp = WordPressPublisher(Config())
wp.test_connection()
"
```

### 6. Dry run (fetch + transform, skip publish)

```bash
python main.py --dry-run
```

### 7. Full run

```bash
python main.py
```

---

## Scheduling

### Option A — Built-in scheduler (runs at 06:00 and 18:00 IST)

```bash
python scheduler.py
```

Keep it running with a process manager:

```bash
# Using screen
screen -S govjobs
python scheduler.py
# Ctrl+A then D to detach

# Using systemd (recommended for VPS)
# See systemd service file below
```

### Option B — System cron

```bash
crontab -e
# Add:
0 6,18 * * *  cd /path/to/govjobs_pipeline && python main.py >> /var/log/govjobs.log 2>&1
```

### Systemd service (VPS deployment)

Create `/etc/systemd/system/govjobs.service`:

```ini
[Unit]
Description=India GovJobs Pipeline
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/govjobs_pipeline
ExecStart=/usr/bin/python3 scheduler.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable govjobs
sudo systemctl start govjobs
sudo systemctl status govjobs
```

---

## WordPress setup for best results

### WP Job Manager (recommended)

1. Install **WP Job Manager** plugin (free on wordpress.org)
2. Install **WP Job Manager – Job Tags** add-on
3. Set in `.env`: `WP_POST_TYPE=job_listing`
4. The pipeline will populate all `_job_*` meta fields automatically

### Standard WordPress (no plugin)

Set `WP_POST_TYPE=post` and create a category called `government-jobs`.
All job details are in the post content as HTML.

---

## Adding new sources

1. Add a new fetcher class in `fetchers.py` inheriting logic from `RSSFetcher`
2. Add its toggle and URL to `config.py`
3. Call it inside `FetcherManager.fetch_all()`

Example for a State PSC:

```python
# In fetchers.py:
class MPSCFetcher(RSSFetcher):
    def __init__(self, cfg):
        super().__init__("MPSC", "https://mpsc.gov.in/rss.xml", cfg)

# In FetcherManager.fetch_all():
if self.cfg.ENABLE_MPSC:
    all_entries += MPSCFetcher(self.cfg).fetch()
```

---

## Database queries (audit / debug)

```bash
sqlite3 govjobs.db

-- Jobs published in the last 7 days
SELECT source, title, created_at FROM published_jobs
WHERE created_at >= datetime('now', '-7 days')
ORDER BY created_at DESC;

-- Count by source
SELECT source, COUNT(*) as total FROM published_jobs GROUP BY source;

-- Pipeline run history
SELECT * FROM pipeline_runs ORDER BY run_at DESC LIMIT 10;
```

---

## File structure

```
govjobs_pipeline/
├── main.py          ← Entry point (single run)
├── scheduler.py     ← Scheduled runner (daemon)
├── config.py        ← All settings
├── fetchers.py      ← One class per source + compliance checks
├── transform.py     ← Normalise to unified schema
├── database.py      ← SQLite dedup + audit log
├── publisher.py     ← WordPress REST API client
├── requirements.txt
├── .env.example     ← Copy to .env
└── govjobs.db       ← Auto-created on first run
```
