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

*(Last updated: 06:00 SGT, 2026-06-18 — by ink)*

- **Today's haul:** 10 reviews written, QA passed, committed and pushed ✅
  1. Keurig K155 Office Pro (coffee, 8.0/10)
  2. maxtek Dry Erase Markers (home-office, 8.5/10)
  3. YSAGi Desk Pad (home-office, 9.0/10)
  4. Chemex Pour-Over Coffeemaker (coffee, 9.2/10)
  5. Elite Gourmet Single-Serve Coffee (coffee, 8.2/10)
  6. ErGear Monitor Arm (home-office, 8.8/10)
  7. HUANUO Standing Desk (home-office, 8.8/10)
  8. Cuisinart Food Processor 14-Cup (kitchen, 9.0/10)
  9. Chefman TurboFry Air Fryer (kitchen, 8.5/10)
  10. SYOKAMI Japanese Chef Knife (kitchen, 9.0/10)

- **Queue state:** Synced — all 10 ASINs already in used list
- **Briefings used:** 3 from `briefings/` (Keurig, maxtek, YSAGi) + 7 from `briefings/_backlog/` (Chemex, Elite Gourmet, ErGear, HUANUO, Cuisinart, Chefman, SYOKAMI)
- **Next:** Need fresh scrapes; most briefings now consumed

### Notes
- Check MEMORY.md for long-term pending items
- Check HEARTBEAT.md for recurring tasks

---

## Last Session Summary

- **Agent:** ink
- **Checkpoint:** 06:00 SGT, 2026-06-18
- **Message:** 10 reviews written via parallel sub-agents. All QA passed, committed (251523e9b), pushed to main. Report sent to Ops group.
