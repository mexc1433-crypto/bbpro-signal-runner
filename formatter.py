"""
صياد الشمعات | Candle Hunter - Message Formatter
تنسيق الرسائل للقنوات - مبسط وواضح
"""
from typing import Dict, List, Optional
from datetime import datetime
from config import CAPITAL_TIERS


def _emoji_signal(signal_type: str) -> str:
    return "🟢" if signal_type == "BUY" else "🔴"


def _emoji_trade_type(trade_type: str) -> str:
    return {
        "SCALPING": "⚡",
        "MEDIUM": "📊",
        "SWING": "🎯",
    }.get(trade_type, "📌")


def _emoji_risk(risk_level: str) -> str:
    return {
        "LOW": "🟢",
        "MEDIUM": "🟡",
        "HIGH": "🔴",
    }.get(risk_level, "⚪")


def _trade_type_ar(trade_type: str) -> str:
    return {
        "SCALPING": "سريع (Scalping)",
        "MEDIUM": "متوسط (Medium)",
        "SWING": "بعيد (Swing)",
    }.get(trade_type, trade_type)


def _fmt_price(price: float) -> str:
    """تنسيق السعر للذهب"""
    if price >= 1000:
        return f"{price:,.2f}"
    elif price >= 1:
        return f"{price:,.4f}"
    else:
        return f"{price:,.6f}"


def _fmt_pct(entry: float, target: float) -> str:
    """نسبة التغير"""
    pct = ((target - entry) / entry) * 100
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.2f}%"


def format_signal_message(signal: Dict, capital_plans: List[Dict],
                           channel_type: str = "PRIVATE") -> str:
    """
    تنسيق رسالة الإشارة
    PUBLIC: رسالة مبسطة جداً - ربح صغير
    PRIVATE: رسالة واضحة وبسيطة - سعر الدخول والخروج والستوب
    """
    emoji = _emoji_signal(signal["signal_type"])
    trade_emoji = _emoji_trade_type(signal["trade_type"])
    risk_emoji = _emoji_risk(signal["risk_level"])
    trade_ar = _trade_type_ar(signal["trade_type"])

    entry = signal["entry_price"]
    is_buy = signal["signal_type"] == "BUY"
    direction = "شراء" if is_buy else "بيع"

    # ═══════════════════════════════════════
    # PUBLIC CHANNEL - بسيط جداً
    # ═══════════════════════════════════════
    if channel_type == "PUBLIC":
        msg = f"{emoji} {direction} | XAU/USD\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"{trade_emoji} النوع: {trade_ar}\n"
        msg += f"📊 الاستراتيجية: {signal['strategy_name']}\n"
        msg += f"🎯 نسبة النجاح: {signal['confidence']}%\n\n"

        msg += f"💵 سعر الدخول: {_fmt_price(entry)}\n"
        msg += f"🎯 هدف 1: {_fmt_price(signal['take_profit_1'])}\n"
        msg += f"🎯 هدف 2: {_fmt_price(signal['take_profit_2'])}\n"
        msg += f"🛑 ستوب لوس: {_fmt_price(signal['stop_loss'])}\n\n"

        msg += f"⚠️ المخاطرة: {signal['risk_level']} {risk_emoji}\n"
        msg += f"⏱️ المدة: {signal.get('holding_time', '')}\n"
        msg += f"📅 {signal.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M'))}\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "⚠️ ليست نصيحة استثمارية\n"
        msg += "🤖 صياد الشمعات | Candle Hunter"

        return msg

    # ═══════════════════════════════════════
    # PRIVATE CHANNEL - واضح ومباشر
    # ═══════════════════════════════════════
    else:
        # Risk/Reward
        rr = abs(signal["take_profit_2"] - entry) / max(abs(entry - signal["stop_loss"]), 0.000001)

        msg = f"{emoji} {direction} | XAU/USD\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"{trade_emoji} النوع: {trade_ar}\n"
        msg += f"📊 الاستراتيجية: {signal['strategy_name']}\n"
        msg += f"🎯 نسبة النجاح: {signal['confidence']}%\n"
        msg += f"🔥 R:R = 1:{rr:.1f}\n\n"

        # الأساسيات - سعر الدخول والأهداف والستوب
        msg += "📍 تفاصيل الصفقة:\n"
        msg += f"💵 سعر الدخول: {_fmt_price(entry)}\n"
        msg += f"🎯 TP1: {_fmt_price(signal['take_profit_1'])} ({_fmt_pct(entry, signal['take_profit_1'])})\n"
        msg += f"🎯 TP2: {_fmt_price(signal['take_profit_2'])} ({_fmt_pct(entry, signal['take_profit_2'])})\n"
        msg += f"🎯 TP3: {_fmt_price(signal['take_profit_3'])} ({_fmt_pct(entry, signal['take_profit_3'])})\n"
        msg += f"🛑 SL: {_fmt_price(signal['stop_loss'])} ({_fmt_pct(entry, signal['stop_loss'])})\n\n"

        # خطة رأس المال - جدول بسيط
        msg += "💰 خطة رأس المال:\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for p in capital_plans:
            profit = p["potential_profit_tp1"]
            profit3 = p["potential_profit_tp3"]
            loss = p["potential_loss"]
            msg += f"${p['capital']} → ربح +${profit} | خسارة -${loss}\n"

        msg += f"\n🛡️ المخاطرة: {signal['risk_level']} {risk_emoji}\n"
        msg += f"⏱️ المدة: {signal.get('holding_time', '')}\n"

        # المؤشرات المستخدمة
        indicators = signal.get("indicators_used", [])
        if indicators:
            msg += f"\n📈 المؤشرات ({len(indicators)}):\n"
            for ind in indicators[:6]:
                msg += f"  ✅ {ind}\n"

        msg += f"\n📅 {signal.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M'))}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "⚠️ ليست نصيحة استثمارية\n"
        msg += "🤖 صياد الشمعات | Candle Hunter"

        return msg


def format_analysis_message(analysis: Dict) -> str:
    """تنسيق رسالة تحليل السوق للذهب"""
    sentiment = analysis.get("sentiment", "NEUTRAL")
    sentiment_emoji = {"BULLISH": "🟢 صاعد", "BEARISH": "🔴 هابط", "NEUTRAL": "⚪ محايد"}.get(sentiment, "⚪ محايد")

    msg = "📊 تحليل سوق الذهب\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🌍 الاتجاه العام: {sentiment_emoji}\n"
    msg += f"💪 قوة الاتجاه: {analysis.get('sentiment_score', 0):.0f}/100\n\n"

    if analysis.get("gold_price"):
        msg += f"🥇 الذهب: ${analysis['gold_price']:,.2f}\n"
        ch = analysis.get("gold_change", 0)
        msg += f"📊 التغير: {ch:+.2f}%\n"

    if analysis.get("vix"):
        msg += f"😱 VIX: {analysis['vix']:.1f} ({analysis.get('vix_label', '')})\n"

    if analysis.get("dxy"):
        msg += f"💵 مؤشر الدولار: {analysis['dxy']:.2f}\n"

    if analysis.get("silver_price"):
        msg += f"🥈 الفضة: ${analysis['silver_price']:,.2f}\n"

    if analysis.get("fear_greed") is not None:
        fg = analysis["fear_greed"]
        fg_label = "خوف شديد" if fg < 25 else "خوف" if fg < 45 else "محايد" if fg < 55 else "طمع" if fg < 75 else "طمع شديد"
        msg += f"😱 الخوف والطمع: {fg} ({fg_label})\n"

    if analysis.get("recommendation"):
        msg += f"\n💡 {analysis['recommendation']}\n"

    msg += f"\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    msg += "🤖 صياد الشمعات | Candle Hunter"

    return msg


def format_summary_message(signals: List[Dict]) -> str:
    """تنسيق ملخص يومي"""
    total = len(signals)
    buy_count = sum(1 for s in signals if s.get("signal_type") == "BUY")
    sell_count = total - buy_count
    avg_conf = sum(s.get("confidence", 0) for s in signals) / max(total, 1)

    msg = "📋 ملخص إشارات اليوم\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📊 إجمالي: {total} إشارة\n"
    msg += f"🟢 شراء: {buy_count} | 🔴 بيع: {sell_count}\n"
    msg += f"📈 متوسط الثقة: {avg_conf:.1f}%\n\n"

    # By trade type
    scalping = sum(1 for s in signals if s.get("trade_type") == "SCALPING")
    medium = sum(1 for s in signals if s.get("trade_type") == "MEDIUM")
    swing = sum(1 for s in signals if s.get("trade_type") == "SWING")
    msg += "توزيع حسب النوع:\n"
    msg += f"  ⚡ سريع: {scalping}\n"
    msg += f"  📊 متوسط: {medium}\n"
    msg += f"  🎯 بعيد: {swing}\n\n"

    # By risk
    low_risk = sum(1 for s in signals if s.get("risk_level") == "LOW")
    med_risk = sum(1 for s in signals if s.get("risk_level") == "MEDIUM")
    high_risk = sum(1 for s in signals if s.get("risk_level") == "HIGH")
    msg += "توزيع حسب المخاطرة:\n"
    msg += f"  🟢 منخفضة: {low_risk}\n"
    msg += f"  🟡 متوسطة: {med_risk}\n"
    msg += f"  🔴 عالية: {high_risk}\n\n"

    # Channel distribution
    public_count = sum(1 for s in signals if s.get("channel") == "PUBLIC")
    private_count = sum(1 for s in signals if s.get("channel") == "PRIVATE")
    msg += "القنوات:\n"
    msg += f"  📢 عامة: {public_count}\n"
    msg += f"  💎 خاصة: {private_count}\n"

    msg += f"\n📅 {datetime.now().strftime('%Y-%m-%d')}\n"
    msg += "🤖 صياد الشمعات | Candle Hunter"

    return msg


def format_market_update(market_data: Dict) -> str:
    """تنسيق رسالة تحديث السوق"""
    msg = "📊 تحديث سوق الذهب\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n"

    if market_data.get("gold_price"):
        msg += f"🥇 XAU/USD: ${market_data['gold_price']:,.2f}\n"
        ch = market_data.get("gold_change", 0)
        msg += f"📊 التغير: {ch:+.2f}%\n"

    if market_data.get("vix"):
        msg += f"😱 VIX: {market_data['vix']:.1f}\n"

    if market_data.get("dxy"):
        msg += f"💵 DXY: {market_data['dxy']:.2f}\n"

    msg += f"\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    msg += "🤖 صياد الشمعات | Candle Hunter"

    return msg
