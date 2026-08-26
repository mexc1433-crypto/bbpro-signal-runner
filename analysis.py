"""
BBPro Signal Bot - Market Analysis
تحليل سوق الذهب (XAU/USD) المتقدم - متعدد الأطر الزمنية
"""
import pandas as pd
import numpy as np
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from market_data import MarketDataFetcher
from indicators import calculate_all_indicators, rsi, ema, adx, macd, atr
from config import TRADING_PAIRS, TIMEFRAMES, GOLD_DISPLAY_NAME

logger = logging.getLogger(__name__)


class MarketAnalyzer:
    """تحليل سوق الذهب المتقدم"""

    def __init__(self, fetcher: MarketDataFetcher):
        self.fetcher = fetcher

    def analyze_pair(self, symbol: str, timeframe: str = '4h') -> Dict:
        """
        تحليل كامل لزوج الذهب
        """
        df = self.fetcher.fetch_ohlcv(symbol, timeframe, 200)
        if df.empty or len(df) < 50:
            return {}

        ind = calculate_all_indicators(df)
        price = float(df['close'].iloc[-1])

        # Trend
        trend, trend_strength = self.calculate_trend_strength(df, ind)

        # Support/Resistance
        support, resistance = self.fetcher.get_support_resistance(df)

        # Pivot points
        pivots = self.fetcher.get_pivot_points(df)

        # Volatility (ATR as % of price)
        atr_val = float(ind['atr'].iloc[-1])
        volatility_pct = (atr_val / price) * 100

        # Volume analysis
        vol_avg = df['volume'].rolling(20).mean().iloc[-1]
        current_vol = df['volume'].iloc[-1]
        vol_status = "مرتفع" if current_vol > vol_avg * 1.5 else "منخفض" if current_vol < vol_avg * 0.5 else "طبيعي"

        # Signal from indicators
        bull_count = 0
        bear_count = 0
        indicator_signals = {}

        # RSI
        rsi_val = float(ind['rsi_14'].iloc[-1])
        if rsi_val > 55:
            bull_count += 1
            indicator_signals['rsi'] = f"صاعد ({rsi_val:.0f})"
        elif rsi_val < 45:
            bear_count += 1
            indicator_signals['rsi'] = f"هابط ({rsi_val:.0f})"
        else:
            indicator_signals['rsi'] = f"محايد ({rsi_val:.0f})"

        # MACD
        macd_hist = float(ind['macd_hist'].iloc[-1])
        if macd_hist > 0:
            bull_count += 1
            indicator_signals['macd'] = "صاعد"
        else:
            bear_count += 1
            indicator_signals['macd'] = "هابط"

        # EMA
        ema50 = float(ind['ema_50'].iloc[-1])
        ema200 = float(ind['ema_200'].iloc[-1]) if not np.isnan(ind['ema_200'].iloc[-1]) else ema50
        if price > ema50 and ema50 > ema200:
            bull_count += 1
            indicator_signals['ema'] = "صاعد (فوق EMA50 و EMA200)"
        elif price < ema50 and ema50 < ema200:
            bear_count += 1
            indicator_signals['ema'] = "هابط (تحت EMA50 و EMA200)"
        else:
            indicator_signals['ema'] = "مختلط"

        # ADX
        adx_val = float(ind['adx'].iloc[-1])
        plus_di = float(ind['plus_di'].iloc[-1])
        minus_di = float(ind['minus_di'].iloc[-1])
        if plus_di > minus_di and adx_val > 25:
            bull_count += 1
            indicator_signals['adx'] = f"صاعد قوي ({adx_val:.0f})"
        elif minus_di > plus_di and adx_val > 25:
            bear_count += 1
            indicator_signals['adx'] = f"هابط قوي ({adx_val:.0f})"
        else:
            indicator_signals['adx'] = f"ضعيف ({adx_val:.0f})"

        # SuperTrend
        st_dir = float(ind['supertrend_dir'].iloc[-1])
        if st_dir == 1:
            bull_count += 1
            indicator_signals['supertrend'] = "صاعد"
        else:
            bear_count += 1
            indicator_signals['supertrend'] = "هابط"

        # Ichimoku
        ichi = ind['ichimoku']
        senkou_a = float(ichi['senkou_a'].iloc[-1])
        senkou_b = float(ichi['senkou_b'].iloc[-1])
        if price > senkou_a and price > senkou_b:
            bull_count += 1
            indicator_signals['ichimoku'] = "فوق السحابة (صاعد)"
        elif price < senkou_a and price < senkou_b:
            bear_count += 1
            indicator_signals['ichimoku'] = "تحت السحابة (هابط)"
        else:
            indicator_signals['ichimoku'] = "داخل السحابة (محايد)"

        # Stochastic
        stoch_k = float(ind['stoch_k'].iloc[-1])
        if stoch_k > 50:
            bull_count += 1
            indicator_signals['stochastic'] = f"صاعد ({stoch_k:.0f})"
        else:
            bear_count += 1
            indicator_signals['stochastic'] = f"هابط ({stoch_k:.0f})"

        # Bollinger Bands
        bb_upper = float(ind['bb_upper'].iloc[-1])
        bb_lower = float(ind['bb_lower'].iloc[-1])
        if price > bb_upper:
            bull_count += 1
            indicator_signals['bollinger'] = "فوق النطاق العلوي (تشبع شرائي)"
        elif price < bb_lower:
            bear_count += 1
            indicator_signals['bollinger'] = "تحت النطاق السفلي (تشبع بيعي)"
        else:
            indicator_signals['bollinger'] = "داخل النطاق (طبيعي)"

        # CCI (if available)
        if 'cci' in ind:
            cci_val = float(ind['cci'].iloc[-1])
            if cci_val > 100:
                bull_count += 1
                indicator_signals['cci'] = f"صاعد قوي ({cci_val:.0f})"
            elif cci_val < -100:
                bear_count += 1
                indicator_signals['cci'] = f"هابط قوي ({cci_val:.0f})"
            else:
                indicator_signals['cci'] = f"محايد ({cci_val:.0f})"

        # CMF (if available)
        if 'cmf' in ind:
            cmf_val = float(ind['cmf'].iloc[-1])
            if cmf_val > 0.1:
                bull_count += 1
                indicator_signals['cmf'] = f"تدفق أموال صاعد ({cmf_val:.2f})"
            elif cmf_val < -0.1:
                bear_count += 1
                indicator_signals['cmf'] = f"تدفق أموال هابط ({cmf_val:.2f})"
            else:
                indicator_signals['cmf'] = f"محايد ({cmf_val:.2f})"

        # Determine signal
        total = bull_count + bear_count
        if total > 0 and bull_count > bear_count + 2:
            signal = "BUY"
            confidence = (bull_count / total) * 100
        elif total > 0 and bear_count > bull_count + 2:
            signal = "SELL"
            confidence = (bear_count / total) * 100
        else:
            signal = "HOLD"
            confidence = 50

        # Recommendation (Arabic)
        if signal == "BUY":
            rec = f"الذهب ({symbol}) يظهر قوة صاعدة مع {bull_count} مؤشرات صاعدة مقابل {bear_count} هابطة. يفضل البحث عن فرص شراء عند التصحيح نحو الدعوم."
        elif signal == "SELL":
            rec = f"الذهب ({symbol}) يظهر ضعف مع {bear_count} مؤشرات هابطة مقابل {bull_count} صاعدة. يفضل الحذر والبحث عن فرق بيع."
        else:
            rec = f"الذهب ({symbol}) في وضع محايد. يفضل الانتظار حتى يتضح الاتجاه."

        return {
            'symbol': symbol,
            'current_price': round(price, 2),
            'trend': trend,
            'trend_strength': trend_strength,
            'support_levels': [round(s, 2) for s in support],
            'resistance_levels': [round(r, 2) for r in resistance],
            'indicator_summary': indicator_signals,
            'signal': signal,
            'confidence': round(confidence, 1),
            'volatility': round(volatility_pct, 2),
            'volume_analysis': vol_status,
            'fibonacci_levels': {k: round(v, 2) for k, v in ind['fibonacci'].items()},
            'pivot_points': pivots,
            'bull_count': bull_count,
            'bear_count': bear_count,
            'recommendation': rec,
        }

    def analyze_market_sentiment(self) -> Dict:
        """تحليل معنويات سوق الذهب"""
        overview = self.fetcher.get_market_overview()
        fear_greed = self.fetcher.get_fear_greed_index()

        gold_price = overview.get('gold_price', 0)
        gold_change = overview.get('gold_change', 0)
        vix = overview.get('vix', 0)
        dxy = overview.get('dxy', 0)

        # Sentiment based on VIX + Gold movement + Fear/Greed
        sentiment_score = 50  # neutral start

        if vix > 25:
            sentiment_score -= 15  # خوف عالي = هابط للذهب قصير المدى لكن صاعد طويل المدى
        elif vix < 15:
            sentiment_score += 10

        if gold_change > 0.5:
            sentiment_score += 15
        elif gold_change < -0.5:
            sentiment_score -= 15

        if fear_greed is not None:
            if fear_greed > 60:
                sentiment_score += 5
            elif fear_greed < 40:
                sentiment_score -= 5

        # DXY impact (عكسي مع الذهب)
        if dxy > 0:
            sentiment_score -= 5  # دولار قوي = ذهب ضعيف

        sentiment_score = max(0, min(100, sentiment_score))

        if sentiment_score > 65:
            sentiment = "BULLISH"
        elif sentiment_score < 35:
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"

        # Build recommendation
        rec_parts = []
        rec_parts.append(f"الذهب عند ${gold_price:.2f} ({gold_change:+.2f}%)")
        if vix:
            rec_parts.append(f"VIX: {vix:.1f} ({overview.get('vix_label', '')})")
        if dxy:
            rec_parts.append(f"مؤشر الدولار: {dxy:.2f}")
        if fear_greed is not None:
            rec_parts.append(f"مؤشر الخوف والطمع: {fear_greed}")

        return {
            'sentiment': sentiment,
            'sentiment_score': round(sentiment_score, 1),
            'gold_price': gold_price,
            'gold_change': gold_change,
            'vix': vix,
            'dxy': dxy,
            'fear_greed': fear_greed,
            'market_breadth': (0, 0),
            'recommendation': " | ".join(rec_parts),
        }

    def get_multi_timeframe_analysis(self, symbol: str) -> Dict:
        """
        تحليل متعدد الأطر الزمنية للذهب - يبحث عن التوافق (confluence)
        """
        timeframes = ['5m', '15m', '1h', '4h', '1d']
        results = {}
        bullish_tfs = 0
        bearish_tfs = 0

        for tf in timeframes:
            df = self.fetcher.fetch_ohlcv(symbol, tf, 200)
            if df.empty or len(df) < 50:
                continue

            ind = calculate_all_indicators(df)
            price = float(df['close'].iloc[-1])

            # Quick trend check
            ema9 = float(ind['ema_9'].iloc[-1])
            ema21 = float(ind['ema_21'].iloc[-1])
            ema50 = float(ind['ema_50'].iloc[-1])
            macd_hist = float(ind['macd_hist'].iloc[-1])

            if ema9 > ema21 and price > ema50 and macd_hist > 0:
                results[tf] = "BULLISH"
                bullish_tfs += 1
            elif ema9 < ema21 and price < ema50 and macd_hist < 0:
                results[tf] = "BEARISH"
                bearish_tfs += 1
            else:
                results[tf] = "NEUTRAL"

        total_tfs = len(results)

        # Confluence
        if bullish_tfs >= 3:
            overall = "BULLISH"
            confidence = (bullish_tfs / total_tfs) * 100
        elif bearish_tfs >= 3:
            overall = "BEARISH"
            confidence = (bearish_tfs / total_tfs) * 100
        else:
            overall = "NEUTRAL"
            confidence = 50

        return {
            'symbol': symbol,
            'timeframe_signals': results,
            'overall': overall,
            'confidence': round(confidence, 1),
            'bullish_tfs': bullish_tfs,
            'bearish_tfs': bearish_tfs,
            'recommendation': f"توافق {bullish_tfs}/{total_tfs} أطر زمنية صاعدة و {bearish_tfs} هابطة" if overall == "BULLISH"
                              else f"توافق {bearish_tfs}/{total_tfs} أطر زمنية هابطة و {bullish_tfs} صاعدة" if overall == "BEARISH"
                              else "لا يوجد توافق واضح - السوق محايد"
        }

    def calculate_trend_strength(self, df: pd.DataFrame, ind: Dict) -> Tuple[str, float]:
        """يحسب قوة الاتجاه"""
        adx_val = float(ind['adx'].iloc[-1])
        plus_di = float(ind['plus_di'].iloc[-1])
        minus_di = float(ind['minus_di'].iloc[-1])

        ema9 = float(ind['ema_9'].iloc[-1])
        ema21 = float(ind['ema_21'].iloc[-1])
        ema50 = float(ind['ema_50'].iloc[-1])
        price = float(df['close'].iloc[-1])

        # Score the trend
        score = 0

        # ADX contribution
        if adx_val > 30:
            score += 30
        elif adx_val > 20:
            score += 15

        # EMA alignment
        if ema9 > ema21 > ema50:
            score += 20
        elif ema9 > ema21:
            score += 10

        # Price vs EMA50
        if price > ema50:
            score += 15

        # DI direction
        if plus_di > minus_di:
            score += 15

        # RSI direction
        rsi_val = float(ind['rsi_14'].iloc[-1])
        if rsi_val > 50:
            score += 10

        # MACD
        macd_hist = float(ind['macd_hist'].iloc[-1])
        if macd_hist > 0:
            score += 10

        # Determine trend direction
        if score >= 60:
            trend = "صاعد قوي"
        elif score >= 40:
            trend = "صاعد"
        elif score <= 20:
            trend = "هابط قوي"
        elif score <= 35:
            trend = "هابط"
        else:
            trend = "عرضي"

        return trend, round(score, 1)

    def get_gold_specific_levels(self, df: pd.DataFrame) -> Dict:
        """مستويات ذهب محددة - أرقام مهمة"""
        price = float(df['close'].iloc[-1])

        # Gold key levels (psychological + round numbers)
        key_levels = []
        for base in [4400, 4500, 4600, 4700, 4800, 4900, 5000]:
            for offset in [-50, -20, 0, 20, 50]:
                level = base + offset
                if abs(level - price) < 300:
                    key_levels.append(level)

        # Previous day high/low
        if len(df) >= 2:
            prev_day = df.iloc[-1]
            pdh = float(prev_day['high'])
            pdl = float(prev_day['low'])
        else:
            pdh = pdl = price

        # Weekly high/low (last 7 candles on daily)
        weekly_df = df.tail(7) if len(df) >= 7 else df
        wh = float(weekly_df['high'].max())
        wl = float(weekly_df['low'].min())

        return {
            'key_levels': sorted(key_levels),
            'prev_day_high': round(pdh, 2),
            'prev_day_low': round(pdl, 2),
            'weekly_high': round(wh, 2),
            'weekly_low': round(wl, 2),
        }
