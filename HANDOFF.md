# HANDOFF.md — Session Bridge

> **CRITICAL: Read this on every fresh session start.**
> This is the bridge between sessions. If you don't read this, you will forget pending work.

---

## Active State — 2026-07-09 14:53 SGT

### ✅ Accomplished This Session
- **Scraper .com fix** — scrape_headed.py now forces Amazon.com (cookies + persistent context). Not .sg.
- **calc_stats.py fix** — regex fixed to count `amazon_url:` not `asin:` → site now shows 26,852 Product Verdicts
- **Breville Barista Pro review** — hand-crafted by Gabriel as quality benchmark. Every future review matches this level.
- **~30 reviews rewritten** by sub-agents (decent content, real quotes, but Gabriel said STILL TEMPLATE-ISH — do NOT batch-generate again)
- **4 reviews written properly** this session: KitchenAid Chopper, DREO Fan, WEKAPO Beach Blanket, Ninja 12-Cup Coffee Brewer. These are the quality standard.
- **Jackery Explorer 1000 v2 review** also written.

### 📋 The Plan (already decided, do not re-propose)
**Process:**
1. Scrape each ASIN from Amazon.com (one at a time, paced, 2-3 min between)
2. Write a unique, hand-crafted review from the scraped data (real quotes, specific details, honest cons, strong verdict)
3. No templates. No batch-generation. No sub-agent delegation for writing.
4. Repeat for all 26K reviews.

**Pacing:** Amazon rate-limits aggressive scraping. 2-3 minute delays between ASINs. Kill Chrome between scrapes (pkill). Fresh persistent context per scrape.

**Priority order:** Indexed pages (~146) → existing briefings (176 with data) → daily pipeline → back-catalog (26K)

### 🚫 What NOT To Do
- Do NOT re-propose approaches — everything was decided in the 32 screenshots from the previous session
- Do NOT spawn sub-agents for batch writing
- Do NOT use templates or template-like structures
- Do NOT debug the scraper extensively — it works when properly paced

### 🔧 Scraper Status
- scrape_headed.py updated with persistent Chrome context + pkill at start
- Currently rate-limited from our testing — needs ~15-30 min cooldown
- When it works: extracts 13 reviews per ASIN on average
- Use `python3 scripts/scrape_headed.py <ASIN> <category> --reviews 8`

### 📝 Workflow for Each Review
1. Pick an ASIN from briefings/*_data.json (176 with good data)
2. Read the .json (title, price, rating, review_count, reviews array)
3. Read scraped reviews to find 2-3 compelling real quotes
4. Write unique Breville-quality review (frontmatter + body)
5. Save to content/<category>/<slug>-review.md
6. Commit and push

### 📊 Stats
- 176 briefings with real review data ready to write from
- 26,852 total verdicts on the site
- ~30 rewritten by sub-agents (acceptable but not Gabriel's standard)
- Scraper fix confirmed working on .com

### ⚠️ Key Contacts
- **Gabriel:** @glycDigital (Telegram) — final say on everything
- **Gemma:** @GemmaGLYC_bot — CEO, oversees big picture
- **Ops group:** GLYC Digital Ops

### 📝 Logging
- LOG FIRST before any action
- LOG SHORT — one line per interaction
- Check CONVERSATION_LOG.md tail on startup
- Check HEARTBEAT.md for pending tasks

---

## ⏸️ SUSPENDED — 2026-08-04 23:35 SGT (Gabriel: "Stop the fix, rethink tomorrow")

**Do NOT continue the fix without Gabriel's go-ahead.** Gabriel is rethinking the approach tomorrow.

### State at stop
- ✅ Pushed to main: `951e4ba3f` (today page 4-category fix + writer `## The Verdict` removal + `static/_headers` no-cache) and `0b571bbb6` (deploy.yml wrangler purge attempt). Both deploys green.
- ✅ Verified live: /today/ shows all 10 categories; review pages have single "The Verdict" heading (210 files stripped).
- ⚠️ UNFINISHED: homepage still serves stale CDN copy (`s-maxage=604800`, 7-day cache on `/`). Purge failed (zone lookup empty; wrangler 4.113 has no purge-cache). Deeper issue found: fresh deployment 404s at root — homepage `index.html` not generated; local Hugo build breaks on `data/history/*.jsonl` (unmarshal error) — build works when data/history excluded (CI doesn't track it).
- ⚠️ UNCOMMITTED local work: CONVERSATION_LOG.md, briefings/.pipeline_status, data/asin_queue.json, data/processed_asins.json, memory/.dreams/events.jsonl + untracked briefing files. Left as-is.
- ⚠️ BILLING: DeepSeek balance ~$1.89, email monitor cron failing (billing cooldown / 402). Top-up needed soon.

### Token spend note
- DeepSeek avg: ~$1.07/day (7d), ~$0.84/day (14d). Gabriel flagged $1 over-spend during this session — keep diagnostics bounded, batch checks, avoid loops.
