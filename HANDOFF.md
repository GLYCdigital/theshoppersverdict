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
- `briefings/_backlog/` — Pre-scraped ASINs (10 briefings usable)
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

*(Last updated: 05:15 SGT, 2026-06-22 — by ink — heartbeat poll)*

### Status: June 22 05:15 — Pre-dawn heartbeat. Queue ready for 08:00 pipeline.
- **June 18 ✅** — 10 reviews written, QA passed, committed & pushed
- **June 19 ❌** — Pipeline started (briefings consumed), attempted headed Chrome scrape — no daily batch commit
- **June 20 ❌** — Saturday — pipeline did not run at 08:00; deploy health check alerted ops group
- **June 21 ✅** — 2 reviews written (MCHOSE Laptop Stand, FLEXISPOT Bedside Table). Headed Chrome scraper broken.
- **June 22 05:15** — Pre-dawn heartbeat. No TASK_*.md pending. Pipeline will fire at 08:00 (~2h45m).

### Queue
- **Well-stocked:** ~28K ASINs across 10 categories, 303 used
- **Briefings:** 15 in `briefings/`, 6 in `_backlog/` — some unused
- **Images:** image_fill_pass_v4 completed with 0% success (Amazon blocking). v4 watchdog disabled.

### Notes
- Check MEMORY.md for long-term pending items
- Check HEARTBEAT.md for recurring tasks

---

## Last Session Summary

- **Agent:** ink
- **Checkpoint:** 03:13 SGT, 2026-06-21
- **Message:** Heartbeat poll — no TASK_*.md found. Queue healthy for 08:00 pipeline. HANDOFF updated from stale June 18 state.
