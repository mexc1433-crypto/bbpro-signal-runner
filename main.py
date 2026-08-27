"""
BBPro Signal Bot - Main Entry Point
نقطة التشغيل الرئيسية
"""
import asyncio
import logging
import schedule
import time
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional

# Telegram
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Local imports
from config import *
from market_data import MarketDataFetcher
from indicators import calculate_all_indicators
from strategies import (
    ALL_STRATEGIES, trend_following_strategy, mean_reversion_strategy,
    momentum_strategy, breakout_strategy, scalping_strategy,
    swing_strategy, supertrend_strategy, multi_confluence_strategy,
    vwap_strategy, ichimoku_cloud_strategy, cci_williams_strategy,
    parabolic_sar_strategy, volume_breakout_strategy
)
from risk_manager import RiskManager
from channel_manager import ChannelManager
from formatter import (
    format_signal_message, format_analysis_message,
    format_summary_message, format_market_update
)
from analysis import MarketAnalyzer
from signal_tracker import SignalTracker
from economic_calendar import EconomicCalendar
from confluence import ConfluenceAnalyzer

# ═══════════════════════════════════════════════════════════════
# Logging Setup
# ═══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bbpro_bot.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger("BBProBot")


class BBProSignalBot:
    """البوت الرئيسي لإشارات التداول"""

    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.fetcher = MarketDataFetcher()
        self.risk_manager = RiskManager()
        self.channel_manager = ChannelManager()
        self.analyzer = MarketAnalyzer(self.fetcher)
        self.tracker = SignalTracker()
        self.calendar = EconomicCalendar()
        self.confluence = ConfluenceAnalyzer(self.fetcher)

        self.strategies = ALL_STRATEGIES
        self.signal_history: List[Dict] = []
        self.public_channel = PUBLIC_CHANNEL_ID
        self.private_channel = PRIVATE_CHANNEL_ID
        self._app = None  # Reference to the telegram Application
        self.admin_id = ADMIN_ID  # only owner can use commands

        logger.info("BBPro Signal Bot initialized")

    def _is_admin(self, user_id: int) -> bool:
        """يتحقق إن المستخدم هو الأدمن فقط"""
        if self.admin_id and user_id == self.admin_id:
            return True
        return False

    async def _check_admin(self, update: Update) -> bool:
        """فحص الأدمن قبل أي أمر - يرفع غير المصرح"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            logger.warning(f"⚠️ Unauthorized access by {user_id} ({update.effective_user.full_name})")
            await update.message.reply_text(
                "🚫 عذراً، هذا البوت خاص ولا يمكن استخدامه إلا من قبل المالك."
            )
            return False
        return True

    # ═══════════════════════════════════════════════════════════
    # Market Scanning
    # ═══════════════════════════════════════════════════════════

    def scan_market(self, trade_type: str = "ALL") -> List[Dict]:
        """
        يمسح السوق بالكامل ويولّد الإشارات
        """
        all_signals = []
        pairs = TRADING_PAIRS

        # Determine which strategies to run based on trade type
        if trade_type == "SCALPING":
            timeframes = TIMEFRAMES["SCALPING"]
            strategy_names = ["scalping"]
        elif trade_type == "MEDIUM":
            timeframes = TIMEFRAMES["MEDIUM"]
            strategy_names = ["trend_following", "mean_reversion", "momentum", "supertrend", "multi_confluence"]
        elif trade_type == "SWING":
            timeframes = TIMEFRAMES["SWING"]
            strategy_names = ["breakout", "swing", "multi_confluence"]
        else:
            strategy_names = list(self.strategies.keys())
            timeframes = []

        for symbol in pairs:
            logger.info(f"Scanning {symbol}...")

            for strat_name in strategy_names:
                strat_config = self.strategies[strat_name]
                strat_func = strat_config["func"]
                strat_trade_type = strat_config["trade_type"]

                # Skip if trade type doesn't match (when filtering)
                if trade_type != "ALL" and strat_trade_type != trade_type:
                    if trade_type == "MEDIUM" and strat_trade_type == "MEDIUM":
                        pass
                    elif trade_type == "SWING" and strat_trade_type == "SWING":
                        pass
                    elif trade_type == "SCALPING" and strat_trade_type == "SCALPING":
                        pass
                    else:
                        continue

                # Get timeframes for this strategy's trade type
                tfs = TIMEFRAMES.get(strat_trade_type, ["4h"])

                for tf in tfs:
                    try:
                        df = self.fetcher.fetch_ohlcv(symbol, tf, 200)
                        if df.empty or len(df) < 50:
                            continue

                        signal = strat_func(df, symbol, strat_trade_type)
                        if signal and signal.get("signal_type") != "NEUTRAL":
                            signal["symbol"] = symbol
                            signal["timeframe"] = tf
                            all_signals.append(signal)
                            logger.info(f"Signal found: {symbol} {signal['signal_type']} "
                                       f"({signal['strategy_name']}) confidence={signal['confidence']}%")

                    except Exception as e:
                        logger.error(f"Error scanning {symbol} {tf} {strat_name}: {e}")

        # Sort by confidence
        all_signals.sort(key=lambda x: x["confidence"], reverse=True)
        return all_signals

    # ═══════════════════════════════════════════════════════════
    # Signal Processing & Distribution
    # ═══════════════════════════════════════════════════════════

    async def process_signals(self, signals: List[Dict]):
        # تحسين الإشارات بالتطابق متعدد الأطر
        try:
            confluence_data = self.confluence.analyze_confluence()
            if confluence_data and confluence_data.get("confidence_boost", 0) > 0:
                for signal in signals:
                    self.confluence.enhance_signal_with_confluence(signal, confluence_data)
                logger.info(f"Confluence: {confluence_data['confluence_level']} (+{confluence_data['confidence_boost']}%)")
        except Exception as e:
            logger.warning(f"Confluence analysis failed: {e}")
        """يوزع الإشارات على القنوات المناسبة"""
        for signal in signals:
            # Calculate capital plans
            capital_plans = self.risk_manager.get_all_capital_plans(signal)

            # Determine which channels to send to
            channels = self.channel_manager.get_channel_for_signal(signal)

            for channel in channels:
                if not self.channel_manager.can_send_more(channel):
                    logger.info(f"Channel {channel} daily limit reached")
                    continue

                try:
                    await self.send_signal_to_channel(signal, capital_plans, channel)
                    self.channel_manager.record_signal(channel, signal)
                    self.signal_history.append({**signal, "channel": channel})

                    # Avoid sending too many at once
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Error sending to {channel}: {e}")

    async def send_signal_to_channel(self, signal: Dict, capital_plans: List[Dict],
                                       channel_type: str):
        """يرسل إشارة لقناة محددة"""
        channel_id = self.private_channel if channel_type == "PRIVATE" else self.public_channel

        if not channel_id:
            logger.warning(f"No channel ID for {channel_type}")
            return

        message = format_signal_message(signal, capital_plans, channel_type)

        try:
            await self.bot.send_message(
                chat_id=channel_id,
                text=message,
                parse_mode='HTML'
            )
            logger.info(f"Signal sent to {channel_type} channel: {signal['symbol']}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    # ═══════════════════════════════════════════════════════════
    # Market Analysis
    # ═══════════════════════════════════════════════════════════

    async def send_market_analysis(self):
        """يرسل تحليل السوق للقناتين"""
        try:
            sentiment = self.analyzer.analyze_market_sentiment()
            message = format_analysis_message(sentiment)

            for channel_id in [self.public_channel, self.private_channel]:
                if channel_id:
                    try:
                        await self.bot.send_message(
                            chat_id=channel_id,
                            text=message,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logger.error(f"Error sending analysis: {e}")

            logger.info("Market analysis sent")
        except Exception as e:
            logger.error(f"Error in market analysis: {e}")

    # ═══════════════════════════════════════════════════════════
    # Daily Summary
    # ═══════════════════════════════════════════════════════════

    async def send_daily_summary(self):
        """يرسل ملخص يومي"""
        if not self.signal_history:
            return

        message = format_summary_message(self.signal_history)

        for channel_id in [self.private_channel]:
            if channel_id:
                try:
                    await self.bot.send_message(
                        chat_id=channel_id,
                        text=message,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error sending summary: {e}")

        # Reset daily counts
        self.channel_manager.reset_daily_counts()
        self.signal_history.clear()

    # ═══════════════════════════════════════════════════════════
    # Scheduled Scans
    # ═══════════════════════════════════════════════════════════

    async def run_scalping_scan(self):
        """مسح السكالبينج كل 15 دقيقة"""
        logger.info("🔄 Starting SCALPING scan...")
        signals = self.scan_market("SCALPING")
        if signals:
            await self.process_signals(signals)
        logger.info(f"Scalping scan complete: {len(signals)} signals found")

    async def run_medium_scan(self):
        """مسح المتوسط كل ساعة"""
        logger.info("🔄 Starting MEDIUM scan...")
        signals = self.scan_market("MEDIUM")
        if signals:
            await self.process_signals(signals)
        logger.info(f"Medium scan complete: {len(signals)} signals found")

    async def run_swing_scan(self):
        """مسح السوينج كل 4 ساعات"""
        logger.info("🔄 Starting SWING scan...")
        signals = self.scan_market("SWING")
        if signals:
            await self.process_signals(signals)
        logger.info(f"Swing scan complete: {len(signals)} signals found")

    # ═══════════════════════════════════════════════════════════
    # Bot Commands
    # ═══════════════════════════════════════════════════════════

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /start"""
        if not await self._check_admin(update):
            return
        await update.message.reply_text(
            "🤖 **BBPro Signal Bot**\n\n"
            "بوت إشارات تداول العملات الرقمية\n"
            "📊 13 استراتيجيات | 22+ مؤشر | XAU/USD فقط\n"
            "⚡ 3 أنواع صفقات: سريع / متوسط / بعيد\n\n"
            "الأوامر المتاحة:\n"
            "/help - المساعدة\n"
            "/status - حالة البوت\n"
            "/scan - مسح فوري للسوق\n"
            "/analysis - تحليل السوق\n"
            "/summary - ملخص الإشارات\n"
            "/performance - تقرير الأداء\n"
            "/calendar - الأحداث الاقتصادية\n"
            "/confluence - تحليل التطابق"
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /help"""
        if not await self._check_admin(update):
            return
        await update.message.reply_text(
            "📋 **مساعدة BBPro Signal Bot**\n\n"
            "الأوامر:\n"
            "/start - بدء البوت\n"
            "/status - حالة البوت والإعدادات\n"
            "/scan - مسح فوري للسوق\n"
            "/analysis - تحليل شامل للسوق\n"
            "/summary - ملخص إشارات اليوم\n\n"
            "الاستراتيجيات:\n"
            "• Trend Following\n"
            "• Mean Reversion\n"
            "• Momentum\n"
            "• Breakout\n"
            "• Scalping\n"
            "• Swing\n"
            "• Supertrend\n"
            "• Multi-Confluence\n\n"
            "أنواع الصفقات:\n"
            "⚡ سريع (Scalping) - 1-3 دقائق\n"
            "📊 متوسط (Medium) - ساعة لعدة ساعات\n"
            "🎯 بعيد (Swing) - أيام لأسابيع"
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /status"""
        if not await self._check_admin(update):
            return
        status = (
            "📊 **حالة BBPro Signal Bot**\n\n"
            "الرمز: XAU/USD (الذهب)\n"
            f"الأزواج: {len(TRADING_PAIRS)}\n"
            f"الاستراتيجيات: 8\n"
            f"المؤشرات: 17+\n"
            f"القناة العامة: {'✅' if PUBLIC_CHANNEL_ID else '❌'}\n"
            f"القناة الخاصة: {'✅' if PRIVATE_CHANNEL_ID else '❌'}\n\n"
            f"إشارات اليوم: {len(self.signal_history)}\n"
            f"الحالة: 🟢 يعمل"
        )
        await update.message.reply_text(status)

    async def cmd_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /scan - مسح فوري"""
        if not await self._check_admin(update):
            return
        await update.message.reply_text("🔄 جاري مسح السوق... قد يستغرق دقيقة")
        logger.info(f"Manual scan requested by {update.effective_user.id}")
        signals = self.scan_market("ALL")
        if signals:
            await self.process_signals(signals)
            await update.message.reply_text(f"✅ تم العثور على {len(signals)} إشارة!")
        else:
            await update.message.reply_text("⚠️ لا توجد إشارات في الوقت الحالي")

    async def cmd_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /analysis"""
        if not await self._check_admin(update):
            return
        await update.message.reply_text("📊 جاري تحليل السوق...")
        await self.send_market_analysis()

    async def cmd_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /summary"""
        if not await self._check_admin(update):
            return
        if not self.signal_history:
            await update.message.reply_text("⚠️ لا توجد إشارات اليوم بعد")
            return
        message = format_summary_message(self.signal_history)
        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /performance - تقرير الأداء"""
        if not await self._check_admin(update):
            return
        report = self.tracker.get_performance_report(days=7)
        await update.message.reply_text(report)

    async def cmd_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /calendar - الأحداث الاقتصادية"""
        if not await self._check_admin(update):
            return
        events = self.calendar.get_upcoming_events(hours_ahead=48)
        msg = self.calendar.format_events_message(events)
        await update.message.reply_text(msg)

    async def cmd_confluence(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /confluence - تحليل التطابق"""
        if not await self._check_admin(update):
            return
        await update.message.reply_text("📊 جاري تحليل التطابق...")
        data = self.confluence.analyze_confluence()
        msg = self.confluence.format_confluence_report(data)
        await update.message.reply_text(msg)

    # ═══════════════════════════════════════════════════════════
    # Scheduler — FIXED: uses asyncio.create_task instead of new event loop
    # ═══════════════════════════════════════════════════════════

    def _schedule_async(self, coro_func):
        """يضيف coroutine task للـ event loop النشط (بلا ما يفتح loop جديد)"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(coro_func(), loop=loop)
            else:
                loop.run_until_complete(coro_func())
        except RuntimeError:
            # لو مفيش loop نشط، نفتح واحد
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(coro_func())
            except Exception as e:
                logger.error(f"Job error: {e}")
            finally:
                loop.close()

    def scheduled_scalping(self):
        logger.info("⏰ Scalping schedule triggered")
        self._schedule_async(self.run_scalping_scan)

    def scheduled_medium(self):
        logger.info("⏰ Medium schedule triggered")
        self._schedule_async(self.run_medium_scan)

    def scheduled_swing(self):
        logger.info("⏰ Swing schedule triggered")
        self._schedule_async(self.run_swing_scan)

    def scheduled_analysis(self):
        logger.info("⏰ Analysis schedule triggered")
        self._schedule_async(self.send_market_analysis)

    def scheduled_summary(self):
        logger.info("⏰ Daily summary schedule triggered")
        self._schedule_async(self.send_daily_summary)

    def scheduled_news_check(self):
        logger.info("⏰ News check triggered")
        self._schedule_async(self.check_news_alerts)

    # ═══════════════════════════════════════════════════════════
    # Main Run
    # ═══════════════════════════════════════════════════════════

    async def check_news_alerts(self):
        """يفحص ويطلق تنبيهات الأخبار"""
        try:
            event = self.calendar.check_and_alert()
            if event:
                msg = self.calendar.format_pre_alert(event)
                if self.private_channel:
                    await self.bot.send_message(chat_id=self.private_channel, text=msg)
                    logger.info(f"News alert sent: {event['title']}")
        except Exception as e:
            logger.error(f"News alert error: {e}")

    def run(self):
        """نقطة التشغيل الرئيسية"""
        # Validate config
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN not set! Check .env file")
            sys.exit(1)

        if not PUBLIC_CHANNEL_ID and not PRIVATE_CHANNEL_ID:
            logger.error("No channel IDs set! Check .env file")
            sys.exit(1)

        logger.info("=" * 60)
        logger.info("🚀 BBPro Signal Bot Starting...")
        logger.info("📊 Symbol: XAU/USD (Gold)")
        logger.info(f"💱 Pair: XAU/USD (Gold)")
        logger.info(f"📈 Strategies: 13")
        logger.info(f"📏 Indicators: 22+")
        logger.info(f"📡 Public Channel: {'✅' if PUBLIC_CHANNEL_ID else '❌'}")
        logger.info(f"📡 Private Channel: {'✅' if PRIVATE_CHANNEL_ID else '❌'}")
        logger.info("=" * 60)

        # Setup schedules
        schedule.every(15).minutes.do(self.scheduled_scalping)
        schedule.every(60).minutes.do(self.scheduled_medium)
        schedule.every(4).hours.do(self.scheduled_swing)
        schedule.every(10).minutes.do(self.scheduled_news_check)
        schedule.every(6).hours.do(self.scheduled_analysis)
        schedule.every().day.at("23:00").do(self.scheduled_summary)

        # Setup Telegram commands
        app = Application.builder().token(BOT_TOKEN).build()
        self._app = app

        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("scan", self.cmd_scan))
        app.add_handler(CommandHandler("analysis", self.cmd_analysis))
        app.add_handler(CommandHandler("summary", self.cmd_summary))
        app.add_handler(CommandHandler("performance", self.cmd_performance))
        app.add_handler(CommandHandler("calendar", self.cmd_calendar))
        app.add_handler(CommandHandler("confluence", self.cmd_confluence))

        # Run scheduler in background — داخل الـ event loop النشط
        async def run_scheduler(app):
            # أول scan فوري بعد 30 ثانية من الإطلاق
            logger.info("⏱️ Initial scan in 30 seconds...")
            await asyncio.sleep(30)
            logger.info("🔄 Running initial scalping scan...")
            await self.run_scalping_scan()
            logger.info("🔄 Running initial medium scan...")
            await self.run_medium_scan()

            # بعدها الجدولة العادية
            while True:
                schedule.run_pending()
                await asyncio.sleep(30)

        async def post_init(app):
            await self.bot.send_message(
                chat_id=PRIVATE_CHANNEL_ID or PUBLIC_CHANNEL_ID,
                text="🤖 BBPro Signal Bot بدأ العمل!\n\n"
                     "✅ جميع الأنظمة جاهزة\n"
                     "📊 13 استراتيجيات | 22+ مؤشر | XAU/USD فقط\n"
                     "⏱️ المسح التلقائي مفعّل\n"
                     "🔄 أول مسح بعد 30 ثانية"
            )
            asyncio.create_task(run_scheduler(app))

        app.post_init = post_init

        logger.info("Bot is running! Press Ctrl+C to stop.")
        app.run_polling(stop_signals=None)


if __name__ == '__main__':
    bot = BBProSignalBot()
    bot.run()
