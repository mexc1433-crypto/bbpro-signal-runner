"""
scalping.py — Fast Scalping Strategy (M5/M15)
==============================================
Fast entry/exit signals for quick scalping on M5/M15 timeframes using multiple confirmations:
1. VWAP position (price above/below VWAP for trend direction)
2. Stochastic crossover / overbought/oversold reversal (< 20 oversold buy, > 80 overbought sell)
3. EMA alignment (Fast EMA > Slow EMA for uptrend, or vice versa)
4. RSI momentum (RSI between 40-60 for active momentum)

Requires at least 3 of 4 conditions to align.
Very tight SL/TP calculations (5-15 pips) based on ATR (SL: 1.5x ATR, TP: 1x ATR).
Confidence score: base 50 + 10 per extra confirmation above minimum required.
"""

from __future__ import annotations
import logging
import numpy as np
from typing import Dict, Any, Optional, Tuple, List, Union

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
    from symbol_profiles import get_profile
except ImportError:
    try:
        from .symbol_profiles import get_profile
    except ImportError:
        get_profile = None

logger = logging.getLogger(__name__)


def _extract_ohlcv(bars: Any) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Safely extracts open, high, low, close, volume arrays from various bar formats.
    Supports List[Bar], List[dict], or NumPy 2D array.
    """
    if isinstance(bars, np.ndarray):
        if bars.ndim == 2 and bars.shape[1] >= 5:
            return (bars[:, 0].astype(float),
                    bars[:, 1].astype(float),
                    bars[:, 2].astype(float),
                    bars[:, 3].astype(float),
                    bars[:, 4].astype(float))
        closes = bars.astype(float)
        return closes, closes, closes, closes, np.ones_like(closes)

    if not bars:
        empty = np.array([], dtype=float)
        return empty, empty, empty, empty, empty

    first = bars[0]
    if hasattr(first, "open"):
        opens = np.array([float(getattr(b, "open", 0.0)) for b in bars], dtype=float)
        highs = np.array([float(getattr(b, "high", 0.0)) for b in bars], dtype=float)
        lows = np.array([float(getattr(b, "low", 0.0)) for b in bars], dtype=float)
        closes = np.array([float(getattr(b, "close", 0.0)) for b in bars], dtype=float)
        volumes = np.array([float(getattr(b, "volume", 1000.0) or 1000.0) for b in bars], dtype=float)
    elif isinstance(first, dict):
        opens = np.array([float(b.get("open", b.get("close", 0.0))) for b in bars], dtype=float)
        highs = np.array([float(b.get("high", b.get("close", 0.0))) for b in bars], dtype=float)
        lows = np.array([float(b.get("low", b.get("close", 0.0))) for b in bars], dtype=float)
        closes = np.array([float(b.get("close", 0.0)) for b in bars], dtype=float)
        volumes = np.array([float(b.get("volume", 1000.0) or 1000.0) for b in bars], dtype=float)
    else:
        closes = np.array([float(b) for b in bars], dtype=float)
        opens, highs, lows = closes, closes, closes
        volumes = np.ones_like(closes) * 1000.0

    return opens, highs, lows, closes, volumes


def _get_pip_size(symbol: str, cfg: Optional[BotConfig] = None) -> float:
    """Determine pip size for a symbol."""
    if cfg is not None and hasattr(cfg, "pip_size") and getattr(cfg, "pip_size", 0) > 0:
        return float(getattr(cfg, "pip_size"))

    if get_profile is not None and symbol:
        prof = get_profile(symbol)
        if prof and "pip_size" in prof:
            return float(prof["pip_size"])

    sym = (symbol or "").upper()
    if "JPY" in sym:
        return 0.01
    elif "XAU" in sym or "GOLD" in sym:
        return 0.1
    elif "BTC" in sym or "ETH" in sym or "USDT" in sym:
        return 1.0
    return 0.0001


class ScalpingStrategy:
    """
    ScalpingStrategy — High-probability fast scalping on M5/M15 timeframes.

    Criteria evaluated:
      1. VWAP position (close > VWAP for BUY, close < VWAP for SELL)
      2. Stochastic crossover / overbought/oversold reversal (< 20 oversold for BUY, > 80 overbought for SELL)
      3. EMA alignment (Fast EMA > Slow EMA for BUY, Fast EMA < Slow EMA for SELL)
      4. RSI momentum (40 <= RSI <= 60 for active momentum)

    Requires >= 3 confirmations.
    Confidence: base 50 + 10 per extra confirmation above minimum required.
    SL/TP: Tight 5-15 pips calculated as 1.5x ATR for SL and 1.0x ATR for TP.
    """

    def __init__(self, name: str = "scalping"):
        self.name = name

    def analyze(self, bars: Any, cfg: Optional[BotConfig] = None,
                indicators_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyze price bars for scalping setup.

        Args:
            bars: List of Bar objects, dicts, or numpy arrays
            cfg: BotConfig settings
            indicators_dict: Pre-calculated indicator dict (optional)

        Returns:
            dict containing:
              - 'strategy': strategy name ('scalping')
              - 'signal': TradeDirection enum (BUY, SELL, or NONE/None)
              - 'confidence': confidence percentage (0-100)
              - 'reason': string summary of signal conditions
              - 'sl_pips': stop loss distance in pips
              - 'tp_pips': take profit distance in pips
        """
        no_signal_val = getattr(TradeDirection, "NONE", None)

        try:
            cfg = cfg or BotConfig()
            opens, highs, lows, closes, volumes = _extract_ohlcv(bars)

            # Parameters with defaults
            stoch_oversold = float(getattr(cfg, "scalping_stoch_oversold", 20.0))
            stoch_overbought = float(getattr(cfg, "scalping_stoch_overbought", 80.0))
            sl_atr_mult = float(getattr(cfg, "scalping_sl_atr_mult", 1.5))
            tp_atr_mult = float(getattr(cfg, "scalping_tp_atr_mult", 1.0))
            min_confirmations = int(getattr(cfg, "scalping_min_confirmations", 3))

            fast_ema_p = int(getattr(cfg, "scalping_fast_ema", getattr(cfg, "fast_ema_period", 9)))
            slow_ema_p = int(getattr(cfg, "scalping_slow_ema", getattr(cfg, "slow_ema_period", 21)))
            rsi_p = int(getattr(cfg, "rsi_period", 14))
            atr_p = int(getattr(cfg, "atr_period", 14))

            min_required_bars = max(slow_ema_p, rsi_p, atr_p, 20) + 2
            if len(closes) < min_required_bars:
                return {
                    "strategy": self.name,
                    "signal": no_signal_val,
                    "confidence": 0.0,
                    "reason": f"Insufficient bars ({len(closes)}/{min_required_bars}) for scalping strategy",
                    "sl_pips": 0.0,
                    "tp_pips": 0.0,
                }

            # 1. VWAP
            vwap_val = None
            if indicators_dict and "vwap" in indicators_dict:
                v_raw = indicators_dict["vwap"]
                if isinstance(v_raw, np.ndarray) and len(v_raw) > 0:
                    vwap_val = float(v_raw[-1])
                elif isinstance(v_raw, dict) and "vwap" in v_raw:
                    vwap_val = float(v_raw["vwap"])
                elif isinstance(v_raw, (int, float)):
                    vwap_val = float(v_raw)

            if vwap_val is None or np.isnan(vwap_val):
                vwap_arr = indicators.calc_vwap(highs, lows, closes, volumes)
                vwap_val = float(vwap_arr[-1]) if len(vwap_arr) > 0 else float(closes[-1])

            # 2. Stochastic
            if indicators_dict and "stoch_k" in indicators_dict and "stoch_d" in indicators_dict:
                stoch_k_arr = indicators_dict["stoch_k"]
                stoch_d_arr = indicators_dict["stoch_d"]
            else:
                stoch_k_arr, stoch_d_arr = indicators.calc_stochastic(highs, lows, closes, k_period=5, d_period=3, slowing=3)

            stoch_k_curr = float(stoch_k_arr[-1])
            stoch_d_curr = float(stoch_d_arr[-1])
            stoch_k_prev = float(stoch_k_arr[-2]) if len(stoch_k_arr) >= 2 else stoch_k_curr
            stoch_d_prev = float(stoch_d_arr[-2]) if len(stoch_d_arr) >= 2 else stoch_d_curr

            # 3. EMA alignment
            if indicators_dict and "ema_fast" in indicators_dict and "ema_slow" in indicators_dict:
                ema_fast_arr = indicators_dict["ema_fast"]
                ema_slow_arr = indicators_dict["ema_slow"]
            else:
                ema_fast_arr = indicators.ema(closes, fast_ema_p)
                ema_slow_arr = indicators.ema(closes, slow_ema_p)

            ema_fast_curr = float(ema_fast_arr[-1])
            ema_slow_curr = float(ema_slow_arr[-1])

            # 4. RSI
            if indicators_dict and "rsi" in indicators_dict:
                rsi_arr = indicators_dict["rsi"]
            else:
                rsi_arr = indicators.rsi(closes, rsi_p)

            rsi_curr = float(rsi_arr[-1])

            # ATR for SL/TP
            if indicators_dict and "atr" in indicators_dict:
                atr_arr = indicators_dict["atr"]
            else:
                atr_arr = indicators.atr(highs, lows, closes, atr_p)

            atr_curr = float(atr_arr[-1])
            close_curr = float(closes[-1])

            # Check for NaN values
            val_check = [close_curr, vwap_val, stoch_k_curr, stoch_d_curr, ema_fast_curr, ema_slow_curr, rsi_curr, atr_curr]
            if any(np.isnan(v) or np.isinf(v) for v in val_check):
                return {
                    "strategy": self.name,
                    "signal": no_signal_val,
                    "confidence": 0.0,
                    "reason": "Calculated indicator values contain NaN or Inf",
                    "sl_pips": 0.0,
                    "tp_pips": 0.0,
                }

            # ── Condition Checks ──────────────────────────────────────────────

            # BUY Conditions
            # 1. Price above VWAP
            vwap_buy = close_curr > vwap_val

            # 2. Stochastic oversold reversal / crossover
            #    Oversold (%K < 20 or %D < 20) or bullish crossover while in oversold zone (< 35)
            stoch_buy = (
                stoch_k_curr < stoch_oversold or
                stoch_d_curr < stoch_oversold or
                (stoch_k_curr > stoch_d_curr and stoch_k_prev <= stoch_d_prev and stoch_k_curr < 35.0)
            )

            # 3. Fast EMA > Slow EMA (Uptrend)
            ema_buy = ema_fast_curr > ema_slow_curr

            # 4. RSI momentum (40 <= RSI <= 60)
            rsi_buy = 40.0 <= rsi_curr <= 60.0


            # SELL Conditions
            # 1. Price below VWAP
            vwap_sell = close_curr < vwap_val

            # 2. Stochastic overbought reversal / crossover
            #    Overbought (%K > 80 or %D > 80) or bearish crossover while in overbought zone (> 65)
            stoch_sell = (
                stoch_k_curr > stoch_overbought or
                stoch_d_curr > stoch_overbought or
                (stoch_k_curr < stoch_d_curr and stoch_k_prev >= stoch_d_prev and stoch_k_curr > 65.0)
            )

            # 3. Fast EMA < Slow EMA (Downtrend)
            ema_sell = ema_fast_curr < ema_slow_curr

            # 4. RSI momentum (40 <= RSI <= 60)
            rsi_sell = 40.0 <= rsi_curr <= 60.0

            # ── Count Confirmations ───────────────────────────────────────────
            buy_reasons = []
            if vwap_buy:
                buy_reasons.append(f"Price above VWAP ({close_curr:.5f} > {vwap_val:.5f})")
            if stoch_buy:
                buy_reasons.append(f"Stochastic oversold/reversal (%K={stoch_k_curr:.1f}, %D={stoch_d_curr:.1f} < {stoch_oversold:.0f})")
            if ema_buy:
                buy_reasons.append(f"Fast EMA > Slow EMA ({ema_fast_curr:.5f} > {ema_slow_curr:.5f})")
            if rsi_buy:
                buy_reasons.append(f"RSI in momentum zone ({rsi_curr:.1f} in [40, 60])")

            sell_reasons = []
            if vwap_sell:
                sell_reasons.append(f"Price below VWAP ({close_curr:.5f} < {vwap_val:.5f})")
            if stoch_sell:
                sell_reasons.append(f"Stochastic overbought/reversal (%K={stoch_k_curr:.1f}, %D={stoch_d_curr:.1f} > {stoch_overbought:.0f})")
            if ema_sell:
                sell_reasons.append(f"Fast EMA < Slow EMA ({ema_fast_curr:.5f} < {ema_slow_curr:.5f})")
            if rsi_sell:
                sell_reasons.append(f"RSI in momentum zone ({rsi_curr:.1f} in [40, 60])")

            buy_confirms = len(buy_reasons)
            sell_confirms = len(sell_reasons)

            # Select signal direction
            signal = no_signal_val
            num_aligned = 0
            chosen_reasons = []

            if buy_confirms >= min_confirmations and buy_confirms >= sell_confirms:
                signal = TradeDirection.BUY
                num_aligned = buy_confirms
                chosen_reasons = buy_reasons
            elif sell_confirms >= min_confirmations and sell_confirms > buy_confirms:
                signal = TradeDirection.SELL
                num_aligned = sell_confirms
                chosen_reasons = sell_reasons

            if signal is no_signal_val or signal is None:
                return {
                    "strategy": self.name,
                    "signal": no_signal_val,
                    "confidence": 0.0,
                    "reason": (f"No scalping signal (BUY confirms: {buy_confirms}/4, "
                               f"SELL confirms: {sell_confirms}/4; required: {min_confirmations})"),
                    "sl_pips": 0.0,
                    "tp_pips": 0.0,
                }

            # ── Confidence Scoring ────────────────────────────────────────────
            # Base 50 + 10 per extra confirmation above min_confirmations (e.g. 3 -> 50, 4 -> 60)
            extra_confirmations = num_aligned - min_confirmations
            confidence = float(50.0 + 10.0 * extra_confirmations)
            confidence = min(100.0, max(0.0, confidence))

            # ── SL/TP Calculations ────────────────────────────────────────────
            symbol = getattr(cfg, "symbol", "EURUSD")
            pip_size = _get_pip_size(symbol, cfg)
            atr_pips = (atr_curr / pip_size) if pip_size > 0 else atr_curr

            raw_sl_pips = sl_atr_mult * atr_pips
            raw_tp_pips = tp_atr_mult * atr_pips

            # Constrain SL and TP to tight scalping range (5-15 pips)
            sl_pips = round(max(5.0, min(15.0, raw_sl_pips)), 1)
            tp_pips = round(max(5.0, min(15.0, raw_tp_pips)), 1)

            direction_str = signal.value.upper() if hasattr(signal, "value") else str(signal).upper()
            reason_str = f"Scalping {direction_str} ({num_aligned}/4 confirms): " + "; ".join(chosen_reasons)

            return {
                "strategy": self.name,
                "signal": signal,
                "confidence": round(confidence, 2),
                "reason": reason_str,
                "sl_pips": sl_pips,
                "tp_pips": tp_pips,
            }

        except Exception as e:
            logger.error(f"Error in ScalpingStrategy.analyze: {e}", exc_info=True)
            return {
                "strategy": self.name,
                "signal": no_signal_val,
                "confidence": 0.0,
                "reason": f"Error during scalping analysis: {e}",
                "sl_pips": 0.0,
                "tp_pips": 0.0,
            }

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        """Backward-compatible entry point."""
        return self.analyze(bars, cfg)
