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

    def __init__(self, tracker, bot=None, channel_id=None, admin_id=None, public_channel_id=None):
        self.tracker = tracker
        self.bot = bot
        self.channel_id = channel_id
        self.admin_id = admin_id
        self.public_channel_id = public_channel_id
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

            # إرسال نسخة تسويقية للقناة العامة (إثبات الأداء للمشتركين المحتملين)
            if self.bot and self.public_channel_id:
                try:
                    await self.bot.send_message(
                        chat_id=self.public_channel_id,
                        text=self._format_public_report(stats),
                        parse_mode='HTML',
                    )
                    logger.info("📊 Weekly report sent to PUBLIC channel")
                except Exception as e:
                    logger.warning(f"Public weekly report failed: {e}")

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

        # 🎯 معايرة الثقة — للنسخة التفصيلية (الخاصة + الأدمن)
        try:
            calib = self.tracker.get_calibration(days=30)
            has_calib = any(v["signals"] > 0 for v in calib.values())
            if has_calib:
                msg += "\n🎯 معايرة الثقة (30 يوم):\n"
                for bucket, v in calib.items():
                    if v["signals"] == 0:
                        continue
                    wr = f"{v['win_rate']:.0f}%" if v["win_rate"] is not None else "—"
                    msg += f"  • {bucket}% → {v['signals']} إشارة | نجاح فعلي {wr}\n"
        except Exception:
            pass

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

    def _format_public_report(self, stats: Dict) -> str:
        """نسخة تسويقية للقناة العامة — إثبات أداء + دعوة اشتراك"""
        total = stats.get("total_signals", 0)
        wins = stats.get("wins", 0)
        win_rate = stats.get("win_rate", 0)
        best_pnl = stats.get("best_pnl", 0)
        avg_pnl = stats.get("avg_pnl", 0)

        now = datetime.now()
        week_start = (now - timedelta(days=7)).strftime("%d/%m")
        week_end = now.strftime("%d/%m")

        msg = "📊 تقرير الأداء الأسبوعي\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📅 {week_start} → {week_end}\n\n"
        if total > 0:
            msg += f"🎯 إشارات نشرت: {total}\n"
            msg += f"✅ صفقات رابحة: {wins}\n"
            msg += f"🏆 نسبة النجاح: {win_rate:.0f}%\n"
            msg += f"📈 متوسط العائد: {avg_pnl:+.2f}%\n"
            msg += f"💰 أفضل صفقة: {best_pnl:+.2f}%\n\n"
            msg += "الجودة قبل الكمية — إشارات مفلترة بثقة 85%+ فقط\n\n"
        else:
            msg += "لا إشارات كافية هذا الأسبوع — الجودة قبل الكمية\n\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "🚀 اشترك في القناة الخاصة لتصلك الإشارات لحظياً\n"
        msg += "⚠️ ليست نصيحة استثمارية\n"
        msg += "🤖 صياد الشمعات | Candle Hunter"
        return msg
