"""
صياد الشمعات | Candle Hunter — Advanced Features
Features 3, 6, 8, 9, 10, 14 + Signal Cooldown
"""
import json
import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# FEATURE 3: MEXC Balance Check
# ═══════════════════════════════════════════════════
class BalanceChecker:
    """فحص رصيد MEXC قبل تنفيذ أي صفقة"""

    def __init__(self, auto_trader):
        self.auto_trader = auto_trader
        self.min_balance = float(os.getenv("MIN_MEXC_BALANCE", "10"))
        self.last_check = None
        self.last_balance = 0.0

    def check_owner_balance(self) -> Dict:
        """يفحص رصيد المالك — يرجع هل فيه رصيد كافي ولا لا"""
        try:
            if not self.auto_trader or not self.auto_trader.owner_client:
                return {"ok": False, "reason": "No MEXC client configured"}

            balance = self.auto_trader.owner_client.get_balance()
            if not balance.get("success"):
                return {"ok": False, "reason": "Balance API failed"}

            free = balance.get("free", 0)
            self.last_balance = free
            self.last_check = datetime.now()

            if free < self.min_balance:
                logger.warning(f"💰 Low MEXC balance: ${free:.2f} (min=${self.min_balance})")
                return {
                    "ok": False,
                    "reason": f"Insufficient balance: ${free:.2f} (min ${self.min_balance})",
                    "balance": free,
                }

            logger.info(f"✅ MEXC balance OK: ${free:.2f}")
            return {"ok": True, "balance": free}

        except Exception as e:
            logger.error(f"Balance check error: {e}")
            return {"ok": False, "reason": str(e)}

    def check_user_balance(self, telegram_id: int) -> Dict:
        """يفحص رصيد مستخدم قبل تنفيذ صفقة"""
        try:
            client = self.auto_trader._get_user_client(telegram_id)
            if not client:
                return {"ok": False, "reason": "No client for user"}

            balance = client.get_balance()
            if not balance.get("success"):
                return {"ok": False, "reason": "User balance API failed"}

            free = balance.get("free", 0)
            if free < self.min_balance:
                return {"ok": False, "reason": f"Low balance: ${free:.2f}", "balance": free}

            return {"ok": True, "balance": free}
        except Exception as e:
            return {"ok": False, "reason": str(e)}


# ═══════════════════════════════════════════════════
# FEATURE 6: Smart Position Sizing
# ═══════════════════════════════════════════════════
class SmartPositionSizer:
    """حجم الصفقة يتعادل حسب ثقة الإشارة"""

    def __init__(self):
        # خريطة الثقة → نسبة المخاطرة
        self.risk_map = {
            (95, 100): 2.5,   # ثقة عالية جداً = 2.5% مخاطرة
            (85, 94): 2.0,    # ثقة عالية = 2.0%
            (70, 84): 1.5,    # ثقة متوسطة = 1.5%
            (55, 69): 1.0,    # ثقة منخفضة = 1.0%
            (0, 54): 0.5,     # ثقة ضعيفة = 0.5% فقط
        }

    def get_risk_pct(self, confidence: float) -> float:
        """يرجع نسبة المخاطرة المناسبة حسب الثقة"""
        for (lo, hi), pct in self.risk_map.items():
            if lo <= confidence <= hi:
                return pct
        return 1.0  # افتراضي

    def calculate_size(self, balance: float, confidence: float, entry: float, sl: float) -> Dict:
        """يحسب حجم الصفقة الذكي"""
        risk_pct = self.get_risk_pct(confidence)
        risk_amount = balance * (risk_pct / 100)

        risk_price_pct = abs(entry - sl) / entry
        if risk_price_pct == 0:
            return {"ok": False, "error": "Invalid SL"}

        position_size = risk_amount / risk_price_pct
        amount = position_size / entry

        return {
            "ok": True,
            "risk_pct": risk_pct,
            "risk_amount": risk_amount,
            "position_size": position_size,
            "amount": round(amount, 2),
            "confidence": confidence,
        }


# ═══════════════════════════════════════════════════
# FEATURE 8: Conflict Resolution — إشارات متضادة
# ═══════════════════════════════════════════════════
class ConflictResolver:
    """لو فيه إشارتين عكسيتين، يختار الأعلى ثقة بس"""

    @staticmethod
    def resolve(signals: List[Dict]) -> List[Dict]:
        if not signals:
            return []

        # تجميع حسب الاتجاه
        buys = [s for s in signals if s.get("signal_type") == "BUY"]
        sells = [s for s in signals if s.get("signal_type") == "SELL"]

        # لو في اتجاه واحد بس — مفيش تعارض
        if not buys or not sells:
            return signals

        # في تعارض — اختار الأعلى ثقة
        best_buy = max(buys, key=lambda s: s.get("confidence", 0))
        best_sell = max(sells, key=lambda s: s.get("confidence", 0))

        if best_buy.get("confidence", 0) > best_sell.get("confidence", 0):
            logger.info(f"⚔️ Conflict resolved: BUY ({best_buy['confidence']}%) > SELL ({best_sell['confidence']}%)")
            return [best_buy]
        else:
            logger.info(f"⚔️ Conflict resolved: SELL ({best_sell['confidence']}%) > BUY ({best_buy['confidence']}%)")
            return [best_sell]


# ═══════════════════════════════════════════════════
# FEATURE 9: Fear & Greed Index
# ═══════════════════════════════════════════════════
class FearGreedIndex:
    """مؤشر الخوف والطمع — من alternative.me API"""

    def __init__(self):
        self.cache = None
        self.cache_time = None
        self.cache_ttl = 3600  # ساعة

    def get_index(self) -> Optional[Dict]:
        try:
            if self.cache and self.cache_time:
                if (datetime.now() - self.cache_time).seconds < self.cache_ttl:
                    return self.cache

            resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("data", [{}])[0]
                value = int(data.get("value", 50))
                classification = data.get("value_classification", "Neutral")

                label_ar = {
                    "Extreme Fear": "خوف شديد",
                    "Fear": "خوف",
                    "Neutral": "محايد",
                    "Greed": "طمع",
                    "Extreme Greed": "طمع شديد",
                }.get(classification, "محايد")

                result = {
                    "value": value,
                    "classification": classification,
                    "label_ar": label_ar,
                }
                self.cache = result
                self.cache_time = datetime.now()
                logger.info(f"😱 Fear & Greed: {value} ({label_ar})")
                return result
        except Exception as e:
            logger.warning(f"Fear & Greed API failed: {e}")
            return None

    def should_adjust_confidence(self, signal: Dict) -> Dict:
        """يعدل ثقة الإشارة حسب الخوف والطمع"""
        fg = self.get_index()
        if not fg:
            return {"adjusted": False}

        value = fg["value"]
        signal_type = signal.get("signal_type", "")
        old_conf = signal.get("confidence", 50)

        # خوف شديد = فرصة شراء (contrarian)
        if value < 25 and signal_type == "BUY":
            new_conf = min(95, old_conf + 5)
            signal["confidence"] = new_conf
            signal["fear_greed"] = value
            signal["fear_greed_label"] = fg["label_ar"]
            logger.info(f"😱 Fear & Greed boost: BUY +5% (F&G={value})")
            return {"adjusted": True, "old": old_conf, "new": new_conf, "reason": "خوف شديد = فرصة شراء"}

        # طمع شديد = حذر من الشراء
        elif value > 75 and signal_type == "BUY":
            new_conf = max(30, old_conf - 5)
            signal["confidence"] = new_conf
            signal["fear_greed"] = value
            signal["fear_greed_label"] = fg["label_ar"]
            logger.info(f"😱 Fear & Greed penalty: BUY -5% (F&G={value})")
            return {"adjusted": True, "old": old_conf, "new": new_conf, "reason": "طمع شديد = حذر"}

        # طمع شديد = فرصة بيع (contrarian)
        elif value > 75 and signal_type == "SELL":
            new_conf = min(95, old_conf + 5)
            signal["confidence"] = new_conf
            signal["fear_greed"] = value
            signal["fear_greed_label"] = fg["label_ar"]
            logger.info(f"😱 Fear & Greed boost: SELL +5% (F&G={value})")
            return {"adjusted": True, "old": old_conf, "new": new_conf, "reason": "طمع شديد = فرصة بيع"}

        # خوف شديد = حذر من البيع
        elif value < 25 and signal_type == "SELL":
            new_conf = max(30, old_conf - 5)
            signal["confidence"] = new_conf
            signal["fear_greed"] = value
            signal["fear_greed_label"] = fg["label_ar"]
            logger.info(f"😱 Fear & Greed penalty: SELL -5% (F&G={value})")
            return {"adjusted": True, "old": old_conf, "new": new_conf, "reason": "خوف شديد = حذر من البيع"}

        signal["fear_greed"] = value
        signal["fear_greed_label"] = fg["label_ar"]
        return {"adjusted": False}


# ═══════════════════════════════════════════════════
# FEATURE 10: DXY Correlation Filter
# ═══════════════════════════════════════════════════
class DXYFilter:
    """فلتر مؤشر الدولار — الذهب يتحرك عكس الدولار"""

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.cache = None
        self.cache_time = None
        self.cache_ttl = 1800  # 30 دقيقة

    def get_dxy_trend(self) -> Dict:
        """يجيب اتجاه مؤشر الدولار"""
        try:
            if self.cache and self.cache_time:
                if (datetime.now() - self.cache_time).seconds < self.cache_ttl:
                    return self.cache

            # محاولة جلب DXY من Yahoo
            resp = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
                params={"range": "5d", "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if resp.status_code != 200:
                return {"trend": "UNKNOWN", "change": 0}

            data = resp.json().get("chart", {}).get("result", [{}])[0]
            quotes = data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            closes = [c for c in quotes if c is not None]

            if len(closes) < 2:
                return {"trend": "UNKNOWN", "change": 0}

            current = closes[-1]
            prev = closes[-2]
            change_pct = ((current - prev) / prev) * 100

            if change_pct > 0.3:
                trend = "STRONG_UP"
            elif change_pct > 0:
                trend = "UP"
            elif change_pct < -0.3:
                trend = "STRONG_DOWN"
            else:
                trend = "DOWN"

            result = {"trend": trend, "change": change_pct, "value": current}
            self.cache = result
            self.cache_time = datetime.now()
            logger.info(f"💵 DXY: {trend} ({change_pct:+.2f}%)")
            return result

        except Exception as e:
            logger.warning(f"DXY fetch failed: {e}")
            return {"trend": "UNKNOWN", "change": 0}

    def apply(self, signal: Dict) -> Dict:
        """يعدل ثقة الإشارة حسب اتجاه الدولار"""
        dxy = self.get_dxy_trend()
        trend = dxy.get("trend", "UNKNOWN")
        signal_dir = signal.get("signal_type", "")
        old_conf = signal.get("confidence", 50)

        if trend == "UNKNOWN":
            signal["dxy_trend"] = "UNKNOWN"
            return {"adjusted": False}

        signal["dxy_trend"] = trend
        signal["dxy_change"] = dxy.get("change", 0)

        # الدولار قوي = ذهب ينزل = الشراء أضعف
        if trend in ("UP", "STRONG_UP") and signal_dir == "BUY":
            penalty = 5 if trend == "UP" else 10
            signal["confidence"] = max(30, old_conf - penalty)
            logger.info(f"💵 DXY penalty: BUY -{penalty}% (DXY={trend})")
            return {"adjusted": True, "old": old_conf, "new": signal["confidence"]}

        # الدولار قوي = ذهب ينزل = البيع أقوى
        elif trend in ("UP", "STRONG_UP") and signal_dir == "SELL":
            boost = 5 if trend == "UP" else 10
            signal["confidence"] = min(95, old_conf + boost)
            logger.info(f"💵 DXY boost: SELL +{boost}% (DXY={trend})")
            return {"adjusted": True, "old": old_conf, "new": signal["confidence"]}

        # الدولار ضعيف = ذهب يصعد = الشراء أقوى
        elif trend in ("DOWN", "STRONG_DOWN") and signal_dir == "BUY":
            boost = 5 if trend == "DOWN" else 10
            signal["confidence"] = min(95, old_conf + boost)
            logger.info(f"💵 DXY boost: BUY +{boost}% (DXY={trend})")
            return {"adjusted": True, "old": old_conf, "new": signal["confidence"]}

        # الدولار ضعيف = ذهب يصعد = البيع أضعف
        elif trend in ("DOWN", "STRONG_DOWN") and signal_dir == "SELL":
            penalty = 5 if trend == "DOWN" else 10
            signal["confidence"] = max(30, old_conf - penalty)
            logger.info(f"💵 DXY penalty: SELL -{penalty}% (DXY={trend})")
            return {"adjusted": True, "old": old_conf, "new": signal["confidence"]}

        return {"adjusted": False}


# ═══════════════════════════════════════════════════
# FEATURE 14: Spread Filter
# ═══════════════════════════════════════════════════
class SpreadFilter:
    """فلتر السبريد — يمنع الصفقات لما السبريد كبير"""

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.max_spread_pct = float(os.getenv("MAX_SPREAD_PCT", "0.15"))  # 0.15% max

    def check_spread(self) -> Dict:
        """يفحص السبريد الحالي"""
        try:
            ticker = self.fetcher.fetch_ticker("XAU/USD")
            if not ticker:
                return {"ok": True, "reason": "No ticker — allow"}

            bid = ticker.get("bid", 0)
            ask = ticker.get("ask", 0)
            last = ticker.get("last", 0)

            if not bid or not ask:
                # لو مفيش bid/ask، نحسب تقريبي
                return {"ok": True, "reason": "No bid/ask data", "spread_pct": 0}

            spread = abs(ask - bid)
            spread_pct = (spread / last) * 100 if last else 0

            if spread_pct > self.max_spread_pct:
                logger.warning(f"📏 Wide spread: {spread_pct:.3f}% (max={self.max_spread_pct}%)")
                return {
                    "ok": False,
                    "reason": f"Wide spread: {spread_pct:.3f}%",
                    "spread": spread,
                    "spread_pct": spread_pct,
                }

            return {"ok": True, "spread": spread, "spread_pct": spread_pct}

        except Exception as e:
            logger.warning(f"Spread check failed: {e}")
            return {"ok": True, "reason": "Check failed — allow"}


# ═══════════════════════════════════════════════════
# SIGNAL COOLDOWN: كولداون بين الإشارات
# ═══════════════════════════════════════════════════
class SignalCooldown:
    """منع التوصيات المتتالية — كولداون بين كل إشارة"""

    def __init__(self):
        self.cooldown_minutes = int(os.getenv("SIGNAL_COOLDOWN_MINUTES", "30"))
        self.last_signal_time = None

    def can_send(self) -> bool:
        """هل ممكن نبعت إشارة جديدة ولا لسه في كولداون؟"""
        if not self.last_signal_time:
            return True

        elapsed = (datetime.now() - self.last_signal_time).total_seconds() / 60
        if elapsed < self.cooldown_minutes:
            remaining = self.cooldown_minutes - elapsed
            logger.info(f"⏱️ Cooldown: {remaining:.0f} min remaining (last signal {elapsed:.0f} min ago)")
            return False

        return True

    def record_signal(self):
        """تسجيل إن إشارة اتبعتت"""
        self.last_signal_time = datetime.now()
        logger.info(f"⏱️ Cooldown started: {self.cooldown_minutes} min")

    def get_remaining(self) -> float:
        """كم باقي على الكولداون؟"""
        if not self.last_signal_time:
            return 0
        elapsed = (datetime.now() - self.last_signal_time).total_seconds() / 60
        return max(0, self.cooldown_minutes - elapsed)


# ═══════════════════════════════════════════════════
# FEATURE 12: Market Hours Manager — إيقاف تلقائي
# ═══════════════════════════════════════════════════
class MarketHoursManager:
    """إدارة ساعات السوق — إيقاف تلقائي لما السوق يقفل"""

    # سوق الذهب: Sunday 23:00 → Friday 22:00 UTC (تقريباً)
    # يومي: فتح 23:00 UTC → إغلاق 22:00 UTC (1 ساعة استراحة)

    @staticmethod
    def is_market_open() -> bool:
        """هل سوق الذهب مفتوح دلوقتي؟"""
        now = datetime.utcnow()

        # السبت كله مقفول
        if now.weekday() == 5:  # Saturday
            return False

        # الأحد: يفتح 23:00 UTC
        if now.weekday() == 6:  # Sunday
            if now.hour < 23:
                return False
            return True

        # الجمعة: يقفل 22:00 UTC
        if now.weekday() == 4:  # Friday
            if now.hour >= 22:
                return False
            return True

        # الإتنين-الخميس: مفتوح بس فيه استراحة يومية 22:00-23:00 UTC
        if 0 <= now.weekday() <= 3:
            if now.hour == 22:  # استراحة ساعية
                return False
            return True

        return True

    @staticmethod
    def get_market_status() -> Dict:
        """حالة السوق التفصيلية"""
        now = datetime.utcnow()
        is_open = MarketHoursManager.is_market_open()

        if is_open:
            return {"open": True, "status": "🟢 مفتوح", "next_close": "22:00 UTC"}
        else:
            if now.weekday() == 5:
                return {"open": False, "status": "🔴 مقفول (السبت)", "next_open": "الأحد 23:00 UTC"}
            elif now.weekday() == 6 and now.hour < 23:
                return {"open": False, "status": "🔴 مقفول (الأحد)", "next_open": "اليوم 23:00 UTC"}
            elif now.weekday() == 4 and now.hour >= 22:
                return {"open": False, "status": "🔴 مقفول (الجمعة)", "next_open": "الأحد 23:00 UTC"}
            else:
                return {"open": False, "status": "🟡 استراحة ساعية", "next_open": "23:00 UTC"}


# ═══════════════════════════════════════════════════
# FEATURE 13: Auto-Restart Manager
# ═══════════════════════════════════════════════════
class AutoRestartManager:
    """إعادة تشغيل تلقائي لو البوت وقع"""

    def __init__(self):
        self.start_time = datetime.now()
        self.restart_count = 0
        self.health_check_interval = 300  # 5 دقايق

    def is_healthy(self) -> bool:
        """فحص صحة البوت"""
        try:
            # فحص بسيط: هل الـ event loop شغال؟
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                if loop.is_closed():
                    return False
            except RuntimeError:
                return False

            # فحص الذاكرة
            try:
                import resource
                mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            except (ImportError, AttributeError):
                mem = 0
            # لو الذاكرة فوق 500MB — تحذير
            if mem > 500 * 1024:
                logger.warning(f"⚠️ High memory: {mem / 1024:.0f}MB")

            return True
        except Exception:
            return True  # في حالة الشك — اسمح

    def record_restart(self):
        self.restart_count += 1
        logger.info(f"🔄 Auto-restart #{self.restart_count}")

    def get_uptime(self) -> str:
        """زمن التشغيل"""
        delta = datetime.now() - self.start_time
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        if delta.days > 0:
            return f"{delta.days}d {hours}h {minutes}m"
        return f"{hours}h {minutes}m"
