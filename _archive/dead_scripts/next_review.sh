#!/bin/bash
# Ink 🖋️ — Review Writer Workflow
# Run this to pick up the next available briefing and write a verdict.
#
# Usage: bash next_review.sh
#
# Steps:
# 1. Finds the next unprocessed briefing in the briefings directory
# 2. Opens it for Ink to read
# 3. Ink writes the verdict markdown file
# 4. Saves to the correct category in theshoppersverdict/content/
# 5. Moves briefing to processed/

WORKSPACE="$HOME/.openclaw/workspace"
BRIEFINGS="$WORKSPACE/theshoppersverdict/briefings"
PROCESSED="$BRIEFINGS/processed"
CONTENT="$WORKSPACE/theshoppersverdict/content"
mkdir -p "$PROCESSED"

# Find next unprocessed briefing (excluding already processed ones)
NEXT=$(ls "$BRIEFINGS"/*_briefing.md 2>/dev/null | head -1)

if [ -z "$NEXT" ]; then
    echo "🖋️  No briefings found. Check if Signal has run today."
    exit 0
fi

ASIN=$(basename "$NEXT" | sed 's/_briefing.md//')
echo "🖋️  Next review: ASIN $ASIN"

# ── DEDUP CHECK: Never review the same product twice ──
DEDUP="$WORKSPACE/theshoppersverdict/scripts/dedup_check.py"
# First sync the used-ASIN list from all content files
python3 "$DEDUP" --sync 2>&1

# Now check this specific ASIN
if python3 "$DEDUP" "$ASIN"; then
    echo "✅ ASIN $ASIN is new — proceeding with review."
else
    echo "⛔ ASIN $ASIN already published. Skipping and deleting briefing."
    rm "$NEXT"
    echo "🗑️  Deleted duplicate briefing: $NEXT"
    exit 1
fi
# ──────────────────────────────────────────────────────

# ── BRIEFING VALIDATION: Skip if scrape returned no real data ──
if grep -q 'Product Briefing: Unknown' "$NEXT"; then
    echo "⛔ Briefing for $ASIN has no real product data (scrape failed). Skipping."
    mv "$NEXT" "$BRIEFINGS/failed_empty/"
    echo "🗑️  Archived to failed_empty/"
    exit 1
fi

# ── BRIEFING VALIDATION: Must have an image URL ──
if ! grep -q '| Image | https://m\.media-amazon\.com/images/' "$NEXT"; then
    echo "⛔ Briefing for $ASIN has no Amazon product image. Skipping."
    mv "$NEXT" "$BRIEFINGS/failed_empty/"
    echo "🗑️  Archived to failed_empty/"
    exit 1
fi
# ──────────────────────────────────────────────────────────

echo "📄 Briefing: $NEXT"
echo ""
echo "=== BRIEFING CONTENTS ==="
cat "$NEXT"
echo ""
echo "==========================="
echo ""
echo "🖋️  Ink, write the verdict now."
echo "   Save to: $CONTENT/<category>/<slug>.md"
echo ""
echo "Front matter template (SEO-optimised):"
echo '---'
echo 'title: "Product Name Review: [Benefit]"'
echo "seo_title: 'Product Name Review — [Keyword Hook] | The Shopper'\\''s Verdict'"
echo 'meta_description: "[160-char max. Primary keyword early.]"'
echo 'date: YYYY-MM-DD'
echo "slug: 'product-name-review'"
echo 'verdict_score: X.X'
echo 'review_count: XXXX'
echo 'amazon_rating: X.X'
echo 'amazon_url: "https://www.amazon.com/dp/ASIN/?tag=tsvglyc-20"'
echo 'amazon_image: ""'
echo "image_alt: 'Descriptive alt text with primary keyword'"
echo 'keywords:'
echo '  - "primary keyword"'
echo '  - "long-tail keyword phrase"'
echo 'pros:'
echo '  - "Pro point 1"'
echo '  - "Pro point 2"'
echo 'cons:'
echo '  - "Con point 1"'
echo '  - "Con point 2"'
echo 'faq:'
echo '  - question: "Key question about product?"'
echo '    answer: "Short keyword-rich answer."'
echo '---'
echo ''
echo '⚠️  SEO CHECKLIST:'
echo '  - seo_title set and ≤60 chars?'
echo '  - meta_description unique and ≤160 chars?'
echo '  - slug clean (no ASIN prefix, hyphens)?'
echo '  - image_alt set with primary keyword?'
echo '  - keywords list set (3-5)?'
echo '  - faq section included (3+ questions)?'
echo '  - Primary keyword in first 100 words?'
echo '  - Keyword in at least one H2?'}]}
echo ""
echo "Then run: mv \"$NEXT\" \"$PROCESSED/\""
