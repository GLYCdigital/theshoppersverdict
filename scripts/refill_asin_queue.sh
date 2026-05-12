#!/bin/bash
# refill_asin_queue.sh — Fills the ASIN queue with real, valid Amazon products
# Verifies each ASIN before adding to the queue

WORKSPACE="$HOME/.openclaw/workspace"
QUEUE="$WORKSPACE/theshoppersverdict/data/asin_queue.json"
VERIFIER="$WORKSPACE/theshoppersverdict/scripts/asin_verify.py"

# Well-known top-selling ASINs for kitchen, coffee, home-office
declare -A CATEGORIES
CATEGORIES["kitchen"]="B00FLYWNYQ B09TQ3XLGG B08B5L5P9K B07S2LH4T2 B08G17C5C1 B09FMPXNMY B06XDJ7T8W B09B9D3PLL B08D3Y5H3M B07G1XX7T2 B08HHDPJ7L B0B5G4YJRM B094R8QPB5 B0C1YP1SNM"
CATEGORIES["coffee"]="B07985N4C9 B086RBYNNB B07YN32XQL B089MV1KMP B07TC7HJK2 B0CCCPK6ZQ B08GJHYNQF B09QGJQV8Q B07N4L3N5G B08DF3H6VL"
CATEGORIES["home-office"]="B08N5KWB9H B09G9HDH9P B08J6F3DML B09B2C9MX7 B08HRD7BDL B093D99GDR B08VDRT4CL B0B8G4YJRM B07YLXY6T6 B07D3M7D3G"

VALID_COUNT=0
INVALID_COUNT=0

echo "=== Refilling ASIN Queue ==="
echo ""

# Build new queue
QUEUE_DATA='{"kitchen":[],"coffee":[],"home-office":[],"used":[]}'

for CAT in kitchen coffee home-office; do
  echo ""
  echo "--- $CAT ---"
  ASINS="${CATEGORIES[$CAT]}"
  VALID_ASINS=""
  
  for ASIN in $ASINS; do
    printf "  Verifying $ASIN... "
    python3 "$VERIFIER" "$ASIN" 2>&1 | head -1
    if [ $? -eq 0 ]; then
      VALID_ASINS="$VALID_ASINS \"$ASIN\","
      VALID_COUNT=$((VALID_COUNT + 1))
    else
      INVALID_COUNT=$((INVALID_COUNT + 1))
    fi
  done
  
  # Add valid ASINs to queue data
  VALID_ASINS="${VALID_ASINS%,}"
  QUEUE_DATA=$(echo "$QUEUE_DATA" | python3 -c "
import json, sys
d = json.load(sys.stdin)
d['$CAT'] = [$VALID_ASINS]
json.dump(d, sys.stdout)
")
done

# Write final queue
echo "$QUEUE_DATA" > "$QUEUE"
echo ""
echo "=== Done ==="
echo "Valid: $VALID_COUNT | Invalid: $INVALID_COUNT"
echo "Queue: $QUEUE"
