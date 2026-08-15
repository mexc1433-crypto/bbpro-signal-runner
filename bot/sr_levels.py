"""
sr_levels.py
============
Support/Resistance level detection and display for BBPro Signal Bot.

Detects swing highs and swing lows from historical market bars, clusters close price levels
into support and resistance zones, and formats them for Telegram signal notifications.
"""

import numpy as np
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class SRLevels:
    """
    Support and Resistance level detection and display.
    """

    def __init__(self, lookback: int = 100, min_touches: int = 2, tolerance: float = 0.001):
        """
        Initialize S/R level detector.

        Args:
            lookback: Number of recent bars to evaluate (default: 100).
            min_touches: Minimum bar touches to validate an S/R level (default: 2).
            tolerance: Relative price tolerance for clustering levels (default: 0.001 = 0.1%).
        """
        self.lookback = lookback
        self.min_touches = min_touches
        self.tolerance = tolerance

    def calculate(self, bars: List[Any]) -> Dict[str, Any]:
        """
        Calculates support and resistance levels from bar data.

        Args:
            bars: List of bar objects or dictionaries with high, low, close attributes/keys.

        Returns:
            Dict containing:
                - "resistance": List[float] sorted nearest to price first (max 3)
                - "support": List[float] sorted nearest to price first (max 3)
                - "nearest_resistance": float (or 0.0 if none)
                - "nearest_support": float (or 0.0 if none)
                - "all_levels": List[dict] with price, type, touches, strength
        """
        if not bars:
            return {
                "resistance": [],
                "support": [],
                "nearest_resistance": 0.0,
                "nearest_support": 0.0,
                "all_levels": [],
            }

        recent_bars = bars[-self.lookback:]
        highs = np.array([getattr(b, "high", b.get("high") if isinstance(b, dict) else 0.0) for b in recent_bars], dtype=float)
        lows = np.array([getattr(b, "low", b.get("low") if isinstance(b, dict) else 0.0) for b in recent_bars], dtype=float)
        closes = np.array([getattr(b, "close", b.get("close") if isinstance(b, dict) else 0.0) for b in recent_bars], dtype=float)

        current_price = float(closes[-1])
        n = len(recent_bars)

        # 1. Identify swing highs and swing lows
        swing_points = []
        w = 2  # swing detection window radius
        if n >= 2 * w + 1:
            for i in range(w, n - w):
                # Swing High
                if all(highs[i] >= highs[i - k] for k in range(1, w + 1)) and \
                   all(highs[i] >= highs[i + k] for k in range(1, w + 1)):
                    swing_points.append(highs[i])

                # Swing Low
                if all(lows[i] <= lows[i - k] for k in range(1, w + 1)) and \
                   all(lows[i] <= lows[i + k] for k in range(1, w + 1)):
                    swing_points.append(lows[i])
        else:
            swing_points.extend(highs.tolist())
            swing_points.extend(lows.tolist())

        if len(highs) > 0:
            swing_points.append(float(np.max(highs)))
            swing_points.append(float(np.min(lows)))

        if not swing_points:
            return {
                "resistance": [],
                "support": [],
                "nearest_resistance": 0.0,
                "nearest_support": 0.0,
                "all_levels": [],
            }

        # 2. Cluster swing points into price zones
        swing_points = sorted(swing_points)
        clusters: List[List[float]] = []

        for p in swing_points:
            added = False
            for cluster in clusters:
                cluster_mean = float(np.mean(cluster))
                tol_range = max(cluster_mean * self.tolerance, 1e-8)
                if abs(p - cluster_mean) <= tol_range:
                    cluster.append(p)
                    added = True
                    break
            if not added:
                clusters.append([p])

        # 3. Evaluate each cluster across historical bars
        all_levels = []
        for cluster in clusters:
            level_price = float(np.mean(cluster))

            tol_dist = max(level_price * self.tolerance, 1e-8)
            touches = 0
            for i in range(n):
                if lows[i] <= (level_price + tol_dist) and highs[i] >= (level_price - tol_dist):
                    touches += 1

            touches = max(touches, len(cluster))

            if touches < self.min_touches:
                continue

            level_type = "resistance" if level_price > current_price else "support"
            strength = round(float(touches * 10.0 + len(cluster) * 5.0), 2)

            all_levels.append({
                "price": round(level_price, 5),
                "type": level_type,
                "touches": int(touches),
                "strength": strength,
            })

        # Separate support and resistance levels
        resistance_levels = [lvl for lvl in all_levels if lvl["type"] == "resistance"]
        support_levels = [lvl for lvl in all_levels if lvl["type"] == "support"]

        # Sort nearest to price first
        resistance_levels.sort(key=lambda lvl: lvl["price"] - current_price)
        support_levels.sort(key=lambda lvl: current_price - lvl["price"])

        resistance_prices = [lvl["price"] for lvl in resistance_levels[:3]]
        support_prices = [lvl["price"] for lvl in support_levels[:3]]

        nearest_resistance = resistance_prices[0] if resistance_prices else 0.0
        nearest_support = support_prices[0] if support_prices else 0.0

        return {
            "resistance": resistance_prices,
            "support": support_prices,
            "nearest_resistance": nearest_resistance,
            "nearest_support": nearest_support,
            "all_levels": all_levels,
        }

    def format_for_signal(self, levels: Dict[str, Any], current_price: float, symbol: str = "") -> str:
        """
        Formats Support & Resistance info into Arabic text suitable for Telegram signal messages.

        Example Output:
        ⚠️ مقاومة قوية عند 4435
        💡 دعم قوي عند 4410
        """
        nearest_res = levels.get("nearest_resistance", 0.0)
        nearest_sup = levels.get("nearest_support", 0.0)

        lines = []
        if nearest_res and nearest_res > 0:
            lines.append(f"⚠️ مقاومة قوية عند {self._format_price(nearest_res)}")

        if nearest_sup and nearest_sup > 0:
            lines.append(f"💡 دعم قوي عند {self._format_price(nearest_sup)}")

        return "\n".join(lines)

    @staticmethod
    def _format_price(price: float) -> str:
        """Helper to format price string cleanly (e.g. 4435.0 -> '4435', 1.08500 -> '1.085')."""
        if price == int(price):
            return str(int(price))
        if price >= 100:
            return f"{price:.2f}".rstrip("0").rstrip(".")
        return f"{price:.5f}".rstrip("0").rstrip(".")
