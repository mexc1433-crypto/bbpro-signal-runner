"""
candlestick.py — Japanese Candlestick Pattern Detector
======================================================
This module detects Japanese candlestick patterns for trading signal confirmation.
Supports single-bar, two-bar, and three-bar patterns, returning pattern metadata,
bullish/bearish direction, pattern strength score (0.0 to 1.0), and descriptions.

Functions:
    - detect_engulfing(bars)      : Bullish / Bearish Engulfing (2 bars)
    - detect_pin_bar(bars)        : Pin Bar / Hammer / Shooting Star (1 bar, wick >= 2x body)
    - detect_doji(bars)           : Doji / Dragonfly / Gravestone (1 bar, body <= 10% range)
    - detect_morning_star(bars)   : Morning / Evening Star (3 bars)
    - detect_three_soldiers(bars) : Three White Soldiers / Three Black Crows (3 bars)
    - detect_harami(bars)         : Bullish / Bearish Harami (2 bars, inside body)
    - detect_tweezer(bars)        : Tweezer Top / Bottom (2 bars, matching highs/lows)
    - detect_inside_bar(bars)     : Inside Bar breakout setup (2 bars, range inside previous)
    - detect_all_patterns(bars)   : Convenience function returning all detected patterns sorted by strength
"""

from typing import List, Optional, Dict, Any
import numpy as np

try:
    from ctrader_client import Bar
except ImportError:
    try:
        from bot.ctrader_client import Bar
    except ImportError:
        from dataclasses import dataclass

        @dataclass
        class Bar:
            open: float
            high: float
            low: float
            close: float
            volume: float
            timestamp: float


class _CandleProps:
    """Internal helper to extract price values and candlestick metrics from a Bar object or dict."""

    def __init__(self, bar: Any):
        if isinstance(bar, dict):
            self.open = float(bar.get("open", 0.0))
            self.high = float(bar.get("high", 0.0))
            self.low = float(bar.get("low", 0.0))
            self.close = float(bar.get("close", 0.0))
            self.volume = float(bar.get("volume", 0.0))
            self.timestamp = float(bar.get("timestamp", 0.0))
        else:
            self.open = float(getattr(bar, "open", 0.0))
            self.high = float(getattr(bar, "high", 0.0))
            self.low = float(getattr(bar, "low", 0.0))
            self.close = float(getattr(bar, "close", 0.0))
            self.volume = float(getattr(bar, "volume", 0.0))
            self.timestamp = float(getattr(bar, "timestamp", 0.0))

        self.body = abs(self.close - self.open)
        self.total_range = max(self.high - self.low, 1e-12)
        self.upper_wick = max(0.0, self.high - max(self.open, self.close))
        self.lower_wick = max(0.0, min(self.open, self.close) - self.low)
        self.is_bullish = self.close > self.open
        self.is_bearish = self.close < self.open
        self.is_flat = self.close == self.open


def detect_engulfing(bars: list) -> Optional[Dict[str, Any]]:
    """
    Detects Bullish or Bearish Engulfing pattern from the last 2 bars.

    Parameters:
        bars (list): List of Bar objects or dicts ordered by time ascending.

    Returns:
        Optional[dict]: Pattern dict with keys 'pattern', 'bullish', 'strength', 'description'
                        or None if no engulfing pattern is detected.
    """
    if not bars or len(bars) < 2:
        return None

    prev = _CandleProps(bars[-2])
    curr = _CandleProps(bars[-1])

    # Bullish Engulfing: prev is bearish/flat, curr is bullish, curr body engulfs prev body
    if prev.close <= prev.open and curr.close > curr.open:
        if curr.open <= prev.close and curr.close >= prev.open and curr.body > prev.body:
            ratio = curr.body / max(prev.body, 1e-8)
            strength = float(np.clip(0.70 + 0.10 * min(ratio - 1.0, 2.5), 0.60, 0.95))
            return {
                "pattern": "Bullish Engulfing",
                "bullish": True,
                "strength": round(strength, 2),
                "description": (
                    f"Bullish Engulfing: current bullish body ({curr.body:.5f}) "
                    f"engulfs previous bearish body ({prev.body:.5f})."
                ),
            }

    # Bearish Engulfing: prev is bullish/flat, curr is bearish, curr body engulfs prev body
    if prev.close >= prev.open and curr.close < curr.open:
        if curr.open >= prev.close and curr.close <= prev.open and curr.body > prev.body:
            ratio = curr.body / max(prev.body, 1e-8)
            strength = float(np.clip(0.70 + 0.10 * min(ratio - 1.0, 2.5), 0.60, 0.95))
            return {
                "pattern": "Bearish Engulfing",
                "bullish": False,
                "strength": round(strength, 2),
                "description": (
                    f"Bearish Engulfing: current bearish body ({curr.body:.5f}) "
                    f"engulfs previous bullish body ({prev.body:.5f})."
                ),
            }

    return None


def detect_pin_bar(bars: list) -> Optional[Dict[str, Any]]:
    """
    Detects Pin Bar (Hammer or Shooting Star) from the latest bar.
    Condition: long wick >= 2x body size.

    Parameters:
        bars (list): List of Bar objects or dicts ordered by time ascending.

    Returns:
        Optional[dict]: Pattern dict or None if no pin bar pattern is detected.
    """
    if not bars:
        return None

    curr = _CandleProps(bars[-1])
    min_wick_ratio = 2.0

    # Bullish Pin Bar / Hammer (long lower wick)
    if curr.lower_wick >= min_wick_ratio * max(curr.body, 1e-8) and curr.lower_wick > curr.upper_wick:
        if curr.upper_wick <= 0.35 * curr.total_range:
            wick_to_range = curr.lower_wick / curr.total_range
            strength = float(np.clip(0.60 + 0.35 * wick_to_range, 0.60, 0.95))
            return {
                "pattern": "Hammer",
                "bullish": True,
                "strength": round(strength, 2),
                "description": (
                    f"Bullish Pin Bar (Hammer): long lower wick ({curr.lower_wick:.5f}) "
                    f"is {curr.lower_wick / max(curr.body, 1e-8):.1f}x body size."
                ),
            }

    # Bearish Pin Bar / Shooting Star (long upper wick)
    if curr.upper_wick >= min_wick_ratio * max(curr.body, 1e-8) and curr.upper_wick > curr.lower_wick:
        if curr.lower_wick <= 0.35 * curr.total_range:
            wick_to_range = curr.upper_wick / curr.total_range
            strength = float(np.clip(0.60 + 0.35 * wick_to_range, 0.60, 0.95))
            return {
                "pattern": "Shooting Star",
                "bullish": False,
                "strength": round(strength, 2),
                "description": (
                    f"Bearish Pin Bar (Shooting Star): long upper wick ({curr.upper_wick:.5f}) "
                    f"is {curr.upper_wick / max(curr.body, 1e-8):.1f}x body size."
                ),
            }

    return None


def detect_doji(bars: list) -> Optional[Dict[str, Any]]:
    """
    Detects Doji pattern from the latest bar (body <= 10% of total range).
    Categorizes into Dragonfly Doji, Gravestone Doji, or Standard Doji.

    Parameters:
        bars (list): List of Bar objects or dicts ordered by time ascending.

    Returns:
        Optional[dict]: Pattern dict or None if body > 10% of total range.
    """
    if not bars:
        return None

    curr = _CandleProps(bars[-1])
    body_ratio = curr.body / curr.total_range

    if body_ratio <= 0.10:
        if curr.lower_wick >= 0.60 * curr.total_range and curr.upper_wick <= 0.15 * curr.total_range:
            pattern_name = "Dragonfly Doji"
            bullish = True
        elif curr.upper_wick >= 0.60 * curr.total_range and curr.lower_wick <= 0.15 * curr.total_range:
            pattern_name = "Gravestone Doji"
            bullish = False
        else:
            pattern_name = "Doji"
            bullish = curr.close >= curr.open

        strength = float(np.clip(0.60 + 0.35 * (1.0 - body_ratio / 0.10), 0.60, 0.95))
        return {
            "pattern": pattern_name,
            "bullish": bullish,
            "strength": round(strength, 2),
            "description": (
                f"{pattern_name}: body ({curr.body:.5f}) is {body_ratio * 100:.1f}% "
                f"of total range, indicating market indecision."
            ),
        }

    return None


def detect_morning_star(bars: list) -> Optional[Dict[str, Any]]:
    """
    Detects Morning Star (Bullish Reversal) or Evening Star (Bearish Reversal) from the last 3 bars.

    Parameters:
        bars (list): List of Bar objects or dicts ordered by time ascending.

    Returns:
        Optional[dict]: Pattern dict or None if no Morning/Evening star pattern is detected.
    """
    if not bars or len(bars) < 3:
        return None

    b1 = _CandleProps(bars[-3])
    b2 = _CandleProps(bars[-2])
    b3 = _CandleProps(bars[-1])

    # Morning Star (Bullish Reversal)
    if b1.is_bearish and b1.body >= 0.3 * b1.total_range:
        if b2.body <= 0.4 * b1.body:
            if b3.is_bullish and b3.close >= b1.close + 0.5 * b1.body:
                penetration = (b3.close - b1.close) / max(b1.body, 1e-8)
                strength = float(np.clip(0.70 + 0.20 * min(penetration, 1.0), 0.70, 0.95))
                return {
                    "pattern": "Morning Star",
                    "bullish": True,
                    "strength": round(strength, 2),
                    "description": "Morning Star: 3-bar bullish reversal sequence with star consolidation and deep body penetration.",
                }

    # Evening Star (Bearish Reversal)
    if b1.is_bullish and b1.body >= 0.3 * b1.total_range:
        if b2.body <= 0.4 * b1.body:
            if b3.is_bearish and b3.close <= b1.close - 0.5 * b1.body:
                penetration = (b1.close - b3.close) / max(b1.body, 1e-8)
                strength = float(np.clip(0.70 + 0.20 * min(penetration, 1.0), 0.70, 0.95))
                return {
                    "pattern": "Evening Star",
                    "bullish": False,
                    "strength": round(strength, 2),
                    "description": "Evening Star: 3-bar bearish reversal sequence with star consolidation and deep body penetration.",
                }

    return None


def detect_three_soldiers(bars: list) -> Optional[Dict[str, Any]]:
    """
    Detects Three White Soldiers (Bullish) or Three Black Crows (Bearish) from the last 3 bars.

    Parameters:
        bars (list): List of Bar objects or dicts ordered by time ascending.

    Returns:
        Optional[dict]: Pattern dict or None if no Three Soldiers / Crows pattern detected.
    """
    if not bars or len(bars) < 3:
        return None

    b1 = _CandleProps(bars[-3])
    b2 = _CandleProps(bars[-2])
    b3 = _CandleProps(bars[-1])

    # Three White Soldiers (Bullish)
    if b1.is_bullish and b2.is_bullish and b3.is_bullish:
        if b1.close < b2.close < b3.close and b1.open < b2.open < b3.open:
            if b2.open >= b1.open and b3.open >= b2.open:
                if b3.upper_wick <= 0.45 * b3.body:
                    return {
                        "pattern": "Three White Soldiers",
                        "bullish": True,
                        "strength": 0.85,
                        "description": "Three White Soldiers: 3 consecutive strong bullish bars with progressive higher closes.",
                    }

    # Three Black Crows (Bearish)
    if b1.is_bearish and b2.is_bearish and b3.is_bearish:
        if b1.close > b2.close > b3.close and b1.open > b2.open > b3.open:
            if b2.open <= b1.open and b3.open <= b2.open:
                if b3.lower_wick <= 0.45 * b3.body:
                    return {
                        "pattern": "Three Black Crows",
                        "bullish": False,
                        "strength": 0.85,
                        "description": "Three Black Crows: 3 consecutive strong bearish bars with progressive lower closes.",
                    }

    return None


def detect_harami(bars: list) -> Optional[Dict[str, Any]]:
    """
    Detects Bullish or Bearish Harami pattern from the last 2 bars (inside body pattern).

    Parameters:
        bars (list): List of Bar objects or dicts ordered by time ascending.

    Returns:
        Optional[dict]: Pattern dict or None if no Harami pattern is detected.
    """
    if not bars or len(bars) < 2:
        return None

    prev = _CandleProps(bars[-2])
    curr = _CandleProps(bars[-1])

    # Bullish Harami: prev is long bearish, curr is small body inside prev body
    if prev.is_bearish and prev.body >= 0.3 * prev.total_range:
        curr_min_body = min(curr.open, curr.close)
        curr_max_body = max(curr.open, curr.close)
        if curr_min_body >= prev.close and curr_max_body <= prev.open and curr.body < prev.body * 0.7:
            ratio = 1.0 - (curr.body / max(prev.body, 1e-8))
            strength = float(np.clip(0.65 + 0.20 * ratio, 0.60, 0.90))
            return {
                "pattern": "Bullish Harami",
                "bullish": True,
                "strength": round(strength, 2),
                "description": "Bullish Harami: small body contained inside previous long bearish body.",
            }

    # Bearish Harami: prev is long bullish, curr is small body inside prev body
    if prev.is_bullish and prev.body >= 0.3 * prev.total_range:
        curr_min_body = min(curr.open, curr.close)
        curr_max_body = max(curr.open, curr.close)
        if curr_min_body >= prev.open and curr_max_body <= prev.close and curr.body < prev.body * 0.7:
            ratio = 1.0 - (curr.body / max(prev.body, 1e-8))
            strength = float(np.clip(0.65 + 0.20 * ratio, 0.60, 0.90))
            return {
                "pattern": "Bearish Harami",
                "bullish": False,
                "strength": round(strength, 2),
                "description": "Bearish Harami: small body contained inside previous long bullish body.",
            }

    return None


def detect_tweezer(bars: list) -> Optional[Dict[str, Any]]:
    """
    Detects Tweezer Top (Bearish) or Tweezer Bottom (Bullish) from the last 2 bars.

    Parameters:
        bars (list): List of Bar objects or dicts ordered by time ascending.

    Returns:
        Optional[dict]: Pattern dict or None if no Tweezer pattern detected.
    """
    if not bars or len(bars) < 2:
        return None

    prev = _CandleProps(bars[-2])
    curr = _CandleProps(bars[-1])
    avg_range = (prev.total_range + curr.total_range) / 2.0
    tol = 0.05 * avg_range

    # Tweezer Top (Bearish reversal at resistance): matching highs
    if abs(prev.high - curr.high) <= tol:
        if prev.is_bullish and curr.is_bearish:
            diff_ratio = abs(prev.high - curr.high) / max(avg_range, 1e-8)
            strength = float(np.clip(0.85 - diff_ratio * 3.0, 0.65, 0.90))
            return {
                "pattern": "Tweezer Top",
                "bullish": False,
                "strength": round(strength, 2),
                "description": f"Tweezer Top: matching highs at {curr.high:.5f} signaling strong resistance.",
            }

    # Tweezer Bottom (Bullish reversal at support): matching lows
    if abs(prev.low - curr.low) <= tol:
        if prev.is_bearish and curr.is_bullish:
            diff_ratio = abs(prev.low - curr.low) / max(avg_range, 1e-8)
            strength = float(np.clip(0.85 - diff_ratio * 3.0, 0.65, 0.90))
            return {
                "pattern": "Tweezer Bottom",
                "bullish": True,
                "strength": round(strength, 2),
                "description": f"Tweezer Bottom: matching lows at {curr.low:.5f} signaling strong support.",
            }

    return None


def detect_inside_bar(bars: list) -> Optional[Dict[str, Any]]:
    """
    Detects Inside Bar breakout setup from the last 2 bars.
    Condition: current high <= prev high and current low >= prev low.

    Parameters:
        bars (list): List of Bar objects or dicts ordered by time ascending.

    Returns:
        Optional[dict]: Pattern dict or None if current bar is not inside previous bar.
    """
    if not bars or len(bars) < 2:
        return None

    prev = _CandleProps(bars[-2])
    curr = _CandleProps(bars[-1])

    if curr.high <= prev.high and curr.low >= prev.low:
        bullish = curr.close >= curr.open
        range_ratio = curr.total_range / max(prev.total_range, 1e-8)
        strength = float(np.clip(0.70 + 0.15 * (1.0 - range_ratio), 0.60, 0.85))
        return {
            "pattern": "Inside Bar",
            "bullish": bullish,
            "strength": round(strength, 2),
            "description": (
                f"Inside Bar: range [{curr.low:.5f}, {curr.high:.5f}] "
                f"is completely inside previous bar range [{prev.low:.5f}, {prev.high:.5f}]."
            ),
        }

    return None


def detect_all_patterns(bars: list) -> list:
    """
    Runs all 8 pattern detectors on the provided list of bars.

    Parameters:
        bars (list): List of Bar objects or dicts ordered by time ascending.

    Returns:
        list: List of all detected pattern dicts sorted by strength in descending order.
    """
    if not bars:
        return []

    detectors = [
        detect_engulfing,
        detect_pin_bar,
        detect_doji,
        detect_morning_star,
        detect_three_soldiers,
        detect_harami,
        detect_tweezer,
        detect_inside_bar,
    ]

    detected = []
    for detector in detectors:
        res = detector(bars)
        if res is not None:
            detected.append(res)

    return sorted(detected, key=lambda x: x["strength"], reverse=True)
