"""
news_trading.py — News Trading Strategy for BBPro Signal Bot
===========================================================
High-impact economic news event strategy with pre-news volatility caution
and post-news momentum/breakout signal generation.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np

try:
    from config import TradeDirection, BotConfig
except ImportError:
    from .config import TradeDirection, BotConfig

try:
    from economic_calendar import EconomicCalendar
except ImportError:
    try:
        from .economic_calendar import EconomicCalendar
    except ImportError:
        EconomicCalendar = None

try:
    import indicators
except ImportError:
    from . import indicators


logger = logging.getLogger(__name__)


def _get_pip_size(symbol: str) -> float:
    """Returns pip size based on symbol convention."""
    s = symbol.upper()
    pip_map = {
        "XAUUSD": 0.1,
        "XAGUSD": 0.01,
        "USDJPY": 0.01,
        "EURJPY": 0.01,
        "GBPJPY": 0.01,
        "AUDJPY": 0.01,
        "CADJPY": 0.01,
        "CHFJPY": 0.01,
        "NZDJPY": 0.01,
    }
    if s in pip_map:
        return pip_map[s]
    if "JPY" in s or "XAG" in s:
        return 0.01
    if "XAU" in s:
        return 0.1
    if "BTC" in s or "ETH" in s:
        return 1.0
    return 0.0001


def _extract_ohlcv(bars):
    """Safely extracts OHLCV arrays and timestamps from various bar data formats."""
    timestamps = []

    if isinstance(bars, np.ndarray):
        if bars.ndim == 2 and bars.shape[1] >= 5:
            return bars[:, 0], bars[:, 1], bars[:, 2], bars[:, 3], bars[:, 4], []
        closes = bars.astype(float)
        return closes, closes, closes, closes, np.ones_like(closes), []

    if not bars:
        empty = np.array([], dtype=float)
        return empty, empty, empty, empty, empty, []

    opens, highs, lows, closes, volumes = [], [], [], [], []
    for b in bars:
        if hasattr(b, "open"):
            opens.append(float(getattr(b, "open", 0.0)))
            highs.append(float(getattr(b, "high", 0.0)))
            lows.append(float(getattr(b, "low", 0.0)))
            closes.append(float(getattr(b, "close", 0.0)))
            volumes.append(float(getattr(b, "volume", 1.0)))
            timestamps.append(float(getattr(b, "timestamp", 0.0)))
        elif isinstance(b, dict):
            opens.append(float(b.get("open", 0.0)))
            highs.append(float(b.get("high", 0.0)))
            lows.append(float(b.get("low", 0.0)))
            closes.append(float(b.get("close", 0.0)))
            volumes.append(float(b.get("volume", 1.0)))
            timestamps.append(float(b.get("timestamp", b.get("time", 0.0))))
        else:
            val = float(b)
            opens.append(val)
            highs.append(val)
            lows.append(val)
            closes.append(val)
            volumes.append(1.0)

    return (
        np.array(opens, dtype=float),
        np.array(highs, dtype=float),
        np.array(lows, dtype=float),
        np.array(closes, dtype=float),
        np.array(volumes, dtype=float),
        timestamps
    )


class NewsTradingStrategy:
    """
    News Trading Strategy for BBPro Signal Bot.

    Pre-news: Issue caution alert / signal=None when within 15 min before high-impact economic news.
    Post-news: Evaluate volatility ratio (ATR spike) and candle body size surge within 30 min
               after news releases to generate directional BUY/SELL momentum signals.
    """

    def __init__(self, calendar=None, name="news_trading"):
        self.name = name
        if calendar is not None:
            self.calendar = calendar
        elif EconomicCalendar is not None:
            self.calendar = EconomicCalendar()
        else:
            self.calendar = None

    def _check_news_window(self, symbol, current_time, pre_minutes=15, post_minutes=30):
        """Check if current_time falls within a pre-news or post-news window."""
        if self.calendar is None:
            return {"status": "none", "event": None, "minutes_diff": 0.0, "description": ""}

        currency_map = getattr(self.calendar, "CURRENCY_MAP", {
            "XAUUSD": ["USD"], "EURUSD": ["EUR", "USD"], "GBPUSD": ["GBP", "USD"],
            "USDJPY": ["USD", "JPY"], "EURJPY": ["EUR", "JPY"], "USDCAD": ["USD", "CAD"],
        })
        currencies = currency_map.get(symbol.upper(), ["USD"])

        events_cache = getattr(self.calendar, "_events_cache", [])
        if not events_cache and hasattr(self.calendar, "_get_recurring_events"):
            events = self.calendar._get_recurring_events()
        else:
            events = events_cache

        if not events and hasattr(self.calendar, "_get_recurring_events"):
            events = self.calendar._get_recurring_events()

        pre_event = None
        post_event = None
        min_pre_diff = 0.0
        min_post_diff = 0.0

        for event in events:
            ev_currency = event.get("currency", "")
            if ev_currency not in currencies:
                continue
            if event.get("impact", "high") != "high":
                continue

            try:
                ev_time_str = str(event.get("time", ""))
                ev_dt = datetime.fromisoformat(ev_time_str.replace("Z", "+00:00"))
                if ev_dt.tzinfo is None:
                    ev_dt = ev_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            diff_mins = (current_time - ev_dt).total_seconds() / 60.0

            if -pre_minutes <= diff_mins < 0:
                if pre_event is None or abs(diff_mins) < abs(min_pre_diff):
                    pre_event = event
                    min_pre_diff = diff_mins
            elif 0 <= diff_mins <= post_minutes:
                if post_event is None or diff_mins < min_post_diff:
                    post_event = event
                    min_post_diff = diff_mins

        if pre_event is not None:
            title = pre_event.get("title", "High-Impact Event")
            curr = pre_event.get("currency", "")
            return {"status": "pre_news", "event": pre_event, "minutes_diff": min_pre_diff,
                    "description": f"{title} ({curr})"}

        if post_event is not None:
            title = post_event.get("title", "High-Impact Event")
            curr = post_event.get("currency", "")
            return {"status": "post_news", "event": post_event, "minutes_diff": min_post_diff,
                    "description": f"{title} ({curr})"}

        return {"status": "none", "event": None, "minutes_diff": 0.0, "description": ""}

    def analyze(self, bars, cfg=None, indicators_dict=None):
        """Analyze price action for pre-news caution and post-news breakout signals."""
        try:
            cfg = cfg or BotConfig()
            enabled = getattr(cfg, "news_trading_enabled", getattr(cfg, "enable_news_trading", True))
            if not enabled:
                return {"strategy": self.name, "signal": None, "confidence": 0.0,
                        "reason": "News trading strategy disabled in config", "sl_pips": 0.0, "tp_pips": 0.0}

            lookback = int(getattr(cfg, "news_trading_lookback_bars", 20))
            atr_multiplier = float(getattr(cfg, "news_trading_atr_multiplier", 1.5))
            body_multiplier = float(getattr(cfg, "news_trading_body_multiplier", 2.0))
            pre_minutes = int(getattr(cfg, "news_blackout_before_min", getattr(cfg, "news_trading_pre_minutes", 15)))
            post_minutes = int(getattr(cfg, "news_blackout_after_min", getattr(cfg, "news_trading_post_minutes", 30)))
            symbol = str(getattr(cfg, "symbol", "XAUUSD"))

            opens, highs, lows, closes, volumes, timestamps = _extract_ohlcv(bars)

            if len(closes) < 5:
                return {"strategy": self.name, "signal": None, "confidence": 0.0,
                        "reason": "Insufficient bar data for news trading strategy", "sl_pips": 0.0, "tp_pips": 0.0}

            current_time = datetime.now(timezone.utc)
            if timestamps and timestamps[-1] > 1000000:
                try:
                    current_time = datetime.fromtimestamp(timestamps[-1], tz=timezone.utc)
                except Exception:
                    pass

            window_info = self._check_news_window(symbol, current_time, pre_minutes, post_minutes)
            status = window_info.get("status", "none")
            news_desc = window_info.get("description", "High-Impact News")

            # PRE-NEWS: caution
            if status == "pre_news":
                return {"strategy": self.name, "signal": None, "confidence": 0.0,
                        "reason": "High-impact news approaching - caution",
                        "sl_pips": 0.0, "tp_pips": 0.0, "news_event": news_desc}

            # POST-NEWS: momentum analysis
            if status == "post_news":
                try:
                    if indicators_dict and "atr" in indicators_dict and isinstance(indicators_dict["atr"], np.ndarray):
                        atr_series = indicators_dict["atr"]
                    else:
                        atr_series = indicators.atr(highs, lows, closes, period=14)
                    curr_atr = float(atr_series[-1])
                    if np.isnan(curr_atr) or curr_atr <= 0:
                        curr_atr = float(np.mean(highs[-14:] - lows[-14:]))
                except Exception:
                    curr_atr = float(np.mean(highs[-14:] - lows[-14:]))

                try:
                    valid_atrs = [float(a) for a in atr_series[-lookback:] if not np.isnan(a) and a > 0]
                    avg_atr = float(np.mean(valid_atrs)) if valid_atrs else curr_atr
                except Exception:
                    avg_atr = curr_atr

                atr_ratio = curr_atr / max(avg_atr, 1e-6)

                bodies = np.abs(closes - opens)
                curr_body = float(bodies[-1])
                avg_body_slice = bodies[-lookback-1:-1] if len(bodies) > 1 else bodies
                avg_body = float(np.mean(avg_body_slice)) if len(avg_body_slice) > 0 else curr_body
                body_ratio = curr_body / max(avg_body, 1e-6)

                curr_vol = float(volumes[-1])
                avg_vol_slice = volumes[-lookback-1:-1] if len(volumes) > 1 else volumes
                avg_vol = float(np.mean(avg_vol_slice)) if len(avg_vol_slice) > 0 else curr_vol
                volume_spike = (curr_vol >= avg_vol * 1.5) if avg_vol > 0 else False

                strong_momentum = (body_ratio >= body_multiplier) and (atr_ratio >= atr_multiplier)

                if strong_momentum:
                    curr_open = float(opens[-1])
                    curr_close = float(closes[-1])
                    is_bullish = curr_close > curr_open
                    is_bearish = curr_close < curr_open

                    if is_bullish:
                        signal = TradeDirection.BUY
                    elif is_bearish:
                        signal = TradeDirection.SELL
                    else:
                        signal = None

                    if signal is not None:
                        confidence = 60.0
                        if atr_ratio >= 2.0:
                            confidence += 15.0
                        if body_ratio >= 3.0:
                            confidence += 10.0
                        if volume_spike:
                            confidence += 15.0
                        confidence = round(min(100.0, max(0.0, confidence)), 2)

                        pip_sz = _get_pip_size(symbol)
                        sl_pips = round((2.0 * curr_atr) / pip_sz, 1)
                        tp_pips = round((1.5 * curr_atr) / pip_sz, 1)

                        side_label = "BUY" if is_bullish else "SELL"
                        reason = (f"Post-news {side_label} momentum: Candle body {body_ratio:.2f}x avg "
                                  f"(>={body_multiplier}x), ATR spike {atr_ratio:.2f}x avg (>={atr_multiplier}x)")
                        if volume_spike:
                            reason += f", Volume spike detected ({curr_vol/max(avg_vol, 1e-6):.2f}x avg)"

                        return {"strategy": self.name, "signal": signal, "confidence": confidence,
                                "reason": reason, "sl_pips": sl_pips, "tp_pips": tp_pips,
                                "news_event": news_desc}

                return {"strategy": self.name, "signal": None, "confidence": 0.0,
                        "reason": f"Post-news window active for {news_desc} but momentum criteria not met "
                                  f"(body ratio {body_ratio:.2f}x vs required {body_multiplier}x, "
                                  f"ATR ratio {atr_ratio:.2f}x vs required {atr_multiplier}x)",
                        "sl_pips": 0.0, "tp_pips": 0.0, "news_event": news_desc}

            return {"strategy": self.name, "signal": None, "confidence": 0.0,
                    "reason": "No high-impact news event active in news window",
                    "sl_pips": 0.0, "tp_pips": 0.0}

        except Exception as e:
            logger.error("Error in NewsTradingStrategy.analyze: %s", e, exc_info=True)
            return {"strategy": self.name, "signal": None, "confidence": 0.0,
                    "reason": f"News trading strategy error: {e}",
                    "sl_pips": 0.0, "tp_pips": 0.0}

    def run(self, bars, cfg=None):
        """Wrapper method matching strategy manager interface."""
        return self.analyze(bars, cfg)
