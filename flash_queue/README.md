# flash_queue/ — Shorts render jobs (Ink → Flash)

Ready-to-render YouTube Shorts jobs. One file per published review/post.

**Producer:** `scripts/shorts_from_review.py` (Ink)
**Consumer:** Flash's renderer — no brief, no meeting.

## Generate

```bash
# one specific post / review
python3 scripts/shorts_from_review.py content/blog/2026-11-04-<slug>.md

# newest blog posts
python3 scripts/shorts_from_review.py --recent 5

# backfill highest-value reviews (ranked by review_count × verdict_score)
python3 scripts/shorts_from_review.py --top 100

# preview without writing files
python3 scripts/shorts_from_review.py --top 10 --dry-run
```

`blog_daily.py` calls this automatically after every successful publish (non-fatal —
a failed job never blocks the post from shipping).

## Filename
`YYYY-MM-DD-<slug>.json` (date = generation date, `-2` suffix on slug collision).

## Schema `tsv.shorts.v1`

| field | notes |
|---|---|
| `slug`, `site_url`, `source_file` | source review |
| `product` / `product_full` | short VO-safe name / full marketplace title |
| `asin`, `affiliate_url` | `tag=tsvglyc-20` already injected — **use this link everywhere** |
| `product_image` | Amazon image URL from frontmatter (fallback = product image) |
| `verdict_score`, `amazon_rating`, `review_count`, `price` | may be `null` when the source lacks data |
| `hooks[3]` | 0–3s hook variants; pick one, A/B the rest |
| `beats[5]` | `{beat, t, vo, onscreen[], broll, track}` — 55s total, onscreens ≤44 chars |
| `cta` | `{vo, onscreen, url, button_text}` |
| `thumbnail_text[3]` | thumbnail text options |
| `youtube` | `{title, description, tags[], hashtags[]}` — description already has site + affiliate link |
| `status` | `ready` |

## Rules for Flash
- Never re-append the affiliate tag; `affiliate_url` is final.
- Keep the beat order; VO lines are timed to the 55s target.
- If `product_image` is empty, fall back to the site's og:image for `site_url`.
- Mark `status` → `rendered` / `failed` in place so Ink can repo progress.
