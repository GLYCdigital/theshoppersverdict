#!/bin/bash
# Pipeline Full Runner — does everything, outputs ONE status line
# Called by Ink's cron jobs.
# 0. Bestsellers seed → 1. Scrape → 2. Write → 3. QA → 4. Build → 5. Push

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
export PATH="/opt/homebrew/bin:$PATH"

STATUS_FILE="briefings/.pipeline_status"
> "$STATUS_FILE"

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
ORCH_OUT=$(run_with_timeout 900 python3 scripts/pipeline_orchestrator.py 2>&1) || {
  log "Orchestrator timed out or failed — checking for partial scrapes"
}
echo "$ORCH_OUT" | tail -10
log "Orchestrator done"

# Get yield count from orchestrator output OR from new data files
YIELD=$(echo "$ORCH_OUT" | grep 'Yield:' | grep -oE '[0-9]+' | head -1 || echo "0")

# Fallback: count today's new data files even if orchestrator was killed
if [ "$YIELD" = "0" ]; then
  TODAY=$(date +%Y-%m-%d)
  NEW_FILES=$(find briefings -name "*_data.json" -newer "$STATUS_FILE" -size +100c 2>/dev/null | wc -l | tr -d ' ')
  if [ "$NEW_FILES" -gt 0 ]; then
    log "Yield: $NEW_FILES (from partial-scrape files)"
    echo "⚠️ Orchestrator timed out but found $NEW_FILES new data files — proceeding with partial yield"
    YIELD=$NEW_FILES
  fi
fi

if [ "$YIELD" = "0" ]; then
  log "No new reviews — all ASINs in today's yield already published"
  echo "0 new reviews — all ASINs already published."
  exit 0
fi

# ─── Review Writer ─────────
log "Starting review writer..."
# Only process data files newer than pipeline start (partial yield safe)
WRITER_FILES=$(find briefings -name "*_data.json" -newer "$STATUS_FILE" -size +100c 2>/dev/null || echo "")
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

# ─── Build ─────────────────
log "Building Hugo..."
HUGO_OUT=$(hugo --minify 2>&1) || {
  log "Hugo build failed"
  echo "❌ Hugo build failed. Reviews written but not deployed."
  exit 1
}
echo "$HUGO_OUT" | tail -2
log "Build OK"

# ─── Commit and Push ───────
git add content/ 2>/dev/null || true
if git diff --cached --quiet 2>/dev/null; then
  log "Nothing to commit"
  echo "⚠️ Build OK but nothing to commit — content may be unchanged."
  exit 0
fi

git commit -m "$(date +%Y-%m-%d): Daily batch ($YIELD reviews)" 2>&1 | tail -1
git push 2>&1 | tail -1
echo "✅ $YIELD reviews written, built, and pushed."
log "Complete: $YIELD reviews"
