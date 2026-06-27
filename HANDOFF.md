# HANDOFF.md — Session Bridge

> **CRITICAL: Read this on every fresh session start.**
> This is the bridge between sessions. If you don't read this, you will forget pending work.

---

## Single Workspace (2026-06-02)

The ink and theshoppersverdict workspaces have been merged. This IS the only workspace.
Everything lives here — Hugo content, pipeline scripts, briefings, queue, and agent config.

### Key paths (all workspace-relative)
- `scripts/dedup_check.py` — ASIN dedup (check + sync)
- `scripts/replenish_queue.py` — Queue replenisher
- `scripts/ink_review_writer.py` — Review writer
- `data/asin_queue.json` — ASIN queue + used list
- `briefings/_backlog/` — Pre-scraped ASINs
- `reviews/_backlog/` — Pre-written draft reviews
- `_archive/` — Dead scripts, old tasks, archived briefings

### Cron safety net
| Time | Job | Delivery |
|------|-----|----------|
| 08:00 | Full pipeline (900s) | Ops group |
| 08:45 | Health check | Ops group |
| 09:00 | Auto-retry if 08:00 failed | Ops group |

---

## Pending

*(Last updated: 08:00 SGT, 2026-06-27 — by ink — daily pipeline check)*

### Status: 0 reviews written. All data files exhausted.

#### This Week
- **June 21 ✅** — 2 reviews (MCHOSE Laptop Stand, FLEXISPOT Bedside Table)
- **June 22 ✅** — 2 reviews (DEWALT Line Laser, 3M Safety Glasses)
- **June 23 ❌** — 0 reviews. Queue appeared empty but actually has 28,547 unused ASINs.
- **June 24 ❌** — 0 reviews. Pipeline orchestrator failed at 08:00:02.
- **June 25 ✅** — 4 reviews written (Roter Mond Toaster, WORKPRO Pliers, Mr. Pen Square, Philips OneBlade).
- **June 26 ❌** — 0 reviews. No pipeline run recorded.
- **June 27 ❌** — 0 reviews. All 10 briefing files already published. All 39 data files processed.

### Pipeline Health — CRITICAL
- **Scraper:** Still broken (Amazon blocks Headed Chrome). No working scraper available.
- **Queue:** 28,547 unused ASINs across 10 categories — plenty of product targets, but no way to scrape them.
- **Briefings:** All 39 data files processed. 36 have existing reviews in content/. 3 are dead/404 or empty scrapes.
- **Image fill:** image_fill_pass_v4 still 0% success.
- **Available scraper:** `scripts/scrape_asin_cdp.py` exists (CDP/TradingView-based) but is NOT integrated into the orchestrator.

### Pipeline Health — CRITICAL
- **Scraper:** Still broken (Amazon blocks Headed Chrome). No working scraper available.
- **Queue:** 28,547 unused ASINs across 10 categories — plenty of product targets, but no way to scrape them.
- **Briefings:** All 33 data files processed. 30 have existing reviews in content/. 3 are dead/404.
- **Image fill:** image_fill_pass_v4 still 0% success.
- **Available scraper:** `scripts/scrape_asin_cdp.py` exists (CDP/TradingView-based) but is NOT integrated into the orchestrator.

### What's Needed
- **Working scraper.** The queue is full of ASINs (28K+) but we can't scrape any of them.
- `scrape_asin_cdp.py` uses TradingView's headed browser — could bypass Amazon's bot detection. Needs integration into the pipeline.
- Apify subscription may also be a path (renewed 11 June — $25/month).
- Until we have a working scraper, the pipeline produces 0 reviews daily.

### Last Session Summary

- **Agent:** ink
- **Checkpoint:** 08:00 SGT, 2026-06-27
- **Message:** 10 briefing files examined — all already published in prior batches. Zero new reviews to write. All 39 scraped data files processed (36 reviews exist, 3 are dead/empty). 28K+ ASINs in queue but no working scraper. Reported to Ops group.
