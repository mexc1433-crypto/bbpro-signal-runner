"""Health check endpoint for Vercel."""

from datetime import datetime, timezone
import json
import os


def handler(request):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
            "mode": "signal-only",
            "version": "v3-ultimate",
        }),
    }
