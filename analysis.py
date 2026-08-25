"""
BBPro Signal Bot - Market Analysis
تحليل السوق المتقدم - متعدد الأطر الزمنية
"""
import pandas as pd
import numpy as np
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from market_data import MarketDataFetcher
from indicators import calculate_all_indicators, rsi, ema, adx, macd, atr
from config import TRADING_PAIRS, TIMEFRAMES

logger = logging.getLogger(__name__)


class MarketAnalyzer:
    """تحليل السوق المتقدم"""

    def __init__(self, fetcher: MarketDataFetcher):
        self.fetcher = fetcher

    def analyze_pair(self, symbol: str, timeframe: str = '4h') -> Dict:
        """
        تحليل كامل لزوج واحد
        """
        df = self.fetcher.fetch_ohlcv(symbol, timeframe, 200)
        if df.empty or len(df) < 50:
            return {}

        ind = calculate_all_indicators(df)
        price = df['close'].iloc[-1]

        # Trend
        trend, trend_strength = self.calculate_trend_strength(df, ind)

        # Support/Resistance
        support, resistance = self.fetcher.get_support_resistance(df)

        # Pivot points
        pivots = self.fetcher.get_pivot_points(df)

        # Volatility
        atr_val = ind['atr'].iloc[-1]
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
        rsi_val = ind['rsi_14'].iloc[-1]
        if rsi_val > 55:
            bull_count += 1
            indicator_signals['rsi'] = f"صاعد ({rsi_val:.0f})"
        elif rsi_val < 45:
            bear_count += 1
            indicator_signals['rsi'] = f"هابط ({rsi_val:.0f})"
        else:
            indicator_signals['rsi'] = f"محايد ({rsi_val:.0f})"

        # MACD
        macd_hist = ind['macd_hist'].iloc[-1]
        if macd_hist > 0:
            bull_count += 1
            indicator_signals['macd'] = "صاعد"
        else:
            bear_count += 1
            indicator_signals['macd'] = "هابط"

        # EMA
        ema50 = ind['ema_50'].iloc[-1]
        ema200 = ind['ema_200'].iloc[-1] if not np.isnan(ind['ema_200'].iloc[-1]) else ema50
        if price > ema50 and ema50 > ema200:
            bull_count += 1
            indicator_signals['ema'] = "صاعد (فوق EMA50 و EMA200)"
        elif price < ema50 and ema50 < ema200:
            bear_count += 1
            indicator_signals['ema'] = "هابط (تحت EMA50 و EMA200)"
        else:
            indicator_signals['ema'] = "مختلط"

        # ADX
        adx_val = ind['adx'].iloc[-1]
        plus_di = ind['plus_di'].iloc[-1]
        minus_di = ind['minus_di'].iloc[-1]
        if plus_di > minus_di and adx_val > 25:
            bull_count += 1
            indicator_signals['adx'] = f"صاعد قوي ({adx_val:.0f})"
        elif minus_di > plus_di and adx_val > 25:
            bear_count += 1
            indicator_signals['adx'] = f"هابط قوي ({adx_val:.0f})"
        else:
            indicator_signals['adx'] = f"ضعيف ({adx_val:.0f})"

        # SuperTrend
        st_dir = ind['supertrend_dir'].iloc[-1]
        if st_dir == 1:
            bull_count += 1
            indicator_signals['supertrend'] = "صاعد"
        else:
            bear_count += 1
            indicator_signals['supertrend'] = "هابط"

        # Ichimoku
        ichi = ind['ichimoku']
        senkou_a = ichi['senkou_a'].iloc[-1]
        senkou_b = ichi['senkou_b'].iloc[-1]
        if price > senkou_a and price > senkou_b:
            bull_count += 1
            indicator_signals['ichimoku'] = "فوق السحابة (صاعد)"
        elif price < senkou_a and price < senkou_b:
            bear_count += 1
            indicator_signals['ichimoku'] = "تحت السحابة (هابط)"
        else:
            indicator_signals['ichimoku'] = "داخل السحابة (محايد)"

        # Stochastic
        stoch_k = ind['stoch_k'].iloc[-1]
        if stoch_k > 50:
            bull_count += 1
            indicator_signals['stochastic'] = f"صاعد ({stoch_k:.0f})"
        else:
            bear_count += 1
            indicator_signals['stochastic'] = f"هابط ({stoch_k:.0f})"

        # Determine signal
        if bull_count > bear_count + 2:
            signal = "BUY"
            confidence = (bull_count / (bull_count + bear_count)) * 100
        elif bear_count > bull_count + 2:
            signal = "SELL"
            confidence = (bear_count / (bull_count + bear_count)) * 100
        else:
            signal = "HOLD"
            confidence = 50

        # Recommendation (Arabic)
        if signal == "BUY":
            rec = f"الزوج {symbol} يظهر قوة صاعدة مع {bull_count} مؤشرات صاعدة مقابل {bear_count} هابطة. يفضل البحث عن فرص شراء عند التصحيح نحو الدعوم."
        elif signal == "SELL":
            rec = f"الزوج {symbol} يظهر ضعف مع {bear_count} مؤشرات هابطة مقابل {bull_count} صاعدة. يفضل الحذر والبحث عن فرق بيع."
        else:
            rec = f"الزوج {symbol} في وضع محايد. يفضل الانتظار حتى يتضح الاتجاه."

        return {
            'symbol': symbol,
            'current_price': round(price, 6),
            'trend': trend,
            'trend_strength': trend_strength,
            'support_levels': [round(s, 6) for s in support],
            'resistance_levels': [round(r, 6) for r in resistance],
            'indicator_summary': indicator_signals,
            'signal': signal,
            'confidence': round(confidence, 1),
            'volatility': round(volatility_pct, 2),
            'volume_analysis': vol_status,
            'fibonacci_levels': {k: round(v, 6) for k, v in ind['fibonacci'].items()},
            'pivot_points': pivots,
            'bull_count': bull_count,
            'bear_count': bear_count,
            'recommendation': rec,
        }

    def analyze_market_sentiment(self) -> Dict:
        """تحليل معنويات السوق العامة"""
        overview = self.fetcher.get_market_overview()
        fear_greed = self.fetcher.get_fear_greed_index()
        gainers = self.fetcher.get_top_gainers(10)
        losers = self.fetcher.get_top_losers(10)

        # Market breadth
        bullish_count = 0
        bearish_count = 0
        for g in gainers:
            if g.get('change', 0) > 0:
                bullish_count += 1
        for l in losers:
            if l.get('change', 0) < 0:
                bearish_count += 1

        # Sentiment
        if fear_greed is not None:
            if fear_greed > 60:
                sentiment = "BULLISH"
            elif fear_greed < 40:
                sentiment = "BEARISH"
            else:
                sentiment = "NEUTRAL"
        else:
            sentiment = "NEUTRAL"

        return {
            'sentiment': sentiment,
            'trend_strength': min(abs(fear_greed - 50) * 2, 100) if fear_greed else 50,
            'btc_price': overview.get('btc_price'),
            'btc_change': overview.get('btc_change'),
            'eth_price': overview.get('eth_price'),
            'eth_change': overview.get('eth_change'),
            'fear_greed': fear_greed,
            'top_gainers': gainers,
            'top_losers': losers,
            'market_breadth': (bullish_count, bearish_count),
            'recommendation': f"معنويات السوق: {sentiment}. مؤشر الخوف والطمع: {fear_greed}" if fear_greed else "لم تتوفر بيانات الخوف والطمع",
        }

    def get_multi_timeframe_analysis(self, symbol: str) -> Dict:
        """
        تحليل متعدد الأطر الزمنية - يبحث عن التوافق (confluence)
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
            price = df['close'].iloc[-1]

            # Quick trend check
            ema9 = ind['ema_9'].iloc[-1]
            ema21 = ind['ema_21'].iloc[-1]
            ema50 = ind['ema_50'].iloc[-1]
            rsi_val = ind['rsi_14'].iloc[-1]
            macd_hist = ind['macd_hist'].iloc[-1]

            if ema9 > ema21 and price > ema50 and macd_hist > 0:
                results[tf] = "BULLISH"
                bullish_tfs += 1
            elif ema9 < ema21 and price < ema50 and macd_hist < 0:
                results[tf] = "BEARISH"
                bearish_tfs += 1
            else:
                results[tf] = "NEUTRAL"

        # Confluence
        if bullish_tfs >= 3:
            overall = "BULLISH"
            confidence = (bullish_tfs / len(timeframes)) * 100
        elif bearish_tfs >= 3:
            overall = "BEARISH"
            confidence = (bearish_tfs / len(timeframes)) * 100
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
            'recommendation': f"توافق {bullish_tfs}/{len(timeframes)} أطر زمنية صاعدة و {bearish_tfs} هابطة" if overall == "BULLISH"
                              else f"توافق {bearish_tfs}/{len(timeframes)} أطر زمنية هابطة و {bullish_tfs} صاعدة" if overall == "BEARISH"
                              else "لا يوجد توافق واضح - السوق محايد"
        }

    def calculate_trend_strength(self, df: pd.DataFrame, ind: Dict) -> Tuple[str, float]:
        """يحسب قوة الاتجاه"""
        adx_val = ind['adx'].iloc[-1]
        plus_di = ind['plus_di'].iloc[-1]
        minus_di = ind['minus_di'].iloc[-1]

        ema9 = ind['ema_9'].iloc[-1]
        ema21 = ind['ema_21'].iloc[-1]
        ema50 = ind['ema_50'].iloc[-1]
        price = df['close'].iloc[-1]

        # Score the trend
        score = 0

        # ADX contribution
        if adx_val > 40:
            score += 30
        elif adx_val > 25:
            score += 20
        elif adx_val > 20:
            score += 10

        # DI contribution
        if plus_di > minus_di:
            score += 10
        else:
            score -= 10

        # EMA alignment
        if ema9 > ema21 > ema50:
            score += 15
        elif ema9 < ema21 < ema50:
            score -= 15

        # Price vs EMA
        if price > ema50:
            score += 10
        else:
            score -= 10

        # Determine trend
        if score > 25:
            trend = "BULLISH"
        elif score < -25:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"

        strength = min(abs(score), 100)

        return trend, strength

    def get_market_breadth(self) -> Dict:
        """عرض السوق - كم زوج صاعد مقابل هابط"""
        bullish = 0
        bearish = 0
        for symbol in TRADING_PAIRS[:20]:
            try:
                ticker = self.fetcher.fetch_ticker(symbol)
                change = ticker.get('change_pct', 0)
                if change > 0:
                    bullish += 1
                elif change < 0:
                    bearish += 1
            except:
                continue

        return {
            'bullish': bullish,
            'bearish': bearish,
            'sentiment': 'BULLISH' if bullish > bearish else 'BEARISH' if bearish > bullish else 'NEUTRAL',
        }
