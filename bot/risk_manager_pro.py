"""
risk_manager_pro.py — Advanced Risk Management
================================================
Professional risk management with:
  - Kelly Criterion position sizing
  - R:R-based confidence scoring
  - Multi-level take profit (TP1, TP2, TP3)
  - Break-even logic
  - Signal quality score (0-100)
  - Volatility-adjusted SL/TP
  - Maximum drawdown protection

This is for SIGNAL MODE — it calculates and suggests, doesn't execute.
"""

import numpy as np
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class MultiTP:
    """Multi-level take profit targets."""
    tp1_price: float
    tp2_price: float
    tp3_price: float
    tp1_pips: float
    tp2_pips: float
    tp3_pips: float
    tp1_ratio: float = 0.3   # 30% of position at TP1
    tp2_ratio: float = 0.3   # 30% at TP2
    tp3_ratio: float = 0.4   # 40% at TP3


@dataclass
class SignalQuality:
    """Quality assessment of a trading signal."""
    score: float          # 0-100
    grade: str            # A+, A, B, C, D
    factors: Dict         # breakdown of scoring
    recommendation: str   # "TAKE", "WATCH", "SKIP"


class RiskManagerPro:
    """Advanced risk manager for signal scoring and position sizing."""

    def __init__(self, win_rate: float = 0.55, avg_win_pips: float = 40,
                 avg_loss_pips: float = 25, max_risk_per_trade: float = 0.02):
        self.win_rate = win_rate
        self.avg_win_pips = avg_win_pips
        self.avg_loss_pips = avg_loss_pips
        self.max_risk_per_trade = max_risk_per_trade

    # ------------------------------------------------------------------
    # KELLY CRITERION
    # ------------------------------------------------------------------
    def kelly_fraction(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        Kelly Criterion: f* = (p*b - q) / b
        where p = win rate, q = 1-p, b = win/loss ratio

        Returns recommended fraction of capital (0-1).
        Uses half-Kelly for safety.
        """
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0

        b = avg_win / avg_loss  # win/loss ratio
        p = win_rate
        q = 1 - p

        kelly = (p * b - q) / b
        kelly = max(0, kelly)

        # Half-Kelly for safety
        half_kelly = kelly * 0.5

        # Cap at max risk
        return min(half_kelly, self.max_risk_per_trade)

    # ------------------------------------------------------------------
    # MULTI-LEVEL TAKE PROFIT
    # ------------------------------------------------------------------
    def calculate_multi_tp(self, entry: float, sl_price: float,
                            side: str, pip_size: float,
                            atr_value: float = 0) -> MultiTP:
        """
        Calculate 3 TP levels:
          TP1 = 1R (1x SL distance) — 30% of position
          TP2 = 2R — 30%
          TP3 = 3R — 40%
        """
        sl_dist = abs(entry - sl_price)

        if side.lower() == "buy":
            tp1 = entry + sl_dist * 1.0
            tp2 = entry + sl_dist * 2.0
            tp3 = entry + sl_dist * 3.0
        else:
            tp1 = entry - sl_dist * 1.0
            tp2 = entry - sl_dist * 2.0
            tp3 = entry - sl_dist * 3.0

        tp1_pips = sl_dist / pip_size
        tp2_pips = sl_dist * 2 / pip_size
        tp3_pips = sl_dist * 3 / pip_size

        return MultiTP(
            tp1_price=tp1, tp2_price=tp2, tp3_price=tp3,
            tp1_pips=tp1_pips, tp2_pips=tp2_pips, tp3_pips=tp3_pips,
        )

    # ------------------------------------------------------------------
    # BREAK-EVEN CALCULATION
    # ------------------------------------------------------------------
    def calculate_break_even(self, entry: float, sl_price: float, side: str,
                              pip_size: float, trigger_pips: float = 15) -> Dict:
        """
        When price moves +trigger_pips in favor, move SL to break-even.
        """
        if side.lower() == "buy":
            trigger_price = entry + trigger_pips * pip_size
            new_sl = entry  # break-even
        else:
            trigger_price = entry - trigger_pips * pip_size
            new_sl = entry

        return {
            "trigger_price": trigger_price,
            "new_sl_price": new_sl,
            "trigger_pips": trigger_pips,
            "description": f"Move SL to BE when price reaches {trigger_price:.5f}",
        }

    # ------------------------------------------------------------------
    # SIGNAL QUALITY SCORE
    # ------------------------------------------------------------------
    def score_signal(self, indicators: Dict, mtf_confluence: float = 0,
                      ai_confidence: float = 0, pattern_count: int = 0,
                      rr_ratio: float = 0, adx: float = 0) -> SignalQuality:
        """
        Score a signal from 0-100 based on multiple factors.

        Factors:
          - Trend strength (ADX)       — 20 points
          - MTF confluence             — 20 points
          - R:R ratio                  — 15 points
          - Candlestick patterns       — 15 points
          - AI confidence              — 15 points
          - RSI alignment              — 10 points
          - EMA alignment              — 5 points
        """
        factors = {}
        total = 0

        # ADX (20 points)
        adx_score = min(20, adx / 50 * 20)
        factors["adx"] = adx_score
        total += adx_score

        # MTF confluence (20 points)
        mtf_score = mtf_confluence / 100 * 20
        factors["mtf_confluence"] = mtf_score
        total += mtf_score

        # R:R ratio (15 points) — 1.5 = full score, 1.0 = half, <1.0 = 0
        if rr_ratio >= 2.0:
            rr_score = 15
        elif rr_ratio >= 1.5:
            rr_score = 12
        elif rr_ratio >= 1.0:
            rr_score = 8
        else:
            rr_score = 0
        factors["rr_ratio"] = rr_score
        total += rr_score

        # Candlestick patterns (15 points) — max 2 patterns
        pattern_score = min(15, pattern_count * 7.5)
        factors["patterns"] = pattern_score
        total += pattern_score

        # AI confidence (15 points)
        ai_score = ai_confidence / 100 * 15
        factors["ai_confidence"] = ai_score
        total += ai_score

        # RSI alignment (10 points)
        rsi = indicators.get("rsi", 50)
        side = indicators.get("side", "buy")
        if side == "buy" and rsi < 70:
            rsi_score = 10 - abs(rsi - 50) * 0.2
        elif side == "sell" and rsi > 30:
            rsi_score = 10 - abs(rsi - 50) * 0.2
        else:
            rsi_score = 0
        rsi_score = max(0, rsi_score)
        factors["rsi"] = rsi_score
        total += rsi_score

        # EMA alignment (5 points)
        ema_f = indicators.get("ema_fast", 0)
        ema_s = indicators.get("ema_slow", 0)
        close = indicators.get("close", 0)
        if side == "buy" and ema_f > ema_s and close > ema_f:
            ema_score = 5
        elif side == "sell" and ema_f < ema_s and close < ema_f:
            ema_score = 5
        else:
            ema_score = 0
        factors["ema_alignment"] = ema_score
        total += ema_score

        total = min(100, total)

        # Grade
        if total >= 85:
            grade = "A+"
        elif total >= 75:
            grade = "A"
        elif total >= 65:
            grade = "B"
        elif total >= 50:
            grade = "C"
        else:
            grade = "D"

        # Recommendation
        if total >= 75:
            recommendation = "TAKE ✅"
        elif total >= 55:
            recommendation = "WATCH ⚠️"
        else:
            recommendation = "SKIP ❌"

        return SignalQuality(
            score=total, grade=grade, factors=factors,
            recommendation=recommendation,
        )

    # ------------------------------------------------------------------
    # VOLATILITY-ADJUSTED SL/TP
    # ------------------------------------------------------------------
    def volatility_adjusted_sl_tp(self, entry: float, atr: float,
                                     side: str, pip_size: float,
                                     atr_mult_sl: float = 1.5,
                                     atr_mult_tp: float = 2.5) -> Dict:
        """
        SL and TP adjusted by ATR (Average True Range).
        Higher volatility = wider stops.
        """
        sl_dist = atr * atr_mult_sl
        tp_dist = atr * atr_mult_tp

        if side.lower() == "buy":
            sl_price = entry - sl_dist
            tp_price = entry + tp_dist
        else:
            sl_price = entry + sl_dist
            tp_price = entry - tp_dist

        return {
            "sl_price": sl_price,
            "tp_price": tp_price,
            "sl_pips": sl_dist / pip_size,
            "tp_pips": tp_dist / pip_size,
            "rr_ratio": tp_dist / sl_dist if sl_dist > 0 else 0,
            "atr": atr,
        }

    # ------------------------------------------------------------------
    # MAX DRAWDOWN PROTECTION
    # ------------------------------------------------------------------
    def check_drawdown(self, equity: float, peak_equity: float,
                        max_dd_pct: float = 10.0) -> Dict:
        """
        Check if current drawdown exceeds safe limits.
        """
        if peak_equity <= 0:
            return {"in_drawdown": False, "dd_pct": 0, "action": "none"}

        dd_pct = (peak_equity - equity) / peak_equity * 100

        if dd_pct >= max_dd_pct:
            return {
                "in_drawdown": True,
                "dd_pct": dd_pct,
                "action": "STOP",
                "description": f"Max drawdown reached ({dd_pct:.1f}%) — stop trading",
            }
        elif dd_pct >= max_dd_pct * 0.7:
            return {
                "in_drawdown": True,
                "dd_pct": dd_pct,
                "action": "REDUCE",
                "description": f"Approaching max drawdown ({dd_pct:.1f}%) — reduce risk",
            }
        return {
            "in_drawdown": False,
            "dd_pct": dd_pct,
            "action": "none",
        }

    # ------------------------------------------------------------------
    # FORMAT MULTI-TP FOR TELEGRAM
    # ------------------------------------------------------------------
    def format_multi_tp(self, mtp: MultiTP, symbol: str) -> str:
        """Format multi-level TP for Telegram signal."""
        fmt = ".2f" if "XAU" in symbol.upper() else ".4f" if "JPY" not in symbol.upper() else ".3f"
        return (
            f"TP1: {mtp.tp1_price:{fmt}} (30%)\n"
            f"TP2: {mtp.tp2_price:{fmt}} (30%)\n"
            f"TP3: {mtp.tp3_price:{fmt}} (40%)"
        )
