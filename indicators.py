"""
صياد الشمعات | Candle Hunter - Technical Indicators
مؤشرات فنية شاملة - 22+ مؤشر
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional


# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════

def bullish_cross(fast: pd.Series, slow: pd.Series) -> bool:
    """يكتشف التقاطع الصاعد"""
    if len(fast) < 2 or len(slow) < 2:
        return False
    return fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]


def bearish_cross(fast: pd.Series, slow: pd.Series) -> bool:
    """يكتشف التقاطع الهابط"""
    if len(fast) < 2 or len(slow) < 2:
        return False
    return fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]


# ═══════════════════════════════════════════════════════════════
# 1. RSI - Relative Strength Index
# ═══════════════════════════════════════════════════════════════

def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """RSI - مؤشر القوة النسبية"""
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ═══════════════════════════════════════════════════════════════
# 2. MACD - Moving Average Convergence Divergence
# ═══════════════════════════════════════════════════════════════

def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD - تقارب وتباعد المتوسطات المتحركة"""
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ═══════════════════════════════════════════════════════════════
# 3. Bollinger Bands
# ═══════════════════════════════════════════════════════════════

def bollinger_bands(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands - أطر بولنجر"""
    middle = df['close'].rolling(window=period).mean()
    rolling_std = df['close'].rolling(window=period).std()
    upper = middle + (rolling_std * std)
    lower = middle - (rolling_std * std)
    bandwidth = (upper - lower) / middle
    return upper, middle, lower, bandwidth


# ═══════════════════════════════════════════════════════════════
# 4. EMA - Exponential Moving Average
# ═══════════════════════════════════════════════════════════════

def ema(df: pd.DataFrame, period: int) -> pd.Series:
    """EMA - المتوسط المتحرك الأسي"""
    return df['close'].ewm(span=period, adjust=False).mean()


# ═══════════════════════════════════════════════════════════════
# 5. SMA - Simple Moving Average
# ═══════════════════════════════════════════════════════════════

def sma(df: pd.DataFrame, period: int) -> pd.Series:
    """SMA - المتوسط المتحرك البسيط"""
    return df['close'].rolling(window=period).mean()


# ═══════════════════════════════════════════════════════════════
# 6. Stochastic Oscillator
# ═══════════════════════════════════════════════════════════════

def stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3, smooth: int = 3) -> Tuple[pd.Series, pd.Series]:
    """Stochastic Oscillator - مذبذب ستوكاستيك"""
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    k_fast = 100 * ((df['close'] - low_min) / (high_max - low_min).replace(0, np.nan))
    k = k_fast.rolling(window=smooth).mean()
    d = k.rolling(window=d_period).mean()
    return k, d


# ═══════════════════════════════════════════════════════════════
# 7. ATR - Average True Range
# ═══════════════════════════════════════════════════════════════

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR - متوسط النطاق الحقيقي (لتقلب السوق)"""
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


# ═══════════════════════════════════════════════════════════════
# 8. ADX - Average Directional Index
# ═══════════════════════════════════════════════════════════════

def adx(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """ADX - مؤشر الاتجاه الموجه"""
    high = df['high']
    low = df['low']
    close = df['close']

    plus_dm = high.diff()
    minus_dm = low.diff().abs()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0

    tr = atr(df, period)
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr.replace(0, np.nan))
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.rolling(window=period).mean()

    return adx_val, plus_di, minus_di


# ═══════════════════════════════════════════════════════════════
# 9. Ichimoku Cloud
# ═══════════════════════════════════════════════════════════════

def ichimoku(df: pd.DataFrame, conversion: int = 9, base: int = 26, span_b: int = 52) -> Dict[str, pd.Series]:
    """Ichimoku Cloud - سحابة إيشيموكو"""
    nine_high = df['high'].rolling(window=conversion).max()
    nine_low = df['low'].rolling(window=conversion).min()
    tenkan = (nine_high + nine_low) / 2

    base_high = df['high'].rolling(window=base).max()
    base_low = df['low'].rolling(window=base).min()
    kijun = (base_high + base_low) / 2

    span_b_high = df['high'].rolling(window=span_b).max()
    span_b_low = df['low'].rolling(window=span_b).min()
    senkou_b = (span_b_high + span_b_low) / 2

    senkou_a = (tenkan + kijun) / 2

    chikou = df['close'].shift(-base)

    return {
        'tenkan': tenkan,
        'kijun': kijun,
        'senkou_a': senkou_a,
        'senkou_b': senkou_b,
        'chikou': chikou,
    }


# ═══════════════════════════════════════════════════════════════
# 10. VWAP - Volume Weighted Average Price
# ═══════════════════════════════════════════════════════════════

def vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP - متوسط السعر المرجح بالحجم"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * df['volume']).cumsum() / df['volume'].cumsum().replace(0, np.nan)


# ═══════════════════════════════════════════════════════════════
# 11. Fibonacci Retracement
# ═══════════════════════════════════════════════════════════════

def fibonacci_levels(df: pd.DataFrame, lookback: int = 100) -> Dict[str, float]:
    """Fibonacci Retracement - مستويات فيبوناتشي"""
    recent = df.tail(lookback)
    high = recent['high'].max()
    low = recent['low'].min()
    diff = high - low

    return {
        '0.0': high,
        '0.236': high - 0.236 * diff,
        '0.382': high - 0.382 * diff,
        '0.5': high - 0.5 * diff,
        '0.618': high - 0.618 * diff,
        '0.786': high - 0.786 * diff,
        '1.0': low,
    }


# ═══════════════════════════════════════════════════════════════
# 12. Williams %R
# ═══════════════════════════════════════════════════════════════

def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Williams %R - مؤشر ويليامز"""
    high_max = df['high'].rolling(window=period).max()
    low_min = df['low'].rolling(window=period).min()
    return -100 * (high_max - df['close']) / (high_max - low_min).replace(0, np.nan)


# ═══════════════════════════════════════════════════════════════
# 13. CCI - Commodity Channel Index
# ═══════════════════════════════════════════════════════════════

def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """CCI - مؤشر قناة السلع"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    sma_tp = typical_price.rolling(window=period).mean()
    mean_deviation = typical_price.rolling(window=period).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    return (typical_price - sma_tp) / (0.015 * mean_deviation.replace(0, np.nan))


# ═══════════════════════════════════════════════════════════════
# 14. MFI - Money Flow Index
# ═══════════════════════════════════════════════════════════════

def mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """MFI - مؤشر تدفق الأموال"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    money_flow = typical_price * df['volume']
    positive_flow = money_flow.where(typical_price > typical_price.shift(), 0)
    negative_flow = money_flow.where(typical_price < typical_price.shift(), 0)
    pos_sum = positive_flow.rolling(window=period).sum()
    neg_sum = negative_flow.rolling(window=period).sum()
    mfr = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - (100 / (1 + mfr))


# ═══════════════════════════════════════════════════════════════
# 15. OBV - On Balance Volume
# ═══════════════════════════════════════════════════════════════

def obv(df: pd.DataFrame) -> pd.Series:
    """OBV - الرصيد المتوازن للحجم"""
    obv_val = pd.Series(index=df.index, dtype=float)
    obv_val.iloc[0] = 0
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i-1]:
            obv_val.iloc[i] = obv_val.iloc[i-1] + df['volume'].iloc[i]
        elif df['close'].iloc[i] < df['close'].iloc[i-1]:
            obv_val.iloc[i] = obv_val.iloc[i-1] - df['volume'].iloc[i]
        else:
            obv_val.iloc[i] = obv_val.iloc[i-1]
    return obv_val


# ═══════════════════════════════════════════════════════════════
# 16. Parabolic SAR
# ═══════════════════════════════════════════════════════════════

def parabolic_sar(df: pd.DataFrame, af_start: float = 0.02, af_max: float = 0.2) -> pd.Series:
    """Parabolic SAR - SAR البارابولي"""
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    n = len(df)

    sar = np.zeros(n)
    af = af_start
    ep = high[0]
    trend = 1  # 1 = uptrend, -1 = downtrend
    sar[0] = low[0]

    for i in range(1, n):
        if trend == 1:
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            if low[i] < sar[i]:
                trend = -1
                sar[i] = ep
                af = af_start
                ep = low[i]
            else:
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + af_start, af_max)
        else:
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            if high[i] > sar[i]:
                trend = 1
                sar[i] = ep
                af = af_start
                ep = high[i]
            else:
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + af_start, af_max)

    return pd.Series(sar, index=df.index)


# ═══════════════════════════════════════════════════════════════
# 17. SuperTrend
# ═══════════════════════════════════════════════════════════════

def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> Tuple[pd.Series, pd.Series]:
    """SuperTrend - سوبر ترند"""
    hl2 = (df['high'] + df['low']) / 2
    atr_val = atr(df, period)
    upper_band = hl2 + (multiplier * atr_val)
    lower_band = hl2 - (multiplier * atr_val)

    n = len(df)
    st = pd.Series(np.nan, index=df.index, dtype=float)
    trend_dir = pd.Series(1, index=df.index, dtype=float)

    # Find first valid ATR index
    first_valid = atr_val.first_valid_index()
    if first_valid is None:
        return st, trend_dir
    start_idx = df.index.get_loc(first_valid)

    # Initialize at first valid point
    st.iloc[start_idx] = upper_band.iloc[start_idx]
    trend_dir.iloc[start_idx] = 1

    for i in range(start_idx + 1, n):
        close = df['close'].iloc[i]
        prev_st = st.iloc[i-1]
        prev_dir = trend_dir.iloc[i-1]

        if np.isnan(prev_st):
            st.iloc[i] = upper_band.iloc[i]
            trend_dir.iloc[i] = 1
            continue

        ub = upper_band.iloc[i] if not np.isnan(upper_band.iloc[i]) else upper_band.iloc[i-1]
        lb = lower_band.iloc[i] if not np.isnan(lower_band.iloc[i]) else lower_band.iloc[i-1]

        if close > prev_st:
            trend_dir.iloc[i] = 1
            if prev_dir == 1:
                st.iloc[i] = max(lb, prev_st)
            else:
                st.iloc[i] = lb
        elif close < prev_st:
            trend_dir.iloc[i] = -1
            if prev_dir == -1:
                st.iloc[i] = min(ub, prev_st)
            else:
                st.iloc[i] = ub
        else:
            trend_dir.iloc[i] = prev_dir
            st.iloc[i] = prev_st

    return st, trend_dir


# ═══════════════════════════════════════════════════════════════
# 18. CMF - Chaikin Money Flow
# ═══════════════════════════════════════════════════════════════

def cmf(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """CMF - Chaikin Money Flow (مؤشر تدفق أموال تشايكين)"""
    high_low = (df['high'] - df['low']).replace(0, np.nan)
    mf_multiplier = ((df['close'] - df['low']) - (df['high'] - df['close'])) / high_low
    mf_volume = mf_multiplier * df['volume']
    vol_sum = df['volume'].rolling(window=period).sum().replace(0, np.nan)
    return mf_volume.rolling(window=period).sum() / vol_sum


# ═══════════════════════════════════════════════════════════════
# 19. DMI - Directional Movement Index
# ═══════════════════════════════════════════════════════════════

def dmi(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """DMI - Directional Movement Index (+DI, -DI, ADX)"""
    up_move = df['high'].diff()
    down_move = -df['low'].diff()

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    tr_val = atr(df, period)
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr_val.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr_val.replace(0, np.nan))

    di_sum = plus_di + minus_di
    dx = 100 * (plus_di - minus_di).abs() / di_sum.replace(0, np.nan)
    adx_val = dx.rolling(window=period).mean()

    return plus_di, minus_di, adx_val


# ═══════════════════════════════════════════════════════════════
# 20. Elder Ray (Bull / Bear Power)
# ═══════════════════════════════════════════════════════════════

def elder_ray(df: pd.DataFrame, period: int = 13) -> Tuple[pd.Series, pd.Series]:
    """Elder Ray Index - Bull Power & Bear Power (قوة الثيران والدببة)"""
    ema_val = df['close'].ewm(span=period, adjust=False).mean()
    bull_power = df['high'] - ema_val
    bear_power = df['low'] - ema_val
    return bull_power, bear_power


# ═══════════════════════════════════════════════════════════════
# 21. Keltner Channels
# ═══════════════════════════════════════════════════════════════

def keltner_channels(df: pd.DataFrame, period: int = 20, atr_period: int = 10, multiplier: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Keltner Channels - قنوات كيلتنر"""
    middle = df['close'].ewm(span=period, adjust=False).mean()
    atr_val = atr(df, atr_period)
    upper = middle + (multiplier * atr_val)
    lower = middle - (multiplier * atr_val)
    return upper, middle, lower


# ═══════════════════════════════════════════════════════════════
# 22. TRIX - Triple Exponential Average
# ═══════════════════════════════════════════════════════════════

def trix(df: pd.DataFrame, period: int = 12) -> pd.Series:
    """TRIX - Triple Exponential Average (المتوسط الأسي الثلاثي)"""
    ema1 = df['close'].ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    prev_ema3 = ema3.shift(1).replace(0, np.nan)
    return ((ema3 - ema3.shift(1)) / prev_ema3) * 100


# ═══════════════════════════════════════════════════════════════
# Calculate All Indicators
# ═══════════════════════════════════════════════════════════════

def calculate_all_indicators(df: pd.DataFrame) -> Dict:
    """
    يحسب كل المؤشرات ويرجعها في dict واحد
    """
    if len(df) < 50:
        return {}

    result = {}

    # RSI (multiple periods)
    result['rsi_7'] = rsi(df, 7)
    result['rsi_14'] = rsi(df, 14)
    result['rsi_21'] = rsi(df, 21)

    # MACD
    result['macd_line'], result['macd_signal'], result['macd_hist'] = macd(df)

    # Bollinger
    result['bb_upper'], result['bb_middle'], result['bb_lower'], result['bb_bandwidth'] = bollinger_bands(df)

    # EMAs
    for p in [9, 21, 50, 100, 200]:
        result[f'ema_{p}'] = ema(df, p)

    # SMAs
    for p in [20, 50, 100, 200]:
        result[f'sma_{p}'] = sma(df, p)

    # Stochastic
    result['stoch_k'], result['stoch_d'] = stochastic(df)

    # ATR
    result['atr'] = atr(df)

    # ADX
    result['adx'], result['plus_di'], result['minus_di'] = adx(df)

    # Ichimoku
    result['ichimoku'] = ichimoku(df)

    # VWAP
    result['vwap'] = vwap(df)

    # Fibonacci
    result['fibonacci'] = fibonacci_levels(df)

    # Williams %R
    result['williams_r'] = williams_r(df)

    # CCI
    result['cci'] = cci(df)

    # MFI
    result['mfi'] = mfi(df)

    # OBV
    result['obv'] = obv(df)

    # Parabolic SAR
    result['psar'] = parabolic_sar(df)

    # SuperTrend
    result['supertrend'], result['supertrend_dir'] = supertrend(df)

    # CMF
    result['cmf'] = cmf(df, 20)

    # DMI
    result['dmi_plus'], result['dmi_minus'], result['dmi_adx'] = dmi(df)

    # Elder Ray
    result['bull_power'], result['bear_power'] = elder_ray(df)

    # Keltner Channels
    result['kc_upper'], result['kc_middle'], result['kc_lower'] = keltner_channels(df)

    # TRIX
    result['trix'] = trix(df, 12)

    return result
