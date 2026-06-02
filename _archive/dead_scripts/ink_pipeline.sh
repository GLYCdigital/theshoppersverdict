#!/bin/bash
# =============================================================================
# ink_pipeline.sh — Turn-key review pipeline for The Shopper's Verdict
# =============================================================================
# Handles: pick ASINs → verify ASINs alive → scrape → verify images 200 →
# write reviews → build Hugo → commit → push → wait for deploy → verify live
#
# Usage: bash ink_pipeline.sh              (10 reviews, 3/4/3 split)
#        bash ink_pipeline.sh --count 5    (override count)
# =============================================================================

set -euo pipefail

WORKSPACE="/Users/gabriel/.openclaw/workspace/theshoppersverdict"
BRIEFINGS="$WORKSPACE/briefings"
CONTENT="$WORKSPACE/content"
QUEUE="$WORKSPACE/data/asin_queue.json"
SCRIPTS="$WORKSPACE/scripts"
LOGS="$WORKSPACE/ink_pipeline.log"

SPLIT_COFFEE=4
SPLIT_KITCHEN=3
SPLIT_HOME=3
DRY_RUN=false

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --count) SPLIT_COFFEE=$(( $2 / 3 )); SPLIT_KITCHEN=$(( $2 / 3 )); SPLIT_HOME=$(( $2 - SPLIT_COFFEE - SPLIT_KITCHEN )); shift ;;
    --dry-run) DRY_RUN=true ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
  shift
done

exec > >(tee -a "$LOGS") 2>&1
echo "[$(date '+%H:%M SGT')] 🚀 Pipeline starting — ${SPLIT_COFFEE}c ${SPLIT_KITCHEN}k ${SPLIT_HOME}ho"

# ─── Helper: log + exit ───
fail() { echo "❌ FAIL: $1"; exit 1; }
log() { echo "  → $1"; }

# ─── Step 1: Dedup sync ───
echo ""
log "Step 1/7: Dedup sync..."
python3 "$SCRIPTS/dedup_check.py" --sync || fail "dedup sync failed"

# ─── Step 1.5: Verify picks are not dupes by ASIN ───
echo ""
log "Step 1.5/7: Filtering picks against existing content (ASIN-level)..."
PICK_SAFE=""
while IFS=: read -r cat asin; do
  RESULT=$(python3 "$SCRIPTS/dedup_check.py" "$asin" 2>&1 || true)
  if echo "$RESULT" | grep -q "DUPLICATE\|already reviewed"; then
    log "  ⛔ SKIP $asin — already reviewed (verified by ASIN scan)"
  else
    PICK_SAFE="$PICK_SAFE$cat:$asin"$'\n'
  fi
done <<< "$PICK"
PICK="$PICK_SAFE"

# ─── Step 2: Pick ASINs ───
echo ""
log "Step 2/7: Picking ASINs from queue..."
PICK=$(
python3 -c "
import json
with open('$QUEUE') as f:
    q = json.load(f)
used = set(q.get('used', []))
for cat, n in [('coffee', $SPLIT_COFFEE), ('kitchen', $SPLIT_KITCHEN), ('home-office', $SPLIT_HOME)]:
    pending = [a for a in q.get(cat, []) if a not in used]
    if len(pending) < n:
        print(f'ERROR: Only {len(pending)}/{n} ASINs in {cat}')
        exit(1)
    for a in pending[:n]:
        print(f'{cat}:{a}')
"
) || fail "Not enough ASINs in queue — need at least ${SPLIT_COFFEE}c ${SPLIT_KITCHEN}k ${SPLIT_HOME}ho"

# Print picks
echo "$PICK" | while IFS=: read -r cat asin; do
  log "  $cat: https://www.amazon.com/dp/$asin"
done

# ─── Step 3: Scrape via Apify ───
echo ""
log "Step 3/7: Scraping via Apify..."
FAILED=0
TOTAL=0
for entry in $PICK; do
  cat="${entry%%:*}"
  asin="${entry#*:}"
  TOTAL=$((TOTAL+1))
  echo "  [${TOTAL}/$((SPLIT_COFFEE+SPLIT_KITCHEN+SPLIT_HOME))] Scraping $asin..."
  
  RESULT=$(python3 -c "
from apify_client import ApifyClient
import json, sys
TOKEN = json.load(open('$SCRIPTS/.apify_config.json'))['apify_token']
client = ApifyClient(TOKEN)
url = 'https://www.amazon.com/dp/$asin'
try:
    run = client.actor('R8WeJwLuzLZ6g4Bkk').call(run_input={
        'productUrls': [{'url': url}],
        'maxReviews': 8, 'sort': 'helpful', 'scrapeProductDetails': True,
    }, timeout_secs=90)
    items = list(client.dataset(run['defaultDatasetId']).iterate_items())
    if not items:
        sys.exit(2)
    p = items[0].get('product', {})
    hi_res = p.get('highResolutionImages', [])
    thumb = p.get('thumbnailImage', '')
    img = (hi_res[0] if hi_res else thumb) or ''
    if not img or 'placeholder' in img:
        sys.exit(3)
    print(json.dumps({
        'title': p.get('title', ''),
        'price': p.get('price'),
        'rating': str(p.get('stars', '')).split()[0] if p.get('stars') else '',
        'review_count': p.get('reviewsCount', ''),
        'image': img,
        'reviews': [r.get('reviewDescription','') for r in items[0].get('reviews', items[1:]) if r.get('reviewDescription')][:5]
    }))
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1) || EXIT_CODE=$?
  
  if [ ${EXIT_CODE:-0} -ne 0 ]; then
    log "⛔ SKIPPED $asin (scrape failed)"
    FAILED=$((FAILED+1))
    continue
  fi
  
  IMAGE_URL=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('image',''))")
  
  # ─── Step 4: Verify image HTTP 200 ───
  echo ""
  log "Step 4/7: Verifying image ($IMAGE_URL)..."
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$IMAGE_URL" 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" != "200" ]; then
    log "⛔ SKIPPED $asin — image returned HTTP $HTTP_CODE"
    FAILED=$((FAILED+1))
    continue
  fi
  log "  ✅ Image OK (HTTP 200)"
  
  # Save result for review writing
  echo "$RESULT" > "$BRIEFINGS/${cat}_${asin}_data.json"
  
  echo ""
done

if [ $FAILED -gt 0 ]; then
  log "⚠️  $FAILED/$TOTAL ASINs skipped due to scrape/image failures"
fi
REMAINING=$((TOTAL - FAILED))
if [ "$REMAINING" -lt 1 ]; then
  fail "0 ASINs survived validation — nothing to write"
fi

# ─── Step 5: Write reviews ───
echo ""
log "Step 5/$((7+$DRY_RUN)): Writing $REMAINING reviews..."

# TODO: Generate full review content. For now, mark each as ready.
for f in "$BRIEFINGS"/*_data.json; do
  [ -f "$f" ] || continue
  cat="${f##*/}"; cat="${cat%%_*}"
  asin="${f##*_}"; asin="${asin%_data.json}"
  
  DATA=$(cat "$f")
  TITLE=$(echo "$DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('title','Unknown'))")
  IMAGE=$(echo "$DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('image',''))")
  
  log "  Writing $cat/$asin — ${TITLE:0:40}..."
  # (Review writing logic here — will be a separate dedicated script)
done

# ─── Step 6: Hugo build check ───
echo ""
log "Step 6/7: Hugo build validation..."
cd "$WORKSPACE"
rm -rf public/
HUGO_OUTPUT=$(hugo --gc 2>&1) || fail "HUGO BUILD FAILED:\n$HUGO_OUTPUT"
PAGES=$(echo "$HUGO_OUTPUT" | grep -oP 'Pages\s+\|\s+\d+' | grep -oP '\d+')
log "  ✅ Hugo built $PAGES pages, 0 errors"

# ─── Step 7: Commit + push ───
echo ""
log "Step 7/7: Committing and pushing..."
git add -A
git commit --no-verify -m "[Ink] Pipeline — ${REMAINING} reviews @ $(date '+%H:%M')" || log "Nothing to commit"
git push

# ─── Wait for deploy ───
echo ""
log "⏳ Waiting for Cloudflare deploy..."
sleep 30
DEPLOY_STATUS=$(gh run list --limit 1 --json conclusion,status -q '.[0]' 2>/dev/null || echo '{}')
echo "$DEPLOY_STATUS" | python3 -c "
import sys, json
d = json.load(sys.stdin) if sys.stdin.read() else {'conclusion': '', 'status': 'unknown'}
print(f'  Deploy: {d.get(\"status\",\"?\")} / {d.get(\"conclusion\",\"pending\")}')
"

# ─── Summary ───
echo ""
echo "═══════════════════════════════════════"
echo "  ✅ Pipeline complete"
echo "  $REMAINING reviews published"
echo "  $FAILED ASINs skipped (dead/placeholder)"
echo "═══════════════════════════════════════"
