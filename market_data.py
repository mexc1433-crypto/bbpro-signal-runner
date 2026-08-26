"""
BBPro Signal Bot - Market Data Fetcher
جلب بيانات الذهب (XAU/USD) من Yahoo Finance API مباشرة
"""
import pandas as pd
import numpy as np
import requests
import logging
import time
from typing import Dict, List, Optional, Tuple
from config import (DATA_SOURCE, GOLD_SYMBOL, GOLD_DISPLAY_NAME,
                    TRADING_PAIRS, FEAR_GREED_API, VIX_SYMBOL)

logger = logging.getLogger(__name__)

# Yahoo Finance API
YF_API_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
YF_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
}

# Interval mapping for Yahoo Finance
YF_INTERVALS = {
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "1h",   # Aggregate from 1h
    "1d": "1d",
}

# Range mapping
YF_RANGES = {
    "5m": "5d",
    "15m": "5d",
    "1h": "30d",
    "4h": "60d",
    "1d": "1y",
}


class MarketDataFetcher:
    """جلب بيانات الذهب من Yahoo Finance API مباشرة"""

    def __init__(self, exchange_name: str = None):
        self.exchange_name = exchange_name or "yahoo_finance"
        self.symbol = GOLD_SYMBOL  # GC=F
        self.display_name = GOLD_DISPLAY_NAME  # XAU/USD
        logger.info(f"MarketDataFetcher initialized: {self.display_name} via {self.symbol}")

    def _yf_api_download(self, yf_symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """يجلب بيانات من Yahoo Finance API مباشرة"""
        interval = YF_INTERVALS.get(timeframe, "1h")
        range_ = YF_RANGES.get(timeframe, "30d")

        url = f"{YF_API_BASE}/{yf_symbol}"
        params = {
            "interval": interval,
            "range": range_,
        }

        try:
            resp = requests.get(url, headers=YF_HEADERS, params=params, timeout=15)

            if resp.status_code != 200:
                logger.warning(f"Yahoo API returned {resp.status_code} for {yf_symbol} {timeframe}")
                return pd.DataFrame()

            data = resp.json()

            if 'chart' not in data or data['chart'].get('error'):
                logger.warning(f"Yahoo API error: {data.get('chart', {}).get('error', 'unknown')}")
                return pd.DataFrame()

            result = data['chart']['result'][0]
            timestamps = result.get('timestamp', [])
            quote = result.get('indicators', {}).get('quote', [{}])[0]

            opens = quote.get('open', [])
            highs = quote.get('high', [])
            lows = quote.get('low', [])
            closes = quote.get('close', [])
            volumes = quote.get('volume', [])

            if not timestamps or not closes:
                return pd.DataFrame()

            # Build DataFrame
            df = pd.DataFrame({
                'open': opens,
                'high': highs,
                'low': lows,
                'close': closes,
                'volume': volumes,
            }, index=pd.to_datetime(timestamps, unit='ms'))

            # Drop NaN rows
            df = df.dropna(subset=['open', 'high', 'low', 'close'])

            if len(df) < 20:
                return pd.DataFrame()

            # If 4h requested, aggregate from 1h
            if timeframe == "4h":
                df = self._aggregate_to_4h(df)

            # Take only the last `limit` rows
            df = df.tail(limit)

            return df

        except requests.exceptions.Timeout:
            logger.error(f"Yahoo API timeout for {yf_symbol} {timeframe}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Yahoo API error for {yf_symbol} {timeframe}: {e}")
            return pd.DataFrame()

    def _aggregate_to_4h(self, df: pd.DataFrame) -> pd.DataFrame:
        """يجمّع كل 4 شموع 1h متتالية في شمعة 4h (بدون إنشاء buckets فارغة)"""
        try:
            n = len(df)
            df_trimmed = df.iloc[:n - (n % 4)]
            if len(df_trimmed) < 4:
                return df
            grouped = df_trimmed.groupby(np.arange(len(df_trimmed)) // 4).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            })
            grouped.index = df_trimmed.index[3::4]
            return grouped
        except Exception as e:
            logger.error(f"4h aggregation error: {e}")
            return df

    def fetch_ohlcv(self, symbol: str, timeframe: str = '4h', limit: int = 200) -> pd.DataFrame:
        """يجلب بيانات OHLCV للذهب"""
        # Determine which symbol to use
        yf_sym = self.symbol  # GC=F default

        for attempt in range(3):
            try:
                df = self._yf_api_download(yf_sym, timeframe, limit)
                if not df.empty and len(df) >= 20:
                    return df

                # Try fallback
                fallback = "XAUUSD=X" if yf_sym == "GC=F" else "GC=F"
                logger.info(f"Trying {fallback} as fallback...")
                df = self._yf_api_download(fallback, timeframe, limit)
                if not df.empty:
                    return df

            except Exception as e:
                logger.warning(f"Attempt {attempt+1} for {symbol} {timeframe}: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)

        return pd.DataFrame()

    def fetch_multiple_pairs(self, symbols: List[str], timeframe: str = '4h',
                              limit: int = 200) -> Dict[str, pd.DataFrame]:
        """يجلب بيانات (زوج واحد للذهب)"""
        results = {}
        for symbol in symbols:
            df = self.fetch_ohlcv(symbol, timeframe, limit)
            if not df.empty:
                results[symbol] = df
            time.sleep(0.3)
        return results

    def fetch_ticker(self, symbol: str) -> Dict:
        """يجلب السعر الحالي للذهب"""
        try:
            df = self._yf_api_download(self.symbol, "1h", 24)
            if df.empty:
                return {}

            last_price = float(df['close'].iloc[-1])
            prev_price = float(df['close'].iloc[-2]) if len(df) > 1 else last_price
            change_pct = ((last_price - prev_price) / prev_price) * 100 if prev_price else 0

            return {
                'symbol': self.display_name,
                'last': last_price,
                'high': float(df['high'].max()),
                'low': float(df['low'].min()),
                'volume': float(df['volume'].sum()),
                'change_pct': change_pct,
            }
        except Exception as e:
            logger.error(f"Error fetching ticker: {e}")
            return {}

    def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        """N/A للذهب"""
        return []

    def get_top_losers(self, limit: int = 10) -> List[Dict]:
        """N/A للذهب"""
        return []

    def get_market_overview(self) -> Dict:
        """نظرة عامة على سوق الذهب + المؤشرات المرتبطة"""
        overview = {}
        try:
            ticker = self.fetch_ticker("XAU/USD")
            if ticker:
                overview['gold_price'] = ticker.get('last', 0)
                overview['gold_change'] = ticker.get('change_pct', 0)
                overview['gold_high'] = ticker.get('high', 0)
                overview['gold_low'] = ticker.get('low', 0)
        except Exception as e:
            logger.error(f"Error in gold overview: {e}")

        # VIX (مؤشر الخوف)
        try:
            vix_df = self._yf_api_download(VIX_SYMBOL, "1d", 5)
            if not vix_df.empty:
                overview['vix'] = float(vix_df['close'].iloc[-1])
                overview['vix_label'] = "خوف عالي" if overview['vix'] > 25 else "هدوء" if overview['vix'] < 15 else "متوسط"
        except:
            pass

        # DXY (مؤشر الدولار — عكسي مع الذهب)
        try:
            dxy_df = self._yf_api_download("DX-Y.NYB", "1d", 5)
            if not dxy_df.empty:
                overview['dxy'] = float(dxy_df['close'].iloc[-1])
        except:
            pass

        # Silver (مؤشر مرتبط بالذهب)
        try:
            si_df = self._yf_api_download("SI=F", "1d", 5)
            if not si_df.empty:
                overview['silver_price'] = float(si_df['close'].iloc[-1])
        except:
            pass

        return overview

    def get_fear_greed_index(self) -> Optional[int]:
        """مؤشر الخوف والطمع"""
        try:
            resp = requests.get(FEAR_GREED_API, timeout=10)
            data = resp.json()
            return int(data['data'][0]['value'])
        except Exception as e:
            logger.error(f"Error fetching fear/greed: {e}")
            return None

    def get_support_resistance(self, df: pd.DataFrame, lookback: int = 50) -> Tuple[List[float], List[float]]:
        """يحسب مستويات الدعم والمقاومة"""
        if len(df) < lookback:
            return [], []

        recent = df.tail(lookback)
        highs = recent['high'].values
        lows = recent['low'].values

        # Find pivot highs
        resistance = []
        for i in range(5, len(highs) - 5):
            if highs[i] == max(highs[i-5:i+6]):
                resistance.append(float(highs[i]))

        # Find pivot lows
        support = []
        for i in range(5, len(lows) - 5):
            if lows[i] == min(lows[i-5:i+6]):
                support.append(float(lows[i]))

        # Deduplicate and limit
        resistance = sorted(list(set(resistance)), reverse=True)[:3]
        support = sorted(list(set(support)), reverse=True)[:3]

        return support, resistance

    def get_pivot_points(self, df: pd.DataFrame) -> Dict[str, float]:
        """يحسب النقاط المحورية (Standard, Fibonacci, Camarilla)"""
        if len(df) < 2:
            return {}

        prev = df.iloc[-2]
        high = float(prev['high'])
        low = float(prev['low'])
        close = float(prev['close'])

        pivot = (high + low + close) / 3

        # Standard pivots
        r1 = 2 * pivot - low
        r2 = pivot + (high - low)
        r3 = high + 2 * (pivot - low)
        s1 = 2 * pivot - high
        s2 = pivot - (high - low)
        s3 = low - 2 * (high - pivot)

        # Fibonacci pivots
        fib_r1 = pivot + 0.382 * (high - low)
        fib_r2 = pivot + 0.618 * (high - low)
        fib_s1 = pivot - 0.382 * (high - low)
        fib_s2 = pivot - 0.618 * (high - low)

        # Camarilla pivots
        cam_r1 = close + 1.1 * (high - low) / 4
        cam_r2 = close + 1.1 * (high - low) / 2
        cam_s1 = close - 1.1 * (high - low) / 4
        cam_s2 = close - 1.1 * (high - low) / 2

        return {
            'pivot': round(pivot, 2),
            'r1': round(r1, 2), 'r2': round(r2, 2), 'r3': round(r3, 2),
            's1': round(s1, 2), 's2': round(s2, 2), 's3': round(s3, 2),
            'fib_r1': round(fib_r1, 2), 'fib_r2': round(fib_r2, 2),
            'fib_s1': round(fib_s1, 2), 'fib_s2': round(fib_s2, 2),
            'cam_r1': round(cam_r1, 2), 'cam_r2': round(cam_r2, 2),
            'cam_s1': round(cam_s1, 2), 'cam_s2': round(cam_s2, 2),
        }
