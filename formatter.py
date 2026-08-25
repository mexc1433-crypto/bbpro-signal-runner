"""
BBPro Signal Bot - Message Formatter
تنسيق الرسائل للقنوات
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
    """تنسيق السعر حسب حجمه"""
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
    تنسيق رسالة الإشارة الكاملة
    PUBLIC: رسالة مبسطة - ربح صغير
    PRIVATE: رسالة مفصلة - ربح كبير + كل مستويات رأس المال
    """
    emoji = _emoji_signal(signal["signal_type"])
    trade_emoji = _emoji_trade_type(signal["trade_type"])
    risk_emoji = _emoji_risk(signal["risk_level"])
    trade_ar = _trade_type_ar(signal["trade_type"])

    entry = signal["entry_price"]
    is_buy = signal["signal_type"] == "BUY"

    # ═══════════════════════════════════════
    # PUBLIC CHANNEL - simplified format
    # ═══════════════════════════════════════
    if channel_type == "PUBLIC":
        # Show only small capital tiers for public
        small_plans = [p for p in capital_plans if p["capital"] <= 100][:4]

        msg = f"{emoji} إشارة {'شراء' if is_buy else 'بيع'} | {signal.get('symbol', '???')}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"{trade_emoji} النوع: {trade_ar}\n"
        msg += f"📊 الاستراتيجية: {signal['strategy_name']}\n"
        msg += f"🎯 نسبة النجاح: {signal['confidence']}%\n\n"

        msg += f"💵 سعر الدخول: {_fmt_price(entry)}\n"
        if is_buy:
            msg += f"🎯 هدف 1: {_fmt_price(signal['take_profit_1'])}\n"
            msg += f"🎯 هدف 2: {_fmt_price(signal['take_profit_2'])}\n"
            msg += f"🎯 هدف 3: {_fmt_price(signal['take_profit_3'])}\n"
            msg += f"🛑 الخسارة: {_fmt_price(signal['stop_loss'])}\n"
        else:
            msg += f"🎯 هدف 1: {_fmt_price(signal['take_profit_1'])}\n"
            msg += f"🎯 هدف 2: {_fmt_price(signal['take_profit_2'])}\n"
            msg += f"🎯 هدف 3: {_fmt_price(signal['take_profit_3'])}\n"
            msg += f"🛑 الخسارة: {_fmt_price(signal['stop_loss'])}\n"

        msg += "\n💰 خطة رأس المال:\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        for p in small_plans:
            profit = p["potential_profit_tp1"]
            loss = p["potential_loss"]
            msg += f"💵 ${p['capital']} → حجم ${p['position_size_usd']} | {p['leverage']} | ربح +${profit} | خسارة -${loss}\n"

        msg += f"\n⚠️ المخاطرة: {signal['risk_level']} {_emoji_risk(signal['risk_level'])}\n"
        msg += f"📌 المؤشرات: {', '.join(signal['indicators_used'][:4])}\n"
        msg += f"💡 {signal['reasoning'][:200]}\n" if len(signal.get('reasoning', '')) > 0 else ""
        msg += f"\n📅 {signal.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M'))}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += "⚠️ ليست نصيحة استثمارية - إدارة مخاطرك\n"
        msg += "🤖 BBPro Signal Bot"

        return msg

    # ═══════════════════════════════════════
    # PRIVATE CHANNEL - full detailed format
    # ═══════════════════════════════════════
    else:
        diamond = "💎" if signal["confidence"] >= 80 else ""
        msg = f"{emoji}{diamond} إشارة {'شراء' if is_buy else 'بيع'} {'مميزة' if diamond else ''} | {signal.get('symbol', '???')}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"{trade_emoji} النوع: {trade_ar}\n"
        msg += f"📊 الاستراتيجية: {signal['strategy_name']}\n"
        msg += f"🎯 نسبة النجاح: {signal['confidence']}%\n"

        # Risk/Reward
        rr = abs(signal["take_profit_2"] - entry) / max(abs(entry - signal["stop_loss"]), 0.000001)
        msg += f"🔥 المخاطرة/الربح: 1:{rr:.1f}\n\n"

        msg += f"💵 سعر الدخول: {_fmt_price(entry)}\n"
        if is_buy:
            tp1_pct = _fmt_pct(entry, signal["take_profit_1"])
            tp2_pct = _fmt_pct(entry, signal["take_profit_2"])
            tp3_pct = _fmt_pct(entry, signal["take_profit_3"])
            sl_pct = _fmt_pct(entry, signal["stop_loss"])
            msg += f"🎯 TP1: {_fmt_price(signal['take_profit_1'])} ({tp1_pct})\n"
            msg += f"🎯 TP2: {_fmt_price(signal['take_profit_2'])} ({tp2_pct})\n"
            msg += f"🎯 TP3: {_fmt_price(signal['take_profit_3'])} ({tp3_pct})\n"
            msg += f"🛑 SL: {_fmt_price(signal['stop_loss'])} ({sl_pct})\n"
        else:
            tp1_pct = _fmt_pct(entry, signal["take_profit_1"])
            tp2_pct = _fmt_pct(entry, signal["take_profit_2"])
            tp3_pct = _fmt_pct(entry, signal["take_profit_3"])
            sl_pct = _fmt_pct(entry, signal["stop_loss"])
            msg += f"🎯 TP1: {_fmt_price(signal['take_profit_1'])} ({tp1_pct})\n"
            msg += f"🎯 TP2: {_fmt_price(signal['take_profit_2'])} ({tp2_pct})\n"
            msg += f"🎯 TP3: {_fmt_price(signal['take_profit_3'])} ({tp3_pct})\n"
            msg += f"🛑 SL: {_fmt_price(signal['stop_loss'])} ({sl_pct})\n"

        # Full capital tier table
        msg += "\n📊 خطة رأس المال الكاملة:\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for p in capital_plans:
            profit = p["potential_profit_tp1"]
            profit2 = p["potential_profit_tp2"]
            profit3 = p["potential_profit_tp3"]
            loss = p["potential_loss"]
            ev = p.get("expected_value", 0)
            ev_emoji = "📈" if ev > 0 else "📉"

            msg += f"💵 ${p['capital']} → حجم ${p['position_size_usd']} | {p['leverage']} | TP1: +${profit} | TP2: +${profit2} | TP3: +${profit3} | SL: -${loss} | EV: {ev_emoji}${ev}\n"

        # Advanced analysis
        msg += "\n📈 التحليل الفني المتقدم:\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for indicator in signal.get("indicators_used", []):
            msg += f"• {indicator} ✅\n"

        # Risk management
        msg += "\n🛡️ إدارة المخاطر:\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"• مستوى المخاطرة: {signal['risk_level']} {_emoji_risk(signal['risk_level'])}\n"
        msg += f"• نسبة النجاح: {signal['confidence']}%\n"
        msg += f"• نسبة R:R: 1:{rr:.1f}\n"

        # Reasoning
        reasoning = signal.get("reasoning", "")
        if reasoning:
            msg += f"\n💡 سبب الإشارة:\n{reasoning}\n"

        msg += f"\n📅 {signal.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M'))}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "⚠️ ليست نصيحة استثمارية - إدارة مخاطرك\n"
        msg += "🤖 BBPro Signal Bot 🔥"

        return msg


def format_analysis_message(analysis: Dict) -> str:
    """تنسيق رسالة تحليل السوق"""
    sentiment = analysis.get("sentiment", "NEUTRAL")
    sentiment_emoji = {"BULLISH": "🟢 صاعد", "BEARISH": "🔴 هابط", "NEUTRAL": "⚪ محايد"}.get(sentiment, "⚪ محايد")

    msg = "📊 تحليل السوق الشامل\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🌍 الاتجاه العام: {sentiment_emoji}\n"
    msg += f"💪 قوة الاتجاه: {analysis.get('trend_strength', 0):.0f}%\n\n"

    if analysis.get("btc_price"):
        msg += f"₿ BTC: ${analysis['btc_price']:,.0f}\n"
    if analysis.get("fear_greed") is not None:
        fg = analysis["fear_greed"]
        fg_label = {0: "خوف شديد", 25: "خوف", 50: "محايد", 75: "طمع", 100: "طمع شديد"}
        closest = min(fg_label.keys(), key=lambda x: abs(x - fg))
        msg += f"😱 Fear & Greed: {fg} ({fg_label[closest]})\n"

    if analysis.get("top_gainers"):
        msg += "\n🚀 أكبر ارتفاعات:\n"
        for g in analysis["top_gainers"][:5]:
            msg += f"  {g['symbol']}: +{g['change']:.1f}%\n"

    if analysis.get("top_losers"):
        msg += "\n📉 أكبر انخفاضات:\n"
        for l in analysis["top_losers"][:5]:
            msg += f"  {l['symbol']}: {l['change']:.1f}%\n"

    if analysis.get("recommendation"):
        msg += f"\n💡 التوصية: {analysis['recommendation']}\n"

    msg += f"\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    msg += "🤖 BBPro Signal Bot"

    return msg


def format_summary_message(signals: List[Dict]) -> str:
    """تنسيق ملخص يومي/أسبوعي"""
    total = len(signals)
    buy_count = sum(1 for s in signals if s.get("signal_type") == "BUY")
    sell_count = total - buy_count

    # Pairs count
    pairs = set(s.get("symbol", "") for s in signals)

    # Average confidence
    avg_conf = sum(s.get("confidence", 0) for s in signals) / max(total, 1)

    msg = "📋 ملخص الإشارات اليومي\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📊 إجمالي الإشارات: {total}\n"
    msg += f"🟢 شراء: {buy_count} | 🔴 بيع: {sell_count}\n"
    msg += f"📈 متوسط الثقة: {avg_conf:.1f}%\n"
    msg += f"💱 الأزواج المغطاة: {len(pairs)}\n\n"

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
    msg += f"  🔴 عالية: {high_risk}\n"

    msg += f"\n📅 {datetime.now().strftime('%Y-%m-%d')}\n"
    msg += "🤖 BBPro Signal Bot"

    return msg


def format_market_update(market_data: Dict) -> str:
    """تنسيق تحديث سريع للسوق"""
    msg = "📊 تحديث السوق السريع\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n"

    if market_data.get("btc"):
        msg += f"₿ BTC: ${market_data['btc']:,.0f}\n"
    if market_data.get("eth"):
        msg += f"Ξ ETH: ${market_data['eth']:,.0f}\n"

    if market_data.get("market_breadth"):
        bullish, bearish = market_data["market_breadth"]
        msg += f"\n📈 صاعد: {bullish} | 📉 هابط: {bearish}\n"

    if market_data.get("notable"):
        msg += "\n⚡ حركات بارزة:\n"
        for n in market_data["notable"][:5]:
            msg += f"  {n['symbol']}: {n['change']:+.1f}%\n"

    msg += f"\n📅 {datetime.now().strftime('%H:%M')}\n"
    msg += "🤖 BBPro Signal Bot"

    return msg
