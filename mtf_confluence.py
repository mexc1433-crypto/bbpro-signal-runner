"""
صياد الشمعات | Candle Hunter - Multi-Timeframe Confluence
تحليل متعدد الأطر الزمنية + OBV + Fibonacci + Heikin Ashi
مبني على استراتيجية: إطار كبير للاتجاه + متوسط للمنطقة + صغير للتنفيذ
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MTFConfluence:
    """Multi-Timeframe Confluence Analyzer"""

    def __init__(self):
        self.timeframes = {
            "4h": {"weight": 3, "trend": "neutral"},
            "1h": {"weight": 2, "trend": "neutral"},
            "15m": {"weight": 1, "trend": "neutral"},
            "5m": {"weight": 1, "trend": "neutral"},
        }

    # ═══════════════════════════════════════════
    # 1. EMA Trend Detection per timeframe
    # ═══════════════════════════════════════════

    def detect_trend(self, df: pd.DataFrame) -> str:
        """يحدد الاتجاه: bullish / bearish / neutral"""
        try:
            if df is None or len(df) < 50:
                return "neutral"

            ema9 = df["close"].ewm(span=9, adjust=False).mean()
            ema21 = df["close"].ewm(span=21, adjust=False).mean()
            ema50 = df["close"].ewm(span=50, adjust=False).mean()
            ema200 = df["close"].ewm(span=200, adjust=False).mean()

            close = float(df["close"].iloc[-1])
            e9 = float(ema9.iloc[-1])
            e21 = float(ema21.iloc[-1])
            e50 = float(ema50.iloc[-1])
            e200 = float(ema200.iloc[-1]) if len(ema200) > 0 and not pd.isna(ema200.iloc[-1]) else close

            # Golden Cross: EMA50 > EMA200
            golden_cross = e50 > e200
            # Death Cross: EMA50 < EMA200
            death_cross = e50 < e200

            # Stack alignment
            if close > e9 > e21 > e50 > e200:
                return "strong_bullish"
            elif close > e9 > e21 > e50:
                return "bullish"
            elif close < e9 < e21 < e50 < e200:
                return "strong_bearish"
            elif close < e9 < e21 < e50:
                return "bearish"
            else:
                return "neutral"
        except Exception as e:
            logger.warning(f"Trend detection error: {e}")
            return "neutral"

    def analyze_mtf(self, fetcher) -> Dict:
        """
        يحلل كل الأطر الزمنية ويرجع confluence
        fetcher: MarketDataFetcher instance
        """
        try:
            results = {}
            total_score = 0
            max_score = 0

            for tf, config in self.timeframes.items():
                df = fetcher.fetch_ohlcv(tf, limit=250)
                if df is None or len(df) < 50:
                    results[tf] = {"trend": "unknown", "score": 0, "weight": config["weight"]}
                    continue

                trend = self.detect_trend(df)
                weight = config["weight"]

                score = 0
                if "bullish" in trend:
                    score = 2 if "strong" in trend else 1
                elif "bearish" in trend:
                    score = -2 if "strong" in trend else -1

                weighted = score * weight
                total_score += weighted
                max_score += 2 * weight

                self.timeframes[tf]["trend"] = trend
                results[tf] = {
                    "trend": trend,
                    "score": score,
                    "weighted": weighted,
                    "weight": weight,
                    "ema9": round(float(df["close"].ewm(span=9, adjust=False).mean().iloc[-1]), 2),
                    "ema21": round(float(df["close"].ewm(span=21, adjust=False).mean().iloc[-1]), 2),
                    "ema50": round(float(df["close"].ewm(span=50, adjust=False).mean().iloc[-1]), 2),
                }

            # Confluence score: -100 to +100
            confluence_pct = (total_score / max_score * 100) if max_score > 0 else 0

            if confluence_pct > 50:
                mtf_bias = "strong_bullish"
            elif confluence_pct > 20:
                mtf_bias = "bullish"
            elif confluence_pct < -50:
                mtf_bias = "strong_bearish"
            elif confluence_pct < -20:
                mtf_bias = "bearish"
            else:
                mtf_bias = "neutral"

            return {
                "timeframes": results,
                "total_score": total_score,
                "max_score": max_score,
                "confluence_pct": round(confluence_pct, 1),
                "mtf_bias": mtf_bias,
            }
        except Exception as e:
            logger.error(f"MTF analysis error: {e}")
            return {"mtf_bias": "neutral", "error": str(e)}

    # ═══════════════════════════════════════════
    # 2. OBV + Divergence Detection
    # ═══════════════════════════════════════════

    def calculate_obv(self, df: pd.DataFrame) -> Dict:
        """On-Balance Volume + divergence detection"""
        try:
            if df is None or len(df) < 20:
                return {"obv": 0, "divergence": "none"}

            obv = [0]
            for i in range(1, len(df)):
                if df["close"].iloc[i] > df["close"].iloc[i - 1]:
                    obv.append(obv[-1] + df["volume"].iloc[i])
                elif df["close"].iloc[i] < df["close"].iloc[i - 1]:
                    obv.append(obv[-1] - df["volume"].iloc[i])
                else:
                    obv.append(obv[-1])

            obv_series = pd.Series(obv)

            # آخر 20 شمعة: هل السعر بيرتفع بس OBV بينخفض؟ = Bearish Divergence
            lookback = min(20, len(df) - 1)
            price_start = float(df["close"].iloc[-lookback])
            price_end = float(df["close"].iloc[-1])
            obv_start = float(obv_series.iloc[-lookback])
            obv_end = float(obv_series.iloc[-1])

            price_up = price_end > price_start
            obv_up = obv_end > obv_start

            divergence = "none"
            if price_up and not obv_up:
                divergence = "bearish"  # السعر يصعد لكن الحجم ينخفض = ضعف
            elif not price_up and obv_up:
                divergence = "bullish"  # السعر ينخفض لكن الحجم يرتفع = قوة مخفية

            return {
                "obv_current": round(float(obv_series.iloc[-1]), 2),
                "obv_trend": "up" if obv_up else "down",
                "price_trend": "up" if price_up else "down",
                "divergence": divergence,
            }
        except Exception as e:
            logger.warning(f"OBV error: {e}")
            return {"obv": 0, "divergence": "none"}

    # ═══════════════════════════════════════════
    # 3. Fibonacci Retracement Levels
    # ═══════════════════════════════════════════

    def calculate_fibonacci(self, df: pd.DataFrame, lookback: int = 100) -> Dict:
        """يحسب مستويات فيبوناتشي من آخر swing"""
        try:
            if df is None or len(df) < 20:
                return {"levels": {}, "current_level": "unknown"}

            window = df.tail(lookback)
            swing_high = float(window["high"].max())
            swing_low = float(window["low"].min())
            current = float(df["close"].iloc[-1])

            if swing_high <= swing_low:
                return {"levels": {}, "current_level": "unknown"}

            diff = swing_high - swing_low

            # Retracement levels
            levels = {
                "0.0": round(swing_high, 2),
                "0.236": round(swing_high - diff * 0.236, 2),
                "0.382": round(swing_high - diff * 0.382, 2),
                "0.5": round(swing_high - diff * 0.5, 2),
                "0.618": round(swing_high - diff * 0.618, 2),
                "0.786": round(swing_high - diff * 0.786, 2),
                "1.0": round(swing_low, 2),
            }

            # فين السعر حالياً؟
            current_level = "above_0"
            for fib, price in sorted(levels.items(), key=lambda x: -float(x[0])):
                if current >= price:
                    current_level = fib
                    break

            # Extension levels
            ext_levels = {
                "1.272": round(swing_low - diff * 0.272, 2),
                "1.618": round(swing_low - diff * 0.618, 2),
            }

            # Key zones
            golden_zone_low = levels["0.5"]
            golden_zone_high = levels["0.618"]
            in_golden_zone = golden_zone_low <= current <= golden_zone_high

            return {
                "swing_high": round(swing_high, 2),
                "swing_low": round(swing_low, 2),
                "levels": levels,
                "extension_levels": ext_levels,
                "current_level": current_level,
                "current_price": round(current, 2),
                "in_golden_zone": in_golden_zone,
                "golden_zone": f"${golden_zone_low:.2f} - ${golden_zone_high:.2f}",
            }
        except Exception as e:
            logger.warning(f"Fibonacci error: {e}")
            return {"levels": {}, "current_level": "unknown"}

    # ═══════════════════════════════════════════
    # 4. Heikin Ashi Analysis
    # ═══════════════════════════════════════════

    def calculate_heikin_ashi(self, df: pd.DataFrame) -> Dict:
        """Heikin Ashi: يصفّي الضوضاء ويحدد الاتجاه بدقة"""
        try:
            if df is None or len(df) < 10:
                return {"trend": "unknown", "consecutive_green": 0, "consecutive_red": 0}

            ha_df = pd.DataFrame(index=df.index)
            ha_df["close"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4

            ha_open = [float((df["open"].iloc[0] + df["close"].iloc[0]) / 2)]
            for i in range(1, len(df)):
                ha_open.append(float((ha_open[i - 1] + ha_df["close"].iloc[i - 1]) / 2))
            ha_df["open"] = ha_open
            ha_df["high"] = df[["high", "open", "close"]].max(axis=1).values
            ha_df["low"] = df[["low", "open", "close"]].min(axis=1).values

            # Count consecutive green/red candles
            last_green = 0
            last_red = 0
            for i in range(len(ha_df) - 1, -1, -1):
                if ha_df["close"].iloc[i] > ha_df["open"].iloc[i]:
                    last_green += 1
                    last_red = 0
                elif ha_df["close"].iloc[i] < ha_df["open"].iloc[i]:
                    last_red += 1
                    last_green = 0
                else:
                    break

            # Trend
            ha_close = float(ha_df["close"].iloc[-1])
            ha_open = float(ha_df["open"].iloc[-1])
            prev_ha_close = float(ha_df["close"].iloc[-2]) if len(ha_df) > 1 else ha_close

            # Strong trend: 3+ consecutive same color + small wick
            if last_green >= 3:
                trend = "strong_bullish"
            elif last_red >= 3:
                trend = "strong_bearish"
            elif ha_close > ha_open:
                trend = "bullish"
            elif ha_close < ha_open:
                trend = "bearish"
            else:
                trend = "neutral"

            # Doji detection (indecision)
            body = abs(ha_close - ha_open)
            total_range = float(ha_df["high"].iloc[-1] - ha_df["low"].iloc[-1])
            is_doji = body < total_range * 0.1 if total_range > 0 else False

            return {
                "trend": trend,
                "consecutive_green": last_green,
                "consecutive_red": last_red,
                "ha_close": round(ha_close, 2),
                "ha_open": round(ha_open, 2),
                "is_doji": is_doji,
                "body_size": round(body, 2),
            }
        except Exception as e:
            logger.warning(f"Heikin Ashi error: {e}")
            return {"trend": "unknown", "consecutive_green": 0, "consecutive_red": 0}

    # ═══════════════════════════════════════════
    # 5. Stochastic Oscillator (5-3-3 for scalping)
    # ═══════════════════════════════════════════

    def calculate_stochastic(self, df: pd.DataFrame, k_period: int = 5, d_period: int = 3) -> Dict:
        """Stochastic 5-3-3 للمتداول اللحظي (سكالبينج)"""
        try:
            if df is None or len(df) < k_period + d_period + 3:
                return {"k": 50, "d": 50, "signal": "neutral"}

            low_min = df["low"].rolling(k_period).min()
            high_max = df["high"].rolling(k_period).max()
            range_val = high_max - low_min
            range_val = range_val.replace(0, 1e-10)

            k = ((df["close"] - low_min) / range_val) * 100
            d = k.rolling(d_period).mean()

            current_k = float(k.iloc[-1])
            current_d = float(d.iloc[-1])
            prev_k = float(k.iloc[-2]) if len(k) > 1 else current_k

            signal = "neutral"
            # Oversold + turning up = buy
            if current_k < 20 and current_k > prev_k:
                signal = "buy"
            # Overbought + turning down = sell
            elif current_k > 80 and current_k < prev_k:
                signal = "sell"
            # Crossover
            elif current_k > current_d and prev_k <= float(d.iloc[-2]) if len(d) > 1 else False:
                signal = "buy"
            elif current_k < current_d and prev_k >= float(d.iloc[-2]) if len(d) > 1 else False:
                signal = "sell"

            return {
                "k": round(current_k, 1),
                "d": round(current_d, 1),
                "signal": signal,
                "zone": "oversold" if current_k < 20 else "overbought" if current_k > 80 else "neutral",
            }
        except Exception as e:
            logger.warning(f"Stochastic error: {e}")
            return {"k": 50, "d": 50, "signal": "neutral"}

    # ═══════════════════════════════════════════
    # 6. Full MTF + Advanced Analysis
    # ═══════════════════════════════════════════

    def analyze_full(self, fetcher) -> Dict:
        """تحليل شامل: MTF + OBV + Fibonacci + Heikin Ashi + Stochastic"""
        try:
            mtf = self.analyze_mtf(fetcher)

            # 1h data for detailed analysis
            df_1h = fetcher.fetch_ohlcv("1h", limit=200)
            obv = self.calculate_obv(df_1h) if df_1h is not None else {"divergence": "none"}
            fib = self.calculate_fibonacci(df_1h) if df_1h is not None else {"current_level": "unknown"}
            ha = self.calculate_heikin_ashi(df_1h) if df_1h is not None else {"trend": "unknown"}

            # 5m data for stochastic
            df_5m = fetcher.fetch_ohlcv("5m", limit=100)
            stoch = self.calculate_stochastic(df_5m) if df_5m is not None else {"signal": "neutral"}

            # Combined bias
            bias_votes = 0
            mtf_bias = mtf.get("mtf_bias", "neutral")
            if "bullish" in mtf_bias: bias_votes += 3
            if "bearish" in mtf_bias: bias_votes -= 3

            ha_trend = ha.get("trend", "neutral")
            if "bullish" in ha_trend: bias_votes += 2
            if "bearish" in ha_trend: bias_votes -= 2

            obv_div = obv.get("divergence", "none")
            if obv_div == "bullish": bias_votes += 2
            if obv_div == "bearish": bias_votes -= 2

            stoch_sig = stoch.get("signal", "neutral")
            if stoch_sig == "buy": bias_votes += 1
            if stoch_sig == "sell": bias_votes -= 1

            combined_bias = "neutral"
            if bias_votes > 3: combined_bias = "bullish"
            elif bias_votes > 5: combined_bias = "strong_bullish"
            elif bias_votes < -3: combined_bias = "bearish"
            elif bias_votes < -5: combined_bias = "strong_bearish"

            return {
                "mtf": mtf,
                "obv": obv,
                "fibonacci": fib,
                "heikin_ashi": ha,
                "stochastic": stoch,
                "combined_bias": combined_bias,
                "bias_score": bias_votes,
            }
        except Exception as e:
            logger.error(f"MTF full analysis error: {e}")
            return {"combined_bias": "neutral", "error": str(e)}

    def get_mtf_confidence_adjustment(self, mtf_data: Dict, signal_type: str) -> float:
        """يعدل ثقة الإشارة بناء على MTF confluence"""
        try:
            adjustment = 0.0
            is_buy = signal_type.lower() in ("buy", "long", "bullish")

            mtf_bias = mtf_data.get("mtf", {}).get("mtf_bias", "neutral")
            confluence_pct = mtf_data.get("mtf", {}).get("confluence_pct", 0)

            # MTF alignment
            if is_buy and "bullish" in mtf_bias:
                adjustment += min(abs(confluence_pct) * 0.1, 5.0)
            elif not is_buy and "bearish" in mtf_bias:
                adjustment += min(abs(confluence_pct) * 0.1, 5.0)
            elif is_buy and "bearish" in mtf_bias:
                adjustment -= min(abs(confluence_pct) * 0.1, 5.0)
            elif not is_buy and "bullish" in mtf_bias:
                adjustment -= min(abs(confluence_pct) * 0.1, 5.0)

            # Heikin Ashi
            ha_trend = mtf_data.get("heikin_ashi", {}).get("trend", "neutral")
            if is_buy and "bullish" in ha_trend: adjustment += 2.0
            elif not is_buy and "bearish" in ha_trend: adjustment += 2.0
            elif is_buy and "bearish" in ha_trend: adjustment -= 2.0
            elif not is_buy and "bullish" in ha_trend: adjustment -= 2.0

            # OBV divergence
            obv_div = mtf_data.get("obv", {}).get("divergence", "none")
            if is_buy and obv_div == "bullish": adjustment += 3.0
            elif not is_buy and obv_div == "bearish": adjustment += 3.0
            elif is_buy and obv_div == "bearish": adjustment -= 2.0
            elif not is_buy and obv_div == "bullish": adjustment -= 2.0

            # Fibonacci golden zone
            fib = mtf_data.get("fibonacci", {})
            if fib.get("in_golden_zone"):
                if is_buy:
                    adjustment += 2.0  # منطقة ذهبية = دخول جيد للشراء
                else:
                    adjustment += 1.0

            # Stochastic
            stoch_sig = mtf_data.get("stochastic", {}).get("signal", "neutral")
            if is_buy and stoch_sig == "buy": adjustment += 2.0
            elif not is_buy and stoch_sig == "sell": adjustment += 2.0

            adjustment = max(-12.0, min(12.0, adjustment))
            return round(adjustment, 1)
        except Exception as e:
            logger.warning(f"MTF confidence error: {e}")
            return 0.0

    def format_mtf_report(self, data: Dict) -> str:
        """تقرير MTF منسق للتلغرام"""
        try:
            report = "📊 تحليل MTF | صياد الشمعات\n"
            report += "━━━━━━━━━━━━━━━━━━━━\n"

            # MTF
            mtf = data.get("mtf", {})
            bias = mtf.get("mtf_bias", "neutral")
            bias_emoji = {"strong_bullish": "🟢🟢", "bullish": "🟢", "neutral": "🟡", "bearish": "🔴", "strong_bearish": "🔴🔴"}.get(bias, "🟡")
            report += f"{bias_emoji} MTF Bias: {bias.upper()}\n"
            report += f"📊 Confluence: {mtf.get('confluence_pct', 0)}%\n\n"

            tfs = mtf.get("timeframes", {})
            for tf in ["4h", "1h", "15m", "5m"]:
                tf_data = tfs.get(tf, {})
                tf_trend = tf_data.get("trend", "?")
                tf_emoji = {"strong_bullish": "🟢🟢", "bullish": "🟢", "neutral": "🟡", "bearish": "🔴", "strong_bearish": "🔴🔴"}.get(tf_trend, "🟡")
                report += f"   {tf_emoji} {tf}: {tf_trend}\n"
            report += "\n"

            # Heikin Ashi
            ha = data.get("heikin_ashi", {})
            ha_emoji = "🟢" if "bullish" in ha.get("trend", "") else "🔴" if "bearish" in ha.get("trend", "") else "🟡"
            report += f"{ha_emoji} Heikin Ashi: {ha.get('trend', '?')}\n"
            report += f"   Green: {ha.get('consecutive_green', 0)} | Red: {ha.get('consecutive_red', 0)}\n"
            if ha.get("is_doji"):
                report += "   ⚠️ Doji = تردد\n"
            report += "\n"

            # OBV
            obv = data.get("obv", {})
            div_emoji = "🟢" if obv.get("divergence") == "bullish" else "🔴" if obv.get("divergence") == "bearish" else "➡️"
            report += f"{div_emoji} OBV Divergence: {obv.get('divergence', 'none')}\n\n"

            # Fibonacci
            fib = data.get("fibonacci", {})
            if fib.get("levels"):
                report += f"📐 Fibonacci:\n"
                report += f"   Swing High: ${fib.get('swing_high', 0):.2f}\n"
                report += f"   Swing Low: ${fib.get('swing_low', 0):.2f}\n"
                report += f"   Current Level: {fib.get('current_level', '?')}\n"
                if fib.get("in_golden_zone"):
                    report += f"   ⭐ في المنطقة الذهبية (50%-61.8%)\n"
                report += "\n"

            # Stochastic
            stoch = data.get("stochastic", {})
            stoch_emoji = "🟢" if stoch.get("signal") == "buy" else "🔴" if stoch.get("signal") == "sell" else "🟡"
            report += f"{stoch_emoji} Stochastic (5-3-3): K={stoch.get('k', 50)} D={stoch.get('d', 50)}\n"
            report += f"   Signal: {stoch.get('signal', 'neutral')} | Zone: {stoch.get('zone', 'neutral')}\n\n"

            # Combined
            combined = data.get("combined_bias", "neutral")
            combined_emoji = {"strong_bullish": "🟢🟢", "bullish": "🟢", "neutral": "🟡", "bearish": "🔴", "strong_bearish": "🔴🔴"}.get(combined, "🟡")
            report += f"🎯 Combined Bias: {combined_emoji} {combined.upper()} (score: {data.get('bias_score', 0)})\n\n"

            report += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            report += "📊 صياد الشمعات | Candle Hunter"

            return report
        except Exception as e:
            logger.error(f"MTF format error: {e}")
            return "⚠️ خطأ في تنسيق تقرير MTF"
