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

## Milestone — first commission
- **2026-08-11ish** — First affiliate commission after months of running + 20k+ reviews: **$0.38**. Proof of concept. Growth bet = daily blog pipeline (13:00 SGT).

## Pipeline checkpoints
Routine midnight/morning/afternoon checkpoints (HANDOFF sync) are noise and intentionally not retained here.
