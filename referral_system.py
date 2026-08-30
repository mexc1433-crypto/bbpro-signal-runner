"""
صياد الشمعات | Candle Hunter — Referral System
نظام الإحالة التلقائي
"""
import json
import os
import logging
import secrets
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "referrals.json")


class ReferralSystem:
    """نظام الإحالة — كل مستخدم له رابط خاص"""

    def __init__(self):
        self.referrals: Dict = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.referrals = json.load(f)
                logger.info(f"Loaded {len(self.referrals)} referral records")
        except Exception as e:
            logger.error(f"Error loading referrals: {e}")
            self.referrals = {}

    def _save(self):
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.referrals, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving referrals: {e}")

    def get_or_create_code(self, telegram_id: int, username: str = "") -> str:
        """يجيب كود الإحالة أو يعمل واحد جديد"""
        uid = str(telegram_id)
        if uid not in self.referrals:
            code = secrets.token_hex(4)  # 8 chars
            self.referrals[uid] = {
                "telegram_id": telegram_id,
                "username": username,
                "referral_code": code,
                "referrals": [],
                "created_at": datetime.now().isoformat(),
            }
            self._save()
            logger.info(f"📝 New referral code for {telegram_id}: {code}")
        return self.referrals[uid]["referral_code"]

    def get_referral_link(self, telegram_id: int, username: str = "", bot_username: str = "") -> str:
        """رابط الإحالة الكامل"""
        code = self.get_or_create_code(telegram_id, username)
        if bot_username:
            return f"https://t.me/{bot_username}?start=ref_{code}"
        return f"https://t.me/candle_hunter_bot?start=ref_{code}"

    def add_referral(self, referrer_code: str, new_user_id: int, new_username: str = "") -> bool:
        """تسجيل إحالة جديدة"""
        for uid, data in self.referrals.items():
            if data.get("referral_code") == referrer_code:
                # نتأكد إن المستخدم الجديد ما اتحالش قبل كدا
                existing = [r for r in data.get("referrals", []) if r.get("telegram_id") == new_user_id]
                if existing:
                    return False

                data["referrals"].append({
                    "telegram_id": new_user_id,
                    "username": new_username,
                    "joined_at": datetime.now().isoformat(),
                })
                self._save()
                logger.info(f"👥 New referral: {data['telegram_id']} ← {new_user_id} (total: {len(data['referrals'])})")
                return True
        return False

    def get_referral_stats(self, telegram_id: int) -> Dict:
        """إحصائيات الإحالة لمستخدم"""
        uid = str(telegram_id)
        data = self.referrals.get(uid, {})
        refs = data.get("referrals", [])
        return {
            "code": data.get("referral_code", ""),
            "total_referrals": len(refs),
            "referrals": refs,
            "link": self.get_referral_link(telegram_id, data.get("username", "")),
        }

    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """أعلى المستخدمين في الإحالات"""
        all_users = []
        for uid, data in self.referrals.items():
            count = len(data.get("referrals", []))
            if count > 0:
                all_users.append({
                    "telegram_id": data["telegram_id"],
                    "username": data.get("username", ""),
                    "count": count,
                })
        all_users.sort(key=lambda x: x["count"], reverse=True)
        return all_users[:limit]

    def format_referral_info(self, telegram_id: int, bot_username: str = "") -> str:
        """تنسيق معلومات الإحالة لمستخدم"""
        stats = self.get_referral_stats(telegram_id)
        link = self.get_referral_link(telegram_id, "", bot_username)

        msg = "👥 نظام الإحالة\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🔗 رابط الإحالة الخاص بك:\n{link}\n\n"
        msg += f"📊 إجمالي الإحالات: {stats['total_referrals']}\n"
        msg += f"🆔 كود الإحالة: {stats['code']}\n\n"
        msg += "شارك الرابط مع أصدقائك!\n"
        msg += "🤖 صياد الشمعات | Candle Hunter"
        return msg
