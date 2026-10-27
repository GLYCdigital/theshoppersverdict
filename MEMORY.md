# Long-Term Memory

## Scraper Status — FIXED
- Gabriel has built a working Amazon scraper using image-based extraction.
- Handles: Amazon .sg → .com redirect, country pop-up dismissal, bot detection bypass.
- ✅ No more "scraper broken" — it works. Needs integration into the full pipeline.

## Apify Reminder (Backup)
- Apify subscription renews 11 June 2026
- Rent curious_coder/amazon-scraper before renewal to keep pipeline running
- Cost: $25/month - supports product images ("photos")
- Get it at: https://console.apify.com/actors/uzzHpNqi9keWCc5o5

## Notable past incidents
- **2026-05-18** — Gabriel flagged no reviews posted. ink_daily.sh fired at 08:00 but Signal delivered 9/10 briefings → pipeline skipped; 10th briefing arrived after 08:00 with no retry. Fixed by adding a 09:00 retry cron.
- **2026-05-24** — Daily pipeline: 12 briefings, 1 review (Breville Oracle Jet) written; 11 briefings had empty Scout data → archived to failed_empty/ (repeat failures). Queue synced.
- **2026-08-13** — Major outage fixed: the Aug 7 "26k-review LLM rewrite" deleted 7 static pages (about/contact/affiliate-disclosure/privacy-policy/terms-of-service/newsletter/search), left an unclosed `<noscript>` swallowing the homepage footer, blanked /best-of/, and stripped title/frontmatter from 7 reviews (empty /verdicts/ placeholders). All restored & deployed. Remaining blocker: Cloudflare cache purge — `wrangler pages deployment purge-cache` was removed in wrangler 4.113, and the API token has no zone access, so the homepage footer fix is still serving a stale cached copy until Gabriel purges manually or grants zone scope.
- **2026-10-27** — Discovered the **scraper has been dead since 2026-08-07** (81 days): no briefing written since, while reviews kept shipping. Only 5 of 906 briefings carried `scrapeTimestamp`; file mtime runs 27–36 days late on restored files, so staleness was invisible. Built `scripts/build_product_ledger.py` → `state/product_ledger.json` (862 records, product-family key, marketplace/currency/observed_at, explicit `ungated` list) + `state/price_history.jsonl` (append-only, 1,946 observations). Note: `data/` is scanned by Hugo and **aborts the build** on `.jsonl` — hence `state/`. Also fixed: `layouts/partials/schema.html` shipped an unconditional Product `offers` block, so **24,634 price-less pages emitted invalid schema** with a US return policy; `layouts/index.json` `$p.Summary` panic aborted the homepage render (deploy-blocking). The 1,192 stale numeric prices were dropped (`ec9b482b0`, then 7 `$`-prefixed stragglers in `309d603cd`, then 25 text values like `"Check price on Amazon"`/`N/A` in `fe4ffc20c` — they sorted into the homepage top-3 priced block as strings); 1,187 recovered from git into the history archive. **All pushed to main through `fe4ffc20c`** (built green at 25,951 pages, verified before each push). Remaining: body-prose price claims in ~477 posts (1,410 `$X` mentions) still assert stale prices; 65 pages leak raw YAML into the article body; the pre-commit hook is structurally unpassable (25,409/25,900 posts lack `faq`) and should become warning-only; auto-committer lands work under Gabriel's git identity with no agent attribution.

## Milestone — first commission
- **2026-08-11ish** — First affiliate commission after months of running + 20k+ reviews: **$0.38**. Proof of concept. Growth bet = daily blog pipeline (13:00 SGT).

## Standing rules (Gabriel)
- **Rectify immediately, never embarrass.** If a content/pipeline bug is found, fix it at the root AND clean up the shipped artifact (re-roll the bad post) in the same turn — don't wait to be asked.
- **Pre-publish tripwire** (`scripts/blog_daily.py` `validate_post()`): blocks degenerate posts (same product vs its twin listing, missing/duplicate slug) before generation, auto re-picking. Added 2026-10-16 after the STANLEY "X vs X" mirror-comparison incident.

## Pipeline checkpoints
Routine midnight/morning/afternoon checkpoints (HANDOFF sync) are noise and intentionally not retained here.
