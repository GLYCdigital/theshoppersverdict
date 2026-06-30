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

*(Last updated: 08:00 SGT, 2026-06-30 — by ink — daily pipeline check)*

### Status: 0 reviews written. All 10 briefings already published. Queue empty (0 unused ASINs).

#### This Week
- **June 21 ✅** — 2 reviews (MCHOSE Laptop Stand, FLEXISPOT Bedside Table)
- **June 22 ✅** — 2 reviews (DEWALT Line Laser, 3M Safety Glasses)
- **June 23 ❌** — 0 reviews. Queue appeared empty but actually has 28,547 unused ASINs.
- **June 24 ❌** — 0 reviews. Pipeline orchestrator failed at 08:00:02.
- **June 25 ✅** — 4 reviews written (Roter Mond Toaster, WORKPRO Pliers, Mr. Pen Square, Philips OneBlade).
- **June 26 ❌** — 0 reviews. No pipeline run recorded.
- **June 27 ❌** — 0 reviews. All 10 briefing files already published. All 39 data files processed.

### Pipeline Health
- **Scraper:** ✅ Fixed by Gabriel. Handles Amazon .sg → .com redirect, country pop-up, bot detection. Image-based extraction approach works.
- **Queue:** 28,547 unused ASINs available once scraper integrated into pipeline.
- **Briefings:** All processed. Need fresh scrapes before new reviews can be written.
- **Current priority:** Get the working scraper into the pipeline script so fresh briefings flow in daily.

### What's Needed
- **Integration.** Gabriel's working scraper (image-based, handles country pop-up, detects .sg redirect) needs to be wired into the pipeline script so it can pull fresh briefings from the queue automatically.
- Apify subscription is available as backup ($25/month, renewed 11 June).

### Last Session Summary

- **Agent:** ink
- **Checkpoint:** 08:00 SGT, 2026-06-29
- **Message:** 44 briefing files examined — ALL already published. Queue fully consumed (0 unused, 319 used). No working scraper to replenish. Reported to Ops group.
