"""
vwap.py — VWAP (Volume Weighted Average Price) Strategy
=========================================================
VWAP is used by institutions to measure the average price weighted by volume.
This module provides VWAP calculation, bands, and trading signals.

Features:
  - VWAP calculation (session-based)
  - VWAP bands (±1, ±2 standard deviations)
  - Buy/sell signals based on VWAP cross and band interactions
  - Anchored VWAP support
"""

import numpy as np
from typing import Dict, Optional, List
from dataclasses import dataclass


@dataclass
class VWAPResult:
    """Result from VWAP analysis."""
    signal: Optional[str]  # "buy", "sell", None
    confidence: float       # 0-100
    reason: str
    vwap: float
    upper_band: float
    lower_band: float


class VWAPStrategy:
    """VWAP-based trading strategy."""

    def __init__(self, num_bars_session: int = 96, band_mult: float = 1.0,
                 band_mult_2: float = 2.0):
        """
        Args:
            num_bars_session: bars per session (96 = 24h on M15, 48 = 24h on M30)
            band_mult: multiplier for first band
            band_mult_2: multiplier for second band
        """
        self.num_bars_session = num_bars_session
        self.band_mult = band_mult
        self.band_mult_2 = band_mult_2

    def calculate_vwap(self, highs: np.ndarray, lows: np.ndarray,
                        closes: np.ndarray, volumes: np.ndarray) -> Dict:
        """
        Calculate VWAP and bands.

        VWAP = Σ(Typical Price × Volume) / Σ(Volume)
        where Typical Price = (High + Low + Close) / 3
        """
        n = min(len(closes), self.num_bars_session)

        typical_prices = (highs[-n:] + lows[-n:] + closes[-n:]) / 3.0
        vols = volumes[-n:]

        # Handle zero volume
        total_vol = np.sum(vols)
        if total_vol <= 0:
            vols = np.ones_like(vols)
            total_vol = len(vols)

        # Cumulative VWAP
        cumvol = np.cumsum(vols)
        cumtp = np.cumsum(typical_prices * vols)
        vwap_arr = cumtp / cumvol

        vwap_now = float(vwap_arr[-1])

        # VWAP bands (standard deviation of price vs VWAP)
        deviations = typical_prices - vwap_arr
        std = np.std(deviations)

        upper_1 = vwap_now + std * self.band_mult
        lower_1 = vwap_now - std * self.band_mult
        upper_2 = vwap_now + std * self.band_mult_2
        lower_2 = vwap_now - std * self.band_mult_2

        return {
            "vwap": vwap_now,
            "upper_1": float(upper_1),
            "lower_1": float(lower_1),
            "upper_2": float(upper_2),
            "lower_2": float(lower_2),
            "std": float(std),
            "vwap_array": vwap_arr,
        }

    def analyze(self, bars: list) -> VWAPResult:
        """
        Analyze bars for VWAP signals.

        Signals:
          - BUY: price crosses above VWAP from below (bullish)
          - SELL: price crosses below VWAP from above (bearish)
          - BUY: price touches lower band and bounces (oversold)
          - SELL: price touches upper band and rejects (overbought)
        """
        if len(bars) < 20:
            return VWAPResult(None, 0, "Not enough bars", 0, 0, 0)

        highs = np.array([b.high for b in bars])
        lows = np.array([b.low for b in bars])
        closes = np.array([b.close for b in bars])
        volumes = np.array([b.volume if hasattr(b, 'volume') and b.volume else 1000.0 for b in bars])

        vwap_data = self.calculate_vwap(highs, lows, closes, volumes)
        vwap = vwap_data["vwap"]
        upper_1 = vwap_data["upper_1"]
        lower_1 = vwap_data["lower_1"]

        close_now = closes[-1]
        close_prev = closes[-2]

        signal = None
        confidence = 0
        reason = ""

        # VWAP cross
        if close_prev < vwap and close_now > vwap:
            signal = "buy"
            confidence = 70
            reason = f"Price crossed above VWAP ({vwap:.5f})"

        elif close_prev > vwap and close_now < vwap:
            signal = "sell"
            confidence = 70
            reason = f"Price crossed below VWAP ({vwap:.5f})"

        # Lower band bounce (oversold)
        elif close_now <= lower_1 and close_now > close_prev:
            signal = "buy"
            confidence = 65
            reason = f"Bounce off lower VWAP band ({lower_1:.5f})"

        # Upper band rejection (overbought)
        elif close_now >= upper_1 and close_now < close_prev:
            signal = "sell"
            confidence = 65
            reason = f"Rejection at upper VWAP band ({upper_1:.5f})"

        # Price above VWAP = bullish bias
        elif close_now > vwap:
            confidence = 45
            reason = f"Price above VWAP ({vwap:.5f}) — bullish bias"
            # Don't generate a strong buy signal, just bias

        # Price below VWAP = bearish bias
        elif close_now < vwap:
            confidence = 45
            reason = f"Price below VWAP ({vwap:.5f}) — bearish bias"

        return VWAPResult(
            signal=signal,
            confidence=confidence,
            reason=reason,
            vwap=float(vwap),
            upper_band=float(upper_1),
            lower_band=float(lower_1),
        )

    def format_for_signal(self, result: VWAPResult, symbol: str) -> str:
        """Format VWAP info for Telegram signal."""
        if result.vwap == 0:
            return ""

        if "XAU" in symbol.upper():
            return f"📊 VWAP: {result.vwap:.2f}"
        if "JPY" in symbol.upper():
            return f"📊 VWAP: {result.vwap:.3f}"
        return f"📊 VWAP: {result.vwap:.4f}"
