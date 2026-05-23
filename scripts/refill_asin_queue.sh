#!/bin/bash
# refill_asin_queue.sh — Refills the ASIN queue with fresh Amazon products
# Now uses dynamic search scraping via replenish_queue.py
# Usage: bash refill_asin_queue.sh [--all | --category coffee] [--force]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPLENISH="$SCRIPT_DIR/replenish_queue.py"

# Default: refill all categories if below threshold
if [ $# -eq 0 ]; then
    python3 "$REPLENISH" --all
else
    python3 "$REPLENISH" "$@"
fi

echo ""
echo "=== Queue Status ==="
QUEUE="$SCRIPT_DIR/../data/asin_queue.json"
python3 -c "
import json
with open('$QUEUE') as f:
    d = json.load(f)
used = set(d.get('used', []))
for cat in ['coffee', 'kitchen', 'home-office']:
    pending = [a for a in d.get(cat, []) if a not in used]
    print(f'  {cat}: {len(pending)} pending')
"
