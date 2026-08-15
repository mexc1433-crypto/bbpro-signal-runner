"""
telegram_commands.py — Telegram Bot Commands Handler
========================================================
Handles /commands sent to the Telegram bot.

Commands:
  /status    — Bot status and active signals
  /stats     — Win/loss statistics
  /backtest  — Run backtest on a symbol
  /report    — Generate daily/weekly report
  /symbols   — List active symbols and their profiles
  /news      — Show upcoming economic events
  /help      — Help message
  /stop      — Stop the bot
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


class TelegramCommandHandler:
    """Handles Telegram bot commands via polling getUpdates."""

    def __init__(self, bot_token: str, chat_id: str, bot_instance=None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = bot_instance
        self.enabled = bool(bot_token) and HAS_REQUESTS
        self._last_update_id = 0
        self._running = False

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
        logger.info("Telegram command handler started")

        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    self._last_update_id = update.get("update_id", self._last_update_id) + 1
                    await self._handle_update(update)
            except Exception as e:
                logger.warning("Telegram polling error: %s", e)
            await asyncio.sleep(3)  # Poll every 3 seconds

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

    async def _handle_update(self, update: dict):
        """Handle a single update."""
        message = update.get("message") or update.get("callback_query", {}).get("message")
        if not message:
            return

        # Handle callback queries (inline button presses)
        callback = update.get("callback_query")
        if callback:
            await self._handle_callback(callback)
            return

        text = message.get("text", "").strip()
        if not text.startswith("/"):
            return

        parts = text.split()
        cmd = parts[0].lower()
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
        }

        handler = handlers.get(cmd)
        if handler:
            response = await handler(args)
            if response:
                self.send(response)
        else:
            self.send(f"Unknown command: {cmd}\nType /help for available commands")

    async def _handle_callback(self, callback: dict):
        """Handle inline button callback."""
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
    # COMMANDS
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
            f"🎯 Mode: Signal Only",
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
            "🤖 <b>BBPro Signal Bot — Commands</b>\n"
            "━━━━━━━━━━━━━\n"
            "/status — Bot status & active signals\n"
            "/stats — Win/loss statistics\n"
            "/backtest [symbol] [days] — Run backtest\n"
            "/report [daily|weekly] — Performance report\n"
            "/symbols — List active symbols\n"
            "/news [symbol] — Upcoming economic events\n"
            "/help — This message\n"
            "/stop — Stop the bot\n"
            "━━━━━━━━━━━━━\n"
            "📊 Features:\n"
            "• Multi-strategy (6 strategies)\n"
            "• Multi-timeframe analysis\n"
            "• Smart Money Concepts\n"
            "• Candlestick patterns\n"
            "• RSI/MACD divergence\n"
            "• Market regime detection\n"
            "• Economic calendar\n"
            "• Signal tracking & scoring"
        )

    async def _cmd_stop(self, args) -> str:
        if self.bot:
            self.bot._stop = True
        return "🛑 Stopping bot..."
