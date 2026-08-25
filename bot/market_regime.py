"""
market_regime.py — Market Regime Detection
=============================================
Detects current market regime to adapt strategy selection.

Regimes:
  - TRENDING_STRONG   — ADX > 30, clear EMA separation
  - TRENDING_NORMAL   — ADX 20-30, moderate trend
  - RANGING           — ADX < 20, sideways
  - VOLATILE          — High ATR, large bars
  - CHOPPY           — Erratic price action, avoid trading

Different strategies work better in different regimes.
"""

import numpy as np
from typing import Dict
from dataclasses import dataclass


@dataclass
class MarketRegime:
    """Current market regime analysis."""
    regime: str           # "trending_strong", "trending_normal", "ranging", "volatile", "choppy"
    confidence: float      # 0-100
    adx: float
    atr: float
    volatility_pct: float  # ATR as % of price
    trend_direction: str   # "up", "down", "flat"
    recommended_strategies: list
    description: str


class MarketRegimeDetector:
    """Detects market regime to optimize strategy selection."""

    # Strategy recommendations per regime
    REGIME_STRATEGIES = {
        "trending_strong": ["breakout", "momentum", "ema_crossover"],
        "trending_normal": ["ema_crossover", "sr_bounce", "breakout"],
        "ranging": ["bb_mean_reversion", "rsi_reversal", "sr_bounce"],
        "volatile": ["sr_bounce", "breakout"],
        "choppy": [],  # Don't trade in choppy markets
    }

    def __init__(self, adx_period: int = 14, atr_period: int = 14,
                 ema_fast: int = 50, ema_slow: int = 200):
        self.adx_period = adx_period
        self.atr_period = atr_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow

    def detect(self, bars: list) -> MarketRegime:
        """Analyze bars and determine market regime."""
        if len(bars) < 50:
            return MarketRegime("unknown", 0, 0, 0, 0, "flat", [], "Not enough data")

        highs = np.array([b.high for b in bars])
        lows = np.array([b.low for b in bars])
        closes = np.array([b.close for b in bars])

        # Calculate indicators
        try:
            from indicators import atr, ema, calc_adx
            atr_arr = atr(highs, lows, closes, self.atr_period)
            adx_arr = calc_adx(highs, lows, closes, self.adx_period)
            ema_f = ema(closes, self.ema_fast)
            ema_s = ema(closes, self.ema_slow)
        except Exception:
            # Fallback simple calculations
            atr_arr = self._simple_atr(highs, lows, self.atr_period)
            adx_arr = np.full(len(closes), 20.0)
            ema_f = self._simple_ema(closes, self.ema_fast)
            ema_s = self._simple_ema(closes, self.ema_slow)

        adx_now = float(adx_arr[-1]) if not np.isnan(adx_arr[-1]) else 20
        atr_now = float(atr_arr[-1]) if not np.isnan(atr_arr[-1]) else 0
        ema_f_now = float(ema_f[-1]) if not np.isnan(ema_f[-1]) else 0
        ema_s_now = float(ema_s[-1]) if not np.isnan(ema_s[-1]) else 0
        close_now = float(closes[-1])

        # Volatility as % of price
        vol_pct = (atr_now / close_now * 100) if close_now > 0 else 0

        # Trend direction
        if ema_f_now > ema_s_now and close_now > ema_f_now:
            trend_dir = "up"
        elif ema_f_now < ema_s_now and close_now < ema_f_now:
            trend_dir = "down"
        else:
            trend_dir = "flat"

        # Bar-to-bar volatility
        bar_ranges = (highs[-20:] - lows[-20:]) / closes[-20:]
        avg_bar_range = float(np.mean(bar_ranges))

        # Choppy detection: alternating large up/down bars
        closes_diff = np.diff(closes[-10:])
        direction_changes = np.sum(np.diff(np.sign(closes_diff)) != 0)
        is_choppy = direction_changes >= 6 and avg_bar_range > 0.005

        # Determine regime
        if is_choppy:
            regime = "choppy"
            confidence = 70
        elif adx_now >= 30:
            regime = "trending_strong"
            confidence = min(95, 50 + adx_now)
        elif adx_now >= 20:
            regime = "trending_normal"
            confidence = 65
        elif vol_pct > 1.5 or avg_bar_range > 0.008:
            regime = "volatile"
            confidence = 60
        else:
            regime = "ranging"
            confidence = 55

        recommended = self.REGIME_STRATEGIES.get(regime, [])

        descriptions = {
            "trending_strong": f"ترند قوي (ADX={adx_now:.0f}) — استراتيجياتBreakout/Momentum",
            "trending_normal": f"ترند عادي (ADX={adx_now:.0f}) — EMA/S/R",
            "ranging": f"سوق عرضي (ADX={adx_now:.0f}) — Mean Reversion/RSI",
            "volatile": f"تذبذب عالي (ATR={vol_pct:.2f}%) — حذر",
            "choppy": f"سوق متقطع — تجنب التداول",
            "unknown": "بيانات غير كافية",
        }

        return MarketRegime(
            regime=regime,
            confidence=confidence,
            adx=adx_now,
            atr=atr_now,
            volatility_pct=vol_pct,
            trend_direction=trend_dir,
            recommended_strategies=recommended,
            description=descriptions.get(regime, ""),
        )

    def _simple_atr(self, highs, lows, period):
        """Simple ATR fallback."""
        tr = np.zeros(len(highs))
        for i in range(1, len(highs)):
            tr[i] = max(highs[i] - lows[i],
                        abs(highs[i] - lows[i-1]),
                        abs(lows[i] - highs[i-1]))
        return np.convolve(tr, np.ones(period)/period, mode='same')

    def _simple_ema(self, data, period):
        """Simple EMA fallback."""
        ema = np.zeros(len(data))
        mult = 2 / (period + 1)
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = data[i] * mult + ema[i-1] * (1 - mult)
        return ema
