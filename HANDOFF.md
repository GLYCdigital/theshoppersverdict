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

*(Last updated: 20:10 SGT, 2026-06-08 — by ink)*

- **Backlog:** 18 pre-scraped briefing files in `briefings/_backlog/` (ready for review writing)
- **Backlog:** 4 pre-written reviews in `reviews/_backlog/` (ready for formatting/publishing)
- **Action:** Gabriel must update OpenClaw agent workspace config from `ink` → `theshoppersverdict`

### Notes
- Check MEMORY.md for long-term pending items
- Check HEARTBEAT.md for recurring tasks

---

## Last Session Summary

- **Agent:** ink
- **Checkpoint:** 20:10 SGT, 2026-06-08
- **Message:** Pipeline ran today — 10 reviews written (commit 06b415a). No TASK files pending. Backlog stands at 18 briefings + 4 reviews. HANDOFF refreshed.
