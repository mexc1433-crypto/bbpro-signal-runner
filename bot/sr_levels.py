"""
sr_levels.py — Support & Resistance Level Detection
=====================================================
Detects swing highs/lows and clusters them into S/R levels.
"""

import numpy as np
from typing import Dict, List


class SRLevels:
    """Support/Resistance level calculator."""

    def __init__(self, lookback: int = 100, min_touches: int = 2, tolerance: float = 0.001):
        self.lookback = lookback
        self.min_touches = min_touches
        self.tolerance = tolerance  # % tolerance for clustering

    def _find_swings(self, highs, lows, window=3):
        """Find swing highs and lows."""
        swing_highs = []
        swing_lows = []
        for i in range(window, len(highs) - window):
            if highs[i] == max(highs[i-window:i+window+1]):
                swing_highs.append(highs[i])
            if lows[i] == min(lows[i-window:i+window+1]):
                swing_lows.append(lows[i])
        return swing_highs, swing_lows

    def _cluster(self, levels, current_price):
        """Cluster nearby levels into single levels."""
        if not levels:
            return []

        levels_sorted = sorted(levels)
        clusters = [[levels_sorted[0]]]

        for lvl in levels_sorted[1:]:
            if abs(lvl - clusters[-1][-1]) / clusters[-1][-1] < self.tolerance:
                clusters[-1].append(lvl)
            else:
                clusters.append([lvl])

        # Average each cluster and count touches
        result = []
        for cluster in clusters:
            avg = sum(cluster) / len(cluster)
            result.append({
                "price": avg,
                "touches": len(cluster),
                "strength": min(1.0, len(cluster) / 5),
            })
        return result

    def calculate(self, bars: list) -> Dict:
        """Calculate S/R levels from bars."""
        if not bars or len(bars) < 20:
            return {
                "resistance": [], "support": [],
                "nearest_resistance": 0, "nearest_support": 0,
                "all_levels": [],
            }

        n = min(len(bars), self.lookback)
        highs = [b.high for b in bars[-n:]]
        lows = [b.low for b in bars[-n:]]
        close_now = bars[-1].close

        swing_highs, swing_lows = self._find_swings(highs, lows)

        res_clusters = self._cluster(swing_highs, close_now)
        sup_clusters = self._cluster(swing_lows, close_now)

        # Filter: only levels above current price are resistance, below are support
        resistance = [r["price"] for r in res_clusters if r["price"] > close_now]
        support = [s["price"] for s in sup_clusters if s["price"] < close_now]

        # Sort by proximity to current price
        resistance.sort(key=lambda x: x - close_now)
        support.sort(key=lambda x: close_now - x)

        # Limit to 3 each
        resistance = resistance[:3]
        support = support[:3]

        nearest_res = resistance[0] if resistance else 0
        nearest_sup = support[0] if support else 0

        all_levels = (
            [{"price": r, "type": "resistance", "touches": 1, "strength": 0.5} for r in resistance] +
            [{"price": s, "type": "support", "touches": 1, "strength": 0.5} for s in support]
        )

        return {
            "resistance": resistance,
            "support": support,
            "nearest_resistance": nearest_res,
            "nearest_support": nearest_sup,
            "all_levels": all_levels,
        }

    def format_for_signal(self, levels: dict, current_price: float, symbol: str) -> str:
        """Format S/R levels for Telegram message."""
        lines = []
        for r in levels.get("resistance", [])[:2]:
            lines.append(f"⚠️ مقاومة عند {r:.2f}" if "XAU" in symbol.upper() else f"⚠️ مقاومة عند {r:.4f}")
        for s in levels.get("support", [])[:2]:
            lines.append(f"💡 دعم عند {s:.2f}" if "XAU" in symbol.upper() else f"💡 دعم عند {s:.4f}")
        return "\n".join(lines) if lines else ""
