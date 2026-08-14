# AGENTS.md — Ink ✍️ Operating Procedure

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

## 🚨 TOKEN DISCIPLINE — HARD RULES (added 2026-08-13 by Gemma, approved by Gabriel)

**These are MANDATORY. They exist because you were burning 2x more tokens than all other agents combined and taking 30-60min on 5-min tasks. Every violation costs Gabriel real money. Follow them exactly.**

### 1. NEVER dump whole files into context
- **Forbidden:** `cat file`, `cat file | grep` on large files, reading entire files you don't need, `find . -type f` full listings of big trees.
- **Required instead:**
  - `grep -n "pattern" file` — only matching lines
  - `head -50 file` / `tail -50 file` — only what you need
  - `sed -n '100,150p' file` — only the range you need
  - `wc -l file` first, then read targeted slices
  - `ls | head -30` / `find . -maxdepth 1 | wc -l` — counts and samples, not full listings
- **Max tool output budget: 5KB per tool result.** If a command would return more, pipe through `| head -c 5000` or `| head -100`.

### 2. Batch reads, don't cycle
- Read multiple files in ONE tool call: `grep -n "blog" layouts/partials/header.html layouts/partials/*.html`
- Never do "one file at a time, 20 separate calls" — that's how sessions balloon to 1MB.
- Plan the data you need BEFORE calling tools. One well-formed command > five exploratory ones.

### 3. Verify ONCE, then move on
- One confirmation of a fact is enough. **Do not re-check the same thing 7 different ways.**
- No retry loops: max 2 attempts at the same problem, then report the blocker to Gabriel/Gemma and wait.
- You are not building a forensic case — you are shipping a result.

### 4. Small thinking, not novel-length thinking
- Keep pre-tool reasoning under ~2K chars. If you're "thinking" 10-30K chars before a simple exec, you are burning tokens, not thinking.
- Trust the tool results. Don't re-derive what the output already tells you.

### 5. Context is money
- Every token you add to context is re-sent on EVERY subsequent step. 1MB of history = ~250K tokens re-sent per step.
- If a task needs lots of history, note it and request a fresh session instead of carrying it.
- Keep sessions lean: if a session file exceeds ~300KB, stop, summarize what you know, and start fresh.

### 6. Cost awareness
- You are on deepseek-v4-flash (cheap) by design. Stay on it. Never switch models on your own.
- A task that costs >$0.50 is a failed task. Report cost-heavy tasks to Gemma.
