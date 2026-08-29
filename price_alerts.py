"""
صياد الشمعات | Candle Hunter — Price Alerts System
تنبيهات السعر للمستخدمين
"""
import json
import os
import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_alerts.json")


class PriceAlertManager:
    """إدارة تنبيهات السعر للمستخدمين"""

    def __init__(self):
        self.alerts: List[Dict] = []
        self._load()

    def _load(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.alerts = json.load(f)
                logger.info(f"Loaded {len(self.alerts)} price alerts")
        except Exception as e:
            logger.error(f"Error loading price alerts: {e}")
            self.alerts = []

    def _save(self):
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.alerts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving price alerts: {e}")

    def add_alert(self, telegram_id: int, target_price: float, direction: str = "ABOVE") -> Dict:
        """إضافة تنبيه سعر جديد"""
        alert = {
            "id": f"alert_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "telegram_id": telegram_id,
            "target_price": target_price,
            "direction": direction,  # ABOVE أو BELOW
            "created_at": datetime.now().isoformat(),
            "triggered": False,
        }
        self.alerts.append(alert)
        self._save()
        logger.info(f"🔔 Price alert added: {telegram_id} → {direction} {target_price}")
        return alert

    def remove_alert(self, alert_id: str) -> bool:
        """حذف تنبيه"""
        before = len(self.alerts)
        self.alerts = [a for a in self.alerts if a["id"] != alert_id]
        if len(self.alerts) < before:
            self._save()
            return True
        return False

    def get_user_alerts(self, telegram_id: int) -> List[Dict]:
        """جلب تنبيهات مستخدم"""
        return [a for a in self.alerts if a["telegram_id"] == telegram_id and not a["triggered"]]

    def check_alerts(self, current_price: float) -> List[Dict]:
        """فحص كل التنبيهات — يرجع اللي اشتغلت"""
        triggered = []
        for alert in self.alerts:
            if alert["triggered"]:
                continue

            target = alert["target_price"]
            direction = alert["direction"]

            if direction == "ABOVE" and current_price >= target:
                alert["triggered"] = True
                alert["triggered_at"] = datetime.now().isoformat()
                alert["triggered_price"] = current_price
                triggered.append(alert)
                logger.info(f"🔔 Alert triggered: {alert['id']} ABOVE {target} (price={current_price})")

            elif direction == "BELOW" and current_price <= target:
                alert["triggered"] = True
                alert["triggered_at"] = datetime.now().isoformat()
                alert["triggered_price"] = current_price
                triggered.append(alert)
                logger.info(f"🔔 Alert triggered: {alert['id']} BELOW {target} (price={current_price})")

        if triggered:
            # تنظيف التنبيهات اللي اشتغلت من أكثر من 7 أيام
            cutoff = (datetime.now().isoformat()[:10])
            self.alerts = [a for a in self.alerts if not (a.get("triggered", False) and a.get("triggered_at", "")[:10] < cutoff)]
            self._save()

        return triggered

    def format_user_alerts(self, telegram_id: int) -> str:
        """تنسيق تنبيهات المستخدم كرسالة"""
        alerts = self.get_user_alerts(telegram_id)
        if not alerts:
            return "🔔 لا توجد تنبيهات سعر نشطة\n\nاضغط '🔔 تنبيه سعر جديد' لإضافة تنبيه."

        msg = "🔔 تنبيهات السعر النشطة\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        for a in alerts:
            direction_emoji = "⬆️" if a["direction"] == "ABOVE" else "⬇️"
            direction_ar = "فوق" if a["direction"] == "ABOVE" else "تحت"
            msg += f"{direction_emoji} {direction_ar} ${a['target_price']:,.2f}\n"
            msg += f"   🕐 {a['created_at'][:16].replace('T', ' ')}\n"
            msg += f"   🆔 {a['id']}\n\n"

        msg += "لحذف تنبيه: /delete_alert_معرف_التنبيه"
        return msg
