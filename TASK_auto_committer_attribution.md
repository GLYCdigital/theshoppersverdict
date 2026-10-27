# TASK: Auto-committer attribution

**Opened:** 2026-10-27 by Ink
**Status:** open — needs owner decision

## Problem
A process auto-commits working-tree changes under **Gabriel Leong <glycdigital@gmail.com>**.
On 2026-10-27 it landed `6695b52ef` (Art's schema fix) and other agents' edits under Gabriel's
name, mid-session, without any agent claiming the commit.

Result: git history answers *what* changed but not *who did it or why* — the exact
forensic gap that made the 81-day scraper outage hard to date.

## Evidence
- `git reflog --date=iso` shows commits at 20:16 and 20:24 today authored by Gabriel's identity
  during a session where neither Ink nor Art deliberately committed those paths.
- `6695b52ef` (schema.html offers gate) belongs to Art; `ec9b482b0` (price drop) belongs to ink:main.

## Options
1. **Trailer (cheapest):** auto-committer appends `Agent: <name>` + `Task: <ticket>` trailer.
2. **Stop auto-committing:** require deliberate commits with an agent-set identity.
3. **Per-agent git identity:** set `user.name`/`user.email` per workspace so `git log` is honest.

Recommend option 1 + 3 together: trailer preserves intent, identity preserves attribution.

## Definition of done
`git log --format="%an | %s | %(trailers)"` on any automated commit names the acting agent.
