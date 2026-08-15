"""
volume_profile.py — Volume Profile Strategy
=============================================
Volume Profile shows where most trading activity occurred.
Identifies POC (Point of Control), Value Area High/Low, and volume nodes.

Signals:
  BUY: Price at/below VAL (low volume area) bouncing toward POC
  SELL: Price at/above VAH (high volume area) rejecting toward POC

Note: Forex volume is tick volume (not true volume), but still shows activity patterns.
"""

import numpy as np
from typing import Dict, Any, Optional, List, Tuple

try:
    from config import TradeDirection, BotConfig
except ImportError:
    from .config import TradeDirection, BotConfig


class VolumeProfileStrategy:
    """
    Volume Profile Strategy.

    Builds a volume histogram by price level, finds POC and Value Area,
    and generates signals when price interacts with key levels.
    """

    def __init__(self, name: str = "volume_profile"):
        self.name = name
        self.num_bins = 20
        self.value_area_pct = 0.70  # 70% of volume in value area

    def _build_volume_profile(self, highs: np.ndarray, lows: np.ndarray,
                               closes: np.ndarray, volumes: np.ndarray,
                               num_bins: int = None) -> Dict[str, Any]:
        """
        Build volume profile histogram.
        For each price bin, accumulate volume of bars whose range overlaps.
        """
        num_bins = num_bins or self.num_bins
        n = len(closes)
        if n < 10:
            return None

        price_min = float(np.min(lows))
        price_max = float(np.max(highs))
        if price_max == price_min:
            return None

        bin_size = (price_max - price_min) / num_bins
        bin_volumes = np.zeros(num_bins)
        bin_centers = np.zeros(num_bins)

        for i in range(num_bins):
            bin_low = price_min + i * bin_size
            bin_high = bin_low + bin_size
            bin_centers[i] = (bin_low + bin_high) / 2

        # Distribute volume across price bins
        for i in range(n):
            bar_high = highs[i]
            bar_low = lows[i]
            bar_vol = volumes[i] if volumes[i] > 0 else 1.0

            # Find which bins this bar overlaps
            low_bin = int((bar_low - price_min) / bin_size)
            high_bin = int((bar_high - price_min) / bin_size)
            low_bin = max(0, min(num_bins - 1, low_bin))
            high_bin = max(0, min(num_bins - 1, high_bin))

            # Distribute volume evenly across overlapping bins
            num_overlapping = high_bin - low_bin + 1
            vol_per_bin = bar_vol / max(num_overlapping, 1)
            for b in range(low_bin, high_bin + 1):
                bin_volumes[b] += vol_per_bin

        # Find POC (Point of Control) — bin with highest volume
        poc_idx = int(np.argmax(bin_volumes))
        poc_price = float(bin_centers[poc_idx])

        # Find Value Area (70% of total volume around POC)
        total_vol = np.sum(bin_volumes)
        if total_vol == 0:
            return None

        target_vol = total_vol * self.value_area_pct
        vol_sum = bin_volumes[poc_idx]
        va_low_idx = poc_idx
        va_high_idx = poc_idx

        while vol_sum < target_vol and (va_low_idx > 0 or va_high_idx < num_bins - 1):
            # Expand to whichever side has more volume
            expand_low = bin_volumes[va_low_idx - 1] if va_low_idx > 0 else 0
            expand_high = bin_volumes[va_high_idx + 1] if va_high_idx < num_bins - 1 else 0

            if expand_low >= expand_high and va_low_idx > 0:
                va_low_idx -= 1
                vol_sum += bin_volumes[va_low_idx]
            elif va_high_idx < num_bins - 1:
                va_high_idx += 1
                vol_sum += bin_volumes[va_high_idx]
            else:
                break

        vah = float(bin_centers[va_high_idx])
        val = float(bin_centers[va_low_idx])

        # Identify volume nodes
        avg_vol = total_vol / num_bins
        hvn_threshold = avg_vol * 1.5  # High Volume Node
        lvn_threshold = avg_vol * 0.5  # Low Volume Node

        high_vol_nodes = [float(bin_centers[i]) for i in range(num_bins)
                         if bin_volumes[i] > hvn_threshold]
        low_vol_nodes = [float(bin_centers[i]) for i in range(num_bins)
                        if bin_volumes[i] < lvn_threshold]

        return {
            "poc": poc_price,
            "vah": vah,  # Value Area High
            "val": val,  # Value Area Low
            "bin_volumes": bin_volumes.tolist(),
            "bin_centers": bin_centers.tolist(),
            "high_vol_nodes": high_vol_nodes,
            "low_vol_nodes": low_vol_nodes,
            "total_vol": float(total_vol),
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
                volumes = np.array([b.volume for b in bars], dtype=float)
            elif isinstance(bars[0], dict):
                opens = np.array([b["open"] for b in bars], dtype=float)
                highs = np.array([b["high"] for b in bars], dtype=float)
                lows = np.array([b["low"] for b in bars], dtype=float)
                closes = np.array([b["close"] for b in bars], dtype=float)
                volumes = np.array([b.get("volume", 1.0) for b in bars], dtype=float)
            else:
                closes = np.array(bars, dtype=float)
                opens, highs, lows = closes, closes, closes
                volumes = np.ones(len(closes), dtype=float)

            if len(closes) < 30:
                return {"signal": None, "confidence": 0.0, "reason": "Insufficient data", "strategy": self.name}

            # Use last 100 bars for volume profile
            lookback = min(100, len(closes))
            vp = self._build_volume_profile(
                highs[-lookback:], lows[-lookback:], closes[-lookback:],
                volumes[-lookback:], self.num_bins
            )

            if vp is None:
                return {"signal": None, "confidence": 0.0, "reason": "VP build failed", "strategy": self.name}

            poc = vp["poc"]
            vah = vp["vah"]
            val = vp["val"]

            curr_close = float(closes[-1])
            curr_open = float(opens[-1])
            curr_high = float(highs[-1])
            curr_low = float(lows[-1])
            is_bullish = curr_close > curr_open
            is_bearish = curr_close < curr_open

            # BUY: Price at/below VAL and bouncing up
            if curr_low <= val * 1.001 and is_bullish and curr_close > val:
                # How far below VAL we went
                depth = max(0, val - curr_low) / max(val, 0.0001)
                confidence = round(min(92.0, 60.0 + depth * 100 + 15.0), 2)
                # Check if near a low volume node (price will move fast)
                for lvn in vp["low_vol_nodes"]:
                    if abs(curr_close - lvn) / max(lvn, 0.0001) < 0.002:
                        confidence = round(min(95.0, confidence + 5.0), 2)
                        break

                reason = (
                    f"Volume Profile BUY: Price bouncing off VAL ({val:.5f}) "
                    f"toward POC ({poc:.5f}) with bullish candle"
                )
                return {
                    "signal": TradeDirection.BUY,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            # SELL: Price at/above VAH and rejecting down
            if curr_high >= vah * 0.999 and is_bearish and curr_close < vah:
                depth = max(0, curr_high - vah) / max(vah, 0.0001)
                confidence = round(min(92.0, 60.0 + depth * 100 + 15.0), 2)
                for lvn in vp["low_vol_nodes"]:
                    if abs(curr_close - lvn) / max(lvn, 0.0001) < 0.002:
                        confidence = round(min(95.0, confidence + 5.0), 2)
                        break

                reason = (
                    f"Volume Profile SELL: Price rejecting from VAH ({vah:.5f}) "
                    f"toward POC ({poc:.5f}) with bearish candle"
                )
                return {
                    "signal": TradeDirection.SELL,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            return {"signal": None, "confidence": 0.0,
                     "reason": f"Price at {curr_close:.5f}, POC={poc:.5f}, VAH={vah:.5f}, VAL={val:.5f}",
                     "strategy": self.name}

        except Exception as e:
            return {"signal": None, "confidence": 0.0, "reason": f"Error: {e}", "strategy": self.name}

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        return self.analyze(bars, cfg)
