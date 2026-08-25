"""
signal_tracker.py — Active Signal Tracking
=============================================
Tracks signals after sending and checks if TP or SL was hit.
"""

import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ActiveSignal:
    signal_id: str
    symbol: str
    side: str          # "buy" or "sell"
    entry: float
    sl: float
    tp: float
    bar_time: float   # timestamp of the bar when signal was sent
    created_at: float = field(default_factory=time.time)


class SignalTracker:
    """Tracks active signals and checks if they hit TP/SL/expiry."""

    def __init__(self, expiry_bars: int = 48, db_path: str = ""):
        self.expiry_bars = expiry_bars
        self.db_path = db_path
        self._active: Dict[str, ActiveSignal] = {}
        self._results: List[dict] = []

    def add_signal(self, signal_id: str, symbol: str, side: str,
                   entry: float, sl: float, tp: float, bar_time: float):
        """Add a new signal to track."""
        self._active[signal_id] = ActiveSignal(
            signal_id=signal_id, symbol=symbol, side=side,
            entry=entry, sl=sl, tp=tp, bar_time=bar_time,
        )

    async def check_signals(self, client) -> List[dict]:
        """Check all active signals against current prices."""
        if not self._active:
            return []

        results = []
        # Group by symbol to minimize API calls
        symbols = set(s.symbol for s in self._active.values())
        quotes = {}
        for sym in symbols:
            try:
                bid, ask = await client.get_quote(sym)
                quotes[sym] = (bid, ask)
            except Exception:
                pass

        now = time.time()

        for sig_id, sig in list(self._active.items()):
            quote = quotes.get(sig.symbol)
            if not quote or not quote[0]:
                continue

            _, ask = quote
            current = ask

            if sig.side == "buy":
                # Check TP
                if current >= sig.tp:
                    pips = abs(sig.tp - sig.entry) / self._pip_size(sig.symbol)
                    results.append({
                        "signal_id": sig_id, "result": "WIN",
                        "symbol": sig.symbol, "side": sig.side,
                        "price": sig.tp, "pips": pips,
                    })
                # Check SL
                elif current <= sig.sl:
                    pips = abs(sig.sl - sig.entry) / self._pip_size(sig.symbol)
                    results.append({
                        "signal_id": sig_id, "result": "LOSS",
                        "symbol": sig.symbol, "side": sig.side,
                        "price": sig.sl, "pips": pips,
                    })
            else:  # sell
                # Check TP
                if current <= sig.tp:
                    pips = abs(sig.entry - sig.tp) / self._pip_size(sig.symbol)
                    results.append({
                        "signal_id": sig_id, "result": "WIN",
                        "symbol": sig.symbol, "side": sig.side,
                        "price": sig.tp, "pips": pips,
                    })
                # Check SL
                elif current >= sig.sl:
                    pips = abs(sig.entry - sig.sl) / self._pip_size(sig.symbol)
                    results.append({
                        "signal_id": sig_id, "result": "LOSS",
                        "symbol": sig.symbol, "side": sig.side,
                        "price": sig.sl, "pips": pips,
                    })

            # Check expiry (24h default for m30 = 48 bars)
            if sig_id not in [r["signal_id"] for r in results]:
                max_age = self.expiry_bars * 1800  # 30 min per bar (m30)
                if now - sig.created_at > max_age:
                    results.append({
                        "signal_id": sig_id, "result": "EXPIRED",
                        "symbol": sig.symbol, "side": sig.side,
                        "price": current, "pips": 0,
                    })

        # Store results
        for r in results:
            self._results.append(r)

        return results

    def _pip_size(self, symbol: str) -> float:
        pip_map = {"XAUUSD": 0.1, "XAGUSD": 0.01, "USDJPY": 0.01, "EURJPY": 0.01, "GBPJPY": 0.01}
        return pip_map.get(symbol.upper(), 0.0001)

    def get_active(self) -> List[ActiveSignal]:
        return list(self._active.values())

    def remove_signal(self, signal_id: str):
        self._active.pop(signal_id, None)

    def get_stats(self) -> dict:
        """Get win/loss statistics."""
        wins = sum(1 for r in self._results if r["result"] == "WIN")
        losses = sum(1 for r in self._results if r["result"] == "LOSS")
        expired = sum(1 for r in self._results if r["result"] == "EXPIRED")
        total = len(self._results)
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        total_pips = sum(r["pips"] if r["result"] == "WIN" else -r["pips"]
                        for r in self._results if r["result"] in ("WIN", "LOSS"))

        return {
            "total": total, "wins": wins, "losses": losses,
            "expired": expired, "win_rate": win_rate, "total_pips": total_pips,
        }
