"""
smc.py — Smart Money Concepts (SMC) Module
=============================================
Institutional-grade analysis: Order Blocks, Fair Value Gaps,
Liquidity Zones, Break of Structure (BOS), Change of Character (CHoCH).

Based on ICT concepts and the joshyattridge/smart-money-concepts library.
Pure Python implementation — no external dependencies needed.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SMCSignal:
    """Result from SMC analysis."""
    signal: Optional[str]  # "buy", "sell", None
    confidence: float      # 0-100
    reason: str
    components: Dict       # detailed breakdown


class SmartMoneyConcepts:
    """
    Smart Money Concepts analyzer.
    Detects institutional order flow patterns.
    """

    def __init__(self, swing_length: int = 10, range_percent: float = 0.01,
                 body_multiplier: float = 1.5, lookback: int = 10):
        self.swing_length = swing_length
        self.range_percent = range_percent
        self.body_multiplier = body_multiplier
        self.lookback = lookback

    # ------------------------------------------------------------------
    # SWING HIGHS AND LOWS
    # ------------------------------------------------------------------
    def find_swings(self, highs: np.ndarray, lows: np.ndarray) -> List[dict]:
        """Find swing highs and lows."""
        swings = []
        n = len(highs)
        sl = self.swing_length

        for i in range(sl, n - sl):
            # Swing high
            is_high = True
            for j in range(i - sl, i + sl + 1):
                if j != i and highs[j] >= highs[i]:
                    is_high = False
                    break
            if is_high:
                swings.append({"index": i, "type": "high", "level": float(highs[i])})

            # Swing low
            is_low = True
            for j in range(i - sl, i + sl + 1):
                if j != i and lows[j] <= lows[i]:
                    is_low = False
                    break
            if is_low:
                swings.append({"index": i, "type": "low", "level": float(lows[i])})

        return swings

    # ------------------------------------------------------------------
    # BREAK OF STRUCTURE (BOS) & CHANGE OF CHARACTER (CHoCH)
    # ------------------------------------------------------------------
    def detect_bos_choch(self, highs: np.ndarray, lows: np.ndarray,
                          closes: np.ndarray, swings: List[dict]) -> Dict:
        """
        BOS = trend continuation (price breaks previous high in uptrend)
        CHoCH = trend reversal (price breaks structure in opposite direction)
        """
        if len(swings) < 3 or len(closes) < 5:
            return {"bos": None, "choch": None, "level": 0, "direction": "neutral"}

        # Get last few swing highs and lows
        swing_highs = [s for s in swings if s["type"] == "high"]
        swing_lows = [s for s in swings if s["type"] == "low"]

        if not swing_highs or not swing_lows:
            return {"bos": None, "choch": None, "level": 0, "direction": "neutral"}

        last_high = swing_highs[-1]
        last_low = swing_lows[-1]
        close_now = closes[-1]
        close_prev = closes[-2]

        bos = None
        choch = None
        direction = "neutral"

        # Determine current trend from last BOS
        # Bullish BOS: close breaks above last swing high
        if close_now > last_high["level"] and close_prev <= last_high["level"]:
            # Check if previous structure was bullish (BOS) or bearish (CHoCH)
            if len(swing_highs) >= 2 and last_high["index"] > swing_highs[-2]["index"]:
                bos = "bullish"
                direction = "buy"
            else:
                choch = "bullish"
                direction = "buy"

        # Bearish BOS: close breaks below last swing low
        elif close_now < last_low["level"] and close_prev >= last_low["level"]:
            if len(swing_lows) >= 2 and last_low["index"] > swing_lows[-2]["index"]:
                bos = "bearish"
                direction = "sell"
            else:
                choch = "bearish"
                direction = "sell"

        level = last_high["level"] if bos == "bullish" or choch == "bullish" else \
                last_low["level"] if bos == "bearish" or choch == "bearish" else 0

        return {
            "bos": bos,
            "choch": choch,
            "level": level,
            "direction": direction,
        }

    # ------------------------------------------------------------------
    # ORDER BLOCKS
    # ------------------------------------------------------------------
    def detect_order_blocks(self, highs: np.ndarray, lows: np.ndarray,
                             opens: np.ndarray, closes: np.ndarray,
                             volumes: np.ndarray,
                             swings: List[dict]) -> List[dict]:
        """
        Order Block = last opposite-colored candle before a strong move.
        Bullish OB: last bearish candle before a strong bullish move that breaks structure.
        Bearish OB: last bullish candle before a strong bearish move.
        """
        obs = []
        if len(closes) < 10:
            return obs

        # Calculate average body
        bodies = np.abs(closes - opens)
        avg_body = np.mean(bodies[-50:]) if len(bodies) >= 50 else np.mean(bodies)

        for i in range(3, len(closes) - 1):
            # Bullish OB: bearish candle at i-1, strong bullish move at i
            if closes[i-1] < opens[i-1] and closes[i] > opens[i]:
                body_i = abs(closes[i] - opens[i])
                if body_i > avg_body * self.body_multiplier:
                    # Check if it created a BOS
                    if any(s["type"] == "high" and s["index"] == i for s in swings):
                        ob = {
                            "type": "bullish",
                            "top": float(max(opens[i-1], closes[i-1])),
                            "bottom": float(min(opens[i-1], closes[i-1])),
                            "index": i - 1,
                            "volume": float(volumes[i-1] + volumes[i]) if len(volumes) > i else 0,
                        }
                        obs.append(ob)

            # Bearish OB: bullish candle at i-1, strong bearish move at i
            elif closes[i-1] > opens[i-1] and closes[i] < opens[i]:
                body_i = abs(closes[i] - opens[i])
                if body_i > avg_body * self.body_multiplier:
                    if any(s["type"] == "low" and s["index"] == i for s in swings):
                        ob = {
                            "type": "bearish",
                            "top": float(max(opens[i-1], closes[i-1])),
                            "bottom": float(min(opens[i-1], closes[i-1])),
                            "index": i - 1,
                            "volume": float(volumes[i-1] + volumes[i]) if len(volumes) > i else 0,
                        }
                        obs.append(ob)

        return obs[-5:]  # return last 5

    # ------------------------------------------------------------------
    # FAIR VALUE GAPS (FVG)
    # ------------------------------------------------------------------
    def detect_fvg(self, highs: np.ndarray, lows: np.ndarray,
                    opens: np.ndarray, closes: np.ndarray) -> List[dict]:
        """
        Fair Value Gap = 3-candle imbalance.
        Bullish FVG: candle1.high < candle3.low (gap up)
        Bearish FVG: candle1.low > candle3.high (gap down)
        """
        fvgs = []
        n = len(closes)

        # Calculate average body for momentum filter
        bodies = np.abs(closes - opens)
        avg_body = np.mean(bodies[-50:]) if len(bodies) >= 50 else np.mean(bodies)
        avg_body = max(avg_body, 0.0001)

        for i in range(2, n):
            first_high = highs[i-2]
            first_low = lows[i-2]
            middle_body = abs(closes[i-1] - opens[i-1])
            third_low = lows[i]
            third_high = highs[i]

            # Bullish FVG
            if third_low > first_high and middle_body > avg_body * self.body_multiplier:
                fvgs.append({
                    "type": "bullish",
                    "top": float(third_low),
                    "bottom": float(first_high),
                    "index": i,
                    "filled": False,
                })

            # Bearish FVG
            elif third_high < first_low and middle_body > avg_body * self.body_multiplier:
                fvgs.append({
                    "type": "bearish",
                    "top": float(first_low),
                    "bottom": float(third_high),
                    "index": i,
                    "filled": False,
                })

        # Check if FVGs were filled by later price action
        for fvg in fvgs:
            for j in range(fvg["index"] + 1, n):
                if fvg["type"] == "bullish":
                    if lows[j] <= fvg["bottom"]:
                        fvg["filled"] = True
                        break
                else:
                    if highs[j] >= fvg["top"]:
                        fvg["filled"] = True
                        break

        # Return unfilled FVGs (most relevant)
        unfilled = [f for f in fvgs if not f["filled"]]
        return unfilled[-5:]  # last 5 unfilled

    # ------------------------------------------------------------------
    # LIQUIDITY ZONES
    # ------------------------------------------------------------------
    def detect_liquidity(self, highs: np.ndarray, lows: np.ndarray,
                          swings: List[dict]) -> List[dict]:
        """
        Liquidity = multiple highs/lows within a small range.
        These are areas where stop orders cluster (targets for smart money).
        """
        if not swings:
            return []

        liquidity_zones = []
        swing_highs = [s for s in swings if s["type"] == "high"]
        swing_lows = [s for s in swings if s["type"] == "low"]

        # Cluster swing highs
        for i in range(len(swing_highs)):
            for j in range(i + 1, len(swing_highs)):
                level1 = swing_highs[i]["level"]
                level2 = swing_highs[j]["level"]
                if abs(level1 - level2) / max(level1, level2) < self.range_percent:
                    avg = (level1 + level2) / 2
                    liquidity_zones.append({
                        "type": "buyside",  # buy stops above
                        "level": avg,
                        "touches": 2,
                    })

        # Cluster swing lows
        for i in range(len(swing_lows)):
            for j in range(i + 1, len(swing_lows)):
                level1 = swing_lows[i]["level"]
                level2 = swing_lows[j]["level"]
                if abs(level1 - level2) / max(level1, level2) < self.range_percent:
                    avg = (level1 + level2) / 2
                    liquidity_zones.append({
                        "type": "sellside",  # sell stops below
                        "level": avg,
                        "touches": 2,
                    })

        return liquidity_zones[-5:]

    # ------------------------------------------------------------------
    # LIQUIDITY SWEEP DETECTION
    # ------------------------------------------------------------------
    def detect_liquidity_sweep(self, highs: np.ndarray, lows: np.ndarray,
                                closes: np.ndarray, swings: List[dict]) -> Optional[dict]:
        """
        Liquidity sweep = price briefly takes out a swing high/low then reverses.
        This is a strong reversal signal.
        """
        if not swings or len(closes) < 3:
            return None

        close_now = closes[-1]
        close_prev = closes[-2]
        high_now = highs[-1]
        low_now = lows[-1]

        # Check for buy-side liquidity sweep (swept highs then reversed down)
        for s in swings[-10:]:
            if s["type"] == "high":
                if high_now > s["level"] and close_now < s["level"]:
                    return {
                        "type": "buyside_sweep",
                        "signal": "sell",
                        "level": s["level"],
                        "confidence": 80,
                        "reason": f"Liquidity sweep above {s['level']:.5f} → reversal",
                    }

        # Check for sell-side liquidity sweep (swept lows then reversed up)
        for s in swings[-10:]:
            if s["type"] == "low":
                if low_now < s["level"] and close_now > s["level"]:
                    return {
                        "type": "sellside_sweep",
                        "signal": "buy",
                        "level": s["level"],
                        "confidence": 80,
                        "reason": f"Liquidity sweep below {s['level']:.5f} → reversal",
                    }

        return None

    # ------------------------------------------------------------------
    # FULL ANALYSIS
    # ------------------------------------------------------------------
    def analyze(self, bars: list) -> SMCSignal:
        """
        Run full SMC analysis on bars.
        Returns SMCSignal with direction, confidence, and breakdown.
        """
        if len(bars) < 30:
            return SMCSignal(None, 0, "Not enough bars", {})

        highs = np.array([b.high for b in bars])
        lows = np.array([b.low for b in bars])
        opens = np.array([b.open for b in bars])
        closes = np.array([b.close for b in bars])
        volumes = np.array([b.volume if hasattr(b, 'volume') and b.volume else 1.0 for b in bars])

        # Find swings
        swings = self.find_swings(highs, lows)

        # BOS/CHoCH
        bos_choch = self.detect_bos_choch(highs, lows, closes, swings)

        # Order Blocks
        order_blocks = self.detect_order_blocks(highs, lows, opens, closes, volumes, swings)

        # FVGs
        fvgs = self.detect_fvg(highs, lows, opens, closes)

        # Liquidity
        liquidity = self.detect_liquidity(highs, lows, swings)

        # Liquidity sweep
        sweep = self.detect_liquidity_sweep(highs, lows, closes, swings)

        # Determine signal
        signal = None
        confidence = 0
        reasons = []
        components = {
            "bos": bos_choch.get("bos"),
            "choch": bos_choch.get("choch"),
            "order_blocks": len(order_blocks),
            "fvgs": len(fvgs),
            "unfilled_fvgs": len([f for f in fvgs if not f.get("filled", True)]),
            "liquidity_zones": len(liquidity),
            "sweep": sweep,
        }

        # BOS/CHoCH direction
        if bos_choch["bos"] == "bullish":
            signal = "buy"
            confidence += 30
            reasons.append("Bullish BOS")
        elif bos_choch["bos"] == "bearish":
            signal = "sell"
            confidence += 30
            reasons.append("Bearish BOS")

        if bos_choch["choch"] == "bullish":
            signal = "buy"
            confidence += 40
            reasons.append("Bullish CHoCH (reversal)")
        elif bos_choch["choch"] == "bearish":
            signal = "sell"
            confidence += 40
            reasons.append("Bearish CHoCH (reversal)")

        # Liquidity sweep (strong signal)
        if sweep:
            if sweep["signal"] == "buy":
                signal = "buy"
                confidence += sweep["confidence"] * 0.5
                reasons.append(sweep["reason"])
            elif sweep["signal"] == "sell":
                signal = "sell"
                confidence += sweep["confidence"] * 0.5
                reasons.append(sweep["reason"])

        # Unfilled FVGs as confluence
        unfilled_fvgs = [f for f in fvgs if not f.get("filled", True)]
        if unfilled_fvgs:
            close_now = closes[-1]
            for fvg in unfilled_fvgs[-2:]:
                if fvg["type"] == "bullish" and close_now > fvg["top"]:
                    confidence += 10
                    reasons.append("Bullish FVG support below")
                elif fvg["type"] == "bearish" and close_now < fvg["bottom"]:
                    confidence += 10
                    reasons.append("Bearish FVG resistance above")

        confidence = min(100, confidence)

        return SMCSignal(
            signal=signal,
            confidence=confidence,
            reason=" | ".join(reasons) if reasons else "No SMC signal",
            components=components,
        )

    # ------------------------------------------------------------------
    # FORMAT FOR TELEGRAM
    # ------------------------------------------------------------------
    def format_for_signal(self, result: SMCSignal, symbol: str) -> str:
        """Format SMC analysis for Telegram signal message."""
        lines = []
        if result.components.get("bos"):
            lines.append(f"🏛️ BOS: {result.components['bos']}")
        if result.components.get("choch"):
            lines.append(f"🔄 CHoCH: {result.components['choch']}")
        if result.components.get("order_blocks"):
            lines.append(f"📦 Order Blocks: {result.components['order_blocks']}")
        if result.components.get("unfilled_fvgs"):
            lines.append(f"⚡ FVGs unfilled: {result.components['unfilled_fvgs']}")
        if result.components.get("sweep"):
            lines.append(f"🌊 Liquidity sweep detected")

        return "\n".join(lines) if lines else ""
