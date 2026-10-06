"""
صياد الشمعات | Candle Hunter - Main Entry Point
نقطة التشغيل الرئيسية
"""
import subprocess
import sys

# Runtime install of missing packages (bypass Docker build cache)
def _ensure_packages():
    missing = []
    try:
        import ccxt
    except ImportError:
        missing.append("ccxt==4.5.75")
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        missing.append("cryptography>=42.0.0")
    if missing:
        print(f"Installing missing packages: {missing}")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)

_ensure_packages()

import asyncio
import logging
# schedule replaced by PTB JobQueue
import time
import sys
import os
import json
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional

# Telegram
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

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
from chart_generator import generate_signal_chart
from economic_calendar import EconomicCalendar
from confluence import ConfluenceAnalyzer
from enhanced_confluence import EnhancedConfluence
from enhanced_apis import finnhub_news, groq_analyze_news, get_confidence_adjustment
from signal_filters import VolatilityFilter, ActiveHoursFilter, TrendFilter
from price_alerts import PriceAlertManager
from smc_analyzer import SMCAnalyzer
from mtf_confluence import MTFConfluence
from advanced_features import (
    BalanceChecker, SmartPositionSizer, ConflictResolver,
    FearGreedIndex, DXYFilter, SpreadFilter, US10YFilter,
    SignalCooldown, MarketHoursManager, AutoRestartManager,
)
from weekly_report import WeeklyReporter
from referral_system import ReferralSystem
from pre_close_alert import PreCloseAlert
from user_manager import UserManager, Encryption
from auto_trader import AutoTrader
from signal_forwarder import SignalForwarder
import pandas as pd
from mexc_client import MexcClient
from circuit_breaker import CircuitBreaker
from subscription_manager import SubscriptionManager
from adaptive_learning import AdaptiveLearning

# ═══════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("CandleHunterBot")

# Reduce noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


class CandleHunterSignalBot:
    """البوت الرئيسي"""

    # مراحل التسجيل
    REG_STEP_UID = "awaiting_uid"
    REG_STEP_API_KEY = "awaiting_api_key"
    REG_STEP_API_SECRET = "awaiting_api_secret"

    def __init__(self):
        self.bot: Optional[Bot] = None
        self.fetcher = MarketDataFetcher()
        self.risk_manager = RiskManager()
        self.channel_manager = ChannelManager()
        self.analyzer = MarketAnalyzer(self.fetcher)
        self.tracker = SignalTracker()
        self.calendar = EconomicCalendar()
        self.confluence = ConfluenceAnalyzer(self.fetcher)
        self.enhanced_confluence = EnhancedConfluence(self.fetcher)
        self.volatility_filter = VolatilityFilter()
        self.active_hours_filter = ActiveHoursFilter()
        self.trend_filter = TrendFilter(self.fetcher)
        self.price_alerts = PriceAlertManager()
        self.smc = SMCAnalyzer()
        self.mtf = MTFConfluence()
        self.broadcast_state = {}  # for broadcast feature

        # ===== Advanced Features (non-dependent on auto_trader) =====
        self.position_sizer = SmartPositionSizer()
        self.conflict_resolver = ConflictResolver()
        self.fear_greed = FearGreedIndex()
        self.dxy_filter = DXYFilter(self.fetcher)
        self.us10y_filter = US10YFilter(self.fetcher)
        self.spread_filter = SpreadFilter(self.fetcher)
        self.cooldown = SignalCooldown()
        self.market_hours = MarketHoursManager()
        self.auto_restart = AutoRestartManager()
        self.circuit_breaker = CircuitBreaker()
        self.subscription_manager = SubscriptionManager()
        self.adaptive_learning = AdaptiveLearning()
        self._max_concurrent_positions = 1
        self._scheduler_task = None
        self.pre_close = PreCloseAlert()
        self.referral_system = ReferralSystem()
        self.weekly_reporter = None  # يتظهر بعد ما bot يتعمل
        self.user_manager = UserManager()

        # Auto-trader (سيتم تهيئته بعد قراءة env vars)
        owner_api_key = os.getenv("MEXC_API_KEY", "")
        owner_api_secret = os.getenv("MEXC_API_SECRET", "")
        self.forwarder = SignalForwarder()
        self.auto_trader = AutoTrader(self.user_manager, owner_api_key, owner_api_secret)
        self.balance_checker = BalanceChecker(self.auto_trader)

        self.strategies = ALL_STRATEGIES
        self.signal_history: List[Dict] = []
        self.private_channel = int(PRIVATE_CHANNEL_ID) if PRIVATE_CHANNEL_ID else None
        self.public_channel = int(PUBLIC_CHANNEL_ID) if PUBLIC_CHANNEL_ID else None
        self.admin_id = ADMIN_ID
        self.mexc_referral_code = os.getenv("MEXC_REFERRAL_CODE", "")

        # حالة التسجيل المؤقتة
        self._registration_state: Dict[int, Dict] = {}

    # ═══════════════════════════════════════════════════════════
    # Helper Functions
    # ═══════════════════════════════════════════════════════════

    def _is_admin(self, user_id: int) -> bool:
        return user_id == self.admin_id

    async def _check_channel_subscription(self, user_id: int) -> bool:
        """فحص اشتراك المستخدم في القناة العامة"""
        if not self.public_channel:
            return True  # لو مفيش قناة، اسمح
        try:
            member = await self.bot.get_chat_member(self.public_channel, user_id)
            return member.status in ["member", "administrator", "creator"]
        except Exception as e:
            logger.warning(f"Channel subscription check failed: {e}")
            return False

    def _get_main_menu(self, is_admin: bool = False) -> InlineKeyboardMarkup:
        """القائمة الرئيسية بأزرار"""
        buttons = [
            [InlineKeyboardButton("📡 مسح السوق", callback_data="scan"),
             InlineKeyboardButton("📊 حالة السوق", callback_data="status")],
            [InlineKeyboardButton("📈 ملخص اليوم", callback_data="summary"),
             InlineKeyboardButton("🎯 تحليل التطابق", callback_data="confluence")],
            [InlineKeyboardButton("🔬 تحليل 20 مؤشر", callback_data="scan_pro")],
            [InlineKeyboardButton("📈 الإحصائيات", callback_data="stats"),
             InlineKeyboardButton("🔔 تنبيه سعر", callback_data="price_alerts")],
            [InlineKeyboardButton("👥 الإحالة", callback_data="referral"),
             InlineKeyboardButton("🕒 حالة السوق", callback_data="market_status")],
            [InlineKeyboardButton("📅 الأحداث الاقتصادية", callback_data="calendar"),
             InlineKeyboardButton("🔍 تحليل السوق", callback_data="analysis")],
        ]

        # أزرار المستخدم
        user_buttons = [
            [InlineKeyboardButton("👤 حسابي", callback_data="myaccount"),
             InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")],
        ]
        buttons.extend(user_buttons)

        # أزرار الأدمن فقط
        if is_admin:
            admin_buttons = [
                [InlineKeyboardButton("📊 تقرير الأداء", callback_data="performance"),
                 InlineKeyboardButton("👥 المستخدمين", callback_data="users")],
                [InlineKeyboardButton("🤖 حالة Auto-Trade", callback_data="autostatus"),
                 InlineKeyboardButton("⚙️ إعدادات الأدمن", callback_data="admin")],
            ]
            buttons.extend(admin_buttons)

        return InlineKeyboardMarkup(buttons)

    def _get_settings_menu(self) -> InlineKeyboardMarkup:
        """قائمة الإعدادات"""
        buttons = [
            [InlineKeyboardButton("🟢 مخاطرة منخفضة", callback_data="risk_LOW"),
             InlineKeyboardButton("🟡 مخاطرة متوسطة", callback_data="risk_MEDIUM")],
            [InlineKeyboardButton("🔴 مخاطرة عالية", callback_data="risk_HIGH")],
            [InlineKeyboardButton("⏸️ إيقاف التداول", callback_data="pause"),
             InlineKeyboardButton("▶️ تشغيل التداول", callback_data="resume")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(buttons)

    def _get_admin_menu(self) -> InlineKeyboardMarkup:
        """قائمة الأدمن"""
        buttons = [
            [InlineKeyboardButton("📊 إحصائيات النظام", callback_data="admin_stats"),
             InlineKeyboardButton("👥 قائمة المسجلين", callback_data="admin_users")],
            [InlineKeyboardButton("🤖 تقرير Auto-Trade", callback_data="admin_auto"),
             InlineKeyboardButton("💰 رصيد MEXC", callback_data="admin_balance")],
            [InlineKeyboardButton("🔒 إغلاق كل الصفقات", callback_data="admin_closeall"),
             InlineKeyboardButton("📢 رسالة جماعية", callback_data="admin_broadcast")],
            [InlineKeyboardButton("📋 تقرير الأداء", callback_data="admin_performance")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(buttons)

    def _get_registration_menu(self) -> InlineKeyboardMarkup:
        """قائمة التسجيل"""
        buttons = [
            [InlineKeyboardButton("🚀 تسجيل الآن", callback_data="register_start")],
            [InlineKeyboardButton("📋 كيف أبدأ؟", callback_data="howto")],
        ]
        return InlineKeyboardMarkup(buttons)

    def _get_help_menu(self) -> InlineKeyboardMarkup:
        """قائمة المساعدة"""
        buttons = [
            [InlineKeyboardButton("📡 مسح السوق", callback_data="scan"),
             InlineKeyboardButton("📊 حالتي", callback_data="myaccount")],
            [InlineKeyboardButton("👥 الإحالة", callback_data="referral"),
             InlineKeyboardButton("🔔 تنبيه سعر", callback_data="price_alerts")],
            [InlineKeyboardButton("💎 اشتراكي", callback_data="subscription"),
             InlineKeyboardButton("🧠 أداء الاستراتيجيات", callback_data="adaptive_stats")],
            [InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings"),
             InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(buttons)

    # ═══════════════════════════════════════════════════════════
    # Market Scanning
    # ═══════════════════════════════════════════════════════════

    async def scan_market(self, trade_type: str = "ALL") -> List[Dict]:
        """يمسح السوق بالكامل ويولّد الإشارات"""
        all_signals = []

        # فحص الإشارات المعلقة + تحديث التتبع + إرسال رسالة الإغلاق
        try:
            ticker = self.fetcher.fetch_ticker("XAU/USD")
            if ticker and ticker.get("last"):
                # شموع 15 دقيقة (آخر ساعتين) — المتتبع بيفحص القمة/القاع مش اللحظة بس
                candles_15m = None
                try:
                    # fetch_ohlcv بترفض أقل من 20 شمعة — نجيب 40 ونأخذ آخر 8
                    df15 = self.fetcher.fetch_ohlcv("XAU/USD", "15m", 40)
                    if df15 is not None and not df15.empty:
                        df15 = df15.tail(8)  # آخر ساعتين
                        candles_15m = [
                            {"ts": idx.to_pydatetime(), "high": float(h), "low": float(l)}
                            for idx, h, l in zip(df15.index, df15["high"], df15["low"])
                        ]
                except Exception as e:
                    logger.debug(f"15m candles for tracker failed: {e}")
                updated = self.tracker.check_pending_signals(ticker["last"], candles_15m)
                for s in updated:
                    # 🔒 حدث تأمين TP1 — تنبيه فوري لإدارة الصفقة (الصفقة لسه شغالة)
                    if s.get("_event") == "TP1_SECURED":
                        s.pop("_event", None)
                        logger.info(f"📋 Signal {s['id']} → TP1 SECURED (still running)")
                        try:
                            await self._send_tp1_alert(s)
                        except Exception as e:
                            logger.warning(f"Failed to send TP1 alert: {e}")
                        continue
                    logger.info(f"📋 Signal {s['id']} → {s['result']} (exit={s['exit_price']})")
                    # إرسال رسالة إغلاق الصفقة للقناة الخاصة
                    try:
                        await self._send_close_notification(s)
                    except Exception as e:
                        logger.warning(f"Failed to send close notification: {e}")
                self.tracker.cleanup_old_signals(30)

                # 🔔 FEATURE 7: Check Price Alerts
                triggered_alerts = self.price_alerts.check_alerts(ticker["last"])
                for alert in triggered_alerts:
                    try:
                        dir_emoji = "⬆️" if alert["direction"] == "ABOVE" else "⬇️"
                        dir_ar = "فوق" if alert["direction"] == "ABOVE" else "تحت"
                        await self.bot.send_message(
                            chat_id=alert["telegram_id"],
                            text=f"🔔 تنبيه سعر!\n\n"
                                 f"{dir_emoji} الذهب وصل ${ticker['last']:,.2f}\n"
                                 f"التنبيه: {dir_ar} ${alert['target_price']:,.2f}\n\n"
                                 f"🤖 صياد الشمعات | Candle Hunter",
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send price alert: {e}")

                # ⏰ FEATURE 7: Pre-Close Alerts — تنبيه قبل TP/SL بـ 5 دقايق
                try:
                    pending = self.tracker.get_pending_signals()
                    self.pre_close.check_signals(pending, ticker["last"], self.bot)
                    # 🛑 CIRCUIT BREAKER: سجل نتائج الإشارات المغلقة
                    for sig in updated:
                        if sig.get("result") == "WIN":
                            self.circuit_breaker.record_win()
                        elif sig.get("result") == "LOSS":
                            should_pause, reason = self.circuit_breaker.record_loss(sig.get("strategy_name", ""))
                            if should_pause:
                                logger.warning(f"🛑 Circuit Breaker triggered: {reason}")
                                # إرسال تنبيه للقناة الخاصة
                                if self.private_channel:
                                    try:
                                        await self.bot.send_message(
                                            chat_id=self.private_channel,
                                            text="🛑 **Circuit Breaker مفعّل**\n" + str(reason) + "\nالتداول متوقف مؤقتاً"
                                        )
                                    except:
                                        pass
                        # 🧠 ADAPTIVE LEARNING: سجل النتيجة
                        if sig.get("result") in ("WIN", "LOSS"):
                            session_name = getattr(self.market_hours, 'get_current_session_name', lambda: "unknown")()
                            self.adaptive_learning.record_result(
                                sig.get("strategy_name", ""), session_name, sig.get("result", "")
                            )
                except Exception as e:
                    logger.warning(f"Pre-close check failed: {e}")

                # 📊 FEATURE 4: Weekly Report — جمعة 8م
                try:
                    if not self.weekly_reporter:
                        self.weekly_reporter = WeeklyReporter(
                            self.tracker, self.bot, self.private_channel, self.admin_id, self.public_channel
                        )
                    if self.weekly_reporter.should_run_now():
                        await self.weekly_reporter.send_weekly_report()
                except Exception as e:
                    logger.warning(f"Weekly report check failed: {e}")

                # 🤖 FEATURE 16: OCO Order Management — كل دقيقة
                if not hasattr(self, '_last_oco_check') or (datetime.now() - self._last_oco_check).total_seconds() >= 60:
                    try:
                        oco_result = await self.auto_trader.check_oco_all()
                        if oco_result.get("owner", {}).get("position_closed"):
                            exit_price = oco_result["owner"].get("exit_price", 0)
                            logger.info(f"🔔 OCO: Owner position closed at ${exit_price:.2f} — orders cleaned up")
                            try:
                                await self.app.bot.send_message(
                                    chat_id=ADMIN_ID,
                                    text=f"🔔 OCO: تم إغلاق الصفقة على حسابك عند ${exit_price:.2f}\nتم إلغاء كل الأوامر المعلقة."
                                )
                            except:
                                pass
                    except Exception as e:
                        logger.warning(f"OCO check error: {e}")
                    self._last_oco_check = datetime.now()

                # 🔄 FEATURE 13: Auto-Restart health check
                try:
                    if not self.auto_restart.is_healthy():
                        logger.error("🔄 Bot unhealthy — attempting restart")
                        self.auto_restart.record_restart()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Signal tracking check failed: {e}")

        # 🌙 Market Hours — تم نقله لـ process_signals (MarketHoursManager)
        # 🛑 FEATURE 6: Daily Drawdown Limit — إيقاف بعد 3 خسائر أو 5% drawdown
        should_stop, stop_reason = self.tracker.should_pause_trading()
        if should_stop:
            logger.warning(stop_reason)
            return all_signals

        # إيقاف الإشارات وقت الأخبار عالية التأثير (60 دقيقة قبل وبعد)
        try:
            if self.calendar.is_high_impact_soon(60):
                logger.warning("⚠️ High impact news within 60 min - pausing signals")
                # إرسال تنبيه للقناة الخاصة
                try:
                    upcoming = self.calendar.get_upcoming_events(hours_ahead=1)
                    high_events = [e for e in upcoming if e.get("impact") == "High"]
                    if high_events and not getattr(self, '_news_alert_sent', False):
                        event = high_events[0]
                        alert_msg = self.calendar.format_pre_alert(event)
                        if self.private_channel:
                            await self.bot.send_message(
                                chat_id=self.private_channel,
                                text=alert_msg,
                                parse_mode='HTML'
                            )
                            self._news_alert_sent = True
                            logger.info(f"📢 News alert sent: {event.get('title', '')}")
                        # 📢 تنبيه مختصر للقناة العامة (معلومي — بياخد باله من السوق)
                        if self.public_channel and not getattr(self, '_news_alert_public_sent', False):
                            try:
                                _pub_msg = (
                                    "⚠️ <b>خبر اقتصادي قوي بعد قليل</b>\n"
                                    f"🔴 {event.get('title', '')}\n"
                                    "━━━━━━━━━━━━━━━━━━━━\n"
                                    "🔄 التقلب هيتزايد بشدة على الذهب\n"
                                    "💡 تجنب فتح صفقات جديدة لحد ما السوق يهدى\n"
                                    "━━━━━━━━━━━━━━━━━━━━\n"
                                    "🤖 صياد الشمعات | Candle Hunter"
                                )
                                await self.bot.send_message(
                                    chat_id=self.public_channel,
                                    text=_pub_msg,
                                    parse_mode='HTML'
                                )
                                self._news_alert_public_sent = True
                                logger.info(f"📢 Public news alert sent: {event.get('title', '')}")
                            except Exception as pe:
                                logger.warning(f"Public news alert failed: {pe}")
                except Exception as e:
                    logger.warning(f"News alert failed: {e}")
                return all_signals
            else:
                self._news_alert_sent = False
                self._news_alert_public_sent = False
        except Exception as e:
            logger.warning(f"Calendar check failed: {e}")

        pairs = TRADING_PAIRS

        if trade_type == "SCALPING":
            timeframes = TIMEFRAMES["SCALPING"]
            strategy_names = ["scalping", "momentum", "mean_reversion"]
        elif trade_type == "MEDIUM":
            timeframes = TIMEFRAMES["MEDIUM"]
            strategy_names = ["trend_following", "mean_reversion", "momentum", "supertrend", "multi_confluence"]
        elif trade_type == "SWING":
            timeframes = TIMEFRAMES["SWING"]
            strategy_names = ["breakout", "swing", "multi_confluence"]
        else:
            strategy_names = list(self.strategies.keys())
            timeframes = ["5m", "15m", "1h", "4h", "1d"]

        for symbol in pairs:
            for timeframe in timeframes:
                try:
                    logger.info(f"Scanning {symbol} {timeframe}...")
                    df = self.fetcher.fetch_ohlcv(symbol, timeframe, 200)

                    if df.empty or len(df) < 50:
                        logger.warning(f"Insufficient data for {symbol} {timeframe}")
                        continue

                    # 📊 FEATURE 1: Volatility Filter
                    current_price = df['close'].iloc[-1]
                    vol_check = self.volatility_filter.check(df, current_price)
                    if not vol_check["ok"]:
                        logger.info(f"🚫 Volatility filter: {vol_check['reason']}")
                        continue

                    _blacklist = [s.strip() for s in os.getenv("STRATEGY_BLACKLIST", "").split(",") if s.strip()]
                    # 🤖 بلاك ليست تلقائية — من تقرير الأسبوع (أداء < 45% على 30 يوم)
                    try:
                        _ab_path = os.path.join(os.getenv("STATE_DIR", "/app/data"), "auto_blacklist.json")
                        if os.path.exists(_ab_path):
                            _blacklist += [x for x in json.load(open(_ab_path)) if x and x not in _blacklist]
                    except Exception:
                        pass
                    # 🔒 حصرية VIP: على فريم 4 ساعات نشغّل نجوم الباك تيست كمان
                    tf_strategies = list(strategy_names)
                    if trade_type == "MEDIUM" and timeframe == "4h":
                        tf_strategies += ["volume_breakout", "breakout"]
                    for strat_name in tf_strategies:
                        if strat_name not in self.strategies:
                            continue
                        if strat_name in _blacklist:
                            continue
                        try:
                            strat_config = self.strategies[strat_name]
                            func = strat_config["func"]
                            trade_t = strat_config["trade_type"]
                            signal = func(df, symbol, trade_t)

                            if signal and signal.get("signal_type") != "NEUTRAL":
                                signal["strategy_name"] = strat_name
                                signal["timeframe"] = timeframe
                                signal["trade_type"] = trade_t
                                # 🔒 فريم 4 ساعات = محتوى VIP حصري (الباك تيست: أعلى نسب نجاح)
                                if trade_type == "MEDIUM" and timeframe == "4h":
                                    signal["trade_type"] = "SWING"
                                    signal["vip_exclusive"] = True
                                signal["timestamp"] = datetime.now().strftime('%Y-%m-%d %H:%M')

                                # ⏰ FEATURE 5: Active Hours Filter
                                signal = self.active_hours_filter.apply(signal)

                                # 📈 FEATURE 12: Trend-Only Filter — منع الإشارات عكس الترند
                                trend_result = self.trend_filter.check_signal(signal)
                                if not trend_result["ok"]:
                                    logger.info(f"🚫 Trend filter: {trend_result['reason']}")
                                    continue

                                all_signals.append(signal)
                        except Exception as e:
                            logger.error(f"Error scanning {symbol} {tf} {strat_name}: {e}")

                except Exception as e:
                    logger.error(f"Error fetching {symbol} {timeframe}: {e}")

        # Sort by confidence
        all_signals.sort(key=lambda x: x["confidence"], reverse=True)
        return all_signals

    # ═══════════════════════════════════════════════════════════
    # Signal Processing & Distribution
    # ═══════════════════════════════════════════════════════════

    def _confirm_candle_gate(self, signal: Dict) -> Dict:
        """🕯️ شمعة التأكيد: آخر شمعة 15m مقفولة توافق الاتجاه،
        والسعر لسه قريب من الدخول (مجاش الفرصة واتفوتت).
        الشراء لازم شمعة صاعدة، البيع شمعة هابطة."""
        try:
            df = self.fetcher.fetch_ohlcv("15m", limit=6)
            if df is None or len(df) < 3:
                return {"ok": True, "reason": "no_data"}  # مفيش داتا = مش بنمنع

            last_closed = df.iloc[-2]  # الأخيرة لسه بتتشكل
            sig_dir = signal.get("signal_type", "")
            entry = signal.get("entry_price", 0)
            current = float(df["close"].iloc[-1])

            # 1) اتجاه الشمعة المقفولة
            bullish = float(last_closed["close"]) > float(last_closed["open"])
            if sig_dir == "BUY" and not bullish:
                return {"ok": False, "reason": "last 15m candle bearish"}
            if sig_dir == "SELL" and bullish:
                return {"ok": False, "reason": "last 15m candle bullish"}

            # 2) السعر لسه قريب من الدخول (ما يكفيش المفروض) — 0.6x ATR
            try:
                hl = df["high"] - df["low"]
                atr15 = float(hl.iloc[-5:].mean())
            except Exception:
                atr15 = 0
            if entry > 0 and atr15 > 0:
                drift = abs(current - entry)
                if drift > (0.6 * atr15):
                    return {"ok": False, "reason": f"price ran away ({drift:.2f} > 0.6×ATR)"}

            return {"ok": True, "reason": f"candle confirmed, drift={abs(current-entry):.2f}"}
        except Exception as e:
            return {"ok": True, "reason": f"gate_error({e})"}  # fail-open

    def _filter_distance(self, signal: Dict) -> bool:
        """فلتر المسافة: لو الفرق بين الدخول والستوب أقل من 0.3% نتجاهل"""
        entry = signal.get("entry_price", 0)
        sl = signal.get("stop_loss", 0)
        if entry <= 0 or sl <= 0:
            return False
        distance_pct = abs(entry - sl) / entry * 100
        if distance_pct < 0.3:
            logger.info(f"🚫 Filtered: distance too small ({distance_pct:.2f}%) - {signal.get('signal_type', '?')}")
            return False
        return True

    def _is_duplicate_signal(self, signal: Dict) -> bool:
        """منع التكرار: لو في توصية مفتوحة على نفس الاتجاه أو نفس السعر خلال ساعتين"""
        signal_type = signal.get("signal_type", "")
        entry_price = signal.get("entry_price", 0)
        now = datetime.now()

        # 1. تحقق من الإشارات المعلقة (PENDING) في tracker — لو في صفقة لسه مفتوحة نفس الاتجاه
        #    لكن تجاهل الإشارات اللي تعدّت TTL (هتتقفل في الـ scan الجاية)
        for sig in self.tracker.signals:
            if sig.get("status") != "PENDING":
                continue
            if sig.get("signal_type") == signal_type:
                # فحص عمر الإشارة — لو قديمة، مش duplicate
                try:
                    created = datetime.fromisoformat(sig.get("created_at", ""))
                    age_hours = (now - created).total_seconds() / 3600
                    trade_type = sig.get("trade_type", "MEDIUM")
                    ttl = self.tracker.PENDING_TTL_HOURS.get(trade_type, self.tracker.DEFAULT_TTL_HOURS)
                    if age_hours >= ttl:
                        logger.info(f"⏰ Stale PENDING signal ({age_hours:.1f}h > TTL {ttl}h) — not blocking")
                        continue
                except:
                    pass
                logger.info(f"🚫 Duplicate: PENDING {signal_type} signal still open (id={sig['id']})")
                return True

        # 2. تحقق من signal_history — نفس الاتجاه خلال ساعتين
        for prev in self.signal_history:
            if prev.get("signal_type") != signal_type:
                continue
            try:
                prev_time = datetime.strptime(prev.get("timestamp", ""), "%Y-%m-%d %H:%M")
                if (now - prev_time).total_seconds() <= 7200:  # ساعتين بدل ساعة
                    # لو نفس سعر الدخول بالظبط → نفس الإشارة
                    if abs(prev.get("entry_price", 0) - entry_price) < 0.01:
                        logger.info(f"🚫 Duplicate: exact same signal (entry={entry_price})")
                        return True
                    logger.info(f"🚫 Duplicate: same direction ({signal_type}) within 2h")
                    return True
            except:
                continue
        return False

    def _log_rejected_signal(self, signal: Dict, threshold: int, reason: str = None):
        """تسجيل الإشارات المرفوضة داخلياً للتحليل — لا تُنشر ولا تدخل إحصائيات الأداء"""
        try:
            import json as _json
            path = os.path.join(os.getenv("STATE_DIR", os.path.dirname(os.path.abspath(__file__))), "rejected_signals.json")
            entries = []
            try:
                with open(path, "r", encoding="utf-8") as f:
                    entries = _json.load(f)
            except Exception:
                entries = []
            entries.append({
                "id": f"rej_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "symbol": signal.get("symbol", "XAU/USD"),
                "signal_type": signal.get("signal_type", "BUY"),
                "entry_price": signal.get("entry_price", 0),
                "stop_loss": signal.get("stop_loss", 0),
                "take_profit_1": signal.get("take_profit_1", 0),
                "strategy_name": signal.get("strategy_name", "Unknown"),
                "confidence": signal.get("confidence", 0),
                "rejected_reason": reason or f"confidence < MIN_CONFIDENCE ({threshold}%)",
                "created_at": datetime.now().isoformat(),
            })
            # الاحتفاظ بآخر 500 إشارة مرفوضة فقط
            entries = entries[-500:]
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(entries, f, ensure_ascii=False, indent=1)
        except Exception as e:
            logger.warning(f"Failed to log rejected signal: {e}")

    def _confirm_signal(self, signal: Dict) -> bool:
        """تأكيد الإشارة: شروط إضافية قبل الإرسال"""
        confidence = signal.get("confidence", 0)
        # حد أدنى للثقة 55%
        if confidence < 55:
            logger.info(f"🚫 Low confidence: {confidence}% < 55%")
            return False
        # R:R لا يقل عن 1:1.5 — خسارة واحدة ما تاكلش ربحين
        entry = signal.get("entry_price", 0)
        tp2 = signal.get("take_profit_2", 0)
        sl = signal.get("stop_loss", 0)
        min_rr = float(os.getenv("MIN_RR", "1.5"))
        if entry > 0 and sl > 0 and tp2 > 0:
            rr = abs(tp2 - entry) / abs(entry - sl)
            if rr < min_rr:
                logger.info(f"🚫 Low R:R: 1:{rr:.1f} < 1:{min_rr}")
                return False
        return True

    async def process_signals(self, signals: List[Dict]):
        """يوزع الإشارات على القنوات المناسبة — مع فلترة وتأكيد"""

        # 🌙 FEATURE 12: Market Hours — لو السوق مقفول ما تبعتش
        if not self.market_hours.is_market_open():
            mkt = self.market_hours.get_market_status()
            logger.info(f"🌙 Market closed: {mkt['status']} — no signals sent")
            return

        # 🛑 CIRCUIT BREAKER: لو في إيقاف نشط، ما تبعتش إشارات
        cb_paused, cb_reason = self.circuit_breaker.is_paused()
        if cb_paused:
            logger.warning(f"🛑 Circuit Breaker active: {cb_reason} — skipping signals")
            return

        # 📦 MAX CONCURRENT POSITIONS: الحماية الفعلية في الـ trade bot (بيتخطى التنفيذ لو في صفقة)
        # هنا warning فقط — الإشارات مستمرة للقنوات للمتداولين اليدويين
        # (visibility check اختياري — بوت التداول متوقف بأمر المالك)
        if os.getenv("TRADE_BOT_HEALTH_CHECK", "on").lower() not in ("off", "false", "0"):
            try:
                import requests as _req
                _tb_url = os.getenv("TRADE_BOT_URL", "https://bbpro-trade-bot-production.up.railway.app")
                _resp = _req.get(f"{_tb_url}/positions", timeout=10)
                if _resp.status_code == 200:
                    for _u in _resp.json().get("users", []):
                        if _u.get("user") in ("", None) or _u.get("telegram_id") == 8533137153:
                            _n = len(_u.get("positions", []))
                            if _n >= self._max_concurrent_positions:
                                logger.info(f"📦 Owner has {_n} open position(s) — trade bot will skip auto-execution; channel signals continue")
            except Exception as e:
                logger.warning(f"Position visibility check failed: {e}")

        # ⏱️ SIGNAL COOLDOWN: لو في كولداون ما تبعتش
        if not self.cooldown.can_send():
            remaining = self.cooldown.get_remaining()
            logger.info(f"⏱️ Cooldown active: {remaining:.0f} min remaining — skipping signals")
            return

        # 📏 FEATURE 14: Spread Filter — لو السبريد كبير ما تفتحش صفقة
        spread = self.spread_filter.check_spread()
        if not spread.get("ok"):
            logger.warning(f"📏 Spread too wide: {spread['reason']} — skipping")
            return

        # ⚔️ FEATURE 8: Conflict Resolution — اختار الأعلى ثقة لو فيه تعارض
        signals = self.conflict_resolver.resolve(signals)
        if not signals:
            logger.info("📊 No signals after conflict resolution")
            return
        # تحسين الإشارات بالتطابق المحسّن (20 مؤشر على 5 أطر زمنية)
        try:
            enhanced_data = self.enhanced_confluence.analyze(["5m", "15m", "1h", "4h", "1d"])
            if enhanced_data and enhanced_data.get("direction") != "NEUTRAL":
                for signal in signals:
                    self.enhanced_confluence.enhance_signal(signal, enhanced_data)
                logger.info(f"Enhanced Confluence: {enhanced_data['direction']} "
                           f"(agreement={enhanced_data['agreement_score']:.0f}%, "
                           f"buy={enhanced_data['total_buy']}, sell={enhanced_data['total_sell']})")
            else:
                logger.info(f"Enhanced Confluence: NEUTRAL (no boost)")
        except Exception as e:
            logger.warning(f"Enhanced confluence failed, trying legacy: {e}")
            try:
                confluence_data = self.confluence.analyze_confluence()
                if confluence_data and confluence_data.get("confidence_boost", 0) > 0:
                    for signal in signals:
                        self.confluence.enhance_signal_with_confluence(signal, confluence_data)
                    logger.info(f"Legacy Confluence: {confluence_data['confluence_level']} (+{confluence_data['confidence_boost']}%)")
            except Exception as e2:
                logger.warning(f"Legacy confluence also failed: {e2}")

        # 😱 FEATURE 9: Fear & Greed Index — تعديل ثقة الإشارات
        for signal in signals:
            self.fear_greed.should_adjust_confidence(signal)

        # 💵 FEATURE 10: DXY Correlation — تعديل حسب قوة الدولار
        for signal in signals:
            self.dxy_filter.apply(signal)
            # 🏦 FEATURE 20: US10Y Real Yields — العائد الحقيقي بيعصر الذهب
            self.us10y_filter.apply(signal)

        # 🤖 FEATURE 15: AI News Sentiment — Groq AI تحليل الأخبار
        ai_adjustment = 0
        if not hasattr(self, '_last_ai_check') or (datetime.now() - self._last_ai_check).total_seconds() > 3600:
            try:
                news = finnhub_news(limit=10)
                if news:
                    headlines = [n["headline"] for n in news[:8]]
                    summaries = [n.get("summary", "") for n in news[:8]]
                    ai_result = groq_analyze_news(headlines, summaries)
                    self._last_ai_check = datetime.now()
                    self._last_ai_sentiment = ai_result
                    logger.info(f"🤖 AI Sentiment: {ai_result.get('gold_sentiment')} ({ai_result.get('confidence')}%) — {ai_result.get('summary_ar','')[:50]}")
            except Exception as e:
                logger.warning(f"AI sentiment check failed: {e}")
        
        # Apply AI adjustment to each signal
        ai_result = getattr(self, '_last_ai_sentiment', {})
        if ai_result and ai_result.get("gold_sentiment") != "neutral":
            for signal in signals:
                sig_dir = signal.get("signal_type", "").upper()
                is_buy = "BUY" in sig_dir or "LONG" in sig_dir
                ai_adj = get_confidence_adjustment(ai_result, "buy" if is_buy else "sell")
                if ai_adj != 0:
                    old_conf = signal.get("confidence", 50)
                    signal["confidence"] = max(0, min(100, old_conf + ai_adj))
                    logger.info(f"🤖 AI adjusted signal {sig_dir}: {old_conf:.0f} → {signal['confidence']:.0f} ({ai_adj:+.1f})")

        # 🧠 ADAPTIVE LEARNING: تعديل ثقة الإشارات حسب أداء الاستراتيجية التاريخي
        for signal in signals:
            strategy = signal.get("strategy_name", "")
            session = self.market_hours.get_current_session_name() if hasattr(self.market_hours, 'get_current_session_name') else "unknown"
            adjustment = self.adaptive_learning.get_adjustment(strategy, session)
            if adjustment != 0:
                old_conf = signal.get("confidence", 50)
                signal["confidence"] = max(0, min(100, old_conf + adjustment))
                logger.info(f"🧠 Adaptive: {strategy} [{session}] {old_conf:.0f} → {signal['confidence']:.0f} ({adjustment:+.1f}%)")

        # 🎯 FEATURE 2: Multi-Signal Confirmation (Soft Filter)
        # لو استراتيجيتين+ توافقوا → multi_confirmed = True (boost)
        # لو استراتيجية واحدة بس بس confidence >= 75% → نمررها مع علامة single
        # لو استراتيجية واحدة و confidence < 75% → نحجبها
        direction_counts = {}
        for s in signals:
            d = s.get("signal_type", "")
            direction_counts[d] = direction_counts.get(d, 0) + 1

        confirmed_signals = []
        for s in signals:
            d = s.get("signal_type", "")
            count = direction_counts.get(d, 0)
            if count >= 2 and s.get("confidence", 0) >= 75:
                # استراتيجيتين+ متوافقين + ثقة عالية = تأكيد مزدوج
                s["multi_confirmed"] = True
                s["confirming_strategies"] = count
                confirmed_signals.append(s)
            elif count >= 2 and s.get("confidence", 0) < 75:
                logger.info(f"🚫 Filtered: {s.get('strategy_name')} {d} (multi but weak, conf={s.get('confidence', 0):.0f}% < 75%)")
                self._log_rejected_signal(s, 75, reason=f"multi_weak (conf={s.get('confidence', 0):.0f}%)")
            elif s.get("confidence", 0) >= 80:
                # استراتيجية واحدة: لازم ثقة أعلى (80%) للتعويض
                s["multi_confirmed"] = False
                s["confirming_strategies"] = count
                s["single_strategy"] = True
                confirmed_signals.append(s)
                logger.info(f"⚡ Single-strategy pass: {s.get('strategy_name')} {d} (conf={s.get('confidence', 0):.0f}%)")
            else:
                logger.info(f"🚫 Filtered: {s.get('strategy_name')} {d} (only 1 strategy, conf={s.get('confidence', 0):.0f}% < 80%)")
                self._log_rejected_signal(s, 80, reason=f"single_strategy (conf={s.get('confidence', 0):.0f}%)")

        if not confirmed_signals:
            logger.info(f"📊 No signals passed multi-confirmation filter")
            return

        multi_count = sum(1 for s in confirmed_signals if s.get("multi_confirmed"))
        single_count = sum(1 for s in confirmed_signals if s.get("single_strategy"))
        logger.info(f"📊 {len(signals)} signals → {len(confirmed_signals)} passed ({multi_count} multi + {single_count} single)")

        # فلترة الإشارات: مسافة + تكرار + تأكيد
        filtered_signals = []
        for signal in confirmed_signals:
            if not self._filter_distance(signal):
                continue
            if not self._confirm_signal(signal):
                continue
            if self._is_duplicate_signal(signal):
                continue
            filtered_signals.append(signal)

        if not filtered_signals:
            logger.info(f"📊 All {len(confirmed_signals)} confirmed signals filtered out")
            return

        logger.info(f"📊 {len(confirmed_signals)} confirmed → {len(filtered_signals)} after filtering")

        # ⏰ ساعات وحشة: من باك تيست — نمنع النشر في أوقات تاريخياً ضعيفة
        _bad_hours = set()
        try:
            _bh = os.getenv("BAD_HOURS", "")
            _bad_hours = {int(h.strip()) for h in _bh.split(",") if h.strip().isdigit()}
        except Exception:
            pass

        sent_directions = set()
        # 📐 بيانات 1h لمنطقة Premium/Discount (مرة واحدة للمسح كله)
        try:
            _df_pd = self.fetcher.fetch_ohlcv("1h", limit=150)
        except Exception:
            _df_pd = None
        min_conf_gate = int(os.getenv("MIN_CONFIDENCE", "85"))
        # 🔒 DEAD-HOURS GATE: عتبة أعلى في الساعات الضعيفة (آسيوي/ميت) — إشارات كاذبة أقل
        try:
            _sinfo = self.active_hours_filter.get_session_info()
            if _sinfo.get("session") in ("ASIAN", "DEAD"):
                _dead_gate = int(os.getenv("DEAD_HOURS_MIN_CONFIDENCE", "90"))
                min_conf_gate = max(min_conf_gate, _dead_gate)
                logger.info(f"🔒 Dead-hours gate active ({_sinfo.get('session')}): threshold {min_conf_gate}%")
        except Exception as _e:
            logger.debug(f"Session check skipped: {_e}")
        for signal in filtered_signals:
            # منع تكرار نفس الاتجاه داخل نفس المسح
            sig_dir = signal.get("signal_type", "")
            if sig_dir in sent_directions:
                logger.info(f"🚫 Skip duplicate direction in same scan: {sig_dir}")
                continue

            # 📐 PREMIUM/DISCOUNT: شراء من الخصم، بيع من العلاوة — قبل بوابة الثقة
            try:
                if _df_pd is not None and len(_df_pd) >= 30:
                    self.smc.apply_premium_discount(signal, _df_pd)
            except Exception as _pe:
                logger.debug(f"Premium/Discount skipped: {_pe}")

            # ⏰ بوابة الساعات الوحشة — التاريخ بيقول الساعة دي ضعيفة
            if _bad_hours and datetime.now().hour in _bad_hours:
                logger.info(f"⏰ Bad hour {datetime.now().hour}:00 — {signal.get('strategy_name', '?')} muted")
                self._log_rejected_signal(signal, min_conf_gate, reason=f"bad_hour_{datetime.now().hour}")
                continue

            # 🛡️ QUALITY FILTER: عتبة ثقة النشر — الإشارات الأضعف تُسجل داخلياً فقط
            _conf_int = round(signal.get("confidence", 0))
            if _conf_int < min_conf_gate:
                logger.info(f"🛡️ Quality gate: {signal.get('strategy_name')} {sig_dir} conf={signal.get('confidence', 0):.0f}% < {min_conf_gate}% — not published (logged for analysis)")
                self._log_rejected_signal(signal, min_conf_gate)
                continue

            # 🧠 SMC/PRICE-ACTION GATE: تأكيد الهيكل قبل النشر (BOS/CHOCH/OB/FVG/Sweep/قوة الشموع)
            if os.getenv("SMC_GATE", "1") == "1":
                try:
                    df_smc = self.fetcher.fetch_ohlcv("15m", limit=120)
                    smc_min = int(os.getenv("SMC_MIN_CONFLUENCE", "3"))
                    # قاعدة الثقة العالية: إشارة ≥90% تحتاج SMC 2/6 فقط (بدل 3/6)
                    if _conf_int >= int(os.getenv("SMC_HIGH_CONF_RELAX", "90")):
                        smc_min = min(smc_min, 2)
                    gate = self.smc.directional_gate(df_smc, sig_dir, smc_min)
                    if not gate["passed"]:
                        logger.info(f"🧠 SMC gate: {signal.get('strategy_name')} {sig_dir} confluence {gate['score']}/{gate.get('max', 6)} < {smc_min} — not published")
                        self._log_rejected_signal(
                            signal, min_conf_gate,
                            reason=f"SMC confluence {gate['score']}/{gate.get('max', 6)} < {smc_min} ({gate.get('reason', '')})"
                        )
                        continue
                    logger.info(f"🧠 SMC gate passed: {sig_dir} confluence {gate['score']}/{gate.get('max', 6)} (min={smc_min})")
                except Exception as e:
                    logger.warning(f"SMC gate check failed (fail-open): {e}")

            # 🕯️ CONFIRMATION CANDLE: آخر شمعة 15m مقفولة لازم توافق الاتجاه
            if os.getenv("CONFIRM_CANDLE", "1") == "1":
                try:
                    _conf = self._confirm_candle_gate(signal)
                    if not _conf["ok"]:
                        logger.info(f"🕯️ Confirm-candle gate: {sig_dir} {_conf['reason']} — not published")
                        self._log_rejected_signal(signal, min_conf_gate, reason=_conf["reason"])
                        continue
                except Exception as _ce:
                    logger.debug(f"Confirm candle skipped: {_ce}")

            # 📐 DYNAMIC SL/TP (ATR-based): تعديل SL/TP حسب التقلب الحالي
            try:
                df_15m = self.fetcher.fetch_ohlcv("15m", limit=20)
                if df_15m is not None and len(df_15m) >= 14:
                    high_low = df_15m["high"] - df_15m["low"]
                    high_close = (df_15m["high"] - df_15m["close"].shift()).abs()
                    low_close = (df_15m["low"] - df_15m["close"].shift()).abs()
                    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                    atr = float(tr.iloc[-14:].mean())
                    atr_pct = (atr / signal["entry_price"]) * 100

                    entry = signal["entry_price"]
                    is_buy = signal["signal_type"] == "BUY"
                    # SL = 1.5x ATR, TP1 = 1x ATR, TP2 = 2x ATR
                    if atr_pct > 0.1:
                        sl_mult = 1.5
                        tp1_mult = 1.0
                        tp2_mult = 2.0
                        if is_buy:
                            signal["stop_loss"] = round(entry - (atr * sl_mult), 2)
                            signal["take_profit_1"] = round(entry + (atr * tp1_mult), 2)
                            signal["take_profit_2"] = round(entry + (atr * tp2_mult), 2)
                        else:
                            signal["stop_loss"] = round(entry + (atr * sl_mult), 2)
                            signal["take_profit_1"] = round(entry - (atr * tp1_mult), 2)
                            signal["take_profit_2"] = round(entry - (atr * tp2_mult), 2)
                        logger.info(f"📐 ATR SL/TP: atr={atr:.2f} ({atr_pct:.2f}%) SL={signal['stop_loss']} TP1={signal['take_profit_1']} TP2={signal['take_profit_2']}")

                        # 💧 LIQUIDITY TARGETS: TP1 عند أقرب بركة سيولة تعطي R:R أحسن
                        try:
                            _df_liq = self.fetcher.fetch_ohlcv("1h", limit=250)
                            if _df_liq is not None:
                                _lt = self.smc.liquidity_targets(
                                    _df_liq, entry, signal["stop_loss"], sig_dir, atr
                                )
                                if _lt:
                                    # ما نحطش TP أبعد من TP2 الأصلي (السيولة ممكن تبقى بعيدة)
                                    if _lt["tp1"] and (
                                        (is_buy and _lt["tp1"] < signal["take_profit_2"]) or
                                        ((not is_buy) and _lt["tp1"] > signal["take_profit_2"])
                                    ):
                                        old_tp1 = signal["take_profit_1"]
                                        signal["take_profit_1"] = _lt["tp1"]
                                        signal["liquidity_pool"] = _lt["pool"]
                                        logger.info(f"💧 Liquidity TP1: {old_tp1} → {_lt['tp1']} (pool={_lt['pool']}, RR={_lt['rr']})")
                        except Exception as _le:
                            logger.debug(f"Liquidity targets skipped: {_le}")
            except Exception as e:
                logger.warning(f"ATR adjustment failed: {e}")

            capital_plans = self.risk_manager.get_all_capital_plans(signal)
            channels = self.channel_manager.get_channel_for_signal(signal)

            for channel in channels:
                if not self.channel_manager.can_send_more(channel):
                    logger.info(f"Channel {channel} daily limit reached")
                    continue

                try:
                    await self.send_signal_to_channel(signal, capital_plans, channel)
                    self.channel_manager.record_signal(channel, signal)
                    self.signal_history.append({**signal, "channel": channel})
                    sent_directions.add(sig_dir)
                    # ⏱️ Record cooldown
                    self.cooldown.record_signal()
                    # 🧠 Record to adaptive learning
                    session_name = self.market_hours.get_current_session_name() if hasattr(self.market_hours, 'get_current_session_name') else "unknown"
                    self.adaptive_learning.record_signal(
                        signal.get("strategy_name", ""), session_name,
                        signal.get("signal_type", ""), signal.get("confidence", 50)
                    )
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Error sending to {channel}: {e}")

        # 💰 FEATURE 3: Balance Check — owner فقط، لا يحجب التنفيذ عن المستخدمين
        if filtered_signals:
            bal = self.balance_checker.check_owner_balance()
            if not bal.get("ok"):
                logger.warning(f"💰 Owner balance low: {bal['reason']} — signal still forwarded for users")
            else:
                # 📐 FEATURE 6: Smart Position Sizing — تعديل حجم الصفقة (owner only)
                for sig in filtered_signals:
                    sizing = self.position_sizer.calculate_size(
                        bal["balance"],
                        sig.get("confidence", 50),
                        sig.get("entry_price", 0),
                        sig.get("stop_loss", 0),
                    )
                    if sizing.get("ok"):
                        sig["smart_amount"] = sizing["amount"]
                        sig["smart_risk_pct"] = sizing["risk_pct"]
                        logger.info(f"📐 Smart sizing: {sizing['amount']} (risk={sizing['risk_pct']}%)")

            # 📡 إرسال الإشارة لبوت التداول التلقائي (دائماً — trade bot يفحص رصيد كل مستخدم لوحده)
            try:
                forward_result = await self.forwarder.forward_signal(filtered_signals[0])
                if forward_result.get("success"):
                    logger.info(f"📡 Signal forwarded to trade bot: {filtered_signals[0].get('signal_type', '')}")
                else:
                    logger.warning(f"⚠️ Forward failed: {forward_result.get('error', 'unknown')}")
            except Exception as e:
                logger.error(f"Signal forward error: {e}")

    def _format_user_notification(self, signal: Dict, result: Dict) -> str:
        """إشعار المستخدم بتنفيذ صفقة على حسابه"""
        side = "شراء 🟢" if result.get("side") == "buy" else "بيع 🔴"
        msg = "🤖 تم تنفيذ صفقة تلقائياً على حسابك\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📊 {signal.get('symbol', 'XAU/USD')} {side}\n"
        msg += f"💰 السعر: {result.get('fill_price', 0):.2f}\n"
        msg += f"📦 الحجم: {result.get('amount', 0)}\n"
        msg += f"📈 الرافعة: {result.get('leverage', 10)}x\n"
        msg += f"🛑 وقف الخسارة: {signal.get('stop_loss', 0):.2f}\n"
        msg += f"🎯 هدف: {signal.get('take_profit_1', 0):.2f}\n"
        msg += f"📋 الاستراتيجية: {signal.get('strategy_name', '')}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        msg += "🤖 صياد الشمعات | Candle Hunter"
        return msg

    async def send_signal_to_channel(self, signal: Dict, capital_plans: List[Dict],
                                       channel_type: str):
        """يرسل إشارة لقناة محددة — مع صورة تحليل لو الثقة عالية"""
        channel_id = self.private_channel if channel_type == "PRIVATE" else self.public_channel

        if not channel_id:
            logger.warning(f"No channel ID for {channel_type}")
            return

        message = format_signal_message(signal, capital_plans, channel_type)

        try:
            # لو الثقة ≥ 75% — ولّد صورة المخطط
            chart_path = None
            if signal.get("confidence", 0) >= 75:
                try:
                    timeframe = signal.get("timeframe", "1h")
                    df = self.fetcher.fetch_ohlcv("XAU/USD", timeframe, 100)
                    if df is not None and not df.empty and len(df) >= 20:
                        # mplfinance requires capitalized column names
                        df_chart = df.rename(columns={
                            'open': 'Open', 'high': 'High',
                            'low': 'Low', 'close': 'Close',
                            'volume': 'Volume'
                        })
                        chart_path = generate_signal_chart(df_chart, signal, "signal_chart.png")
                        logger.info(f"📊 Chart generated for high-confidence signal ({signal['confidence']}%)")
                except Exception as e:
                    logger.warning(f"Chart generation failed: {e}")

            # إرسال الصورة مع الرسالة لو موجودة
            if chart_path and os.path.exists(chart_path):
                with open(chart_path, 'rb') as photo:
                    await self.bot.send_photo(
                        chat_id=channel_id,
                        photo=photo,
                        caption=message,
                        parse_mode='HTML'
                    )
                logger.info(f"Signal + chart sent to {channel_type} channel: {signal.get('symbol', 'XAU/USD')}")
            else:
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=message,
                    parse_mode='HTML'
                )
                logger.info(f"Signal sent to {channel_type} channel: {signal.get('symbol', 'XAU/USD')}")

            # تتبع الإشارة في القناة الخاصة فقط
            if channel_type == "PRIVATE":
                try:
                    self.tracker.track_signal(signal)
                    logger.info(f"📋 Tracking signal: {signal.get('signal_type', '?')} {signal.get('symbol', '?')}")
                except Exception as e:
                    logger.warning(f"Failed to track signal: {e}")

        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def _send_tp1_alert(self, signal: Dict):
        """🔒 تنبيه فوري عند ضرب TP1 — إدارة مخاطر حسب اتفاق المالك"""
        direction = "شراء" if signal.get("signal_type") == "BUY" else "بيع"
        entry = signal.get("entry_price", 0)
        tp1 = signal.get("tp1_price", signal.get("take_profit_1", 0))
        tp2 = signal.get("take_profit_2", 0)
        tp3 = signal.get("take_profit_3", 0)

        msg = "🔒 الهدف الأول ضمنت! | XAU/USD\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📊 {direction} @ {entry:,.2f} → TP1 ${tp1:,.2f} ✅\n\n"
        msg += "🛡️ خطوات إدارة الصفقة:\n"
        msg += "• أغلق نص الحجم الآن — الربع الأول في الجيب\n"
        msg += f"• حرّك الستوب لنقطة الدخول ${entry:,.2f} — الصفقة بقت بلا خسارة\n"
        targets = f"TP2 ${tp2:,.2f}" if tp2 else ""
        if tp3:
            targets += f" | TP3 ${tp3:,.2f}"
        if targets:
            msg += f"• سيب النص التاني يجري لـ {targets}\n"
        msg += "\n🤖 صياد الشمعات | Candle Hunter"

        if self.private_channel:
            try:
                await self.bot.send_message(chat_id=self.private_channel, text=msg)
            except Exception as e:
                logger.warning(f"TP1 alert send failed: {e}")

    async def _send_close_notification(self, signal: Dict):
        """رسالة إغلاق الصفقة لما TP أو SL يوصل"""
        is_win = signal.get("result") == "WIN"
        is_protected = signal.get("result") == "PROTECTED"
        emoji = "✅" if is_win else ("🔒" if is_protected else "❌")
        result_text = ("ضرب الهدف 🎯" if is_win
                       else ("صفقة مؤمنة — نص على TP1 والباقي على الدخول" if is_protected
                             else "ضرب الستوب 🛑"))
        direction = "شراء" if signal.get("signal_type") == "BUY" else "بيع"

        entry = signal.get("entry_price", 0)
        exit_price = signal.get("exit_price", 0)
        pnl_pct = ((exit_price - entry) / entry * 100)
        if signal.get("signal_type") == "SELL":
            pnl_pct = ((entry - exit_price) / entry * 100)
        sign = "+" if pnl_pct > 0 else ""

        msg = f"{emoji} إغلاق صفقة | XAU/USD\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📊 {direction} → {result_text}\n"
        if is_protected:
            msg += f"💵 TP1 المحقق: ${signal.get('tp1_price', 0):,.2f} (نص الحجم)\n"
        msg += f"💵 الدخول: {entry:,.2f}\n"
        msg += f"🏁 الخروج: {exit_price:,.2f}\n"
        msg += f"📈 النتيجة: {sign}{pnl_pct:.2f}%\n\n"
        if is_partial_tp1:
            # 🛡️ إدارة المخاطر عند TP1 — الاتفاق مع المالك
            tp2 = signal.get("take_profit_2", 0)
            tp3 = signal.get("take_profit_3", 0)
            msg += "🛡️ خطوات إدارة الصفقة:\n"
            msg += "• أغلق نص الحجم الآن (أول هدف ضمنت)\n"
            msg += f"• حرّك الستوب لنقطة الدخول ${entry:,.2f} — الصفقة بقت بلا خسارة\n"
            targets = f"TP2 ${tp2:,.2f}" if tp2 else ""
            if tp3:
                targets += f" | TP3 ${tp3:,.2f}"
            if targets:
                msg += f"• سيب النص التاني يجري لـ {targets}\n"
            msg += "\n"
        msg += f"📅 {signal.get('exit_time', datetime.now().strftime('%Y-%m-%d %H:%M'))}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "🤖 صياد الشمعات | Candle Hunter"

        # إرسال للقناة الخاصة
        if self.private_channel:
            try:
                await self.bot.send_message(
                    chat_id=self.private_channel,
                    text=msg,
                    parse_mode='HTML'
                )
                logger.info(f"📢 Close notification sent: {signal['id']} → {signal['result']}")
            except Exception as e:
                logger.error(f"Error sending close notification: {e}")

    # ═══════════════════════════════════════════════════════════
    # Telegram Commands
    # ═══════════════════════════════════════════════════════════


    def _ensure_message(self, update):
        """فحص أن update.message ليس None"""
        if update.message is None and update.effective_message is None:
            return None
        return update.message or update.effective_message

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """أمر /start — يرحب بالمستخدم ويظهر القائمة"""
        user = update.effective_user
        user_id = user.id
        is_admin = self._is_admin(user_id)

        # لو أدمن — اعرض القائمة الكاملة
        if is_admin:
            welcome = (
                "🤖 **صياد الشمعات | Candle Hunter — وضع الأدمن**\n\n"
                "📊 13 استراتيجية | 22+ مؤشر | XAU/USD فقط\n"
                "🤖 تنفيذ تلقائي على MEXC\n"
                "👥 نظام إحالات + أعضاء\n\n"
                "اختر من القائمة:"
            )
            await update.message.reply_text(
                welcome,
                reply_markup=self._get_main_menu(is_admin=True)
            )
            return

        # لو مستخدم عادي ومسجل — اعرض القائمة
        if self.user_manager.is_registered(user_id):
            user_data = self.user_manager.get_user(user_id)
            if user_data.get("status") == "BANNED":
                await update.message.reply_text("❌ تم حظر حسابك. تواصل مع الإدارة.")
                return

            welcome = (
                f"أهلاً {user.first_name}! 👋\n\n"
                "🤖 صياد الشمعات | Candle Hunter\n"
                "📊 توصيات ذهب (XAU/USD) + تنفيذ تلقائي\n\n"
                "اختر من القائمة:"
            )
            await update.message.reply_text(
                welcome,
                reply_markup=self._get_main_menu(is_admin=False)
            )
            return

        # لو مستخدم جديد غير مسجل — اعرض شاشة التسجيل
        ref_link = self.user_manager.get_referral_link(self.mexc_referral_code)
        welcome = (
            "🤖 أهلاً بك في صياد الشمعات | Candle Hunter!\n\n"
            "📊 بوت توصيات الذهب (XAU/USD)\n"
            "🤖 تنفيذ تلقائي على MEXC\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📋 **للتسجيل تحتاج:**\n\n"
            "1️⃣ التسجيل في MEXC برابط الإحالة\n"
            f"   👉 {ref_link}\n\n"
            "2️⃣ إنشاء API Key على MEXC\n"
            "   (صلاحيات: قراءة + تداول، بدون سحب)\n\n"
            "3️⃣ الاشتراك في القناة العامة\n\n"
            "4️⃣ إرسال MEXC UID + API Key للبوت\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "اضغط زر التسجيل للبدء 🚀"
        )
        await update.message.reply_text(
            welcome,
            reply_markup=self._get_registration_menu()
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """أمر /help"""
        user_id = update.effective_user.id
        is_admin = self._is_admin(user_id)

        help_text = (
            "📋 **مساعدة صياد الشمعات | Candle Hunter**\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📊 **التوصيات:**\n"
            "• مسح السوق الفوري\n"
            "• تحليل شامل للسوق\n"
            "• ملخص إشارات اليوم\n\n"
            "🤖 **التداول التلقائي:**\n"
            "• تنفيذ تلقائي على MEXC\n"
            "• SL و TP تلقائي\n"
            "• إدارة مخاطرة ذكية\n\n"
            "⚙️ **الإعدادات:**\n"
            "• تحديد مستوى المخاطرة\n"
            "• إيقاف/تشغيل التداول\n"
            "• معلومات حسابك\n\n"
            "📅 **الأدوات:**\n"
            "• التقويم الاقتصادي\n"
            "• تحليل التطابق متعدد الأطر\n"
            "• تتبع أداء الإشارات\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "💡 **ملاحظات مهمة:**\n"
            "• التوصيات للتحليل فقط، القرار قرارك\n"
            "• التداول في الذهب ينطوي على مخاطر\n"
            "• لا تستثمر أكثر مما يمكنك تحمل خسارته\n"
            "• تحقق دائماً من صفقاتك على MEXC\n"
        )

        if is_admin:
            help_text += "\n🔧 **أوامر الأدمن:**\n• /users — المسجلين\n• /stats — إحصائيات\n• /autostatus — حالة Auto-Trade\n"

        await update.message.reply_text(
            help_text,
            reply_markup=self._get_help_menu()
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """أمر /status"""
        user_id = update.effective_user.id
        is_admin = self._is_admin(user_id)

        # حالة البوت
        status = (
            "📊 **حالة صياد الشمعات | Candle Hunter**\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📊 الرمز: XAU/USD (الذهب)\n"
            f"📈 الاستراتيجيات: 13\n"
            f"📏 المؤشرات: 22+\n"
            f"📡 القناة العامة: {'✅' if self.public_channel else '❌'}\n"
            f"📡 القناة الخاصة: {'✅' if self.private_channel else '❌'}\n"
            f"🤖 Auto-Trade: {'✅ مفعل' if self.auto_trader.owner_client else '❌ غير مفعل'}\n"
            f"👥 المسجلين: {self.user_manager.get_stats()['total']}\n"
            f"📋 إشارات اليوم: {len(self.signal_history)}\n"
            f"🟢 الحالة: يعمل\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

        # لو أدمن، أضف معلومات إضافية
        if is_admin:
            stats = self.user_manager.get_stats()
            status += f"\n🔧 **إحصائيات الأدمن:**\n"
            status += f"🟢 نشطين: {stats['active']} | ⏸️ متوقفين: {stats['paused']}\n"
            status += f"📋 إجمالي الصفقات: {stats['total_trades']}\n"
            status += f"💰 إجمالي PnL: ${stats['total_pnl']:.2f}\n"

        await update.message.reply_text(status)

    async def cmd_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """أمر /scan — مسح فوري"""
        user_id = update.effective_user.id
        is_admin = self._is_admin(user_id)

        # لو مش أدمن ولا مسجل
        if not is_admin and not self.user_manager.is_registered(user_id):
            await update.message.reply_text("❌ لازم تسجل أول مرة. اكتب /start")
            return

        await update.message.reply_text("🔄 جاري مسح السوق... قد يستغرق دقيقة")
        signals = await self.scan_market("ALL")
        if signals:
            await self.process_signals(signals)
            await update.message.reply_text(f"✅ تم العثور على {len(signals)} إشارة!")
        else:
            await update.message.reply_text("⚠️ لا توجد إشارات في الوقت الحالي")

    async def cmd_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """📊 تقرير شامل للذهب من كل الـ APIs"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id) and not self.user_manager.is_registered(user_id):
            await update.message.reply_text("❌ لازم تسجل أول مرة. اكتب /start")
            return
        msg = await update.message.reply_text("📊 جاري جمع البيانات من كل المصادر...")
        try:
            ctx = get_enhanced_market_context()
            report = format_gold_report(ctx)
            news = ctx.get("news", [])
            if news:
                report += f"\n📰 آخر الأخبار ({len(news)} خبر):\n"
                for n in news[:5]:
                    report += f"  • {n['headline'][:70]}\n"
            await msg.edit_text(report)
        except Exception as e:
            await msg.edit_text(f"❌ خطأ: {e}")

    async def cmd_daily_brief(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """🤖 ملخص يومي ذكي بالعربي"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            return
        msg = await update.message.reply_text("🤖 جاري تحليل الأخبار و توليد الملخص اليومي...")
        try:
            news = finnhub_news(limit=15)
            if not news:
                await msg.edit_text("❌ لا توجد أخبار متاحة حالياً")
                return
            brief = groq_daily_gold_brief(news)
            await msg.edit_text(f"📋 الملخص اليومي للذهب\n\n{brief}")
        except Exception as e:
            await msg.edit_text(f"❌ خطأ: {e}")

    async def cmd_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """أمر /summary"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id) and not self.user_manager.is_registered(user_id):
            await update.message.reply_text("❌ لازم تسجل أول مرة. اكتب /start")
            return
        if not self.signal_history:
            await update.message.reply_text("⚠️ لا توجد إشارات اليوم بعد")
            return
        message = format_summary_message(self.signal_history)
        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """أمر /performance — تقرير 7 أيام"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id) and not self.user_manager.is_registered(user_id):
            await update.message.reply_text("❌ لازم تسجل أول مرة. اكتب /start")
            return
        report = self.tracker.get_performance_report(days=7)
        await update.message.reply_text(report)

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """أمر /stats — لوحة إحصائيات شاملة (30 يوم)"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id) and not self.user_manager.is_registered(user_id):
            await update.message.reply_text("❌ لازم تسجل أول مرة. اكتب /start")
            return

        # لو المستخدم كتب رقم بعد /stats
        days = 30
        if context.args and context.args[0].isdigit():
            days = int(context.args[0])
            days = min(days, 365)

        report = self.tracker.format_detailed_report(days=days)
        await update.message.reply_text(report)

    async def cmd_confluence_enhanced(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """أمر /scan_pro — تحليل تطابق محسّن (20 مؤشر)"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id) and not self.user_manager.is_registered(user_id):
            await update.message.reply_text("❌ لازم تسجل أول مرة. اكتب /start")
            return
        await update.message.reply_text("🔬 جاري تحليل 20 مؤشر على 5 أطر زمنية...")
        try:
            data = self.enhanced_confluence.analyze(["5m", "15m", "1h", "4h", "1d"])
            msg = self.enhanced_confluence.format_report(data)
            await update.message.reply_text(msg)
        except Exception as e:
            logger.error(f"Enhanced confluence command error: {e}")
            await update.message.reply_text("❌ حدث خطأ في التحليل")

    async def cmd_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """أمر /calendar"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id) and not self.user_manager.is_registered(user_id):
            await update.message.reply_text("❌ لازم تسجل أول مرة. اكتب /start")
            return
        events = self.calendar.get_upcoming_events(hours_ahead=48)
        msg = self.calendar.format_events_message(events)
        await update.message.reply_text(msg)

    async def cmd_confluence(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        """أمر /confluence"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id) and not self.user_manager.is_registered(user_id):
            await update.message.reply_text("❌ لازم تسجل أول مرة. اكتب /start")
            return
        await update.message.reply_text("📊 جاري تحليل التطابق...")
        data = self.confluence.analyze_confluence()
        msg = self.confluence.format_confluence_report(data)
        await update.message.reply_text(msg)

    # ═══════════════════════════════════════════════════════════
    # Registration Flow (للمستخدمين الجدد)
    # ═══════════════════════════════════════════════════════════

    async def handle_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة رسائل التسجيل (MEXC UID, API Key, API Secret)"""
        if update.message is None:
            return
        user_id = update.effective_user.id
        text = update.message.text.strip()

        if user_id not in self._registration_state:
            return

        state = self._registration_state[user_id]
        step = state.get("step")

        if step == self.REG_STEP_UID:
            # استلام MEXC UID
            if not text.isdigit():
                await update.message.reply_text(
                    "❌ MEXC UID يجب أن يكون رقم\n"
                    "أدخل رقم الـ UID الصحيح:"
                )
                return

            state["uid"] = text
            state["step"] = self.REG_STEP_API_KEY
            await update.message.reply_text(
                "✅ تم استلام MEXC UID\n\n"
                "🔑 الآن أرسل **API Key** من MEXC\n"
                "📍 تجده في: MEXC → Profile → API Management\n\n"
                "⚠️ تأكد أن API Key لها صلاحيات:\n"
                "✅ Read (قراءة)\n"
                "✅ Spot Trading أو Futures Trading\n"
                "❌ Withdrawals (يجب أن تكون معطلة)"
            )

        elif step == self.REG_STEP_API_KEY:
            # استلام API Key
            if len(text) < 10:
                await update.message.reply_text("❌ API Key غير صحيح. أعد الإرسال:")
                return

            state["api_key"] = text
            state["step"] = self.REG_STEP_API_SECRET
            await update.message.reply_text(
                "✅ تم استلام API Key\n\n"
                "🔐 الآن أرسل **API Secret Key**\n"
                "⚠️ هذا آخر خطوة — سيتم تشفير مفتاحك فوراً"
            )

        elif step == self.REG_STEP_API_SECRET:
            # استلام API Secret
            if len(text) < 10:
                await update.message.reply_text("❌ API Secret غير صحيح. أعد الإرسال:")
                return

            # فحص صلاحية API
            await update.message.reply_text("⏳ جاري التحقق من API Keys...")

            validation = MexcClient.validate_api(state["api_key"], text)

            if not validation.get("valid"):
                await update.message.reply_text(
                    f"❌ فشل التحقق من API Keys\n"
                    f"السبب: {validation.get('error', 'غير معروف')}\n\n"
                    "تأكد من:\n"
                    "• المفاتيح صحيحة\n"
                    "• ليست معطلة\n"
                    "• لديها صلاحية تداول\n\n"
                    "اكتب /start للبدء من جديد"
                )
                del self._registration_state[user_id]
                return

            # فحص اشتراك القناة
            is_subscribed = await self._check_channel_subscription(user_id)
            if not is_subscribed:
                channel_link = f"t.me/c/{abs(self.public_channel) - 1000000000000}" if self.public_channel else ""
                await update.message.reply_text(
                    "❌ يجب الاشتراك في القناة العامة أولاً!\n\n"
                    f"📎 اشترك هنا: {channel_link}\n\n"
                    "ثم اكتب /start مرة أخرى"
                )
                del self._registration_state[user_id]
                return

            # ✅ تسجيل المستخدم
            username = update.effective_user.username or f"user_{user_id}"
            self.user_manager.register_user(
                telegram_id=user_id,
                username=username,
                mexc_uid=state["uid"],
                api_key=state["api_key"],
                api_secret=text,
            )

            del self._registration_state[user_id]

            success_msg = (
                "🎉 **تم التسجيل بنجاح!**\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ MEXC UID: {state['uid']}\n"
                f"💰 رصيد MEXC: ${validation.get('usdt_balance', 0):.2f}\n"
                f"🔐 API Keys: مشفرة ✅\n"
                f"🤖 التداول التلقائي: مفعل ✅\n"
                f"⚖️ المخاطرة: متوسطة (2%)\n"
                f"📈 الرافعة: 10x\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "📊 **ماذا سيحدث الآن؟**\n"
                "• البوت سيراقب السوق تلقائياً\n"
                "• عند ظهور إشارة ذهب قوية → ستنفذ على حسابك\n"
                "• ستستلم إشعار بكل صفقة\n"
                "• يمكنك التحكم في الإعدادات من القائمة\n\n"
                "⚠️ **ملاحظات مهمة:**\n"
                "• لا تستثمر أكثر مما يمكنك تحمل خسارته\n"
                "• راجع صفقاتك على MEXC بانتظام\n"
                "• يمكنك إيقاف التداول في أي وقت\n"
            )
            await update.message.reply_text(
                success_msg,
                reply_markup=self._get_main_menu(is_admin=self._is_admin(user_id))
            )

    # ═══════════════════════════════════════════════════════════
    # Callback Query Handler (الأزرار)
    # ═══════════════════════════════════════════════════════════

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أزرار Inline Keyboard"""
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        user_id = query.from_user.id
        data = query.data
        is_admin = self._is_admin(user_id)

        # ===== القائمة الرئيسية =====
        if data == "main_menu":
            if is_admin:
                await query.edit_message_text(
                    "🤖 صياد الشمعات | Candle Hunter — القائمة الرئيسية",
                    reply_markup=self._get_main_menu(is_admin=True)
                )
            elif self.user_manager.is_registered(user_id):
                await query.edit_message_text(
                    "🤖 صياد الشمعات | Candle Hunter — القائمة الرئيسية",
                    reply_markup=self._get_main_menu(is_admin=False)
                )
            else:
                await query.edit_message_text(
                    "🤖 أهلاً بك! للتسجيل اضغط الزر أدناه",
                    reply_markup=self._get_registration_menu()
                )

        # ===== التسجيل =====
        elif data == "register_start":
            if self.user_manager.is_registered(user_id):
                await query.edit_message_text("✅ أنت مسجل بالفعل!")
                return

            self._registration_state[user_id] = {"step": self.REG_STEP_UID}
            ref_link = self.user_manager.get_referral_link(self.mexc_referral_code)
            await query.edit_message_text(
                "🚀 **بدء التسجيل**\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "1️⃣ سجل في MEXC أولاً (لو لم تسجل):\n"
                f"   {ref_link}\n\n"
                "2️⃣ أنشئ API Key على MEXC:\n"
                "   MEXC → Profile → API Management\n\n"
                "3️⃣ اشترك في القناة العامة\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📝 **الخطوة 1:** أرسل MEXC UID الخاص بك\n"
                "📍 تجده في: MEXC → Profile → رقم الـ UID"
            )

        elif data == "howto":
            ref_link = self.user_manager.get_referral_link(self.mexc_referral_code)
            await query.edit_message_text(
                "📋 **كيف أبدأ؟ — دليل خطوة بخطوة**\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "1️⃣ **سجل في MEXC**\n"
                f"   👉 {ref_link}\n"
                "   (تحصل على بونص تصل لـ 12K USDT)\n\n"
                "2️⃣ **أكمل KYC** (تأكيد الهوية)\n"
                "   MEXC → Profile → KYC Verification\n\n"
                "3️⃣ **أودع USDT** في حسابك\n"
                "   (تحويل من أي محفظة أو شراء مباشر)\n\n"
                "4️⃣ **أنشئ API Key**\n"
                "   MEXC → Profile → API Management → Create\n"
                "   ✅ Read + Futures Trading\n"
                "   ❌ Withdrawals (معطلة!)\n\n"
                "5️⃣ **اشترك في القناة العامة**\n\n"
                "6️⃣ **سجل في البوت**\n"
                "   اضغط: 🚀 تسجيل الآن\n"
                "   أدخل: MEXC UID → API Key → API Secret\n\n"
                "7️⃣ **استمتع بالتداول التلقائي!** 🎉\n"
                "   البوت سيراقب السوق وينفذ الصفقات على حسابك\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ التداول ينطوي على مخاطر — لا تستثمر أكثر مما تتحمل",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🚀 تسجيل الآن", callback_data="register_start"),
                    InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"),
                ]])
            )

        # ===== أوامر السوق =====
        elif data == "scan":
            await query.edit_message_text("🔄 جاري مسح السوق...")
            signals = await self.scan_market("ALL")
            if signals:
                await self.process_signals(signals)
                await query.edit_message_text(
                    f"✅ تم العثور على {len(signals)} إشارة!",
                    reply_markup=self._get_main_menu(is_admin)
                )
            else:
                await query.edit_message_text(
                    "⚠️ لا توجد إشارات في الوقت الحالي",
                    reply_markup=self._get_main_menu(is_admin)
                )

        elif data == "status":
            await self.cmd_status(update, context)

        elif data == "mtf_analysis":
            try:
                mtf_data = self.mtf.analyze_full(self.fetcher)
                report = self.mtf.format_mtf_report(mtf_data)
                await query.edit_message_text(report)
            except Exception as e:
                await query.edit_message_text(f"⚠️ خطأ: {e}")

        elif data == "smc_analysis":
            try:
                df = await self.fetcher.fetch_ohlcv("1h", limit=200)
                if df is not None and len(df) > 20:
                    smc_data = self.smc.analyze_all(df, "1h")
                    report = self.smc.format_smc_report(smc_data)
                    await query.edit_message_text(report)
                else:
                    await query.edit_message_text("⚠️ مفيش بيانات كافية")
            except Exception as e:
                await query.edit_message_text(f"⚠️ خطأ: {e}")

        elif data == "analysis":
            await query.edit_message_text("📊 جاري تحليل السوق...")
            await self.send_market_analysis()

        elif data == "summary":
            if not self.signal_history:
                await query.edit_message_text("⚠️ لا توجد إشارات اليوم")
            else:
                message = format_summary_message(self.signal_history)
                await query.edit_message_text(message[:4096])

        elif data == "confluence":
            await query.edit_message_text("📊 جاري تحليل التطابق...")
            conf_data = self.confluence.analyze_confluence()
            msg = self.confluence.format_confluence_report(conf_data)
            await query.edit_message_text(msg)

        elif data == "scan_pro":
            await query.edit_message_text("🔬 جاري تحليل 20 مؤشر على 5 أطر زمنية...")
            try:
                enhanced_data = self.enhanced_confluence.analyze(["5m", "15m", "1h", "4h", "1d"])
                msg = self.enhanced_confluence.format_report(enhanced_data)
                # Split if too long for Telegram
                if len(msg) > 4096:
                    await query.edit_message_text(msg[:4096])
                else:
                    await query.edit_message_text(msg)
            except Exception as e:
                await query.edit_message_text(f"❌ خطأ في التحليل: {e}")

        elif data == "stats":
            report = self.tracker.format_detailed_report(days=30)
            if len(report) > 4096:
                await query.edit_message_text(report[:4096])
            else:
                await query.edit_message_text(report)

        elif data == "price_alerts":
            alerts_msg = self.price_alerts.format_user_alerts(user_id)
            keyboard = [
                [InlineKeyboardButton("🔔 تنبيه سعر جديد", callback_data="alert_new")],
                [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
            ]
            await query.edit_message_text(
                alerts_msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

        elif data == "alert_new":
            await query.edit_message_text(
                "🔔 تنبيه سعر جديد\n\n"
                "اكتب السعر المستهدف بهذا الشكل:\n"
                "alert 4500 above\n"
                "أو\n"
                "alert 4450 below\n\n"
                "⬆️ above = تنبيه لما السعر يفوق الرقم\n"
                "⬇️ below = تنبيه لما السعر ينزل تحت الرقم"
            )

        elif data == "referral":
            bot_username = (await self.bot.get_me()).username
            ref_msg = self.referral_system.format_referral_info(user_id, bot_username)
            keyboard = [
                [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
            ]
            await query.edit_message_text(
                ref_msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

        elif data == "market_status":
            mkt = self.market_hours.get_market_status()
            status_emoji = "🟢" if mkt["open"] else "🔴"
            cooldown_remaining = self.cooldown.get_remaining()
            uptime = self.auto_restart.get_uptime()

            msg = f"🕒 حالة السوق\n"
            msg += "━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"{status_emoji} السوق: {mkt['status']}\n"
            msg += f"⏰ الإغلاق القادم: {mkt.get('next_close', '—')}\n"
            msg += f"🔓 الفتح القادم: {mkt.get('next_open', '—')}\n\n"
            msg += f"⏱️ كولداون الإشارات: {cooldown_remaining:.0f} دقيقة\n"
            msg += f"🔄 زمن التشغيل: {uptime}\n"
            msg += f"🔄 إعادات التشغيل: {self.auto_restart.restart_count}\n\n"
            msg += "🤖 صياد الشمعات | Candle Hunter"

            keyboard = [
                [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
            ]
            await query.edit_message_text(
                msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

        elif data == "admin_broadcast":
            if user_id != self.admin_id:
                await query.edit_message_text("❌ غير مصرح")
                return
            await query.edit_message_text(
                "📢 رسالة جماعية\n\n"
                "اكتب رسالتك بهذا الشكل:\n"
                "broadcast رسالتك هنا\n\n"
                f"👥 سيتم الإرسال لـ {len(self.user_manager.get_all_telegram_ids())} مستخدم"
            )

        elif data == "calendar":
            events = self.calendar.get_upcoming_events(hours_ahead=48)
            msg = self.calendar.format_events_message(events)
            await query.edit_message_text(msg)

        elif data == "performance":
            if is_admin:
                report = self.tracker.get_performance_report(days=7)
                await query.edit_message_text(report)
            else:
                await query.edit_message_text("❌ للأدمن فقط")

        # ===== حساب المستخدم =====
        elif data == "myaccount":
            info = self.user_manager.format_user_info(user_id)
            await query.edit_message_text(
                info,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings"),
                    InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"),
                ]])
            )

        elif data == "settings":
            user = self.user_manager.get_user(user_id)
            if not user and not is_admin:
                await query.edit_message_text("❌ غير مسجل")
                return
            await query.edit_message_text(
                "⚙️ **الإعدادات**\n\n"
                "اختر مستوى المخاطرة أو تحكم في التداول:",
                reply_markup=self._get_settings_menu()
            )

        # ===== إعدادات المخاطرة =====
        elif data == "risk_LOW":
            self.user_manager.set_risk_level(user_id, "LOW")
            await query.edit_message_text(
                "✅ تم ضبط المخاطرة: 🟢 منخفض (1%، 5x)\n"
                "أقل مخاطرة = أمان أكثر",
                reply_markup=self._get_settings_menu()
            )

        elif data == "risk_MEDIUM":
            self.user_manager.set_risk_level(user_id, "MEDIUM")
            await query.edit_message_text(
                "✅ تم ضبط المخاطرة: 🟡 متوسط (2%، 10x)\n"
                "متوازن بين العائد والمخاطرة",
                reply_markup=self._get_settings_menu()
            )

        elif data == "risk_HIGH":
            self.user_manager.set_risk_level(user_id, "HIGH")
            await query.edit_message_text(
                "✅ تم ضبط المخاطرة: 🔴 عالي (5%، 20x)\n"
                "⚠️ مخاطرة عالية — كن حذراً!",
                reply_markup=self._get_settings_menu()
            )

        elif data == "pause":
            self.user_manager.pause_user(user_id)
            await query.edit_message_text(
                "⏸️ تم إيقاف التداول التلقائي على حسابك\n"
                "لن يتم تنفيذ صفقات جديدة حتى تشغله",
                reply_markup=self._get_settings_menu()
            )

        elif data == "resume":
            self.user_manager.resume_user(user_id)
            await query.edit_message_text(
                "▶️ تم تشغيل التداول التلقائي\n"
                "سيتم تنفيذ الإشارات على حسابك",
                reply_markup=self._get_settings_menu()
            )

        # ===== أوامر الأدمن =====
        elif data == "users" and is_admin:
            stats = self.user_manager.format_admin_stats()
            await query.edit_message_text(
                stats[:4096],
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"),
                ]])
            )

        elif data == "autostatus" and is_admin:
            if self.auto_trader.owner_client:
                balance = self.auto_trader.owner_client.get_balance()
                positions = self.auto_trader.owner_client.get_positions()
                msg = "🤖 **حالة Auto-Trade**\n\n"
                msg += f"👑 حساب الأدمن: {'✅' if balance.get('success') else '❌'}\n"
                msg += f"💰 الرصيد: ${balance.get('free', 0):.2f}\n"
                msg += f"📊 صفقات مفتوحة: {len(positions)}\n"
                if positions:
                    for p in positions:
                        msg += f"  • {p['side']} {p['size']} @ {p['entry_price']:.2f} | PnL: ${p['unrealized_pnl']:.2f}\n"
                msg += f"\n👥 المستخدمين النشطين: {len(self.user_manager.get_active_users())}"
                await query.edit_message_text(msg)
            else:
                await query.edit_message_text(
                    "❌ Auto-Trade غير مفعل\n"
                    "أضف MEXC_API_KEY و MEXC_API_SECRET في Railway"
                )

        elif data == "admin" and is_admin:
            await query.edit_message_text(
                "⚙️ **لوحة تحكم الأدمن**\n\n"
                "اختر ما تريد:",
                reply_markup=self._get_admin_menu()
            )

        elif data == "admin_stats" and is_admin:
            stats = self.user_manager.format_admin_stats()
            await query.edit_message_text(
                stats[:4096],
                reply_markup=self._get_admin_menu()
            )

        elif data == "admin_users" and is_admin:
            users = self.user_manager.get_all_users()
            if not users:
                await query.edit_message_text(
                    "👥 لا يوجد مسجلين بعد",
                    reply_markup=self._get_admin_menu()
                )
                return
            msg = "👥 **المسجلين**\n\n"
            for u in users[:20]:
                status = {"ACTIVE": "🟢", "PAUSED": "⏸️", "BANNED": "🔴"}.get(u.get("status"), "❓")
                msg += f"{status} @{u.get('username', 'N/A')} (UID: {u.get('mexc_uid', '?')})\n"
                msg += f"   📋 {u.get('total_trades', 0)} صفقة | 💰 ${u.get('total_pnl', 0):.2f}\n"
            await query.edit_message_text(
                msg[:4096],
                reply_markup=self._get_admin_menu()
            )

        elif data == "admin_auto" and is_admin:
            await query.edit_message_text(
                "🤖 **تقرير Auto-Trade**\n\n"
                f"👑 Owner Client: {'✅' if self.auto_trader.owner_client else '❌'}\n"
                f"👥 Active Users: {len(self.user_manager.get_active_users())}\n"
                f"📋 Total Trades: {self.user_manager.get_stats()['total_trades']}\n"
                f"💰 Total PnL: ${self.user_manager.get_stats()['total_pnl']:.2f}",
                reply_markup=self._get_admin_menu()
            )

        elif data == "admin_balance" and is_admin:
            if self.auto_trader.owner_client:
                balance = self.auto_trader.owner_client.get_balance()
                positions = self.auto_trader.owner_client.get_positions()
                msg = "💰 **رصيد MEXC**\n\n"
                msg += f"💵 المتاح: ${balance.get('free', 0):.2f}\n"
                msg += f"📊 الإجمالي: ${balance.get('total', 0):.2f}\n"
                msg += f"📈 صفقات مفتوحة: {len(positions)}\n"
                await query.edit_message_text(msg, reply_markup=self._get_admin_menu())
            else:
                await query.edit_message_text("❌ MEXC API غير مفعل")

        elif data == "admin_closeall" and is_admin:
            result = await self.auto_trader.close_all_for_owner()
            if result.get("success"):
                await query.edit_message_text(
                    f"✅ تم إغلاق {result.get('closed', 0)} صفقة",
                    reply_markup=self._get_admin_menu()
                )
            else:
                await query.edit_message_text(
                    f"❌ فشل: {result.get('error', 'خطأ')}",
                    reply_markup=self._get_admin_menu()
                )

        elif data == "admin_performance" and is_admin:
            report = self.tracker.get_performance_report(days=7)
            await query.edit_message_text(report, reply_markup=self._get_admin_menu())

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الرسائل النصية العادية (خلال التسجيل)"""
        if update.message is None:
            return
        user_id = update.effective_user.id
        if user_id in self._registration_state:
            await self.handle_registration(update, context)
        else:
            # لو مش في حالة تسجيل، اعرض القائمة
            await self.cmd_start(update, context)

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
        except Exception as e:
            logger.error(f"Analysis error: {e}")

    async def send_daily_summary(self):
        """يرسل ملخص يومي شامل للقناة الخاصة"""
        if not self.private_channel:
            return

        # لا ترسل ملخص في الويك إند
        if not self.market_hours.is_market_open():
            logger.info("📊 Daily summary skipped — market closed")
            return
        try:
            # تقرير الإحصائيات التفصيلي
            report = self.tracker.format_detailed_report(days=1)
            await self.bot.send_message(
                chat_id=self.private_channel,
                text=report
            )

            # ملخص الإشارات
            today_signals = [
                s for s in self.signal_history
                if s.get("timestamp", "").startswith(datetime.now().strftime('%Y-%m-%d'))
            ]
            if today_signals:
                message = format_summary_message(today_signals)
                await self.bot.send_message(
                    chat_id=self.private_channel,
                    text=message,
                    parse_mode='HTML'
                )

            logger.info(f"Daily summary sent: {len(today_signals)} signals today")
        except Exception as e:
            logger.error(f"Daily summary error: {e}")

    # ═══════════════════════════════════════════════════════════
    # Scheduled Scans
    # ═══════════════════════════════════════════════════════════

    async def run_scalping_scan(self):
        logger.info("🔄 Starting SCALPING scan...")
        signals = await self.scan_market("SCALPING")
        if signals:
            await self.process_signals(signals)
        logger.info(f"Scalping scan complete: {len(signals)} signals found")

    async def run_medium_scan(self):
        logger.info("🔄 Starting MEDIUM scan...")
        signals = await self.scan_market("MEDIUM")
        if signals:
            await self.process_signals(signals)
        logger.info(f"Medium scan complete: {len(signals)} signals found")

    async def run_swing_scan(self):
        logger.info("🔄 Starting SWING scan...")
        signals = await self.scan_market("SWING")
        if signals:
            await self.process_signals(signals)
        logger.info(f"Swing scan complete: {len(signals)} signals found")

    # ═══════════════════════════════════════════════════════════
    # Scheduler
    # ═══════════════════════════════════════════════════════════

    def _schedule_async(self, coro_func):
        """يضيف coroutine task للـ event loop النشط"""
        try:
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(coro_func(), loop=loop)
        except RuntimeError:
            logger.warning("No running loop for scheduled job, skipping")
        except Exception as e:
            logger.error(f"Schedule async error: {e}")

    async def _job_scalping(self, context=None):
        logger.info("⏰ Scalping schedule triggered")
        await self.run_scalping_scan()

    async def _job_medium(self, context=None):
        logger.info("⏰ Medium schedule triggered")
        await self.run_medium_scan()

    async def _job_swing(self, context=None):
        logger.info("⏰ Swing schedule triggered")
        await self.run_swing_scan()

    async def _job_analysis(self, context=None):
        logger.info("⏰ Analysis schedule triggered")
        await self.send_market_analysis()

    async def _job_summary(self, context=None):
        logger.info("⏰ Daily summary schedule triggered")
        await self.send_daily_summary()

    async def _job_news_check(self, context=None):
        logger.info("⏰ News check triggered")
        try:
            await self.check_news_alerts()
        except Exception as e:
            logger.error(f"News check job error: {e}")

    # Legacy sync wrappers (fallback)
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
        self._schedule_async(self.check_news_alerts)

    async def _job_health_monitor(self, context=None):
        """Health monitor: check all systems every 30 min"""
        try:
            # Check Trade Bot (skip if TRADE_BOT_HEALTH_CHECK=off — bot stopped by owner)
            trade_bot_ok = True
            if os.getenv("TRADE_BOT_HEALTH_CHECK", "on").lower() not in ("off", "false", "0"):
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            os.getenv("TRADE_BOT_URL", "https://bbpro-trade-bot-production.up.railway.app") + "/stats",
                            timeout=10
                        )
                        trade_bot_ok = resp.status_code == 200
                except:
                    trade_bot_ok = False

            # Check MEXC API (owner)
            mexc_ok = True
            if self.auto_trader and self.auto_trader.owner_client:
                try:
                    bal = self.auto_trader.owner_client.get_balance()
                    mexc_ok = bal.get("success", False)
                    if mexc_ok:
                        self.circuit_breaker.record_api_success()
                    else:
                        should_pause, reason = self.circuit_breaker.record_api_failure()
                        if should_pause and self.private_channel:
                            await self.bot.send_message(
                                chat_id=self.private_channel,
                                text="⚠️ **MEXC API not responding**\n" + str(reason)
                            )
                except:
                    mexc_ok = False
                    should_pause, reason = self.circuit_breaker.record_api_failure()
                    if should_pause and self.private_channel:
                        await self.bot.send_message(
                            chat_id=self.private_channel,
                            text="⚠️ **MEXC API failed**\n" + str(reason)
                        )

            # Failsafe: Check user API keys
            active_users = self.user_manager.get_active_users()
            for user in active_users:
                try:
                    api_key, api_secret = self.user_manager.get_user_api(user["telegram_id"])
                    if not api_key or not api_secret:
                        continue
                    client = MexcClient(api_key, api_secret, is_futures=True)
                    bal = client.get_balance()
                    if not bal.get("success"):
                        self.user_manager.pause_user(user["telegram_id"])
                        try:
                            await self.bot.send_message(
                                chat_id=user["telegram_id"],
                                text="⚠️ **مفتاح MEXC API مش شغال**\n"
                                     "تم إيقاف التداول التلقائي على حسابك.\n"
                                     "حدث مفتاحك من: MEXC → Profile → API Management\n"
                                     "ثم استخدم /start لإعادة التسجيل"
                            )
                        except:
                            pass
                        logger.warning(f"Dead API key for user {user.get('telegram_id')} — paused & notified")
                except:
                    pass

            if not trade_bot_ok or not mexc_ok:
                logger.warning(f"🏥 Health: TradeBot={'OK' if trade_bot_ok else 'DOWN'} MEXC={'OK' if mexc_ok else 'DOWN'}")
                if not trade_bot_ok and self.private_channel:
                    await self.bot.send_message(
                        chat_id=self.private_channel,
                        text="⚠️ **Trade Bot مش مستجيب** — جاري المراقبة"
                    )
            else:
                logger.info("🏥 Health: All systems OK")

        except Exception as e:
            logger.error(f"Health monitor error: {e}")

    async def _job_subscription_check(self, context=None):
        """Check expired subscriptions every hour"""
        try:
            expired = self.subscription_manager.expire_check_all()
            for sub in expired:
                tid = sub.get("telegram_id")
                if tid:
                    try:
                        price = self.subscription_manager.get_price_for_user(tid)
                        await self.bot.send_message(
                            chat_id=tid,
                            text=(
                                "💎 اشتراكك انتهى\n"
                                "━━━━━━━━━━━━━━━━━━━━\n"
                                f"تجدد بـ ${price}/أسبوع\n"
                                "تواصل مع الإدارة للتجديد"
                            )
                        )
                    except:
                        pass
        except Exception as e:
            logger.error(f"Subscription check error: {e}")

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
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN not set! Check .env file")
            sys.exit(1)

        if not PUBLIC_CHANNEL_ID and not PRIVATE_CHANNEL_ID:
            logger.error("No channel IDs set! Check .env file")
            sys.exit(1)

        logger.info("━" * 40)
        logger.info("🚀 صياد الشمعات | Candle Hunter Starting...")
        logger.info("📊 Symbol: XAU/USD (Gold)")
        logger.info(f"📈 Strategies: 13")
        logger.info(f"📏 Indicators: 22+")
        logger.info(f"📡 Public Channel: {'✅' if self.public_channel else '❌'}")
        logger.info(f"📡 Private Channel: {'✅' if self.private_channel else '❌'}")
        logger.info(f"🤖 Auto-Trade: {'✅' if self.auto_trader.owner_client else '❌'}")
        logger.info(f"👥 Users: {self.user_manager.get_stats()['total']}")
        logger.info(f"⏱️ Signal Cooldown: {self.cooldown.cooldown_minutes} min")
        logger.info(f"📏 Spread Filter: max {self.spread_filter.max_spread_pct}%")
        logger.info(f"😱 Fear & Greed: ✅")
        logger.info(f"💵 DXY Filter: ✅")
        logger.info(f"📊 Weekly Report: ✅ (Friday 8PM)")
        logger.info(f"👥 Referral System: ✅")
        logger.info(f"📐 Smart Sizing: ✅")
        logger.info(f"⏰ Pre-Close Alerts: ✅")
        logger.info(f"🔄 Auto-Restart: ✅")
        logger.info(f"🤖 AI News Sentiment: ✅ (Groq + Finnhub)")
        logger.info(f"🥇 GoldAPI Spot: ✅ (LBMA)")
        logger.info(f"💰 FMP Gold Futures: ✅")
        logger.info(f"🔔 OCO Order Management: ✅")
        logger.info(f"🧠 SMC + Order Flow: ✅ (VWAP/OB/FVG/VP/ADX)")
        logger.info(f"📊 MTF Confluence: ✅ (4h/1h/15m/5m + OBV/Fib/HA)")
        logger.info("━" * 40)

        # Setup Telegram commands
        app = Application.builder().token(BOT_TOKEN).build()
        self._app = app
        self.bot = app.bot

        # Command handlers
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("scan", self.cmd_scan))
        app.add_handler(CommandHandler("brief", self.cmd_daily_brief))
        app.add_handler(CommandHandler("analysis", self.cmd_analysis))
        app.add_handler(CommandHandler("summary", self.cmd_summary))
        app.add_handler(CommandHandler("performance", self.cmd_performance))
        app.add_handler(CommandHandler("stats", self.cmd_stats))
        app.add_handler(CommandHandler("scan_pro", self.cmd_confluence_enhanced))
        app.add_handler(CommandHandler("calendar", self.cmd_calendar))
        app.add_handler(CommandHandler("confluence", self.cmd_confluence))

        # Callback query handler (الأزرار)
        app.add_handler(CallbackQueryHandler(self.handle_callback))

        # Text message handler (للتسجيل)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

        # Setup schedules using PTB JobQueue (native async, no GC issues)
        if app.job_queue:
            # app.job_queue.run_repeating(self._job_scalping, interval=900, first=120)    # SCALPING DISABLED — medium + swing only
            app.job_queue.run_repeating(self._job_medium, interval=3600, first=3600)    # 60 min
            app.job_queue.run_repeating(self._job_swing, interval=14400, first=14400)  # 4 hours
            app.job_queue.run_repeating(self._job_news_check, interval=600, first=600) # 10 min
            app.job_queue.run_repeating(self._job_health_monitor, interval=1800, first=300) # 30 min health
            app.job_queue.run_repeating(self._job_subscription_check, interval=3600, first=600) # 1 hour sub check
            app.job_queue.run_repeating(self._job_analysis, interval=21600, first=21600) # 6 hours
            app.job_queue.run_daily(callback=self._job_summary, time=dt_time(hour=23, minute=0))  # 23:00 daily
            logger.info("✅ JobQueue scheduled: medium(60m), swing(4h), news(10m), health(30m), subs(1h), analysis(6h), summary(23:00) — scalping disabled")
        else:
            logger.error("❌ JobQueue not available!")

        # Run scheduler in background
        async def run_scheduler(app):
            logger.info("⏱️ Initial scan in 30 seconds...")
            await asyncio.sleep(30)
            # SCALPING DISABLED — skipping initial scalping scan
            logger.info("🔄 Running initial medium scan...")
            await self.run_medium_scan()
            logger.info("✅ Initial scans complete — JobQueue takes over")

        async def post_init(app):
            # لا إرسال رسالة بدء في القناة
            # Store reference to prevent garbage collection
            self._scheduler_task = asyncio.create_task(run_scheduler(app))

        app.post_init = post_init

        # Error handler — تجاهل Conflict (multiple instances مؤقت)
        async def error_handler(update, context):
            error = context.error
            from telegram.error import Conflict, NetworkError, TimedOut
            if isinstance(error, Conflict):
                logger.warning("⚠️ Telegram Conflict — another instance running. Waiting 10s...")
                await asyncio.sleep(10)
                return
            elif isinstance(error, (NetworkError, TimedOut)):
                logger.warning(f"⚠️ Network error: {error}")
                return
            else:
                import traceback
                logger.error(f"Unhandled error: {error}")
                logger.error(traceback.format_exc())

        app.add_error_handler(error_handler)

        logger.info("Bot is running! Press Ctrl+C to stop.")
        # Start health check server for Railway
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status":"ok","bot":"candle-hunter"}')

            def do_GET(self):
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(self.path)
                if parsed.path == "/signals/state":
                    qs = parse_qs(parsed.query)
                    if qs.get("secret", [""])[0] != os.getenv("SIGNALS_API_SECRET", ""):
                        self.send_response(401)
                        self.end_headers()
                        return
                    data_file = os.path.join(
                        os.getenv("STATE_DIR", os.path.dirname(os.path.abspath(__file__))),
                        "signals_data.json")
                    try:
                        size = os.path.getsize(data_file)
                        content = open(data_file).read()
                        info = {"exists": True, "size": size,
                                "count": len(json.loads(content)) if size > 2 else 0,
                                "state_dir": os.getenv("STATE_DIR", "")}
                    except Exception as e:
                        info = {"exists": False, "error": str(e),
                                "state_dir": os.getenv("STATE_DIR", "")}
                    body = json.dumps(info).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif parsed.path == "/signals/latest":
                    qs = parse_qs(parsed.query)
                    if qs.get("secret", [""])[0] != os.getenv("SIGNALS_API_SECRET", ""):
                        self.send_response(401)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(b'{"error":"unauthorized"}')
                        return
                    data_file = os.path.join(
                        os.getenv("STATE_DIR", os.path.dirname(os.path.abspath(__file__))),
                        "signals_data.json")
                    try:
                        with open(data_file, "r", encoding="utf-8") as f:
                            signals = json.load(f)
                    except Exception:
                        signals = []
                    since = qs.get("since", [""])[0]
                    if since:
                        signals = [s for s in signals if str(s.get("created_at", "")) > since]
                    limit = min(int(qs.get("limit", ["10"])[0]), 50)
                    signals = sorted(signals, key=lambda s: str(s.get("created_at", "")), reverse=True)[:limit]
                    body = json.dumps({"signals": signals}, ensure_ascii=False).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif parsed.path == "/signals/rejected":
                    qs = parse_qs(parsed.query)
                    if qs.get("secret", [""])[0] != os.getenv("SIGNALS_API_SECRET", ""):
                        self.send_response(401)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(b'{"error":"unauthorized"}')
                        return
                    rej_file = os.path.join(
                        os.getenv("STATE_DIR", os.path.dirname(os.path.abspath(__file__))),
                        "rejected_signals.json")
                    try:
                        with open(rej_file, "r", encoding="utf-8") as f:
                            rejected = json.load(f)
                    except Exception:
                        rejected = []
                    limit = min(int(qs.get("limit", ["100"])[0]), 500)
                    rejected = sorted(rejected, key=lambda s: str(s.get("created_at", s.get("rejected_at", ""))), reverse=True)[:limit]
                    from collections import Counter
                    reasons = Counter()
                    confs = []
                    for r in rejected:
                        reason = str(r.get("rejected_reason") or r.get("reason") or "quality_gate")[:30]
                        reasons[reason] += 1
                        c = r.get("confidence", 0)
                        if isinstance(c, (int, float)):
                            confs.append(round(c))
                    summary = {
                        "count": len(rejected),
                        "top_confidences": sorted(confs, reverse=True)[:10],
                        "reasons": dict(reasons),
                        "oldest": str(rejected[-1].get("created_at", "")) if rejected else "",
                    }
                    body = json.dumps({"summary": summary, "rejected": rejected}, ensure_ascii=False).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok","bot":"candle-hunter"}')

            def log_message(self, format, *args):
                pass
        
        def start_health_server():
            server = HTTPServer(('0.0.0.0', int(os.environ.get('PORT', 8080))), HealthHandler)
            server.serve_forever()
        
        threading.Thread(target=start_health_server, daemon=True).start()
        logger.info(f"✅ Health endpoint on port {os.environ.get('PORT', 8080)}")
        
        app.run_polling(stop_signals=None)


if __name__ == '__main__':
    bot = CandleHunterSignalBot()
    bot.run()
