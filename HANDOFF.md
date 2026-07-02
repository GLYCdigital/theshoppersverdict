# HANDOFF.md — Session Bridge

> **CRITICAL: Read this on every fresh session start.**
> This is the bridge between sessions. If you don't read this, you will forget pending work.

---

## Single Workspace (2026-06-30)

Everything lives here — Hugo content, pipeline scripts, briefings, queue, and agent config.

### Key paths (all workspace-relative)
- `scripts/fetch_bestsellers.py` — Pulls live Amazon bestseller ASINs
- `scripts/scrape_headed.py` — Gabriel's working headed Chrome scraper
- `scripts/pipeline_orchestrator.py` — Full pipeline orchestrator
- `scripts/pipeline_full_runner.sh` — Cron runner
- `scripts/ink_review_writer.py` — Review writer
- `scripts/dedup_check.py` — ASIN dedup
- `data/asin_queue.json` — ASIN queue
- `briefings/` — Scraped product data

### Pipeline Flow (wired and tested)
```
🌱 Seed → Fetch Amazon bestsellers → prepend to front of queue
🔍 Pre-filter → curl check (skip dead ASINs in ~2s)
🖋️ Scrape → Headed Chrome (scrape_headed.py)
📝 Write → ink_review_writer.py
✅ QA → Pre-commit validation
🚀 Push → Commit and deploy to main
```

### Cron
| Time | Job | Delivery |
|------|-----|----------|
| 08:00 | Full pipeline (1800s timeout) | Ops group |
| 08:45 | Health check | Ops group |
| 09:00 | Auto-retry (1800s timeout) | Ops group |

Pipeline auto-replenishes: if any category has < 10 pending, it fetches fresh bestsellers.

---

## Status

### ✅ Working
- **Scraper:** Gabriel's headed Chrome scraper — handles country pop-ups, bot checks, image verification
- **Bestseller fetch:** Pulls live ASINs from Amazon bestseller pages per category
- **Queue:** 29,022 pending ASINs across 10 categories
- **Pre-filter:** curl HTTP 200 check — skips dead/404 ASINs instantly
- **Full pipeline:** Proven end-to-end 2026-06-30 (3 reviews written and pushed)

### Last Session Summary
- **Date:** 2026-06-30
- **Agent:** ink
- **Done:**
  - Wired `fetch_bestsellers.py` as pipeline step 0 (prepends fresh ASINs)
  - Added pre-filter curl liveness check to orchestrator
  - Auto-replenish when queue runs low
  - Cron timeouts bumped to 1800s
  - Published 3 reviews from fresh bestseller ASINs
  - No more "scraper broken" — scraper works, process works
## Status

### ✅ Working
- **Scraper:** Gabriel's headed Chrome scraper — handles country pop-ups, bot checks, image verification
- **Bestseller fetch:** Pulls live ASINs from Amazon bestseller pages per category
- **Queue:** 29,020 pending ASINs across 10 categories
- **Pre-filter:** curl HTTP 200 check — skips dead/404 ASINs instantly
- **Full pipeline:** Works but queue ASINs tend to be dead; manual liveness check needed

### Last Session Summary
- **Date:** 2026-07-02
- **Agent:** ink
- **Done:**
  - Published 10 fresh reviews (manual scrape + write)
  - Killed stuck 08:00 pipeline (in sleep cooldown, producing nothing)
  - Fixed Hugo lang.NumFmt → FormatNumber deprecation in header & trust-bar templates
  - All 10 reviews passed pre-commit QA, committed (8ff377490), pushed to main
  - Cloudflare Pages CI handles build & deploy

### Known Issues
- Many queue ASINs are discontinued/dead — pre-filter curl test often insufficient
- Hugo build takes very long on Mac (20K+ pages) — CI handles it
- Pipeline's sleep cooldowns too aggressive for Singapore IP to Amazon.com access
