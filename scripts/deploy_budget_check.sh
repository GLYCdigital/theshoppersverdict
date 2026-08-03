#!/bin/bash
# deploy_budget_check.sh — Pre-push "deploy budget gate" for The Shopper's Verdict
#
# Cloudflare Pages (free plan) rejects deployments over 20,000 files.
# Hugo alone currently builds ~18,000 files; every review adds one. This gate
# counts the built output and FAILS before push when we're at risk, so we never
# discover the cap post-push (the silent-404 problem).
#
# Usage:
#   scripts/deploy_budget_check.sh                 # count public/ (default)
#   scripts/deploy_budget_check.sh <dir>           # count any built dir
#   scripts/deploy_budget_check.sh --warn=90 --fail=97  # custom thresholds (%)
#
# Exit codes:
#   0 = under warn threshold (OK)
#   1 = over FAIL threshold (block push)
#   2 = between warn and fail (warning only; push allowed but flagged)
#
# Same style as qa_check.sh: loud, greppable, exit-code driven.
#
# Optional alert: if TELEGRAM_BOT_TOKEN + OPS_CHAT_ID are set, sends a
# pre-push alert to the ops group when over budget (no-op otherwise).

CAP=20000
WARN_PCT=90     # warn at 90% of cap (18,000)
FAIL_PCT=97     # hard fail at 97% of cap (19,400)

for arg in "$@"; do
    case "$arg" in
        --warn=*) WARN_PCT="${arg#*=}" ;;
        --fail=*) FAIL_PCT="${arg#*=}" ;;
        -*) echo "Unknown option: $arg" >&2; exit 1 ;;
        *) TARGET="$arg" ;;
    esac
done

TARGET="${TARGET:-public}"

if [ ! -d "$TARGET" ]; then
    echo "❌ deploy_budget_check: build dir not found: $TARGET (run hugo first)"
    exit 1
fi

COUNT=$(find "$TARGET" -type f | wc -l | tr -d ' ')
WARN_LIMIT=$((CAP * WARN_PCT / 100))
FAIL_LIMIT=$((CAP * FAIL_PCT / 100))

echo "── Deploy budget gate ────────────────────────────────"
echo "  Build dir:   $TARGET"
echo "  Files:       $COUNT"
echo "  Cap:         $CAP (Cloudflare Pages free plan)"
echo "  Warn ≥:      $WARN_LIMIT (${WARN_PCT}%)"
echo "  Fail ≥:      $FAIL_LIMIT (${FAIL_PCT}%)"
echo ""

alert_ops() {
    local level="$1" msg="$2"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${OPS_CHAT_ID:-}" ]; then
        curl -s --max-time 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d chat_id="$OPS_CHAT_ID" -d parse_mode=HTML \
            -d "text=<b>🚦 Deploy budget ${level}</b> — theshoppersverdict%0A$msg" \
            >/dev/null 2>&1 || true
    fi
}

if [ "$COUNT" -ge "$FAIL_LIMIT" ]; then
    REMAIN=$((CAP - COUNT))
    echo "🚫 BLOCK: $COUNT files ≥ $FAIL_LIMIT fail threshold."
    echo "   Only $REMAIN file(s) of headroom left. Push will break the live site."
    echo "   Fix: trim taxonomy/archive pages, or plan a Cloudflare plan upgrade (Gemma)."
    alert_ops "BLOCKED" "🚫 <b>$COUNT files</b> ≥ $FAIL_LIMIT fail threshold — push would break the live site. Trim taxonomy/archive pages or upgrade the Cloudflare plan."
    exit 1
elif [ "$COUNT" -ge "$WARN_LIMIT" ]; then
    REMAIN=$((CAP - COUNT))
    echo "⚠️  WARN: $COUNT files ≥ $WARN_LIMIT warn threshold."
    echo "   $REMAIN file(s) of headroom left. Deploy still works, but plan a trim."
    alert_ops "WARNING" "⚠️ <b>$COUNT files</b> ≥ $WARN_LIMIT warn threshold — only $REMAIN file(s) of headroom left. Plan a trim soon."
    exit 2
else
    REMAIN=$((CAP - COUNT))
    echo "✅ OK: $COUNT files, $REMAIN file(s) of headroom under the ${CAP}-file cap."
    exit 0
fi
