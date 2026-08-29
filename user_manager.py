"""
صياد الشمعات | Candle Hunter - User Manager
إدارة المستخدمين المسجلين + التشفير
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
from cryptography.fernet import Fernet
import base64
import hashlib

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users_data.json")
# مفتاح التشفير من environment variable
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")


class Encryption:
    """تشفير وفك تشفير API Keys"""

    @staticmethod
    def _get_key() -> bytes:
        """توليد مفتاح ثابت من ENCRYPTION_KEY أو BOT_TOKEN"""
        source = ENCRYPTION_KEY or os.getenv("BOT_TOKEN", "default_key_change_me")
        # تحويل لأولة 32-byte ثم base64
        key = hashlib.sha256(source.encode()).digest()[:32]
        return base64.urlsafe_b64encode(key)

    @staticmethod
    def encrypt(text: str) -> str:
        """تشفير نص"""
        try:
            f = Fernet(Encryption._get_key())
            return f.encrypt(text.encode()).decode()
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return text

    @staticmethod
    def decrypt(encrypted: str) -> str:
        """فك تشفير نص"""
        try:
            f = Fernet(Encryption._get_key())
            return f.decrypt(encrypted.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return encrypted


class UserManager:
    """إدارة المستخدمين المسجلين"""

    def __init__(self):
        self.users: Dict[int, Dict] = {}  # telegram_id -> user_data
        self._load()

    def _load(self):
        """تحميل المستخدمين من ملف"""
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.users = json.load(f)
                logger.info(f"Loaded {len(self.users)} registered users")
        except Exception as e:
            logger.error(f"Error loading users data: {e}")
            self.users = {}

    def _save(self):
        """حفظ المستخدمين في ملف"""
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving users data: {e}")

    def register_user(self, telegram_id: int, username: str, mexc_uid: str,
                       api_key: str, api_secret: str) -> Dict:
        """تسجيل مستخدم جديد"""
        # تشفير API Keys
        enc_api_key = Encryption.encrypt(api_key)
        enc_api_secret = Encryption.encrypt(api_secret)

        self.users[str(telegram_id)] = {
            "telegram_id": telegram_id,
            "username": username,
            "mexc_uid": mexc_uid,
            "api_key_encrypted": enc_api_key,
            "api_secret_encrypted": enc_api_secret,
            "status": "ACTIVE",  # ACTIVE / PAUSED / BANNED
            "auto_trade": True,
            "risk_level": "MEDIUM",  # LOW / MEDIUM / HIGH
            "leverage": 10,
            "registered_at": datetime.now().isoformat(),
            "total_trades": 0,
            "total_pnl": 0.0,
            "last_trade_time": None,
            "is_admin": False,
        }
        self._save()
        logger.info(f"User registered: {telegram_id} (@{username})")
        return self.users[str(telegram_id)]

    def is_registered(self, telegram_id: int) -> bool:
        """هل المستخدم مسجل؟"""
        return str(telegram_id) in self.users

    def get_user(self, telegram_id: int) -> Optional[Dict]:
        """جلب بيانات مستخدم"""
        return self.users.get(str(telegram_id))

    def get_user_api(self, telegram_id: int) -> tuple:
        """جلب API Keys مفكوكة التشفير"""
        user = self.get_user(telegram_id)
        if not user:
            return None, None
        api_key = Encryption.decrypt(user["api_key_encrypted"])
        api_secret = Encryption.decrypt(user["api_secret_encrypted"])
        return api_key, api_secret

    def update_user(self, telegram_id: int, updates: Dict):
        """تحديث بيانات مستخدم"""
        uid = str(telegram_id)
        if uid in self.users:
            self.users[uid].update(updates)
            self._save()

    def pause_user(self, telegram_id: int):
        """إيقاف التداول التلقائي لمستخدم"""
        self.update_user(telegram_id, {"auto_trade": False, "status": "PAUSED"})
        logger.info(f"User {telegram_id} paused auto-trade")

    def resume_user(self, telegram_id: int):
        """استئناف التداول التلقائي"""
        self.update_user(telegram_id, {"auto_trade": True, "status": "ACTIVE"})
        logger.info(f"User {telegram_id} resumed auto-trade")

    def ban_user(self, telegram_id: int):
        """حظر مستخدم"""
        self.update_user(telegram_id, {"status": "BANNED", "auto_trade": False})
        logger.info(f"User {telegram_id} banned")

    def set_risk_level(self, telegram_id: int, level: str):
        """تغيير مستوى المخاطرة"""
        risk_config = {
            "LOW": {"risk_pct": 1.0, "leverage": 5},
            "MEDIUM": {"risk_pct": 2.0, "leverage": 10},
            "HIGH": {"risk_pct": 5.0, "leverage": 20},
        }
        config = risk_config.get(level, risk_config["MEDIUM"])
        self.update_user(telegram_id, {
            "risk_level": level,
            "leverage": config["leverage"],
        })

    def record_trade(self, telegram_id: int, pnl: float = 0.0):
        """تسجيل صفقة منفذة"""
        user = self.get_user(telegram_id)
        if user:
            self.update_user(telegram_id, {
                "total_trades": user.get("total_trades", 0) + 1,
                "total_pnl": user.get("total_pnl", 0) + pnl,
                "last_trade_time": datetime.now().isoformat(),
            })

    def get_active_users(self) -> List[Dict]:
        """جلب كل المستخدمين النشطين (للتنفيذ التلقائي)"""
        return [
            u for u in self.users.values()
            if u.get("status") == "ACTIVE" and u.get("auto_trade", True)
        ]

    def get_all_users(self) -> List[Dict]:
        """جلب كل المستخدمين"""
        return list(self.users.values())

    def get_all_telegram_ids(self) -> List[int]:
        """جلب كل Telegram IDs — للرسائل الجماعية"""
        return [int(uid) for uid in self.users.keys() if self.users[uid].get("status") != "BANNED"]

    def get_stats(self) -> Dict:
        """إحصائيات المستخدمين"""
        all_users = list(self.users.values())
        active = [u for u in all_users if u.get("status") == "ACTIVE"]
        paused = [u for u in all_users if u.get("status") == "PAUSED"]
        banned = [u for u in all_users if u.get("status") == "BANNED"]
        total_trades = sum(u.get("total_trades", 0) for u in all_users)
        total_pnl = sum(u.get("total_pnl", 0) for u in all_users)

        return {
            "total": len(all_users),
            "active": len(active),
            "paused": len(paused),
            "banned": len(banned),
            "total_trades": total_trades,
            "total_pnl": total_pnl,
        }

    def get_referral_link(self, referral_code: str = "") -> str:
        """رابط إحالة MEXC"""
        if referral_code:
            return f"https://www.mexc.com/register?referralCode={referral_code}"
        return "https://www.mexc.com/register"

    def format_user_info(self, telegram_id: int) -> str:
        """معلومات حساب المستخدم"""
        user = self.get_user(telegram_id)
        if not user:
            return "❌ أنت غير مسجل. اكتب /start للتسجيل"

        status_emoji = {"ACTIVE": "🟢 نشط", "PAUSED": "⏸️ متوقف", "BANNED": "🔴 محظور"}
        risk_emoji = {"LOW": "🟢 منخفض", "MEDIUM": "🟡 متوسط", "HIGH": "🔴 عالي"}

        msg = "👤 معلومات حسابك\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📛 الاسم: @{user.get('username', 'N/A')}\n"
        msg += f"🆔 MEXC UID: {user.get('mexc_uid', 'N/A')}\n"
        msg += f"📊 الحالة: {status_emoji.get(user.get('status'), '❓')}\n"
        msg += f"🔄 التداول التلقائي: {'✅ مفعل' if user.get('auto_trade') else '❌ متوقف'}\n"
        msg += f"⚖️ المخاطرة: {risk_emoji.get(user.get('risk_level'), '🟡 متوسط')}\n"
        msg += f"📈 الرافعة: {user.get('leverage', 10)}x\n"
        msg += f"📋 إجمالي الصفقات: {user.get('total_trades', 0)}\n"
        msg += f"💰 إجمالي PnL: ${user.get('total_pnl', 0):.2f}\n"
        msg += f"📅 التسجيل: {user.get('registered_at', 'N/A')[:10]}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"

        return msg

    def format_admin_stats(self) -> str:
        """إحصائيات الأدمن"""
        stats = self.get_stats()
        msg = "📊 إحصائيات النظام\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"👥 إجمالي المسجلين: {stats['total']}\n"
        msg += f"🟢 نشطين: {stats['active']}\n"
        msg += f"⏸️ متوقفين: {stats['paused']}\n"
        msg += f"🔴 محظورين: {stats['banned']}\n"
        msg += f"📋 إجمالي الصفقات: {stats['total_trades']}\n"
        msg += f"💰 إجمالي PnL: ${stats['total_pnl']:.2f}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"

        # قائمة المسجلين
        users = self.get_all_users()
        if users:
            msg += "\n📋 المسجلين:\n"
            for u in users[:15]:
                status = {"ACTIVE": "🟢", "PAUSED": "⏸️", "BANNED": "🔴"}.get(u.get("status"), "❓")
                msg += f"{status} @{u.get('username', 'N/A')} | UID: {u.get('mexc_uid', 'N/A')}\n"
                msg += f"   صفقات: {u.get('total_trades', 0)} | PnL: ${u.get('total_pnl', 0):.2f}\n"
            if len(users) > 15:
                msg += f"\n... و {len(users) - 15} آخرين\n"

        return msg
