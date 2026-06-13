# HANDOFF.md — Session Bridge

> **CRITICAL: Read this on every fresh session start.**
> This is the bridge between sessions. If you don't read this, you will forget pending work.

---

## Single Workspace (2026-06-02)

The ink and theshoppersverdict workspaces have been merged. This IS the only workspace.
Everything lives here — Hugo content, pipeline scripts, briefings, data, and agent config.

### Key paths (all workspace-relative)
- `scripts/dedup_check.py` — ASIN dedup (check + sync)
- `scripts/replenish_queue.py` — Queue replenisher
- `scripts/ink_review_writer.py` — Review writer
- `data/asin_queue.json` — ASIN queue + used list
- `briefings/_backlog/` — Pre-scraped ASINs (18 candidates)
- `reviews/_backlog/` — Pre-written draft reviews (4 candidates)
- `_archive/` — Dead scripts, old tasks, archived briefings

### Cron safety net
| Time | Job | Delivery |
|------|-----|----------|
| 08:00 | Full pipeline (900s) | Ops group |
| 08:45 | Health check | Ops group |
| 09:00 | Auto-retry if 08:00 failed | Ops group |

---

## Pending

*(Last updated: 08:00 SGT, 2026-06-13 — by ink)*

- **Today's haul:** 0 new reviews — all 10 briefings already had reviews written. 1 pending review from yesterday (Schick Hydro Silk dermaplane) committed and pushed.
- **Queue state:** 930 pending ASINs across all categories. 280 used. Pipeline needs fresh scrapes.
- **Action:** Need new ASIN scrapes run. Queue is stale — mostly 404 dead products.
- **Pipeline issue:** scrape_asin.py still needs permanent fix for Apify format drift.

### Notes
- Check MEMORY.md for long-term pending items
- Check HEARTBEAT.md for recurring tasks

---

## Last Session Summary

- **Agent:** ink
- **Checkpoint:** 08:00 SGT, 2026-06-13
- **Message:** Pipeline ran — 0 new reviews (all briefings already processed). 1 pending review (Schick Hydro Silk) committed. 930 pending ASINs need scraping. HANDOFF refreshed.
