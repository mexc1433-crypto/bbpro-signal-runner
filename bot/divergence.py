"""
divergence.py — RSI & MACD Divergence Detection
=================================================
Divergence = price makes higher high but indicator makes lower high (bearish)
or price makes lower low but indicator makes higher low (bullish).

This is one of the most reliable reversal signals in trading.
"""

import numpy as np
from typing import Dict, List, Optional


class DivergenceDetector:
    """Detects RSI and MACD divergences."""

    def __init__(self, lookback: int = 50, min_swing_dist: float = 0.001):
        self.lookback = lookback
        self.min_swing_dist = min_swing_dist

    def _find_swings(self, data: np.ndarray, window: int = 3) -> List[dict]:
        """Find local maxima and minima."""
        swings = []
        for i in range(window, len(data) - window):
            # Local max
            is_max = all(data[i] >= data[j] for j in range(i - window, i + window + 1) if j != i)
            if is_max:
                swings.append({"index": i, "type": "high", "value": float(data[i])})

            # Local min
            is_min = all(data[i] <= data[j] for j in range(i - window, i + window + 1) if j != i)
            if is_min:
                swings.append({"index": i, "type": "low", "value": float(data[i])})
        return swings

    def detect_rsi_divergence(self, closes: np.ndarray, rsi_arr: np.ndarray) -> Dict:
        """
        Detect RSI divergence.

        Bullish: price lower low, RSI higher low
        Bearish: price higher high, RSI lower high
        """
        if len(closes) < 30 or len(rsi_arr) < 30:
            return {"divergence": None, "type": None, "confidence": 0, "description": ""}

        # Find recent swings
        price_swings = self._find_swings(closes, window=3)
        rsi_swings = self._find_swings(rsi_arr, window=3)

        price_highs = [s for s in price_swings if s["type"] == "high"]
        price_lows = [s for s in price_swings if s["type"] == "low"]
        rsi_highs = [s for s in rsi_swings if s["type"] == "high"]
        rsi_lows = [s for s in rsi_swings if s["type"] == "low"]

        # Bearish divergence: price higher high, RSI lower high
        if len(price_highs) >= 2 and len(rsi_highs) >= 2:
            p1, p2 = price_highs[-2], price_highs[-1]
            r1, r2 = rsi_highs[-2], rsi_highs[-1]

            if p2["value"] > p1["value"] and r2["value"] < r1["value"]:
                # Ensure RSI values aren't NaN
                if not np.isnan(r1["value"]) and not np.isnan(r2["value"]):
                    strength = abs(r1["value"] - r2["value"])
                    return {
                        "divergence": "bearish",
                        "type": "regular",
                        "confidence": min(85, 50 + strength * 2),
                        "description": f"Bearish RSI divergence: price {p1['value']:.5f}→{p2['value']:.5f}, RSI {r1['value']:.0f}→{r2['value']:.0f}",
                    }

        # Bullish divergence: price lower low, RSI higher low
        if len(price_lows) >= 2 and len(rsi_lows) >= 2:
            p1, p2 = price_lows[-2], price_lows[-1]
            r1, r2 = rsi_lows[-2], rsi_lows[-1]

            if p2["value"] < p1["value"] and r2["value"] > r1["value"]:
                if not np.isnan(r1["value"]) and not np.isnan(r2["value"]):
                    strength = abs(r2["value"] - r1["value"])
                    return {
                        "divergence": "bullish",
                        "type": "regular",
                        "confidence": min(85, 50 + strength * 2),
                        "description": f"Bullish RSI divergence: price {p1['value']:.5f}→{p2['value']:.5f}, RSI {r1['value']:.0f}→{r2['value']:.0f}",
                    }

        return {"divergence": None, "type": None, "confidence": 0, "description": ""}

    def detect_macd_divergence(self, closes: np.ndarray, macd_arr: np.ndarray) -> Dict:
        """
        Detect MACD histogram divergence.

        Bullish: price lower low, MACD higher low
        Bearish: price higher high, MACD lower high
        """
        if len(closes) < 30 or len(macd_arr) < 30:
            return {"divergence": None, "type": None, "confidence": 0, "description": ""}

        price_swings = self._find_swings(closes, window=3)
        macd_swings = self._find_swings(macd_arr, window=3)

        price_highs = [s for s in price_swings if s["type"] == "high"]
        price_lows = [s for s in price_swings if s["type"] == "low"]
        macd_highs = [s for s in macd_swings if s["type"] == "high"]
        macd_lows = [s for s in macd_swings if s["type"] == "low"]

        # Bearish: price higher high, MACD lower high
        if len(price_highs) >= 2 and len(macd_highs) >= 2:
            p1, p2 = price_highs[-2], price_highs[-1]
            m1, m2 = macd_highs[-2], macd_highs[-1]

            if p2["value"] > p1["value"] and m2["value"] < m1["value"]:
                if not np.isnan(m1["value"]) and not np.isnan(m2["value"]):
                    return {
                        "divergence": "bearish",
                        "type": "regular",
                        "confidence": 75,
                        "description": "Bearish MACD divergence",
                    }

        # Bullish: price lower low, MACD higher low
        if len(price_lows) >= 2 and len(macd_lows) >= 2:
            p1, p2 = price_lows[-2], price_lows[-1]
            m1, m2 = macd_lows[-2], macd_lows[-1]

            if p2["value"] < p1["value"] and m2["value"] > m1["value"]:
                if not np.isnan(m1["value"]) and not np.isnan(m2["value"]):
                    return {
                        "divergence": "bullish",
                        "type": "regular",
                        "confidence": 75,
                        "description": "Bullish MACD divergence",
                    }

        return {"divergence": None, "type": None, "confidence": 0, "description": ""}

    def detect_all(self, closes: np.ndarray, rsi_arr: np.ndarray,
                    macd_arr: Optional[np.ndarray] = None) -> Dict:
        """Detect all divergences."""
        result = {"rsi": None, "macd": None, "any_bullish": False, "any_bearish": False}

        rsi_div = self.detect_rsi_divergence(closes, rsi_arr)
        result["rsi"] = rsi_div

        if rsi_div["divergence"] == "bullish":
            result["any_bullish"] = True
        elif rsi_div["divergence"] == "bearish":
            result["any_bearish"] = True

        if macd_arr is not None:
            macd_div = self.detect_macd_divergence(closes, macd_arr)
            result["macd"] = macd_div
            if macd_div["divergence"] == "bullish":
                result["any_bullish"] = True
            elif macd_div["divergence"] == "bearish":
                result["any_bearish"] = True

        return result
