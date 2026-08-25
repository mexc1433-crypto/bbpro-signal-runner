"""
BBPro Signal Bot - Market Data Fetcher
جلب بيانات السوق من المنصات
"""
import ccxt
import pandas as pd
import numpy as np
import requests
import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple
from config import (EXCHANGE_NAME, EXCHANGE_API_KEY, EXCHANGE_API_SECRET,
                    TRADING_PAIRS, FEAR_GREED_API)

logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """جلب بيانات السوق من المنصات"""

    def __init__(self, exchange_name: str = None):
        exchange = exchange_name or EXCHANGE_NAME
        self.exchange_name = exchange

        exchange_class = getattr(ccxt, exchange, ccxt.mexc)

        opts = {
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'},
        }
        if EXCHANGE_API_KEY and EXCHANGE_API_SECRET:
            opts['apiKey'] = EXCHANGE_API_KEY
            opts['secret'] = EXCHANGE_API_SECRET

        self.exchange = exchange_class(opts)

    def fetch_ohlcv(self, symbol: str, timeframe: str = '4h', limit: int = 200) -> pd.DataFrame:
        """
        يجلب بيانات OHLCV ويرجعها DataFrame
        """
        for attempt in range(3):
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                return df
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} for {symbol} {timeframe}: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
        return pd.DataFrame()

    def fetch_multiple_pairs(self, symbols: List[str], timeframe: str = '4h',
                              limit: int = 200) -> Dict[str, pd.DataFrame]:
        """يجلب بيانات أزواج متعددة"""
        results = {}
        for symbol in symbols:
            df = self.fetch_ohlcv(symbol, timeframe, limit)
            if not df.empty:
                results[symbol] = df
            time.sleep(0.3)  # Rate limit
        return results

    def fetch_ticker(self, symbol: str) -> Dict:
        """يجلب معلومات ticker"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'symbol': symbol,
                'last': ticker.get('last', 0),
                'high': ticker.get('high', 0),
                'low': ticker.get('low', 0),
                'volume': ticker.get('baseVolume', 0),
                'change_pct': ticker.get('percentage', 0),
            }
        except Exception as e:
            logger.error(f"Error fetching ticker {symbol}: {e}")
            return {}

    def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        """أكبر ارتفاعات"""
        try:
            tickers = self.exchange.fetch_tickers()
            usdt_tickers = [
                {'symbol': k, 'last': v.get('last', 0), 'change': v.get('percentage', 0)}
                for k, v in tickers.items()
                if '/USDT' in k and v.get('percentage') is not None and v.get('last', 0) > 0
            ]
            gainers = sorted(usdt_tickers, key=lambda x: x['change'], reverse=True)
            return gainers[:limit]
        except Exception as e:
            logger.error(f"Error fetching gainers: {e}")
            return []

    def get_top_losers(self, limit: int = 10) -> List[Dict]:
        """أكبر انخفاضات"""
        try:
            tickers = self.exchange.fetch_tickers()
            usdt_tickers = [
                {'symbol': k, 'last': v.get('last', 0), 'change': v.get('percentage', 0)}
                for k, v in tickers.items()
                if '/USDT' in k and v.get('percentage') is not None and v.get('last', 0) > 0
            ]
            losers = sorted(usdt_tickers, key=lambda x: x['change'])
            return losers[:limit]
        except Exception as e:
            logger.error(f"Error fetching losers: {e}")
            return []

    def get_market_overview(self) -> Dict:
        """نظرة عامة على السوق"""
        overview = {}
        try:
            btc = self.fetch_ticker('BTC/USDT')
            overview['btc_price'] = btc.get('last', 0)
            overview['btc_change'] = btc.get('change_pct', 0)

            eth = self.fetch_ticker('ETH/USDT')
            overview['eth_price'] = eth.get('last', 0)
            overview['eth_change'] = eth.get('change_pct', 0)
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
        closes = recent['close'].values

        # Find pivot highs
        resistance = []
        for i in range(5, len(highs) - 5):
            if highs[i] == max(highs[i-5:i+6]):
                resistance.append(highs[i])

        # Find pivot lows
        support = []
        for i in range(5, len(lows) - 5):
            if lows[i] == min(lows[i-5:i+6]):
                support.append(lows[i])

        # Deduplicate and limit
        resistance = sorted(list(set(resistance)), reverse=True)[:3]
        support = sorted(list(set(support)), reverse=True)[:3]

        return support, resistance

    def get_pivot_points(self, df: pd.DataFrame) -> Dict[str, float]:
        """يحسب النقاط المحورية"""
        if len(df) < 2:
            return {}

        prev = df.iloc[-2]
        high = prev['high']
        low = prev['low']
        close = prev['close']

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
            'pivot': round(pivot, 6),
            'r1': round(r1, 6), 'r2': round(r2, 6), 'r3': round(r3, 6),
            's1': round(s1, 6), 's2': round(s2, 6), 's3': round(s3, 6),
            'fib_r1': round(fib_r1, 6), 'fib_r2': round(fib_r2, 6),
            'fib_s1': round(fib_s1, 6), 'fib_s2': round(fib_s2, 6),
            'cam_r1': round(cam_r1, 6), 'cam_r2': round(cam_r2, 6),
            'cam_s1': round(cam_s1, 6), 'cam_s2': round(cam_s2, 6),
        }
