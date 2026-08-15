"""
correlation.py — Currency Correlation Analysis
================================================
Confirms or denies signals based on known currency pair correlations.
Reduces false signals by checking if correlated pairs agree.

Known correlations:
  EURUSD <-> GBPUSD:  +0.88 (strong positive)
  EURUSD <-> USDJPY:   -0.65 (moderate negative)
  XAUUSD <-> EURUSD:   +0.55 (moderate positive)
  USDJPY <-> USDCAD:   -0.58 (moderate negative)
  EURJPY <-> EURUSD:   +0.73 (moderate positive)
"""

import numpy as np
from typing import Dict, List, Optional


# Known correlation pairs
CORRELATION_MAP = {
    "EURUSD": {"GBPUSD": 0.88, "USDJPY": -0.65, "XAUUSD": 0.55, "EURJPY": 0.73},
    "GBPUSD": {"EURUSD": 0.88, "USDJPY": -0.55, "XAUUSD": 0.45},
    "USDJPY": {"EURUSD": -0.65, "USDCAD": -0.58, "GBPUSD": -0.55},
    "EURJPY": {"EURUSD": 0.73, "GBPUSD": 0.60, "USDJPY": 0.55},
    "USDCAD": {"USDJPY": -0.58, "EURUSD": -0.45, "XAUUSD": 0.40},
    "XAUUSD": {"EURUSD": 0.55, "GBPUSD": 0.45, "USDCAD": 0.40},
}


class CorrelationAnalyzer:
    """
    Currency Correlation Analyzer.
    Confirms signals by checking if correlated pairs move in the expected direction.
    """

    def __init__(self, window: int = 50, min_correlation: float = 0.5):
        self.window = window
        self.min_correlation = min_correlation

    def compute_correlation(self, closes_a: np.ndarray, closes_b: np.ndarray,
                            window: int = None) -> float:
        """Compute rolling Pearson correlation between two close arrays."""
        window = window or self.window
        min_len = min(len(closes_a), len(closes_b), window)

        if min_len < 10:
            return 0.0

        a = closes_a[-min_len:]
        b = closes_b[-min_len:]

        # Compute returns
        ret_a = np.diff(a) / a[:-1]
        ret_b = np.diff(b) / b[:-1]

        if len(ret_a) < 5 or np.std(ret_a) == 0 or np.std(ret_b) == 0:
            return 0.0

        corr = np.corrcoef(ret_a, ret_b)[0, 1]
        return float(corr) if not np.isnan(corr) else 0.0

    def get_correlated_pairs(self, symbol: str) -> List[str]:
        """Return symbols known to correlate with the given symbol."""
        return list(CORRELATION_MAP.get(symbol.upper(), {}).keys())

    def analyze(self, closes_map: Dict[str, np.ndarray], symbol: str,
                signal: str) -> Dict:
        """
        Analyze if correlated pairs confirm the signal.

        Args:
            closes_map: Dict of symbol -> close prices array
            symbol: The symbol being analyzed
            signal: 'buy' or 'sell'

        Returns:
            {confirmed: bool, confidence_adjustment: float, reason: str}
        """
        symbol = symbol.upper()
        signal = signal.lower()

        correlated = CORRELATION_MAP.get(symbol, {})
        if not correlated or not closes_map:
            return {"confirmed": True, "confidence_adjustment": 0.0,
                    "reason": "No correlated pairs available"}

        confirmations = 0
        disagreements = 0
        total_checked = 0
        details = []

        for other_symbol, expected_corr in correlated.items():
            if other_symbol not in closes_map:
                continue

            other_closes = closes_map[other_symbol]
            if len(other_closes) < 20:
                continue

            # Check if other pair is trending in expected direction
            # Look at last 5 bars for short-term trend
            if len(other_closes) < 5:
                continue

            recent_change = (other_closes[-1] - other_closes[-5]) / other_closes[-5]

            # Expected direction based on correlation
            # Positive correlation: same direction
            # Negative correlation: opposite direction
            if expected_corr > 0:
                expected_direction = signal  # buy -> up, sell -> down
            else:
                expected_direction = "sell" if signal == "buy" else "buy"

            # Check if other pair moved in expected direction
            if expected_direction == "buy" and recent_change > 0:
                confirmations += 1
                details.append(f"{other_symbol} trending up ✓")
            elif expected_direction == "sell" and recent_change < 0:
                confirmations += 1
                details.append(f"{other_symbol} trending down ✓")
            else:
                disagreements += 1
                details.append(f"{other_symbol} diverging ✗")

            total_checked += 1

        if total_checked == 0:
            return {"confirmed": True, "confidence_adjustment": 0.0,
                    "reason": "No correlated data available"}

        # Confidence adjustment
        ratio = confirmations / total_checked
        if ratio >= 0.75:
            adjustment = 5.0 + (ratio - 0.75) * 20  # 5-10% boost
            confirmed = True
        elif ratio >= 0.5:
            adjustment = 0.0
            confirmed = True
        else:
            adjustment = -10.0  # -10% penalty for disagreement
            confirmed = False

        reason = f"Correlation: {confirmations}/{total_checked} confirm, {disagreements} disagree — {'; '.join(details)}"

        return {
            "confirmed": confirmed,
            "confidence_adjustment": round(adjustment, 2),
            "reason": reason,
        }
