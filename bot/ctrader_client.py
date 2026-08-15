"""
cTrader client — REST + Yahoo Finance (Signal-Only Mode)

• Historical bars     → Yahoo Finance (HTTPS 443)
• Live quotes         → Yahoo Finance (HTTPS 443)
• Account balance     → Spotware REST (optional)
• NO order execution  → Signal-only mode

This client fetches market data only. It does NOT execute trades.
"""

from __future__ import annotations
import asyncio, logging, time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import aiohttp

logger = logging.getLogger(__name__)

# ─── Data classes ─────────────────────────────────────────────────────────────
@dataclass
class Bar:
    open: float; high: float; low: float; close: float
    volume: float; timestamp: float

@dataclass
class SymbolInfo:
    pip_size: float
    min_volume_units: int
    volume_step_units: int
    pip_value_per_unit: float = 0.0  # value of 1 pip for 1 unit of volume, in account CCY


# ─── Client ───────────────────────────────────────────────────────────────────
class CTraderClient:

    YAHOO: Dict[str, str] = {
        "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X", "USDCAD": "USDCAD=X",
        "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
        "AUDUSD": "AUDUSD=X", "NZDUSD": "NZDUSD=X",
        "XAUUSD": "GC=F",     "XAGUSD": "SI=F",
        "US30":   "YM=F",     "NAS100": "NQ=F",
    }

    # Pip size per symbol
    PIP: Dict[str, float] = {
        "XAUUSD": 0.1, "XAGUSD": 0.01,
        "USDJPY": 0.01, "EURJPY": 0.01, "GBPJPY": 0.01,
    }

    # Contract size per symbol (1 lot = contract_size units)
    CONTRACT_SIZE: Dict[str, float] = {
        "XAUUSD": 100,    # Gold: 1 lot = 100 oz
        "XAGUSD": 5000,   # Silver: 1 lot = 5000 oz
        # Forex pairs: 1 lot = 100,000 units
    }

    # Pip value per unit (in account currency, approx EUR)
    PIP_VALUE_PER_UNIT: Dict[str, float] = {
        "EURUSD": 0.0001,   # 1 pip = 0.0001 EUR per unit
        "GBPUSD": 0.0001,
        "USDCAD": 0.00007,  # approx (depends on EUR/CAD rate)
        "USDJPY": 0.000065, # approx
        "EURJPY": 0.000065,
        "GBPJPY": 0.000065,
        "XAUUSD": 0.01,     # Gold: 1 pip (0.1) = ~0.01 EUR per oz
        "XAGUSD": 0.001,
    }

    def __init__(self, cfg):
        self.cfg = cfg
        self._equity_cache = 0.0
        self._last_bar_cache: Dict[str, List[Bar]] = {}
        self._last_quote_cache: Dict[str, Tuple[float, float]] = {}

    # Connection (data-only, no broker connection needed)
    async def connect(self) -> None:
        logger.info("📡 Signal-only mode — fetching market data via Yahoo Finance")

    async def disconnect(self) -> None:
        pass

    @property
    def is_live(self) -> bool:
        return False  # Always signal-only

    # ─── Symbol info ─────────────────────────────────────────────────────────
    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        pip = self.PIP.get(symbol, 0.0001)
        contract = self.CONTRACT_SIZE.get(symbol, 100_000.0)
        pip_val = self.PIP_VALUE_PER_UNIT.get(symbol, 0.0001)

        if "XAU" in symbol:
            return SymbolInfo(pip, 100, 100, pip_val)
        return SymbolInfo(pip, 1000, 1000, pip_val)

    # ─── Historical bars (Yahoo Finance) ─────────────────────────────────────
    async def get_recent_bars(self, symbol: str, timeframe: str,
                               count: int = 300) -> List[Bar]:
        ticker = self.YAHOO.get(symbol)
        if not ticker:
            return []
        TF_MINS = {"m1": 1, "m5": 5, "m15": 15, "m30": 30, "h1": 60, "h4": 240, "d1": 1440}
        YF_IV   = {"m1": "1m", "m5": "5m", "m15": "15m", "m30": "30m",
                   "h1": "1h", "h4": "1h", "d1": "1d"}
        mins = TF_MINS.get(timeframe, 30)
        iv   = YF_IV.get(timeframe, "30m")
        now  = int(time.time())
        p1   = now - max(count, 300) * mins * 60
        url  = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                f"?period1={p1}&period2={now}&interval={iv}&includePrePost=false")
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url,
                                    headers={"User-Agent": "Mozilla/5.0"},
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status != 200:
                        return []
                    raw = await r.json(content_type=None)
                    res = raw["chart"]["result"][0]
                    tss = res.get("timestamp", [])
                    q   = res["indicators"]["quote"][0]
                    bars = []
                    for i, ts in enumerate(tss):
                        try:
                            o = q["open"][i]  or 0
                            h = q["high"][i]  or o
                            l = q["low"][i]   or o
                            c = q["close"][i] or o
                            v = (q.get("volume") or [0]*len(tss))[i] or 0
                            if c > 0:
                                bars.append(Bar(o, h, l, c, v, float(ts)))
                        except (IndexError, TypeError):
                            pass
                    result = bars[-count:]
                    if result:
                        self._last_bar_cache[symbol] = result
                        logger.debug("[Yahoo] %d bars %s/%s last=%.5f",
                                     len(result), symbol, timeframe, result[-1].close)
                    return result
        except Exception as e:
            logger.warning("[Yahoo] %s/%s: %s", symbol, timeframe, e)
            return self._last_bar_cache.get(symbol, [])

    # ─── Live quote (from last bar) ───────────────────────────────────────────
    async def get_quote(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        cached = self._last_bar_cache.get(symbol)
        if cached:
            p   = cached[-1].close
            pip = self.PIP.get(symbol, 0.0001)
            spd = pip * 2
            return round(p - spd/2, 5), round(p + spd/2, 5)
        bars = await self.get_recent_bars(symbol, "m1", count=2)
        if bars:
            p   = bars[-1].close
            pip = self.PIP.get(symbol, 0.0001)
            spd = pip * 2
            return round(p - spd/2, 5), round(p + spd/2, 5)
        return None, None

    # ─── Account equity (Spotware REST — optional) ───────────────────────────
    async def get_account_equity(self) -> float:
        if not self.cfg.access_token and not self.cfg.api_token:
            return 10_000.0  # demo placeholder for signal-only mode

        for token in [self.cfg.access_token, getattr(self.cfg, "api_token", "")]:
            if not token:
                continue
            try:
                url = (f"https://api.spotware.com/connect/tradingaccounts"
                       f"?access_token={token}")
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url,
                                        headers={"User-Agent": "BBPro/2.0"},
                                        timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status == 200:
                            data = await r.json(content_type=None)
                            for a in data.get("data", []):
                                if str(a.get("accountId")) == str(self.cfg.account_id):
                                    bal = a["balance"] / 100
                                    self._equity_cache = bal
                                    return bal
            except Exception as e:
                logger.warning("get_equity: %s", e)
        return self._equity_cache or 10_000.0

    async def subscribe_spots(self, symbol: str) -> None:
        pass  # No-op in signal-only mode
