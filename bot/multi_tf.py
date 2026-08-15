"""
multi_tf.py
===========
Multi-timeframe confluence analysis for BBPro Signal Bot.

Fetches market data across multiple timeframes (M15, M30, H1, H4) using the provided
cTrader / Yahoo Finance client and calculates indicator trends on each timeframe to
determine signal confluence and overall market direction.
"""

import asyncio
import logging
import numpy as np
from typing import Dict, Any, List, Optional

try:
    from .indicators import bollinger_bands, rsi, ema, atr, calc_adx
except (ImportError, ValueError):
    from indicators import bollinger_bands, rsi, ema, atr, calc_adx

logger = logging.getLogger(__name__)


class MultiTFAnalyzer:
    """
    Analyzes multi-timeframe indicator confluence across M15, M30, H1, and H4.
    """

    TIMEFRAMES = ["m15", "m30", "h1", "h4"]

    async def analyze(self, client, symbol: str, cfg: Optional[Any] = None) -> Dict[str, Any]:
        """
        Fetches M15, M30, H1, H4 bars and computes indicators for each timeframe.

        Args:
            client: cTrader / Yahoo Finance client instance with async get_recent_bars(symbol, timeframe, count).
            symbol: Trading symbol (e.g. "EURUSD", "US30", "XAUUSD").
            cfg: Optional bot configuration object.

        Returns:
            Dict containing:
                - "timeframes": Dict[str, dict] with analysis for m15, m30, h1, h4
                - "confluence": float (0-100), percentage of timeframes in agreement
                - "direction": "buy", "sell", or "neutral"
                - "agreement_count": int (0 to 4), number of TFs agreeing
                - "description": str, human readable summary
        """
        bar_count = getattr(cfg, "multi_tf_bar_count", 300) if cfg is not None else 300

        # Fetch bars for all 4 timeframes concurrently
        tasks = [client.get_recent_bars(symbol, tf, bar_count) for tf in self.TIMEFRAMES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        tf_analysis: Dict[str, Dict[str, Any]] = {}

        for tf, res in zip(self.TIMEFRAMES, results):
            if isinstance(res, Exception) or not res:
                logger.warning("Failed to fetch bars for %s on timeframe %s: %s", symbol, tf, res)
                tf_analysis[tf] = self._empty_tf_dict()
            else:
                tf_analysis[tf] = self._analyze_timeframe(res)

        # Compute confluence across timeframes
        buy_count = sum(1 for tf_data in tf_analysis.values() if tf_data["direction"] == "buy")
        sell_count = sum(1 for tf_data in tf_analysis.values() if tf_data["direction"] == "sell")

        if buy_count >= 3:
            direction = "buy"
            agreement_count = buy_count
            confluence = (buy_count / 4.0) * 100.0
        elif sell_count >= 3:
            direction = "sell"
            agreement_count = sell_count
            confluence = (sell_count / 4.0) * 100.0
        elif buy_count == 2 and sell_count < 2:
            direction = "buy"
            agreement_count = 2
            confluence = 50.0
        elif sell_count == 2 and buy_count < 2:
            direction = "sell"
            agreement_count = 2
            confluence = 50.0
        else:
            direction = "neutral"
            agreement_count = max(buy_count, sell_count)
            confluence = 0.0

        # Build human-readable summary
        tf_summaries = [f"{tf.upper()}:{tf_analysis[tf]['direction']}" for tf in self.TIMEFRAMES]
        tf_str = ", ".join(tf_summaries)

        if direction != "neutral":
            description = (
                f"Multi-TF Confluence ({symbol}): {agreement_count}/4 TFs agree on {direction.upper()} "
                f"({confluence:.0f}% confluence). [{tf_str}]"
            )
        else:
            description = (
                f"Multi-TF Confluence ({symbol}): Mixed signals ({confluence:.0f}% confluence, neutral). [{tf_str}]"
            )

        return {
            "timeframes": tf_analysis,
            "confluence": float(confluence),
            "direction": direction,
            "agreement_count": int(agreement_count),
            "description": description,
        }

    def _analyze_timeframe(self, bars: List[Any]) -> Dict[str, Any]:
        """Computes indicators and trend direction for a single timeframe's bars."""
        if len(bars) < 50:
            return self._empty_tf_dict()

        highs = np.array([getattr(b, "high", b.get("high") if isinstance(b, dict) else 0.0) for b in bars], dtype=float)
        lows = np.array([getattr(b, "low", b.get("low") if isinstance(b, dict) else 0.0) for b in bars], dtype=float)
        closes = np.array([getattr(b, "close", b.get("close") if isinstance(b, dict) else 0.0) for b in bars], dtype=float)

        current_price = closes[-1]

        # 1. EMA 50 vs EMA 200 Trend
        ema50_arr = ema(closes, 50)
        ema200_arr = ema(closes, min(200, max(50, len(closes))))

        ema50_val = ema50_arr[-1] if not np.isnan(ema50_arr[-1]) else current_price
        ema200_val = ema200_arr[-1] if not np.isnan(ema200_arr[-1]) else current_price

        if ema50_val > ema200_val:
            ema_trend = "bullish"
            direction = "buy"
        elif ema50_val < ema200_val:
            ema_trend = "bearish"
            direction = "sell"
        else:
            ema_trend = "flat"
            direction = "neutral"

        # 2. RSI Level
        rsi_arr = rsi(closes, 14)
        rsi_val = float(rsi_arr[-1]) if not np.isnan(rsi_arr[-1]) else 50.0

        # 3. ADX Trend Strength
        adx_arr = calc_adx(highs, lows, closes, 14)
        adx_val = float(adx_arr[-1]) if not np.isnan(adx_arr[-1]) else 0.0

        # 4. Price vs Bollinger Bands Position
        mid_arr, upper_arr, lower_arr = bollinger_bands(closes, period=20, deviations=2.0)
        upper_val = upper_arr[-1] if not np.isnan(upper_arr[-1]) else current_price
        lower_val = lower_arr[-1] if not np.isnan(lower_arr[-1]) else current_price
        mid_val = mid_arr[-1] if not np.isnan(mid_arr[-1]) else current_price

        if current_price > upper_val:
            bb_position = "above_upper"
        elif current_price < lower_val:
            bb_position = "below_lower"
        elif current_price >= mid_val:
            bb_position = "upper_half"
        else:
            bb_position = "lower_half"

        return {
            "ema_trend": ema_trend,
            "rsi": round(rsi_val, 2),
            "adx": round(adx_val, 2),
            "bb_position": bb_position,
            "direction": direction,
            "ema50": round(float(ema50_val), 5),
            "ema200": round(float(ema200_val), 5),
            "close": round(float(current_price), 5),
        }

    @staticmethod
    def _empty_tf_dict() -> Dict[str, Any]:
        """Default fallback dictionary when timeframe data is unavailable or insufficient."""
        return {
            "ema_trend": "flat",
            "rsi": 50.0,
            "adx": 0.0,
            "bb_position": "middle",
            "direction": "neutral",
            "ema50": 0.0,
            "ema200": 0.0,
            "close": 0.0,
        }
