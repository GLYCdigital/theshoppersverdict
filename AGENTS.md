
## 🏠 Single Workspace
This IS the only workspace. Everything lives here:
- `content/` — Hugo site content (the deployed reviews)
- `scripts/` — Pipeline scripts (dedup, scraper, writer)
- `briefings/` — Scraped product data
- `data/` — ASIN queue, subscribers
- All paths are workspace-relative. No cross-workspace references.

## Session Startup — 每次醒来先做这些
1. **HANDOFF.md** — 检查是否有未完成的写作任务
2. **CONVERSATION_LOG.md tail（最后5行）** — 检查上次写作状态
3. **MEMORY.md** — 了解当前产品评论队列

## 📣 Telegram Handles
- **Gabriel:** @glycDigital
- **Gemma:** @GemmaGLYC_bot
- **Ops group:** GLYC Digital Ops (telegram:group:-1003250348876)

## 📝 Logging Rules
- **LOG FIRST** — Before any action or reply, append to CONVERSATION_LOG.md
- **LOG SHORT** — One line per interaction: `[HH:MM SGT] what happened`
- **DM replies** — Log every Gabriel DM before responding. LOG FIRST, LOG OR DIE.
- **LOG OR DIE** — Never skip. If this session dies mid-turn, at minimum the previous turn was saved.
- **Startup** — On fresh session, read CONVERSATION_LOG.md tail first, then MEMORY.md.
