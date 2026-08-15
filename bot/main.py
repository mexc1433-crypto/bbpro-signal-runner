"""
main.py
=======
BBPro Signal Bot — Ultimate Edition

Signal-only bot that sends trade recommendations via Telegram.

Features:
  1. Cooldown per symbol (prevent spam)
  2. R:R ratio enforcement (auto-reject if < 1.5)
  3. Signal tracking (WIN/LOSS/EXPIRED)
  4. Inline Telegram buttons
  5. Candlestick pattern confirmation
  6. Multi-strategy support (BB, RSI, EMA, S/R, Mean Reversion)
  7. Multi-timeframe confluence
  8. Signal expiry
  9. Support/Resistance levels in signal
 10. Economic calendar integration
 11. Symbol-specific profiles
 13. Pre-signal alerts
 15. Daily/weekly performance reports

No real orders are placed. The human takes the decision.
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
from indicators import compute_all_indicators
from filters import multi_layer_filter, parse_news_times, should_close_all_on_friday
from risk_manager import calculate_sl_tp, DailyState, check_daily_reset
from ctrader_client import CTraderClient, SymbolInfo, Bar
from notifications.telegram import create_notifier
from groq_analyzer import GroqAnalyzer
from storage.database import TradeDB
from analytics.performance import PerformanceAnalyzer

# Optional imports for new features
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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BBProSignal")


class BollingerBreakoutSignalBot:
    """Signal-only bot — Ultimate Edition."""

    def __init__(self, cfg: Optional[BotConfig] = None):
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

        # ── NEW: Cooldown tracking ────────────────────────────────────────
        self._last_signal_time: Dict[str, datetime] = {}

        # ── NEW: Pre-signal alert tracking ────────────────────────────────
        self._pre_alert_sent: Dict[str, bool] = {}

        # ── NEW: Components ────────────────────────────────────────────────
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

        # Daily report tracking
        self._last_report_date: Optional[str] = None

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
        logger.info("BBPro Signal Bot — ULTIMATE Edition")
        logger.info("=" * 70)
        logger.info("Symbol: %s | TF: %s | Mode: SIGNAL ONLY", self.cfg.symbol, self.cfg.timeframe)
        logger.info("Strategies: %s", ", ".join(self.cfg.enabled_strategies) if self.cfg.enabled_strategies else "none")
        logger.info("Features: Cooldown=%dm | R:R≥%.1f | MTF=%s | Candlestick=%s | EconCal=%s",
                    self.cfg.cooldown_minutes, self.cfg.min_rr_ratio,
                    self.cfg.enable_multi_tf, self.cfg.enable_candlestick_confirm,
                    self.cfg.enable_economic_calendar)
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

        # Telegram start notification (first symbol only)
        if self.cfg.telegram_enabled:
            self.notifier.send_startup_message([self.cfg.symbol])

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

        # ── NEW: Daily report ─────────────────────────────────────────────
        if self.cfg.enable_daily_report and self._last_report_date != now_utc.strftime("%Y-%m-%d"):
            if now_utc.hour >= self.cfg.daily_report_hour_utc:
                self._last_report_date = now_utc.strftime("%Y-%m-%d")
                if self.reporter and self.tracker:
                    stats = self.tracker.get_stats()
                    stats["pending"] = len(self.tracker.get_active())
                    self.notifier.send_daily_report(stats)

        # ── NEW: Check signal tracking results ────────────────────────────
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

        # ── NEW: Economic calendar check ──────────────────────────────────
        if self.econ_cal:
            try:
                is_blackout, reason = self.econ_cal.is_blackout(self.cfg.symbol)
                if is_blackout:
                    if self.cfg.show_debug:
                        logger.info("[%s] Economic blackout: %s", self.cfg.symbol, reason)
                    return
            except Exception as e:
                logger.warning("[%s] Econ calendar error: %s", self.cfg.symbol, e)

        # Friday close
        if should_close_all_on_friday(now=now_utc):
            return

        # New bar check
        if await self._check_new_bar():
            await self._on_bar_close(now_utc)

    # ------------------------------------------------------------------
    #  NEW-BAR DETECTION (FIXED)
    # ------------------------------------------------------------------
    async def _check_new_bar(self) -> bool:
        if not self.symbol_info:
            return False
        new_bars = await self.client.get_recent_bars(
            self.cfg.symbol, self.cfg.timeframe, count=2
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
                    self.bars = self.bars[:-1] + new_bars[-1:]
            else:
                self.bars = list(new_bars)

            max_window = max(self.cfg.slow_ema_period, 500)
            if len(self.bars) > max_window * 2:
                self.bars = self.bars[-max_window * 2:]
            self._last_bar_ts = latest_ts
            return True
        return False

    # ------------------------------------------------------------------
    #  BAR-CLOSE EVALUATION — Ultimate Signal Detection
    # ------------------------------------------------------------------
    async def _on_bar_close(self, now_utc: datetime) -> None:
        if len(self.bars) < max(self.cfg.bb_period, self.cfg.slow_ema_period, self.cfg.atr_period) + 5:
            return

        if self._kill_switch_active:
            return

        # ── NEW: Cooldown check ──────────────────────────────────────────
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

        # ── NEW: Pre-signal alert ────────────────────────────────────────
        if self.cfg.enable_pre_signal_alert:
            bb_width = bb_upper - bb_lower
            if bb_width > 0:
                # Check if price is approaching bands
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
                    # Reset if price moves away from bands
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

        # ── NEW: Multi-timeframe confluence ──────────────────────────────
        mtf_result = None
        if self.cfg.enable_multi_tf and self.mtf_analyzer:
            try:
                mtf_result = await self.mtf_analyzer.analyze(self.client, self.cfg.symbol, self.cfg)
                if mtf_result["confluence"] < self.cfg.min_tf_confluence:
                    if self.cfg.show_debug:
                        logger.info("[%s] MTF confluence too low: %.0f%%", self.cfg.symbol, mtf_result["confluence"])
                    return
                if mtf_result["direction"] == "neutral":
                    if self.cfg.show_debug:
                        logger.info("[%s] MTF neutral", self.cfg.symbol)
                    return
            except Exception as e:
                logger.warning("[%s] MTF analysis failed: %s", self.cfg.symbol, e)

        # ── NEW: Run multi-strategy ───────────────────────────────────────
        best_signal = None
        best_score = 0
        best_strategy = ""
        consensus_direction = None

        if HAS_STRATEGIES and self.strategy_mgr:
            try:
                results = self.strategy_mgr.run_all(self.bars, self.cfg)
                if results:
                    # Check for consensus
                    buy_count = sum(1 for r in results if r.get("signal") == TradeDirection.BUY)
                    sell_count = sum(1 for r in results if r.get("signal") == TradeDirection.SELL)

                    if buy_count >= self.cfg.min_consensus_count and buy_count > sell_count:
                        consensus_direction = TradeDirection.BUY
                    elif sell_count >= self.cfg.min_consensus_count and sell_count > buy_count:
                        consensus_direction = TradeDirection.SELL

                    if self.cfg.require_consensus and not consensus_direction:
                        return

                    # Get best signal
                    best = self.strategy_mgr.get_best_signal(results)
                    if best and best.get("signal"):
                        best_signal = best["signal"]
                        best_score = best.get("confidence", 0)
                        best_strategy = best.get("strategy", "")
                    elif consensus_direction:
                        best_signal = consensus_direction
                        best_score = max(buy_count, sell_count) * 20
                        best_strategy = "consensus"
            except Exception as e:
                logger.warning("[%s] Strategy manager failed: %s", self.cfg.symbol, e)

        # Determine direction: use strategy manager or fallback to BB breakout
        directions_to_check = []
        if best_signal:
            directions_to_check = [best_signal]
        else:
            # Fallback: check both directions with BB breakout
            directions_to_check = [TradeDirection.BUY, TradeDirection.SELL]

        # ── NEW: Candlestick pattern confirmation ────────────────────────
        patterns = []
        if self.cfg.enable_candlestick_confirm and HAS_CANDLESTICK:
            try:
                patterns = detect_all_patterns(self.bars[-10:])
            except Exception as e:
                logger.warning("[%s] Candlestick detection failed: %s", self.cfg.symbol, e)

        # Check directions
        for direction in directions_to_check:
            breakout = self._check_breakout(direction, close_now, close_prev,
                                            bb_upper, bb_lower, bb_upper_p, bb_lower_p)
            if not breakout and not best_signal:
                continue

            # Use best_signal from strategy manager even without BB breakout
            if best_signal and not breakout and best_strategy != "consensus":
                continue

            # ── NEW: Candlestick confirmation ─────────────────────────────
            if self.cfg.enable_candlestick_confirm and patterns:
                matching = [p for p in patterns if (p["bullish"] and direction == TradeDirection.BUY) or
                            (not p["bullish"] and direction == TradeDirection.SELL)]
                if matching:
                    strongest = max(matching, key=lambda p: p["strength"])
                    if strongest["strength"] < self.cfg.min_pattern_strength:
                        if self.cfg.show_debug:
                            logger.info("[%s] Pattern too weak: %s (%.1f)", self.cfg.symbol, strongest["pattern"], strongest["strength"])
                        continue
                else:
                    if self.cfg.show_debug:
                        logger.info("[%s] No matching candlestick pattern", self.cfg.symbol)
                    # Don't skip — patterns are confirmation, not hard requirement

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

            # ── NEW: R:R ratio check ──────────────────────────────────────
            sl_dist = abs(close_now - sl_tp.sl_price)
            tp_dist = abs(sl_tp.tp_price - close_now)
            rr_ratio = tp_dist / sl_dist if sl_dist > 0 else 0

            if self.cfg.min_rr_ratio > 0 and rr_ratio < self.cfg.min_rr_ratio:
                logger.info("[%s] R:R too low: %.2f < %.2f", self.cfg.symbol, rr_ratio, self.cfg.min_rr_ratio)
                # Adjust TP to meet minimum R:R
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

            # ── NEW: Support/Resistance levels ─────────────────────────────
            sr_text = ""
            if self.cfg.enable_sr_levels and self.sr_calc:
                try:
                    sr_levels = self.sr_calc.calculate(self.bars)
                    sr_text = self.sr_calc.format_for_signal(sr_levels, close_now, self.cfg.symbol)
                except Exception as e:
                    logger.warning("[%s] S/R calculation failed: %s", self.cfg.symbol, e)

            # ── NEW: Groq AI analysis ──────────────────────────────────────
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

            # ── NEW: Generate signal ID ───────────────────────────────────
            signal_id = str(uuid.uuid4())[:8]

            # ── SEND SIGNAL TO TELEGRAM ────────────────────────────────────
            # Include strategy name in the message
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

            # ── NEW: Track signal ──────────────────────────────────────────
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

            # ── NEW: Update cooldown ──────────────────────────────────────
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
            })

            # AI analysis message
            if self.ai.enabled and ai_reasoning:
                self.notifier.send(
                    f"📊 AI | {self.cfg.symbol} {side.upper()}\n"
                    f"Confidence: {ai_confidence}%\n{ai_reasoning}"
                )

            logger.info("[%s] SIGNAL SENT: %s @ %.5f | SL=%.1fp TP=%.1fp | R:R=1:%.1f | Score=%.0f | AI=%d%% | Strat=%s",
                        self.cfg.symbol, side.upper(), close_now,
                        sl_tp.sl_pips, sl_tp.tp_pips, rr_ratio, score, ai_confidence, strategy_name)
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


async def run_symbol(symbol: str, web_enabled: bool = False):
    from config import load_config
    cfg = load_config()
    cfg.symbol = symbol
    if not web_enabled:
        cfg.web_monitor_enabled = False

    # Apply symbol profile
    if HAS_PROFILES:
        apply_profile(cfg, symbol)

    bot = BollingerBreakoutSignalBot(cfg)
    try:
        await bot.run()
    except Exception as e:
        logger.error("[%s] Bot error: %s", symbol, e)


async def run_all_symbols():
    logger.info("🚀 Starting BBPro Signal Bot Ultimate — %d symbols: %s",
                len(ALL_SYMBOLS), ", ".join(ALL_SYMBOLS))
    tasks = [
        asyncio.create_task(run_symbol(sym, web_enabled=(i == 0)))
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
