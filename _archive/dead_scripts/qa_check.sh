#!/bin/bash
# 🔍 Ink QA — SEO Validation for Review Files
# Runs before git push. Checks every new/modified review for required SEO fields.
# If any fail, push is blocked and errors are reported.
#
# Usage: bash qa_check.sh [file ...]
#        If no files given, checks all .md files in content/ directories

WORKSPACE="$HOME/.openclaw/workspace"
CONTENT="$WORKSPACE/theshoppersverdict/content"
CATEGORIES="kitchen coffee home-office"

ERRORS=0
PASSED=0

# Required fields and their human-readable labels
REQUIRED_FIELDS=(
  "seo_title:SEO title (seo_title)"
  "meta_description:Meta description (meta_description)"
  "slug:URL slug (slug)"
  "image_alt:Image alt text (image_alt)"
  "keywords:Keywords list (keywords)"
  "verdict_score:Verdict score (verdict_score)"
  "amazon_image:Amazon product image (amazon_image)"
  "review_count:Review count (review_count)"
  "amazon_rating:Amazon rating (amazon_rating)"
  "price:Product price (price)"
  "amazon_url:Amazon URL (amazon_url)"
  "faq:FAQ section (faq)"
)

SEO_CHECKS=(
  "seo_title_length:seo_title ≤60 chars"
  "meta_description_length:meta_description ≤160 chars"
  "keyword_in_first_100:Primary keyword in first 100 words"
  "slug_clean:No ASIN in slug"
  "faq_questions_3:At least 3 FAQ questions"
)

check_file() {
  local file="$1"
  local basename=$(basename "$file")
  local failed=0

  # Read the YAML frontmatter (between first --- and second ---)
  local fm=$(sed -n '/^---$/,/^---$/p' "$file" | sed '1d;$d')

  echo "  🔎 $basename"

  for field_spec in "${REQUIRED_FIELDS[@]}"; do
    local field_name="${field_spec%%:*}"
    local field_label="${field_spec##*:}"

    if echo "$fm" | grep -q "^${field_name}:"; then
      # Check it's not empty — handle both inline values and multi-line YAML lists
      local inline_val=$(echo "$fm" | sed -n "/^${field_name}:/p" | sed "s/^${field_name}:[[:space:]]*//; s/^'//; s/'$//; s/^\"//; s/\"$//")
      local has_content=false
      if [ -n "$inline_val" ] && [ "$inline_val" != "[]" ]; then
        has_content=true
      fi
      # Check multi-line YAML list (e.g. keywords/faq values on lines after the field)
      local next_item=$(echo "$fm" | grep -A1 "^${field_name}:" | tail -1)
      if echo "$next_item" | grep -qE '^\s+- '; then
        has_content=true
      fi
      if ! $has_content; then
        echo "    ❌ $field_label is empty"
        failed=1
      fi
    else
      echo "    ❌ MISSING: $field_label"
      failed=1
    fi
  done

  # slug check: no ASIN prefix
  local slug=$(echo "$fm" | sed -n '/^slug:/p' | sed 's/^slug:[[:space:]]*//; s/^"//; s/"$//; s/^'"'"'//; s/'"'"'$//')
  if [ -n "$slug" ]; then
    if echo "$slug" | grep -qiE '^B0[0-9A-Z]{2,}'; then
      echo "    ❌ Slug contains ASIN prefix: '$slug'"
      failed=1
    fi
    if echo "$slug" | grep -q '_'; then
      echo "    ❌ Slug contains underscores: '$slug' (use hyphens)"
      failed=1
    fi
    if ! echo "$slug" | grep -q 'review$'; then
      echo "    ⚠️  Slug doesn't end with '-review': '$slug'"
    fi
  fi

  # seo_title length check
  local seo_title=$(echo "$fm" | sed -n '/^seo_title:/p' | sed 's/^seo_title:[[:space:]]*//; s/^"//; s/"$//; s/^'"'"'//; s/'"'"'$//')
  if [ -n "$seo_title" ] && [ ${#seo_title} -gt 60 ]; then
    echo "    ❌ seo_title is ${#seo_title} chars (max 60): '$seo_title'"
    failed=1
  fi

  # meta_description length check
  local meta_desc=$(echo "$fm" | sed -n '/^meta_description:/p' | sed 's/^meta_description:[[:space:]]*//; s/^"//; s/"$//; s/^'"'"'//; s/'"'"'$//')
  if [ -n "$meta_desc" ] && [ ${#meta_desc} -gt 160 ]; then
    echo "    ❌ meta_description is ${#meta_desc} chars (max 160)"
    failed=1
  fi

  # amazon_url affiliate tag check + LIVE ASIN VERIFICATION
  local amazon_url=$(echo "$fm" | sed -n '/^amazon_url:/p' | sed 's/^amazon_url:[[:space:]]*//; s/^"//; s/"$//; s/^'"'"'//; s/'"'"'$//')
  if [ -n "$amazon_url" ]; then
    if ! echo "$amazon_url" | grep -q '?tag=tsvglyc-20'; then
      echo "    ❌ amazon_url missing ?tag=tsvglyc-20: '$amazon_url'"
      failed=1
    fi
    if ! echo "$amazon_url" | grep -qE '^https://www\.amazon\.com/dp/'; then
      echo "    ❌ amazon_url invalid format (should start with https://www.amazon.com/dp/): '$amazon_url'"
      failed=1
    fi
    # LIVE VERIFICATION: Check the ASIN points to a real product page
    local asin=$(echo "$amazon_url" | sed 's|https://www.amazon.com/dp/||; s|?tag=tsvglyc-20||')
    if [ -n "$asin" ]; then
      local asin_check=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 \
        -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15" \
        "https://www.amazon.com/dp/$asin" 2>/dev/null)
      if [ "$asin_check" = "404" ]; then
        echo "    ❌ amazon_url ASIN $asin returns 404 — product does not exist on Amazon"
        failed=1
      fi
    fi
  fi

  # amazon_image URL validation — LIVE CHECK
  local amazon_image=$(echo "$fm" | sed -n '/^amazon_image:/p' | sed 's/^amazon_image:[[:space:]]*//; s/^"//; s/"$//; s/^'"'"'//; s/'"'"'$//')
  if [ -z "$amazon_image" ]; then
    echo "    ❌ amazon_image is empty or missing"
    failed=1
  elif ! echo "$amazon_image" | grep -qE '^https://m\.media-amazon\.com/images/'; then
    echo "    ❌ amazon_image URL doesn't look like an Amazon CDN image: $amazon_image"
    failed=1
  else
    # LIVE VERIFICATION: check the image URL returns an actual image
    local img_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -H "User-Agent: Mozilla/5.0" "$amazon_image" 2>/dev/null)
    local img_type=$(curl -s -o /dev/null -w "%{content_type}" --max-time 5 -H "User-Agent: Mozilla/5.0" "$amazon_image" 2>/dev/null)
    if [ "$img_code" != "200" ]; then
      echo "    ❌ amazon_image URL returns HTTP $img_code (not 200). Image does not exist on Amazon CDN: $amazon_image"
      failed=1
    elif ! echo "$img_type" | grep -qE '^image/'; then
      echo "    ❌ amazon_image URL returns $img_type, not an image. Invalid URL: $amazon_image"
      failed=1
    fi
  fi

  # FAQ question count
  local faq_count=$(echo "$fm" | awk 'BEGIN{c=0} /^  - question:/{c++} END{print c}')
  if [ -n "$faq_count" ] && [ "$faq_count" -gt 0 ] 2>/dev/null && [ "$faq_count" -lt 3 ] 2>/dev/null; then
    echo "    ❌ Only $faq_count FAQ questions (minimum 3)"
    failed=1
  fi

  if [ "$failed" -eq 1 ]; then
    ERRORS=$((ERRORS + 1))
  else
    PASSED=$((PASSED + 1))
    echo "    ✅ Pass"
  fi
}

echo ""
echo "══════════════════════════════════════"
echo "  🔍 Ink QA — SEO Validation"
echo "══════════════════════════════════════"
echo ""

# If files specified, check only those
if [ $# -gt 0 ]; then
  for file in "$@"; do
    if [ -f "$file" ]; then
      check_file "$file"
    else
      echo "  ⚠️  File not found: $file"
    fi
  done
else
  # Check all .md files (excluding _index.md)
  for cat in $CATEGORIES; do
    dir="$CONTENT/$cat"
    if [ -d "$dir" ]; then
      echo "📁 Category: $cat"
      for file in "$dir"/*.md; do
        [ "$(basename "$file")" = "_index.md" ] && continue
        [ -f "$file" ] && check_file "$file"
      done
      echo ""
    fi
  done
fi

echo "══════════════════════════════════════"
echo "  📊 Results: $PASSED passed, $ERRORS failed"
echo "══════════════════════════════════════"

if [ "$ERRORS" -gt 0 ]; then
  echo ""
  echo "  ❌ SEO VALIDATION FAILED — do not push until fixed."
  echo ""
  exit 1
else
  echo ""
  echo "  ✅ All reviews pass SEO validation."
  echo ""
  exit 0
fi
