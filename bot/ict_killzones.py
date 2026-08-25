"""
ict_killzones.py — ICT Killzones + Liquidity Sweep Strategy
=============================================================
ICT (Inner Circle Trader) concepts:
  - Killzones: High-probability trading windows (London/NY sessions)
  - Liquidity Sweeps: Price raids previous highs/lows then reverses
  - Session-based signal generation (only during killzones)

Based on ICT concepts. Pure Python — no external dependencies.
"""

import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

try:
    from config import TradeDirection, BotConfig
except ImportError:
    from .config import TradeDirection, BotConfig


class ICTKillzoneStrategy:
    """
    ICT Killzone + Liquidity Sweep Strategy.

    Only generates signals during high-probability killzones.
    Detects liquidity sweeps (stop raids) and reversal entries.
    """

    def __init__(self, name: str = "ict_killzones"):
        self.name = name
        # Killzone times in UTC
        self.killzones = {
            "asian":      {"start": 1,  "end": 5},   # 01:00-05:00 UTC
            "london":     {"start": 7,  "end": 10},   # 07:00-10:00 UTC
            "new_york":   {"start": 12, "end": 15},   # 12:00-15:00 UTC
            "london_close": {"start": 15, "end": 17}, # 15:00-17:00 UTC
        }

    def _get_current_killzone(self, timestamp: float) -> Optional[str]:
        """Check if current time is within a killzone."""
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        hour = dt.hour

        for name, kz in self.killzones.items():
            if kz["start"] <= hour < kz["end"]:
                return name
        return None

    def _find_session_highs_lows(self, highs: np.ndarray, lows: np.ndarray,
                                  timestamps: np.ndarray, lookback: int = 20) -> Dict:
        """Find previous session highs and lows."""
        if len(highs) < lookback:
            lookback = len(highs)

        # Previous session range (before current bar)
        prev_highs = highs[-lookback:-1]
        prev_lows = lows[-lookback:-1]

        return {
            "session_high": float(np.max(prev_highs)),
            "session_low": float(np.min(prev_lows)),
            "session_high_idx": int(np.argmax(prev_highs)),
            "session_low_idx": int(np.argmin(prev_lows)),
        }

    def analyze(self, bars: Any, cfg: Optional[BotConfig] = None,
                indicators_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            cfg = cfg or BotConfig()

            # Extract OHLCV
            if hasattr(bars[0], "open"):
                opens = np.array([b.open for b in bars], dtype=float)
                highs = np.array([b.high for b in bars], dtype=float)
                lows = np.array([b.low for b in bars], dtype=float)
                closes = np.array([b.close for b in bars], dtype=float)
                timestamps = np.array([b.timestamp for b in bars], dtype=float)
            elif isinstance(bars[0], dict):
                opens = np.array([b["open"] for b in bars], dtype=float)
                highs = np.array([b["high"] for b in bars], dtype=float)
                lows = np.array([b["low"] for b in bars], dtype=float)
                closes = np.array([b["close"] for b in bars], dtype=float)
                timestamps = np.array([b.get("timestamp", b.get("time", 0)) for b in bars], dtype=float)
            else:
                closes = np.array(bars, dtype=float)
                opens, highs, lows = closes, closes, closes
                timestamps = np.arange(len(closes), dtype=float)

            if len(closes) < 25:
                return {"signal": None, "confidence": 0.0, "reason": "Insufficient data", "strategy": self.name}

            current_ts = timestamps[-1]
            killzone = self._get_current_killzone(current_ts)

            if killzone is None:
                return {"signal": None, "confidence": 0.0,
                        "reason": "Outside killzone hours", "strategy": self.name}

            # Find session levels
            levels = self._find_session_highs_lows(highs, lows, timestamps, lookback=20)

            curr_high = float(highs[-1])
            curr_low = float(lows[-1])
            curr_close = float(closes[-1])
            prev_close = float(closes[-2])
            curr_open = float(opens[-1])

            session_high = levels["session_high"]
            session_low = levels["session_low"]

            # Bullish Liquidity Sweep
            # Price broke below session low but closed back above
            if curr_low < session_low and curr_close > session_low:
                # Check for bullish reversal candle
                is_bullish = curr_close > curr_open
                sweep_depth = (session_low - curr_low) / max(session_low, 0.0001)
                recovery = (curr_close - session_low) / max(session_low, 0.0001)

                if is_bullish and recovery > 0:
                    confidence = round(min(95.0, 65.0 + sweep_depth * 1000 + 15.0), 2)
                    # Boost if in London or NY killzone
                    if killzone in ("london", "new_york"):
                        confidence = round(min(98.0, confidence + 10.0), 2)
                    reason = (
                        f"Bullish Liquidity Sweep in {killzone} killzone: "
                        f"Price swept session low ({session_low:.5f}) then closed above ({curr_close:.5f})"
                    )
                    return {
                        "signal": TradeDirection.BUY,
                        "confidence": confidence,
                        "reason": reason,
                        "strategy": self.name,
                    }

            # Bearish Liquidity Sweep
            # Price broke above session high but closed back below
            if curr_high > session_high and curr_close < session_high:
                is_bearish = curr_close < curr_open
                sweep_depth = (curr_high - session_high) / max(session_high, 0.0001)
                recovery = (session_high - curr_close) / max(session_high, 0.0001)

                if is_bearish and recovery > 0:
                    confidence = round(min(95.0, 65.0 + sweep_depth * 1000 + 15.0), 2)
                    if killzone in ("london", "new_york"):
                        confidence = round(min(98.0, confidence + 10.0), 2)
                    reason = (
                        f"Bearish Liquidity Sweep in {killzone} killzone: "
                        f"Price swept session high ({session_high:.5f}) then closed below ({curr_close:.5f})"
                    )
                    return {
                        "signal": TradeDirection.SELL,
                        "confidence": confidence,
                        "reason": reason,
                        "strategy": self.name,
                    }

            return {
                "signal": None,
                "confidence": 0.0,
                "reason": f"In {killzone} killzone but no liquidity sweep detected",
                "strategy": self.name,
            }

        except Exception as e:
            return {"signal": None, "confidence": 0.0, "reason": f"Error: {e}", "strategy": self.name}

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        return self.analyze(bars, cfg)
