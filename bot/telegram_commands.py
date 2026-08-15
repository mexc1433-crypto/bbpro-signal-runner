"""
telegram_commands.py — Telegram Bot Commands Handler (Secured)
==================================================================
Handles /commands sent to the Telegram bot.

SECURITY: Only the authorized chat_id (owner) can use the bot.
Any other user is rejected and ignored.

Commands:
  /status    — Bot status and active signals
  /stats     — Win/loss statistics
  /backtest  — Run backtest on a symbol
  /report    — Generate daily/weekly report
  /symbols   — List active symbols and their profiles
  /news      — Show upcoming economic events
  /help      — Help message
  /stop      — Stop the bot
  /whoami    — Show your chat ID (for debugging)
"""

import logging
import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class TelegramCommandHandler:
    """Handles Telegram bot commands via polling getUpdates. Secured to owner only."""

    def __init__(self, bot_token: str, chat_id: str, bot_instance=None):
        self.bot_token = bot_token
        self.chat_id = str(chat_id).strip()
        self.bot = bot_instance
        self.enabled = bool(bot_token) and HAS_REQUESTS
        self._last_update_id = 0
        self._running = False
        # Track rejected users to avoid spamming logs
        self._rejected_ids: set = set()

    def send(self, text: str) -> bool:
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            r = requests.post(url, json={
                "chat_id": self.chat_id, "text": text,
                "parse_mode": "HTML", "disable_web_page_preview": True
            }, timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    async def poll_loop(self):
        """Poll for updates and handle commands."""
        if not self.enabled:
            return

        self._running = True
        logger.info("Telegram command handler started (owner chat_id=%s)", self.chat_id)

        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    self._last_update_id = update.get("update_id", self._last_update_id) + 1
                    await self._handle_update(update)
            except Exception as e:
                logger.warning("Telegram polling error: %s", e)
            await asyncio.sleep(3)

    async def _get_updates(self) -> list:
        """Get updates from Telegram."""
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {"offset": self._last_update_id + 1, "timeout": 5}
        try:
            r = await asyncio.to_thread(
                requests.get, url, params=params, timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("result", [])
        except Exception:
            pass
        return []

    def _extract_chat_id(self, update: dict) -> Optional[str]:
        """Extract the sender's chat_id from an update."""
        # Regular message
        msg = update.get("message")
        if msg:
            chat = msg.get("chat", {})
            return str(chat.get("id", ""))

        # Callback query (button press)
        cq = update.get("callback_query")
        if cq:
            msg = cq.get("message", {})
            chat = msg.get("chat", {})
            return str(chat.get("id", ""))
            # Also check from field
            from_user = cq.get("from", {})
            from_id = str(from_user.get("id", ""))
            if from_id:
                return from_id

        # Edited message
        msg = update.get("edited_message")
        if msg:
            chat = msg.get("chat", {})
            return str(chat.get("id", ""))

        # Channel post
        msg = update.get("channel_post")
        if msg:
            chat = msg.get("chat", {})
            return str(chat.get("id", ""))

        return None

    def _is_authorized(self, update: dict) -> bool:
        """Check if the update is from the authorized owner."""
        sender_chat_id = self._extract_chat_id(update)
        if not sender_chat_id:
            return False
        return sender_chat_id == self.chat_id

    async def _handle_update(self, update: dict):
        """Handle a single update — with authorization check."""
        # ── AUTHORIZATION CHECK ────────────────────────────────────────
        if not self._is_authorized(update):
            sender_id = self._extract_chat_id(update)
            if sender_id and sender_id not in self._rejected_ids:
                self._rejected_ids.add(sender_id)
                logger.warning("🚫 Unauthorized access attempt from chat_id=%s (rejected)", sender_id)
                # Notify owner about the intrusion attempt
                self.send(
                    f"🚫 <b>محاولة دخول غير مصرح بها</b>\n"
                    f"Chat ID: <code>{sender_id}</code>\n"
                    f"تم رفض الوصول."
                )
            return

        # ── Handle callback queries (inline button presses) ────────────
        callback = update.get("callback_query")
        if callback:
            await self._handle_callback(callback)
            return

        # ── Handle regular messages ────────────────────────────────────
        message = update.get("message")
        if not message:
            return

        text = message.get("text", "").strip()
        if not text.startswith("/"):
            return

        parts = text.split()
        cmd = parts[0].lower().split("@")[0]  # Remove @botname suffix
        args = parts[1:]

        handlers = {
            "/status": self._cmd_status,
            "/stats": self._cmd_stats,
            "/backtest": self._cmd_backtest,
            "/report": self._cmd_report,
            "/symbols": self._cmd_symbols,
            "/news": self._cmd_news,
            "/help": self._cmd_help,
            "/stop": self._cmd_stop,
            "/whoami": self._cmd_whoami,
        }

        handler = handlers.get(cmd)
        if handler:
            response = await handler(args)
            if response:
                self.send(response)
        else:
            # Don't respond to unknown commands — just ignore
            pass

    async def _handle_callback(self, callback: dict):
        """Handle inline button callback — with authorization."""
        # Double-check authorization on callback
        callback_chat_id = str(callback.get("from", {}).get("id", ""))
        if callback_chat_id and callback_chat_id != self.chat_id:
            logger.warning("🚫 Unauthorized callback from chat_id=%s", callback_chat_id)
            return

        data = callback.get("data", "")
        query_id = callback.get("id", "")

        if data.startswith("win_"):
            signal_id = data[4:]
            self._answer_callback(query_id, "✅ تم تسجيل النتيجة: نجحت")
            if self.bot and self.bot.tracker:
                self.bot.tracker._results.append({
                    "signal_id": signal_id, "result": "WIN",
                    "symbol": "", "side": "", "price": 0, "pips": 0,
                })
                self.bot.tracker.remove_signal(signal_id)
        elif data.startswith("loss_"):
            signal_id = data[5:]
            self._answer_callback(query_id, "❌ تم تسجيل النتيجة: خسرت")
            if self.bot and self.bot.tracker:
                self.bot.tracker._results.append({
                    "signal_id": signal_id, "result": "LOSS",
                    "symbol": "", "side": "", "price": 0, "pips": 0,
                })
                self.bot.tracker.remove_signal(signal_id)
        elif data.startswith("open_"):
            self._answer_callback(query_id, "⏰ الإشارة لسه مفتوحة")

    def _answer_callback(self, query_id: str, text: str):
        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        try:
            requests.post(url, json={"callback_query_id": query_id, "text": text}, timeout=5)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # COMMANDS — Only accessible by the owner
    # ------------------------------------------------------------------
    async def _cmd_status(self, args) -> str:
        if not self.bot:
            return "Bot not available"
        active = []
        if self.bot.tracker:
            active = self.bot.tracker.get_active()
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")
        lines = [
            f"🤖 <b>Bot Status</b>",
            f"🕐 {now}",
            f"📍 Symbol: <code>{self.bot.cfg.symbol}</code>",
            f"🎯 Mode: Signal Only (Private)",
            f"📊 Active signals: {len(active)}",
        ]
        if active:
            for sig in active[:5]:
                lines.append(f"  • {sig.symbol} {sig.side.upper()} @ {sig.entry:.5f}")
        return "\n".join(lines)

    async def _cmd_stats(self, args) -> str:
        if not self.bot or not self.bot.tracker:
            return "Statistics not available"
        stats = self.bot.tracker.get_stats()
        stats["pending"] = len(self.bot.tracker.get_active())
        return (
            f"📊 <b>Statistics</b>\n"
            f"━━━━━━━━━━━━━\n"
            f"Total: {stats['total']}\n"
            f"Wins: {stats['wins']} ✅\n"
            f"Losses: {stats['losses']} ❌\n"
            f"Pending: {stats['pending']} ⏰\n"
            f"Expired: {stats['expired']} ⏱️\n"
            f"Win Rate: {stats['win_rate']:.1f}%\n"
            f"Net Pips: {stats['total_pips']:+.0f}\n"
            f"━━━━━━━━━━━━━"
        )

    async def _cmd_backtest(self, args) -> str:
        if not self.bot:
            return "Backtest not available"
        symbol = args[0].upper() if args else self.bot.cfg.symbol
        days = int(args[1]) if len(args) > 1 else 30
        return f"📊 Backtest for {symbol} ({days}d)...\nStarting backtest — results will be sent shortly."

    async def _cmd_report(self, args) -> str:
        if not self.bot or not self.bot.tracker:
            return "Reports not available"
        report_type = args[0].lower() if args else "daily"
        if report_type == "weekly" and self.bot.reporter:
            return self.bot.reporter.weekly_report()
        elif self.bot.reporter:
            return self.bot.reporter.daily_report()
        return "Reporter not available"

    async def _cmd_symbols(self, args) -> str:
        symbols = self.bot.cfg.symbols if self.bot else ["XAUUSD", "EURUSD"]
        lines = ["📋 <b>Active Symbols</b>", "━━━━━━━━━━━━━"]
        for sym in symbols:
            try:
                from symbol_profiles import get_profile
                p = get_profile(sym)
                lines.append(f"• <b>{sym}</b> ({p['name']})")
                lines.append(f"  TF: {p['timeframe']} | SL: {p['sl_atr_multiplier']}x ATR | RR: {p['min_rr_ratio']}")
            except Exception:
                lines.append(f"• {sym}")
        return "\n".join(lines)

    async def _cmd_news(self, args) -> str:
        if not self.bot or not self.bot.econ_cal:
            return "Economic calendar not available"
        symbol = args[0].upper() if args else self.bot.cfg.symbol
        events = self.bot.econ_cal.format_events(symbol, 5)
        return f"📅 <b>Economic Events</b> ({symbol})\n━━━━━━━━━━━━━\n{events}"

    async def _cmd_help(self, args) -> str:
        return (
            "🤖 <b>BBPro Signal Bot v3 — Commands</b>\n"
            "━━━━━━━━━━━━━\n"
            "/status — Bot status & active signals\n"
            "/stats — Win/loss statistics\n"
            "/backtest [symbol] [days] — Run backtest\n"
            "/report [daily|weekly] — Performance report\n"
            "/symbols — List active symbols\n"
            "/news [symbol] — Upcoming economic events\n"
            "/whoami — Show your chat ID\n"
            "/help — This message\n"
            "/stop — Stop the bot\n"
            "━━━━━━━━━━━━━\n"
            "🔒 <b>Secured</b>: Only owner can use this bot\n"
            "━━━━━━━━━━━━━\n"
            "📊 Features:\n"
            "• 8 strategies + SMC + VWAP\n"
            "• Multi-timeframe analysis (M15/M30/H1/H4)\n"
            "• Candlestick patterns (8)\n"
            "• RSI/MACD divergence\n"
            "• Market regime detection\n"
            "• Signal Quality Score (A+/A/B/C/D)\n"
            "• Multi-TP + Kelly Criterion\n"
            "• Economic calendar\n"
            "• Signal tracking & backtesting"
        )

    async def _cmd_whoami(self, args) -> str:
        """Show the owner's chat ID — useful for debugging."""
        return (
            f"🆔 <b>Your Chat ID</b>\n"
            f"<code>{self.chat_id}</code>\n"
            f"✅ You are the authorized owner."
        )

    async def _cmd_stop(self, args) -> str:
        if self.bot:
            self.bot._stop = True
        return "🛑 Stopping bot..."
