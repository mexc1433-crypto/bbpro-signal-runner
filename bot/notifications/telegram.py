"""
notifications/telegram.py - BBPro Signal Bot (Ultimate Edition)

Signal-only mode: sends trade recommendations with inline buttons.
Features:
  - Formatted signal message with R:R ratio
  - Support/Resistance levels in message
  - Inline buttons for tracking results
  - Pre-signal alerts
  - Signal result notifications
  - Daily/weekly performance reports
"""

import logging
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class TelegramNotifier:
    API_BASE = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled and bool(bot_token) and bool(chat_id) and HAS_REQUESTS
        if self.enabled:
            logger.info("Telegram notifier enabled (chat_id=%s)", chat_id)
        else:
            logger.info("Telegram notifier disabled")

    def send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.enabled:
            return False
        url = self.API_BASE.format(token=self.bot_token, method="sendMessage")
        payload = {"chat_id": self.chat_id, "text": text,
                   "parse_mode": parse_mode, "disable_web_page_preview": True}
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code != 200:
                logger.warning("Telegram send failed: %s %s", r.status_code, r.text[:200])
                return False
            return True
        except Exception as e:
            logger.warning("Telegram send error: %s", e)
            return False

    async def send_async(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.enabled:
            return False
        return await asyncio.to_thread(self.send, text, parse_mode)

    def format_price(self, symbol: str, value) -> str:
        if not isinstance(value, (int, float)):
            return str(value)
        su = symbol.upper()
        if "JPY" in su:
            return f"{value:.3f}"
        if "XAU" in su or "GOLD" in su:
            return f"{value:.2f}"
        if "XAG" in su:
            return f"{value:.3f}"
        return f"{value:.4f}"

    # ── Main signal message ─────────────────────────────────────────────
    def send_signal(self, symbol: str, side: str, entry_price: float,
                    sl_price: float, tp_price: float,
                    score: float = 0, ai_confidence: int = 0,
                    rr_ratio: float = 0, strategy: str = "",
                    sr_text: str = "", signal_id: str = "") -> bool:
        """
        Sends a trade recommendation:
        XAUUSD BUY NOW 4422🌟
        SL : 4413
        TP : 4430
        R:R = 1:1.8 ✅
        ⚠️ مقاومة عند 4435
        📊 Strategy: Breakout | Score: 85 | AI: 75%
        """
        star = "🌟"
        side_str = "BUY" if side.upper() == "BUY" else "SELL"

        price_str = self.format_price(symbol, entry_price)
        sl_str = self.format_price(symbol, sl_price)
        tp_str = self.format_price(symbol, tp_price)

        # Calculate pips
        pip_map = {"XAUUSD": 0.1, "XAGUSD": 0.01, "USDJPY": 0.01, "EURJPY": 0.01, "GBPJPY": 0.01}
        pip = pip_map.get(symbol.upper(), 0.0001)
        sl_pips = abs(entry_price - sl_price) / pip
        tp_pips = abs(tp_price - entry_price) / pip

        # R:R ratio
        rr_str = ""
        if rr_ratio > 0:
            rr_emoji = "✅" if rr_ratio >= 1.5 else "⚠️"
            rr_str = f"\nR:R = 1:{rr_ratio:.1f} {rr_emoji}"

        # Strategy info
        strat_str = ""
        parts = []
        if strategy:
            parts.append(f"📋 {strategy}")
        if score > 0:
            parts.append(f"Score: {score:.0f}")
        if ai_confidence > 0:
            parts.append(f"AI: {ai_confidence}%")
        if parts:
            strat_str = f"\n📊 {' | '.join(parts)}"

        # S/R levels
        sr_str = f"\n{sr_text}" if sr_text else ""

        # Pips info
        pips_str = f"\nSL: {sl_pips:.0f} pips | TP: {tp_pips:.0f} pips"

        msg = (
            f"{symbol.upper()} {side_str} NOW {price_str}{star}\n"
            f"SL : {sl_str}\n"
            f"TP : {tp_str}"
            f"{pips_str}"
            f"{rr_str}"
            f"{sr_str}"
            f"{strat_str}"
        )

        # Send with inline buttons if enabled
        if signal_id:
            return self.send_with_buttons(msg, signal_id, symbol, side)
        return self.send(msg)

    def send_with_buttons(self, text: str, signal_id: str, symbol: str, side: str) -> bool:
        """Send message with inline keyboard buttons for tracking."""
        if not self.enabled:
            return False

        url = self.API_BASE.format(token=self.bot_token, method="sendMessage")
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ نجحت", "callback_data": f"win_{signal_id}"},
                {"text": "❌ خسرت", "callback_data": f"loss_{signal_id}"},
                {"text": "⏰ مفتوحة", "callback_data": f"open_{signal_id}"},
            ]]
        }
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": keyboard
        }
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code != 200:
                logger.warning("Telegram button send failed: %s", r.text[:200])
                # Fallback to plain message
                return self.send(text)
            return True
        except Exception as e:
            logger.warning("Telegram button send error: %s", e)
            return self.send(text)

    def answer_callback(self, callback_query_id: str, text: str = "") -> bool:
        """Answer a callback query from inline button press."""
        if not self.enabled:
            return False
        url = self.API_BASE.format(token=self.bot_token, method="answerCallbackQuery")
        payload = {"callback_query_id": callback_query_id, "text": text}
        try:
            requests.post(url, json=payload, timeout=5)
            return True
        except Exception:
            return False

    # ── Pre-signal alert ─────────────────────────────────────────────────
    def send_pre_signal_alert(self, symbol: str, current_price: float,
                               bb_band: float, band_type: str, side: str) -> bool:
        """Send a pre-signal alert when price is approaching BB band."""
        side_emoji = "🟢" if side.lower() == "buy" else "🔴"
        msg = (
            f"⚡ {symbol.upper()} approaching BB {band_type}\n"
            f"Current: {self.format_price(symbol, current_price)}\n"
            f"BB {band_type}: {self.format_price(symbol, bb_band)}\n"
            f"Possible {side.upper()} signal next bar {side_emoji}"
        )
        return self.send(msg)

    # ── Signal result notification ────────────────────────────────────────
    def send_signal_result(self, symbol: str, side: str, result: str,
                            price: float, pips: float, signal_id: str = "") -> bool:
        """Send signal result (WIN/LOSS/EXPIRED)."""
        if result == "WIN":
            emoji = "✅"
            msg = (
                f"{emoji} {symbol.upper()} {side.upper()} hit TP\n"
                f"@ {self.format_price(symbol, price)}\n"
                f"+{pips:.0f} pips 🎯"
            )
        elif result == "LOSS":
            emoji = "❌"
            msg = (
                f"{emoji} {symbol.upper()} {side.upper()} hit SL\n"
                f"@ {self.format_price(symbol, price)}\n"
                f"-{pips:.0f} pips"
            )
        else:
            msg = f"⏰ {symbol.upper()} {side.upper()} signal expired"

        return self.send(msg)

    # ── Startup message ──────────────────────────────────────────────────
    def send_startup_message(self, symbols: list) -> bool:
        now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")
        symbols_str = " · ".join(symbols)
        msg = (
            f"🤖 BBPro Signal Bot — نشط الآن\n"
            f"📡 الأزواج: {symbols_str}\n"
            f"🎯 وضع التوصيات فقط\n"
            f"🚀 {len(symbols)} استراتيجيات نشطة\n"
            f"📊 Multi-TF + Candlestick + Economic Calendar\n"
            f"🕐 {now_utc}"
        )
        return self.send(msg)

    # ── Daily performance report ──────────────────────────────────────────
    def send_daily_report(self, stats: dict) -> bool:
        msg = (
            f"📊 تقرير اليوم\n"
            f"━━━━━━━━━━━━━\n"
            f"الإشارات: {stats.get('total', 0)}\n"
            f"نجحت: {stats.get('wins', 0)} ✅\n"
            f"خسرت: {stats.get('losses', 0)} ❌\n"
            f"معلقة: {stats.get('pending', 0)} ⏰\n"
            f"منتهية: {stats.get('expired', 0)} ⏱️\n"
            f"Win Rate: {stats.get('win_rate', 0):.1f}%\n"
            f"صافي Pips: {stats.get('total_pips', 0):+.0f}\n"
            f"━━━━━━━━━━━━━"
        )
        return self.send(msg)

    # ── Weekly performance report ─────────────────────────────────────────
    def send_weekly_report(self, stats: dict) -> bool:
        msg = (
            f"📊 تقرير الأسبوع\n"
            f"━━━━━━━━━━━━━\n"
            f"إجمالي الإشارات: {stats.get('total', 0)}\n"
            f"نجحت: {stats.get('wins', 0)} ✅\n"
            f"خسرت: {stats.get('losses', 0)} ❌\n"
            f"Win Rate: {stats.get('win_rate', 0):.1f}%\n"
            f"صافي Pips: {stats.get('total_pips', 0):+.0f}\n"
            f"أفضل يوم: {stats.get('best_day', 'N/A')}\n"
            f"أسوأ يوم: {stats.get('worst_day', 'N/A')}\n"
            f"━━━━━━━━━━━━━"
        )
        return self.send(msg)

    # ── Economic calendar alert ──────────────────────────────────────────
    def send_news_alert(self, events: str) -> bool:
        msg = f"📅 أخبار قادمة:\n{events}"
        return self.send(msg)

    # ── Standard notifications ────────────────────────────────────────────
    def notify_start(self, symbol, timeframe, risk_pct):
        self.send(f"🤖 <b>BBPro Signal Bot Started</b>\nSymbol: <code>{symbol}</code>\nTF: <code>{timeframe}</code>")

    def notify_stop(self):
        self.send("🛑 <b>BBPro Signal Bot Stopped</b>")

    def notify_daily_dd_hit(self, dd_pct, max_pct):
        self.send(f"🛑 <b>DAILY DD LIMIT</b>\nCurrent: <code>{dd_pct:.2f}%</code>\nMax: <code>{max_pct:.1f}%</code>")

    def notify_kill_switch(self, reason):
        self.send(f"⚠️ <b>KILL-SWITCH</b>\n<code>{reason}</code>")

    def notify_signal_rejected(self, symbol, side, reason):
        self.send(f"❌ <b>Signal Rejected</b>\n{symbol} {side}\nReason: {reason}")


def create_notifier(bot_token: str, chat_id: str, enabled: bool = True):
    return TelegramNotifier(bot_token, chat_id, enabled)
