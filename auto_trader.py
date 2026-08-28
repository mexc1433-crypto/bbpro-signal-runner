"""
BBPro Signal Bot - Auto Trader
محرك التنفيذ التلقائي متعدد الحسابات
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from mexc_client import MexcClient
from user_manager import UserManager

logger = logging.getLogger(__name__)


class AutoTrader:
    """ينفذ الإشارات تلقائياً على كل الحسابات المسجلة"""

    # مخاطرة المالك
    OWNER_RISK_PCT = 2.0
    OWNER_LEVERAGE = 10

    def __init__(self, user_manager: UserManager, owner_api_key: str = "", owner_api_secret: str = ""):
        self.user_manager = user_manager
        self.owner_api_key = owner_api_key
        self.owner_api_secret = owner_api_secret
        self.owner_client: Optional[MexcClient] = None
        self._init_owner_client()

    def _init_owner_client(self):
        """تهيئة عميل المالك"""
        if self.owner_api_key and self.owner_api_secret:
            try:
                self.owner_client = MexcClient(self.owner_api_key, self.owner_api_secret, is_futures=True)
                balance = self.owner_client.get_balance()
                if balance.get("success"):
                    logger.info(f"✅ Owner MEXC client ready | Balance: ${balance['free']:.2f}")
                else:
                    logger.warning("⚠️ Owner MEXC client init failed - check API keys")
            except Exception as e:
                logger.error(f"Owner MEXC client error: {e}")
        else:
            logger.warning("⚠️ No owner MEXC API keys - auto-trade for owner disabled")

    async def execute_for_everyone(self, signal: Dict) -> Dict:
        """
        ينفذ إشارة على:
        1. حساب المالك
        2. كل المستخدمين النشطين
        """
        results = {
            "signal": signal.get("signal_type", ""),
            "strategy": signal.get("strategy_name", ""),
            "owner": None,
            "users": [],
            "total_executed": 0,
            "total_failed": 0,
        }

        # 1. تنفيذ على حساب المالك
        if self.owner_client:
            owner_result = await self._execute_for_owner(signal)
            results["owner"] = owner_result
            if owner_result.get("success"):
                results["total_executed"] += 1
            else:
                results["total_failed"] += 1

        # 2. تنفيذ على حسابات المستخدمين
        active_users = self.user_manager.get_active_users()
        for user in active_users:
            try:
                user_result = await self._execute_for_user(signal, user)
                results["users"].append({
                    "telegram_id": user["telegram_id"],
                    "username": user.get("username", ""),
                    "result": user_result,
                })
                if user_result.get("success"):
                    results["total_executed"] += 1
                    self.user_manager.record_trade(user["telegram_id"])
                else:
                    results["total_failed"] += 1
            except Exception as e:
                logger.error(f"Error executing for user {user.get('telegram_id')}: {e}")
                results["total_failed"] += 1

        logger.info(
            f"Auto-trade: {signal.get('signal_type', '')} | "
            f"Executed: {results['total_executed']} | "
            f"Failed: {results['total_failed']}"
        )

        return results

    async def _execute_for_owner(self, signal: Dict) -> Dict:
        """تنفيذ على حساب المالك"""
        try:
            balance = self.owner_client.get_balance()
            if not balance.get("success") or balance["free"] <= 0:
                return {"success": False, "error": "No balance", "account": "owner"}

            risk_amount = balance["free"] * (self.OWNER_RISK_PCT / 100)
            result = self.owner_client.open_position(
                signal=signal,
                risk_amount=risk_amount,
                leverage=self.OWNER_LEVERAGE,
            )

            if result.get("success"):
                logger.info(
                    f"✅ Owner trade: {signal['signal_type']} "
                    f"{result['amount']} @ {result['fill_price']}"
                )
            return result

        except Exception as e:
            logger.error(f"Owner execution error: {e}")
            return {"success": False, "error": str(e), "account": "owner"}

    async def _execute_for_user(self, signal: Dict, user: Dict) -> Dict:
        """تنفيذ على حساب مستخدم"""
        try:
            # فك تشفير API Keys
            api_key, api_secret = self.user_manager.get_user_api(user["telegram_id"])
            if not api_key or not api_secret:
                return {"success": False, "error": "No API keys"}

            # إنشاء عميل للمستخدم
            client = MexcClient(api_key, api_secret, is_futures=True)

            # جلب الرصيد
            balance = client.get_balance()
            if not balance.get("success") or balance["free"] <= 0:
                return {"success": False, "error": "No balance"}

            # حساب المخاطرة حسب مستوى المستخدم
            risk_config = {
                "LOW": {"risk_pct": 1.0, "leverage": 5},
                "MEDIUM": {"risk_pct": 2.0, "leverage": 10},
                "HIGH": {"risk_pct": 5.0, "leverage": 20},
            }
            config = risk_config.get(user.get("risk_level", "MEDIUM"), risk_config["MEDIUM"])
            risk_amount = balance["free"] * (config["risk_pct"] / 100)

            # تنفيذ الصفقة
            result = client.open_position(
                signal=signal,
                risk_amount=risk_amount,
                leverage=config["leverage"],
            )

            if result.get("success"):
                logger.info(
                    f"✅ User @{user.get('username', '')} trade: "
                    f"{signal['signal_type']} {result['amount']} @ {result['fill_price']}"
                )
                # إشعار المستخدم
                await self._notify_user(user["telegram_id"], signal, result)

            return result

        except Exception as e:
            logger.error(f"User execution error: {e}")
            return {"success": False, "error": str(e)}

    async def _notify_user(self, telegram_id: int, signal: Dict, result: Dict):
        """إشعار المستخدم بتنفيذ الصفقة"""
        try:
            # هذا سيتم من البوت الرئيسي
            # نخزن الإشعار في dict مؤقت
            if not hasattr(self, '_pending_notifications'):
                self._pending_notifications = {}
            self._pending_notifications[telegram_id] = {
                "signal": signal,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Notify user error: {e}")

    def get_pending_notifications(self) -> Dict:
        """جلب الإشعارات المعلقة"""
        notifs = getattr(self, '_pending_notifications', {})
        self._pending_notifications = {}
        return notifs

    async def close_all_for_owner(self) -> Dict:
        """إغلاق كل صفقات المالك"""
        if self.owner_client:
            return self.owner_client.close_position()
        return {"success": False, "error": "Owner client not initialized"}

    async def close_all_for_user(self, telegram_id: int) -> Dict:
        """إغلاق كل صفقات مستخدم"""
        try:
            api_key, api_secret = self.user_manager.get_user_api(telegram_id)
            if not api_key or not api_secret:
                return {"success": False, "error": "User not found"}

            client = MexcClient(api_key, api_secret, is_futures=True)
            return client.close_position()
        except Exception as e:
            logger.error(f"Close all for user error: {e}")
            return {"success": False, "error": str(e)}

    def format_execution_report(self, results: Dict) -> str:
        """تقرير التنفيذ التلقائي"""
        msg = "🤖 تقرير التنفيذ التلقائي\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📊 الإشارة: {results.get('signal', '')} | {results.get('strategy', '')}\n"
        msg += f"✅ تم تنفيذ: {results['total_executed']}\n"
        msg += f"❌ فشل: {results['total_failed']}\n"

        if results.get("owner"):
            owner = results["owner"]
            if owner.get("success"):
                msg += f"\n👑 حسابك: ✅ {owner['side']} {owner['amount']} @ {owner['fill_price']:.2f}\n"
            else:
                msg += f"\n👑 حسابك: ❌ {owner.get('error', 'فشل')}\n"

        if results.get("users"):
            msg += "\n👥 المستخدمين:\n"
            for u in results["users"]:
                emoji = "✅" if u["result"].get("success") else "❌"
                msg += f"{emoji} @{u['username']}: "
                if u["result"].get("success"):
                    msg += f"{u['result']['side']} {u['result']['amount']} @ {u['result']['fill_price']:.2f}\n"
                else:
                    msg += f"{u['result'].get('error', 'فشل')}\n"

        msg += f"\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        msg += "🤖 BBPro Signal"

        return msg
