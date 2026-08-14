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
- Each post: title, seo_title (≤60 chars), meta_description (≤155 chars), markdown body, image, faq.
- Generate with: `python3 scripts/blog_daily.py` (auto-picks topic from review corpus, never repeats used products, commits + pushes).
- Dry-run/test: `python3 scripts/blog_daily.py --dry-run` (writes to /tmp, no git).
- Affiliate + SEO blueprint (from Gemini guidance):
  - Evergreen URL slugs — no year, 3-5 words, keyword-only, no stopwords.
  - Quick Summary box with "Check Price on Amazon" button within the first 200 words (~50% of clicks).
  - Contextual text links on product names (never "click here").
  - Button copy: "Check Price on Amazon" / "View Amazon Deals" / "Check Availability" — never "Buy".
  - Comparison table with price, rating, verdict + button per item (2+ products).
  - Final Verdict section with a large full-width CTA button.
  - FAQ block in frontmatter → FAQPage schema (AI-search rich results).

## Weekly cadence
7 posts/week = 1 per day. Post goes live via the normal commit → CI deploy.
