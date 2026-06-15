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

*(Last updated: 08:30 SGT, 2026-06-15 — by ink)*

- **Today's haul:** 3 reviews written — eos Cashmere Shave Oil (luxury-beauty), Klein Tools Wire Cutter/Stripper (home-improvement), Klein Lineman's Pliers (home-improvement)
- **Queue state:** Synced — 10 stale ASINs moved from queue to used. Queue has ~926 unused ASINs remaining but most lack fresh data.
- **Action:** Need more fresh scrapes. Pipeline orchestrated run got 3/10 today (headed Chrome scraping). Remaining 7 slots empty — too many 404 products in queue.
- **Pipeline note:** Orchestrator works but slow (45s scrape cooldown). Yielded 3/10. Need better ASIN replenishment or pre-scraping.

### Notes
- Check MEMORY.md for long-term pending items
- Check HEARTBEAT.md for recurring tasks

---

## Last Session Summary

- **Agent:** ink
- **Checkpoint:** 08:30 SGT, 2026-06-15
- **Message:** Pipeline ran — 3 new reviews written (eos Cashmere Shave Oil, Klein Tools Wire Cutter/Stripper, Klein Lineman's Pliers). Committed and pushed. Queue synced (10 ASINs added to used). 3 of 10 target met.
