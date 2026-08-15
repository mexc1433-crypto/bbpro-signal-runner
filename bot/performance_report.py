"""
performance_report.py — Periodic Performance Reports
======================================================
Generates daily and weekly performance reports for Telegram.
"""

from typing import Optional
from datetime import datetime, timezone


class PerformanceReporter:
    """Generates formatted performance reports."""

    def __init__(self, tracker, notifier=None):
        self.tracker = tracker
        self.notifier = notifier

    def daily_report(self) -> str:
        """Generate daily performance report."""
        stats = self.tracker.get_stats()
        stats["pending"] = len(self.tracker.get_active())

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

        if self.notifier:
            self.notifier.send(msg)
        return msg

    def weekly_report(self) -> str:
        """Generate weekly performance report."""
        stats = self.tracker.get_stats()

        msg = (
            f"📊 تقرير الأسبوع\n"
            f"━━━━━━━━━━━━━\n"
            f"إجمالي الإشارات: {stats.get('total', 0)}\n"
            f"نجحت: {stats.get('wins', 0)} ✅\n"
            f"خسرت: {stats.get('losses', 0)} ❌\n"
            f"Win Rate: {stats.get('win_rate', 0):.1f}%\n"
            f"صافي Pips: {stats.get('total_pips', 0):+.0f}\n"
            f"━━━━━━━━━━━━━"
        )

        if self.notifier:
            self.notifier.send(msg)
        return msg

    def format_signal_result(self, signal: dict, result: str) -> str:
        """Format individual signal result."""
        symbol = signal.get("symbol", "")
        side = signal.get("side", "")
        price = signal.get("price", 0)
        pips = signal.get("pips", 0)

        if result == "WIN":
            return f"✅ {symbol.upper()} {side.upper()} hit TP\n@ {price}\n+{pips:.0f} pips 🎯"
        elif result == "LOSS":
            return f"❌ {symbol.upper()} {side.upper()} hit SL\n@ {price}\n-{pips:.0f} pips"
        else:
            return f"⏰ {symbol.upper()} {side.upper()} signal expired"
