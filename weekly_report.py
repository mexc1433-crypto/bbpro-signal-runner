"""
صياد الشمعات | Candle Hunter — Weekly Performance Report
تقرير أسبوعي تلقائي كل يوم جمعة
"""
import logging
from datetime import datetime, timedelta
from typing import Dict

logger = logging.getLogger(__name__)


class WeeklyReporter:
    """تقرير الأداء الأسبوعي التلقائي"""

    def __init__(self, tracker, bot=None, channel_id=None, admin_id=None):
        self.tracker = tracker
        self.bot = bot
        self.channel_id = channel_id
        self.admin_id = admin_id
        self.last_report_date = None

    async def send_weekly_report(self):
        """يبعت التقرير الأسبوعي — يتمن كل يوم جمعة 8 مساءً"""
        now = datetime.now()

        # نتأكد إنه جمعة
        if now.weekday() != 4:  # 4 = Friday
            return

        # نتأكد إنه ما إتبعتش النهارده
        today_str = now.strftime("%Y-%m-%d")
        if self.last_report_date == today_str:
            return

        try:
            stats = self.tracker.get_performance_stats(days=7)
            report = self._format_report(stats)

            # إرسال للقناة الخاصة
            if self.bot and self.channel_id:
                await self.bot.send_message(
                    chat_id=self.channel_id,
                    text=report,
                    parse_mode='HTML',
                )
                logger.info("📊 Weekly report sent to channel")

            # إرسال للأدمن كمان
            if self.bot and self.admin_id:
                await self.bot.send_message(
                    chat_id=self.admin_id,
                    text=report,
                    parse_mode='HTML',
                )

            self.last_report_date = today_str
        except Exception as e:
            logger.error(f"Weekly report failed: {e}")

    def _format_report(self, stats: Dict) -> str:
        """تنسيق التقرير الأسبوعي"""
        total = stats.get("total_signals", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        pending = stats.get("pending", 0)
        win_rate = stats.get("win_rate", 0)
        best_pnl = stats.get("best_pnl", 0)
        worst_pnl = stats.get("worst_pnl", 0)
        avg_pnl = stats.get("avg_pnl", 0)
        total_pnl = stats.get("total_pnl", 0)
        best_strategy = stats.get("best_strategy", "N/A")

        # الأسبوع
        now = datetime.now()
        week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        week_end = now.strftime("%Y-%m-%d")

        msg = "📊 التقرير الأسبوعي — صياد الشمعات\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📅 الفترة: {week_start} → {week_end}\n\n"

        msg += f"📈 إجمالي الإشارات: {total}\n"
        msg += f"✅ رابحة: {wins}\n"
        msg += f"❌ خاسرة: {losses}\n"
        msg += f"⏳ معلقة: {pending}\n\n"

        if total > 0:
            msg += f"🎯 نسبة النجاح: {win_rate:.1f}%\n"
            msg += f"💰 أفضل صفقة: {best_pnl:+.2f}%\n"
            msg += f"📉 أسوأ صفقة: {worst_pnl:+.2f}%\n"
            msg += f"📊 متوسط الربح: {avg_pnl:+.2f}%\n"
            msg += f"💵 إجمالي الأداء: {total_pnl:+.2f}%\n\n"

            if best_strategy != "N/A":
                msg += f"🏆 أفضل استراتيجية: {best_strategy}\n"

        msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "⚠️ ليست نصيحة استثمارية\n"
        msg += "🤖 صياد الشمعات | Candle Hunter"

        return msg

    def should_run_now(self) -> bool:
        """هل الوقت مناسب لإرسال التقرير؟ (جمعة 8م)"""
        now = datetime.now()
        if now.weekday() != 4:  # Friday
            return False
        if now.hour != 20:  # 8 PM
            return False
        today_str = now.strftime("%Y-%m-%d")
        if self.last_report_date == today_str:
            return False
        return True
