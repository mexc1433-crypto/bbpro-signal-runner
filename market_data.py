"""
BBPro Signal Bot - Market Data Fetcher
جلب بيانات الذهب (XAU/USD) من Yahoo Finance
"""
import pandas as pd
import numpy as np
import requests
import logging
import time
from typing import Dict, List, Optional, Tuple
from config import (DATA_SOURCE, GOLD_SYMBOL, GOLD_DISPLAY_NAME,
                    TRADING_PAIRS, FEAR_GREED_API, VIX_SYMBOL)

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False
    logging.error("yfinance not installed! Run: pip install yfinance")

logger = logging.getLogger(__name__)

# Yahoo Finance interval mapping
YF_INTERVALS = {
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "1h",   # yfinance doesn't support 4h, we aggregate from 1h
    "1d": "1d",
}

# Period mapping for yfinance (how much history to fetch)
YF_PERIODS = {
    "5m": "5d",
    "15m": "5d",
    "1h": "30d",
    "4h": "60d",
    "1d": "1y",
}


class MarketDataFetcher:
    """جلب بيانات الذهب من Yahoo Finance"""

    def __init__(self, exchange_name: str = None):
        self.exchange_name = exchange_name or "yfinance"
        self.symbol = GOLD_SYMBOL  # GC=F (Gold Futures)
        self.display_name = GOLD_DISPLAY_NAME  # XAU/USD
        logger.info(f"MarketDataFetcher initialized: {self.display_name} via {self.symbol}")

    def _yf_download(self, yf_symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """يحمل بيانات من Yahoo Finance"""
        interval = YF_INTERVALS.get(timeframe, "1h")
        period = YF_PERIODS.get(timeframe, "30d")

        try:
            df = yf.download(yf_symbol, period=period, interval=interval,
                            progress=False, auto_adjust=False)

            if df.empty:
                logger.warning(f"yfinance returned empty for {yf_symbol} {timeframe}")
                return pd.DataFrame()

            # Handle multi-index columns from newer yfinance versions
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Normalize column names to lowercase
            df.columns = [c.lower() for c in df.columns]

            # Ensure we have OHLCV columns
            needed = ['open', 'high', 'low', 'close', 'volume']
            for col in needed:
                if col not in df.columns:
                    df[col] = np.nan

            df = df[needed].dropna(subset=['open', 'high', 'low', 'close'])

            # If 4h requested, aggregate from 1h data
            if timeframe == "4h" and interval == "1h":
                df = self._aggregate_to_4h(df)

            # Take only the last `limit` rows
            df = df.tail(limit)

            return df

        except Exception as e:
            logger.error(f"yfinance download error for {yf_symbol} {timeframe}: {e}")
            return pd.DataFrame()

    def _aggregate_to_4h(self, df: pd.DataFrame) -> pd.DataFrame:
        """يجمّع بيانات 1h إلى 4h"""
        try:
            # Resample to 4-hour candles
            agg = df.resample('4h').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            })
            agg = agg.dropna()
            return agg
        except Exception as e:
            logger.error(f"4h aggregation error: {e}")
            return df

    def fetch_ohlcv(self, symbol: str, timeframe: str = '4h', limit: int = 200) -> pd.DataFrame:
        """
        يجلب بيانات OHLCV ويرجعها DataFrame
        symbol ممكن يكون XAU/USD أو GC=F
        """
        # Map display symbol to yfinance symbol
        yf_sym = self.symbol  # GC=F default
        if symbol in ("XAU/USD", "XAUUSD", "GOLD"):
            yf_sym = self.symbol
        elif symbol.startswith("GC"):
            yf_sym = symbol
        elif symbol in ("XAUUSD=X",):
            yf_sym = "XAUUSD=X"

        for attempt in range(3):
            try:
                df = self._yf_download(yf_sym, timeframe, limit)
                if not df.empty and len(df) >= 20:
                    return df
                # Try alternative symbol
                if yf_sym == "GC=F":
                    logger.info("Trying XAUUSD=X as fallback...")
                    df = self._yf_download("XAUUSD=X", timeframe, limit)
                    if not df.empty:
                        return df
                elif yf_sym == "XAUUSD=X":
                    logger.info("Trying GC=F as fallback...")
                    df = self._yf_download("GC=F", timeframe, limit)
                    if not df.empty:
                        return df
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} for {symbol} {timeframe}: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)

        return pd.DataFrame()

    def fetch_multiple_pairs(self, symbols: List[str], timeframe: str = '4h',
                              limit: int = 200) -> Dict[str, pd.DataFrame]:
        """يجلب بيانات (زوج واحد بس للذهب)"""
        results = {}
        for symbol in symbols:
            df = self.fetch_ohlcv(symbol, timeframe, limit)
            if not df.empty:
                results[symbol] = df
            time.sleep(0.3)
        return results

    def fetch_ticker(self, symbol: str) -> Dict:
        """يجلب معلومات ticker للذهب"""
        try:
            yf_sym = self.symbol
            ticker = yf.Ticker(yf_sym)
            info = ticker.history(period="2d", interval="1h")

            if info.empty:
                return {}

            if isinstance(info.columns, pd.MultiIndex):
                info.columns = info.columns.get_level_values(0)
            info.columns = [c.lower() for c in info.columns]

            last_price = float(info['close'].iloc[-1])
            prev_price = float(info['close'].iloc[-2]) if len(info) > 1 else last_price
            change_pct = ((last_price - prev_price) / prev_price) * 100 if prev_price else 0

            return {
                'symbol': self.display_name,
                'last': last_price,
                'high': float(info['high'].max()),
                'low': float(info['low'].min()),
                'volume': float(info['volume'].sum()),
                'change_pct': change_pct,
            }
        except Exception as e:
            logger.error(f"Error fetching ticker: {e}")
            # Fallback: simple download
            try:
                df = self._yf_download(self.symbol, "1h", 2)
                if not df.empty:
                    last = float(df['close'].iloc[-1])
                    return {
                        'symbol': self.display_name,
                        'last': last,
                        'high': float(df['high'].max()),
                        'low': float(df['low'].min()),
                        'volume': float(df['volume'].sum()) if 'volume' in df else 0,
                        'change_pct': 0,
                    }
            except:
                pass
            return {}

    def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        """N/A للذهب — يرجع قائمة فارغة"""
        return []

    def get_top_losers(self, limit: int = 10) -> List[Dict]:
        """N/A للذهب — يرجع قائمة فارغة"""
        return []

    def get_market_overview(self) -> Dict:
        """نظرة عامة على سوق الذهب"""
        overview = {}
        try:
            ticker = self.fetch_ticker("XAU/USD")
            if ticker:
                overview['gold_price'] = ticker.get('last', 0)
                overview['gold_change'] = ticker.get('change_pct', 0)
                overview['gold_high'] = ticker.get('high', 0)
                overview['gold_low'] = ticker.get('low', 0)
        except Exception as e:
            logger.error(f"Error in market overview: {e}")

        # VIX (مؤشر الخوف)
        try:
            vix_df = self._yf_download(VIX_SYMBOL, "1d", 5)
            if not vix_df.empty:
                overview['vix'] = float(vix_df['close'].iloc[-1])
                overview['vix_label'] = "خوف عالي" if overview['vix'] > 25 else "هدوء" if overview['vix'] < 15 else "متوسط"
        except:
            pass

        # DXY (مؤشر الدولار — يؤثر على الذهب عكسياً)
        try:
            dxy_df = self._yf_download("DX-Y.NYB", "1d", 5)
            if not dxy_df.empty:
                overview['dxy'] = float(dxy_df['close'].iloc[-1])
        except:
            pass

        return overview

    def get_fear_greed_index(self) -> Optional[int]:
        """مؤشر الخوف والطمع (من السوق العام)"""
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
