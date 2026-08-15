"""
main.py
=======
BBPro Signal Bot — Ultimate Edition v3

Signal-only bot that sends trade recommendations via Telegram.
NO real orders are placed. The human takes the decision.

Features:
  1.  Cooldown per symbol (prevent spam)
  2.  R:R ratio enforcement (auto-reject if < 1.5)
  3.  Signal tracking (WIN/LOSS/EXPIRED)
  4.  Inline Telegram buttons
  5.  Candlestick pattern confirmation (8 patterns)
  6.  Multi-strategy engine (8 strategies)
  7.  Multi-timeframe confluence (M15/M30/H1/H4)
  8.  Signal expiry
  9.  Support/Resistance levels in signal
 10.  Economic calendar integration
 11.  Symbol-specific profiles (6 symbols)
 12.  Pre-signal alerts
 13.  Daily/weekly performance reports
 14.  Smart Money Concepts (SMC): Order Blocks, FVG, BOS/CHoCH, Liquidity Sweeps
 15.  VWAP strategy with bands
 16.  RSI & MACD Divergence detection
 17.  Market Regime Detection (trending/ranging/volatile/choppy)
 18.  Risk Manager Pro: Kelly Criterion, Multi-TP, Break-Even, Signal Quality Score
 19.  Backtesting engine
 20.  Telegram bot commands (/status, /stats, /backtest, /report, /news, /help)
"""

import asyncio
import logging
import signal as sig_module
import sys
import os
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from config import BotConfig, DEFAULT_CONFIG, TradeDirection, BreakoutMode
from indicators import compute_all_indicators, calc_fibonacci
from filters import multi_layer_filter, parse_news_times, should_close_all_on_friday
from risk_manager import calculate_sl_tp, DailyState, check_daily_reset
from ctrader_client import CTraderClient, SymbolInfo, Bar
from notifications.telegram import create_notifier
from groq_analyzer import GroqAnalyzer
from storage.database import TradeDB
from analytics.performance import PerformanceAnalyzer

# ── Core feature imports ──────────────────────────────────────────────────
try:
    from candlestick import detect_all_patterns
    HAS_CANDLESTICK = True
except ImportError:
    HAS_CANDLESTICK = False

try:
    from strategies import StrategyManager
    HAS_STRATEGIES = True
except ImportError:
    HAS_STRATEGIES = False

try:
    from multi_tf import MultiTFAnalyzer
    HAS_MTF = True
except ImportError:
    HAS_MTF = False

try:
    from sr_levels import SRLevels
    HAS_SR = True
except ImportError:
    HAS_SR = False

try:
    from signal_tracker import SignalTracker
    HAS_TRACKER = True
except ImportError:
    HAS_TRACKER = False

try:
    from performance_report import PerformanceReporter
    HAS_REPORTER = True
except ImportError:
    HAS_REPORTER = False

try:
    from economic_calendar import EconomicCalendar
    HAS_ECON_CAL = True
except ImportError:
    HAS_ECON_CAL = False

try:
    from symbol_profiles import get_profile, apply_profile
    HAS_PROFILES = True
except ImportError:
    HAS_PROFILES = False

# ── Advanced feature imports (v3) ──────────────────────────────────────────
try:
    from smc import SmartMoneyConcepts
    HAS_SMC = True
except ImportError:
    HAS_SMC = False

try:
    from vwap import VWAPStrategy
    HAS_VWAP = True
except ImportError:
    HAS_VWAP = False

try:
    from risk_manager_pro import RiskManagerPro
    HAS_RISK_PRO = True
except ImportError:
    HAS_RISK_PRO = False

try:
    from backtest import Backtester
    HAS_BACKTEST = True
except ImportError:
    HAS_BACKTEST = False

try:
    from market_regime import MarketRegimeDetector
    HAS_REGIME = True
except ImportError:
    HAS_REGIME = False

try:
    from divergence import DivergenceDetector
    HAS_DIVERGENCE = True
except ImportError:
    HAS_DIVERGENCE = False

try:
    from telegram_commands import TelegramCommandHandler
    HAS_TG_CMDS = True
except ImportError:
    HAS_TG_CMDS = False

# ── v4 Advanced strategies ──────────────────────────────────────────────────
try:
    from fvg_strategy import FVGStrategy
    HAS_FVG_STRAT = True
except ImportError:
    HAS_FVG_STRAT = False

try:
    from ict_killzones import ICTKillzoneStrategy
    HAS_ICT_STRAT = True
except ImportError:
    HAS_ICT_STRAT = False

try:
    from volume_profile import VolumeProfileStrategy
    HAS_VP_STRAT = True
except ImportError:
    HAS_VP_STRAT = False

try:
    from correlation import CorrelationAnalyzer
    HAS_CORRELATION = True
except ImportError:
    HAS_CORRELATION = False


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BBProSignal")


class BollingerBreakoutSignalBot:
    """Signal-only bot — Ultimate Edition v3."""

    def __init__(self, cfg: Optional[BotConfig] = None, enable_commands: bool = True):
        self.cfg = cfg or DEFAULT_CONFIG
        self.client = CTraderClient(self.cfg)
        self.daily_state = DailyState()
        self._daily_signal_count = 0
        self._daily_signals: list = []
        self.news_times = parse_news_times(self.cfg.manual_news_times)
        self.symbol_info: Optional[SymbolInfo] = None
        self.bars: List[Bar] = []
        self._stop = False
        self._last_bar_ts: Optional[float] = None
        self._kill_switch_active = False

        # Cooldown tracking
        self._last_signal_time: Dict[str, datetime] = {}

        # Pre-signal alert tracking
        self._pre_alert_sent: Dict[str, bool] = {}

        # ── Core components ────────────────────────────────────────────
        self.notifier = create_notifier(
            self.cfg.telegram_bot_token,
            self.cfg.telegram_chat_id,
            self.cfg.telegram_enabled,
        )
        self.db: Optional[TradeDB] = (
            TradeDB(self.cfg.db_path) if self.cfg.db_enabled else None
        )
        self.analyzer = PerformanceAnalyzer(self.cfg.db_path) if self.cfg.db_enabled else None
        self.ai = GroqAnalyzer()

        # Signal tracker
        self.tracker: Optional[SignalTracker] = None
        if HAS_TRACKER:
            self.tracker = SignalTracker(
                expiry_bars=self.cfg.signal_expiry_bars,
                db_path=self.cfg.db_path if self.cfg.db_enabled else "",
            )

        # Performance reporter
        self.reporter: Optional[PerformanceReporter] = None
        if HAS_REPORTER and self.tracker:
            self.reporter = PerformanceReporter(self.tracker, self.notifier)

        # Economic calendar
        self.econ_cal: Optional[EconomicCalendar] = None
        if HAS_ECON_CAL and self.cfg.enable_economic_calendar:
            self.econ_cal = EconomicCalendar(
                blackout_before_min=self.cfg.news_blackout_before_min,
                blackout_after_min=self.cfg.news_blackout_after_min,
            )

        # Strategy manager
        self.strategy_mgr: Optional[StrategyManager] = None
        if HAS_STRATEGIES:
            self.strategy_mgr = StrategyManager()

        # MTF analyzer
        self.mtf_analyzer: Optional[MultiTFAnalyzer] = None
        if HAS_MTF:
            self.mtf_analyzer = MultiTFAnalyzer()

        # S/R levels calculator
        self.sr_calc: Optional[SRLevels] = None
        if HAS_SR:
            self.sr_calc = SRLevels(lookback=self.cfg.sr_lookback)

        # ── Advanced components (v3) ────────────────────────────────────
        self.smc: Optional[SmartMoneyConcepts] = None
        if HAS_SMC:
            self.smc = SmartMoneyConcepts()

        self.vwap: Optional[VWAPStrategy] = None
        if HAS_VWAP:
            self.vwap = VWAPStrategy()

        self.risk_pro: Optional[RiskManagerPro] = None
        if HAS_RISK_PRO:
            self.risk_pro = RiskManagerPro()

        self.backtester: Optional[Backtester] = None
        if HAS_BACKTEST:
            self.backtester = Backtester()

        self.regime_detector: Optional[MarketRegimeDetector] = None
        if HAS_REGIME:
            self.regime_detector = MarketRegimeDetector()

        self.divergence: Optional[DivergenceDetector] = None
        if HAS_DIVERGENCE:
            self.divergence = DivergenceDetector()

        # ── v4 Advanced strategy components ──────────────────────────────
        self.fvg_strategy: Optional[FVGStrategy] = None
        if HAS_FVG_STRAT:
            self.fvg_strategy = FVGStrategy()

        self.ict_killzones: Optional[ICTKillzoneStrategy] = None
        if HAS_ICT_STRAT:
            self.ict_killzones = ICTKillzoneStrategy()

        self.vol_profile: Optional[VolumeProfileStrategy] = None
        if HAS_VP_STRAT:
            self.vol_profile = VolumeProfileStrategy()

        self.correlation: Optional[CorrelationAnalyzer] = None
        if HAS_CORRELATION:
            self.correlation = CorrelationAnalyzer()

        # Telegram command handler (only one instance should poll to avoid 409 Conflict)
        self.cmd_handler: Optional[TelegramCommandHandler] = None
        if enable_commands and HAS_TG_CMDS and self.cfg.telegram_enabled:
            self.cmd_handler = TelegramCommandHandler(
                bot_token=self.cfg.telegram_bot_token,
                chat_id=self.cfg.telegram_chat_id,
                bot_instance=self,
            )

        # Daily report tracking
        self._last_report_date: Optional[str] = None

        # Active feature flags
        features = []
        if HAS_CANDLESTICK: features.append("Candlestick")
        if HAS_STRATEGIES: features.append("MultiStrat")
        if HAS_MTF: features.append("MTF")
        if HAS_SR: features.append("S/R")
        if HAS_TRACKER: features.append("Tracker")
        if HAS_ECON_CAL: features.append("EconCal")
        if HAS_SMC: features.append("SMC")
        if HAS_VWAP: features.append("VWAP")
        if HAS_RISK_PRO: features.append("RiskPro")
        if HAS_BACKTEST: features.append("Backtest")
        if HAS_REGIME: features.append("Regime")
        if HAS_DIVERGENCE: features.append("Divergence")
        if HAS_TG_CMDS: features.append("TgCmds")
        if HAS_FVG_STRAT: features.append("FVG")
        if HAS_ICT_STRAT: features.append("ICT-Killzones")
        if HAS_VP_STRAT: features.append("VolProfile")
        if HAS_CORRELATION: features.append("Correlation")
        self._features = features

    # ------------------------------------------------------------------
    #  LIFECYCLE
    # ------------------------------------------------------------------
    async def run(self) -> None:
        # Start web monitor
        if self.cfg.web_monitor_enabled:
            try:
                from web.monitor import start_monitor
                start_monitor(self.cfg.db_path, self.cfg.web_monitor_port,
                              self.cfg.web_monitor_host)
                logger.info("🌐 Web monitor: http://localhost:%d", self.cfg.web_monitor_port)
            except Exception as e:
                logger.warning("Web monitor failed to start: %s", e)

        logger.info("=" * 70)
        logger.info("BBPro Signal Bot — ULTIMATE Edition v3")
        logger.info("=" * 70)
        logger.info("Symbol: %s | TF: %s | Mode: SIGNAL ONLY", self.cfg.symbol, self.cfg.timeframe)
        logger.info("Strategies: %s", ", ".join(self.cfg.enabled_strategies) if self.cfg.enabled_strategies else "none")
        logger.info("Features active: %s", ", ".join(self._features))
        logger.info("Telegram=%s | DB=%s | Web=%s",
                    self.cfg.telegram_enabled, self.cfg.db_enabled, self.cfg.web_monitor_enabled)
        logger.info("=" * 70)

        # Apply symbol profile
        if HAS_PROFILES:
            apply_profile(self.cfg, self.cfg.symbol)

        # Connect (data-only)
        await self.client.connect()
        await asyncio.sleep(1.0)

        # Fetch symbol info
        try:
            self.symbol_info = await self.client.get_symbol_info(self.cfg.symbol)
            logger.info("Symbol info: pip_size=%.5f | pip_val=%.5f",
                        self.symbol_info.pip_size, self.symbol_info.pip_value_per_unit)
        except Exception as e:
            logger.error("Failed to fetch symbol info: %s", e)
            self.symbol_info = await self._fallback_symbol_info(self.cfg.symbol)

        # Warm-up bars
        warmup_count = max(self.cfg.bb_period, self.cfg.slow_ema_period, self.cfg.atr_period) + 50
        self.bars = await self.client.get_recent_bars(
            self.cfg.symbol, self.cfg.timeframe, count=warmup_count
        )
        if self.bars:
            logger.info("Warm-up bars loaded: %d (%s)", len(self.bars), self.cfg.symbol)
            self._last_bar_ts = self.bars[-1].timestamp
        else:
            logger.warning("No warm-up bars for %s", self.cfg.symbol)

        equity = await self.client.get_account_equity()
        self.daily_state.reset(equity, datetime.now(timezone.utc))

        # Telegram start notification — handled by run_all_symbols()

        # Start Telegram command handler
        if self.cmd_handler:
            asyncio.create_task(self.cmd_handler.poll_loop())
            logger.info("Telegram command handler started (/help for commands)")

        self._install_signal_handlers()

        logger.info("Entering main loop for %s (poll every %ds)", self.cfg.symbol, self.cfg.poll_interval_sec)
        try:
            while not self._stop:
                await self._tick()
                await asyncio.sleep(self.cfg.poll_interval_sec)
        except asyncio.CancelledError:
            logger.info("Main loop cancelled for %s", self.cfg.symbol)
        finally:
            await self.client.disconnect()
            logger.info("Bot stopped for %s", self.cfg.symbol)

    async def _fallback_symbol_info(self, symbol: str) -> SymbolInfo:
        pip_map = {"XAUUSD": 0.1, "XAGUSD": 0.01, "USDJPY": 0.01, "EURJPY": 0.01, "GBPJPY": 0.01}
        pip = pip_map.get(symbol, 0.0001)
        pip_val = {"XAUUSD": 0.01, "EURUSD": 0.0001, "GBPUSD": 0.0001,
                   "USDJPY": 0.000065, "EURJPY": 0.000065}.get(symbol, 0.0001)
        return SymbolInfo(pip, 1000, 1000, pip_val)

    def _install_signal_handlers(self):
        try:
            loop = asyncio.get_running_loop()
            for s in (sig_module.SIGINT, sig_module.SIGTERM):
                loop.add_signal_handler(s, self._request_stop)
        except NotImplementedError:
            pass

    def _request_stop(self):
        logger.info("Stop signal received for %s", self.cfg.symbol)
        self._stop = True

    # ------------------------------------------------------------------
    #  MAIN TICK
    # ------------------------------------------------------------------
    async def _tick(self) -> None:
        now_utc = datetime.now(timezone.utc)

        equity = await self.client.get_account_equity()
        if check_daily_reset(self.daily_state, equity, now_utc):
            logger.info("New day reset for %s | Signals yesterday: %d", self.cfg.symbol, self._daily_signal_count)
            self._daily_signal_count = 0
            self._daily_signals = []
            self._last_signal_time.clear()
            self._pre_alert_sent.clear()

        # Daily report
        if self.cfg.enable_daily_report and self._last_report_date != now_utc.strftime("%Y-%m-%d"):
            if now_utc.hour >= self.cfg.daily_report_hour_utc:
                self._last_report_date = now_utc.strftime("%Y-%m-%d")
                if self.reporter and self.tracker:
                    stats = self.tracker.get_stats()
                    stats["pending"] = len(self.tracker.get_active())
                    self.notifier.send_daily_report(stats)

        # Check signal tracking results
        if self.tracker and self.tracker.get_active():
            try:
                results = await self.tracker.check_signals(self.client)
                for result in results:
                    self.notifier.send_signal_result(
                        symbol=result.get("symbol", ""),
                        side=result.get("side", ""),
                        result=result["result"],
                        price=result.get("price", 0),
                        pips=result.get("pips", 0),
                        signal_id=result.get("signal_id", ""),
                    )
                    self.tracker.remove_signal(result["signal_id"])
            except Exception as e:
                logger.warning("[%s] Signal tracking error: %s", self.cfg.symbol, e)

        # Economic calendar check
        if self.econ_cal:
            try:
                is_blackout, reason = self.econ_cal.is_blackout(self.cfg.symbol)
                if is_blackout:
                    if self.cfg.show_debug:
                        logger.info("[%s] Economic blackout: %s", self.cfg.symbol, reason)
                    return
                # News pre-alert: notify about upcoming high-impact news
                next_event = self.econ_cal.get_next_event(self.cfg.symbol)
                if next_event:
                    try:
                        event_time = datetime.fromisoformat(next_event["time"].replace("Z", "+00:00"))
                        if event_time.tzinfo is None:
                            event_time = event_time.replace(tzinfo=timezone.utc)
                        mins_until = (event_time - now_utc).total_seconds() / 60
                        if 30 < mins_until < 45 and not self._pre_alert_sent.get(f"{self.cfg.symbol}_news"):
                            self.notifier.send(
                                f"📰 NEWS ALERT | {self.cfg.symbol}\n"
                                f"⏰ {next_event.get('title', 'Economic Event')} in ~{int(mins_until)} min\n"
                                f"🔑 Currency: {next_event.get('currency', 'N/A')}\n"
                                f"⚠️ High impact — signals paused during release"
                            )
                            self._pre_alert_sent[f"{self.cfg.symbol}_news"] = True
                        elif mins_until > 60:
                            self._pre_alert_sent.pop(f"{self.cfg.symbol}_news", None)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("[%s] Econ calendar error: %s", self.cfg.symbol, e)

        # Friday close
        if should_close_all_on_friday(now=now_utc):
            return

        # New bar check
        if await self._check_new_bar():
            await self._on_bar_close(now_utc)

    # ------------------------------------------------------------------
    #  NEW-BAR DETECTION
    # ------------------------------------------------------------------
    async def _check_new_bar(self) -> bool:
        if not self.symbol_info:
            return False
        new_bars = await self.client.get_recent_bars(
            self.cfg.symbol, self.cfg.timeframe, count=5
        )
        if not new_bars:
            return False
        latest_ts = new_bars[-1].timestamp
        if self._last_bar_ts is None or latest_ts > self._last_bar_ts:
            if self._last_bar_ts is not None:
                truly_new = [b for b in new_bars if b.timestamp > self._last_bar_ts]
                if truly_new:
                    self.bars.extend(truly_new)
                else:
                    # Same timestamp — update the last bar (still forming)
                    if new_bars[-1].timestamp == self._last_bar_ts:
                        self.bars[-1] = new_bars[-1]
                    else:
                        self.bars.append(new_bars[-1])
            else:
                self.bars = list(new_bars)

            max_window = max(self.cfg.slow_ema_period, 500)
            if len(self.bars) > max_window * 2:
                self.bars = self.bars[-max_window * 2:]
            self._last_bar_ts = latest_ts
            return True
        elif latest_ts == self._last_bar_ts and self.bars:
            # Update the last (forming) bar with latest prices
            self.bars[-1] = new_bars[-1]
        return False

    # ------------------------------------------------------------------
    #  BAR-CLOSE EVALUATION — Ultimate Signal Detection
    # ------------------------------------------------------------------
    async def _on_bar_close(self, now_utc: datetime) -> None:
        if len(self.bars) < max(self.cfg.bb_period, self.cfg.slow_ema_period, self.cfg.atr_period) + 5:
            return

        if self._kill_switch_active:
            return

        # Cooldown check
        if self._is_in_cooldown(self.cfg.symbol, now_utc):
            if self.cfg.show_debug:
                remaining = self._cooldown_remaining(self.cfg.symbol, now_utc)
                logger.info("[%s] Cooldown active (%.0f min remaining)", self.cfg.symbol, remaining)
            return

        # Fetch H4 bars
        try:
            bars_h4 = await self.client.get_recent_bars(self.cfg.symbol, "h4", count=250)
        except Exception:
            bars_h4 = []

        # Compute indicators
        closes = np.array([b.close for b in self.bars])
        highs  = np.array([b.high for b in self.bars])
        lows   = np.array([b.low for b in self.bars])
        ind = compute_all_indicators(highs, lows, closes, self.cfg)

        idx = -1
        close_now  = float(closes[idx])
        close_prev = float(closes[idx - 1])
        bb_upper   = float(ind["bb_upper"][idx])
        bb_lower   = float(ind["bb_lower"][idx])
        bb_upper_p = float(ind["bb_upper"][idx - 1])
        bb_lower_p = float(ind["bb_lower"][idx - 1])
        rsi_now    = float(ind["rsi"][idx])
        ema_f      = float(ind["ema_fast"][idx])
        ema_s      = float(ind["ema_slow"][idx])
        atr_now    = float(ind["atr"][idx])
        adx_now    = float(ind["adx"][idx]) if "adx" in ind else 0.0
        if np.isnan(adx_now):
            adx_now = 0.0

        if any(np.isnan([bb_upper, bb_lower, rsi_now, ema_f, ema_s, atr_now])):
            return

        # ── Market Regime Detection ────────────────────────────────────
        regime = None
        regime_strategies = None
        if self.regime_detector:
            try:
                regime = self.regime_detector.detect(self.bars)
                regime_strategies = set(regime.recommended_strategies)
                if regime.regime == "choppy":
                    if self.cfg.show_debug:
                        logger.info("[%s] Market choppy — skipping", self.cfg.symbol)
                    return
                if self.cfg.show_debug:
                    logger.info("[%s] Regime: %s (ADX=%.0f, conf=%.0f%%)",
                                self.cfg.symbol, regime.regime, regime.adx, regime.confidence)
            except Exception as e:
                logger.warning("[%s] Regime detection failed: %s", self.cfg.symbol, e)

        # ── Pre-signal alert ────────────────────────────────────────────
        if self.cfg.enable_pre_signal_alert:
            bb_width = bb_upper - bb_lower
            if bb_width > 0:
                dist_to_upper = (bb_upper - close_now) / bb_width
                dist_to_lower = (close_now - bb_lower) / bb_width

                if dist_to_upper <= (1 - self.cfg.pre_signal_threshold) and not self._pre_alert_sent.get(f"{self.cfg.symbol}_buy"):
                    self.notifier.send_pre_signal_alert(self.cfg.symbol, close_now, bb_upper, "upper", "buy")
                    self._pre_alert_sent[f"{self.cfg.symbol}_buy"] = True
                    self._pre_alert_sent.pop(f"{self.cfg.symbol}_sell", None)

                elif dist_to_lower <= (1 - self.cfg.pre_signal_threshold) and not self._pre_alert_sent.get(f"{self.cfg.symbol}_sell"):
                    self.notifier.send_pre_signal_alert(self.cfg.symbol, close_now, bb_lower, "lower", "sell")
                    self._pre_alert_sent[f"{self.cfg.symbol}_sell"] = True
                    self._pre_alert_sent.pop(f"{self.cfg.symbol}_buy", None)

                else:
                    if dist_to_upper > 0.3:
                        self._pre_alert_sent.pop(f"{self.cfg.symbol}_buy", None)
                    if dist_to_lower > 0.3:
                        self._pre_alert_sent.pop(f"{self.cfg.symbol}_sell", None)

        # Spread guard
        spread_pips = 1.0
        bid, ask = await self.client.get_quote(self.cfg.symbol)
        if bid and ask:
            spread_pips = (ask - bid) / self.symbol_info.pip_size

        if self.cfg.max_spread_pips > 0 and spread_pips > self.cfg.max_spread_pips:
            return

        # ── Multi-timeframe confluence ──────────────────────────────────
        mtf_result = None
        if self.cfg.enable_multi_tf and self.mtf_analyzer:
            try:
                mtf_result = await self.mtf_analyzer.analyze(self.client, self.cfg.symbol, self.cfg)
                if mtf_result["confluence"] < self.cfg.min_tf_confluence:
                    if self.cfg.show_debug:
                        logger.info("[%s] MTF confluence too low: %.0f%% < %.0f%%",
                                    self.cfg.symbol, mtf_result["confluence"], self.cfg.min_tf_confluence)
                    return
            except Exception as e:
                logger.warning("[%s] MTF analysis failed: %s", self.cfg.symbol, e)

        # ── Multi-strategy analysis ─────────────────────────────────────
        best_signal = None
        best_strategy = ""
        strategy_results = []
        if self.strategy_mgr:
            try:
                strategy_results = self.strategy_mgr.run_all(self.bars, self.cfg)
                if strategy_results:
                    best = self.strategy_mgr.get_best_signal(strategy_results)
                    if best:
                        best_signal = best.get("signal")
                        best_strategy = best.get("strategy", "unknown")

                    # Consensus check
                    if self.cfg.require_consensus:
                        consensus = self.strategy_mgr.get_consensus(strategy_results)
                        if consensus:
                            best_signal = consensus.get("signal")
                            best_strategy = f"consensus({consensus.get('strategy', 'unknown')})"
                        else:
                            if self.cfg.show_debug:
                                logger.info("[%s] No strategy consensus", self.cfg.symbol)
                            return
            except Exception as e:
                logger.warning("[%s] Strategy analysis failed: %s", self.cfg.symbol, e)

        # Filter strategies by market regime
        if regime_strategies and strategy_results:
            filtered = [r for r in strategy_results if r.get("strategy") in regime_strategies]
            if filtered:
                strategy_results = filtered
                best = self.strategy_mgr.get_best_signal(filtered)
                if best:
                    best_signal = best.get("signal")
                    best_strategy = best.get("strategy", "unknown")

        # Determine direction to check
        if best_signal:
            directions_to_check = [best_signal]
        else:
            directions_to_check = [TradeDirection.BUY, TradeDirection.SELL]

        # ── Candlestick pattern confirmation ────────────────────────────
        patterns = []
        if self.cfg.enable_candlestick_confirm and HAS_CANDLESTICK:
            try:
                patterns = detect_all_patterns(self.bars[-10:])
            except Exception as e:
                logger.warning("[%s] Candlestick detection failed: %s", self.cfg.symbol, e)

        # ── SMC Analysis ────────────────────────────────────────────────
        smc_result = None
        if self.smc:
            try:
                smc_result = self.smc.analyze(self.bars)
            except Exception as e:
                logger.warning("[%s] SMC analysis failed: %s", self.cfg.symbol, e)

        # ── VWAP Analysis ───────────────────────────────────────────────
        vwap_result = None
        if self.vwap:
            try:
                vwap_result = self.vwap.analyze(self.bars)
            except Exception as e:
                logger.warning("[%s] VWAP analysis failed: %s", self.cfg.symbol, e)

        # ── Divergence Detection ────────────────────────────────────────
        div_result = None
        if self.divergence:
            try:
                rsi_arr = ind.get("rsi", np.array([]))
                div_result = self.divergence.detect_all(closes, rsi_arr)
                if div_result.get("any_bullish") or div_result.get("any_bearish"):
                    logger.info("[%s] Divergence detected: bullish=%s bearish=%s",
                                self.cfg.symbol,
                                div_result.get("any_bullish", False),
                                div_result.get("any_bearish", False))
            except Exception as e:
                logger.warning("[%s] Divergence detection failed: %s", self.cfg.symbol, e)

        # ── FVG Strategy Analysis ──────────────────────────────────────
        fvg_result = None
        if self.fvg_strategy:
            try:
                fvg_result = self.fvg_strategy.analyze(self.bars, self.cfg)
                if fvg_result and fvg_result.get("signal"):
                    logger.info("[%s] FVG signal: %s (conf=%.0f%%)",
                                self.cfg.symbol, fvg_result.get("signal"),
                                fvg_result.get("confidence", 0) * 100)
            except Exception as e:
                logger.warning("[%s] FVG analysis failed: %s", self.cfg.symbol, e)

        # ── ICT Killzones Strategy ──────────────────────────────────────
        ict_result = None
        if self.ict_killzones:
            try:
                ict_result = self.ict_killzones.analyze(self.bars, self.cfg)
                if ict_result and ict_result.get("signal"):
                    logger.info("[%s] ICT Killzone signal: %s (conf=%.0f%%) zone=%s",
                                self.cfg.symbol, ict_result.get("signal"),
                                ict_result.get("confidence", 0) * 100,
                                ict_result.get("killzone", "unknown"))
            except Exception as e:
                logger.warning("[%s] ICT Killzones failed: %s", self.cfg.symbol, e)

        # ── Volume Profile Strategy ────────────────────────────────────
        vp_result = None
        if self.vol_profile:
            try:
                vp_result = self.vol_profile.analyze(self.bars, self.cfg)
                if vp_result and vp_result.get("signal"):
                    logger.info("[%s] Volume Profile signal: %s (conf=%.0f%%)",
                                self.cfg.symbol, vp_result.get("signal"),
                                vp_result.get("confidence", 0) * 100)
            except Exception as e:
                logger.warning("[%s] Volume Profile failed: %s", self.cfg.symbol, e)

        # ── Fibonacci Retracement Levels ───────────────────────────────
        fib_levels = None
        try:
            lookback = min(len(self.bars), 200)
            recent_bars = self.bars[-lookback:]
            fib_high = max(b.high for b in recent_bars)
            fib_low = min(b.low for b in recent_bars)
            fib_levels = calc_fibonacci(fib_high, fib_low)
        except Exception as e:
            logger.warning("[%s] Fibonacci calculation failed: %s", self.cfg.symbol, e)

        # Check directions
        for direction in directions_to_check:
            breakout = self._check_breakout(direction, close_now, close_prev,
                                            bb_upper, bb_lower, bb_upper_p, bb_lower_p)
            if not breakout and not best_signal:
                continue

            if best_signal and not breakout and best_strategy != "consensus":
                continue

            # Candlestick confirmation
            if self.cfg.enable_candlestick_confirm and patterns:
                matching = [p for p in patterns if (p["bullish"] and direction == TradeDirection.BUY) or
                            (not p["bullish"] and direction == TradeDirection.SELL)]
                if matching:
                    strongest = max(matching, key=lambda p: p["strength"])
                    if strongest["strength"] < self.cfg.min_pattern_strength:
                        if self.cfg.show_debug:
                            logger.info("[%s] Pattern too weak: %s (%.1f)", self.cfg.symbol, strongest["pattern"], strongest["strength"])
                        continue

            # Volatility ratio
            if self.cfg.min_volatility_ratio > 0:
                std = float(np.std(closes[-self.cfg.std_dev_period:]))
                if std > 0:
                    ratio = atr_now / std
                    if ratio < self.cfg.min_volatility_ratio:
                        continue

            # Multi-layer filter
            side = "buy" if direction == TradeDirection.BUY else "sell"
            indicators_dict = {
                "rsi": rsi_now,
                "adx": adx_now,
                "close": close_now,
                "ema50": ema_f,
                "ema200": ema_s,
                "spread_pips": spread_pips,
                "max_spread": self.cfg.max_spread_pips,
                "bars": self.bars,
                "bars_h4": bars_h4,
                "time": now_utc,
            }

            result = multi_layer_filter(side, indicators_dict)
            score = result.get("score", 0)
            passed = result.get("pass", False)
            reasons = result.get("reasons", [])

            if not passed:
                logger.info("[%s] Signal rejected: %s (score=%d, reasons=%s)", self.cfg.symbol, side, score, reasons)
                continue

            # Compute SL/TP
            sl_tp = calculate_sl_tp(
                self.cfg, direction=direction, entry_price=close_now,
                atr_value=atr_now, pip_size=self.symbol_info.pip_size,
            )
            if sl_tp is None:
                continue

            # Min SL distance
            if sl_tp.sl_pips < self.cfg.min_sl_pips:
                if direction == TradeDirection.BUY:
                    new_sl_price = close_now - self.cfg.min_sl_pips * self.symbol_info.pip_size
                else:
                    new_sl_price = close_now + self.cfg.min_sl_pips * self.symbol_info.pip_size
                sl_tp = type(sl_tp)(
                    sl_pips=self.cfg.min_sl_pips, tp_pips=sl_tp.tp_pips,
                    sl_price=new_sl_price, tp_price=sl_tp.tp_price,
                )

            # R:R ratio check
            sl_dist = abs(close_now - sl_tp.sl_price)
            tp_dist = abs(sl_tp.tp_price - close_now)
            rr_ratio = tp_dist / sl_dist if sl_dist > 0 else 0

            if self.cfg.min_rr_ratio > 0 and rr_ratio < self.cfg.min_rr_ratio:
                logger.info("[%s] R:R too low: %.2f < %.2f", self.cfg.symbol, rr_ratio, self.cfg.min_rr_ratio)
                if direction == TradeDirection.BUY:
                    sl_tp = type(sl_tp)(
                        sl_pips=sl_tp.sl_pips,
                        tp_pips=sl_tp.sl_pips * self.cfg.min_rr_ratio,
                        sl_price=sl_tp.sl_price,
                        tp_price=close_now + sl_dist * self.cfg.min_rr_ratio,
                    )
                else:
                    sl_tp = type(sl_tp)(
                        sl_pips=sl_tp.sl_pips,
                        tp_pips=sl_tp.sl_pips * self.cfg.min_rr_ratio,
                        sl_price=sl_tp.sl_price,
                        tp_price=close_now - sl_dist * self.cfg.min_rr_ratio,
                    )
                rr_ratio = self.cfg.min_rr_ratio

            # ── S/R levels ───────────────────────────────────────────────
            sr_text = ""
            if self.cfg.enable_sr_levels and self.sr_calc:
                try:
                    sr_levels = self.sr_calc.calculate(self.bars)
                    sr_text = self.sr_calc.format_for_signal(sr_levels, close_now, self.cfg.symbol)
                except Exception as e:
                    logger.warning("[%s] S/R calculation failed: %s", self.cfg.symbol, e)

            # ── Groq AI analysis ─────────────────────────────────────────
            ai_confidence = 0
            ai_verdict = ""
            ai_reasoning = ""

            if self.ai.enabled:
                try:
                    ai_result = await asyncio.to_thread(
                        self.ai.analyze_signal,
                        symbol=self.cfg.symbol,
                        direction=side,
                        confluence_score=int(score),
                        indicators={
                            "RSI": round(rsi_now, 1),
                            "EMA_fast": round(ema_f, 5),
                            "EMA_slow": round(ema_s, 5),
                            "ADX": round(adx_now, 1),
                            "ATR": round(atr_now, 5),
                            "BB_upper": round(bb_upper, 5),
                            "BB_lower": round(bb_lower, 5),
                        },
                        atr=atr_now, adx=adx_now, spread_pips=spread_pips,
                    )
                    if ai_result:
                        ai_confidence = ai_result.confidence
                        ai_verdict = ai_result.verdict
                        ai_reasoning = ai_result.reasoning

                        ai_min = int(os.environ.get("AI_MIN_CONFIDENCE", "60"))
                        if ai_result.confidence < ai_min:
                            logger.info("[%s] AI rejected: %d%% < %d%%", self.cfg.symbol, ai_result.confidence, ai_min)
                            continue
                        if ai_result.verdict == "WAIT":
                            logger.info("[%s] AI says WAIT", self.cfg.symbol)
                            continue
                except Exception as e:
                    logger.warning("[%s] AI gate failed: %s", self.cfg.symbol, e)

            # ── SMC confirmation bonus ───────────────────────────────────
            smc_text = ""
            if smc_result and smc_result.signal:
                if (smc_result.signal == "buy" and direction == TradeDirection.BUY) or \
                   (smc_result.signal == "sell" and direction == TradeDirection.SELL):
                    score += 10  # SMC alignment bonus
                    smc_text = self.smc.format_for_signal(smc_result, self.cfg.symbol)

            # ── VWAP confirmation bonus ──────────────────────────────────
            vwap_text = ""
            if vwap_result and vwap_result.signal:
                if (vwap_result.signal == "buy" and direction == TradeDirection.BUY) or \
                   (vwap_result.signal == "sell" and direction == TradeDirection.SELL):
                    score += 5  # VWAP alignment bonus
                vwap_text = self.vwap.format_for_signal(vwap_result, self.cfg.symbol)

            # ── FVG confirmation bonus ────────────────────────────────────
            fvg_text = ""
            if fvg_result and fvg_result.get("signal"):
                fvg_sig = fvg_result.get("signal")
                if (fvg_sig == TradeDirection.BUY and direction == TradeDirection.BUY) or \
                   (fvg_sig == TradeDirection.SELL and direction == TradeDirection.SELL):
                    score += 8  # FVG alignment bonus
                    fvg_text = f"📍 FVG: {fvg_result.get('reason', 'FVG entry')}"

            # ── ICT Killzone confirmation bonus ───────────────────────────
            ict_text = ""
            if ict_result and ict_result.get("signal"):
                ict_sig = ict_result.get("signal")
                if (ict_sig == TradeDirection.BUY and direction == TradeDirection.BUY) or \
                   (ict_sig == TradeDirection.SELL and direction == TradeDirection.SELL):
                    score += 7  # ICT Killzone alignment bonus
                    ict_text = f"⏰ ICT Killzone: {ict_result.get('killzone', 'active')} — {ict_result.get('reason', 'liquidity sweep')}"

            # ── Volume Profile confirmation bonus ────────────────────────
            vp_text = ""
            if vp_result and vp_result.get("signal"):
                vp_sig = vp_result.get("signal")
                if (vp_sig == TradeDirection.BUY and direction == TradeDirection.BUY) or \
                   (vp_sig == TradeDirection.SELL and direction == TradeDirection.SELL):
                    score += 6  # Volume Profile alignment bonus
                    vp_text = f"📊 Volume Profile: {vp_result.get('reason', 'VP confirmation')}"

            # ── Fibonacci levels text ────────────────────────────────────
            fib_text = ""
            if fib_levels:
                try:
                    fib_text = (
                        f"📐 Fibonacci Levels:\n"
                        f"  0.0:   {fib_levels[0.0]:.5f}\n"
                        f"  0.382: {fib_levels[0.382]:.5f}\n"
                        f"  0.5:   {fib_levels[0.5]:.5f}\n"
                        f"  0.618: {fib_levels[0.618]:.5f}\n"
                        f"  0.786: {fib_levels[0.786]:.5f}\n"
                        f"  1.0:   {fib_levels[1.0]:.5f}"
                    )
                except Exception:
                    fib_text = ""

            # ── Divergence confirmation ──────────────────────────────────
            div_text = ""
            if div_result:
                if div_result.get("any_bullish") and direction == TradeDirection.BUY:
                    score += 8
                    div_text = "⚡ Bullish Divergence detected"
                elif div_result.get("any_bearish") and direction == TradeDirection.SELL:
                    score += 8
                    div_text = "⚡ Bearish Divergence detected"

            # ── Signal Quality Score ─────────────────────────────────────
            quality = None
            quality_text = ""
            if self.risk_pro:
                try:
                    quality = self.risk_pro.score_signal(
                        indicators={
                            "rsi": rsi_now,
                            "ema_fast": ema_f,
                            "ema_slow": ema_s,
                            "close": close_now,
                            "side": side,
                        },
                        mtf_confluence=mtf_result["confluence"] if mtf_result else 50,
                        ai_confidence=ai_confidence,
                        pattern_count=len(patterns),
                        rr_ratio=rr_ratio,
                        adx=adx_now,
                    )
                    quality_text = f"Quality: {quality.grade} ({quality.score:.0f}/100) — {quality.recommendation}"

                    # Skip low-quality signals
                    if quality.score < 40:
                        logger.info("[%s] Signal quality too low: %.0f (%s)", self.cfg.symbol, quality.score, quality.grade)
                        continue
                except Exception as e:
                    logger.warning("[%s] Quality scoring failed: %s", self.cfg.symbol, e)

            # ── Multi-Level TP ───────────────────────────────────────────
            multi_tp_text = ""
            multi_tp = None
            if self.risk_pro:
                try:
                    multi_tp = self.risk_pro.calculate_multi_tp(
                        entry=close_now, sl_price=sl_tp.sl_price,
                        side=side, pip_size=self.symbol_info.pip_size,
                    )
                    multi_tp_text = self.risk_pro.format_multi_tp(multi_tp, self.cfg.symbol)

                    # Break-even suggestion
                    be = self.risk_pro.calculate_break_even(
                        entry=close_now, sl_price=sl_tp.sl_price,
                        side=side, pip_size=self.symbol_info.pip_size,
                    )
                    multi_tp_text += f"\n💡 BE at {be['trigger_price']:.5f}"
                except Exception as e:
                    logger.warning("[%s] Multi-TP calculation failed: %s", self.cfg.symbol, e)

            # ── Generate signal ID ──────────────────────────────────────
            signal_id = str(uuid.uuid4())[:8]

            # ── Build extra info text ────────────────────────────────────
            extra_parts = []
            if smc_text:
                extra_parts.append(f"🏛️ SMC:\n{smc_text}")
            if vwap_text:
                extra_parts.append(vwap_text)
            if div_text:
                extra_parts.append(div_text)
            if quality_text:
                extra_parts.append(f"⭐ {quality_text}")
            if multi_tp_text:
                extra_parts.append(f"🎯 Multi-TP:\n{multi_tp_text}")
            if regime:
                extra_parts.append(f"📊 Regime: {regime.regime} (ADX={regime.adx:.0f})")
            if fvg_text:
                extra_parts.append(fvg_text)
            if ict_text:
                extra_parts.append(ict_text)
            if vp_text:
                extra_parts.append(vp_text)
            if fib_text:
                extra_parts.append(fib_text)
            extra_text = "\n\n".join(extra_parts) if extra_parts else ""

            # ── SEND SIGNAL TO TELEGRAM ─────────────────────────────────
            strategy_name = best_strategy if best_strategy else "BB Breakout"
            if patterns:
                strongest = max(patterns, key=lambda p: p["strength"])
                strategy_name += f" + {strongest['pattern']}"

            self.notifier.send_signal(
                symbol=self.cfg.symbol,
                side=side,
                entry_price=close_now,
                sl_price=sl_tp.sl_price,
                tp_price=sl_tp.tp_price,
                score=score,
                ai_confidence=ai_confidence,
                rr_ratio=rr_ratio,
                strategy=strategy_name,
                sr_text=sr_text,
                signal_id=signal_id if self.cfg.enable_inline_buttons else "",
            )

            # Send extra analysis as follow-up
            if extra_text:
                self.notifier.send(
                    f"📊 Analysis | {self.cfg.symbol}\n\n{extra_text}"
                )

            # Track signal
            if self.tracker:
                self.tracker.add_signal(
                    signal_id=signal_id,
                    symbol=self.cfg.symbol,
                    side=side,
                    entry=close_now,
                    sl=sl_tp.sl_price,
                    tp=sl_tp.tp_price,
                    bar_time=self._last_bar_ts or time.time(),
                )

            # Update cooldown
            self._last_signal_time[self.cfg.symbol] = now_utc

            # Log to DB
            if self.db:
                try:
                    self.db.log_trade_open(
                        symbol=self.cfg.symbol, side=side,
                        volume_units=0, entry_price=close_now,
                        sl_price=sl_tp.sl_price, tp_price=sl_tp.tp_price,
                        sl_pips=sl_tp.sl_pips, tp_pips=sl_tp.tp_pips,
                        atr=atr_now, adx=adx_now, rsi=rsi_now,
                        label=self.cfg.bot_label,
                    )
                except Exception:
                    pass

            self._daily_signal_count += 1
            self._daily_signals.append({
                "symbol": self.cfg.symbol, "side": side,
                "price": close_now, "sl": sl_tp.sl_price, "tp": sl_tp.tp_price,
                "score": score, "ai_confidence": ai_confidence,
                "rr": rr_ratio, "strategy": strategy_name,
                "signal_id": signal_id,
                "time": now_utc.isoformat(),
                "quality": quality.grade if quality else "N/A",
                "regime": regime.regime if regime else "unknown",
            })

            # AI analysis message
            if self.ai.enabled and ai_reasoning:
                self.notifier.send(
                    f"🤖 AI | {self.cfg.symbol} {side.upper()}\n"
                    f"Confidence: {ai_confidence}%\n{ai_reasoning}"
                )

            logger.info("[%s] SIGNAL SENT: %s @ %.5f | SL=%.1fp TP=%.1fp | R:R=1:%.1f | Score=%.0f | AI=%d%% | Strat=%s | Quality=%s",
                        self.cfg.symbol, side.upper(), close_now,
                        sl_tp.sl_pips, sl_tp.tp_pips, rr_ratio, score, ai_confidence,
                        strategy_name, quality.grade if quality else "N/A")
            break

    # ------------------------------------------------------------------
    #  COOLDOWN HELPERS
    # ------------------------------------------------------------------
    def _is_in_cooldown(self, symbol: str, now: datetime) -> bool:
        last = self._last_signal_time.get(symbol)
        if not last:
            return False
        elapsed = (now - last).total_seconds() / 60
        return elapsed < self.cfg.cooldown_minutes

    def _cooldown_remaining(self, symbol: str, now: datetime) -> float:
        last = self._last_signal_time.get(symbol)
        if not last:
            return 0
        elapsed = (now - last).total_seconds() / 60
        return max(0, self.cfg.cooldown_minutes - elapsed)

    # ------------------------------------------------------------------
    #  BREAKOUT DETECTION
    # ------------------------------------------------------------------
    def _check_breakout(self, direction: TradeDirection,
                        close_now: float, close_prev: float,
                        bb_upper: float, bb_lower: float,
                        bb_upper_p: float, bb_lower_p: float) -> bool:
        pip = self.symbol_info.pip_size
        if direction == TradeDirection.BUY:
            if self.cfg.bb_mode == BreakoutMode.TOUCH_BAND:
                return close_now >= bb_upper and close_prev < bb_upper_p
            if self.cfg.bb_mode == BreakoutMode.PENETRATION_PIPS:
                return close_now >= bb_upper + pip
            return close_now > bb_upper and close_prev <= bb_upper_p
        else:
            if self.cfg.bb_mode == BreakoutMode.TOUCH_BAND:
                return close_now <= bb_lower and close_prev > bb_lower_p
            if self.cfg.bb_mode == BreakoutMode.PENETRATION_PIPS:
                return close_now <= bb_lower - pip
            return close_now < bb_lower and close_prev >= bb_lower_p

    def activate_kill_switch(self, reason: str):
        self._kill_switch_active = True
        logger.error("KILL-SWITCH: %s", reason)
        self.notifier.notify_kill_switch(reason)


# ===========================================================================
#  ENTRY POINT
# ===========================================================================
ALL_SYMBOLS = [
    "XAUUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "EURJPY",
    "USDCAD",
]


def _start_keepalive():
    def _ping():
        while True:
            try:
                port = os.environ.get("PORT", "8080")
                url = f"http://127.0.0.1:{port}/health"
                urllib.request.urlopen(url, timeout=10)
            except Exception:
                pass
            time.sleep(600)
    t = threading.Thread(target=_ping, daemon=True)
    t.start()


async def run_symbol(symbol: str, web_enabled: bool = False, enable_commands: bool = False):
    from config import load_config
    cfg = load_config()
    cfg.symbol = symbol
    if not web_enabled:
        cfg.web_monitor_enabled = False

    # Apply symbol profile
    if HAS_PROFILES:
        apply_profile(cfg, symbol)

    bot = BollingerBreakoutSignalBot(cfg, enable_commands=enable_commands)
    try:
        await bot.run()
    except Exception as e:
        logger.error("[%s] Bot error: %s", symbol, e)


async def run_all_symbols():
    logger.info("🚀 Starting BBPro Signal Bot Ultimate v3 — %d symbols: %s",
                len(ALL_SYMBOLS), ", ".join(ALL_SYMBOLS))

    # Send ONE combined startup message for all symbols
    try:
        from config import load_config
        cfg = load_config()
        from notifications.telegram import create_notifier
        notifier = create_notifier(
            cfg.telegram_bot_token,
            cfg.telegram_chat_id,
            cfg.telegram_enabled,
        )
        # Count total strategies (8 available strategies, ~3-4 enabled per symbol)
        total_strategies = 11  # 8 core + FVG + ICT Killzones + Volume Profile
        notifier.send_startup_message(ALL_SYMBOLS, total_strategies)
    except Exception as e:
        logger.warning("Failed to send combined startup message: %s", e)

    tasks = [
        asyncio.create_task(run_symbol(sym, web_enabled=(i == 0), enable_commands=(i == 0)))
        for i, sym in enumerate(ALL_SYMBOLS)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("[%s] Task failed: %s", ALL_SYMBOLS[i], result)


def main():
    MAX_RETRIES = 10
    RETRY_DELAY = 30

    _start_keepalive()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            asyncio.run(run_all_symbols())
            break
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            break
        except Exception as e:
            logger.exception("Fatal error (attempt %d/%d): %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                logger.info("⏳ Retrying in %d seconds...", RETRY_DELAY)
                time.sleep(RETRY_DELAY)
            else:
                logger.error("Max retries reached. Exiting.")
                sys.exit(1)


if __name__ == "__main__":
    main()
