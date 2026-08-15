"""
strategies.py
=============
Trading Strategy Suite & Strategy Manager for BBPro Signal Bot.

Implements multiple technical trading strategies for Forex, Gold, and Crypto markets:
1. RSIReversalStrategy      — Overbought/Oversold RSI reversal with candle confirmation
2. EMACrossoverStrategy     — EMA 50/200 Golden Cross / Death Cross & Near-Cross warnings
3. SupportResistanceStrategy — Bounce off swing S/R levels with rejection candle confirmation
4. BBMeanReversionStrategy  — Reversion to Bollinger Band middle from outer band touch
5. BreakoutStrategy         — Bollinger Band breakout with volume & ADX confirmation
6. MACDCrossoverStrategy    — MACD signal line crossover with momentum & zero-line context
7. StochasticReversalStrategy — Stochastic %K/%D crossover in overbought/oversold zones
8. TrendADXStrategy         — Strong trend continuation scalping/swing with ADX & EMA pullback

StrategyManager:
- Manages and runs all enabled strategies
- Calculates highest-confidence signal
- Determines multi-strategy consensus
"""

import logging
import numpy as np
from typing import Dict, Any, List, Optional, Tuple, Union

try:
    from config import TradeDirection, BotConfig
except ImportError:
    from .config import TradeDirection, BotConfig

try:
    from ctrader_client import Bar
except ImportError:
    try:
        from .ctrader_client import Bar
    except ImportError:
        Bar = Any

try:
    import indicators
except ImportError:
    from . import indicators



try:
    from volume_profile import VolumeProfileStrategy
except ImportError:
    try:
        from .volume_profile import VolumeProfileStrategy
    except ImportError:
        VolumeProfileStrategy = None

try:
    from ict_killzones import ICTKillzoneStrategy
except ImportError:
    try:
        from .ict_killzones import ICTKillzoneStrategy
    except ImportError:
        ICTKillzoneStrategy = None


try:
    from fvg_strategy import FVGStrategy
    HAS_FVG = True
except ImportError:
    HAS_FVG = False

try:
    from ict_killzones import ICTKillzoneStrategy
    HAS_ICT = True
except ImportError:
    HAS_ICT = False

try:
    from volume_profile import VolumeProfileStrategy
    HAS_VP = True
except ImportError:
    HAS_VP = False


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  DATA EXTRACTION HELPER
# ---------------------------------------------------------------------------
def _extract_ohlcv(bars: Union[List[Any], np.ndarray]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Safely extracts open, high, low, close, volume arrays from various input structures.
    Supports List[Bar], List[dict], or NumPy 2D array.
    """
    if isinstance(bars, np.ndarray):
        if bars.ndim == 2 and bars.shape[1] >= 5:
            return bars[:, 0], bars[:, 1], bars[:, 2], bars[:, 3], bars[:, 4]
        closes = bars.astype(float)
        return closes, closes, closes, closes, np.ones_like(closes)

    if not bars:
        empty = np.array([], dtype=float)
        return empty, empty, empty, empty, empty

    first = bars[0]
    if hasattr(first, "open"):
        opens = np.array([getattr(b, "open", 0.0) for b in bars], dtype=float)
        highs = np.array([getattr(b, "high", 0.0) for b in bars], dtype=float)
        lows = np.array([getattr(b, "low", 0.0) for b in bars], dtype=float)
        closes = np.array([getattr(b, "close", 0.0) for b in bars], dtype=float)
        volumes = np.array([getattr(b, "volume", 0.0) for b in bars], dtype=float)
    elif isinstance(first, dict):
        opens = np.array([b.get("open", 0.0) for b in bars], dtype=float)
        highs = np.array([b.get("high", 0.0) for b in bars], dtype=float)
        lows = np.array([b.get("low", 0.0) for b in bars], dtype=float)
        closes = np.array([b.get("close", 0.0) for b in bars], dtype=float)
        volumes = np.array([b.get("volume", 0.0) for b in bars], dtype=float)
    else:
        closes = np.array([float(b) for b in bars], dtype=float)
        opens, highs, lows, volumes = closes, closes, closes, np.ones_like(closes)

    return opens, highs, lows, closes, volumes


def _default_result(strategy_name: str, reason: str = "No signal") -> Dict[str, Any]:
    """Returns standard empty/neutral signal dictionary."""
    return {
        "signal": None,
        "confidence": 0.0,
        "reason": reason,
        "strategy": strategy_name,
    }


# ===========================================================================
#  STRATEGY 1: RSI REVERSAL
# ===========================================================================
class RSIReversalStrategy:
    """
    RSI Overbought/Oversold Reversal Strategy with Candle Confirmation.

    BUY Setup:
      - RSI was in oversold territory (< rsi_oversold, e.g. 30) within last 3 bars
      - RSI turns upward (RSI[-1] > RSI[-2])
      - Latest bar is bullish (Close > Open)

    SELL Setup:
      - RSI was in overbought territory (> rsi_overbought, e.g. 70) within last 3 bars
      - RSI turns downward (RSI[-1] < RSI[-2])
      - Latest bar is bearish (Close < Open)
    """

    def __init__(self, name: str = "rsi_reversal"):
        self.name = name

    def analyze(self, bars: Any, cfg: Optional[BotConfig] = None,
                indicators_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            cfg = cfg or BotConfig()
            opens, highs, lows, closes, volumes = _extract_ohlcv(bars)
            period = getattr(cfg, "rsi_period", 14)
            oversold = getattr(cfg, "rsi_oversold", 30.0)
            overbought = getattr(cfg, "rsi_overbought", 70.0)

            if len(closes) < period + 3:
                return _default_result(self.name, "Insufficient data for RSI calculation")

            if indicators_dict and "rsi" in indicators_dict:
                rsi_arr = indicators_dict["rsi"]
            else:
                rsi_arr = indicators.rsi(closes, period=period)

            if len(rsi_arr) < 3 or np.isnan(rsi_arr[-1]) or np.isnan(rsi_arr[-2]):
                return _default_result(self.name, "RSI values unavailable")

            latest_rsi = rsi_arr[-1]
            prev_rsi = rsi_arr[-2]
            min_recent_rsi = np.nanmin(rsi_arr[-3:])
            max_recent_rsi = np.nanmax(rsi_arr[-3:])

            is_bullish_candle = closes[-1] > opens[-1]
            is_bearish_candle = closes[-1] < opens[-1]

            # BUY Reversal
            if min_recent_rsi < oversold and latest_rsi > prev_rsi and is_bullish_candle:
                extremity = oversold - min_recent_rsi
                confidence = round(min(98.0, max(50.0, 60.0 + extremity * 1.5)), 2)
                reason = (
                    f"RSI oversold reversal: min RSI {min_recent_rsi:.1f} (< {oversold:.1f}) "
                    f"turned up to {latest_rsi:.1f} with bullish candle"
                )
                return {
                    "signal": TradeDirection.BUY,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            # SELL Reversal
            if max_recent_rsi > overbought and latest_rsi < prev_rsi and is_bearish_candle:
                extremity = max_recent_rsi - overbought
                confidence = round(min(98.0, max(50.0, 60.0 + extremity * 1.5)), 2)
                reason = (
                    f"RSI overbought reversal: max RSI {max_recent_rsi:.1f} (> {overbought:.1f}) "
                    f"turned down to {latest_rsi:.1f} with bearish candle"
                )
                return {
                    "signal": TradeDirection.SELL,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            return _default_result(self.name, f"RSI level {latest_rsi:.1f} in neutral zone")

        except Exception as e:
            logger.warning("RSIReversalStrategy error: %s", e)
            return _default_result(self.name, f"Error: {e}")

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        return self.analyze(bars, cfg)


# ===========================================================================
#  STRATEGY 2: EMA CROSSOVER
# ===========================================================================
class EMACrossoverStrategy:
    """
    Exponential Moving Average Crossover Strategy (EMA 50 / EMA 200).

    Golden Cross (BUY):
      - Fast EMA crosses above Slow EMA

    Death Cross (SELL):
      - Fast EMA crosses below Slow EMA

    Near-Cross / Early Warning:
      - Fast and Slow EMAs are converging within 0.15% threshold
    """

    def __init__(self, name: str = "ema_crossover"):
        self.name = name

    def analyze(self, bars: Any, cfg: Optional[BotConfig] = None,
                indicators_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            cfg = cfg or BotConfig()
            opens, highs, lows, closes, volumes = _extract_ohlcv(bars)
            fast_p = getattr(cfg, "fast_ema_period", 50)
            slow_p = getattr(cfg, "slow_ema_period", 200)

            if len(closes) < min(slow_p, max(fast_p, 50)):
                # Fallback to shorter period if historical data is limited
                slow_p = min(slow_p, len(closes) - 1)
                fast_p = min(fast_p, max(5, slow_p // 4))

            if len(closes) < fast_p + 2:
                return _default_result(self.name, "Insufficient bars for EMA crossover")

            if indicators_dict and "ema_fast" in indicators_dict and "ema_slow" in indicators_dict:
                ema_fast = indicators_dict["ema_fast"]
                ema_slow = indicators_dict["ema_slow"]
            else:
                ema_fast = indicators.ema(closes, fast_p)
                ema_slow = indicators.ema(closes, slow_p)

            if (np.isnan(ema_fast[-1]) or np.isnan(ema_slow[-1]) or
                np.isnan(ema_fast[-2]) or np.isnan(ema_slow[-2])):
                return _default_result(self.name, "EMA indicator NaN values")

            f_curr, s_curr = float(ema_fast[-1]), float(ema_slow[-1])
            f_prev, s_prev = float(ema_fast[-2]), float(ema_slow[-2])
            price = float(closes[-1])

            # Golden Cross (BUY)
            if f_prev <= s_prev and f_curr > s_curr:
                confidence = 85.0
                if price > f_curr:
                    confidence = 90.0
                reason = f"Golden Cross: EMA{fast_p} ({f_curr:.5f}) crossed above EMA{slow_p} ({s_curr:.5f})"
                return {
                    "signal": TradeDirection.BUY,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            # Death Cross (SELL)
            if f_prev >= s_prev and f_curr < s_curr:
                confidence = 85.0
                if price < f_curr:
                    confidence = 90.0
                reason = f"Death Cross: EMA{fast_p} ({f_curr:.5f}) crossed below EMA{slow_p} ({s_curr:.5f})"
                return {
                    "signal": TradeDirection.SELL,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            # Near-Cross Early Warning Detection
            if price > 0:
                diff_curr = abs(f_curr - s_curr) / price
                diff_prev = abs(f_prev - s_prev) / price

                # Converging within 0.15% of price
                if diff_curr < 0.0015 and diff_curr < diff_prev:
                    if f_curr < s_curr:
                        reason = (
                            f"Near Golden Cross warning: EMA{fast_p} approaching EMA{slow_p} "
                            f"(gap {diff_curr * 100:.3f}%)"
                        )
                        return {
                            "signal": TradeDirection.BUY,
                            "confidence": 55.0,
                            "reason": reason,
                            "strategy": self.name,
                        }
                    else:
                        reason = (
                            f"Near Death Cross warning: EMA{fast_p} approaching EMA{slow_p} "
                            f"(gap {diff_curr * 100:.3f}%)"
                        )
                        return {
                            "signal": TradeDirection.SELL,
                            "confidence": 55.0,
                            "reason": reason,
                            "strategy": self.name,
                        }

            return _default_result(
                self.name,
                f"EMA{fast_p} ({f_curr:.5f}) and EMA{slow_p} ({s_curr:.5f}) aligned without cross"
            )

        except Exception as e:
            logger.warning("EMACrossoverStrategy error: %s", e)
            return _default_result(self.name, f"Error: {e}")

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        return self.analyze(bars, cfg)


# ===========================================================================
#  STRATEGY 3: SUPPORT & RESISTANCE BOUNCE
# ===========================================================================
class SupportResistanceStrategy:
    """
    Support & Resistance Bounce Strategy.

    Detects key swing highs and lows as S/R levels over a lookback window.
    BUY: Price bounces off support with bullish rejection (pinbar or bullish close)
    SELL: Price bounces off resistance with bearish rejection (pinbar or bearish close)
    """

    def __init__(self, name: str = "support_resistance", lookback: int = 80, tolerance: float = 0.002):
        self.name = name
        self.lookback = lookback
        self.tolerance = tolerance

    def analyze(self, bars: Any, cfg: Optional[BotConfig] = None,
                indicators_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            cfg = cfg or BotConfig()
            opens, highs, lows, closes, volumes = _extract_ohlcv(bars)

            if len(closes) < 20:
                return _default_result(self.name, "Insufficient data for S/R detection")

            lookback = min(self.lookback, len(closes))
            r_highs = highs[-lookback:]
            r_lows = lows[-lookback:]
            r_closes = closes[-lookback:]

            curr_price = float(closes[-1])
            curr_open = float(opens[-1])
            curr_low = float(lows[-1])
            curr_high = float(highs[-1])

            # Calculate ATR for dynamic buffer
            if indicators_dict and "atr" in indicators_dict and not np.isnan(indicators_dict["atr"][-1]):
                atr_val = float(indicators_dict["atr"][-1])
            else:
                atr_arr = indicators.atr(highs, lows, closes, getattr(cfg, "atr_period", 14))
                atr_val = float(atr_arr[-1]) if not np.isnan(atr_arr[-1]) else curr_price * 0.002

            # Identify Swing Points
            w = 2
            n = len(r_closes)
            swing_highs = []
            swing_lows = []

            for i in range(w, n - w):
                if all(r_highs[i] >= r_highs[i - k] for k in range(1, w + 1)) and \
                   all(r_highs[i] >= r_highs[i + k] for k in range(1, w + 1)):
                    swing_highs.append(r_highs[i])

                if all(r_lows[i] <= r_lows[i - k] for k in range(1, w + 1)) and \
                   all(r_lows[i] <= r_lows[i + k] for k in range(1, w + 1)):
                    swing_lows.append(r_lows[i])

            # Cluster support and resistance levels
            supports = [s for s in swing_lows if s < curr_price]
            resistances = [r for r in swing_highs if r > curr_price]

            nearest_support = max(supports) if supports else (np.min(r_lows) if len(r_lows) > 0 else 0.0)
            nearest_resistance = min(resistances) if resistances else (np.max(r_highs) if len(r_highs) > 0 else 0.0)

            candle_range = max(curr_high - curr_low, 1e-8)
            lower_wick = min(curr_open, curr_price) - curr_low
            upper_wick = curr_high - max(curr_open, curr_price)

            buffer = max(atr_val * 0.75, curr_price * self.tolerance)

            # Bullish Bounce off Support
            if nearest_support > 0 and (curr_low <= nearest_support + buffer):
                if curr_price > nearest_support and (curr_price > curr_open or lower_wick / candle_range > 0.4):
                    dist_pct = ((curr_price - nearest_support) / curr_price) * 100.0
                    wick_ratio = lower_wick / candle_range
                    confidence = round(min(90.0, max(60.0, 65.0 + (wick_ratio * 20.0))), 2)
                    reason = (
                        f"Bullish bounce off Support {nearest_support:.5f} "
                        f"(dist: {dist_pct:.2f}%, lower wick ratio: {wick_ratio:.0%})"
                    )
                    return {
                        "signal": TradeDirection.BUY,
                        "confidence": confidence,
                        "reason": reason,
                        "strategy": self.name,
                    }

            # Bearish Bounce off Resistance
            if nearest_resistance > 0 and (curr_high >= nearest_resistance - buffer):
                if curr_price < nearest_resistance and (curr_price < curr_open or upper_wick / candle_range > 0.4):
                    dist_pct = ((nearest_resistance - curr_price) / curr_price) * 100.0
                    wick_ratio = upper_wick / candle_range
                    confidence = round(min(90.0, max(60.0, 65.0 + (wick_ratio * 20.0))), 2)
                    reason = (
                        f"Bearish bounce off Resistance {nearest_resistance:.5f} "
                        f"(dist: {dist_pct:.2f}%, upper wick ratio: {wick_ratio:.0%})"
                    )
                    return {
                        "signal": TradeDirection.SELL,
                        "confidence": confidence,
                        "reason": reason,
                        "strategy": self.name,
                    }

            return _default_result(
                self.name,
                f"Price {curr_price:.5f} between Support ({nearest_support:.5f}) and Resistance ({nearest_resistance:.5f})"
            )

        except Exception as e:
            logger.warning("SupportResistanceStrategy error: %s", e)
            return _default_result(self.name, f"Error: {e}")

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        return self.analyze(bars, cfg)


# ===========================================================================
#  STRATEGY 4: BOLLINGER BANDS MEAN REVERSION
# ===========================================================================
class BBMeanReversionStrategy:
    """
    Bollinger Bands Mean Reversion Strategy.

    BUY Setup:
      - Price touched or penetrated lower BB (low[-2] <= lower_bb[-2])
      - Current bar closes back inside lower BB with bullish candle (close[-1] > open[-1])

    SELL Setup:
      - Price touched or penetrated upper BB (high[-2] >= upper_bb[-2])
      - Current bar closes back inside upper BB with bearish candle (close[-1] < open[-1])
    """

    def __init__(self, name: str = "bb_mean_reversion"):
        self.name = name

    def analyze(self, bars: Any, cfg: Optional[BotConfig] = None,
                indicators_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            cfg = cfg or BotConfig()
            opens, highs, lows, closes, volumes = _extract_ohlcv(bars)

            period = getattr(cfg, "bb_period", 20)
            devs = getattr(cfg, "bb_deviations", 2.0)

            if len(closes) < period + 2:
                return _default_result(self.name, "Insufficient data for Bollinger Bands")

            if indicators_dict and all(k in indicators_dict for k in ("bb_mid", "bb_upper", "bb_lower")):
                bb_mid = indicators_dict["bb_mid"]
                bb_upper = indicators_dict["bb_upper"]
                bb_lower = indicators_dict["bb_lower"]
            else:
                bb_mid, bb_upper, bb_lower = indicators.bollinger_bands(closes, period, devs)

            if np.isnan(bb_mid[-1]) or np.isnan(bb_upper[-1]) or np.isnan(bb_lower[-1]):
                return _default_result(self.name, "BB indicator NaN values")

            # Check optional RSI filter confirmation
            rsi_val = 50.0
            if indicators_dict and "rsi" in indicators_dict and not np.isnan(indicators_dict["rsi"][-1]):
                rsi_val = float(indicators_dict["rsi"][-1])

            # BUY setup: touched lower band then closed back inside
            if (lows[-2] <= bb_lower[-2] or closes[-2] <= bb_lower[-2]) and closes[-1] > bb_lower[-1]:
                if closes[-1] > opens[-1]:
                    confidence = 70.0
                    if rsi_val < 40.0:
                        confidence = 85.0
                    reason = (
                        f"Mean Reversion BUY: Price touched lower BB ({bb_lower[-2]:.5f}) "
                        f"and closed inside ({closes[-1]:.5f}) towards middle BB ({bb_mid[-1]:.5f})"
                    )
                    return {
                        "signal": TradeDirection.BUY,
                        "confidence": confidence,
                        "reason": reason,
                        "strategy": self.name,
                    }

            # SELL setup: touched upper band then closed back inside
            if (highs[-2] >= bb_upper[-2] or closes[-2] >= bb_upper[-2]) and closes[-1] < bb_upper[-1]:
                if closes[-1] < opens[-1]:
                    confidence = 70.0
                    if rsi_val > 60.0:
                        confidence = 85.0
                    reason = (
                        f"Mean Reversion SELL: Price touched upper BB ({bb_upper[-2]:.5f}) "
                        f"and closed inside ({closes[-1]:.5f}) towards middle BB ({bb_mid[-1]:.5f})"
                    )
                    return {
                        "signal": TradeDirection.SELL,
                        "confidence": confidence,
                        "reason": reason,
                        "strategy": self.name,
                    }

            return _default_result(self.name, "No BB mean reversion pattern detected")

        except Exception as e:
            logger.warning("BBMeanReversionStrategy error: %s", e)
            return _default_result(self.name, f"Error: {e}")

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        return self.analyze(bars, cfg)


# ===========================================================================
#  STRATEGY 5: BOLLINGER BREAKOUT
# ===========================================================================
class BreakoutStrategy:
    """
    Bollinger Bands Breakout Strategy (Original Core Strategy).

    BUY Setup:
      - Close price breaks above upper Bollinger Band

    SELL Setup:
      - Close price breaks below lower Bollinger Band
    """

    def __init__(self, name: str = "breakout"):
        self.name = name

    def analyze(self, bars: Any, cfg: Optional[BotConfig] = None,
                indicators_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            cfg = cfg or BotConfig()
            opens, highs, lows, closes, volumes = _extract_ohlcv(bars)

            period = getattr(cfg, "bb_period", 20)
            devs = getattr(cfg, "bb_deviations", 2.0)

            if len(closes) < period + 2:
                return _default_result(self.name, "Insufficient data for BB Breakout")

            if indicators_dict and all(k in indicators_dict for k in ("bb_mid", "bb_upper", "bb_lower")):
                bb_mid = indicators_dict["bb_mid"]
                bb_upper = indicators_dict["bb_upper"]
                bb_lower = indicators_dict["bb_lower"]
            else:
                bb_mid, bb_upper, bb_lower = indicators.bollinger_bands(closes, period, devs)

            if np.isnan(bb_upper[-1]) or np.isnan(bb_lower[-1]):
                return _default_result(self.name, "BB indicator NaN values")

            # Check ADX trend confirmation if available
            adx_val = 0.0
            if indicators_dict and "adx" in indicators_dict and not np.isnan(indicators_dict["adx"][-1]):
                adx_val = float(indicators_dict["adx"][-1])
            min_adx = getattr(cfg, "min_adx", 25.0)

            # Volume expansion confirmation
            vol_boost = False
            if len(volumes) >= 20 and np.mean(volumes[-20:-1]) > 0:
                avg_vol = np.mean(volumes[-20:-1])
                if volumes[-1] > avg_vol * 1.2:
                    vol_boost = True

            # Bullish Breakout
            if closes[-1] > bb_upper[-1]:
                confidence = 70.0
                if adx_val >= min_adx:
                    confidence += 10.0
                if vol_boost:
                    confidence += 10.0
                confidence = round(min(95.0, confidence), 2)

                reason = (
                    f"BB Breakout BUY: Close ({closes[-1]:.5f}) broke above Upper BB ({bb_upper[-1]:.5f}) "
                    f"[ADX: {adx_val:.1f}]"
                )
                return {
                    "signal": TradeDirection.BUY,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            # Bearish Breakout
            if closes[-1] < bb_lower[-1]:
                confidence = 70.0
                if adx_val >= min_adx:
                    confidence += 10.0
                if vol_boost:
                    confidence += 10.0
                confidence = round(min(95.0, confidence), 2)

                reason = (
                    f"BB Breakout SELL: Close ({closes[-1]:.5f}) broke below Lower BB ({bb_lower[-1]:.5f}) "
                    f"[ADX: {adx_val:.1f}]"
                )
                return {
                    "signal": TradeDirection.SELL,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            return _default_result(
                self.name,
                f"Close ({closes[-1]:.5f}) inside bands [{bb_lower[-1]:.5f} - {bb_upper[-1]:.5f}]"
            )

        except Exception as e:
            logger.warning("BreakoutStrategy error: %s", e)
            return _default_result(self.name, f"Error: {e}")

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        return self.analyze(bars, cfg)


# ===========================================================================
#  STRATEGY 6: MACD CROSSOVER (ADDITIONAL RESEARCH STRATEGY 1)
# ===========================================================================
class MACDCrossoverStrategy:
    """
    MACD Signal Line Crossover Strategy with Zero Line & Histogram Momentum.

    BUY Setup:
      - MACD line crosses above Signal line
      - Extra confidence if crossover happens below Zero line (bullish reversal)

    SELL Setup:
      - MACD line crosses below Signal line
      - Extra confidence if crossover happens above Zero line (bearish reversal)
    """

    def __init__(self, name: str = "macd_crossover"):
        self.name = name

    def analyze(self, bars: Any, cfg: Optional[BotConfig] = None,
                indicators_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            cfg = cfg or BotConfig()
            opens, highs, lows, closes, volumes = _extract_ohlcv(bars)

            fast_p = getattr(cfg, "macd_fast", 12)
            slow_p = getattr(cfg, "macd_slow", 26)
            signal_p = getattr(cfg, "macd_signal", 9)

            if len(closes) < slow_p + signal_p + 2:
                return _default_result(self.name, "Insufficient data for MACD")

            macd_line, signal_line, hist = indicators.calc_macd(closes, fast_p, slow_p, signal_p)

            if (len(macd_line) < 2 or np.isnan(macd_line[-1]) or
                np.isnan(signal_line[-1]) or np.isnan(macd_line[-2])):
                return _default_result(self.name, "MACD indicator NaN values")

            m_curr, s_curr = macd_line[-1], signal_line[-1]
            m_prev, s_prev = macd_line[-2], signal_line[-2]

            # Bullish MACD Crossover
            if m_prev <= s_prev and m_curr > s_curr:
                confidence = 75.0
                if m_curr < 0:  # Reversal from oversold territory below zero
                    confidence = 85.0
                reason = (
                    f"MACD Bullish Crossover: MACD line ({m_curr:.5f}) crossed above Signal ({s_curr:.5f})"
                )
                return {
                    "signal": TradeDirection.BUY,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            # Bearish MACD Crossover
            if m_prev >= s_prev and m_curr < s_curr:
                confidence = 75.0
                if m_curr > 0:  # Reversal from overbought territory above zero
                    confidence = 85.0
                reason = (
                    f"MACD Bearish Crossover: MACD line ({m_curr:.5f}) crossed below Signal ({s_curr:.5f})"
                )
                return {
                    "signal": TradeDirection.SELL,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            return _default_result(self.name, f"MACD ({m_curr:.5f}) and Signal ({s_curr:.5f}) no crossover")

        except Exception as e:
            logger.warning("MACDCrossoverStrategy error: %s", e)
            return _default_result(self.name, f"Error: {e}")

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        return self.analyze(bars, cfg)


# ===========================================================================
#  STRATEGY 7: STOCHASTIC REVERSAL (ADDITIONAL RESEARCH STRATEGY 2)
# ===========================================================================
class StochasticReversalStrategy:
    """
    Stochastic Oscillator Overbought/Oversold Crossover Strategy.

    BUY Setup:
      - %K line crosses above %D line while in Oversold territory (< stoch_oversold, e.g. 20)

    SELL Setup:
      - %K line crosses below %D line while in Overbought territory (> stoch_overbought, e.g. 80)
    """

    def __init__(self, name: str = "stochastic_reversal"):
        self.name = name

    def analyze(self, bars: Any, cfg: Optional[BotConfig] = None,
                indicators_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            cfg = cfg or BotConfig()
            opens, highs, lows, closes, volumes = _extract_ohlcv(bars)

            k_period = getattr(cfg, "stoch_k_period", 5)
            d_period = getattr(cfg, "stoch_d_period", 3)
            slowing = getattr(cfg, "stoch_slowing", 3)
            oversold = getattr(cfg, "stoch_oversold", 20.0)
            overbought = getattr(cfg, "stoch_overbought", 80.0)

            if len(closes) < k_period + d_period + slowing + 2:
                return _default_result(self.name, "Insufficient data for Stochastic Oscillator")

            k_arr, d_arr = indicators.calc_stochastic(highs, lows, closes, k_period, d_period, slowing)

            if (len(k_arr) < 2 or np.isnan(k_arr[-1]) or
                np.isnan(d_arr[-1]) or np.isnan(k_arr[-2])):
                return _default_result(self.name, "Stochastic indicator NaN values")

            k_curr, d_curr = k_arr[-1], d_arr[-1]
            k_prev, d_prev = k_arr[-2], d_arr[-2]

            # BUY: %K crosses above %D in oversold zone
            if k_prev <= d_prev and k_curr > d_curr and k_prev < oversold:
                extremity = oversold - k_prev
                confidence = round(min(95.0, 70.0 + (extremity * 1.0)), 2)
                reason = (
                    f"Stochastic Oversold Reversal: %K ({k_curr:.1f}) crossed above %D ({d_curr:.1f}) "
                    f"from oversold level {k_prev:.1f} (< {oversold:.1f})"
                )
                return {
                    "signal": TradeDirection.BUY,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            # SELL: %K crosses below %D in overbought zone
            if k_prev >= d_prev and k_curr < d_curr and k_prev > overbought:
                extremity = k_prev - overbought
                confidence = round(min(95.0, 70.0 + (extremity * 1.0)), 2)
                reason = (
                    f"Stochastic Overbought Reversal: %K ({k_curr:.1f}) crossed below %D ({d_curr:.1f}) "
                    f"from overbought level {k_prev:.1f} (> {overbought:.1f})"
                )
                return {
                    "signal": TradeDirection.SELL,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            return _default_result(self.name, f"Stochastic %K ({k_curr:.1f}) and %D ({d_curr:.1f}) in range")

        except Exception as e:
            logger.warning("StochasticReversalStrategy error: %s", e)
            return _default_result(self.name, f"Error: {e}")

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        return self.analyze(bars, cfg)


# ===========================================================================
#  STRATEGY 8: TREND ADX PULLBACK (ADDITIONAL RESEARCH STRATEGY 3)
# ===========================================================================
class TrendADXStrategy:
    """
    Trend ADX Pullback & Bounce Strategy (Proven Forex Scalp/Swing Setup).

    Uses ADX for trend strength filtering (> min_adx, e.g. 25) + Fast/Slow EMA alignment.
    BUY: Strong Uptrend (ADX > 25, Fast EMA > Slow EMA) + Price pulls back to Fast EMA and bounces up.
    SELL: Strong Downtrend (ADX > 25, Fast EMA < Slow EMA) + Price pulls back to Fast EMA and bounces down.
    """

    def __init__(self, name: str = "trend_adx"):
        self.name = name

    def analyze(self, bars: Any, cfg: Optional[BotConfig] = None,
                indicators_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            cfg = cfg or BotConfig()
            opens, highs, lows, closes, volumes = _extract_ohlcv(bars)

            fast_p = getattr(cfg, "fast_ema_period", 50)
            slow_p = getattr(cfg, "slow_ema_period", 200)
            adx_p = getattr(cfg, "adx_period", 14)
            min_adx = getattr(cfg, "min_adx", 25.0)

            if len(closes) < max(slow_p, adx_p * 2) + 2:
                return _default_result(self.name, "Insufficient data for Trend ADX Strategy")

            if indicators_dict and "adx" in indicators_dict:
                adx_arr = indicators_dict["adx"]
            else:
                adx_arr = indicators.calc_adx(highs, lows, closes, adx_p)

            if indicators_dict and "ema_fast" in indicators_dict and "ema_slow" in indicators_dict:
                ema_fast = indicators_dict["ema_fast"]
                ema_slow = indicators_dict["ema_slow"]
            else:
                ema_fast = indicators.ema(closes, fast_p)
                ema_slow = indicators.ema(closes, slow_p)

            if (np.isnan(adx_arr[-1]) or np.isnan(ema_fast[-1]) or np.isnan(ema_slow[-1])):
                return _default_result(self.name, "Trend ADX indicator NaN values")

            curr_adx = float(adx_arr[-1])
            f_ema = float(ema_fast[-1])
            s_ema = float(ema_slow[-1])
            curr_low = float(lows[-1])
            curr_high = float(highs[-1])
            curr_close = float(closes[-1])
            curr_open = float(opens[-1])

            if curr_adx < min_adx:
                return _default_result(self.name, f"ADX trend too weak ({curr_adx:.1f} < {min_adx:.1f})")

            # Uptrend Pullback Bounce (BUY)
            if f_ema > s_ema and curr_low <= f_ema * 1.001 and curr_close > curr_open:
                confidence = round(min(95.0, 75.0 + (curr_adx - min_adx) * 0.5), 2)
                reason = (
                    f"Strong Uptrend Continuation (ADX {curr_adx:.1f}): Pullback bounce off "
                    f"EMA{fast_p} ({f_ema:.5f}) with bullish close"
                )
                return {
                    "signal": TradeDirection.BUY,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            # Downtrend Pullback Bounce (SELL)
            if f_ema < s_ema and curr_high >= f_ema * 0.999 and curr_close < curr_open:
                confidence = round(min(95.0, 75.0 + (curr_adx - min_adx) * 0.5), 2)
                reason = (
                    f"Strong Downtrend Continuation (ADX {curr_adx:.1f}): Pullback bounce off "
                    f"EMA{fast_p} ({f_ema:.5f}) with bearish close"
                )
                return {
                    "signal": TradeDirection.SELL,
                    "confidence": confidence,
                    "reason": reason,
                    "strategy": self.name,
                }

            return _default_result(self.name, f"ADX strong ({curr_adx:.1f}) but no pullback bounce setup")

        except Exception as e:
            logger.warning("TrendADXStrategy error: %s", e)
            return _default_result(self.name, f"Error: {e}")

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        return self.analyze(bars, cfg)


# ===========================================================================
#  STRATEGY MANAGER
# ===========================================================================
class StrategyManager:
    """
    Manages all trading strategies, executes analysis across market data,
    computes pre-cached indicator dictionaries for efficiency, and aggregates
    signals (best signal & multi-strategy consensus).
    """

    def __init__(self, cfg: Optional[BotConfig] = None):
        self.cfg = cfg or BotConfig()
        self.strategies: Dict[str, Any] = {
            "breakout": BreakoutStrategy(),
            "rsi_reversal": RSIReversalStrategy(),
            "ema_crossover": EMACrossoverStrategy(),
            "support_resistance": SupportResistanceStrategy(),
            "bb_mean_reversion": BBMeanReversionStrategy(),
            "macd_crossover": MACDCrossoverStrategy(),
            "stochastic_reversal": StochasticReversalStrategy(),
            "trend_adx": TrendADXStrategy(),
        }
        # Add advanced strategies if available
        if HAS_FVG:
            self.strategies["fvg"] = FVGStrategy()
        if HAS_ICT:
            self.strategies["ict_killzones"] = ICTKillzoneStrategy()
        if HAS_VP:
            self.strategies["volume_profile"] = VolumeProfileStrategy()
        if ICTKillzoneStrategy is not None:
            self.strategies["ict_killzones"] = ICTKillzoneStrategy()

    def run_all(self, bars: Any, cfg: Optional[BotConfig] = None) -> List[Dict[str, Any]]:
        """
        Executes all active strategies against the provided price bars.

        Args:
            bars: List of Bar dataclasses, list of dicts, or NumPy array.
            cfg: BotConfig instance (optional, defaults to self.cfg).

        Returns:
            List of strategy result dictionaries.
        """
        current_cfg = cfg or self.cfg
        enabled = getattr(current_cfg, "enabled_strategies", None)

        opens, highs, lows, closes, volumes = _extract_ohlcv(bars)
        if len(closes) < 10:
            logger.warning("Insufficient bars (%d) for StrategyManager execution", len(closes))
            return []

        # Pre-compute common indicator bundle for performance
        try:
            indicators_dict = indicators.compute_all_indicators(highs, lows, closes, current_cfg)
        except Exception as e:
            logger.warning("Failed to compute indicator bundle: %s", e)
            indicators_dict = {}

        results: List[Dict[str, Any]] = []

        for strat_id, strategy in self.strategies.items():
            if enabled and strat_id not in enabled:
                continue

            try:
                res = strategy.analyze(bars, current_cfg, indicators_dict)
                results.append(res)
            except Exception as e:
                logger.warning("Strategy '%s' execution error: %s", strat_id, e)
                results.append(_default_result(strat_id, f"Execution failed: {e}"))

        return results

    def get_best_signal(self, results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Extracts the strategy result with the highest confidence score among valid signals.

        Args:
            results: List of strategy result dictionaries from run_all().

        Returns:
            The result dictionary with highest confidence, or a fallback None signal dict.
        """
        valid_signals = [
            r for r in results
            if r.get("signal") in (TradeDirection.BUY, TradeDirection.SELL)
            and r.get("confidence", 0.0) > 0.0
        ]

        if not valid_signals:
            return _default_result("none", "No valid strategy signal found")

        best = max(valid_signals, key=lambda r: r.get("confidence", 0.0))
        return best

    def get_consensus(self, results: List[Dict[str, Any]],
                      min_consensus_count: Optional[int] = None) -> Dict[str, Any]:
        """
        Determines if multiple independent strategies agree on the market direction.
        If 3 or more strategies (or min_consensus_count) agree, returns a consensus signal
        with boosted confidence score.

        Args:
            results: List of strategy result dictionaries.
            min_consensus_count: Minimum agreeing strategies threshold (default: cfg or 3).

        Returns:
            Consensus signal dictionary.
        """
        required_count = min_consensus_count
        if required_count is None:
            required_count = getattr(self.cfg, "min_consensus_count", 3)
            if required_count < 2:
                required_count = 3

        buy_results = [
            r for r in results
            if r.get("signal") == TradeDirection.BUY and r.get("confidence", 0.0) > 0.0
        ]
        sell_results = [
            r for r in results
            if r.get("signal") == TradeDirection.SELL and r.get("confidence", 0.0) > 0.0
        ]

        buy_count = len(buy_results)
        sell_count = len(sell_results)

        if buy_count >= required_count and buy_count > sell_count:
            agree_results = buy_results
            direction = TradeDirection.BUY
            count = buy_count
        elif sell_count >= required_count and sell_count > buy_count:
            agree_results = sell_results
            direction = TradeDirection.SELL
            count = sell_count
        else:
            return {
                "signal": None,
                "confidence": 0.0,
                "reason": f"No consensus reached (BUY: {buy_count}, SELL: {sell_count}, required: {required_count})",
                "strategy": "consensus",
            }

        avg_conf = sum(r.get("confidence", 0.0) for r in agree_results) / count
        boost = 10.0 if count == 3 else (15.0 if count >= 4 else 5.0)
        final_conf = round(min(100.0, avg_conf + boost), 2)

        agree_names = ", ".join([r.get("strategy", "unknown") for r in agree_results])
        reason = (
            f"Multi-Strategy Consensus {direction.value.upper()}: {count} strategies agree "
            f"({agree_names}) with avg confidence {avg_conf:.1f}% + {boost:.0f}% boost"
        )

        return {
            "signal": direction,
            "confidence": final_conf,
            "reason": reason,
            "strategy": "consensus",
        }
