"""
backtest.py — Simple Backtesting Engine
==========================================
Backtests strategies on historical data and reports performance.

Features:
  - Run strategies on historical bars
  - Calculate win rate, total pips, max drawdown
  - Per-strategy breakdown
  - Telegram-ready report format
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class BacktestResult:
    """Result of a backtest run."""
    total_signals: int
    wins: int
    losses: int
    expired: int
    win_rate: float
    total_pips: float
    max_drawdown_pips: float
    best_trade_pips: float
    worst_trade_pips: float
    avg_win_pips: float
    avg_loss_pips: float
    profit_factor: float


class Backtester:
    """Simple backtesting engine for signal strategies."""

    def __init__(self, pip_size: float = 0.0001):
        self.pip_size = pip_size

    def run(self, bars: list, strategy_analyzer, max_bars: int = 500,
            tp_pips: float = 40, sl_pips: float = 25,
            expiry_bars: int = 48) -> BacktestResult:
        """
        Run backtest on historical bars.

        Args:
            bars: List of Bar objects with open/high/low/close
            strategy_analyzer: Object with .analyze(bars) method returning signal
            max_bars: Maximum bars to backtest
            tp_pips: Take profit in pips
            sl_pips: Stop loss in pips
            expiry_bars: Bars before signal expires

        Returns:
            BacktestResult with statistics
        """
        if len(bars) < 50:
            return BacktestResult(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        start = max(50, len(bars) - max_bars)
        signals = []
        pip = self.pip_size

        for i in range(start, len(bars) - 1):
            window = bars[:i + 1]
            try:
                result = strategy_analyzer.analyze(window)
                if result and result.signal:
                    side = result.signal.lower()
                    entry = bars[i].close

                    if side == "buy":
                        sl = entry - sl_pips * pip
                        tp = entry + tp_pips * pip
                    else:
                        sl = entry + sl_pips * pip
                        tp = entry - tp_pips * pip

                    # Check outcome
                    outcome = self._check_outcome(bars, i + 1, side, tp, sl, expiry_bars)
                    signals.append({
                        "side": side,
                        "entry": entry,
                        "tp": tp,
                        "sl": sl,
                        "outcome": outcome,
                    })
            except Exception:
                continue

        return self._calculate_stats(signals)

    def _check_outcome(self, bars: list, start_idx: int, side: str,
                        tp: float, sl: float, expiry_bars: int) -> str:
        """Check if TP or SL was hit after signal."""
        end = min(start_idx + expiry_bars, len(bars))

        for j in range(start_idx, end):
            bar = bars[j]

            if side == "buy":
                if bar.high >= tp:
                    return "WIN"
                if bar.low <= sl:
                    return "LOSS"
            else:
                if bar.low <= tp:
                    return "WIN"
                if bar.high >= sl:
                    return "LOSS"

        return "EXPIRED"

    def _calculate_stats(self, signals: list) -> BacktestResult:
        """Calculate statistics from backtest signals."""
        wins = [s for s in signals if s["outcome"] == "WIN"]
        losses = [s for s in signals if s["outcome"] == "LOSS"]
        expired = [s for s in signals if s["outcome"] == "EXPIRED"]

        pip = self.pip_size

        win_pips = [abs(s["tp"] - s["entry"]) / pip for s in wins]
        loss_pips = [abs(s["entry"] - s["sl"]) / pip for s in losses]

        total_win_pips = sum(win_pips) if win_pips else 0
        total_loss_pips = sum(loss_pips) if loss_pips else 0

        total_pips = total_win_pips - total_loss_pips

        # Max drawdown
        equity = 0
        peak = 0
        max_dd = 0
        for s in signals:
            if s["outcome"] == "WIN":
                equity += abs(s["tp"] - s["entry"]) / pip
            elif s["outcome"] == "LOSS":
                equity -= abs(s["entry"] - s["sl"]) / pip
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        avg_win = np.mean(win_pips) if win_pips else 0
        avg_loss = np.mean(loss_pips) if loss_pips else 0

        profit_factor = total_win_pips / total_loss_pips if total_loss_pips > 0 else 0

        total_decided = len(wins) + len(losses)
        win_rate = (len(wins) / total_decided * 100) if total_decided > 0 else 0

        return BacktestResult(
            total_signals=len(signals),
            wins=len(wins),
            losses=len(losses),
            expired=len(expired),
            win_rate=win_rate,
            total_pips=total_pips,
            max_drawdown_pips=max_dd,
            best_trade_pips=max(win_pips) if win_pips else 0,
            worst_trade_pips=min(loss_pips) if loss_pips else 0,
            avg_win_pips=avg_win,
            avg_loss_pips=avg_loss,
            profit_factor=profit_factor,
        )

    def format_report(self, result: BacktestResult, symbol: str) -> str:
        """Format backtest report for Telegram."""
        return (
            f"📊 Backtest: {symbol}\n"
            f"━━━━━━━━━━━━━\n"
            f"الإشارات: {result.total_signals}\n"
            f"نجحت: {result.wins} ✅\n"
            f"خسرت: {result.losses} ❌\n"
            f"منتهية: {result.expired} ⏰\n"
            f"Win Rate: {result.win_rate:.1f}%\n"
            f"صافي Pips: {result.total_pips:+.0f}\n"
            f"Max DD: {result.max_drawdown_pips:.0f} pips\n"
            f"أفضل صفقة: +{result.best_trade_pips:.0f} pips\n"
            f"أسوأ صفقة: -{result.worst_trade_pips:.0f} pips\n"
            f"Profit Factor: {result.profit_factor:.2f}\n"
            f"━━━━━━━━━━━━━"
        )
