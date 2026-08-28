"""
صياد الشمعات | Candle Hunter - Signal Forwarder
يبعت الإشارات لبوت التداول التلقائي عبر HTTP API
"""
import logging
import os
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class SignalForwarder:
    """يوجّه الإشارات من بوت التوصيات إلى بوت التداول"""

    def __init__(self):
        self.trade_bot_url = os.getenv("TRADE_BOT_URL", "")
        self.secret = os.getenv("SIGNAL_BOT_SECRET", "bbpro-secret-2026")

    def is_configured(self) -> bool:
        """هل بوت التداول مضبوط؟"""
        return bool(self.trade_bot_url)

    async def forward_signal(self, signal: Dict) -> Dict:
        """إرسال الإشارة لبوت التداول"""
        if not self.is_configured():
            logger.debug("Trade bot URL not set — skipping forward")
            return {"success": False, "error": "not_configured"}

        payload = {
            "signal_type": signal.get("signal_type", ""),
            "strategy_name": signal.get("strategy_name", ""),
            "entry_price": signal.get("entry_price", 0),
            "stop_loss": signal.get("stop_loss", 0),
            "take_profit_1": signal.get("take_profit_1", 0),
            "take_profit_2": signal.get("take_profit_2", 0),
            "take_profit_3": signal.get("take_profit_3", 0),
            "confidence": signal.get("confidence", 0),
            "timeframe": signal.get("timeframe", ""),
            "symbol": signal.get("symbol", "XAU/USD"),
            "secret": self.secret,
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                url = f"{self.trade_bot_url}/signal"
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.info(f"📡 Signal forwarded to trade bot: {payload['signal_type']}")
                    return {"success": True, "response": resp.json()}
                else:
                    logger.error(f"Trade bot error: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.error(f"Error forwarding signal: {e}")
            return {"success": False, "error": str(e)}
