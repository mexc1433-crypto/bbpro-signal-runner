"""
session_awareness.py
====================
BBPro Signal Bot — Session-Aware Strategy Weighting & DXY Filter

This module provides market session awareness based on UTC hours and adjusts
strategy weights, confidence bonuses, and volatility indicators accordingly.
It also includes a Dollar Index (DXY) filter fetching real-time data from Yahoo
Finance ('DX-Y.NYB') to filter signals on USD trading pairs when DXY is trending.

Trading Sessions (UTC):
  - Asian Session (00:00-07:00 UTC): Favor range/mean-reversion strategies
  - London Session (07:00-12:00 UTC): Favor breakout strategies
  - New York Session (12:00-17:00 UTC): Favor trend strategies
  - London/NY Overlap (12:00-17:00 UTC): Highest volatility, all strategies active with bonus confidence
  - Off-hours (17:00-00:00 UTC): Reduced confidence, favor scalping and mean reversion
"""

import json
import logging
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union
import numpy as np

logger = logging.getLogger(__name__)


class SessionAwareness:
    """
    Session Awareness and Strategy Weighting System with DXY Filter.
    """

    def __init__(self, dxy_cache_ttl: int = 300):
        """
        Initialize SessionAwareness with DXY cache TTL in seconds (default 5 minutes).
        """
        self.dxy_symbol = "DX-Y.NYB"
        self.dxy_cache_ttl = dxy_cache_ttl
        self._dxy_cache: Optional[Dict[str, Any]] = None
        self._dxy_cache_time: float = 0.0

    # ------------------------------------------------------------------
    # SESSION DETECTION
    # ------------------------------------------------------------------
    def get_active_session(
        self, dt: Optional[datetime] = None, timestamp: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Detect current trading session based on UTC hour.

        Returns:
            Dict containing session name, hour, weight adjustments, bonus, and volatility flag.
        """
        if timestamp is not None:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif dt is None:
            dt = datetime.now(timezone.utc)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        hour = dt.hour

        # Detect session name and description
        if 0 <= hour < 7:
            session_name = "Asian"
            description = "Asian Session — Range/mean-reversion market"
        elif 7 <= hour < 12:
            session_name = "London"
            description = "London Session — High volume breakout & momentum window"
        elif 12 <= hour < 17:
            session_name = "London/NY Overlap"
            description = "London/NY Overlap — Peak global market liquidity & volatility"
        else:
            session_name = "Off-hours"
            description = "Off-hours — Low liquidity, favor scalping & mean reversion"

        weights = self.get_strategy_weights(session_name)
        bonus = self.get_session_bonus(session_name)
        high_vol = self.is_high_volatility_session(session_name)

        return {
            "session": session_name,
            "name": session_name,
            "hour": hour,
            "dt": dt.isoformat(),
            "timestamp": dt.timestamp(),
            "description": description,
            "high_volatility": high_vol,
            "bonus": bonus,
            "weight_adjustments": weights,
        }

    # ------------------------------------------------------------------
    # STRATEGY WEIGHTS
    # ------------------------------------------------------------------
    def _normalize_session_name(self, session: Union[str, Dict[str, Any]]) -> str:
        """Helper to normalize session input from string or dict."""
        if isinstance(session, dict):
            raw = str(session.get("session") or session.get("name") or "")
        elif session is not None:
            raw = str(session)
        else:
            raw = ""

        s = raw.lower().strip()
        if "overlap" in s:
            return "London/NY Overlap"
        elif "asian" in s or "asia" in s:
            return "Asian"
        elif "london" in s:
            return "London"
        elif "new york" in s or "newyork" in s or "ny" in s:
            return "New York"
        elif "off" in s:
            return "Off-hours"
        else:
            return "Off-hours"

    def get_strategy_weights(self, session: Union[str, Dict[str, Any]]) -> Dict[str, float]:
        """
        Get strategy weight multipliers (bounded 0.5 to 1.5) for the given session.

        Args:
            session: Session name string or session dict from get_active_session()

        Returns:
            Dict mapping strategy names to weight multipliers.
        """
        norm_session = self._normalize_session_name(session)

        if norm_session == "Asian":
            # Favor range / mean-reversion strategies
            weights = {
                "bb_mean_reversion": 1.4,
                "rsi_reversal": 1.4,
                "stochastic_reversal": 1.4,
                "sr_bounce": 1.3,
                "scalping": 1.2,
                "pairs_trading": 1.1,
                "volume_profile": 0.9,
                "ict_killzones": 0.8,
                "smc": 0.7,
                "fvg": 0.7,
                "breakout": 0.6,
                "ema_crossover": 0.6,
                "trend_adx": 0.6,
                "macd_crossover": 0.6,
                "news_trading": 0.6,
            }
        elif norm_session == "London":
            # Favor breakout strategies
            weights = {
                "breakout": 1.4,
                "macd_crossover": 1.3,
                "trend_adx": 1.4,
                "fvg": 1.3,
                "ict_killzones": 1.4,
                "smc": 1.3,
                "volume_profile": 1.2,
                "ema_crossover": 1.2,
                "news_trading": 1.2,
                "sr_bounce": 1.0,
                "pairs_trading": 0.9,
                "rsi_reversal": 0.8,
                "scalping": 0.8,
                "bb_mean_reversion": 0.7,
                "stochastic_reversal": 0.7,
            }
        elif norm_session == "New York":
            # Favor trend strategies
            weights = {
                "ema_crossover": 1.4,
                "trend_adx": 1.4,
                "smc": 1.5,
                "breakout": 1.3,
                "macd_crossover": 1.3,
                "ict_killzones": 1.3,
                "fvg": 1.3,
                "news_trading": 1.3,
                "volume_profile": 1.2,
                "sr_bounce": 1.0,
                "pairs_trading": 0.9,
                "rsi_reversal": 0.8,
                "scalping": 0.8,
                "bb_mean_reversion": 0.7,
                "stochastic_reversal": 0.7,
            }
        elif norm_session == "London/NY Overlap":
            # Highest volatility, all strategies active with bonus confidence
            weights = {
                "smc": 1.5,
                "ict_killzones": 1.5,
                "breakout": 1.4,
                "ema_crossover": 1.4,
                "trend_adx": 1.4,
                "fvg": 1.4,
                "macd_crossover": 1.3,
                "volume_profile": 1.3,
                "news_trading": 1.3,
                "bb_mean_reversion": 1.2,
                "rsi_reversal": 1.2,
                "stochastic_reversal": 1.2,
                "scalping": 1.2,
                "sr_bounce": 1.2,
                "pairs_trading": 1.2,
            }
        else:  # Off-hours
            # Reduced confidence, favor scalping and mean reversion
            weights = {
                "scalping": 1.3,
                "bb_mean_reversion": 1.2,
                "rsi_reversal": 1.2,
                "stochastic_reversal": 1.2,
                "sr_bounce": 1.1,
                "pairs_trading": 1.1,
                "volume_profile": 0.7,
                "smc": 0.6,
                "fvg": 0.6,
                "breakout": 0.5,
                "ema_crossover": 0.5,
                "trend_adx": 0.5,
                "macd_crossover": 0.5,
                "ict_killzones": 0.5,
                "news_trading": 0.5,
            }

        # Enforce strict bounds (0.5 to 1.5)
        return {k: max(0.5, min(1.5, float(v))) for k, v in weights.items()}

    # ------------------------------------------------------------------
    # SESSION BONUS & VOLATILITY
    # ------------------------------------------------------------------
    def get_session_bonus(self, session: Union[str, Dict[str, Any]]) -> float:
        """
        Get confidence bonus (0.0 to 15.0) for the given session.
        """
        norm_session = self._normalize_session_name(session)

        if norm_session == "London/NY Overlap":
            return 15.0
        elif norm_session in ("London", "New York"):
            return 10.0
        elif norm_session == "Asian":
            return 5.0
        else:  # Off-hours
            return 0.0

    def is_high_volatility_session(self, session: Union[str, Dict[str, Any]]) -> bool:
        """
        Check if current session is classified as high volatility.
        """
        norm_session = self._normalize_session_name(session)
        return norm_session in ("London/NY Overlap", "London", "New York")

    # ------------------------------------------------------------------
    # DXY (DOLLAR INDEX) FILTER
    # ------------------------------------------------------------------
    def get_dxy_status(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Fetch DXY data from Yahoo Finance ('DX-Y.NYB') and analyze trend status.

        Returns:
            Dict with price, 24h change %, regime, is_trending, is_ranging, trend_direction.
        """
        now = time.time()
        if (
            use_cache
            and self._dxy_cache is not None
            and (now - self._dxy_cache_time) < self.dxy_cache_ttl
        ):
            return self._dxy_cache

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{self.dxy_symbol}?range=5d&interval=1h"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        closes: List[float] = []
        error_msg: Optional[str] = None

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result = data.get("chart", {}).get("result", [])[0]
                quote = result.get("indicators", {}).get("quote", [])[0]
                raw_closes = quote.get("close", [])
                closes = [float(c) for c in raw_closes if c is not None]
        except Exception as e:
            logger.warning("Failed to fetch DXY data from Yahoo Finance: %s", e)
            error_msg = str(e)

        # Process market data or fallback if empty
        if not closes or len(closes) < 10:
            result_dict = {
                "symbol": self.dxy_symbol,
                "price": closes[-1] if closes else 100.0,
                "change_24h_pct": 0.0,
                "regime": "ranging",
                "is_trending": False,
                "is_ranging": True,
                "trend_direction": "neutral",
                "sma20": closes[-1] if closes else 100.0,
                "sma50": closes[-1] if closes else 100.0,
                "timestamp": now,
                "error": error_msg or "Insufficient data",
            }
            self._dxy_cache = result_dict
            self._dxy_cache_time = now
            return result_dict

        curr_price = closes[-1]
        prev_24h = closes[-24] if len(closes) >= 24 else closes[0]
        change_24h_pct = ((curr_price - prev_24h) / prev_24h) * 100.0

        prev_5b = closes[-5] if len(closes) >= 5 else closes[0]
        change_5b_pct = ((curr_price - prev_5b) / prev_5b) * 100.0

        # Calculate moving averages
        sma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else curr_price
        sma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else sma20

        # Determine regime and trend direction
        is_bullish = (curr_price > sma20 >= sma50) and (change_24h_pct > 0.10 or change_5b_pct > 0.05)
        is_bearish = (curr_price < sma20 <= sma50) and (change_24h_pct < -0.10 or change_5b_pct < -0.05)

        if is_bullish:
            regime = "trending_bullish"
            trend_direction = "bullish"
            is_trending = True
            is_ranging = False
        elif is_bearish:
            regime = "trending_bearish"
            trend_direction = "bearish"
            is_trending = True
            is_ranging = False
        else:
            regime = "ranging"
            trend_direction = "neutral"
            is_trending = False
            is_ranging = True

        result_dict = {
            "symbol": self.dxy_symbol,
            "price": curr_price,
            "change_24h_pct": round(change_24h_pct, 3),
            "regime": regime,
            "is_trending": is_trending,
            "is_ranging": is_ranging,
            "trend_direction": trend_direction,
            "sma20": round(sma20, 3),
            "sma50": round(sma50, 3),
            "timestamp": now,
            "error": None,
        }

        self._dxy_cache = result_dict
        self._dxy_cache_time = now
        return result_dict

    def is_dxy_trending(self, dxy_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Check if DXY is currently in a trending state.
        """
        if dxy_data is None:
            dxy_data = self.get_dxy_status()
        return dxy_data.get("is_trending", False)

    def should_filter_usd_pair(
        self,
        symbol: str,
        direction: str = "buy",
        dxy_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Determine if USD pairs should be filtered based on DXY trend.

        Args:
            symbol: Trading symbol (e.g. 'EURUSD', 'USDJPY', 'XAUUSD', 'GBPUSD')
            direction: Trade direction ('buy' or 'sell')
            dxy_data: Optional pre-fetched DXY status dict

        Returns:
            Dict containing 'filtered' (bool), 'reason' (str), and DXY status context.
        """
        clean_symbol = symbol.upper().replace("/", "").replace("-", "")
        clean_dir = direction.lower().strip()

        if "USD" not in clean_symbol:
            return {
                "filtered": False,
                "reason": f"Symbol {symbol} is not a USD pair",
                "symbol": symbol,
                "direction": direction,
                "dxy_regime": "n/a",
            }

        if dxy_data is None:
            dxy_data = self.get_dxy_status()

        regime = dxy_data.get("regime", "ranging")
        trend_dir = dxy_data.get("trend_direction", "neutral")
        is_trending = dxy_data.get("is_trending", False)

        if not is_trending or regime == "ranging":
            return {
                "filtered": False,
                "reason": "DXY is ranging — USD pairs allowed",
                "symbol": symbol,
                "direction": direction,
                "dxy_regime": regime,
                "dxy_trend": trend_dir,
            }

        # Check whether symbol is USD Base (USDJPY, USDCAD, USDCHF) or USD Quote (EURUSD, GBPUSD, XAUUSD)
        is_usd_base = clean_symbol.startswith("USD")

        # Direction impact on USD exposure:
        # USD Base (e.g., USDJPY): BUY = Buying USD, SELL = Selling USD
        # USD Quote (e.g., EURUSD): BUY = Selling USD, SELL = Buying USD
        buying_usd = (is_usd_base and clean_dir == "buy") or (not is_usd_base and clean_dir == "sell")

        if regime == "trending_bullish":
            if not buying_usd:
                return {
                    "filtered": True,
                    "reason": f"Filtering {direction.upper()} {symbol}: Opposes strong USD bullish trend (DXY trending UP)",
                    "symbol": symbol,
                    "direction": direction,
                    "dxy_regime": regime,
                    "dxy_trend": trend_dir,
                }
            else:
                return {
                    "filtered": False,
                    "reason": f"Allowed {direction.upper()} {symbol}: Aligns with strong USD bullish trend",
                    "symbol": symbol,
                    "direction": direction,
                    "dxy_regime": regime,
                    "dxy_trend": trend_dir,
                }
        elif regime == "trending_bearish":
            if buying_usd:
                return {
                    "filtered": True,
                    "reason": f"Filtering {direction.upper()} {symbol}: Opposes strong USD bearish trend (DXY trending DOWN)",
                    "symbol": symbol,
                    "direction": direction,
                    "dxy_regime": regime,
                    "dxy_trend": trend_dir,
                }
            else:
                return {
                    "filtered": False,
                    "reason": f"Allowed {direction.upper()} {symbol}: Aligns with strong USD bearish trend",
                    "symbol": symbol,
                    "direction": direction,
                    "dxy_regime": regime,
                    "dxy_trend": trend_dir,
                }

        return {
            "filtered": False,
            "reason": "DXY trend filter passed",
            "symbol": symbol,
            "direction": direction,
            "dxy_regime": regime,
        }

    # Method Aliases for caller compatibility
    filter_usd_pair = should_filter_usd_pair
    check_dxy_filter = should_filter_usd_pair
