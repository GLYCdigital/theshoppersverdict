#!/bin/bash
# watchdog_v4.sh — Run every hour to ensure image_fill_pass_v4 is running.
# Checks if the script is alive; if not and there are still empty images, restarts it.

WORKSPACE="/Users/gabriel/.openclaw/workspace/theshoppersverdict"
cd "$WORKSPACE" || exit 1

# Count remaining empty images
REMAINING=$(grep -r 'amazon_image: ""' content/ --include="*.md" 2>/dev/null | wc -l)
REMAINING=${REMAINING// /}

echo "[$(date '+%H:%M SGT')] Watchdog: $REMAINING empty images remaining"

if [ "$REMAINING" -le 100 ]; then
    echo "[$(date '+%H:%M SGT')] Watchdog: Under 100 remaining — stopping watchdog."
    exit 0
fi

# Check if v4 is running
V4_PID=$(pgrep -f "image_fill_pass_v4.py" 2>/dev/null | head -1)

if [ -z "$V4_PID" ]; then
    echo "[$(date '+%H:%M SGT')] Watchdog: v4 not running. Restarting..."
    cd "$WORKSPACE"
    nohup python3 -u scripts/image_fill_pass_v4.py > /tmp/v4_watchdog_restart.log 2>&1 &
    echo "[$(date '+%H:%M SGT')] Watchdog: Started v4 (PID $!)"
    
    # Report via Telegram ops group
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=-1003250348876" \
        -d "text=🖋️ Watchdog: v4 script was down, restarted at $(date '+%H:%M SGT'). $REMAINING images remaining." \
        -d "disable_notification=true" > /dev/null 2>&1
else
    echo "[$(date '+%H:%M SGT')] Watchdog: v4 is running (PID $V4_PID)"
fi
