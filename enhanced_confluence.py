"""
صياد الشمعات | Candle Hunter - Enhanced Multi-Indicator Confluence
محرّك تطابق محسّن: يحسب توافق كل المؤشرات على أطر زمنية متعددة
"""
import logging
import pandas as pd
from typing import Dict, List, Tuple
from indicators import (
    rsi, macd, bollinger_bands, ema, sma, stochastic, atr, adx,
    ichimoku, vwap, williams_r, cci, mfi, obv, parabolic_sar,
    supertrend, cmf, elder_ray, keltner_channels, trix
)

logger = logging.getLogger(__name__)


class EnhancedConfluence:
    """محرّك التطابق المحسّن — يقيس توافق 20+ مؤشر"""

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def _score_indicators(self, df: pd.DataFrame) -> Dict:
        """يحسب نتيجة كل مؤشر على إطار زمني واحد"""
        scores = {"BUY": 0, "SELL": 0, "NEUTRAL": 0}
        details = []

        if df.empty or len(df) < 50:
            return {"scores": scores, "details": details, "total": 0}

        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        last_idx = len(df) - 1

        # 1. RSI
        try:
            rsi_val = rsi(df, 14).iloc[last_idx]
            if rsi_val < 30:
                scores["BUY"] += 1; details.append(("RSI", "BUY", f"{rsi_val:.1f} — تشبع بيعي"))
            elif rsi_val > 70:
                scores["SELL"] += 1; details.append(("RSI", "SELL", f"{rsi_val:.1f} — تشبع شرائي"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 2. MACD
        try:
            macd_line, signal_line, hist = macd(df)
            if hist.iloc[last_idx] > 0 and macd_line.iloc[last_idx] > signal_line.iloc[last_idx]:
                scores["BUY"] += 1; details.append(("MACD", "BUY", "تقاطع صاعد"))
            elif hist.iloc[last_idx] < 0 and macd_line.iloc[last_idx] < signal_line.iloc[last_idx]:
                scores["SELL"] += 1; details.append(("MACD", "SELL", "تقاطع هابط"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 3. Bollinger Bands
        try:
            upper, middle, lower, _ = bollinger_bands(df, 20, 2.0)
            price = close.iloc[last_idx]
            if price <= lower.iloc[last_idx]:
                scores["BUY"] += 1; details.append(("Bollinger", "BUY", "سعر تحت الباند السفلي"))
            elif price >= upper.iloc[last_idx]:
                scores["SELL"] += 1; details.append(("Bollinger", "SELL", "سعر فوق الباند العلوي"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 4. EMA Cross (9/21)
        try:
            ema9 = ema(df, 9).iloc[last_idx]
            ema21 = ema(df, 21).iloc[last_idx]
            if ema9 > ema21:
                scores["BUY"] += 1; details.append(("EMA 9/21", "BUY", "تقاطع صاعد"))
            else:
                scores["SELL"] += 1; details.append(("EMA 9/21", "SELL", "تقاطع هابط"))
        except: pass

        # 5. SMA Cross (50/200)
        try:
            sma50 = sma(df, 50).iloc[last_idx]
            sma200 = sma(df, 200).iloc[last_idx] if len(df) >= 200 else sma50
            if sma50 > sma200:
                scores["BUY"] += 1; details.append(("SMA 50/200", "BUY", "ترند صاعد"))
            else:
                scores["SELL"] += 1; details.append(("SMA 50/200", "SELL", "ترند هابط"))
        except: pass

        # 6. Stochastic
        try:
            k, d = stochastic(df)
            k_val = k.iloc[last_idx]
            if k_val < 20 and k.iloc[last_idx] > d.iloc[last_idx]:
                scores["BUY"] += 1; details.append(("Stochastic", "BUY", f"{k_val:.1f} — تشبع بيعي + تقاطع"))
            elif k_val > 80 and k.iloc[last_idx] < d.iloc[last_idx]:
                scores["SELL"] += 1; details.append(("Stochastic", "SELL", f"{k_val:.1f} — تشبع شرائي + تقاطع"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 7. ADX (trend strength)
        try:
            adx_val, plus_di, minus_di = adx(df, 14)
            if adx_val.iloc[last_idx] > 25:
                if plus_di.iloc[last_idx] > minus_di.iloc[last_idx]:
                    scores["BUY"] += 1; details.append(("ADX", "BUY", f"ADX={adx_val.iloc[last_idx]:.1f} — ترند قوي صاعد"))
                else:
                    scores["SELL"] += 1; details.append(("ADX", "SELL", f"ADX={adx_val.iloc[last_idx]:.1f} — ترند قوي هابط"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 8. Ichimoku
        try:
            ich = ichimoku(df)
            price = close.iloc[last_idx]
            span_a = ich['span_a'].iloc[last_idx]
            span_b = ich['span_b'].iloc[last_idx]
            if price > span_a and price > span_b:
                scores["BUY"] += 1; details.append(("Ichimoku", "BUY", "فوق السحابة"))
            elif price < span_a and price < span_b:
                scores["SELL"] += 1; details.append(("Ichimoku", "SELL", "تحت السحابة"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 9. Supertrend
        try:
            st_val, st_dir = supertrend(df, 10, 3.0)
            if st_dir.iloc[last_idx] == 1:
                scores["BUY"] += 1; details.append(("Supertrend", "BUY", "إشارة صاعدة"))
            else:
                scores["SELL"] += 1; details.append(("Supertrend", "SELL", "إشارة هابطة"))
        except: pass

        # 10. Parabolic SAR
        try:
            sar_val = parabolic_sar(df)
            price = close.iloc[last_idx]
            if price > sar_val.iloc[last_idx]:
                scores["BUY"] += 1; details.append(("PSAR", "BUY", "سعر فوق SAR — صاعد"))
            else:
                scores["SELL"] += 1; details.append(("PSAR", "SELL", "سعر تحت SAR — هابط"))
        except: pass

        # 11. CCI
        try:
            cci_val = cci(df, 20).iloc[last_idx]
            if cci_val < -100:
                scores["BUY"] += 1; details.append(("CCI", "BUY", f"{cci_val:.1f} — تشبع بيعي"))
            elif cci_val > 100:
                scores["SELL"] += 1; details.append(("CCI", "SELL", f"{cci_val:.1f} — تشبع شرائي"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 12. Williams %R
        try:
            wr_val = williams_r(df, 14).iloc[last_idx]
            if wr_val < -80:
                scores["BUY"] += 1; details.append(("Williams %R", "BUY", f"{wr_val:.1f} — تشبع بيعي"))
            elif wr_val > -20:
                scores["SELL"] += 1; details.append(("Williams %R", "SELL", f"{wr_val:.1f} — تشبع شرائي"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 13. MFI
        try:
            mfi_val = mfi(df, 14).iloc[last_idx]
            if mfi_val < 20:
                scores["BUY"] += 1; details.append(("MFI", "BUY", f"{mfi_val:.1f} — تدفق أموال سالب"))
            elif mfi_val > 80:
                scores["SELL"] += 1; details.append(("MFI", "SELL", f"{mfi_val:.1f} — تدفق أموال موجب"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 14. OBV trend
        try:
            obv_val = obv(df)
            if obv_val.iloc[last_idx] > obv_val.iloc[last_idx - 5]:
                scores["BUY"] += 1; details.append(("OBV", "BUY", "حجم تراكمي صاعد"))
            else:
                scores["SELL"] += 1; details.append(("OBV", "SELL", "حجم تراكمي هابط"))
        except: pass

        # 15. CMF
        try:
            cmf_val = cmf(df, 20).iloc[last_idx]
            if cmf_val > 0.05:
                scores["BUY"] += 1; details.append(("CMF", "BUY", f"{cmf_val:.2f} — ضغط شرائي"))
            elif cmf_val < -0.05:
                scores["SELL"] += 1; details.append(("CMF", "SELL", f"{cmf_val:.2f} — ضغط بيعي"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 16. Elder Ray (Bull/Bear Power)
        try:
            bull_power, bear_power = elder_ray(df, 13)
            if bull_power.iloc[last_idx] > 0 and bull_power.iloc[last_idx] > abs(bear_power.iloc[last_idx]):
                scores["BUY"] += 1; details.append(("Elder Ray", "BUY", "قوة الثور > الدببة"))
            elif bear_power.iloc[last_idx] < 0 and abs(bear_power.iloc[last_idx]) > bull_power.iloc[last_idx]:
                scores["SELL"] += 1; details.append(("Elder Ray", "SELL", "قوة الدببة > الثور"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 17. TRIX
        try:
            trix_val = trix(df, 12).iloc[last_idx]
            if trix_val > 0:
                scores["BUY"] += 1; details.append(("TRIX", "BUY", f"{trix_val:.4f} — زخم صاعد"))
            else:
                scores["SELL"] += 1; details.append(("TRIX", "SELL", f"{trix_val:.4f} — زخم هابط"))
        except: pass

        # 18. Keltner Channels
        try:
            k_upper, k_middle, k_lower = keltner_channels(df, 20, 10, 2.0)
            price = close.iloc[last_idx]
            if price <= k_lower.iloc[last_idx]:
                scores["BUY"] += 1; details.append(("Keltner", "BUY", "سعر تحت القناة السفلى"))
            elif price >= k_upper.iloc[last_idx]:
                scores["SELL"] += 1; details.append(("Keltner", "SELL", "سعر فوق القناة العليا"))
            else:
                scores["NEUTRAL"] += 1
        except: pass

        # 19. ATR (volatility — not directional but adjusts confidence)
        try:
            atr_val = atr(df, 14).iloc[last_idx]
            if atr_val > close.iloc[last_idx] * 0.01:
                details.append(("ATR", "VOLATILE", f"ATR={atr_val:.2f} — تذبذب عالي"))
        except: pass

        # 20. VWAP
        try:
            vwap_val = vwap(df).iloc[last_idx]
            price = close.iloc[last_idx]
            if price > vwap_val:
                scores["BUY"] += 1; details.append(("VWAP", "BUY", "فوق VWAP — صاعد"))
            else:
                scores["SELL"] += 1; details.append(("VWAP", "SELL", "تحت VWAP — هابط"))
        except: pass

        total = sum(scores.values())
        return {"scores": scores, "details": details, "total": total}

    def analyze(self, timeframes: List[str] = None) -> Dict:
        """
        يحلل التطابق على أطر زمنية متعددة
        Returns: direction, confidence, agreement_score, per_timeframe details
        """
        if timeframes is None:
            timeframes = ["5m", "15m", "1h", "4h", "1d"]

        per_tf: Dict[str, Dict] = {}
        total_buy = 0
        total_sell = 0
        total_neutral = 0
        all_details = []

        for tf in timeframes:
            try:
                df = self.fetcher.fetch_ohlcv("XAU/USD", tf, 200)
                if df.empty or len(df) < 50:
                    continue

                result = self._score_indicators(df)
                scores = result["scores"]
                per_tf[tf] = result

                total_buy += scores["BUY"]
                total_sell += scores["SELL"]
                total_neutral += scores["NEUTRAL"]

                # Determine direction for this TF
                if scores["BUY"] > scores["SELL"]:
                    all_details.append((tf, "BUY", scores["BUY"], scores["SELL"]))
                elif scores["SELL"] > scores["BUY"]:
                    all_details.append((tf, "SELL", scores["BUY"], scores["SELL"]))
                else:
                    all_details.append((tf, "NEUTRAL", scores["BUY"], scores["SELL"]))

            except Exception as e:
                logger.warning(f"Confluence analysis for {tf}: {e}")

        # Final direction
        total_directional = total_buy + total_sell
        if total_directional == 0:
            direction = "NEUTRAL"
            confidence = 0
        else:
            buy_pct = total_buy / total_directional * 100
            sell_pct = total_sell / total_directional * 100

            if buy_pct > 70:
                direction = "BUY"
                confidence = min(95, 60 + buy_pct * 0.35)
            elif sell_pct > 70:
                direction = "SELL"
                confidence = min(95, 60 + sell_pct * 0.35)
            elif buy_pct > 55:
                direction = "BUY"
                confidence = 50 + buy_pct * 0.2
            elif sell_pct > 55:
                direction = "SELL"
                confidence = 50 + sell_pct * 0.2
            else:
                direction = "NEUTRAL"
                confidence = 40

        # Agreement score: how many TFs agree
        tf_directions = [d[1] for d in all_details]
        agree_count = max(tf_directions.count("BUY"), tf_directions.count("SELL"))
        agreement_score = (agree_count / len(timeframes) * 100) if timeframes else 0

        return {
            "direction": direction,
            "confidence": round(confidence, 1),
            "agreement_score": round(agreement_score, 1),
            "total_buy": total_buy,
            "total_sell": total_sell,
            "total_neutral": total_neutral,
            "per_timeframe": per_tf,
            "tf_summary": all_details,
        }

    def format_report(self, data: Dict) -> str:
        """تقرير التطابق المحسّن بصيغة عربية"""
        direction = data["direction"]
        dir_emoji = "🟢 شراء" if direction == "BUY" else "🔴 بيع" if direction == "SELL" else "⚪ محايد"
        confidence = data["confidence"]
        agreement = data["agreement_score"]

        msg = "🔬 تحليل التطابق المحسّن (20 مؤشر)\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🎯 الاتجاه: {dir_emoji}\n"
        msg += f"📊 الثقة: {confidence:.1f}%\n"
        msg += f"🤝 توافق الأطر: {agreement:.0f}%\n"
        msg += f"🟢 مؤشرات شرائية: {data['total_buy']}\n"
        msg += f"🔴 مؤشرات بيعية: {data['total_sell']}\n"
        msg += f"⚪ محايدة: {data['total_neutral']}\n\n"

        # Per timeframe
        tf_names = {"5m": "5 دقائق", "15m": "15 دقيقة", "1h": "1 ساعة", "4h": "4 ساعات", "1d": "يومي"}
        msg += "📋 التفصيل حسب الإطار:\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for tf, dir_tf, buy_n, sell_n in data["tf_summary"]:
            emoji = "🟢" if dir_tf == "BUY" else "🔴" if dir_tf == "SELL" else "⚪"
            name = tf_names.get(tf, tf)
            msg += f"{emoji} {name}: شراء {buy_n} / بيع {sell_n}\n"

        # Top indicators from 1h (most representative)
        if "1h" in data["per_timeframe"]:
            details = data["per_timeframe"]["1h"]["details"]
            if details:
                msg += "\n🔑 أبرز المؤشرات (1h):\n"
                for name, dir_i, desc in details[:8]:
                    emoji = "🟢" if dir_i == "BUY" else "🔴" if dir_i == "SELL" else "⚪"
                    msg += f"{emoji} {name}: {desc}\n"

        msg += "\n🤖 صياد الشمعات | Candle Hunter"
        return msg

    def enhance_signal(self, signal: Dict, analysis: Dict) -> Dict:
        """يعزز ثقة الإشارة بناءً على التطابق المحسّن"""
        if analysis["direction"] == "NEUTRAL":
            return signal

        signal_dir = signal.get("signal_type", "")
        if signal_dir != analysis["direction"]:
            # Contradiction — reduce confidence
            original = signal.get("confidence", 50)
            signal["confidence"] = max(30, original - 15)
            signal["confluence_conflict"] = True
            logger.info(f"⚠️ Confluence conflict: signal={signal_dir}, analysis={analysis['direction']} → -15%")
            return signal

        # Agreement — boost confidence based on agreement score
        original = signal.get("confidence", 50)
        agreement = analysis["agreement_score"]

        if agreement >= 80:
            boost = 20
        elif agreement >= 60:
            boost = 15
        elif agreement >= 40:
            boost = 10
        else:
            boost = 5

        signal["confidence"] = min(95, original + boost)
        signal["confluence_agreement"] = agreement
        signal["confluence_boost"] = boost
        logger.info(f"✅ Enhanced: {original}% → {signal['confidence']}% (+{boost}% from {agreement:.0f}% agreement)")

        return signal
