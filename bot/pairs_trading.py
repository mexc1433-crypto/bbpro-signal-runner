"""
pairs_trading.py — Statistical Arbitrage / Pairs Trading Strategy
===================================================================
Implements statistical arbitrage between highly correlated asset pairs
(e.g., XAUUSD vs XAGUSD, EURUSD vs GBPUSD, USDJPY vs EURJPY).

Strategy Logic:
1. Calculates rolling correlation over lookback window (default 50 bars).
   - Skips pairs with correlation < 0.7.
2. Normalizes close price series (Price / Price[0] over lookback window).
3. Computes the spread = Normalized Price A - Normalized Price B.
4. Calculates the z-score of the spread: z = (spread[-1] - mean(spread)) / std(spread).
5. Signal Rules:
   - z-score > +2.0: Sell outperformer A, Buy underperformer B (mean reversion).
   - z-score < -2.0: Buy underperformer A, Sell outperformer B (mean reversion).
   - |z-score| < 0.2: Neutral / Signal exit as spread returns to mean 0.
6. Confidence: base 55 + (|z-score| - 2) * 10, capped at 85.
"""

import asyncio
import logging
import numpy as np
from typing import Dict, Any, List, Optional, Tuple, Union

try:
    from config import TradeDirection, BotConfig
except ImportError:
    try:
        from .config import TradeDirection, BotConfig
    except ImportError:
        class TradeDirection:
            BUY = "buy"
            SELL = "sell"
        BotConfig = None

logger = logging.getLogger(__name__)


def _extract_closes(bars: Any) -> np.ndarray:
    """Safely extracts close prices as NumPy float array from various input structures."""
    if bars is None:
        return np.array([], dtype=float)
    if isinstance(bars, np.ndarray):
        if bars.ndim == 2 and bars.shape[1] >= 4:
            return bars[:, 3].astype(float)
        return bars.astype(float)
    if not bars:
        return np.array([], dtype=float)

    first = bars[0]
    if hasattr(first, "close"):
        return np.array([getattr(b, "close", 0.0) for b in bars], dtype=float)
    elif isinstance(first, dict):
        return np.array([b.get("close", 0.0) for b in bars], dtype=float)
    else:
        try:
            return np.array([float(b) for b in bars], dtype=float)
        except (ValueError, TypeError):
            return np.array([], dtype=float)


class PairsTradingStrategy:
    """
    Pairs Trading / Statistical Arbitrage Strategy.

    Monitors pairs of correlated symbols, tracks normalized price spread z-score,
    and generates mean-reversion trading signals when spreads diverge significantly.
    """

    DEFAULT_PAIRS: List[List[str]] = [
        ["XAUUSD", "XAGUSD"],
        ["EURUSD", "GBPUSD"],
        ["USDJPY", "EURJPY"],
    ]

    def __init__(
        self,
        name: str = "pairs_trading",
        client: Optional[Any] = None,
        pairs: Optional[List[List[str]]] = None,
    ):
        """
        Initialize PairsTradingStrategy.

        Args:
            name: Strategy name identifier.
            client: Optional cTrader / market data client for fetching bars of pair symbols.
            pairs: Optional list of correlated symbol pairs, e.g. [["XAUUSD", "XAGUSD"], ...].
        """
        self.name = name
        self.client = client
        self.pairs = pairs or self.DEFAULT_PAIRS

    def compute_correlation(
        self, closes_a: np.ndarray, closes_b: np.ndarray, lookback: int = 50
    ) -> float:
        """
        Calculate rolling Pearson correlation between two close price series over lookback.

        Args:
            closes_a: Close prices array for symbol A.
            closes_b: Close prices array for symbol B.
            lookback: Rolling window size (default 50).

        Returns:
            Pearson correlation coefficient between -1.0 and +1.0.
        """
        if len(closes_a) < 10 or len(closes_b) < 10:
            return 0.0

        min_len = min(len(closes_a), len(closes_b), lookback)
        a = closes_a[-min_len:]
        b = closes_b[-min_len:]

        # Returns-based Pearson correlation
        ret_a = np.diff(a) / a[:-1]
        ret_b = np.diff(b) / b[:-1]

        if len(ret_a) >= 5 and np.std(ret_a) > 0 and np.std(ret_b) > 0:
            corr = np.corrcoef(ret_a, ret_b)[0, 1]
            if not np.isnan(corr):
                return float(corr)

        # Fallback to price series correlation
        std_a = np.std(a)
        std_b = np.std(b)
        if std_a > 0 and std_b > 0:
            corr = np.corrcoef(a, b)[0, 1]
            if not np.isnan(corr):
                return float(corr)

        return 0.0

    def calculate_zscore(
        self, closes_a: np.ndarray, closes_b: np.ndarray, lookback: int = 50
    ) -> Tuple[float, float, float]:
        """
        Calculate z-score of the spread between normalized prices of symbol A and B.

        Normalized price = price / price[0] over the lookback window.
        Spread = Normalized A - Normalized B.

        Args:
            closes_a: Close prices array for symbol A.
            closes_b: Close prices array for symbol B.
            lookback: Rolling window size (default 50).

        Returns:
            Tuple of (z_score, latest_spread, spread_std)
        """
        if len(closes_a) < lookback or len(closes_b) < lookback:
            return 0.0, 0.0, 0.0

        a = closes_a[-lookback:]
        b = closes_b[-lookback:]

        if a[0] == 0 or b[0] == 0:
            return 0.0, 0.0, 0.0

        # Normalized price series
        norm_a = a / a[0]
        norm_b = b / b[0]

        # Spread series (Normalized A - Normalized B)
        spread = norm_a - norm_b
        mean_s = float(np.mean(spread))
        std_s = float(np.std(spread))

        if std_s == 0.0 or np.isnan(std_s):
            return 0.0, float(spread[-1]), 0.0

        z_score = (float(spread[-1]) - mean_s) / std_s
        return float(z_score), float(spread[-1]), std_s

    def _get_closes_for_symbol(
        self,
        target_symbol: str,
        bars: Any,
        current_symbol: Optional[str],
        cfg: Optional[BotConfig],
        indicators_dict: Optional[Dict[str, Any]],
    ) -> np.ndarray:
        """Helper to fetch or extract close prices for target_symbol."""
        target_upper = target_symbol.upper()

        # 1. If target matches current bar symbol
        if current_symbol and current_symbol.upper() == target_upper and bars is not None:
            closes = _extract_closes(bars)
            if len(closes) > 0:
                return closes

        # 2. Check indicators_dict caches
        if indicators_dict and isinstance(indicators_dict, dict):
            closes_map = indicators_dict.get("closes_map") or indicators_dict.get("all_closes")
            if closes_map and isinstance(closes_map, dict) and target_upper in closes_map:
                return _extract_closes(closes_map[target_upper])

            bars_map = indicators_dict.get("bars_map") or indicators_dict.get("all_bars")
            if bars_map and isinstance(bars_map, dict) and target_upper in bars_map:
                return _extract_closes(bars_map[target_upper])

        # 3. Use client to fetch bars
        if self.client is not None:
            tf = getattr(cfg, "timeframe", "m30") if cfg else "m30"
            lookback = getattr(cfg, "pairs_trading_lookback", 50) if cfg else 50
            count = max(lookback * 2, 100)
            fetched = self._fetch_bars_from_client(target_upper, tf, count)
            if fetched:
                return _extract_closes(fetched)

        # 4. Fallback: if current bars are provided and target not explicitly specified
        if bars is not None:
            return _extract_closes(bars)

        return np.array([], dtype=float)

    def _fetch_bars_from_client(
        self, symbol: str, timeframe: str = "m30", count: int = 200
    ) -> List[Any]:
        """Safely fetch bars from market data client in both sync and async environments."""
        if self.client is None:
            return []

        try:
            if hasattr(self.client, "get_recent_bars"):
                fn = getattr(self.client, "get_recent_bars")
                import inspect
                if inspect.iscoroutinefunction(fn):
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    if loop is not None and loop.is_running():
                        import concurrent.futures
                        def _run_in_new_loop():
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                return new_loop.run_until_complete(fn(symbol, timeframe, count))
                            finally:
                                new_loop.close()
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                            return pool.submit(_run_in_new_loop).result(timeout=10)
                    else:
                        return asyncio.run(fn(symbol, timeframe, count))
                else:
                    return fn(symbol, timeframe, count)

            # Check alternative method names
            for method in ["get_bars", "get_history", "get_recent_bars_sync"]:
                if hasattr(self.client, method):
                    return getattr(self.client, method)(symbol, timeframe, count)

        except Exception as e:
            logger.warning("PairsTradingStrategy: Exception fetching bars for %s: %s", symbol, e)

        return []

    def analyze(
        self,
        bars: Any,
        cfg: Optional[BotConfig] = None,
        indicators_dict: Optional[Dict[str, Any]] = None,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze statistical arbitrage / pairs trading setup.

        Args:
            bars: Bars for the primary symbol (List[Bar], List[dict], or np.ndarray).
            cfg: BotConfig instance with strategy parameters.
            indicators_dict: Optional dictionary with pre-computed indicators or closes map.
            symbol: Optional explicit symbol name being analyzed.

        Returns:
            Dict containing: 'strategy', 'signal', 'confidence', 'reason', 'z_score', 'correlation', 'pair'
        """
        try:
            cfg = cfg or BotConfig()

            # Config settings
            lookback = getattr(cfg, "pairs_trading_lookback", 50) if cfg else 50
            min_corr = getattr(cfg, "pairs_trading_correlation_threshold", 0.7) if cfg else 0.7
            z_thresh = getattr(cfg, "pairs_trading_zscore_threshold", 2.0) if cfg else 2.0
            configured_pairs = getattr(cfg, "pairs_trading_symbols", None) or self.pairs

            # Determine primary symbol name
            primary_symbol = symbol
            if not primary_symbol and cfg and getattr(cfg, "symbol", None):
                primary_symbol = cfg.symbol
            if not primary_symbol and bars is not None and not isinstance(bars, np.ndarray) and len(bars) > 0:
                primary_symbol = getattr(bars[0], "symbol", None) or (bars[0].get("symbol") if isinstance(bars[0], dict) else None)

            # Filter active pairs matching primary_symbol if specified
            active_pairs = []
            if primary_symbol:
                ps_upper = primary_symbol.upper()
                for p in configured_pairs:
                    if len(p) >= 2 and (p[0].upper() == ps_upper or p[1].upper() == ps_upper):
                        active_pairs.append(p)

            if not active_pairs:
                active_pairs = configured_pairs

            best_result = None
            max_confidence = -1.0

            for pair in active_pairs:
                if len(pair) < 2:
                    continue

                sym_a, sym_b = pair[0].upper(), pair[1].upper()

                # Fetch close prices for symbol A and symbol B
                closes_a = self._get_closes_for_symbol(sym_a, bars, primary_symbol, cfg, indicators_dict)
                closes_b = self._get_closes_for_symbol(sym_b, bars, primary_symbol, cfg, indicators_dict)

                if len(closes_a) < lookback or len(closes_b) < lookback:
                    reason = f"Insufficient bars ({len(closes_a)}/{len(closes_b)}) for pair {sym_a}/{sym_b} (need {lookback})"
                    res = {
                        "strategy": self.name,
                        "signal": None,
                        "confidence": 0.0,
                        "reason": reason,
                        "z_score": 0.0,
                        "correlation": 0.0,
                        "pair": [sym_a, sym_b],
                    }
                    if best_result is None:
                        best_result = res
                    continue

                # Compute rolling correlation
                corr = self.compute_correlation(closes_a, closes_b, lookback)

                if abs(corr) < min_corr:
                    reason = f"Pair {sym_a}/{sym_b} correlation ({corr:.2f}) below threshold ({min_corr:.2f})"
                    res = {
                        "strategy": self.name,
                        "signal": None,
                        "confidence": 0.0,
                        "reason": reason,
                        "z_score": 0.0,
                        "correlation": round(corr, 4),
                        "pair": [sym_a, sym_b],
                    }
                    if best_result is None:
                        best_result = res
                    continue

                # Calculate spread z-score
                z_score, spread_val, spread_std = self.calculate_zscore(closes_a, closes_b, lookback)

                # Determine which symbol is being analyzed as target
                target_is_a = True
                if primary_symbol and primary_symbol.upper() == sym_b:
                    target_is_a = False

                signal = None
                confidence = 0.0
                reason = ""

                # Signal Conditions
                if z_score > z_thresh:
                    # Normalized A > Normalized B: A outperformed, B underperformed
                    if target_is_a:
                        # Target is A -> Sell outperformer A
                        signal = TradeDirection.SELL
                        reason = (
                            f"Pairs Trading ({sym_a}/{sym_b}): z-score {z_score:.2f} > {z_thresh:.1f} "
                            f"(corr {corr:.2f}). {sym_a} outperforming {sym_b} -> SELL {sym_a} / BUY {sym_b}"
                        )
                    else:
                        # Target is B -> Buy underperformer B
                        signal = TradeDirection.BUY
                        reason = (
                            f"Pairs Trading ({sym_a}/{sym_b}): z-score {z_score:.2f} > {z_thresh:.1f} "
                            f"(corr {corr:.2f}). {sym_b} underperforming {sym_a} -> BUY {sym_b} / SELL {sym_a}"
                        )

                    # Confidence formula: base 55 + (z-score - 2) * 10, capped at 85
                    confidence = min(85.0, max(55.0, 55.0 + (z_score - z_thresh) * 10.0))

                elif z_score < -z_thresh:
                    # Normalized A < Normalized B: A underperformed, B outperformed
                    if target_is_a:
                        # Target is A -> Buy underperformer A
                        signal = TradeDirection.BUY
                        reason = (
                            f"Pairs Trading ({sym_a}/{sym_b}): z-score {z_score:.2f} < -{z_thresh:.1f} "
                            f"(corr {corr:.2f}). {sym_a} underperforming {sym_b} -> BUY {sym_a} / SELL {sym_b}"
                        )
                    else:
                        # Target is B -> Sell outperformer B
                        signal = TradeDirection.SELL
                        reason = (
                            f"Pairs Trading ({sym_a}/{sym_b}): z-score {z_score:.2f} < -{z_thresh:.1f} "
                            f"(corr {corr:.2f}). {sym_b} outperforming {sym_a} -> SELL {sym_b} / BUY {sym_a}"
                        )

                    # Confidence formula: base 55 + (|z-score| - 2) * 10, capped at 85
                    confidence = min(85.0, max(55.0, 55.0 + (abs(z_score) - z_thresh) * 10.0))

                elif abs(z_score) < 0.2:
                    # Signal exit when z-score returns to near 0
                    signal = None
                    confidence = 0.0
                    reason = (
                        f"Pairs Trading ({sym_a}/{sym_b}): z-score {z_score:.2f} returned to mean 0 "
                        f"(corr {corr:.2f}). Signal exit."
                    )

                else:
                    signal = None
                    confidence = 0.0
                    reason = (
                        f"Pairs Trading ({sym_a}/{sym_b}): z-score {z_score:.2f} within normal range "
                        f"[-{z_thresh:.1f}, {z_thresh:.1f}] (corr {corr:.2f})"
                    )

                res = {
                    "strategy": self.name,
                    "signal": signal,
                    "confidence": round(float(confidence), 2),
                    "reason": reason,
                    "z_score": round(float(z_score), 4),
                    "correlation": round(float(corr), 4),
                    "pair": [sym_a, sym_b],
                }

                if signal is not None and confidence > max_confidence:
                    max_confidence = confidence
                    best_result = res
                elif best_result is None:
                    best_result = res

            if best_result is None:
                best_result = {
                    "strategy": self.name,
                    "signal": None,
                    "confidence": 0.0,
                    "reason": "No pair data available",
                    "z_score": 0.0,
                    "correlation": 0.0,
                    "pair": [],
                }

            return best_result

        except Exception as e:
            logger.error("PairsTradingStrategy error: %s", e, exc_info=True)
            return {
                "strategy": self.name,
                "signal": None,
                "confidence": 0.0,
                "reason": f"Error in pairs_trading strategy: {e}",
                "z_score": 0.0,
                "correlation": 0.0,
                "pair": [],
            }

    async def analyze_async(
        self,
        bars: Any,
        cfg: Optional[BotConfig] = None,
        indicators_dict: Optional[Dict[str, Any]] = None,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Async variant of analyze for execution within asyncio loops."""
        return self.analyze(bars, cfg, indicators_dict, symbol)

    def run(self, bars: Any, cfg: Optional[BotConfig] = None) -> Dict[str, Any]:
        """Convenience wrapper method."""
        return self.analyze(bars, cfg)
