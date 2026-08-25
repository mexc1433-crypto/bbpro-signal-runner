"""
BBPro Signal Bot - Channel Manager
إدارة توزيع الإشارات على القنوات
"""
from typing import Dict, List, Optional
from datetime import datetime, date
from config import CHANNEL_RULES


class ChannelManager:
    """يدير توزيع الإشارات بين القناة العامة والخاصة"""

    def __init__(self):
        self.rules = CHANNEL_RULES
        self.daily_counts = {"PUBLIC": 0, "PRIVATE": 0}
        self.last_reset_date = date.today()
        self.signal_history = {"PUBLIC": [], "PRIVATE": []}

    def _check_reset(self):
        """إعادة تعيين العدادات اليومية"""
        if self.last_reset_date != date.today():
            self.daily_counts = {"PUBLIC": 0, "PRIVATE": 0}
            self.signal_history = {"PUBLIC": [], "PRIVATE": []}
            self.last_reset_date = date.today()

    def should_send_to_public(self, signal: Dict) -> bool:
        """
        هل الإشارة تصلح للقناة العامة؟
        - 1-3 إشارات يومياً
        - SCALPING و MEDIUM فقط
        - مخاطرة منخفضة فقط
        - ثقة >= 50%
        """
        self._check_reset()
        rules = self.rules["PUBLIC"]

        # Daily limit check
        if self.daily_counts["PUBLIC"] >= rules["max_signals"]:
            return False

        # Trade type check
        if signal.get("trade_type") not in rules["allowed_types"]:
            return False

        # Risk level check
        if signal.get("risk_level") not in ["LOW"]:
            return False

        # Confidence check
        if signal.get("confidence", 0) < rules["min_confidence"]:
            return False

        return True

    def should_send_to_private(self, signal: Dict) -> bool:
        """
        هل الإشارة تصلح للقناة الخاصة؟
        - 1-10 إشارات يومياً
        - MEDIUM و SWING فقط (لا سكالبينج)
        - كل مستويات المخاطرة
        - ثقة >= 65%
        """
        self._check_reset()
        rules = self.rules["PRIVATE"]

        # Daily limit check
        if self.daily_counts["PRIVATE"] >= rules["max_signals"]:
            return False

        # Trade type check - exclude scalping
        if signal.get("trade_type") in rules["blocked_types"]:
            return False

        if signal.get("trade_type") not in rules["allowed_types"]:
            return False

        # Confidence check
        if signal.get("confidence", 0) < rules["min_confidence"]:
            return False

        return True

    def get_channel_for_signal(self, signal: Dict) -> List[str]:
        """يحدد أي قناة/قنوات ترسل لها الإشارة"""
        channels = []
        if self.should_send_to_public(signal):
            channels.append("PUBLIC")
        if self.should_send_to_private(signal):
            channels.append("PRIVATE")
        return channels

    def can_send_more(self, channel: str) -> bool:
        """هل يمكن إرسال المزيد لهذه القناة؟"""
        self._check_reset()
        return self.daily_counts[channel] < self.rules[channel]["max_signals"]

    def record_signal(self, channel: str, signal: Dict):
        """يسجل إشارة مرسلة"""
        self._check_reset()
        self.daily_counts[channel] += 1
        self.signal_history[channel].append({
            **signal,
            "sent_at": datetime.now().isoformat(),
        })

    def reset_daily_counts(self):
        """إعادة تعيين العدادات"""
        self.daily_counts = {"PUBLIC": 0, "PRIVATE": 0}
        self.signal_history = {"PUBLIC": [], "PRIVATE": []}
        self.last_reset_date = date.today()

    def get_daily_stats(self) -> Dict:
        """إحصائيات اليوم"""
        self._check_reset()
        return {
            "public_count": self.daily_counts["PUBLIC"],
            "public_max": self.rules["PUBLIC"]["max_signals"],
            "private_count": self.daily_counts["PRIVATE"],
            "private_max": self.rules["PRIVATE"]["max_signals"],
        }
