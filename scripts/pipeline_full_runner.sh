#!/bin/bash
# Pipeline Full Runner — does everything, outputs ONE status line
# Called by Ink's cron jobs. Minimal model inference on agent side.
# Timeout: 10 min per step. Total < 20 min.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
export PATH="/opt/homebrew/bin:$PATH"

STATUS_FILE="briefings/.pipeline_status"
> "$STATUS_FILE"

log() { echo "$(date '+%H:%M:%S') $*" >> "$STATUS_FILE"; }

# ─── Orchestrator (10 min timeout) ──────────
log "Starting orchestrator..."
ORCH_OUT=$(timeout 600 python3 scripts/pipeline_orchestrator.py 2>&1) || {
  log "Orchestrator timed out or failed"
  echo "❌ Pipeline orchestrator failed. Check $STATUS_FILE"
  exit 1
}
echo "$ORCH_OUT" | tail -10
log "Orchestrator done"

# Get yield count
YIELD=$(echo "$ORCH_OUT" | grep 'Yield:' | grep -oE '[0-9]+' | head -1 || echo "?")
log "Yield: $YIELD"

if [ "$YIELD" = "0" ]; then
  # Check for pending work to commit
  git add content/ 2>/dev/null || true
  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "$(date +%Y-%m-%d): Housekeeping — pending content" 2>&1 | tail -1
    git push 2>&1 | tail -1
    echo "Pushed pending content."
  fi
  echo "0 new reviews — all briefings already processed."
  exit 0
fi

# ─── Review Writer (10 min timeout) ─────────
log "Starting review writer..."
WRITER_OUT=$(timeout 600 python3 scripts/ink_review_writer.py briefings/*_data.json 2>&1) || {
  log "Review writer failed"
  echo "⚠️ Review writer failed. Pipeline: $YIELD briefings ready. Check $STATUS_FILE"
  exit 1
}
echo "$WRITER_OUT" | tail -5
log "Writer done"

# ─── Build ───────────────────────────────────
log "Building Hugo..."
HUGO_OUT=$(hugo --minify 2>&1) || {
  log "Hugo build failed"
  echo "❌ Hugo build failed. Reviews written but not deployed."
  exit 1
}
echo "$HUGO_OUT" | tail -2
log "Build OK"

# ─── Commit and Push ─────────────────────────
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
