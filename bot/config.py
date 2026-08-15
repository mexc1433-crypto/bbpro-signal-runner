"""
config.py
==========
BBPro Signal Bot — Configuration (Ultimate Edition)

All credentials loaded from environment variables.
No personal data hardcoded.

New features:
  - Cooldown per symbol
  - R:R ratio enforcement
  - Multi-strategy support
  - Multi-timeframe confluence
  - Signal tracking & expiry
  - Economic calendar
  - Candlestick pattern confirmation
  - Periodic performance reports
"""

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class BreakoutMode(str, Enum):
    TOUCH_BAND       = "touch"
    CLOSE_OUTSIDE    = "close"
    PENETRATION_PIPS = "penetration"


class TradeDirection(str, Enum):
    BUY  = "buy"
    SELL = "sell"


class SizingMode(str, Enum):
    RISK_PERCENT = "risk_percent"
    FIXED_LOTS   = "fixed_lots"


@dataclass
class BotConfig:
    # cTrader Open API
    client_id:     str = ""
    client_secret: str = ""
    access_token:  str = ""
    api_token:     str = ""
    account_id:     str = ""
    host:           str = "demo.ctraderapi.com"
    port:           int = 5035
    symbol:         str = "XAUUSD"
    timeframe:      str = "m30"

    # Signal-only mode (no real trades, just Telegram recommendations)
    signal_only_mode: bool = True

    # ── NEW: Signal cooldown ──────────────────────────────────────────────
    # Minimum minutes between signals for the same symbol
    cooldown_minutes: int = 120

    # ── NEW: Risk:Reward ratio enforcement ─────────────────────────────────
    # Minimum R:R ratio (1.5 = TP must be 1.5x the SL distance)
    min_rr_ratio: float = 1.5

    # ── NEW: Signal expiry ────────────────────────────────────────────────
    # Number of bars before a signal expires if TP/SL not hit
    signal_expiry_bars: int = 48

    # ── NEW: Multi-strategy ────────────────────────────────────────────────
    # Enabled strategies: "breakout", "rsi_reversal", "ema_crossover",
    #                     "sr_bounce", "bb_mean_reversion"
    enabled_strategies: List[str] = field(default_factory=lambda: [
        "breakout", "rsi_reversal", "ema_crossover", "sr_bounce", "bb_mean_reversion"
    ])
    # Require 3+ strategies to agree before sending signal
    require_consensus: bool = False
    min_consensus_count: int = 2

    # ── NEW: Multi-timeframe confluence ───────────────────────────────────
    enable_multi_tf: bool = True
    min_tf_confluence: float = 50.0  # minimum % agreement
    mtf_timeframes: List[str] = field(default_factory=lambda: ["m15", "m30", "h1", "h4"])

    # ── NEW: Candlestick pattern confirmation ──────────────────────────────
    enable_candlestick_confirm: bool = True
    min_pattern_strength: float = 0.5  # 0-1, minimum pattern strength

    # ── NEW: Economic calendar ────────────────────────────────────────────
    enable_economic_calendar: bool = True
    news_blackout_before_min: int = 15
    news_blackout_after_min: int = 30

    # ── NEW: Pre-signal alert ─────────────────────────────────────────────
    enable_pre_signal_alert: bool = True
    # Distance from BB band to trigger pre-signal alert (in % of band width)
    pre_signal_threshold: float = 0.8  # 80% of way to band

    # ── NEW: Performance reports ──────────────────────────────────────────
    enable_daily_report: bool = True
    daily_report_hour_utc: int = 22
    enable_weekly_report: bool = True
    weekly_report_day: int = 5  # Friday

    # ── NEW: Support/Resistance in signal ──────────────────────────────────
    enable_sr_levels: bool = True
    sr_lookback: int = 100

    # ── NEW: Telegram inline buttons ──────────────────────────────────────
    enable_inline_buttons: bool = True

    # Bollinger Bands
    bb_period:             int   = 20
    bb_deviations:         float = 2.0
    bb_mode:               BreakoutMode = BreakoutMode.CLOSE_OUTSIDE
    require_close_confirm: bool  = True

    # RSI
    rsi_period:        int   = 14
    rsi_overbought:    float = 70.0
    rsi_oversold:      float = 30.0
    rsi_exit_long:     float = 75.0
    rsi_exit_short:    float = 25.0
    enable_rsi_filter: bool  = True

    # Trend EMA
    fast_ema_period:     int  = 50
    slow_ema_period:     int  = 200
    enable_trend_filter: bool = True
    require_both_emas:   bool = True

    # ADX
    enable_adx_filter: bool  = True
    min_adx:          float = 25.0
    adx_period:       int   = 14

    # ATR
    atr_period:            int   = 14
    sl_atr_multiplier:     float = 1.5
    tp_atr_multiplier:     float = 2.0
    min_sl_pips:           float = 10.0
    sl_pad_pips:           float = 1.0
    min_volatility_ratio:  float = 1.2
    std_dev_period:        int   = 14
    bot_label:             str   = "BBProSignal"
    show_debug:            bool  = False

    # Sizing (info only in signal-only mode)
    risk_per_trade:    float = 0.5
    sizing_mode:       SizingMode = SizingMode.RISK_PERCENT
    fixed_volume_lots: float = 0.01
    max_volume_lots:   float = 10.0

    # Daily limits
    enable_daily_dd:    bool  = True
    max_daily_loss_pct: float = 3.0
    max_daily_trades:   int   = 0
    max_concurrent_pos: int   = 1

    # Sessions
    enable_session_filter: bool = True
    allow_asian:           bool = False
    allow_london:          bool = True
    allow_new_york:        bool = True
    only_overlap:          bool = False

    # Safety
    max_spread_pips:      float = 3.0
    kill_switch_on_error: bool  = True
    conflict_gate:        bool  = True

    # Friday / News
    trade_on_friday:       bool      = False
    friday_close_hour_utc: int       = 20
    enable_news_filter:    bool      = True
    news_blackout_minutes: int       = 30
    manual_news_times:     List[str] = field(default_factory=list)

    # Telegram
    telegram_enabled:   bool = False
    telegram_bot_token: str  = ""
    telegram_chat_id:   str  = ""

    # Database
    db_enabled: bool = True
    db_path:    str  = "/tmp/bbpro_trades.db"

    # Web Monitor
    web_monitor_enabled: bool = True
    web_monitor_host:    str  = "0.0.0.0"
    web_monitor_port:    int  = int(os.environ.get('PORT', 8080))

    # Bot Loop
    poll_interval_sec:   int   = 30
    warmup_bars:         int   = 300
    magic_label:         str   = "BBProSignal"

    # Volume filter
    enable_volume_filter: bool  = True
    volume_ma_period:     int   = 20
    volume_threshold:     float = 1.2

    # Stochastic
    stoch_k_period: int = 5
    stoch_d_period: int = 3
    stoch_slowing: int = 3
    stoch_overbought: float = 80.0
    stoch_oversold: float = 20.0
    enable_stoch_filter: bool = True

    # MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    enable_macd_filter: bool = False

    # Multi-symbol
    symbols: List[str] = field(default_factory=lambda: ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'EURJPY', 'USDCAD'])
    multi_symbol_mode: bool = True

    @property
    def hostname(self):
        return self.host

    def validate(self):
        errors = []
        if not self.client_id:
            errors.append("client_id not set")
        if not self.client_secret:
            errors.append("client_secret not set")
        if not self.access_token:
            errors.append("access_token not set")
        return errors


def load_config() -> BotConfig:
    """Load config from environment variables."""
    cfg = BotConfig()

    # cTrader credentials
    cfg.client_id = (
        os.environ.get('CTRADER_CLIENT_ID_3')
        or os.environ.get('CTRADER_CLIENT_ID')
        or ''
    ).strip()

    cfg.client_secret = (
        os.environ.get('CTRADER_SECRET_4')
        or os.environ.get('CTRADER_SECRET')
        or ''
    ).strip()

    cfg.access_token = (
        os.environ.get('CTRADER_ACCESS_TOKEN_2')
        or os.environ.get('CTRADER_ACCESS_TOKEN')
        or os.environ.get('CTRADER_API_TOKEN')
        or ''
    ).strip()

    cfg.api_token = (
        os.environ.get('CTRADER_API_TOKEN')
        or os.environ.get('CTRADER_ACCESS_TOKEN_2')
        or ''
    ).strip()

    cfg.account_id = os.environ.get('CTRADER_ACCOUNT_ID', '').strip()

    # Telegram
    cfg.telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    cfg.telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        cfg.telegram_enabled = True

    # Database
    db_env = os.environ.get('DB_ENABLED', 'true').strip().lower()
    cfg.db_enabled = db_env != 'false'
    cfg.db_path = os.environ.get('DB_PATH', '/tmp/bbpro_trades.db').strip() or '/tmp/bbpro_trades.db'

    # Signal-only mode
    cfg.signal_only_mode = os.environ.get('SIGNAL_ONLY_MODE', 'true').strip().lower() != 'false'

    # ── NEW: Load extended config from env ────────────────────────────────
    cfg.cooldown_minutes = int(os.environ.get('COOLDOWN_MINUTES', '120'))
    cfg.min_rr_ratio = float(os.environ.get('MIN_RR_RATIO', '1.5'))
    cfg.signal_expiry_bars = int(os.environ.get('SIGNAL_EXPIRY_BARS', '48'))
    cfg.require_consensus = os.environ.get('REQUIRE_CONSENSUS', 'false').strip().lower() == 'true'
    cfg.min_consensus_count = int(os.environ.get('MIN_CONSENSUS', '2'))
    cfg.enable_multi_tf = os.environ.get('ENABLE_MTF', 'true').strip().lower() != 'false'
    cfg.min_tf_confluence = float(os.environ.get('MIN_TF_CONFLUENCE', '50'))
    cfg.enable_candlestick_confirm = os.environ.get('ENABLE_CANDLESTICK', 'true').strip().lower() != 'false'
    cfg.enable_economic_calendar = os.environ.get('ENABLE_ECON_CAL', 'true').strip().lower() != 'false'
    cfg.enable_pre_signal_alert = os.environ.get('ENABLE_PRE_SIGNAL', 'true').strip().lower() != 'false'
    cfg.enable_daily_report = os.environ.get('ENABLE_DAILY_REPORT', 'true').strip().lower() != 'false'
    cfg.enable_sr_levels = os.environ.get('ENABLE_SR_LEVELS', 'true').strip().lower() != 'false'
    cfg.enable_inline_buttons = os.environ.get('ENABLE_INLINE_BUTTONS', 'true').strip().lower() != 'false'

    return cfg


DEFAULT_CONFIG = load_config()
