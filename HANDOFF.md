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
