# Blog 7-Day Rotation

One post per day, 1500-2500 words each. Every post ends with 2-3 internal
links to existing review pages (distributes link equity to money pages).

| Day | Slot | Content type | Example |
|-----|------|-------------|---------|
| Mon | comparison | "X vs Y" head-to-head | Breville Barista Express vs Barista Touch |
| Tue | price_bracket | "Best [category] under $X" | Best air fryers under $100 |
| Wed | worth_it | "Is X worth it?" | Is the Apple Watch Ultra worth it? |
| Thu | how_to | How-to / buying guide | How to choose your first espresso machine |
| Fri | comparison | "X vs Y" (second) | Nespresso Vertuo vs OriginalLine |
| Sat | seasonal | Seasonal / gift guide | Best Mother's Day gifts under $50 |
| Sun | deal_alert | Price-drop / deal roundup (ShelfWatch) | 5 kitchen gadgets that dropped 20% this week |

## Writing rules
- Slot guidance lives in `scripts/blog_writer.py` (SLOT_GUIDANCE dict).
- Internal-link targets must be real review URLs from `content/<category>/`.
- Each post: title, seo_title (≤60 chars), meta_description (≤155 chars), markdown body.
- Generate with: `python3 scripts/blog_writer.py --config scripts/blog_tasks/<date>-<slot>.json`

## Weekly cadence
7 posts/week = 1 per day. Post goes live via the normal commit → CI deploy.
