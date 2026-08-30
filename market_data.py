"""
صياد الشمعات | Candle Hunter - Market Data Fetcher
جلب بيانات الذهب من MEXC مباشرة (XAU/USDT:USDT) - لحظي 100%
Yahoo Finance كـ fallback + مؤشرات السوق (VIX, DXY)
"""
import pandas as pd
import numpy as np
import requests
import logging
import time
import os
from typing import Dict, List, Optional, Tuple

try:
    import ccxt
except ImportError:
    ccxt = None

from config import (DATA_SOURCE, GOLD_SYMBOL, GOLD_DISPLAY_NAME,
                    TRADING_PAIRS, FEAR_GREED_API, VIX_SYMBOL)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════
# MEXC Configuration
# ═══════════════════════════════════════════════════
MEXC_API_KEY = os.getenv("MEXC_API_KEY", "")
MEXC_API_SECRET = os.getenv("MEXC_API_SECRET", "")
MEXC_GOLD_SYMBOL = "XAU/USDT:USDT"  # أعلى حجم تداول ($605M)
MEXC_MARKET_TYPE = "swap"  # futures

# Yahoo Finance (fallback + market indicators)
YF_API_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
YF_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

# Timeframe mapping for MEXC
MEXC_TIMEFRAMES = {
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# Yahoo Finance intervals (for fallback)
YF_INTERVALS = {
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "1h",
    "1d": "1d",
}

YF_RANGES = {
    "5m": "5d",
    "15m": "5d",
    "1h": "30d",
    "4h": "60d",
    "1d": "1y",
}


class MarketDataFetcher:
    """جلب بيانات الذهب من MEXC مباشرة + Yahoo Finance fallback"""

    def __init__(self, exchange_name: str = None):
        self.exchange_name = exchange_name or "mexc"
        self.symbol = GOLD_SYMBOL
        self.display_name = GOLD_DISPLAY_NAME
        self.mexc_symbol = MEXC_GOLD_SYMBOL
        
        # Initialize MEXC exchange via CCXT
        self._exchange = None
        if ccxt and MEXC_API_KEY and MEXC_API_SECRET:
            try:
                self._exchange = ccxt.mexc({
                    'apiKey': MEXC_API_KEY,
                    'secret': MEXC_API_SECRET,
                    'options': {'defaultType': MEXC_MARKET_TYPE}
                })
                logger.info(f"✅ MEXC connected: {self.mexc_symbol} (swap/futures)")
            except Exception as e:
                logger.error(f"MEXC init error: {e}")
        
        logger.info(f"MarketDataFetcher: {self.display_name} via MEXC ({self.mexc_symbol})")

    def _mexc_fetch_ohlcv(self, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """يجلب بيانات OHLCV من MEXC مباشرة"""
        if not self._exchange:
            return pd.DataFrame()

        mexc_tf = MEXC_TIMEFRAMES.get(timeframe, "1h")
        
        for attempt in range(3):
            try:
                ohlcv = self._exchange.fetch_ohlcv(
                    self.mexc_symbol,
                    timeframe=mexc_tf,
                    limit=limit
                )
                
                if not ohlcv or len(ohlcv) < 20:
                    logger.warning(f"MEXC: not enough data for {mexc_tf} ({len(ohlcv) if ohlcv else 0} candles)")
                    return pd.DataFrame()

                # Build DataFrame
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('datetime', inplace=True)
                df.drop('timestamp', axis=1, inplace=True)
                df = df.dropna(subset=['open', 'high', 'low', 'close'])
                
                logger.info(f"MEXC {mexc_tf}: {len(df)} candles loaded (last: {df['close'].iloc[-1]:.2f})")
                return df.tail(limit)

            except Exception as e:
                logger.warning(f"MEXC attempt {attempt+1} for {mexc_tf}: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
        
        return pd.DataFrame()

    def _yf_api_download(self, yf_symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """Yahoo Finance fallback"""
        interval = YF_INTERVALS.get(timeframe, "1h")
        range_ = YF_RANGES.get(timeframe, "30d")

        url = f"{YF_API_BASE}/{yf_symbol}"
        params = {"interval": interval, "range": range_}

        try:
            resp = requests.get(url, headers=YF_HEADERS, params=params, timeout=15)
            if resp.status_code != 200:
                return pd.DataFrame()

            data = resp.json()
            if 'chart' not in data or data['chart'].get('error'):
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

            df = pd.DataFrame({
                'open': opens,
                'high': highs,
                'low': lows,
                'close': closes,
                'volume': volumes,
            }, index=pd.to_datetime(timestamps, unit='ms'))
            df = df.dropna(subset=['open', 'high', 'low', 'close'])

            if len(df) < 20:
                return pd.DataFrame()

            if timeframe == "4h":
                df = self._aggregate_to_4h(df)

            return df.tail(limit)

        except Exception as e:
            logger.error(f"Yahoo API error for {yf_symbol} {timeframe}: {e}")
            return pd.DataFrame()

    def _aggregate_to_4h(self, df: pd.DataFrame) -> pd.DataFrame:
        """يجمّع كل 4 شموع 1h في شمعة 4h"""
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
        """يجلب بيانات OHLCV — MEXC أولاً، Yahoo Finance كـ fallback"""
        
        # 1. Try MEXC first
        if self._exchange:
            df = self._mexc_fetch_ohlcv(timeframe, limit)
            if not df.empty and len(df) >= 20:
                return df
            logger.warning("MEXC fetch failed, trying Yahoo Finance fallback...")

        # 2. Yahoo Finance fallback
        for yf_sym in [self.symbol, "XAUUSD=X"]:
            df = self._yf_api_download(yf_sym, timeframe, limit)
            if not df.empty and len(df) >= 20:
                logger.info(f"Using Yahoo Finance fallback: {yf_sym}")
                return df

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
        """يجلب السعر الحالي للذهب من MEXC"""
        # 1. Try MEXC
        if self._exchange:
            try:
                ticker = self._exchange.fetch_ticker(self.mexc_symbol)
                last_price = ticker.get('last', 0)
                prev_price = ticker.get('open', last_price) or last_price
                change_pct = ((last_price - prev_price) / prev_price * 100) if prev_price else 0
                
                return {
                    'symbol': self.display_name,
                    'last': float(last_price),
                    'high': float(ticker.get('high', 0)),
                    'low': float(ticker.get('low', 0)),
                    'volume': float(ticker.get('baseVolume', 0)),
                    'change_pct': float(change_pct),
                }
            except Exception as e:
                logger.warning(f"MEXC ticker error: {e}")
                
                # Fallback: use last OHLCV candle as ticker
                try:
                    df = self._mexc_fetch_ohlcv("1m", 2)
                    if df is not None and not df.empty and len(df) >= 2:
                        last_price = float(df["close"].iloc[-1])
                        prev_price = float(df["close"].iloc[-2])
                        change_pct = ((last_price - prev_price) / prev_price * 100) if prev_price else 0
                        logger.info(f"MEXC ticker via OHLCV: ${last_price:.2f}")
                        return {
                            "symbol": self.display_name,
                            "last": last_price,
                            "high": float(df["high"].max()),
                            "low": float(df["low"].min()),
                            "volume": float(df["volume"].sum()),
                            "change_pct": change_pct,
                        }
                except Exception as e2:
                    logger.warning(f"OHLCV ticker fallback failed: {e2}")

        # 2. Yahoo fallback
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
        return []

    def get_top_losers(self, limit: int = 10) -> List[Dict]:
        return []

    def get_market_overview(self) -> Dict:
        """نظرة عامة على سوق الذهب + المؤشرات المرتبطة"""
        overview = {}
        
        # Gold price from MEXC
        try:
            ticker = self.fetch_ticker("XAU/USD")
            if ticker:
                overview['gold_price'] = ticker.get('last', 0)
                overview['gold_change'] = ticker.get('change_pct', 0)
                overview['gold_high'] = ticker.get('high', 0)
                overview['gold_low'] = ticker.get('low', 0)
        except Exception as e:
            logger.error(f"Error in gold overview: {e}")

        # VIX (Yahoo Finance — MEXC doesn't have it)
        try:
            vix_df = self._yf_api_download(VIX_SYMBOL, "1d", 5)
            if not vix_df.empty:
                overview['vix'] = float(vix_df['close'].iloc[-1])
                overview['vix_label'] = "خوف عالي" if overview['vix'] > 25 else "هدوء" if overview['vix'] < 15 else "متوسط"
        except:
            pass

        # DXY (Yahoo Finance)
        try:
            dxy_df = self._yf_api_download("DX-Y.NYB", "1d", 5)
            if not dxy_df.empty:
                overview['dxy'] = float(dxy_df['close'].iloc[-1])
        except:
            pass

        # Silver (Yahoo Finance)
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

        resistance = []
        for i in range(5, len(highs) - 5):
            if highs[i] == max(highs[i-5:i+6]):
                resistance.append(float(highs[i]))

        support = []
        for i in range(5, len(lows) - 5):
            if lows[i] == min(lows[i-5:i+6]):
                support.append(float(lows[i]))

        resistance = sorted(list(set(resistance)), reverse=True)[:3]
        support = sorted(list(set(support)), reverse=True)[:3]

        return support, resistance

    def get_pivot_points(self, df: pd.DataFrame) -> Dict[str, float]:
        """يحسب النقاط المحورية"""
        if len(df) < 2:
            return {}

        prev = df.iloc[-2]
        high = float(prev['high'])
        low = float(prev['low'])
        close = float(prev['close'])

        pivot = (high + low + close) / 3

        r1 = 2 * pivot - low
        s1 = 2 * pivot - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = high + 2 * (pivot - low)
        s3 = low - 2 * (high - pivot)

        return {
            'pivot': pivot, 'r1': r1, 'r2': r2, 'r3': r3,
            's1': s1, 's2': s2, 's3': s3,
        }
