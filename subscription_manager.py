"""
صياد الشمعات | Candle Hunter - Subscription Manager
نظام اشتراكات أسبوعي: $5 أول مرة، $10 بعدها
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subscriptions.json")


class SubscriptionManager:
    """
    خطط الاشتراك:
    - FREE: إشارات عامة فقط (scalping)، بدون auto-trade
    - PREMIUM (أسبوعي): $5 أول مرة، $10 بعدها — إشارات خاصة + auto-trade + AI
    """

    WEEKLY_FIRST_PRICE = 5.0   # أول مرة
    WEEKLY_PRICE = 10.0        # كل مرة بعدها
    TRIAL_DAYS = 3             # تجربة مجانية 3 أيام

    def __init__(self):
        self.subscriptions: Dict = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    self.subscriptions = json.load(f)
        except:
            pass

    def _save(self):
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(self.subscriptions, f, ensure_ascii=False, indent=2)
        except:
            pass

    def start_trial(self, telegram_id: int, username: str = "") -> Dict:
        """بدء تجربة مجانية 3 أيام"""
        key = str(telegram_id)
        if key in self.subscriptions:
            if self.subscriptions[key].get("trial_used"):
                return {"success": False, "error": "تم استخدام التجربة المجانية من قبل"}

        self.subscriptions[key] = {
            "telegram_id": telegram_id,
            "username": username,
            "plan": "PREMIUM",
            "status": "TRIAL",
            "trial_used": True,
            "subscribed_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=self.TRIAL_DAYS)).isoformat(),
            "is_first_paid": False,
            "payment_history": [],
        }
        self._save()
        logger.info(f"Trial started for {telegram_id} — {self.TRIAL_DAYS} days")
        return {"success": True, "plan": "PREMIUM", "trial_days": self.TRIAL_DAYS}

    def activate_subscription(self, telegram_id: int, username: str = "") -> Dict:
        """تفعيل اشتراك مدفوع"""
        key = str(telegram_id)
        is_first = True

        if key in self.subscriptions:
            if not self.subscriptions[key].get("is_first_paid", False):
                is_first = True
            else:
                is_first = False

        price = self.WEEKLY_FIRST_PRICE if is_first else self.WEEKLY_PRICE

        self.subscriptions[key] = {
            "telegram_id": telegram_id,
            "username": username,
            "plan": "PREMIUM",
            "status": "ACTIVE",
            "trial_used": self.subscriptions.get(key, {}).get("trial_used", False),
            "subscribed_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
            "is_first_paid": True,
            "price_paid": price,
            "payment_history": self.subscriptions.get(key, {}).get("payment_history", []) + [
                {"date": datetime.now().isoformat(), "amount": price, "type": "weekly"}
            ],
        }
        self._save()
        logger.info(f"Subscription activated for {telegram_id} — ${price} ({'first' if is_first else 'renewal'})")
        return {"success": True, "price": price, "is_first": is_first, "expires_in_days": 7}

    def check_subscription(self, telegram_id: int) -> Dict:
        """فحص حالة الاشتراك"""
        key = str(telegram_id)
        if key not in self.subscriptions:
            return {"active": False, "plan": "FREE", "reason": "No subscription"}

        sub = self.subscriptions[key]
        try:
            expires_at = datetime.fromisoformat(sub["expires_at"])
            if datetime.now() < expires_at:
                remaining = expires_at - datetime.now()
                return {
                    "active": True,
                    "plan": sub["plan"],
                    "status": sub["status"],
                    "remaining_days": remaining.days,
                    "remaining_hours": int(remaining.seconds / 3600),
                    "expires_at": sub["expires_at"],
                }
            else:
                sub["status"] = "EXPIRED"
                self._save()
                return {"active": False, "plan": "FREE", "reason": "Subscription expired"}
        except:
            return {"active": False, "plan": "FREE", "reason": "Error reading subscription"}

    def is_premium(self, telegram_id: int) -> bool:
        """هل المستخدم مشترك PREMIUM؟"""
        result = self.check_subscription(telegram_id)
        return result.get("active") and result.get("plan") == "PREMIUM"

    def expire_check_all(self) -> list:
        """فحص كل الاشتراكات المنتهية"""
        expired = []
        for key, sub in self.subscriptions.items():
            try:
                expires_at = datetime.fromisoformat(sub["expires_at"])
                if datetime.now() >= expires_at and sub["status"] not in ("EXPIRED", "FREE"):
                    sub["status"] = "EXPIRED"
                    expired.append(sub)
            except:
                continue
        if expired:
            self._save()
        return expired

    def get_price_for_user(self, telegram_id: int) -> float:
        """سعر الاشتراك للمستخدم — $5 أول مرة، $10 بعدها"""
        key = str(telegram_id)
        if key not in self.subscriptions or not self.subscriptions[key].get("is_first_paid"):
            return self.WEEKLY_FIRST_PRICE
        return self.WEEKLY_PRICE

    def format_subscription_info(self, telegram_id: int) -> str:
        """رسالة معلومات الاشتراك"""
        result = self.check_subscription(telegram_id)
        price = self.get_price_for_user(telegram_id)

        if result.get("active"):
            remaining = result.get("remaining_days", 0)
            hours = result.get("remaining_hours", 0)
            msg = (
                f"💎 اشتراكك الحالي\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 الخطة: PREMIUM\n"
                f"✅ الحالة: نشط\n"
                f"⏳ متبقي: {remaining} يوم و {hours} ساعة\n"
                f"💰 سعر التجديد: ${price}\n"
            )
        else:
            trial_used = self.subscriptions.get(str(telegram_id), {}).get("trial_used", False)
            msg = (
                f"💎 اشتراكك الحالي\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 الخطة: FREE\n"
                f"❌ الحالة: غير مشترك\n"
            )
            if not trial_used:
                msg += f"🎁 تجربة مجانية متاحة: {self.TRIAL_DAYS} أيام\n"
            msg += f"💰 سعر الاشتراك: ${price}/أسبوع\n"
            msg += f"💳 أول مرة فقط: ${self.WEEKLY_FIRST_PRICE}\n"
            msg += f"🔄 بعدها: ${self.WEEKLY_PRICE}/أسبوع\n"

        return msg
