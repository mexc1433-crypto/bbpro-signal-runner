"""
صياد الشمعات | Candle Hunter - Advanced Signal Filters
فلتر السيولة والتذبذب + فلتر الساعات النشطة
"""
import logging
from datetime import datetime
from typing import Dict, Optional
import pandas as pd
from indicators import atr

logger = logging.getLogger(__name__)


class VolatilityFilter:
    """فلتر السيولة والتذبذب — يمنع الإشارات في ظروف غير مثالية"""

    def __init__(self):
        # ATR كنسبة من السعر — النطاق المثالي
        self.atr_min_pct = 0.15   # أقل من كده = لا حركة =skip
        self.atr_max_pct = 1.5    # أعلى من كده = تذبذب خطير =skip

    def check(self, df: pd.DataFrame, price: float) -> Dict:
        """يفحص السيولة والتذبذب. Returns: {ok: bool, reason: str, atr_pct: float}"""
        if df.empty or len(df) < 50 or price <= 0:
            return {"ok": False, "reason": "بيانات غير كافية", "atr_pct": 0}

        try:
            atr_val = atr(df, 14).iloc[-1]
            atr_pct = (atr_val / price) * 100

            if atr_pct < self.atr_min_pct:
                return {
                    "ok": False,
                    "reason": f"تذبذب منخفض جداً (ATR={atr_pct:.2f}%) — لا حركة",
                    "atr_pct": atr_pct
                }

            if atr_pct > self.atr_max_pct:
                return {
                    "ok": False,
                    "reason": f"تذبذب خطير (ATR={atr_pct:.2f}%) — تجنب",
                    "atr_pct": atr_pct
                }

            # تذبذب مثالي
            return {
                "ok": True,
                "reason": f"تذبذب طبيعي (ATR={atr_pct:.2f}%)",
                "atr_pct": atr_pct
            }
        except Exception as e:
            logger.warning(f"Volatility filter error: {e}")
            return {"ok": True, "reason": "تخطي الفلتر", "atr_pct": 0}


class ActiveHoursFilter:
    """فلتر الساعات النشطة — يعزز ثقة الإشارات في فترات السيولة العالية"""

    # فترات نشطة (UTC) — افتتاح لندن ونيويورك
    LONDON_OPEN = 7    # 10:00 Cairo = 07:00 UTC
    LONDON_CLOSE = 15  # 18:00 Cairo
    NY_OPEN = 12       # 15:00 Cairo = 12:00 UTC
    NY_CLOSE = 20      # 23:00 Cairo

    # ساعات ضعيفة — ندني الثقة بس ما نمنعش
    ASIAN_LOW = 0      # 03:00 Cairo
    ASIAN_HIGH = 5     # 08:00 Cairo

    def get_session_info(self, dt: datetime = None) -> Dict:
        """يحدد الجلسة النشطة والثقة الإضافية"""
        if dt is None:
            dt = datetime.utcnow()

        hour = dt.hour

        # جلسة لندن (10:00 - 18:00 Cairo)
        if self.LONDON_OPEN <= hour < self.LONDON_CLOSE:
            return {
                "session": "LONDON",
                "name": "لندن",
                "active": True,
                "confidence_boost": 10,
            }

        # جلسة نيويورك (15:00 - 23:00 Cairo)
        elif self.NY_OPEN <= hour < self.NY_CLOSE:
            return {
                "session": "NEW_YORK",
                "name": "نيويورك",
                "active": True,
                "confidence_boost": 12,
            }

        # تداخل لندن + نيويورك (15:00 - 18:00 Cairo) — أعلى سيولة
        elif self.NY_OPEN <= hour < self.LONDON_CLOSE:
            return {
                "session": "LONDON_NY_OVERLAP",
                "name": "لندن+نيويورك",
                "active": True,
                "confidence_boost": 15,
            }

        # الجلسة الآسيوية (03:00 - 08:00 Cairo) — سيولة ضعيفة
        elif self.ASIAN_LOW <= hour < self.ASIAN_HIGH:
            return {
                "session": "ASIAN",
                "name": "آسيا",
                "active": False,
                "confidence_boost": -5,
            }

        # ساعات ميتة
        else:
            return {
                "session": "DEAD",
                "name": "ساعات ضعيفة",
                "active": False,
                "confidence_boost": -10,
            }

    def apply(self, signal: Dict, dt: datetime = None) -> Dict:
        """يعدل ثقة الإشارة حسب الجلسة"""
        session_info = self.get_session_info(dt)

        original = signal.get("confidence", 50)
        boost = session_info["confidence_boost"]
        new_conf = max(20, min(95, original + boost))

        signal["confidence"] = new_conf
        signal["session"] = session_info["session"]
        signal["session_name"] = session_info["name"]

        logger.info(
            f"⏰ Session: {session_info['name']} "
            f"({'active' if session_info['active'] else 'slow'}) "
            f"→ confidence {original}% → {new_conf}% ({'+' if boost > 0 else ''}{boost}%)"
        )

        return signal


class TrendFilter:
    """فلتر اتجاه TREND فقط — يمنع الإشارات عكس الترند العام"""

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def get_higher_tf_trend(self) -> Dict:
        """يحدد الترند العام على فريم 4H و 1D"""
        trends = {}
        for tf in ["4h", "1d"]:
            try:
                df = self.fetcher.fetch_ohlcv("XAU/USD", tf, limit=100)
                if df.empty or len(df) < 50:
                    continue

                # EMA50 + EMA200 للترند العام
                from indicators import ema
                ema50 = ema(df, 50).iloc[-1]
                ema200 = ema(df, 200).iloc[-1] if len(df) >= 200 else ema(df, min(len(df)-1, 50)).iloc[-1]
                price = df['close'].iloc[-1]

                if price > ema50 > ema200:
                    trends[tf] = "BULLISH"
                elif price < ema50 < ema200:
                    trends[tf] = "BEARISH"
                else:
                    trends[tf] = "NEUTRAL"

            except Exception as e:
                logger.warning(f"TrendFilter error on {tf}: {e}")
                trends[tf] = "UNKNOWN"

        # الترند النهائي = agreement بين 4H و 1D
        if trends.get("4h") == trends.get("1d") and trends.get("4h") != "NEUTRAL":
            return {"trend": trends["4h"], "agreement": True, "details": trends}
        elif trends.get("4h") == "NEUTRAL" or trends.get("1d") == "NEUTRAL":
            return {"trend": "NEUTRAL", "agreement": False, "details": trends}
        else:
            return {"trend": "MIXED", "agreement": False, "details": trends}

    def check_signal(self, signal: Dict) -> Dict:
        """يفحص هل الإشارة مع الترند ولا ضده"""
        trend_data = self.get_higher_tf_trend()
        trend = trend_data["trend"]
        signal_dir = signal.get("signal_type", "")

        # لو الترند محايد أو مكسود — اسمح بكل الإشارات بس قلل الثقة
        if trend == "NEUTRAL" or trend == "MIXED" or trend == "UNKNOWN":
            signal["trend_aligned"] = False
            signal["trend"] = trend
            signal["confidence"] = max(30, signal.get("confidence", 50) - 5)
            return {"ok": True, "reason": f"ترند {trend} — ثقة مخفضة", "trend": trend}

        # لو الإشارة مع الترند — زود الثقة
        if (trend == "BULLISH" and signal_dir == "BUY") or (trend == "BEARISH" and signal_dir == "SELL"):
            signal["trend_aligned"] = True
            signal["trend"] = trend
            signal["confidence"] = min(95, signal.get("confidence", 50) + 8)
            logger.info(f"📈 Trend aligned: {signal_dir} in {trend} trend → +8% confidence")
            return {"ok": True, "reason": f"مع الترند {trend}", "trend": trend}

        # لو الإشارة عكس الترند — ارفضها
        signal["trend_aligned"] = False
        signal["trend"] = trend
        logger.info(f"🚫 Against trend: {signal_dir} in {trend} trend — REJECTED")
        return {"ok": False, "reason": f"عكس الترند {trend}", "trend": trend}
