"""
backtest.py — Multi-Strategy Backtesting Engine
================================================
Downloads historical data via yfinance, runs all bot strategies bar-by-bar,
and generates a per-strategy performance report.

Usage (CLI):
    python -m bot.backtest --symbol EURUSD --period 1y --interval 1h
    python -m bot.backtest --symbol XAUUSD --period 6mo --interval 30m

Usage (import):
    from bot.backtest import run_backtest, format_report
    report = run_backtest(symbol="EURUSD", period="1y", interval="1h")
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Lazy imports for bot internals ──────────────────────────────────────────

def _import_bot_modules():
    """Import bot modules lazily so this file can also run standalone."""
    try:
        from bot.config import BotConfig, TradeDirection, load_config
        from bot.strategies import StrategyManager
        from bot.indicators import (
            rsi as calc_rsi, ema as calc_ema, atr as calc_atr,
            bollinger_bands, calc_stochastic, calc_macd, calc_adx,
            compute_all_indicators,
        )
        return BotConfig, TradeDirection, load_config, StrategyManager, {
            "rsi": calc_rsi, "ema": calc_ema, "atr": calc_atr,
            "bollinger_bands": bollinger_bands,
            "stochastic": calc_stochastic, "macd": calc_macd,
            "adx": calc_adx,
            "compute_all": compute_all_indicators,
        }
    except ImportError as e:
        logger.warning("Could not import bot modules: %s", e)
        return None, None, None, None, None


# ── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    """Single simulated trade."""
    bar_index: int
    strategy: str
    side: str          # "buy" or "sell"
    entry_price: float
    sl_price: float
    tp_price: float
    outcome: str = "EXPIRED"   # WIN, LOSS, EXPIRED
    exit_price: float = 0.0
    pips: float = 0.0
    bars_held: int = 0


@dataclass
class StrategyStats:
    """Per-strategy performance metrics."""
    name: str
    total_signals: int = 0
    wins: int = 0
    losses: int = 0
    expired: int = 0
    win_rate: float = 0.0
    total_pips: float = 0.0
    avg_win_pips: float = 0.0
    avg_loss_pips: float = 0.0
    profit_factor: float = 0.0
    max_consecutive_losses: int = 0
    best_trade_pips: float = 0.0
    worst_trade_pips: float = 0.0


@dataclass
class BacktestResult:
    """Overall backtest result."""
    symbol: str
    period: str
    interval: str
    total_bars: int
    total_signals: int
    wins: int
    losses: int
    expired: int
    overall_win_rate: float
    total_pips: float
    max_drawdown_pips: float
    profit_factor: float
    per_strategy: List[Dict] = field(default_factory=list)


# ── Data Download ───────────────────────────────────────────────────────────

def download_data(symbol: str, period: str = "1y", interval: str = "1h") -> List[dict]:
    """Download OHLCV data from Yahoo Finance. Returns list of bar dicts."""
    import yfinance as yf

    # Map forex symbols to Yahoo Finance format
    yf_symbol = symbol.upper()
    if yf_symbol == "XAUUSD":
        yf_symbol = "GC=F"
    elif yf_symbol in ("EURUSD", "GBPUSD", "USDJPY", "EURJPY", "USDCAD"):
        yf_symbol = yf_symbol + "=X"

    logger.info("Downloading %s (%s, %s interval)...", yf_symbol, period, interval)
    df = yf.download(yf_symbol, period=period, interval=interval, progress=False)

    if df is None or df.empty:
        raise ValueError(f"No data returned for {yf_symbol}")

    # Handle multi-level columns from yfinance
    if df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)

    bars = []
    for idx, row in df.iterrows():
        bars.append({
            "time": idx.to_pytimestamp() if hasattr(idx, "to_pytimestamp") else idx,
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row.get("Volume", 0)),
        })

    logger.info("Downloaded %d bars for %s", len(bars), symbol)
    return bars


# ── Backtest Engine ─────────────────────────────────────────────────────────

class MultiStrategyBacktester:
    """Backtests multiple strategies on historical data."""

    def __init__(self, pip_size: float = 0.0001, sl_pips: float = 25,
                 tp_pips: float = 40, expiry_bars: int = 48):
        self.pip_size = pip_size
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.expiry_bars = expiry_bars

    def run(self, bars: List[dict], strategy_mgr, cfg, min_confidence: float = 0.3) -> Tuple[List[TradeRecord], BacktestResult]:
        """
        Run all strategies on historical bars.

        Args:
            bars: List of bar dicts with open/high/low/close/volume
            strategy_mgr: StrategyManager instance
            cfg: BotConfig instance
            min_confidence: Minimum strategy confidence to count a signal

        Returns:
            (list of TradeRecord, BacktestResult)
        """
        if len(bars) < 250:
            logger.warning("Not enough bars for backtest: %d (need 250+)", len(bars))
            return [], BacktestResult(
                symbol=cfg.symbol, period="", interval="",
                total_bars=len(bars), total_signals=0, wins=0, losses=0,
                expired=0, overall_win_rate=0, total_pips=0,
                max_drawdown_pips=0, profit_factor=0
            )

        all_trades: List[TradeRecord] = []
        warmup = max(cfg.bb_period, cfg.slow_ema_period, cfg.atr_period) + 10
        pip = self.pip_size

        logger.info("Backtesting %d bars (warmup=%d)...", len(bars) - warmup, warmup)

        for i in range(warmup, len(bars) - 1):
            window = bars[:i + 1]

            try:
                # Run all strategies on the window
                results = strategy_mgr.run_all(window, cfg)

                for r in results:
                    signal = r.get("signal")
                    confidence = r.get("confidence", 0)
                    strat_name = r.get("strategy", "unknown")

                    # Normalize signal
                    if hasattr(signal, "value"):
                        signal = signal.value

                    if signal not in ("buy", "sell") or confidence < min_confidence:
                        continue

                    entry = bars[i]["close"]
                    if signal == "buy":
                        sl = entry - self.sl_pips * pip
                        tp = entry + self.tp_pips * pip
                    else:
                        sl = entry + self.sl_pips * pip
                        tp = entry - self.tp_pips * pip

                    # Check outcome
                    outcome, exit_price, bars_held = self._check_outcome(
                        bars, i + 1, signal, tp, sl, self.expiry_bars
                    )

                    if outcome == "WIN":
                        pips = abs(tp - entry) / pip
                    elif outcome == "LOSS":
                        pips = -abs(entry - sl) / pip
                    else:
                        pips = 0

                    trade = TradeRecord(
                        bar_index=i, strategy=strat_name, side=signal,
                        entry_price=entry, sl_price=sl, tp_price=tp,
                        outcome=outcome, exit_price=exit_price,
                        pips=pips, bars_held=bars_held,
                    )
                    all_trades.append(trade)

            except Exception as e:
                logger.debug("Bar %d error: %s", i, e)
                continue

        result = self._compute_stats(all_trades, bars, cfg)
        return all_trades, result

    def _check_outcome(self, bars: List[dict], start_idx: int, side: str,
                       tp: float, sl: float, expiry: int) -> Tuple[str, float, int]:
        """Check if TP or SL was hit. Returns (outcome, exit_price, bars_held)."""
        end = min(start_idx + expiry, len(bars))

        for j in range(start_idx, end):
            bar = bars[j]

            if side == "buy":
                if bar["high"] >= tp:
                    return "WIN", tp, j - start_idx + 1
                if bar["low"] <= sl:
                    return "LOSS", sl, j - start_idx + 1
            else:
                if bar["low"] <= tp:
                    return "WIN", tp, j - start_idx + 1
                if bar["high"] >= sl:
                    return "LOSS", sl, j - start_idx + 1

        return "EXPIRED", bars[end - 1]["close"] if end > start_idx else 0, expiry

    def _compute_stats(self, trades: List[TradeRecord], bars: List[dict], cfg) -> BacktestResult:
        """Compute per-strategy and overall statistics."""
        # Group by strategy
        by_strategy: Dict[str, List[TradeRecord]] = {}
        for t in trades:
            by_strategy.setdefault(t.strategy, []).append(t)

        per_strategy: List[Dict] = []
        for name, strat_trades in sorted(by_strategy.items()):
            stats = self._strategy_stats(name, strat_trades)
            per_strategy.append(asdict(stats))

        # Overall stats
        wins = sum(1 for t in trades if t.outcome == "WIN")
        losses = sum(1 for t in trades if t.outcome == "LOSS")
        expired = sum(1 for t in trades if t.outcome == "EXPIRED")
        total_decided = wins + losses
        win_rate = (wins / total_decided * 100) if total_decided > 0 else 0

        total_pips = sum(t.pips for t in trades)
        gross_win = sum(t.pips for t in trades if t.pips > 0)
        gross_loss = abs(sum(t.pips for t in trades if t.pips < 0))
        profit_factor = gross_win / gross_loss if gross_loss > 0 else 0

        # Max drawdown
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            equity += t.pips
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        return BacktestResult(
            symbol=cfg.symbol, period="", interval="",
            total_bars=len(bars), total_signals=len(trades),
            wins=wins, losses=losses, expired=expired,
            overall_win_rate=win_rate, total_pips=total_pips,
            max_drawdown_pips=max_dd, profit_factor=profit_factor,
            per_strategy=per_strategy,
        )

    def _strategy_stats(self, name: str, trades: List[TradeRecord]) -> StrategyStats:
        """Calculate stats for a single strategy."""
        wins = [t for t in trades if t.outcome == "WIN"]
        losses = [t for t in trades if t.outcome == "LOSS"]
        expired = [t for t in trades if t.outcome == "EXPIRED"]

        win_pips = [t.pips for t in wins]
        loss_pips = [t.pips for t in losses]

        total_decided = len(wins) + len(losses)
        win_rate = (len(wins) / total_decided * 100) if total_decided > 0 else 0

        gross_win = sum(win_pips) if win_pips else 0
        gross_loss = abs(sum(loss_pips)) if loss_pips else 0
        profit_factor = gross_win / gross_loss if gross_loss > 0 else 0

        # Max consecutive losses
        max_streak = 0
        current_streak = 0
        for t in trades:
            if t.outcome == "LOSS":
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0

        return StrategyStats(
            name=name,
            total_signals=len(trades),
            wins=len(wins),
            losses=len(losses),
            expired=len(expired),
            win_rate=round(win_rate, 1),
            total_pips=round(sum(t.pips for t in trades), 1),
            avg_win_pips=round(np.mean(win_pips), 1) if win_pips else 0,
            avg_loss_pips=round(np.mean(loss_pips), 1) if loss_pips else 0,
            profit_factor=round(profit_factor, 2),
            max_consecutive_losses=max_streak,
            best_trade_pips=round(max(win_pips), 1) if win_pips else 0,
            worst_trade_pips=round(min(loss_pips), 1) if loss_pips else 0,
        )


# ── Report Formatting ───────────────────────────────────────────────────────

def format_report(result: BacktestResult) -> str:
    """Format backtest report for Telegram/console output."""
    lines = [
        f"📊 Backtest Report: {result.symbol}",
        f"━━━━━━━━━━━━━━━━━",
        f"Bars: {result.total_bars} | Signals: {result.total_signals}",
        f"✅ Wins: {result.wins} | ❌ Losses: {result.losses} | ⏰ Expired: {result.expired}",
        f"Win Rate: {result.overall_win_rate:.1f}%",
        f"Net Pips: {result.total_pips:+.1f}",
        f"Max Drawdown: {result.max_drawdown_pips:.1f} pips",
        f"Profit Factor: {result.profit_factor:.2f}",
        f"",
        f"📋 Per-Strategy Breakdown:",
        f"━━━━━━━━━━━━━━━━━",
    ]

    for s in result.per_strategy:
        emoji = "🟢" if s["win_rate"] >= 55 else ("🟡" if s["win_rate"] >= 40 else "🔴")
        lines.append(
            f"{emoji} {s['name']}: {s['total_signals']} sigs | "
            f"WR: {s['win_rate']}% | PF: {s['profit_factor']} | "
            f"Max Loss Streak: {s['max_consecutive_losses']}"
        )

    lines.append("━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_report_json(result: BacktestResult) -> str:
    """Format as JSON for API consumption."""
    return json.dumps(asdict(result), indent=2, default=str)


# ── Main Entry Point ────────────────────────────────────────────────────────

def run_backtest(symbol: str = "EURUSD", period: str = "1y",
                 interval: str = "1h", sl_pips: float = 25,
                 tp_pips: float = 40, expiry_bars: int = 48) -> BacktestResult:
    """Run a full backtest and return results."""
    BotConfig, TradeDirection, load_config, StrategyManager, indicators = _import_bot_modules()

    if BotConfig is None:
        raise RuntimeError("Could not import bot modules. Run from project root.")

    cfg = load_config()
    cfg.symbol = symbol

    # Determine pip size
    pip_size = 0.01 if "JPY" in symbol else 0.0001
    if symbol == "XAUUSD":
        pip_size = 0.1

    # Download data
    bars = download_data(symbol, period, interval)

    # Initialize strategy manager
    strategy_mgr = StrategyManager(cfg)

    # Run backtest
    backtester = MultiStrategyBacktester(
        pip_size=pip_size, sl_pips=sl_pips,
        tp_pips=tp_pips, expiry_bars=expiry_bars
    )

    _, result = backtester.run(bars, strategy_mgr, cfg)
    result.period = period
    result.interval = interval

    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="BBPro Multi-Strategy Backtester")
    parser.add_argument("--symbol", default="EURUSD", help="Trading symbol (e.g. EURUSD, XAUUSD)")
    parser.add_argument("--period", default="1y", help="Data period (1y, 6mo, 3mo, 1mo)")
    parser.add_argument("--interval", default="1h", help="Bar interval (1h, 30m, 15m, 5m)")
    parser.add_argument("--sl", type=float, default=25, help="Stop loss in pips")
    parser.add_argument("--tp", type=float, default=40, help="Take profit in pips")
    parser.add_argument("--expiry", type=int, default=48, help="Signal expiry in bars")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    result = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        sl_pips=args.sl, tp_pips=args.tp, expiry_bars=args.expiry
    )

    if args.json:
        print(format_report_json(result))
    else:
        print(format_report(result))


if __name__ == "__main__":
    main()
