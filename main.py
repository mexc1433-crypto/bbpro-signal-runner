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
    swing_strategy, supertrend_strategy, multi_confluence_strategy
)
from risk_manager import RiskManager
from channel_manager import ChannelManager
from formatter import (
    format_signal_message, format_analysis_message,
    format_summary_message, format_market_update
)
from analysis import MarketAnalyzer

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
        self.fetcher = MarketDataFetcher(EXCHANGE_NAME)
        self.risk_manager = RiskManager()
        self.channel_manager = ChannelManager()
        self.analyzer = MarketAnalyzer(self.fetcher)

        self.strategies = ALL_STRATEGIES
        self.signal_history: List[Dict] = []
        self.public_channel = PUBLIC_CHANNEL_ID
        self.private_channel = PRIVATE_CHANNEL_ID

        logger.info("BBPro Signal Bot initialized")

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
                    # For MEDIUM strategies, allow them in MEDIUM scan
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
        welcome = (
            "🤖 مرحباً بك في BBPro Signal Bot\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 بوت إشارات تداول العملات الرقمية\n"
            "⚡ 8 استراتيجيات تداول متقدمة\n"
            "📈 17+ مؤشر فني\n"
            "🎯 3 أنواع صفقات (سريع/متوسط/بعيد)\n"
            "💰 تقسيم حسب رأس المال ($10 - $1000+)\n"
            "🛡️ إدارة مخاطر متقدمة\n\n"
            "📋 الأوامر المتاحة:\n"
            "/help - المساعدة\n"
            "/status - حالة البوت\n"
            "/scan - مسح فوري\n"
            "/analysis - تحليل السوق\n"
            "/summary - ملخص الإشارات\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ ليست نصيحة استثمارية"
        )
        await update.message.reply_text(welcome)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /help"""
        help_text = (
            "📋 دليل BBPro Signal Bot\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📊 الاستراتيجيات (8):\n"
            "• تتبع الاتجاه (EMA+ADX+MACD)\n"
            "• العودة للمتوسط (BB+RSI+Stoch)\n"
            "• الزخم (MACD+RSI+Vol+MFI)\n"
            "• الاختراق (Squeeze+Vol+ADX)\n"
            "• السكالبينج السريع (RSI7+EMA+Stoch+WR)\n"
            "• السوينج (Ichimoku+Fib+EMA+ADX)\n"
            "• السوبر ترند (ST+ATR+ADX)\n"
            "• التقاء متعدد (10 مؤشرات)\n\n"
            "📈 المؤشرات (17+):\n"
            "RSI, MACD, Bollinger, EMA, SMA, Stochastic,\n"
            "ATR, ADX, Ichimoku, VWAP, Fibonacci, Williams %R,\n"
            "CCI, MFI, OBV, Parabolic SAR, SuperTrend\n\n"
            "⚡ أنواع الصفقات:\n"
            "• سريع (5m/15m) - ربح 0.5-1.2%\n"
            "• متوسط (1h/4h) - ربح 1.5-4%\n"
            "• بعيد (1d) - ربح 3-8%\n\n"
            "💰 رأس المال: $10 → $1000+\n\n"
            "📡 القنوات:\n"
            "• العامة: 1-3 إشارات (سريع+متوسط) ربح صغير\n"
            "• الخاصة: 1-10 إشارات (متوسط+بعيد) ربح كبير\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ ليست نصيحة استثمارية"
        )
        await update.message.reply_text(help_text)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /status"""
        stats = self.channel_manager.get_daily_stats()
        status = (
            "📊 حالة BBPro Signal Bot\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 البوت: يعمل\n"
            f"💱 المنصة: {EXCHANGE_NAME.upper()}\n"
            f"📊 الأزواج: {len(TRADING_PAIRS)}\n"
            f"📈 الاستراتيجيات: 8\n"
            f"📏 المؤشرات: 17+\n\n"
            f"📋 إشارات اليوم:\n"
            f"  العامة: {stats['public_count']}/{stats['public_max']}\n"
            f"  الخاصة: {stats['private_count']}/{stats['private_max']}\n"
            f"  الإجمالي: {stats['public_count'] + stats['private_count']}\n\n"
            f"📊 إجمالي الإشارات: {len(self.signal_history)}\n"
            f"📅 الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(status)

    async def cmd_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /scan - مسح فوري"""
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("⛔ هذا الأمر للمشرف فقط")
            return

        await update.message.reply_text("🔄 بدء المسح الفوري لكل الأزواج...")
        signals = self.scan_market("ALL")
        if signals:
            await self.process_signals(signals)
            await update.message.reply_text(
                f"✅ تم العثور على {len(signals)} إشارة وتم إرسالها"
            )
        else:
            await update.message.reply_text("⚠️ لا توجد إشارات في الوقت الحالي")

    async def cmd_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /analysis"""
        await update.message.reply_text("📊 جاري تحليل السوق...")
        sentiment = self.analyzer.analyze_market_sentiment()
        message = format_analysis_message(sentiment)
        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /summary"""
        if not self.signal_history:
            await update.message.reply_text("⚠️ لا توجد إشارات اليوم بعد")
            return
        message = format_summary_message(self.signal_history)
        await update.message.reply_text(message, parse_mode='HTML')

    # ═══════════════════════════════════════════════════════════
    # Scheduler
    # ═══════════════════════════════════════════════════════════

    def run_async_job(self, coro_func):
        """يشغل coroutine job في الـ event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(coro_func())
        except Exception as e:
            logger.error(f"Job error: {e}")
        finally:
            loop.close()

    def scheduled_scalping(self):
        self.run_async_job(self.run_scalping_scan)

    def scheduled_medium(self):
        self.run_async_job(self.run_medium_scan)

    def scheduled_swing(self):
        self.run_async_job(self.run_swing_scan)

    def scheduled_analysis(self):
        self.run_async_job(self.send_market_analysis)

    def scheduled_summary(self):
        self.run_async_job(self.send_daily_summary)

    # ═══════════════════════════════════════════════════════════
    # Main Run
    # ═══════════════════════════════════════════════════════════

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
        logger.info(f"📊 Exchange: {EXCHANGE_NAME.upper()}")
        logger.info(f"💱 Pairs: {len(TRADING_PAIRS)}")
        logger.info(f"📈 Strategies: 8")
        logger.info(f"📏 Indicators: 17+")
        logger.info(f"📡 Public Channel: {'✅' if PUBLIC_CHANNEL_ID else '❌'}")
        logger.info(f"📡 Private Channel: {'✅' if PRIVATE_CHANNEL_ID else '❌'}")
        logger.info("=" * 60)

        # Setup schedules
        schedule.every(15).minutes.do(self.scheduled_scalping)
        schedule.every(60).minutes.do(self.scheduled_medium)
        schedule.every(4).hours.do(self.scheduled_swing)
        schedule.every(6).hours.do(self.scheduled_analysis)
        schedule.every().day.at("23:00").do(self.scheduled_summary)

        # Setup Telegram commands
        app = Application.builder().token(BOT_TOKEN).build()

        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("scan", self.cmd_scan))
        app.add_handler(CommandHandler("analysis", self.cmd_analysis))
        app.add_handler(CommandHandler("summary", self.cmd_summary))

        # Run scheduler in background
        async def run_scheduler(app):
            while True:
                schedule.run_pending()
                await asyncio.sleep(30)

        async def post_init(app):
            await self.bot.send_message(
                chat_id=PRIVATE_CHANNEL_ID or PUBLIC_CHANNEL_ID,
                text="🤖 BBPro Signal Bot بدأ العمل!\n\n✅ جميع الأنظمة جاهزة\n📊 8 استراتيجيات | 17+ مؤشر\n⏱️ المسح التلقائي مفعّل"
            )
            asyncio.create_task(run_scheduler(app))

        app.post_init = post_init

        logger.info("Bot is running! Press Ctrl+C to stop.")
        app.run_polling(stop_signals=None)


if __name__ == '__main__':
    bot = BBProSignalBot()
    bot.run()
