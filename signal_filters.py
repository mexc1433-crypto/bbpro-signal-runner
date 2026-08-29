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
