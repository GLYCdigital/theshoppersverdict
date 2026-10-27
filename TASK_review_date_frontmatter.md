# TASK: recency blocks on the homepage returned nothing

**Opened:** 2026-10-27 by Ink · **Corrected same night** after ink:main checked the writer
**Status:** blog whitelist FIXED · upstream cause still open

## Correction to the original diagnosis
My first version blamed the review writer for stamping the scrape date into `date:`.
**That was wrong.** `scripts/ink_llm_writer.py` writes `date: {today}` (L209/L249/L317/L325).
The August dates come from older files, not from the current writer.

## Actual causes (two, and I had only found the smaller one)
1. **`layouts/index.html` whitelisted the 10 category types but not `"blog"`.** The only
   recent content on the site is 19 October + 18 September blog posts, and every recency
   block was blind to them. **Fixed:** the recency pool is now `union $all (blog)`, and the
   fallback sorts by publish date because blog posts carry no `amazon_rating`.
   Verified: build exit 0, 25,951 pages, Editor's Favourite now shows October posts.
2. **No category reviews have been published since 2026-08-07** — zero non-blog posts carry
   a September or October date. That is the scraper/pipeline stop, not a template bug. No
   amount of date or whitelist fixing makes new reviews appear; only the pipeline restart does.

## Decision recorded
`date:` means **publication date**, one meaning per field. Fact freshness lives in the ledger
as `observed_at` / `observed_at_source` and never enters frontmatter, so restoring a price can
never rewrite a publication date. No bulk migration needed — only posts created after the
pipeline restart can affect a recency block.

## Still open
Pipeline restart (blocked on the scraper revival). Once reviews publish again, verify one lands
in "this week" on the homepage the same day.

## Fourth silent-instrument candidate
`/best-of/` — blanked once already in the Aug 7 incident. Worth rendering and eyeballing rather
than trusting that it is populated.
