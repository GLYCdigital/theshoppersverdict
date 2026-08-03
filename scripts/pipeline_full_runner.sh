#!/bin/bash
# Pipeline Full Runner — does everything, outputs ONE status line
# Called by Ink's cron jobs.
# 0. Bestsellers seed → 1. Scrape → 2. Write → 3. QA → 4. Build → 5. Push

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
export PATH="/opt/homebrew/bin:$PATH"

TODAY=$(date '+%Y-%m-%d')

# ─── Guard: skip if today's pipeline already completed ───
# Check git log for a batch commit already made today
if git log --after="$TODAY 00:00" --before="$TODAY 23:59" --oneline --grep="batch" 2>/dev/null | grep -q .; then
  echo "⏭️  $TODAY: Pipeline already ran today (batch commit found). Skipping."
  exit 0
fi

STATUS_FILE="briefings/.pipeline_status"
> "$STATUS_FILE"

# Snapshot run start time BEFORE any logging — the status file's mtime gets
# bumped by every log() line, which made `find -newer $STATUS_FILE` always
# return 0 (scraped files were older than the last log line). Use this marker
# instead so the writer actually picks up today's yield.
RUN_START=$(date '+%Y-%m-%d %H:%M:%S')

log() { echo "$(date '+%H:%M:%S') $*" >> "$STATUS_FILE"; }

# macOS doesn't ship with `timeout` — use subshell timer instead
run_with_timeout() {
  local limit=$1
  shift
  "$@" &
  local pid=$!
  ( sleep "$limit" && kill "$pid" 2>/dev/null ) &
  local killer=$!
  wait "$pid" 2>/dev/null
  local rc=$?
  kill "$killer" 2>/dev/null
  return $rc
}

# ─── Orchestrator ──────────
log "Starting orchestrator (seeds bestsellers + scrapes)..."
# No inner timeout — cron's 2700s outer timeout handles hangs
ORCH_OUT=$(python3 scripts/pipeline_orchestrator.py 2>&1) || {
  log "Orchestrator failed — checking for partial scrapes"
}
echo "$ORCH_OUT" | tail -10
log "Orchestrator done"

# Count data files from this run (reliable — counts files, not text output)
# Uses RUN_START marker, NOT $STATUS_FILE mtime (see bug note above)
YIELD=$(find briefings -name "*_data.json" -newermt "$RUN_START" -size +100c 2>/dev/null | wc -l | tr -d ' ')
if [ -z "$YIELD" ] || [ "$YIELD" = "0" ]; then
  YIELD=0
fi

if [ "$YIELD" = "0" ]; then
  log "No new reviews — all ASINs in today's yield already published"
  echo "0 new reviews — all ASINs already published."
  exit 0
fi

# ─── Review Writer ─────────
log "Starting review writer..."
# Only process data files newer than pipeline start (partial yield safe)
WRITER_FILES=$(find briefings -name "*_data.json" -newermt "$RUN_START" -size +100c 2>/dev/null || echo "")
if [ -z "$WRITER_FILES" ]; then
  WRITER_FILES="briefings/*_data.json"
fi
WRITER_OUT=$(run_with_timeout 600 python3 scripts/ink_review_writer.py $WRITER_FILES 2>&1) || {
  log "Review writer failed"
  echo "⚠️ Review writer failed. Pipeline: $YIELD briefings ready. Check $STATUS_FILE"
  exit 1
}
echo "$WRITER_OUT" | tail -5
log "Writer done"

# ─── ShelfWatch snapshot ───
# Append today's fresh scrape data to the price/rating history store (data/history/).
# This accumulates the time-series that powers the ShelfWatch category-intelligence
# product — without it, "movement" reports have no data. Runs on briefings + the
# processed dir (writer may have moved files already).
if [ -x scripts/shelfwatch.py ]; then
    SNAP_IN="$WRITER_FILES"
    if [ -d briefings/processed ] && [ -n "$(ls briefings/processed/*_data.json 2>/dev/null)" ]; then
        SNAP_IN="$SNAP_IN briefings/processed"
    fi
    SNAP_OUT=$(python3 scripts/shelfwatch.py --snapshot $SNAP_IN 2>&1) || true
    echo "$SNAP_OUT" | tail -1
    log "ShelfWatch snapshot: $SNAP_OUT"
fi

# ─── Commit and Push ───────
# Local build skipped — Cloudflare Pages CI handles it (Mac OOMs on 30K pages)
git add content/ 2>/dev/null || true
if git diff --cached --quiet 2>/dev/null; then
  log "Nothing to commit"
  echo "⚠️ Writer ran but nothing to commit — content may be unchanged."
  exit 0
fi

git commit -m "$TODAY: Daily batch ($YIELD reviews)" 2>&1 | tail -1

# ─── Deploy budget gate (pre-push) ───
# Cloudflare Pages rejects >20K files. If the gate blocks, keep the commit
# but alert ops — never push blind into a silent 404.
if [ -x scripts/deploy_budget_check.sh ]; then
    if [ -d public ]; then
        GATE_RC=0
        scripts/deploy_budget_check.sh || GATE_RC=$?
        if [ "$GATE_RC" -ge 1 ]; then
            echo "🚫 Deploy budget gate BLOCKED push — fix trim or plan upgrade first."
            log "Deploy budget gate BLOCKED ($GATE_RC)"
            exit 1
        elif [ "$GATE_RC" -eq 2 ]; then
            echo "⚠️ Deploy budget warning — pushing anyway, but plan a trim."
            log "Deploy budget WARNING"
        fi
    else
        echo "ℹ️ No local public/ build — skipping pre-push budget gate (CI will gate)."
    fi
fi

git push 2>&1 | tail -1
echo "✅ $YIELD reviews written and pushed (Cloudflare CI builds)."
log "Complete: $YIELD reviews pushed to main"
