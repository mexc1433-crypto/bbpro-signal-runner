"""
fvg_strategy.py — Fair Value Gap (FVG) Strategy
================================================
ICT concept: Fair Value Gap = 3-candle price imbalance.
Price tends to return to fill these gaps, creating entry opportunities.

Bullish FVG: candle[i-2].high < candle[i].low (gap up, imbalance left)
Bearish FVG: candle[i-2].low > candle[i].high (gap down, imbalance left)

Strategy: Wait for price to return to unfilled FVG, then enter in FVG direction.
"""

import numpy as np
from typing import Dict, Any, Optional, List

try:
    from config import TradeDirection, BotConfig
except ImportError:
    from .config import TradeDirection, BotConfig


class FVGStrategy:
    """
    Fair Value Gap Strategy.

    Detects FVGs, tracks whether they've been filled,
    and generates signals when price returns to unfilled gaps.
    """

    def __init__(self, name: str = "fvg"):
        self.name = name
        self.body_multiplier = 1.5  # minimum middle candle body for momentum
        self.fvg_lookback = 50  # how many bars to look back for FVGs

    def _detect_fvgs(self, highs: np.ndarray, lows: np.ndarray,
                     opens: np.ndarray, closes: np.ndarray) -> List[dict]:
        """Detect Fair Value Gaps in the price data."""
        fvgs = []
        n = len(closes)

        if n < 3:
            return fvgs

        # Calculate average body for momentum filter
        bodies = np.abs(closes - opens)
        avg_body = np.mean(bodies[-50:]) if len(bodies) >= 50 else np.mean(bodies)

        start = max(2, n - self.fvg_lookback)

        for i in range(start, n):
            first_high = highs[i-2]
            first_low = lows[i-2]
            middle_body = abs(closes[i-1] - opens[i-1])
            third_low = lows[i]
            third_high = highs[i]

            # Bullish FVG: gap between candle1.high and candle3.low
            if third_low > first_high and middle_body > avg_body * self.body_multiplier:
                fvgs.append({
                    "type": "bullish",
                    "top": float(third_low),
                    "bottom": float(first_high),
                    "index": i,
                    "filled": False,
                })

            # Bearish FVG: gap between candle1.low and candle3.high
            elif third_high < first_low and middle_body > avg_body * self.body_multiplier:
                fvgs.append({
                    "type": "bearish",
                    "top": float(first_low),
                    "bottom": float(third_high),
                    "index": i,
                    "filled": False,
                })

        # Check if FVGs were filled
        for fvg in fvgs:
            for j in range(fvg["index"] + 1, n):
                if fvg["type"] == "bullish":
                    if lows[j] <= fvg["bottom"]:
                        fvg["filled"] = True
                        break
                else:
                    if highs[j] >= fvg["top"]:
                        fvg["filled"] = True
                        break

        return fvgs

    def _check_premium_discount(self, highs: np.ndarray, lows: np.ndarray,
                                  lookback: int = 50) -> Dict[str, Any]:
        """Check if price is in premium or discount zone."""
        if len(highs) < lookback:
            lookback = len(highs)

        range_high = float(np.max(highs[-lookback:]))
        range_low = float(np.min(lows[-lookback:]))
        mid_point = (range_high + range_low) / 2

        return {
            "range_high": range_high,
            "range_low": range_low,
            "mid_point": mid_point,
            "is_premium": float(lows[-1]) > mid_point,
            "is_discount": float(highs[-1]) < mid_point,
        }

    def analyze(self, bars: Any, cfg: Optional[BotConfig] = None,
                indicators_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            cfg = cfg or BotConfig()

            if hasattr(bars[0], "open"):
                opens = np.array([b.open for b in bars], dtype=float)
                highs = np.array([b.high for b in bars], dtype=float)
                lows = np.array([b.low for b in bars], dtype=float)
                closes = np.array([b.close for b in bars], dtype=float)
            elif isinstance(bars[0], dict):
                opens = np.array([b["open"] for b in bars], dtype=float)
                highs = np.array([b["high"] for b in bars], dtype=float)
                lows = np.array([b["low"] for b in bars], dtype=float)
                closes = np.array([b["close"] for b in bars], dtype=float)
            else:
                closes = np.array(bars, dtype=float)
                opens, highs, lows = closes, closes, closes

            if len(closes) < 15:
                return {"signal": None, "confidence": 0.0, "reason": "Insufficient data", "strategy": self.name}

            # Detect FVGs
            fvgs = self._detect_fvgs(highs, lows, opens, closes)
            unfilled = [f for f in fvgs if not f["filled"]]

            if not unfilled:
                return {"signal": None, "confidence": 0.0, "reason": "No unfilled FVGs", "strategy": self.name}

            # Get premium/discount zone
            pd_zone = self._check_premium_discount(highs, lows)

            curr_high = float(highs[-1])
            curr_low = float(lows[-1])
            curr_close = float(closes[-1])
            curr_open = float(opens[-1])
            is_bullish = curr_close > curr_open
            is_bearish = curr_close < curr_open

            # Check if price is interacting with any unfilled FVG
            for fvg in unfilled[-3:]:  # check last 3 unfilled FVGs
                fvg_top = fvg["top"]
                fvg_bottom = fvg["bottom"]
                fvg_mid = (fvg_top + fvg_bottom) / 2

                # Bullish FVG entry: price touching FVG from above and bouncing
                if fvg["type"] == "bullish":
                    # Check if current bar touched the FVG
                    if curr_low <= fvg_top and curr_close > fvg_bottom:
                        # Price entered FVG and bounced back up
                        if is_bullish:
                            # Better if in discount zone
                            zone_bonus = 10.0 if pd_zone["is_discount"] else 0.0
                            # Calculate how deep into the FVG we went
                            depth = max(0, fvg_top - curr_low) / max(fvg_top - fvg_bottom, 0.0001)
                            confidence = round(min(95.0, 60.0 + depth * 20 + zone_bonus), 2)
                            reason = (
                                f"Bullish FVG entry: Price returned to unfilled FVG "
                                f"({fvg_bottom:.5f}-{fvg_top:.5f}) and bounced with bullish candle"
                            )
                            return {
                                "signal": TradeDirection.BUY,
                                "confidence": confidence,
                                "reason": reason,
                                "strategy": self.name,
                            }

                # Bearish FVG entry: price touching FVG from below and rejecting
                elif fvg["type"] == "bearish":
                    if curr_high >= fvg_bottom and curr_close < fvg_top:
                        if is_bearish:
                            zone_bonus = 10.0 if pd_zone["is_premium"] else 0.0
                            depth = max(0, curr_high - fvg_bottom) / max(fvg_top - fvg_bottom, 0.0001)
                            confidence = round(min(95.0, 60.0 + depth * 20 + zone_bonus), 2)
                            reason = (
                                f"Bearish FVG entry: Price returned to unfilled FVG "
                                f"({fvg_bottom:.5f}-{fvg_top:.5f}) and rejected with bearish candle"
                            )
                            return {
                                "signal": TradeDirection.SELL,
                                "confidence": confidence,
                                "reason": reason,
                                "strategy": self.name,
                            }

            return {"signal": None, "confidence": 0.0,
                     "reason": f"{len(unfilled)} unfilled FVGs but price not interacting",
                     "strategy": self.name}

        except Exception as e:
            return {"signal": None, "confidence": 0.0, "reason": f"Error: {e}", "strategy": self.name}

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        return self.analyze(bars, cfg)
