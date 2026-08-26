"""
BBPro Signal Bot - Trading Strategies
13 استراتيجيات تداول متقدمة
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
from indicators import (
    rsi, macd, bollinger_bands, ema, sma, stochastic, atr, adx,
    ichimoku, vwap, fibonacci_levels, williams_r, cci, mfi, obv,
    parabolic_sar, supertrend, calculate_all_indicators,
    bullish_cross, bearish_cross
)
from config import TRADE_TARGETS


def _make_signal(
    strategy_name: str,
    signal_type: str,
    confidence: float,
    indicators_used: List[str],
    entry_price: float,
    stop_loss: float,
    tp1: float, tp2: float, tp3: float,
    risk_level: str,
    trade_type: str,
    reasoning: str,
) -> Dict:
    """يبني dict إشارة موحد"""
    return {
        'strategy_name': strategy_name,
        'signal_type': signal_type,
        'confidence': round(confidence, 1),
        'indicators_used': indicators_used,
        'entry_price': round(entry_price, 6),
        'stop_loss': round(stop_loss, 6),
        'take_profit_1': round(tp1, 6),
        'take_profit_2': round(tp2, 6),
        'take_profit_3': round(tp3, 6),
        'risk_level': risk_level,
        'trade_type': trade_type,
        'reasoning': reasoning,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


# ═══════════════════════════════════════════════════════════════
# 1. Trend Following Strategy
# ═══════════════════════════════════════════════════════════════

def trend_following_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "MEDIUM") -> Optional[Dict]:
    """
    استراتيجية تتبع الاتجاه - EMA crossover + ADX + MACD
    تعمل بشكل أفضل في الأسواق ذات الاتجاه الواضح
    """
    if len(df) < 60:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]

    ema9 = ind['ema_9'].iloc[-1]
    ema21 = ind['ema_21'].iloc[-1]
    ema50 = ind['ema_50'].iloc[-1]
    ema200 = ind['ema_200'].iloc[-1] if not np.isnan(ind['ema_200'].iloc[-1]) else ema50
    adx_val = ind['adx'].iloc[-1]
    macd_hist = ind['macd_hist'].iloc[-1]
    macd_hist_prev = ind['macd_hist'].iloc[-2]

    bullish_ema = ema9 > ema21 > ema50
    bearish_ema = ema9 < ema21 < ema50
    strong_trend = adx_val > 25
    macd_bullish = macd_hist > 0 and macd_hist > macd_hist_prev
    macd_bearish = macd_hist < 0 and macd_hist < macd_hist_prev
    above_200 = price > ema200
    below_200 = price < ema200

    confidence = 0
    reasoning_parts = []

    if bullish_ema and strong_trend and macd_bullish and above_200:
        confidence = 75
        reasoning_parts.append("EMA 9 فوق 21 فوق 50 (ترتيب صاعد)")
        if adx_val > 35:
            confidence += 10
            reasoning_parts.append(f"ADX {adx_val:.0f} (اتجاه قوي جداً)")
        else:
            reasoning_parts.append(f"ADX {adx_val:.0f} (اتجاه مؤكد)")

        if bullish_cross(ind['ema_9'], ind['ema_21']):
            confidence += 5
            reasoning_parts.append("تقاطع EMA 9/21 صاعد حديث")

        reasoning_parts.append("MACD histogram موجب ومتزايد")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = price * (1 - targets['sl_pct'] / 100)

        risk_level = "LOW" if confidence >= 70 else "MEDIUM"
        return _make_signal(
            "Trend Following (EMA+ADX+MACD)", "BUY", min(confidence, 95),
            ["EMA 9/21/50/200", "ADX", "MACD", "Price vs EMA200"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    elif bearish_ema and strong_trend and macd_bearish and below_200:
        confidence = 75
        reasoning_parts.append("EMA 9 تحت 21 تحت 50 (ترتيب هابط)")
        if adx_val > 35:
            confidence += 10
            reasoning_parts.append(f"ADX {adx_val:.0f} (اتجاه هابط قوي)")
        else:
            reasoning_parts.append(f"ADX {adx_val:.0f} (اتجاه هابط مؤكد)")

        if bearish_cross(ind['ema_9'], ind['ema_21']):
            confidence += 5

        reasoning_parts.append("MACD histogram سالب ومتزايد هبوطاً")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = price * (1 + targets['sl_pct'] / 100)

        risk_level = "LOW" if confidence >= 70 else "MEDIUM"
        return _make_signal(
            "Trend Following (EMA+ADX+MACD)", "SELL", min(confidence, 95),
            ["EMA 9/21/50/200", "ADX", "MACD", "Price vs EMA200"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════
# 2. Mean Reversion Strategy
# ═══════════════════════════════════════════════════════════════

def mean_reversion_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "MEDIUM") -> Optional[Dict]:
    """
    استراتيجية العودة للمتوسط - Bollinger + RSI + Stochastic
    تعمل في الأسواق العرضية (range markets)
    """
    if len(df) < 50:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]

    bb_lower = ind['bb_lower'].iloc[-1]
    bb_upper = ind['bb_upper'].iloc[-1]
    bb_middle = ind['bb_middle'].iloc[-1]
    rsi_val = ind['rsi_14'].iloc[-1]
    stoch_k = ind['stoch_k'].iloc[-1]
    stoch_d = ind['stoch_d'].iloc[-1]

    confidence = 0
    reasoning_parts = []

    # BUY: السعر تحت BB lower + RSI oversold + Stochastic oversold
    if price <= bb_lower and rsi_val < 35 and stoch_k < 20:
        confidence = 65
        reasoning_parts.append(f"السعر تحت Bollinger السفلي ({price:.6f} ≤ {bb_lower:.6f})")
        reasoning_parts.append(f"RSI {rsi_val:.0f} (تشبع بيعي)")
        reasoning_parts.append(f"Stochastic K={stoch_k:.0f}% (تشبع بيعي)")

        if stoch_k > stoch_d:
            confidence += 10
            reasoning_parts.append("Stochastic بدأ reversal صاعد")

        if rsi_val < 25:
            confidence += 8
            reasoning_parts.append("تشبع بيعي حاد")

        if price < bb_lower * 0.998:
            confidence += 5
            reasoning_parts.append("اختراق قوي تحت BB")

        targets = TRADE_TARGETS[trade_type]
        tp1 = bb_middle
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = price * (1 - targets['sl_pct'] / 100)

        risk_level = "MEDIUM" if confidence < 75 else "LOW"
        return _make_signal(
            "Mean Reversion (BB+RSI+Stoch)", "BUY", min(confidence, 92),
            ["Bollinger Bands", "RSI 14", "Stochastic"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    # SELL: السعر فوق BB upper + RSI overbought + Stochastic overbought
    elif price >= bb_upper and rsi_val > 65 and stoch_k > 80:
        confidence = 65
        reasoning_parts.append(f"السعر فوق Bollinger العلوي ({price:.6f} ≥ {bb_upper:.6f})")
        reasoning_parts.append(f"RSI {rsi_val:.0f} (تشبع شرائي)")
        reasoning_parts.append(f"Stochastic K={stoch_k:.0f}% (تشبع شرائي)")

        if stoch_k < stoch_d:
            confidence += 10
            reasoning_parts.append("Stochastic بدأ reversal هابط")

        if rsi_val > 75:
            confidence += 8
            reasoning_parts.append("تشبع شرائي حاد")

        targets = TRADE_TARGETS[trade_type]
        tp1 = bb_middle
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = price * (1 + targets['sl_pct'] / 100)

        risk_level = "MEDIUM" if confidence < 75 else "LOW"
        return _make_signal(
            "Mean Reversion (BB+RSI+Stoch)", "SELL", min(confidence, 92),
            ["Bollinger Bands", "RSI 14", "Stochastic"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════
# 3. Momentum Strategy
# ═══════════════════════════════════════════════════════════════

def momentum_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "MEDIUM") -> Optional[Dict]:
    """
    استراتيجية الزخم - MACD + RSI momentum + Volume + MFI
    تلتقط الحركات القوية مع تأكيد من حجم التداول
    """
    if len(df) < 50:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]
    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    current_vol = df['volume'].iloc[-1]

    macd_line = ind['macd_line'].iloc[-1]
    macd_signal = ind['macd_signal'].iloc[-1]
    macd_hist = ind['macd_hist'].iloc[-1]
    rsi_val = ind['rsi_14'].iloc[-1]
    mfi_val = ind['mfi'].iloc[-1]

    volume_surge = current_vol > vol_avg * 1.5

    confidence = 0
    reasoning_parts = []

    # Bullish momentum
    if macd_line > macd_signal and macd_hist > 0 and rsi_val > 50 and rsi_val < 75:
        confidence = 60
        reasoning_parts.append("MACD line فوق signal line (زخم صاعد)")
        reasoning_parts.append(f"RSI {rsi_val:.0f} (زخم صاعد بدون تشبع)")

        if volume_surge:
            confidence += 12
            reasoning_parts.append(f"حجم تداول مرتفع ({current_vol/vol_avg:.1f}x المتوسط)")

        if mfi_val > 60:
            confidence += 8
            reasoning_parts.append(f"MFI {mfi_val:.0f} (تدفق أموال صاعد)")

        if bullish_cross(ind['macd_line'], ind['macd_signal']):
            confidence += 8
            reasoning_parts.append("تقاطع MACD صاعد حديث")

        if confidence < 60:
            return None

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = price * (1 - targets['sl_pct'] / 100)

        risk_level = "LOW" if confidence >= 75 else "MEDIUM"
        return _make_signal(
            "Momentum (MACD+RSI+Vol+MFI)", "BUY", min(confidence, 90),
            ["MACD", "RSI 14", "Volume", "MFI"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    # Bearish momentum
    elif macd_line < macd_signal and macd_hist < 0 and rsi_val < 50 and rsi_val > 25:
        confidence = 60
        reasoning_parts.append("MACD line تحت signal line (زخم هابط)")
        reasoning_parts.append(f"RSI {rsi_val:.0f} (زخم هابط بدون تشبع)")

        if volume_surge:
            confidence += 12
            reasoning_parts.append(f"حجم تداول مرتفع ({current_vol/vol_avg:.1f}x المتوسط)")

        if mfi_val < 40:
            confidence += 8
            reasoning_parts.append(f"MFI {mfi_val:.0f} (تدفق أموال هابط)")

        if bearish_cross(ind['macd_line'], ind['macd_signal']):
            confidence += 8

        if confidence < 60:
            return None

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = price * (1 + targets['sl_pct'] / 100)

        risk_level = "LOW" if confidence >= 75 else "MEDIUM"
        return _make_signal(
            "Momentum (MACD+RSI+Vol+MFI)", "SELL", min(confidence, 90),
            ["MACD", "RSI 14", "Volume", "MFI"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════
# 4. Breakout Strategy
# ═══════════════════════════════════════════════════════════════

def breakout_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "SWING") -> Optional[Dict]:
    """
    استراتيجية الاختراق - Bollinger squeeze + Volume breakout + ADX rising
    تلتقط الحركات بعد فترات التضييق
    """
    if len(df) < 60:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]

    bw_current = ind['bb_bandwidth'].iloc[-1]
    bw_avg = ind['bb_bandwidth'].rolling(20).mean().iloc[-1]
    bw_prev = ind['bb_bandwidth'].iloc[-2]

    adx_val = ind['adx'].iloc[-1]
    adx_prev = ind['adx'].iloc[-2]

    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    current_vol = df['volume'].iloc[-1]

    # Squeeze detection
    squeeze = bw_current < bw_avg * 0.8
    expanding = bw_current > bw_prev

    # Recent high/low
    recent_high = df['high'].rolling(20).max().iloc[-2]
    recent_low = df['low'].rolling(20).min().iloc[-2]

    confidence = 0
    reasoning_parts = []

    # Bullish breakout
    if price > recent_high and current_vol > vol_avg * 1.3 and adx_val > adx_prev:
        confidence = 65
        reasoning_parts.append(f"اختراق المقاومة ({price:.6f} > {recent_high:.6f})")

        if squeeze or expanding:
            confidence += 10
            reasoning_parts.append("Bollinger squeeze + تمدد (طاقة متجمعة)")

        if current_vol > vol_avg * 2:
            confidence += 8
            reasoning_parts.append(f"حجم اختراق ضخم ({current_vol/vol_avg:.1f}x)")

        if adx_val > 30:
            confidence += 7
            reasoning_parts.append(f"ADX {adx_val:.0f} ويزداد (اتجاه قوي)")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = recent_low

        risk_level = "MEDIUM" if confidence < 75 else "LOW"
        return _make_signal(
            "Breakout (Squeeze+Vol+ADX)", "BUY", min(confidence, 90),
            ["Bollinger Bands", "Volume", "ADX", "Support/Resistance"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    # Bearish breakout
    elif price < recent_low and current_vol > vol_avg * 1.3 and adx_val > adx_prev:
        confidence = 65
        reasoning_parts.append(f"كسر الدعم ({price:.6f} < {recent_low:.6f})")

        if squeeze or expanding:
            confidence += 10
            reasoning_parts.append("Bollinger squeeze + تمدد")

        if current_vol > vol_avg * 2:
            confidence += 8

        if adx_val > 30:
            confidence += 7
            reasoning_parts.append(f"ADX {adx_val:.0f} ويزداد")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = recent_high

        risk_level = "MEDIUM" if confidence < 75 else "LOW"
        return _make_signal(
            "Breakout (Squeeze+Vol+ADX)", "SELL", min(confidence, 90),
            ["Bollinger Bands", "Volume", "ADX", "Support/Resistance"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════
# 5. Scalping Strategy
# ═══════════════════════════════════════════════════════════════

def scalping_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "SCALPING") -> Optional[Dict]:
    """
    استراتيجية السكالبينج - RSI(7) + EMA(9/21) + Stochastic + Williams %R
    صفقات سريعة جداً - 15-60 دقيقة
    """
    if len(df) < 30:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]

    rsi7 = ind['rsi_7'].iloc[-1]
    ema9 = ind['ema_9'].iloc[-1]
    ema21 = ind['ema_21'].iloc[-1]
    stoch_k = ind['stoch_k'].iloc[-1]
    stoch_d = ind['stoch_d'].iloc[-1]
    wr = ind['williams_r'].iloc[-1]

    confidence = 0
    reasoning_parts = []

    # Quick BUY
    if rsi7 < 30 and price > ema9 and stoch_k < 20 and stoch_k > stoch_d and wr < -80:
        confidence = 55
        reasoning_parts.append(f"RSI(7) {rsi7:.0f} - تشبع بيعي سريع")
        reasoning_parts.append("السعر فوق EMA 9 (دعم قريب)")
        reasoning_parts.append(f"Stochastic بدء reversal صاعد (K={stoch_k:.0f})")
        reasoning_parts.append(f"Williams %R {wr:.0f} (تشبع بيعي)")

        if bullish_cross(ind['ema_9'], ind['ema_21']):
            confidence += 10
            reasoning_parts.append("تقاطع EMA 9/21 صاعد")

        if stoch_k < 15:
            confidence += 5

        targets = TRADE_TARGETS["SCALPING"]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = price * (1 - targets['sl_pct'] / 100)

        return _make_signal(
            "Scalping (RSI7+EMA9/21+Stoch+WR)", "BUY", min(confidence, 80),
            ["RSI 7", "EMA 9/21", "Stochastic", "Williams %R"],
            price, sl, tp1, tp2, tp3, "LOW", "SCALPING",
            " • ".join(reasoning_parts)
        )

    # Quick SELL
    elif rsi7 > 70 and price < ema9 and stoch_k > 80 and stoch_k < stoch_d and wr > -20:
        confidence = 55
        reasoning_parts.append(f"RSI(7) {rsi7:.0f} - تشبع شرائي سريع")
        reasoning_parts.append("السعر تحت EMA 9 (مقاومة قريبة)")
        reasoning_parts.append(f"Stochastic بدء reversal هابط (K={stoch_k:.0f})")
        reasoning_parts.append(f"Williams %R {wr:.0f} (تشبع شرائي)")

        if bearish_cross(ind['ema_9'], ind['ema_21']):
            confidence += 10
            reasoning_parts.append("تقاطع EMA 9/21 هابط")

        targets = TRADE_TARGETS["SCALPING"]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = price * (1 + targets['sl_pct'] / 100)

        return _make_signal(
            "Scalping (RSI7+EMA9/21+Stoch+WR)", "SELL", min(confidence, 80),
            ["RSI 7", "EMA 9/21", "Stochastic", "Williams %R"],
            price, sl, tp1, tp2, tp3, "LOW", "SCALPING",
            " • ".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════
# 6. Swing Strategy
# ═══════════════════════════════════════════════════════════════

def swing_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "SWING") -> Optional[Dict]:
    """
    استراتيجية السوينج - Ichimoku + Fibonacci + EMA 50/200 + ADX
    صفقات طويلة الأمد - 1-7 أيام
    """
    if len(df) < 120:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]
    fib = ind['fibonacci']
    ichi = ind['ichimoku']

    tenkan = ichi['tenkan'].iloc[-1]
    kijun = ichi['kijun'].iloc[-1]
    senkou_a = ichi['senkou_a'].iloc[-1]
    senkou_b = ichi['senkou_b'].iloc[-1]
    ema50 = ind['ema_50'].iloc[-1]
    ema200 = ind['ema_200'].iloc[-1]
    adx_val = ind['adx'].iloc[-1]

    confidence = 0
    reasoning_parts = []

    # Bullish swing
    above_cloud = price > senkou_a and price > senkou_b
    cloud_green = senkou_a > senkou_b
    tenkan_above_kijun = tenkan > kijun
    above_ema = price > ema50 and ema50 > ema200

    if above_cloud and cloud_green and tenkan_above_kijun and above_ema and adx_val > 20:
        confidence = 70
        reasoning_parts.append("السعر فوق سحابة Ichimoku (اتجاه صاعد قوي)")
        reasoning_parts.append("السحابة خضراء (senkou A > senkou B)")
        reasoning_parts.append("Tenkan فوق Kijun (زخم صاعد)")

        if adx_val > 30:
            confidence += 8
            reasoning_parts.append(f"ADX {adx_val:.0f} (اتجاه قوي)")

        # Check price near fibonacci support
        fib_618 = fib['0.618']
        if abs(price - fib_618) / price < 0.02:
            confidence += 7
            reasoning_parts.append("السعر قرب مستوى فيبوناتشي 61.8% (دعم)")

        if bullish_cross(ichi['tenkan'], ichi['kijun']):
            confidence += 5
            reasoning_parts.append("تقاطع Tenkan/Kijun صاعد حديث")

        targets = TRADE_TARGETS["SWING"]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = max(senkou_b, price * (1 - targets['sl_pct'] / 100))

        risk_level = "LOW" if confidence >= 75 else "MEDIUM"
        return _make_signal(
            "Swing (Ichimoku+Fib+EMA+ADX)", "BUY", min(confidence, 92),
            ["Ichimoku", "Fibonacci", "EMA 50/200", "ADX"],
            price, sl, tp1, tp2, tp3, risk_level, "SWING",
            " • ".join(reasoning_parts)
        )

    # Bearish swing
    below_cloud = price < senkou_a and price < senkou_b
    cloud_red = senkou_a < senkou_b
    tenkan_below_kijun = tenkan < kijun
    below_ema = price < ema50 and ema50 < ema200

    if below_cloud and cloud_red and tenkan_below_kijun and below_ema and adx_val > 20:
        confidence = 70
        reasoning_parts.append("السعر تحت سحابة Ichimoku (اتجاه هابط قوي)")
        reasoning_parts.append("السحابة حمراء (senkou A < senkou B)")
        reasoning_parts.append("Tenkan تحت Kijun (زخم هابط)")

        if adx_val > 30:
            confidence += 8

        fib_382 = fib['0.382']
        if abs(price - fib_382) / price < 0.02:
            confidence += 7
            reasoning_parts.append("السعر قرب مستوى فيبوناتشي 38.2% (مقاومة)")

        if bearish_cross(ichi['tenkan'], ichi['kijun']):
            confidence += 5

        targets = TRADE_TARGETS["SWING"]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = min(senkou_b, price * (1 + targets['sl_pct'] / 100))

        risk_level = "LOW" if confidence >= 75 else "MEDIUM"
        return _make_signal(
            "Swing (Ichimoku+Fib+EMA+ADX)", "SELL", min(confidence, 92),
            ["Ichimoku", "Fibonacci", "EMA 50/200", "ADX"],
            price, sl, tp1, tp2, tp3, risk_level, "SWING",
            " • ".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════
# 7. SuperTrend Strategy
# ═══════════════════════════════════════════════════════════════

def supertrend_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "MEDIUM") -> Optional[Dict]:
    """
    استراتيجية SuperTrend - SuperTrend flips + ATR stops + ADX
    تتبع الاتجاه معstops ديناميكية
    """
    if len(df) < 30:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]

    st = ind['supertrend']
    st_dir = ind['supertrend_dir']
    adx_val = ind['adx'].iloc[-1]
    atr_val = ind['atr'].iloc[-1]

    prev_dir = st_dir.iloc[-2] if len(st_dir) > 1 else 0
    curr_dir = st_dir.iloc[-1]

    confidence = 0
    reasoning_parts = []

    # Bullish flip
    if curr_dir == 1 and prev_dir == -1:
        confidence = 65
        reasoning_parts.append("SuperTrend flip صاعد! (تحول من هابط إلى صاعد)")

        if adx_val > 25:
            confidence += 10
            reasoning_parts.append(f"ADX {adx_val:.0f} (اتجاه مؤكد)")

        if price > st.iloc[-1]:
            confidence += 5
            reasoning_parts.append(f"السعر فوق SuperTrend ({price:.6f} > {st.iloc[-1]:.6f})")

        # ATR volatility check
        atr_pct = (atr_val / price) * 100
        if atr_pct < 3:
            confidence += 5
            reasoning_parts.append(f"تقلب منخفض ATR {atr_pct:.1f}% (مدخل آمن)")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = st.iloc[-1]

        risk_level = "LOW" if confidence >= 75 else "MEDIUM"
        return _make_signal(
            "SuperTrend (ST+ATR+ADX)", "BUY", min(confidence, 88),
            ["SuperTrend", "ATR", "ADX"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    # Bearish flip
    elif curr_dir == -1 and prev_dir == 1:
        confidence = 65
        reasoning_parts.append("SuperTrend flip هابط! (تحول من صاعد إلى هابط)")

        if adx_val > 25:
            confidence += 10
            reasoning_parts.append(f"ADX {adx_val:.0f} (اتجاه هابط مؤكد)")

        if price < st.iloc[-1]:
            confidence += 5
            reasoning_parts.append(f"السعر تحت SuperTrend ({price:.6f} < {st.iloc[-1]:.6f})")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = st.iloc[-1]

        risk_level = "LOW" if confidence >= 75 else "MEDIUM"
        return _make_signal(
            "SuperTrend (ST+ATR+ADX)", "SELL", min(confidence, 88),
            ["SuperTrend", "ATR", "ADX"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════
# 8. Multi-Confluence Strategy (الإشارة الملكية)
# ═══════════════════════════════════════════════════════════════

def multi_confluence_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "MEDIUM") -> Optional[Dict]:
    """
    استراتيجية التقاء متعدد - تجمع 6+ مؤشرات لإشارات عالية الثقة
    تتطلب تأكيد من: EMA alignment, RSI, MACD, ADX, Bollinger, Volume, Ichimoku, SuperTrend
    """
    if len(df) < 120:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]

    # Collect all signals
    bull_scores = []
    bear_scores = []
    indicators_used = []
    reasoning_parts = []

    # 1. EMA alignment
    ema9 = ind['ema_9'].iloc[-1]
    ema21 = ind['ema_21'].iloc[-1]
    ema50 = ind['ema_50'].iloc[-1]
    ema200 = ind['ema_200'].iloc[-1] if not np.isnan(ind['ema_200'].iloc[-1]) else ema50

    if ema9 > ema21 > ema50 > ema200:
        bull_scores.append(15)
        indicators_used.append("EMA Alignment ✓")
        reasoning_parts.append("ترتيب EMA صاعد كامل (9>21>50>200)")
    elif ema9 < ema21 < ema50 < ema200:
        bear_scores.append(15)
        indicators_used.append("EMA Alignment ✓")
        reasoning_parts.append("ترتيب EMA هابط كامل (9<21<50<200)")

    # 2. RSI
    rsi_val = ind['rsi_14'].iloc[-1]
    if 50 < rsi_val < 70:
        bull_scores.append(10)
        indicators_used.append("RSI ✓")
        reasoning_parts.append(f"RSI {rsi_val:.0f} (زخم صاعد بدون تشبع)")
    elif 30 < rsi_val < 50:
        bear_scores.append(10)
        indicators_used.append("RSI ✓")
        reasoning_parts.append(f"RSI {rsi_val:.0f} (زخم هابط بدون تشبع)")

    # 3. MACD
    macd_hist = ind['macd_hist'].iloc[-1]
    macd_hist_prev = ind['macd_hist'].iloc[-2]
    if macd_hist > 0 and macd_hist > macd_hist_prev:
        bull_scores.append(12)
        indicators_used.append("MACD ✓")
        reasoning_parts.append("MACD histogram موجب ومتزايد")
    elif macd_hist < 0 and macd_hist < macd_hist_prev:
        bear_scores.append(12)
        indicators_used.append("MACD ✓")
        reasoning_parts.append("MACD histogram سالب ومتزايد هبوطاً")

    # 4. ADX
    adx_val = ind['adx'].iloc[-1]
    plus_di = ind['plus_di'].iloc[-1]
    minus_di = ind['minus_di'].iloc[-1]
    if adx_val > 25 and plus_di > minus_di:
        bull_scores.append(12)
        indicators_used.append("ADX ✓")
        reasoning_parts.append(f"ADX {adx_val:.0f} + DI+ > DI- (اتجاه صاعد قوي)")
    elif adx_val > 25 and minus_di > plus_di:
        bear_scores.append(12)
        indicators_used.append("ADX ✓")
        reasoning_parts.append(f"ADX {adx_val:.0f} + DI- > DI+ (اتجاه هابط قوي)")

    # 5. Bollinger position
    bb_middle = ind['bb_middle'].iloc[-1]
    bb_upper = ind['bb_upper'].iloc[-1]
    bb_lower = ind['bb_lower'].iloc[-1]
    if price > bb_middle and price < bb_upper:
        bull_scores.append(8)
        indicators_used.append("Bollinger ✓")
        reasoning_parts.append("السعر في النصف العلوي من Bollinger")
    elif price < bb_middle and price > bb_lower:
        bear_scores.append(8)
        indicators_used.append("Bollinger ✓")
        reasoning_parts.append("السعر في النصف السفلي من Bollinger")

    # 6. Volume
    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    current_vol = df['volume'].iloc[-1]
    if current_vol > vol_avg * 1.2:
        bull_scores.append(8) if macd_hist > 0 else None
        bear_scores.append(8) if macd_hist < 0 else None
        indicators_used.append("Volume ✓")
        reasoning_parts.append(f"حجم تداول مرتفع ({current_vol/vol_avg:.1f}x)")

    # 7. Ichimoku
    ichi = ind['ichimoku']
    senkou_a = ichi['senkou_a'].iloc[-1]
    senkou_b = ichi['senkou_b'].iloc[-1]
    if price > senkou_a and price > senkou_b and senkou_a > senkou_b:
        bull_scores.append(10)
        indicators_used.append("Ichimoku ✓")
        reasoning_parts.append("فوق سحابة Ichimoku الخضراء")
    elif price < senkou_a and price < senkou_b and senkou_a < senkou_b:
        bear_scores.append(10)
        indicators_used.append("Ichimoku ✓")
        reasoning_parts.append("تحت سحابة Ichimoku الحمراء")

    # 8. SuperTrend
    st_dir = ind['supertrend_dir'].iloc[-1]
    if st_dir == 1:
        bull_scores.append(8)
        indicators_used.append("SuperTrend ✓")
        reasoning_parts.append("SuperTrend صاعد")
    elif st_dir == -1:
        bear_scores.append(8)
        indicators_used.append("SuperTrend ✓")
        reasoning_parts.append("SuperTrend هابط")

    # 9. MFI
    mfi_val = ind['mfi'].iloc[-1]
    if mfi_val > 55:
        bull_scores.append(5)
        indicators_used.append("MFI ✓")
        reasoning_parts.append(f"MFI {mfi_val:.0f} (تدفق أموال صاعد)")
    elif mfi_val < 45:
        bear_scores.append(5)
        indicators_used.append("MFI ✓")
        reasoning_parts.append(f"MFI {mfi_val:.0f} (تدفق أموال هابط)")

    # 10. CCI
    cci_val = ind['cci'].iloc[-1]
    if 0 < cci_val < 100:
        bull_scores.append(5)
        indicators_used.append("CCI ✓")
    elif -100 < cci_val < 0:
        bear_scores.append(5)
        indicators_used.append("CCI ✓")

    # Calculate final confidence
    bull_total = sum(bull_scores)
    bear_total = sum(bear_scores)
    total_indicators = len(indicators_used)

    if total_indicators < 5:
        return None

    if bull_total > bear_total and bull_total >= 60:
        confidence = min(bull_total, 95)
        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = price * (1 - targets['sl_pct'] / 100)

        risk_level = "LOW" if confidence >= 80 else "MEDIUM" if confidence >= 60 else "HIGH"
        return _make_signal(
            f"Multi-Confluence ({total_indicators} indicators)", "BUY", confidence,
            indicators_used,
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            f"تجمع {total_indicators} مؤشرات على إشارة صاعدة\n" + "\n".join(reasoning_parts)
        )

    elif bear_total > bull_total and bear_total >= 60:
        confidence = min(bear_total, 95)
        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = price * (1 + targets['sl_pct'] / 100)

        risk_level = "LOW" if confidence >= 80 else "MEDIUM" if confidence >= 60 else "HIGH"
        return _make_signal(
            f"Multi-Confluence ({total_indicators} indicators)", "SELL", confidence,
            indicators_used,
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            f"تجمع {total_indicators} مؤشرات على إشارة هابطة\n" + "\n".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 9. VWAP Strategy
# ═══════════════════════════════════════════════════════════════

def vwap_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "MEDIUM") -> Optional[Dict]:
    """
    استراتيجية VWAP - متوسط السعر المرجح بالحجم
    BUY: السعر أكبر من VWAP ويرتد صعوداً
    SELL: السعر أصغر من VWAP ويرفض الارتفاع
    تعتمد الثقة على المسافة من VWAP وحجم التداول
    """
    if len(df) < 30:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]
    prev_close = df['close'].iloc[-2]
    prev_low = df['low'].iloc[-2]
    prev_high = df['high'].iloc[-2]

    vwap_series = ind['vwap']
    vwap_val = vwap_series.iloc[-1]
    vwap_prev = vwap_series.iloc[-2]

    if pd.isna(vwap_val) or vwap_val <= 0:
        return None

    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    current_vol = df['volume'].iloc[-1]

    distance_pct = abs(price - vwap_val) / vwap_val * 100

    confidence = 0
    reasoning_parts = []

    # Bounce check for BUY: touched or stayed near/below VWAP previously, now above
    is_bouncing = (prev_low <= vwap_prev * 1.003 or prev_close <= vwap_prev) and (price > vwap_val)
    
    # Reject check for SELL: touched or stayed near/above VWAP previously, now below
    is_rejecting = (prev_high >= vwap_prev * 0.997 or prev_close >= vwap_prev) and (price < vwap_val)

    if price > vwap_val and is_bouncing:
        confidence = 65
        reasoning_parts.append(f"السعر ({price:.6f}) أعلى من VWAP ({vwap_val:.6f}) مع ارتداد صاعد")

        if distance_pct <= 1.0:
            confidence += 10
            reasoning_parts.append(f"ارتداد من مسافة قريبة جداً من VWAP ({distance_pct:.2f}%)")
        elif distance_pct <= 2.5:
            confidence += 5
            reasoning_parts.append(f"مسافة ارتداد مناسبة من VWAP ({distance_pct:.2f}%)")

        if current_vol > vol_avg * 1.5:
            confidence += 10
            reasoning_parts.append(f"حجم تداول مرتفع يؤكد الارتداد ({current_vol/vol_avg:.1f}x المتوسط)")
        elif current_vol > vol_avg * 1.1:
            confidence += 5
            reasoning_parts.append("حجم تداول أعلى من المتوسط")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = min(vwap_val * 0.995, price * (1 - targets['sl_pct'] / 100))

        risk_level = "LOW" if confidence >= 75 else "MEDIUM"
        return _make_signal(
            "VWAP Strategy", "BUY", min(confidence, 92),
            ["VWAP", "Volume", "Price Action"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    elif price < vwap_val and is_rejecting:
        confidence = 65
        reasoning_parts.append(f"السعر ({price:.6f}) أدنى من VWAP ({vwap_val:.6f}) مع رفض صعودي")

        if distance_pct <= 1.0:
            confidence += 10
            reasoning_parts.append(f"رفض من مسافة قريبة جداً من VWAP ({distance_pct:.2f}%)")
        elif distance_pct <= 2.5:
            confidence += 5
            reasoning_parts.append(f"مسافة رفض مناسبة من VWAP ({distance_pct:.2f}%)")

        if current_vol > vol_avg * 1.5:
            confidence += 10
            reasoning_parts.append(f"حجم تداول مرتفع يؤكد الرفض ({current_vol/vol_avg:.1f}x المتوسط)")
        elif current_vol > vol_avg * 1.1:
            confidence += 5
            reasoning_parts.append("حجم تداول أعلى من المتوسط")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = max(vwap_val * 1.005, price * (1 + targets['sl_pct'] / 100))

        risk_level = "LOW" if confidence >= 75 else "MEDIUM"
        return _make_signal(
            "VWAP Strategy", "SELL", min(confidence, 92),
            ["VWAP", "Volume", "Price Action"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════
# 10. Ichimoku Cloud Strategy
# ═══════════════════════════════════════════════════════════════

def ichimoku_cloud_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "SWING") -> Optional[Dict]:
    """
    استراتيجية سحابة إيشيموكو - Ichimoku Cloud Strategy
    BUY: السعر أعلى السحابة (Senkou A > Senkou B) و Tenkan > Kijun
    SELL: السعر أسفل السحابة (Senkou A < Senkou B) و Tenkan < Kijun
    استراتيجية ذات ثقة عالية (High Confidence)
    """
    if len(df) < 52:
        return None

    ind = calculate_all_indicators(df)
    ich = ind['ichimoku']
    price = df['close'].iloc[-1]

    tenkan = ich['tenkan'].iloc[-1]
    kijun = ich['kijun'].iloc[-1]
    senkou_a = ich['senkou_a'].iloc[-1]
    senkou_b = ich['senkou_b'].iloc[-1]

    tenkan_prev = ich['tenkan'].iloc[-2]
    kijun_prev = ich['kijun'].iloc[-2]

    if pd.isna(senkou_a) or pd.isna(senkou_b) or pd.isna(tenkan) or pd.isna(kijun):
        return None

    cloud_top = max(senkou_a, senkou_b)
    cloud_bottom = min(senkou_a, senkou_b)

    confidence = 0
    reasoning_parts = []

    # BUY: price > cloud (Senkou A > Senkou B) and Tenkan > Kijun
    if price > cloud_top and senkou_a > senkou_b and tenkan > kijun:
        confidence = 78  # High confidence base strategy
        reasoning_parts.append(f"السعر ({price:.6f}) أعلى السحابة الخضراء (Senkou A > Senkou B)")
        reasoning_parts.append(f"Tenkan ({tenkan:.6f}) فوق Kijun ({kijun:.6f})")

        if tenkan_prev <= kijun_prev and tenkan > kijun:
            confidence += 10
            reasoning_parts.append("تقاطع Tenkan/Kijun صاعد حديث (TK Cross)")

        if price > cloud_top * 1.005:
            confidence += 5
            reasoning_parts.append("اختراق واضح وتأكيد فوق السحابة")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = min(kijun, cloud_bottom)
        if sl >= price:
            sl = price * (1 - targets['sl_pct'] / 100)

        risk_level = "LOW" if confidence >= 80 else "MEDIUM"
        return _make_signal(
            "Ichimoku Cloud Strategy", "BUY", min(confidence, 95),
            ["Ichimoku Cloud", "Tenkan/Kijun", "Senkou A/B"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    # SELL: price < cloud (Senkou A < Senkou B) and Tenkan < Kijun
    elif price < cloud_bottom and senkou_a < senkou_b and tenkan < kijun:
        confidence = 78  # High confidence base strategy
        reasoning_parts.append(f"السعر ({price:.6f}) أسفل السحابة الحمراء (Senkou A < Senkou B)")
        reasoning_parts.append(f"Tenkan ({tenkan:.6f}) تحت Kijun ({kijun:.6f})")

        if tenkan_prev >= kijun_prev and tenkan < kijun:
            confidence += 10
            reasoning_parts.append("تقاطع Tenkan/Kijun هابط حديث (TK Cross)")

        if price < cloud_bottom * 0.995:
            confidence += 5
            reasoning_parts.append("كسر واضح وتأكيد أسفل السحابة")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = max(kijun, cloud_top)
        if sl <= price:
            sl = price * (1 + targets['sl_pct'] / 100)

        risk_level = "LOW" if confidence >= 80 else "MEDIUM"
        return _make_signal(
            "Ichimoku Cloud Strategy", "SELL", min(confidence, 95),
            ["Ichimoku Cloud", "Tenkan/Kijun", "Senkou A/B"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════
# 11. CCI + Williams %R Strategy
# ═══════════════════════════════════════════════════════════════

def cci_williams_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "MEDIUM") -> Optional[Dict]:
    """
    استراتيجية CCI + Williams %R
    BUY: CCI < -100 (تشبع بيعي) و Williams %R < -80
    SELL: CCI > 100 (تشبع شرائي) و Williams %R > -20
    """
    if len(df) < 30:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]

    cci_series = ind['cci']
    wr_series = ind['williams_r']

    cci_val = cci_series.iloc[-1]
    cci_prev = cci_series.iloc[-2]
    wr_val = wr_series.iloc[-1]
    wr_prev = wr_series.iloc[-2]

    if pd.isna(cci_val) or pd.isna(wr_val):
        return None

    confidence = 0
    reasoning_parts = []

    # BUY: CCI < -100 and Williams %R < -80
    if cci_val < -100 and wr_val < -80:
        confidence = 64
        reasoning_parts.append(f"CCI في منطقة تشبع بيعي ({cci_val:.1f} < -100)")
        reasoning_parts.append(f"Williams %R في منطقة تشبع بيعي ({wr_val:.1f}% < -80%)")

        if cci_val < -150 or wr_val < -90:
            confidence += 9
            reasoning_parts.append("تشبع بيعي حاد جداً يوحي بانعكاس قريب")

        if cci_val > cci_prev and wr_val > wr_prev:
            confidence += 9
            reasoning_parts.append("بدء ارتداد إيجابي صاعد في المؤشرين")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = price * (1 - targets['sl_pct'] / 100)

        risk_level = "MEDIUM" if confidence < 75 else "LOW"
        return _make_signal(
            "CCI + Williams %R Strategy", "BUY", min(confidence, 88),
            ["CCI (20)", "Williams %R (14)"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    # SELL: CCI > 100 and Williams %R > -20
    elif cci_val > 100 and wr_val > -20:
        confidence = 64
        reasoning_parts.append(f"CCI في منطقة تشبع شرائي ({cci_val:.1f} > 100)")
        reasoning_parts.append(f"Williams %R في منطقة تشبع شرائي ({wr_val:.1f}% > -20%)")

        if cci_val > 150 or wr_val > -10:
            confidence += 9
            reasoning_parts.append("تشبع شرائي حاد جداً يوحي بانعكاس قريب")

        if cci_val < cci_prev and wr_val < wr_prev:
            confidence += 9
            reasoning_parts.append("بدء تصحيح هابط في المؤشرين")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = price * (1 + targets['sl_pct'] / 100)

        risk_level = "MEDIUM" if confidence < 75 else "LOW"
        return _make_signal(
            "CCI + Williams %R Strategy", "SELL", min(confidence, 88),
            ["CCI (20)", "Williams %R (14)"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════
# 12. Parabolic SAR Strategy
# ═══════════════════════════════════════════════════════════════

def parabolic_sar_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "MEDIUM") -> Optional[Dict]:
    """
    استراتيجية Parabolic SAR + ADX
    BUY: انقلاب PSAR من أعلى السعر إلى أسفله (Bullish flip) مع فلتر ADX للاتجاه
    SELL: انقلاب PSAR من أسفل السعر إلى أعلاه (Bearish flip) مع فلتر ADX للاتجاه
    """
    if len(df) < 30:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]
    prev_price = df['close'].iloc[-2]

    psar_series = ind['psar']
    psar_curr = psar_series.iloc[-1]
    psar_prev = psar_series.iloc[-2]

    adx_val = ind['adx'].iloc[-1]

    if pd.isna(psar_curr) or pd.isna(psar_prev) or pd.isna(adx_val):
        return None

    # Bullish flip: prev PSAR was above prev price, curr PSAR is below curr price
    bullish_flip = (psar_prev > prev_price) and (psar_curr < price)

    # Bearish flip: prev PSAR was below prev price, curr PSAR is above curr price
    bearish_flip = (psar_prev < prev_price) and (psar_curr > price)

    confidence = 0
    reasoning_parts = []

    if bullish_flip and adx_val > 20:
        confidence = 66
        reasoning_parts.append(f"انقلاب Parabolic SAR لصالح الشراء (SAR={psar_curr:.6f} < السعر)")
        reasoning_parts.append(f"مؤشر ADX يؤكد قوة الاتجاه ({adx_val:.0f} > 20)")

        if adx_val > 30:
            confidence += 10
            reasoning_parts.append(f"اتجاه قوي جداً (ADX {adx_val:.0f})")
        elif adx_val > 25:
            confidence += 5

        ema50 = ind['ema_50'].iloc[-1] if 'ema_50' in ind else None
        if ema50 is not None and price > ema50:
            confidence += 8
            reasoning_parts.append("السعر فوق EMA 50 (محاذاة الاتجاه)")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = min(psar_curr, price * (1 - targets['sl_pct'] / 100))

        risk_level = "LOW" if confidence >= 75 else "MEDIUM"
        return _make_signal(
            "Parabolic SAR Strategy", "BUY", min(confidence, 90),
            ["Parabolic SAR", "ADX", "EMA 50"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    elif bearish_flip and adx_val > 20:
        confidence = 66
        reasoning_parts.append(f"انقلاب Parabolic SAR لصالح البيع (SAR={psar_curr:.6f} > السعر)")
        reasoning_parts.append(f"مؤشر ADX يؤكد قوة الاتجاه الهابط ({adx_val:.0f} > 20)")

        if adx_val > 30:
            confidence += 10
            reasoning_parts.append(f"اتجاه هابط قوي جداً (ADX {adx_val:.0f})")
        elif adx_val > 25:
            confidence += 5

        ema50 = ind['ema_50'].iloc[-1] if 'ema_50' in ind else None
        if ema50 is not None and price < ema50:
            confidence += 8
            reasoning_parts.append("السعر تحت EMA 50 (محاذاة الاتجاه)")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = max(psar_curr, price * (1 + targets['sl_pct'] / 100))

        risk_level = "LOW" if confidence >= 75 else "MEDIUM"
        return _make_signal(
            "Parabolic SAR Strategy", "SELL", min(confidence, 90),
            ["Parabolic SAR", "ADX", "EMA 50"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    return None


# ═══════════════════════════════════════════════════════════════
# 13. Volume Breakout Strategy
# ═══════════════════════════════════════════════════════════════

def volume_breakout_strategy(df: pd.DataFrame, symbol: str, trade_type: str = "SWING") -> Optional[Dict]:
    """
    استراتيجية اختراق الحجم - OBV + Volume Surge + Breakout
    BUY: اختراق OBV + ارتفاع حجم التداول + اختراق أعلى قمة سابقة
    SELL: كسر OBV + ارتفاع حجم التداول + كسر أدنى قاع سابق
    """
    if len(df) < 30:
        return None

    ind = calculate_all_indicators(df)
    price = df['close'].iloc[-1]

    obv_series = ind['obv']
    obv_curr = obv_series.iloc[-1]
    obv_high = obv_series.rolling(20).max().iloc[-2]
    obv_low = obv_series.rolling(20).min().iloc[-2]

    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    current_vol = df['volume'].iloc[-1]

    recent_high = df['high'].rolling(20).max().iloc[-2]
    recent_low = df['low'].rolling(20).min().iloc[-2]

    if pd.isna(obv_curr) or pd.isna(obv_high) or pd.isna(obv_low) or vol_avg <= 0:
        return None

    volume_surge = current_vol > vol_avg * 1.3
    obv_breakout = obv_curr > obv_high
    obv_breakdown = obv_curr < obv_low
    price_breakout = price > recent_high
    price_breakdown = price < recent_low

    confidence = 0
    reasoning_parts = []

    # BUY: OBV breaks out + volume surge + price breaks recent high
    if price_breakout and volume_surge and obv_breakout:
        confidence = 68
        reasoning_parts.append(f"اختراق قمة 20 شمعة ({price:.6f} > {recent_high:.6f})")
        reasoning_parts.append(f"ارتفاع حجم التداول ({current_vol/vol_avg:.1f}x المتوسط)")
        reasoning_parts.append("مؤشر OBV يسجل قمة جديدة مؤكداً التدفق الشرائي")

        if current_vol > vol_avg * 2.0:
            confidence += 10
            reasoning_parts.append("حجم اختراق استثنائي (Surge > 2.0x)")
        elif current_vol > vol_avg * 1.6:
            confidence += 5

        if obv_high > 0 and obv_curr > obv_high * 1.05:
            confidence += 8
            reasoning_parts.append("اختراق OBV قوي جداً")

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 + targets['tp1_pct'] / 100)
        tp2 = price * (1 + targets['tp2_pct'] / 100)
        tp3 = price * (1 + targets['tp3_pct'] / 100)
        sl = recent_low

        risk_level = "LOW" if confidence >= 78 else "MEDIUM"
        return _make_signal(
            "Volume Breakout Strategy", "BUY", min(confidence, 92),
            ["OBV", "Volume", "Price Breakout"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    # SELL: OBV breaks down + volume surge + price breaks recent low
    elif price_breakdown and volume_surge and obv_breakdown:
        confidence = 68
        reasoning_parts.append(f"كسر قاع 20 شمعة ({price:.6f} < {recent_low:.6f})")
        reasoning_parts.append(f"ارتفاع حجم التداول ({current_vol/vol_avg:.1f}x المتوسط)")
        reasoning_parts.append("مؤشر OBV يسجل قاع جديد مؤكداً التدفق البيعي")

        if current_vol > vol_avg * 2.0:
            confidence += 10
            reasoning_parts.append("حجم كسر استثنائي (Surge > 2.0x)")
        elif current_vol > vol_avg * 1.6:
            confidence += 5

        targets = TRADE_TARGETS[trade_type]
        tp1 = price * (1 - targets['tp1_pct'] / 100)
        tp2 = price * (1 - targets['tp2_pct'] / 100)
        tp3 = price * (1 - targets['tp3_pct'] / 100)
        sl = recent_high

        risk_level = "LOW" if confidence >= 78 else "MEDIUM"
        return _make_signal(
            "Volume Breakout Strategy", "SELL", min(confidence, 92),
            ["OBV", "Volume", "Price Breakout"],
            price, sl, tp1, tp2, tp3, risk_level, trade_type,
            " • ".join(reasoning_parts)
        )

    return None

# Strategy Registry
# ═══════════════════════════════════════════════════════════════

ALL_STRATEGIES = {
    "trend_following": {
        "func": trend_following_strategy,
        "trade_type": "MEDIUM",
        "name_ar": "تتبع الاتجاه",
    },
    "mean_reversion": {
        "func": mean_reversion_strategy,
        "trade_type": "MEDIUM",
        "name_ar": "العودة للمتوسط",
    },
    "momentum": {
        "func": momentum_strategy,
        "trade_type": "MEDIUM",
        "name_ar": "الزخم",
    },
    "breakout": {
        "func": breakout_strategy,
        "trade_type": "SWING",
        "name_ar": "الاختراق",
    },
    "scalping": {
        "func": scalping_strategy,
        "trade_type": "SCALPING",
        "name_ar": "السكالبينج السريع",
    },
    "swing": {
        "func": swing_strategy,
        "trade_type": "SWING",
        "name_ar": "السوينج",
    },
    "supertrend": {
        "func": supertrend_strategy,
        "trade_type": "MEDIUM",
        "name_ar": "السوبر ترند",
    },
    "multi_confluence": {
        "func": multi_confluence_strategy,
        "trade_type": "MEDIUM",
        "name_ar": "التقاء متعدد (الإشارة الملكية)",
    },
    "vwap": {
        "func": vwap_strategy,
        "trade_type": "MEDIUM",
        "name_ar": "استراتيجية VWAP",
    },
    "ichimoku": {
        "func": ichimoku_cloud_strategy,
        "trade_type": "SWING",
        "name_ar": "سحابة إيشيموكو",
    },
    "cci_williams": {
        "func": cci_williams_strategy,
        "trade_type": "MEDIUM",
        "name_ar": "CCI و Williams %R",
    },
    "parabolic_sar": {
        "func": parabolic_sar_strategy,
        "trade_type": "MEDIUM",
        "name_ar": "Parabolic SAR مع ADX",
    },
    "volume_breakout": {
        "func": volume_breakout_strategy,
        "trade_type": "SWING",
        "name_ar": "اختراق الحجم و OBV",
    },
}
