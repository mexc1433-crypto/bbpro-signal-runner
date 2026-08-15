"""
filters.py - BBPro Signal Bot
Multi-layer signal filters for higher win rate.

Key fixes:
  - spread and news_blackout are HARD VETO (always reject if failed)
  - All keys match what main.py sends
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def spread_ok(spread_pips: float, max_spread: float = 3.0) -> bool:
    return spread_pips <= max_spread


def rsi_ok(rsi: float, side: str) -> bool:
    if side.lower() == "buy":
        return rsi < 70
    else:
        return rsi > 30


def adx_ok(adx: float, min_adx: float = 20.0) -> bool:
    return adx >= min_adx


def ema_trend_ok(close: float, ema50: float, ema200: float, side: str) -> bool:
    if side.lower() == "buy":
        return close > ema50 and ema50 > ema200
    else:
        return close < ema50 and ema50 < ema200


def higher_tf_trend(bars_h4: list, side: str) -> bool:
    if not bars_h4 or len(bars_h4) < 200:
        return True
    closes = [b["close"] if isinstance(b, dict) else b for b in bars_h4]
    ema200 = sum(closes[-200:]) / 200
    last_close = closes[-1]
    if side.lower() == "buy":
        return last_close > ema200
    else:
        return last_close < ema200


def market_structure(bars: list, side: str) -> bool:
    if not bars or len(bars) < 6:
        return True
    highs  = [b["high"]  if isinstance(b, dict) else getattr(b, "high", 0) for b in bars[-6:]]
    lows   = [b["low"]   if isinstance(b, dict) else getattr(b, "low", 0)  for b in bars[-6:]]
    if side.lower() == "buy":
        return highs[-1] > highs[-3] and lows[-1] > lows[-3]
    else:
        return highs[-1] < highs[-3] and lows[-1] < lows[-3]


def news_blackout(side: str = "") -> bool:
    """
    Returns True if it's SAFE to trade (no news blackout).
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    h, m = now.hour, now.minute
    blackout_windows = [(8, 25, 9, 0), (13, 25, 14, 0)]
    for (sh, sm, eh, em) in blackout_windows:
        start_mins = sh * 60 + sm
        end_mins   = eh * 60 + em
        now_mins   = h  * 60 + m
        if start_mins <= now_mins <= end_mins:
            return False
    return True


def multi_layer_filter(side: str, indicators: dict) -> dict:
    """
    Master filter — checks all layers and returns score + decision.

    indicators dict keys (matching main.py):
        rsi, adx, close, ema50, ema200, spread_pips, bars (list), bars_h4 (list)

    CRITICAL FIX: spread and news_blackout are HARD VETO.
    If either fails, the signal is rejected immediately.

    Returns:
        { "pass": bool, "score": int (0-100), "reasons": [str] }
    """
    checks = {}
    reasons = []

    # ── HARD VETO CHECKS (must pass, cannot be overridden by score) ──────

    # 1. Spread — HARD VETO
    spread = indicators.get("spread_pips", 1.0)
    checks["spread"] = spread_ok(spread, indicators.get("max_spread", 3.0))
    if not checks["spread"]:
        reasons.append(f"Spread={spread:.1f} عالي")
        return {"pass": False, "score": 0, "reasons": reasons, "checks": checks}

    # 2. News blackout — HARD VETO
    checks["news"] = news_blackout(side)
    if not checks["news"]:
        reasons.append("نافذة أخبار اقتصادية")
        return {"pass": False, "score": 0, "reasons": reasons, "checks": checks}

    # ── SOFT CHECKS (contribute to score) ────────────────────────────────

    # 3. RSI filter
    rsi = indicators.get("rsi", 50)
    checks["rsi"] = rsi_ok(rsi, side)
    if not checks["rsi"]:
        reasons.append(f"RSI={rsi:.1f} في منطقة مشبعة")

    # 4. ADX filter
    adx = indicators.get("adx", 25)
    checks["adx"] = adx_ok(adx)
    if not checks["adx"]:
        reasons.append(f"ADX={adx:.1f} سوق رينج")

    # 5. EMA trend
    close  = indicators.get("close", 0)
    ema50  = indicators.get("ema50", 0)
    ema200 = indicators.get("ema200", 0)
    if close and ema50 and ema200:
        checks["ema_trend"] = ema_trend_ok(close, ema50, ema200, side)
        if not checks["ema_trend"]:
            reasons.append("EMA trend عكسي")
    else:
        checks["ema_trend"] = True

    # 6. Market structure
    bars = indicators.get("bars", [])
    if len(bars) >= 6:
        checks["structure"] = market_structure(bars, side)
        if not checks["structure"]:
            reasons.append("هيكل السوق عكسي")
    else:
        checks["structure"] = True

    # 7. H4 trend
    bars_h4 = indicators.get("bars_h4", [])
    if len(bars_h4) >= 200:
        checks["h4_trend"] = higher_tf_trend(bars_h4, side)
        if not checks["h4_trend"]:
            reasons.append("H4 trend عكسي")
    else:
        checks["h4_trend"] = True

    # Score: spread + news already passed (hard veto).
    # Score the remaining 5 soft checks.
    soft_checks = ["rsi", "adx", "ema_trend", "structure", "h4_trend"]
    passed = sum(1 for k in soft_checks if checks.get(k, True))
    total  = len(soft_checks)
    score  = int((passed / total) * 100)

    # Need at least 3/5 soft checks to pass (score >= 60)
    decision = (score >= 60)

    if decision:
        logger.info("Signal PASSED: score=%d/100 (%d/%d soft checks) side=%s", score, passed, total, side)
    else:
        logger.info("Signal BLOCKED: score=%d/100, reasons=%s", score, reasons)

    return {"pass": decision, "score": score, "reasons": reasons, "checks": checks}


# ── Compatibility aliases ──────────────────────────────────────────────────

def all_entry_filters_pass(side: str, indicators: dict) -> bool:
    result = multi_layer_filter(side, indicators)
    return result["pass"]


def parse_news_times(news_str: str) -> list:
    times = []
    if not news_str:
        return times
    for t in news_str.split(","):
        t = t.strip()
        try:
            parts = t.split(":")
            times.append((int(parts[0]), int(parts[1])))
        except Exception:
            pass
    return times


def should_close_all_on_friday(*args, now=None) -> bool:
    from datetime import datetime, timezone
    if now is None:
        now = datetime.now(timezone.utc)
    return now.weekday() == 4 and now.hour >= 20
