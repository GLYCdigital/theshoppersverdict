#!/bin/bash
# Prime Day Continuous Runner — quality scraping for 10 categories
# Runs continuous batches: scrape → write → build → commit → push → loop
# Modified distribution: 2 per category = 20 reviews per batch
# Each batch ~35-45 min. Target: 500+ quality reviews in 48 hours.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
export PATH="/opt/homebrew/bin:$PATH"

DATE_TAG=$(date '+%Y-%m-%d')
BATCH_NUM=0
TOTAL_REVIEWS=0
START_TIME=$(date +%s)
MAX_RUNTIME=$((48 * 3600))  # 48 hours

echo "==========================================="
echo "🚀 PRIME DAY CONTINUOUS RUNNER"
echo "   Start: $(date)"
echo "   Max runtime: 48 hours"
echo "==========================================="

while true; do
  ELAPSED=$(( $(date +%s) - START_TIME ))
  if [ $ELAPSED -ge $MAX_RUNTIME ]; then
    echo "⏰ 48-hour limit reached. Stopping."
    break
  fi

  BATCH_NUM=$((BATCH_NUM + 1))
  BATCH_START=$(date '+%H:%M:%S')
  echo ""
  echo "─── Batch #$BATCH_NUM ($BATCH_START) ───"

  # ── Scrape with all 10 categories (2 each = 20 ASINs) ──
  echo "  → Running orchestrator (20 ASINs, all 10 categories)..."
  # Default distribution now includes all 10 categories (18 ASINs per batch)
  ORCH_OUT=$(timeout 600 python3 scripts/pipeline_orchestrator.py 2>&1) || {
    echo "  ⚠️ Orchestrator issue, continuing..."
  }
  echo "$ORCH_OUT" | tail -5

  # Check if any new briefing files were created
  NEW_BRIEFS=$(ls briefings/*_data.json 2>/dev/null | wc -l | tr -d ' ')
  if [ "$NEW_BRIEFS" = "0" ]; then
    echo "  ⏭️  No new briefings — queue may be empty. Sleeping 60s..."
    sleep 60
    continue
  fi

  # ── Write Reviews ──
  echo "  → Writing reviews from briefings..."
  WRITER_OUT=$(timeout 300 python3 scripts/ink_review_writer.py briefings/*_data.json 2>&1) || {
    echo "  ⚠️ Writer issue, continuing..."
  }
  echo "$WRITER_OUT" | tail -3

  # Count reviews written
  NEW_COUNT=$(echo "$WRITER_OUT" | grep -oE '^[0-9]+ reviews written' | grep -oE '[0-9]+' || echo "0")
  if [ "$NEW_COUNT" = "0" ]; then
    echo "  ⏭️  No new reviews written — all briefings already done."
    # Still try to commit in case there are pending changes
  fi
  TOTAL_REVIEWS=$((TOTAL_REVIEWS + NEW_COUNT))

  # ── Build Hugo ──
  echo "  → Building Hugo..."
  HUGO_OUT=$(hugo --minify 2>&1) || {
    echo "  ❌ Hugo build failed!"
    echo "$HUGO_OUT" | tail -3
    sleep 30
    continue
  }
  echo "  ✅ Hugo build OK"

  # ── Commit & Push ──
  git add content/ 2>/dev/null || true
  if git diff --cached --quiet 2>/dev/null; then
    echo "  ⏭️  Nothing new to commit"
  else
    git commit -m "$DATE_TAG: Prime Day batch #$BATCH_NUM ($NEW_COUNT reviews)" 2>&1 | tail -1
    git push 2>&1 | tail -1
    echo "  ✅ Pushed batch #$BATCH_NUM"
  fi

  # ── Clean up processed briefings ──
  # Move any remaining data files to processed
  mkdir -p briefings/processed
  for f in briefings/*_data.json; do
    [ -f "$f" ] && mv "$f" briefings/processed/ 2>/dev/null || true
  done

  echo "  ✅ Batch #$BATCH_NUM complete. Running total: $TOTAL_REVIEWS reviews"
  echo ""
  
  # Brief pause between batches
  sleep 5
done

echo ""
echo "==========================================="
echo "🏁 PRIME DAY RUNNER COMPLETE"
echo "   Total batches: $BATCH_NUM"
echo "   Total reviews: $TOTAL_REVIEWS"
echo "   End: $(date)"
echo "==========================================="

# Final push
git add -A
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -m "$DATE_TAG: Prime Day final batch — $TOTAL_REVIEWS total" 2>&1 | tail -1
  git push 2>&1 | tail -1
  echo "✅ Final push complete"
fi
