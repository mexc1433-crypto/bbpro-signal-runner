#!/bin/bash
# ============================================================
# BBPro Signal Bot — Start Script (Termux)
# ============================================================

BOT_DIR="$HOME/bbpro-signal-bot"
cd "$BOT_DIR"

# Load .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Wake lock
termux-wake-lock 2>/dev/null

# Start with auto-restart
MAX_RETRIES=50
RETRY_DELAY=30

for i in $(seq 1 $MAX_RETRIES); do
    echo "[$(date)] Starting BBPro Signal Bot (attempt $i/$MAX_RETRIES)..."
    python -O bot/main.py
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date)] Bot stopped normally."
        break
    fi
    echo "[$(date)] Bot crashed (exit code: $EXIT_CODE). Retrying in ${RETRY_DELAY}s..."
    sleep $RETRY_DELAY
done
