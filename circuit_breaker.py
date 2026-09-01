"""
صياد الشمعات | Candle Hunter - Circuit Breaker
قاطع التيار: يوقف التداول بعد خسائر متتالية
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "circuit_breaker.json")


class CircuitBreaker:
    """
    يوقف التداول تلقائياً لو:
    - 3 خسائر متتالية → يوقف ساعتين
    - 5 خساير في اليوم → يوقف لليوم التالي
    - MEXC API فشل 3 مرات ورا بعض → يوقف 30 دقيقة
    """

    MAX_CONSECUTIVE_LOSSES = 3
    MAX_DAILY_LOSSES = 5
    COOLDOWN_HOURS = 2
    API_FAIL_COOLDOWN_MIN = 30

    def __init__(self):
        self.state: Dict = {
            "consecutive_losses": 0,
            "daily_losses": {},
            "api_failures": 0,
            "paused_until": None,
            "pause_reason": None,
        }
        self._load()

    def _load(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    self.state = json.load(f)
        except:
            pass

    def _save(self):
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except:
            pass

    def record_loss(self, strategy: str = "") -> Tuple[bool, str]:
        """يسجل خسارة ويفحص لو لازم يوقف"""
        self.state["consecutive_losses"] += 1

        today = datetime.now().strftime('%Y-%m-%d')
        daily = self.state["daily_losses"].get(today, 0)
        self.state["daily_losses"][today] = daily + 1

        consecutive = self.state["consecutive_losses"]
        daily_count = self.state["daily_losses"][today]

        if consecutive >= self.MAX_CONSECUTIVE_LOSSES:
            pause_until = datetime.now() + timedelta(hours=self.COOLDOWN_HOURS)
            self.state["paused_until"] = pause_until.isoformat()
            self.state["pause_reason"] = f"🛑 {consecutive} خسائر متتالية — إيقاف ساعتين"
            self._save()
            logger.warning(f"🔴 Circuit Breaker: {consecutive} consecutive losses — pausing 2h")
            return True, self.state["pause_reason"]

        if daily_count >= self.MAX_DAILY_LOSSES:
            tomorrow = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
            self.state["paused_until"] = tomorrow.isoformat()
            self.state["pause_reason"] = f"🛑 {daily_count} خسائر اليوم — إيقاف لليوم التالي"
            self._save()
            logger.warning(f"🔴 Circuit Breaker: {daily_count} daily losses — pausing until tomorrow")
            return True, self.state["pause_reason"]

        self._save()
        return False, ""

    def record_win(self):
        """يسجل ربح — يصفر العداد المتتالي"""
        self.state["consecutive_losses"] = 0
        self._save()

    def record_api_failure(self) -> Tuple[bool, str]:
        """يسجل فشل API ويفحص لو لازم يوقف"""
        self.state["api_failures"] += 1
        if self.state["api_failures"] >= 3:
            pause_until = datetime.now() + timedelta(minutes=self.API_FAIL_COOLDOWN_MIN)
            self.state["paused_until"] = pause_until.isoformat()
            self.state["pause_reason"] = f"⚠️ MEXC API فشل 3 مرات — إيقاف 30 دقيقة"
            self.state["api_failures"] = 0
            self._save()
            logger.warning("🔴 Circuit Breaker: API failures — pausing 30 min")
            return True, self.state["pause_reason"]
        self._save()
        return False, ""

    def record_api_success(self):
        self.state["api_failures"] = 0
        self._save()

    def is_paused(self) -> Tuple[bool, Optional[str]]:
        """هل التداول موقوف؟"""
        if not self.state.get("paused_until"):
            return False, None

        try:
            pause_until = datetime.fromisoformat(self.state["paused_until"])
            if datetime.now() < pause_until:
                remaining = pause_until - datetime.now()
                mins = int(remaining.total_seconds() / 60)
                return True, f"{self.state['pause_reason']} (متبقي {mins} دقيقة)"
            else:
                self.state["paused_until"] = None
                self.state["pause_reason"] = None
                self.state["consecutive_losses"] = 0
                self._save()
                return False, None
        except:
            return False, None

    def reset(self):
        """إعادة ضبط (يدوي من الأدمن)"""
        self.state["consecutive_losses"] = 0
        self.state["paused_until"] = None
        self.state["pause_reason"] = None
        self.state["api_failures"] = 0
        self._save()
        logger.info("✅ Circuit Breaker reset by admin")

    def get_status(self) -> str:
        """حالة الـ circuit breaker"""
        paused, reason = self.is_paused()
        if paused:
            return f"🔴 موقوف: {reason}"

        consecutive = self.state["consecutive_losses"]
        today = datetime.now().strftime('%Y-%m-%d')
        daily = self.state["daily_losses"].get(today, 0)

        return (
            f"🟢 نشط\n"
            f"خسائر متتالية: {consecutive}/{self.MAX_CONSECUTIVE_LOSSES}\n"
            f"خسائر اليوم: {daily}/{self.MAX_DAILY_LOSSES}"
        )
