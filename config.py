"""
صياد الشمعات | Candle Hunter - Configuration
إعدادات البوت الرئيسية - مخصص لـ XAU/USD (الذهب)
"""
import os
from dotenv import load_dotenv
from typing import List, Dict, Any

load_dotenv()

# ═══════════════════════════════════════════════════════════════
# Telegram Configuration
# ═══════════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PUBLIC_CHANNEL_ID = os.getenv("PUBLIC_CHANNEL_ID", "")
PRIVATE_CHANNEL_ID = os.getenv("PRIVATE_CHANNEL_ID", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ═══════════════════════════════════════════════════════════════
# Data Source Configuration
# ═══════════════════════════════════════════════════════════════
# مصدر البيانات الرئيسي: MEXC (XAU/USDT:USDT) — لحظي 100%
# Yahoo Finance كـ fallback + مؤشرات السوق (VIX, DXY)
DATA_SOURCE = os.getenv("DATA_SOURCE", "mexc")
GOLD_SYMBOL = os.getenv("GOLD_SYMBOL", "GC=F")  # fallback للـ Yahoo
GOLD_DISPLAY_NAME = "XAU/USD"

# ═══════════════════════════════════════════════════════════════
# Trading Pairs - زوج واحد فقط (الذهب)
# ═══════════════════════════════════════════════════════════════
TRADING_PAIRS: List[str] = [
    "XAU/USD",
]

# ═══════════════════════════════════════════════════════════════
# Timeframes by Trade Type - أطر زمنية حسب نوع الصفقة
# ═══════════════════════════════════════════════════════════════
TIMEFRAMES: Dict[str, List[str]] = {
    "SCALPING": ["5m", "15m"],     # سريع - 5 دقائق و 15 دقيقة
    "MEDIUM":   ["1h", "4h"],      # متوسط - ساعة و 4 ساعات
    "SWING":    ["1d"],             # بعيد - يومي
}

# ═══════════════════════════════════════════════════════════════
# Capital Tiers - تقسيم رأس المال
# ═══════════════════════════════════════════════════════════════
CAPITAL_TIERS: List[int] = [10, 20, 30, 50, 60, 70, 100, 150, 200, 300, 500, 1000]

CAPITAL_TIER_CONFIG: Dict[int, Dict[str, Any]] = {
    10:   {"risk_pct": 5.0,  "max_trades": 1, "leverage": 10, "label": "مبتدئ"},
    20:   {"risk_pct": 5.0,  "max_trades": 1, "leverage": 10, "label": "مبتدئ"},
    30:   {"risk_pct": 4.0,  "max_trades": 2, "leverage": 10, "label": "صغير"},
    50:   {"risk_pct": 4.0,  "max_trades": 2, "leverage": 5,  "label": "صغير"},
    60:   {"risk_pct": 3.0,  "max_trades": 2, "leverage": 5,  "label": "متوسط"},
    70:   {"risk_pct": 3.0,  "max_trades": 3, "leverage": 5,  "label": "متوسط"},
    100:  {"risk_pct": 2.5,  "max_trades": 3, "leverage": 5,  "label": "متوسط+"},
    150:  {"risk_pct": 2.5,  "max_trades": 3, "leverage": 3,  "label": "كبير"},
    200:  {"risk_pct": 2.0,  "max_trades": 4, "leverage": 3,  "label": "كبير"},
    300:  {"risk_pct": 2.0,  "max_trades": 4, "leverage": 3,  "label": "كبير+"},
    500:  {"risk_pct": 1.5,  "max_trades": 5, "leverage": 2,  "label": "محترف"},
    1000: {"risk_pct": 1.0,  "max_trades": 5, "leverage": 2,  "label": "محترف+"},
}

# ═══════════════════════════════════════════════════════════════
# Channel Rules - قواعد القنوات
# ═══════════════════════════════════════════════════════════════
CHANNEL_RULES: Dict[str, Dict[str, Any]] = {
    "PUBLIC": {
        "name": "القناة العامة",
        "min_signals": 1,
        "max_signals": 3,
        "allowed_types": ["SCALPING", "MEDIUM"],
        "blocked_types": ["SWING"],
        "max_risk": "LOW",
        "min_confidence": 50,
        "profit_mode": "SMALL",
        "description": "صفقات سريعة ومتوسطة - ربح صغير ومخاطرة منخفضة",
    },
    "PRIVATE": {
        "name": "القناة الخاصة",
        "min_signals": 1,
        "max_signals": 10,
        "allowed_types": ["MEDIUM", "SWING"],
        "blocked_types": ["SCALPING"],
        "max_risk": "HIGH",
        "min_confidence": 65,
        "profit_mode": "LARGE",
        "description": "صفقات متوسطة وبعيدة - ربح كبير وتحليل متقدم",
    },
}

# ═══════════════════════════════════════════════════════════════
# Risk Levels - مستويات المخاطرة
# ═══════════════════════════════════════════════════════════════
RISK_LEVELS: Dict[str, Dict[str, Any]] = {
    "LOW": {
        "risk_pct": (0.5, 1.0),     # الذهب أقل تذبذب من الكريبتو
        "min_rr": 2.0,
        "min_confidence": 70,
        "label_ar": "منخفضة",
        "emoji": "🟢",
    },
    "MEDIUM": {
        "risk_pct": (1.0, 2.0),
        "min_rr": 1.5,
        "min_confidence": 55,
        "label_ar": "متوسطة",
        "emoji": "🟡",
    },
    "HIGH": {
        "risk_pct": (2.0, 3.0),
        "min_rr": 1.0,
        "min_confidence": 40,
        "label_ar": "عالية",
        "emoji": "🔴",
    },
}

# ═══════════════════════════════════════════════════════════════
# Trade Type Targets - أهداف كل نوع صفقة (مخصصة للذهب)
# ═══════════════════════════════════════════════════════════════
TRADE_TARGETS: Dict[str, Dict[str, float]] = {
    "SCALPING": {
        "tp1_pct": 0.3, "tp2_pct": 0.5, "tp3_pct": 0.8,    # الذهب يتحرك أقل من الكريبتو
        "sl_pct": 0.3,  "holding_time": "15-60 دقيقة",
    },
    "MEDIUM": {
        "tp1_pct": 0.8, "tp2_pct": 1.5, "tp3_pct": 2.5,
        "sl_pct": 0.8,  "holding_time": "4-24 ساعة",
    },
    "SWING": {
        "tp1_pct": 2.0, "tp2_pct": 4.0, "tp3_pct": 7.0,
        "sl_pct": 1.5,  "holding_time": "1-7 أيام",
    },
}

# ═══════════════════════════════════════════════════════════════
# Scheduling - الجدولة
# ═══════════════════════════════════════════════════════════════
SCAN_INTERVALS: Dict[str, str] = {
    "SCALPING": "15",   # كل 15 دقيقة
    "MEDIUM":   "60",   # كل ساعة
    "SWING":    "240",  # كل 4 ساعات
    "ANALYSIS": "360",  # كل 6 ساعات
    "SUMMARY":  "daily", # يومياً
}

# ═══════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
TIMEZONE = os.getenv("TIMEZONE", "Africa/Cairo")

# ═══════════════════════════════════════════════════════════════
# Fear & Greed API (للذهب نستخدم مؤشر VIX كدليل على الخوف)
# ═══════════════════════════════════════════════════════════════
FEAR_GREED_API = "https://api.alternative.me/fng/?limit=1"
VIX_SYMBOL = "^VIX"  # مؤشر التذبذب - يعكس الخوف في السوق

# ═══════════════════════════════════════════════════════════════
# Advanced Features Configuration
# ═══════════════════════════════════════════════════════════════
MIN_MEXC_BALANCE = float(os.getenv("MIN_MEXC_BALANCE", "10"))
SIGNAL_COOLDOWN_MINUTES = int(os.getenv("SIGNAL_COOLDOWN_MINUTES", "30"))
MAX_SPREAD_PCT = float(os.getenv("MAX_SPREAD_PCT", "0.15"))
