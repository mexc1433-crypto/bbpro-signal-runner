"""
صياد الشمعات | Candle Hunter — Pre-Close Alerts
تنبيه قبل إغلاق الصفقة بـ 5 دقايق
"""
import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)


class PreCloseAlert:
    """تنبيه قبل ما TP أو SL يضرب بـ 5 دقايق"""

    # النسبة اللي من خلالها نبعت تنبيه (90% من المسافة للهدف)
    ALERT_THRESHOLD_TP = 0.85  # لما السعر يوصل 85% من المسافة للـ TP
    ALERT_THRESHOLD_SL = 0.85  # لما السعر يوصل 85% من المسافة للـ SL

    def __init__(self):
        self.alerted_signals = set()  # اللي اتبعتلهم تنبيه

    def check_signals(self, pending_signals: List[Dict], current_price: float, bot=None, user_ids: List[int] = None) -> List[Dict]:
        """يفحص كل الإشارات المعلقة — يبعت تنبيه لو قربت تختتم"""
        alerts_sent = []

        for signal in pending_signals:
            sig_id = signal.get("id", "")
            if sig_id in self.alerted_signals:
                continue  # اتبعت قبل كدا

            entry = signal.get("entry_price", 0)
            tp1 = signal.get("take_profit_1", 0)
            sl = signal.get("stop_loss", 0)
            sig_type = signal.get("signal_type", "")

            if not entry or not tp1 or not sl:
                continue

            # حساب المسافة للهدف والستوب
            tp_distance = abs(tp1 - entry)
            sl_distance = abs(entry - sl)

            if tp_distance == 0 or sl_distance == 0:
                continue

            # المسافة الحالية من الدخول
            current_distance = abs(current_price - entry)

            # هل السعر قرب من TP؟
            if sig_type == "BUY":
                tp_progress = (current_price - entry) / tp_distance if tp_distance else 0
                sl_progress = (entry - current_price) / sl_distance if sl_distance else 0
            else:
                tp_progress = (entry - current_price) / tp_distance if tp_distance else 0
                sl_progress = (current_price - entry) / sl_distance if sl_distance else 0

            # قربت من TP
            if tp_progress >= self.ALERT_THRESHOLD_TP and tp_progress < 1.0:
                self._send_alert(signal, current_price, "TP", bot, user_ids)
                self.alerted_signals.add(sig_id)
                alerts_sent.append({"id": sig_id, "type": "TP", "price": current_price})
                logger.info(f"⏰ Pre-close alert: {sig_id} approaching TP ({tp_progress:.0%})")

            # قربت من SL
            elif sl_progress >= self.ALERT_THRESHOLD_SL and sl_progress < 1.0:
                self._send_alert(signal, current_price, "SL", bot, user_ids)
                self.alerted_signals.add(sig_id)
                alerts_sent.append({"id": sig_id, "type": "SL", "price": current_price})
                logger.info(f"⏰ Pre-close alert: {sig_id} approaching SL ({sl_progress:.0%})")

        return alerts_sent

    def _send_alert(self, signal: Dict, current_price: float, alert_type: str, bot=None, user_ids: List[int] = None):
        """يبعت تنبيه للأدمن"""
        if not bot:
            return

        sig_type = signal.get("signal_type", "")
        direction = "شراء" if sig_type == "BUY" else "بيع"
        entry = signal.get("entry_price", 0)
        target = signal.get("take_profit_1", 0) if alert_type == "TP" else signal.get("stop_loss", 0)

        emoji = "🎯" if alert_type == "TP" else "🛑"
        msg = (
            f"{emoji} تنبيه قبل الإغلاق!\n\n"
            f"{'قربت تضرب الهدف 🎯' if alert_type == 'TP' else 'قربت تضرب الستوب 🛑'}\n\n"
            f"{'شراء' if sig_type == 'BUY' else 'بيع'} | XAU/USD\n"
            f"💵 الدخول: ${entry:,.2f}\n"
            f"{'🎯 الهدف' if alert_type == 'TP' else '🛑 الستوب'}: ${target:,.2f}\n"
            f"📊 السعر الحالي: ${current_price:,.2f}\n\n"
            f"⏰ راقب الصفقة!\n"
            f"🤖 صياد الشمعات | Candle Hunter"
        )

        # إرسال للأدمن
        from config import ADMIN_ID
        try:
            import asyncio
            asyncio.create_task(bot.send_message(chat_id=ADMIN_ID, text=msg))
        except Exception as e:
            logger.warning(f"Pre-close alert send failed: {e}")

    def cleanup(self, closed_signal_ids: List[str]):
        """تنظيف الإشارات اللي اغلقت"""
        for sid in closed_signal_ids:
            self.alerted_signals.discard(sid)
