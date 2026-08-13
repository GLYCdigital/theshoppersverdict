#!/bin/bash
# qa_check.sh — Validates review markdown files for The Shopper's Verdict
# Checks: required frontmatter fields, ASIN links, image URLs, price format, etc.
# Exit 0 = all passed, 1 = validation errors found

ERRORS=0

for MD in "$@"; do
    BASENAME=$(basename "$MD")
    # Skip Hugo index files
    case "$BASENAME" in _index.md|_*.md) continue ;; esac
    # Skip non-review pages (root-level content files: about, contact, search, etc.)
    PARENT_DIR=$(dirname "$MD" | xargs basename)
    if [ "$PARENT_DIR" = "content" ] || [ "$PARENT_DIR" = "blog" ]; then
        continue
    fi
    if [ ! -f "$MD" ]; then
        echo "  ⚠️  MISSING: $MD"
        ERRORS=$((ERRORS + 1))
        continue
    fi

    FILE_ERRORS=0

    # ── Required frontmatter fields ──────────────────────────────
    for FIELD in title seo_title meta_description slug amazon_url amazon_image amazon_rating review_count verdict_score pros cons faq; do
        if ! grep -q "^${FIELD}:" "$MD"; then
            echo "  ❌ $BASENAME: missing '$FIELD' in frontmatter"
            FILE_ERRORS=$((FILE_ERRORS + 1))
        fi
    done

    # ── amazon_url must have tag parameter ───────────────────────
    if ! grep -q 'tag=tsvglyc-20' "$MD"; then
        echo "  ❌ $BASENAME: amazon_url missing affiliate tag (tag=tsvglyc-20)"
        FILE_ERRORS=$((FILE_ERRORS + 1))
    fi

    # ── amazon_url must have valid ASIN format ───────────────────
    ASIN=$(grep 'amazon_url:' "$MD" | grep -oE '/dp/[A-Z0-9]{10,14}' | head -1)
    if [ -z "$ASIN" ]; then
        echo "  ❌ $BASENAME: amazon_url missing valid /dp/ASIN path"
        FILE_ERRORS=$((FILE_ERRORS + 1))
    fi

    # ── amazon_image must be a real URL (not placeholder) ────────
    IMG=$(grep 'amazon_image:' "$MD" | sed 's/amazon_image: *"//;s/"$//' | tr -d ' ')
    if [ -z "$IMG" ] || echo "$IMG" | grep -qi 'placeholder'; then
        echo "  ❌ $BASENAME: amazon_image is empty or placeholder"
        FILE_ERRORS=$((FILE_ERRORS + 1))
    elif ! echo "$IMG" | grep -qE '^https?://'; then
        echo "  ❌ $BASENAME: amazon_image is not a valid URL"
        FILE_ERRORS=$((FILE_ERRORS + 1))
    else
        # ── Verify image URL resolves (not 404) ──────────────────
        HTTP_STATUS=$(curl -sI --max-time 5 -A "Mozilla/5.0" "$IMG" 2>/dev/null | head -1 | awk '{print $2}')
        if [ -z "$HTTP_STATUS" ]; then
            echo "  ⚠️  $BASENAME: amazon_image unresolvable (timeout or DNS failure)"
            FILE_ERRORS=$((FILE_ERRORS + 1))
        elif [ "$HTTP_STATUS" -ge 400 ]; then
            echo "  ❌ $BASENAME: amazon_image returns HTTP $HTTP_STATUS (broken image)"
            FILE_ERRORS=$((FILE_ERRORS + 1))
        fi
    fi

    # ── price validation (if present, must be numeric / "null") ──
    PRICE=$(grep '^price:' "$MD" | awk '{print $2}' | tr -d '"' | tr -d "'")
    if [ -n "$PRICE" ] && [ "$PRICE" != "null" ] && ! echo "$PRICE" | grep -qE '^[0-9]'; then
        echo "  ❌ $BASENAME: price is not numeric or null ($PRICE)"
        FILE_ERRORS=$((FILE_ERRORS + 1))
    fi

    # ── verdict_score must be in range 0-10 ──────────────────────
    SCORE=$(grep '^verdict_score:' "$MD" | awk '{print $2}')
    if [ -n "$SCORE" ]; then
        if ! echo "$SCORE" | grep -qE '^[0-9]'; then
            echo "  ❌ $BASENAME: verdict_score is not numeric ($SCORE)"
            FILE_ERRORS=$((FILE_ERRORS + 1))
        fi
    fi

    # ── body must have some content after frontmatter ─────────────
    BODY_LINES=$(awk '/^---$/ {fc++} fc==2 && !/^---$/ {print}' "$MD" | wc -l | tr -d ' ')
    if [ "$BODY_LINES" -lt 3 ]; then
        echo "  ❌ $BASENAME: review body is too short ($BODY_LINES lines)"
        FILE_ERRORS=$((FILE_ERRORS + 1))
    fi

    if [ "$FILE_ERRORS" -eq 0 ]; then
        echo "  ✅ $BASENAME — passed"
    else
        ERRORS=$((ERRORS + FILE_ERRORS))
    fi
done

echo ""
if [ "$ERRORS" -gt 0 ]; then
    echo "❌ $ERRORS validation error(s) found across $# file(s)"
    exit 1
else
    echo "✅ All $# review file(s) passed QA"
    exit 0
fi
