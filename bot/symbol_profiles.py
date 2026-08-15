"""
symbol_profiles.py — Per-Symbol Configuration Profiles
========================================================
Each symbol has different volatility, spread, and behavior.
This module provides tuned settings per symbol.
"""

SYMBOL_PROFILES = {
    "XAUUSD": {
        "name": "Gold",
        "timeframe": "m30",
        "bb_period": 20,
        "bb_deviations": 2.0,
        "sl_atr_multiplier": 2.0,
        "tp_atr_multiplier": 3.0,
        "max_spread_pips": 5.0,
        "min_adx": 20.0,
        "cooldown_minutes": 120,
        "min_rr_ratio": 1.5,
        "strategies": ["breakout", "rsi_reversal", "sr_bounce", "bb_mean_reversion"],
        "pip_size": 0.1,
    },
    "EURUSD": {
        "name": "Euro/USD",
        "timeframe": "m30",
        "bb_period": 20,
        "bb_deviations": 2.0,
        "sl_atr_multiplier": 1.5,
        "tp_atr_multiplier": 2.0,
        "max_spread_pips": 2.0,
        "min_adx": 25.0,
        "cooldown_minutes": 90,
        "min_rr_ratio": 1.5,
        "strategies": ["breakout", "ema_crossover", "rsi_reversal"],
        "pip_size": 0.0001,
    },
    "GBPUSD": {
        "name": "Pound/USD",
        "timeframe": "m30",
        "bb_period": 20,
        "bb_deviations": 2.0,
        "sl_atr_multiplier": 2.0,
        "tp_atr_multiplier": 2.5,
        "max_spread_pips": 3.0,
        "min_adx": 22.0,
        "cooldown_minutes": 90,
        "min_rr_ratio": 1.5,
        "strategies": ["breakout", "rsi_reversal", "sr_bounce", "bb_mean_reversion"],
        "pip_size": 0.0001,
    },
    "USDJPY": {
        "name": "USD/Yen",
        "timeframe": "m30",
        "bb_period": 20,
        "bb_deviations": 2.0,
        "sl_atr_multiplier": 1.5,
        "tp_atr_multiplier": 2.0,
        "max_spread_pips": 3.0,
        "min_adx": 25.0,
        "cooldown_minutes": 90,
        "min_rr_ratio": 1.5,
        "strategies": ["breakout", "ema_crossover", "rsi_reversal"],
        "pip_size": 0.01,
    },
    "EURJPY": {
        "name": "Euro/Yen",
        "timeframe": "m30",
        "bb_period": 20,
        "bb_deviations": 2.0,
        "sl_atr_multiplier": 2.0,
        "tp_atr_multiplier": 2.5,
        "max_spread_pips": 4.0,
        "min_adx": 22.0,
        "cooldown_minutes": 100,
        "min_rr_ratio": 1.5,
        "strategies": ["breakout", "sr_bounce", "rsi_reversal"],
        "pip_size": 0.01,
    },
    "USDCAD": {
        "name": "USD/CAD",
        "timeframe": "m30",
        "bb_period": 20,
        "bb_deviations": 2.0,
        "sl_atr_multiplier": 1.5,
        "tp_atr_multiplier": 2.0,
        "max_spread_pips": 3.0,
        "min_adx": 25.0,
        "cooldown_minutes": 90,
        "min_rr_ratio": 1.5,
        "strategies": ["breakout", "ema_crossover", "rsi_reversal"],
        "pip_size": 0.0001,
    },
}

DEFAULT_PROFILE = {
    "name": "Unknown",
    "timeframe": "m30",
    "bb_period": 20,
    "bb_deviations": 2.0,
    "sl_atr_multiplier": 1.5,
    "tp_atr_multiplier": 2.0,
    "max_spread_pips": 3.0,
    "min_adx": 25.0,
    "cooldown_minutes": 120,
    "min_rr_ratio": 1.5,
    "strategies": ["breakout", "rsi_reversal", "ema_crossover"],
    "pip_size": 0.0001,
}


def get_profile(symbol: str) -> dict:
    """Get the profile for a symbol, or return default."""
    return SYMBOL_PROFILES.get(symbol.upper(), DEFAULT_PROFILE)


def apply_profile(cfg, symbol: str):
    """Apply symbol-specific settings to a BotConfig instance."""
    profile = get_profile(symbol)

    cfg.symbol = symbol
    cfg.timeframe = profile.get("timeframe", cfg.timeframe)
    cfg.bb_period = profile.get("bb_period", cfg.bb_period)
    cfg.bb_deviations = profile.get("bb_deviations", cfg.bb_deviations)
    cfg.sl_atr_multiplier = profile.get("sl_atr_multiplier", cfg.sl_atr_multiplier)
    cfg.tp_atr_multiplier = profile.get("tp_atr_multiplier", cfg.tp_atr_multiplier)
    cfg.max_spread_pips = profile.get("max_spread_pips", cfg.max_spread_pips)
    cfg.min_adx = profile.get("min_adx", cfg.min_adx)
    cfg.cooldown_minutes = profile.get("cooldown_minutes", cfg.cooldown_minutes)
    cfg.min_rr_ratio = profile.get("min_rr_ratio", cfg.min_rr_ratio)

    strategies = profile.get("strategies", [])
    if strategies:
        cfg.enabled_strategies = strategies

    return cfg
