# TASK: new reviews carry historical `date:` values

**Opened:** 2026-10-27 by Ink
**Status:** open

## Symptom
Homepage "this month" blocks rendered **"No reviews this month"** for months.
Not caused by the price drop — caused by the date field.

## Evidence
- Only **37 posts** on the whole site are dated 2026-09 or 2026-10 (25,900 total).
- All 37 are `/blog/` posts, which the homepage category whitelist excludes.
- Reviews published on 2026-10-26 carry `date: 2026-08-06` in frontmatter.

So every publlished review lands in the past and never enters any recency block
(this week / this month / today's top pick), which is the highest-intent real
estate on the homepage.

## Mitigation shipped
`layouts/index.html` now falls back to newest-by-rating instead of rendering an
empty column (commit `de3cd25e5`). That hides the symptom, it does not fix it.

## Root cause to find
The review writer sets `date:` from the briefing/scrape timestamp rather than
from publication time. Options:
1. Writer sets `date:` = publication date, keep the observed date in a separate field.
2. Homepage blocks sort by `lastmod` / file mtime instead of `date`.
3. Both — `date` is publication, `observed_at` is when facts were seen.

## Definition of done
A review published today appears in the homepage "this week" block, and its
`date:` matches the day it went live.
