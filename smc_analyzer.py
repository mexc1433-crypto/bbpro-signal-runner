"""
صياد الشمعات | Candle Hunter - SMC & Order Flow Analyzer
Smart Money Concepts + Volume Analysis باستخدام Python من OHLCV
مبني على مفاهيم الـ Order Flow المحترف من ملف "ملف سري"
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SMCAnalyzer:
    """
    Smart Money Concepts Analyzer
    يحلل: VWAP, Order Blocks, Fair Value Gaps, Liquidity Zones, Volume Profile, Imbalance
    """

    def __init__(self):
        self.order_blocks: List[Dict] = []
        self.fvg_zones: List[Dict] = []
        self.liquidity_zones: List[Dict] = []
        self.vwap_value: float = 0.0
        self.vwap_upper: float = 0.0
        self.vwap_lower: float = 0.0
        self.poc_price: float = 0.0
        self.volume_nodes: List[Dict] = []

    def calculate_vwap(self, df: pd.DataFrame, anchor: str = "session") -> Dict:
        try:
            if df is None or len(df) < 5:
                return {"vwap": 0, "upper_band": 0, "lower_band": 0, "signal": "neutral"}

            typical_price = (df["high"] + df["low"] + df["close"]) / 3
            volume = df["volume"].replace(0, 1)

            vwap = (typical_price * volume).cumsum() / volume.cumsum()
            current_vwap = float(vwap.iloc[-1])
            current_close = float(df["close"].iloc[-1])

            std_dev = (typical_price - vwap).rolling(20, min_periods=5).std()
            current_std = float(std_dev.iloc[-1]) if len(std_dev) > 0 and not pd.isna(std_dev.iloc[-1]) else 0

            upper = current_vwap + current_std
            lower = current_vwap - current_std

            self.vwap_value = current_vwap
            self.vwap_upper = upper
            self.vwap_lower = lower

            signal = "neutral"
            if current_close > upper:
                signal = "overbought"
            elif current_close > current_vwap:
                signal = "bullish"
            elif current_close < lower:
                signal = "oversold"
            elif current_close < current_vwap:
                signal = "bearish"

            return {
                "vwap": round(current_vwap, 2),
                "upper_band": round(upper, 2),
                "lower_band": round(lower, 2),
                "current_price": round(current_close, 2),
                "signal": signal,
                "distance_pct": round(((current_close - current_vwap) / current_vwap) * 100, 3) if current_vwap > 0 else 0,
            }
        except Exception as e:
            logger.warning(f"VWAP error: {e}")
            return {"vwap": 0, "upper_band": 0, "lower_band": 0, "signal": "neutral"}

    def find_order_blocks(self, df: pd.DataFrame, lookback: int = 50) -> List[Dict]:
        try:
            if df is None or len(df) < 10:
                return []

            blocks = []
            window = df.tail(lookback).reset_index(drop=True)

            for i in range(3, len(window) - 3):
                curr = window.iloc[i]
                next3 = window.iloc[i + 3]
                move = abs(next3["close"] - curr["close"])
                avg_range = (window["high"] - window["low"]).rolling(10).mean().iloc[i]
                if avg_range <= 0 or pd.isna(avg_range):
                    continue

                if move <= avg_range * 1.5:
                    continue

                if curr["close"] < curr["open"] and next3["close"] > curr["high"]:
                    blocks.append({
                        "type": "bullish",
                        "top": float(curr["high"]),
                        "bottom": float(curr["low"]),
                        "midpoint": float((curr["high"] + curr["low"]) / 2),
                        "strength": round(float(move / avg_range), 2),
                        "tested": False,
                    })
                elif curr["close"] > curr["open"] and next3["close"] < curr["low"]:
                    blocks.append({
                        "type": "bearish",
                        "top": float(curr["high"]),
                        "bottom": float(curr["low"]),
                        "midpoint": float((curr["high"] + curr["low"]) / 2),
                        "strength": round(float(move / avg_range), 2),
                        "tested": False,
                    })

            current_price = float(df["close"].iloc[-1])
            for block in blocks:
                if block["bottom"] <= current_price <= block["top"]:
                    block["tested"] = True

            blocks.sort(key=lambda x: x["strength"], reverse=True)
            self.order_blocks = blocks[:5]
            return self.order_blocks
        except Exception as e:
            logger.warning(f"Order Blocks error: {e}")
            return []

    def find_fvg(self, df: pd.DataFrame, lookback: int = 30) -> List[Dict]:
        try:
            if df is None or len(df) < 5:
                return []

            gaps = []
            window = df.tail(lookback).reset_index(drop=True)

            for i in range(2, len(window)):
                c1 = window.iloc[i - 2]
                c3 = window.iloc[i]

                if c1["low"] > c3["high"]:
                    gaps.append({
                        "type": "bullish",
                        "top": float(c1["low"]),
                        "bottom": float(c3["high"]),
                        "size": round(float(c1["low"] - c3["high"]), 2),
                        "filled": False,
                    })
                elif c1["high"] < c3["low"]:
                    gaps.append({
                        "type": "bearish",
                        "top": float(c3["low"]),
                        "bottom": float(c1["high"]),
                        "size": round(float(c3["low"] - c1["high"]), 2),
                        "filled": False,
                    })

            current_price = float(df["close"].iloc[-1])
            for gap in gaps:
                if gap["bottom"] <= current_price <= gap["top"]:
                    gap["filled"] = True

            self.fvg_zones = [g for g in gaps if not g["filled"]][:5]
            return self.fvg_zones
        except Exception as e:
            logger.warning(f"FVG error: {e}")
            return []

    def find_liquidity_zones(self, df: pd.DataFrame, lookback: int = 50, pivot_window: int = 3) -> List[Dict]:
        try:
            if df is None or len(df) < 10:
                return []

            zones = []
            window = df.tail(lookback).reset_index(drop=True)

            for i in range(pivot_window, len(window) - pivot_window):
                is_swing_high = all(
                    window.iloc[i]["high"] >= window.iloc[i + j]["high"]
                    for j in range(-pivot_window, pivot_window + 1) if j != 0
                )
                is_swing_low = all(
                    window.iloc[i]["low"] <= window.iloc[i + j]["low"]
                    for j in range(-pivot_window, pivot_window + 1) if j != 0
                )

                if is_swing_high:
                    zones.append({"type": "resistance", "price": float(window.iloc[i]["high"]), "swept": False})
                if is_swing_low:
                    zones.append({"type": "support", "price": float(window.iloc[i]["low"]), "swept": False})

            current_high = float(df["high"].iloc[-1])
            current_low = float(df["low"].iloc[-1])

            for zone in zones:
                if zone["type"] == "resistance" and current_high > zone["price"]:
                    zone["swept"] = True
                elif zone["type"] == "support" and current_low < zone["price"]:
                    zone["swept"] = True

            unswept = [z for z in zones if not z["swept"]]
            current_price = float(df["close"].iloc[-1])
            unswept.sort(key=lambda z: abs(z["price"] - current_price))
            self.liquidity_zones = unswept[:5]
            return self.liquidity_zones
        except Exception as e:
            logger.warning(f"Liquidity zones error: {e}")
            return []

    def calculate_volume_profile(self, df: pd.DataFrame, bins: int = 20) -> Dict:
        try:
            if df is None or len(df) < 10:
                return {"poc": 0, "value_area_high": 0, "value_area_low": 0}

            price_min = float(df["low"].min())
            price_max = float(df["high"].max())
            if price_max <= price_min:
                return {"poc": 0, "value_area_high": 0, "value_area_low": 0}

            bin_size = (price_max - price_min) / bins
            nodes = []

            for i in range(bins):
                bin_low = price_min + i * bin_size
                bin_high = bin_low + bin_size
                vol = 0.0

                overlapping = (df["low"] < bin_high) & (df["high"] > bin_low)
                for idx in df[overlapping].index:
                    cl = df.loc[idx, "low"]
                    ch = df.loc[idx, "high"]
                    cv = df.loc[idx, "volume"]
                    ol = max(cl, bin_low)
                    oh = min(ch, bin_high)
                    pct = (oh - ol) / (ch - cl) if ch > cl else 0
                    vol += float(cv * pct)

                nodes.append({"price_low": round(bin_low, 2), "price_high": round(bin_high, 2), "volume": round(vol, 2)})

            poc_node = max(nodes, key=lambda x: x["volume"])
            poc_price = (poc_node["price_low"] + poc_node["price_high"]) / 2

            total_vol = sum(n["volume"] for n in nodes)
            target_vol = total_vol * 0.7
            poc_idx = nodes.index(poc_node)
            va_vol = poc_node["volume"]
            va_low_idx = poc_idx
            va_high_idx = poc_idx

            while va_vol < target_vol and (va_low_idx > 0 or va_high_idx < len(nodes) - 1):
                below = nodes[va_low_idx - 1]["volume"] if va_low_idx > 0 else 0
                above = nodes[va_high_idx + 1]["volume"] if va_high_idx < len(nodes) - 1 else 0
                if below >= above and va_low_idx > 0:
                    va_vol += below
                    va_low_idx -= 1
                elif va_high_idx < len(nodes) - 1:
                    va_vol += above
                    va_high_idx += 1
                else:
                    va_vol += below
                    va_low_idx -= 1

            self.poc_price = round(poc_price, 2)
            self.volume_nodes = nodes

            return {
                "poc": round(poc_price, 2),
                "value_area_high": round(nodes[va_high_idx]["price_high"], 2),
                "value_area_low": round(nodes[va_low_idx]["price_low"], 2),
            }
        except Exception as e:
            logger.warning(f"Volume Profile error: {e}")
            return {"poc": 0, "value_area_high": 0, "value_area_low": 0}

    def detect_bollinger_squeeze(self, df: pd.DataFrame, period: int = 20) -> Dict:
        try:
            if df is None or len(df) < period + 10:
                return {"squeeze": False, "percentile": 50, "signal": "neutral"}

            sma = df["close"].rolling(period).mean()
            std = df["close"].rolling(period).std()
            upper = sma + 2 * std
            lower = sma - 2 * std
            band_width = (upper - lower) / sma * 100

            current_width = float(band_width.iloc[-1])
            historical = band_width.iloc[-120:] if len(band_width) > 120 else band_width
            historical = historical.dropna()
            if len(historical) == 0:
                return {"squeeze": False, "percentile": 50, "signal": "neutral"}

            percentile = float((historical < current_width).sum() / len(historical) * 100)
            is_squeeze = percentile < 20

            signal = "neutral"
            if is_squeeze:
                last_close = float(df["close"].iloc[-1])
                last_sma = float(sma.iloc[-1])
                if last_close > last_sma:
                    signal = "potential_breakout_up"
                else:
                    signal = "potential_breakout_down"

            return {"squeeze": is_squeeze, "percentile": round(percentile, 1), "band_width": round(current_width, 3), "signal": signal}
        except Exception as e:
            logger.warning(f"Bollinger Squeeze error: {e}")
            return {"squeeze": False, "percentile": 50, "signal": "neutral"}

    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> Dict:
        try:
            if df is None or len(df) < period * 3:
                return {"adx": 0, "plus_di": 0, "minus_di": 0, "trend_strength": "unknown", "direction": "neutral"}

            high = df["high"]
            low = df["low"]
            close = df["close"]

            tr1 = high - low
            tr2 = (high - close.shift()).abs()
            tr3 = (low - close.shift()).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            up_move = high - high.shift()
            down_move = low.shift() - low
            plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
            minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)

            atr = tr.ewm(alpha=1/period, adjust=False).mean()
            atr = atr.replace(0, 1e-10)
            plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr
            minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr

            dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10) * 100
            dx = dx.replace([float('inf'), float('nan')], 0)
            adx = dx.ewm(alpha=1/period, adjust=False).mean()

            current_adx = float(adx.iloc[-1])
            current_plus = float(plus_di.iloc[-1])
            current_minus = float(minus_di.iloc[-1])

            if current_adx > 25:
                strength = "strong"
            elif current_adx > 20:
                strength = "developing"
            else:
                strength = "weak/ranging"

            return {
                "adx": round(current_adx, 1),
                "plus_di": round(current_plus, 1),
                "minus_di": round(current_minus, 1),
                "trend_strength": strength,
                "direction": "bullish" if current_plus > current_minus else "bearish",
            }
        except Exception as e:
            logger.warning(f"ADX error: {e}")
            return {"adx": 0, "plus_di": 0, "minus_di": 0, "trend_strength": "unknown", "direction": "neutral"}

    def analyze_all(self, df: pd.DataFrame, timeframe: str = "1h") -> Dict:
        try:
            vwap = self.calculate_vwap(df)
            order_blocks = self.find_order_blocks(df)
            fvg = self.find_fvg(df)
            liquidity = self.find_liquidity_zones(df)
            volume_profile = self.calculate_volume_profile(df)
            squeeze = self.detect_bollinger_squeeze(df)
            adx = self.calculate_adx(df)

            current_price = float(df["close"].iloc[-1])
            bias = "neutral"
            bullish_signals = 0
            bearish_signals = 0

            if vwap["signal"] == "bullish": bullish_signals += 1
            elif vwap["signal"] == "bearish": bearish_signals += 1
            elif vwap["signal"] == "overbought": bearish_signals += 1
            elif vwap["signal"] == "oversold": bullish_signals += 1

            if adx.get("direction") == "bullish" and adx.get("adx", 0) > 20: bullish_signals += 1
            elif adx.get("direction") == "bearish" and adx.get("adx", 0) > 20: bearish_signals += 1

            poc = volume_profile.get("poc", 0)
            if poc > 0:
                if current_price > poc: bullish_signals += 1
                else: bearish_signals += 1

            if current_price > vwap["vwap"]: bullish_signals += 1
            else: bearish_signals += 1

            if squeeze["signal"] == "potential_breakout_up": bullish_signals += 1
            elif squeeze["signal"] == "potential_breakout_down": bearish_signals += 1

            if bullish_signals > bearish_signals + 1:
                bias = "bullish"
            elif bearish_signals > bullish_signals + 1:
                bias = "bearish"

            nearest_ob = None
            min_dist = float('inf')
            for ob in order_blocks:
                dist = abs(ob["midpoint"] - current_price)
                if dist < min_dist:
                    min_dist = dist
                    nearest_ob = ob

            nearest_liq = None
            min_dist = float('inf')
            for liq in liquidity:
                dist = abs(liq["price"] - current_price)
                if dist < min_dist:
                    min_dist = dist
                    nearest_liq = liq

            return {
                "timeframe": timeframe,
                "current_price": round(current_price, 2),
                "bias": bias,
                "bullish_score": bullish_signals,
                "bearish_score": bearish_signals,
                "vwap": vwap,
                "adx": adx,
                "bollinger_squeeze": squeeze,
                "volume_profile": volume_profile,
                "order_blocks": order_blocks[:3],
                "nearest_order_block": nearest_ob,
                "fair_value_gaps": fvg[:3],
                "liquidity_zones": liquidity[:3],
                "nearest_liquidity": nearest_liq,
                "analyzed_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"SMC analyze_all error: {e}")
            return {"bias": "neutral", "error": str(e)}


    # ═══════════════════════════════════════════════════════════
    # طبقة تأكيد النشر: BOS / CHOCH / Liquidity Sweep / قوة الشموع
    # ═══════════════════════════════════════════════════════════

    def detect_swings(self, df: pd.DataFrame, window: int = 2) -> Dict:
        """قمم وقيعان السوينج (fractal pivots)"""
        highs, lows = [], []
        h, l = df["high"].values, df["low"].values
        for i in range(window, len(df) - window):
            if h[i] == max(h[i - window:i + window + 1]):
                highs.append({"idx": i, "price": float(h[i])})
            if l[i] == min(l[i - window:i + window + 1]):
                lows.append({"idx": i, "price": float(l[i])})
        return {"highs": highs, "lows": lows}

    def detect_bos_choch(self, df: pd.DataFrame, window: int = 2) -> Dict:
        """BOS (استمرار) و CHOCH (انعكاس) من كسر آخر قمة/قاع سوينج"""
        try:
            swings = self.detect_swings(df, window)
            closes = df["close"].values
            if not swings["highs"] or not swings["lows"]:
                return {"type": "NONE", "direction": "neutral"}

            # آخر حدث كسر: قمة سوينج سابقة اتقفلت فوقها (BOS/CHOCH صاعد)
            # أو قاع سوينج سابق اتقفلت تحته (نازل)
            events = []  # (idx, kind, direction)
            hh = swings["highs"]
            ll = swings["lows"]
            for s in hh:
                for j in range(s["idx"] + 1, len(closes)):
                    if closes[j] > s["price"]:
                        events.append((j, "HIGH_BREAK", "bullish", s["price"]))
                        break
            for s in ll:
                for j in range(s["idx"] + 1, len(closes)):
                    if closes[j] < s["price"]:
                        events.append((j, "LOW_BREAK", "bearish", s["price"]))
                        break
            if not events:
                return {"type": "NONE", "direction": "neutral"}
            events.sort(key=lambda e: e[0])
            last_idx, last_kind, last_dir, last_level = events[-1]

            # نحدد اتجاه الترند قبل الحدث من الحدث اللي قبله
            if len(events) >= 2:
                prev_dir = events[-2][2]
                event_type = "BOS" if prev_dir == last_dir else "CHOCH"
            else:
                event_type = "BOS"
            return {
                "type": event_type, "direction": last_dir,
                "level": last_level, "bars_ago": len(closes) - 1 - last_idx,
            }
        except Exception as e:
            logger.warning(f"detect_bos_choch error: {e}")
            return {"type": "NONE", "direction": "neutral"}

    def detect_liquidity_sweep(self, df: pd.DataFrame, lookback: int = 20, window: int = 2) -> Dict:
        """كنس السيولة: ذيل يخترق قمة/قاع سابقة والإغلاق يرجع جوه"""
        try:
            seg = df.tail(lookback).reset_index(drop=True)
            if len(seg) < window * 2 + 3:
                return {"swept": False, "direction": "neutral"}
            highs = seg["high"].values
            lows = seg["low"].values
            closes = seg["close"].values
            # آخر سوينج قبل آخر 3 شموع
            sw_high, sw_low = None, None
            for i in range(len(seg) - 4 - window, window, -1):
                if sw_high is None and highs[i] == max(highs[i - window:i + window + 1]):
                    sw_high = highs[i]
                if sw_low is None and lows[i] == min(lows[i - window:i + window + 1]):
                    sw_low = lows[i]
                if sw_high and sw_low:
                    break
            last = len(seg) - 1
            if sw_high and highs[last] > sw_high and closes[last] < sw_high:
                return {"swept": True, "direction": "bearish", "level": float(sw_high)}
            if sw_low and lows[last] < sw_low and closes[last] > sw_low:
                return {"swept": True, "direction": "bullish", "level": float(sw_low)}
            return {"swept": False, "direction": "neutral"}
        except Exception as e:
            logger.warning(f"detect_liquidity_sweep error: {e}")
            return {"swept": False, "direction": "neutral"}

    def candle_strength(self, df: pd.DataFrame, n: int = 3) -> float:
        """قوة الشموع: متوسط نسبة الجسم للمدى في آخر n شموع (0-1)"""
        try:
            seg = df.tail(n)
            strengths = []
            for _, row in seg.iterrows():
                rng = float(row["high"] - row["low"])
                if rng <= 0:
                    continue
                strengths.append(abs(float(row["close"] - row["open"])) / rng)
            return round(sum(strengths) / len(strengths), 2) if strengths else 0.0
        except Exception as e:
            logger.warning(f"candle_strength error: {e}")
            return 0.0

    def price_action_confluence(self, df: pd.DataFrame, signal_type: str) -> Dict:
        """طبقة تأكيد SMC/Price Action — 6 عوامل:
        1) BOS في اتجاه الإشارة  2) CHOCH انعكاس مؤكد  3) Order Block في الاتجاه
        4) FVG غير معوض قريب  5) Liquidity Sweep عكس الاتجاه  6) قوة شموع ≥ 50%
        """
        is_buy = signal_type.upper() in ("BUY", "LONG", "BULLISH")
        details = {}
        score = 0

        # 1) BOS / 2) CHOCH
        structure = self.detect_bos_choch(df)
        details["structure"] = structure
        if structure["type"] == "BOS" and (
            (is_buy and structure["direction"] == "bullish") or
            (not is_buy and structure["direction"] == "bearish")
        ):
            score += 1
            details["bos_aligned"] = True
        if structure["type"] == "CHOCH" and (
            (is_buy and structure["direction"] == "bullish") or
            (not is_buy and structure["direction"] == "bearish")
        ):
            score += 1
            details["choch_aligned"] = True

        # 3) Order Block في الاتجاه
        try:
            obs = self.find_order_blocks(df)
            price = float(df["close"].iloc[-1])
            for ob in obs:
                ob_top = ob.get("top", ob.get("high", 0)) or ob.get("zone", [0, 0])[1]
                ob_bot = ob.get("bottom", ob.get("low", 0)) or ob.get("zone", [0, 0])[0]
                ob_type = ob.get("type", "").lower()
                in_zone = ob_bot <= price <= ob_top
                if is_buy and "bull" in ob_type and (in_zone or 0 <= price - ob_top < 3.0):
                    # سعر جوه البلوك الصاعد (ريتست) أو خرج منه لفوق للتو
                    score += 1
                    details["order_block"] = ob_type
                    break
                if (not is_buy) and "bear" in ob_type and (in_zone or 0 <= ob_bot - price < 3.0):
                    score += 1
                    details["order_block"] = ob_type
                    break
        except Exception as e:
            logger.debug(f"OB gate error: {e}")

        # 4) FVG غير معوض في الاتجاه
        try:
            fvgs = self.find_fvg(df)
            for f in fvgs:
                f_dir = f.get("type", f.get("direction", "")).lower()
                filled = f.get("filled", False)
                if not filled and (
                    (is_buy and "bull" in f_dir) or ((not is_buy) and "bear" in f_dir)
                ):
                    score += 1
                    details["fvg"] = f_dir
                    break
        except Exception as e:
            logger.debug(f"FVG gate error: {e}")

        # 5) Liquidity Sweep عكس الاتجاه (كنس السيولة ثم انعكاس)
        sweep = self.detect_liquidity_sweep(df)
        details["sweep"] = {"swept": sweep["swept"], "direction": sweep["direction"]}
        if sweep["swept"] and (
            (is_buy and sweep["direction"] == "bullish") or
            ((not is_buy) and sweep["direction"] == "bearish")
        ):
            score += 1
            details["liquidity_sweep"] = True

        # 6) قوة الشموع
        strength = self.candle_strength(df)
        details["candle_strength"] = strength
        if strength >= 0.5:
            score += 1

        return {
            "score": score, "max": 6, "direction": "buy" if is_buy else "sell",
            "details": details, "signal_type": signal_type,
        }

    def directional_gate(self, df: pd.DataFrame, signal_type: str, min_score: int = 3) -> Dict:
        """بوابة النشر: score >= min_score من 6 عوامل — والفشل مش بيمنع لو مفيش داتا"""
        try:
            if df is None or len(df) < 30:
                return {"passed": True, "score": -1, "reason": "insufficient_data", "details": {}}
            pa = self.price_action_confluence(df, signal_type)
            passed = pa["score"] >= min_score
            return {
                "passed": passed, "score": pa["score"], "max": pa["max"],
                "factors": pa["details"], "reason": None if passed else "low_confluence",
            }
        except Exception as e:
            logger.warning(f"directional_gate error: {e}")
            return {"passed": True, "score": -1, "reason": "gate_error", "details": {}}

    def get_smc_confidence_adjustment(self, smc_data: Dict, signal_type: str) -> float:
        try:
            adjustment = 0.0
            bias = smc_data.get("bias", "neutral")
            adx = smc_data.get("adx", {})
            adx_val = adx.get("adx", 0)
            squeeze = smc_data.get("bollinger_squeeze", {})
            vwap = smc_data.get("vwap", {})

            is_buy = signal_type.lower() in ("buy", "long", "bullish")

            if is_buy and bias == "bullish": adjustment += 5.0
            elif not is_buy and bias == "bearish": adjustment += 5.0
            elif is_buy and bias == "bearish": adjustment -= 5.0
            elif not is_buy and bias == "bullish": adjustment -= 5.0

            if adx_val > 25:
                adx_dir = adx.get("direction", "")
                if (is_buy and adx_dir == "bullish") or (not is_buy and adx_dir == "bearish"):
                    adjustment += 4.0
                else:
                    adjustment -= 3.0
            elif adx_val < 20:
                adjustment -= 2.0

            vwap_sig = vwap.get("signal", "neutral")
            if is_buy and vwap_sig == "bullish": adjustment += 3.0
            elif not is_buy and vwap_sig == "bearish": adjustment += 3.0
            elif is_buy and vwap_sig == "bearish": adjustment -= 3.0
            elif not is_buy and vwap_sig == "bullish": adjustment -= 3.0

            if squeeze.get("squeeze"):
                sq_signal = squeeze.get("signal", "")
                if (is_buy and "up" in sq_signal) or (not is_buy and "down" in sq_signal):
                    adjustment += 4.0
                else:
                    adjustment -= 2.0

            poc = smc_data.get("volume_profile", {}).get("poc", 0)
            price = smc_data.get("current_price", 0)
            if poc > 0 and price > 0:
                if is_buy and price > poc: adjustment += 2.0
                elif not is_buy and price < poc: adjustment += 2.0

            adjustment = max(-15.0, min(15.0, adjustment))
            return round(adjustment, 1)
        except Exception as e:
            logger.warning(f"SMC confidence adjustment error: {e}")
            return 0.0

    def format_smc_report(self, smc_data: Dict) -> str:
        try:
            bias_emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(smc_data.get("bias", "neutral"), "🟡")

            report = "🧠 تحليل SMC | صياد الشمعات\n"
            report += "━━━━━━━━━━━━━━━━━━━━\n"
            report += f"💰 السعر: ${smc_data.get('current_price', 0):.2f}\n"
            report += f"{bias_emoji} Bias: {smc_data.get('bias', 'neutral').upper()}\n"
            report += f"📊 Bulls: {smc_data.get('bullish_score', 0)} | Bears: {smc_data.get('bearish_score', 0)}\n\n"

            vwap = smc_data.get("vwap", {})
            report += f"📐 VWAP: ${vwap.get('vwap', 0):.2f}\n"
            report += f"   Upper: ${vwap.get('upper_band', 0):.2f} | Lower: ${vwap.get('lower_band', 0):.2f}\n"
            report += f"   Signal: {vwap.get('signal', 'neutral')}\n\n"

            adx = smc_data.get("adx", {})
            report += f"💪 ADX: {adx.get('adx', 0)} ({adx.get('trend_strength', '?')})\n"
            report += f"   +DI: {adx.get('plus_di', 0)} | -DI: {adx.get('minus_di', 0)}\n"
            report += f"   Direction: {adx.get('direction', '?')}\n\n"

            vp = smc_data.get("volume_profile", {})
            report += f"📊 Volume Profile:\n"
            report += f"   POC: ${vp.get('poc', 0):.2f}\n"
            report += f"   VA High: ${vp.get('value_area_high', 0):.2f}\n"
            report += f"   VA Low: ${vp.get('value_area_low', 0):.2f}\n\n"

            sq = smc_data.get("bollinger_squeeze", {})
            sq_emoji = "⚠️" if sq.get("squeeze") else "✅"
            report += f"{sq_emoji} Bollinger Squeeze: {'مكبوض! حركة قادمة' if sq.get('squeeze') else 'طبيعي'}\n"
            report += f"   Width Percentile: {sq.get('percentile', 50)}%\n\n"

            obs = smc_data.get("order_blocks", [])
            if obs:
                report += "📦 Order Blocks:\n"
                for ob in obs[:3]:
                    ob_emoji = "🟢" if ob["type"] == "bullish" else "🔴"
                    test = "✅" if ob.get("tested") else "⏳"
                    report += f"   {ob_emoji} {ob['type'].upper()}: ${ob['bottom']:.2f}-${ob['top']:.2f} (STR: {ob['strength']}x) {test}\n"
                report += "\n"

            fvgs = smc_data.get("fair_value_gaps", [])
            if fvgs:
                report += "🎯 Fair Value Gaps:\n"
                for fvg in fvgs[:3]:
                    fvg_emoji = "🟢" if fvg["type"] == "bullish" else "🔴"
                    report += f"   {fvg_emoji} {fvg['type'].upper()}: ${fvg['bottom']:.2f}-${fvg['top']:.2f} (size: ${fvg['size']:.2f})\n"
                report += "\n"

            liqs = smc_data.get("liquidity_zones", [])
            if liqs:
                report += "💧 Liquidity Zones:\n"
                for liq in liqs[:3]:
                    liq_emoji = "🔴" if liq["type"] == "resistance" else "🟢"
                    report += f"   {liq_emoji} {liq['type']}: ${liq['price']:.2f}\n"
                report += "\n"

            report += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            report += "🧠 صياد الشمعات | Candle Hunter"

            return report
        except Exception as e:
            logger.error(f"SMC format error: {e}")
            return "⚠️ خطأ في تنسيق تقرير SMC"

    # ═══════════════════════════════════════════════════
    # Premium/Discount Zone — قاعدة SMC الذهبية:
    # شراء بس من منطقة الخصم (Discount)، بيع بس من منطقة العلاوة (Premium)
    # ═══════════════════════════════════════════════════
    def premium_discount(self, df: pd.DataFrame, lookback: int = 100) -> Dict:
        """منطقة السعر الحالية من مدى الموجة الأخيرة"""
        try:
            if df is None or len(df) < 30:
                return {"zone": "UNKNOWN", "position": 0.5}
            window = df.tail(lookback)
            hi = float(window["high"].max())
            lo = float(window["low"].min())
            if hi <= lo:
                return {"zone": "UNKNOWN", "position": 0.5}
            mid = (hi + lo) / 2.0
            price = float(df["close"].iloc[-1])
            pos = (price - lo) / (hi - lo)  # 0 = قاع المدى، 1 = قمته
            return {
                "zone": "PREMIUM" if pos > 0.5 else "DISCOUNT",
                "position": round(pos, 3),
                "high": hi, "low": lo, "mid": mid, "price": price,
            }
        except Exception as e:
            logger.warning(f"premium_discount error: {e}")
            return {"zone": "UNKNOWN", "position": 0.5}

    def apply_premium_discount(self, signal: Dict, df: pd.DataFrame) -> Dict:
        """تعديل ثقة الإشارة حسب منطقة السعر:
        BUY في Premium = شراء غالي → عقوبة
        BUY في Discount = شراء رخيص → مكافأة (والعكس للبيع)"""
        try:
            zone = self.premium_discount(df)
            sig_dir = signal.get("signal_type", "")
            pos = zone.get("position", 0.5)
            old_conf = signal.get("confidence", 50)
            signal["pd_zone"] = zone.get("zone", "UNKNOWN")
            signal["pd_position"] = pos

            if zone.get("zone") == "UNKNOWN":
                return {"adjusted": False}

            adjustment = 0
            if sig_dir == "BUY":
                # كل ما نطلع لفوق في المدى، الشراء أغلى
                if pos > 0.75:
                    adjustment = -8          # قمة المدى — شراء غالي جداً
                elif pos > 0.5:
                    adjustment = -4          # Premium
                elif pos < 0.35:
                    adjustment = +5          # قاع المدى — شراء رخيص
            elif sig_dir == "SELL":
                if pos < 0.25:
                    adjustment = -8          # قاع المدى — بيع رخيص جداً
                elif pos < 0.5:
                    adjustment = -4          # Discount
                elif pos > 0.65:
                    adjustment = +5          # قمة المدى — بيع غالي

            if adjustment:
                signal["confidence"] = max(30, min(95, old_conf + adjustment))
                logger.info(f"📐 Premium/Discount [{zone['zone']} pos={pos:.2f}] {sig_dir}: {adjustment:+d}% → {signal['confidence']:.0f}%")
                return {"adjusted": True, "old": old_conf, "new": signal["confidence"], **zone}
            return {"adjusted": False, **zone}
        except Exception as e:
            logger.warning(f"apply_premium_discount error: {e}")
            return {"adjusted": False}

    # ═══════════════════════════════════════════════════
    # Liquidity Targets — أهداف عند برك السيولة (قمم/قيعان متساوية)
    # السوق بيجري ناحية السيولة: نحط TP قبل البركة مش بعيد عنها
    # ═══════════════════════════════════════════════════
    def liquidity_targets(self, df: pd.DataFrame, entry: float, sl: float,
                          direction: str, atr: float, min_rr: float = 1.2) -> Optional[Dict]:
        """يدور على برك السيولة (قمم/قيعان ارتداد حقيقية) فوق/تحت الدخول
        ويحط TP1 قدام أقرب بركة تعطي R:R كويس. مفيش → None (نستخدم ATR العادي)"""
        try:
            if df is None or len(df) < 50 or atr <= 0:
                return None
            lookback = df.tail(200)
            highs = lookback["high"].tolist()
            lows = lookback["low"].tolist()

            is_buy = direction.upper() in ("BUY", "LONG", "BULLISH")
            risk = abs(entry - sl)
            if risk <= 0:
                return None

            # قمم/قيعان الارتداد (Pivot): قمة أعلى من جيرانها
            k = 3
            pivot_highs, pivot_lows = [], []
            for i in range(k, len(highs) - k):
                if highs[i] == max(highs[i-k:i+k+1]):
                    pivot_highs.append(highs[i])
                if lows[i] == min(lows[i-k:i+k+1]):
                    pivot_lows.append(lows[i])

            if is_buy:
                # برك السيولة فوق الدخول: قمم ارتداد لسه مش مكسورة (فوق السعر الحالي)
                candidates = sorted(set(h for h in pivot_highs if h > entry + (0.5 * atr)))
                for pool in candidates:
                    tp1 = pool - (0.25 * atr)   # ناخد الجَر قدام البركة
                    if tp1 <= entry + (0.5 * risk):
                        continue
                    rr = (tp1 - entry) / risk
                    if rr >= min_rr:
                        return {"tp1": round(tp1, 2), "pool": round(pool, 2), "rr": round(rr, 2)}
                return None
            else:
                candidates = sorted(set(l for l in pivot_lows if l < entry - (0.5 * atr)), reverse=True)
                for pool in candidates:
                    tp1 = pool + (0.25 * atr)
                    if tp1 >= entry - (0.5 * risk):
                        continue
                    rr = (entry - tp1) / risk
                    if rr >= min_rr:
                        return {"tp1": round(tp1, 2), "pool": round(pool, 2), "rr": round(rr, 2)}
                return None
        except Exception as e:
            logger.warning(f"liquidity_targets error: {e}")
            return None
