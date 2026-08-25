"""
economic_calendar.py — Economic Calendar Integration
=====================================================
Fetches economic events and blocks signals during high-impact news.
Falls back to hardcoded high-impact times if API unavailable.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class EconomicCalendar:
    """Economic calendar with blackout windows."""

    # Currency to symbols mapping
    CURRENCY_MAP = {
        "XAUUSD": ["USD"],
        "XAGUSD": ["USD"],
        "EURUSD": ["EUR", "USD"],
        "GBPUSD": ["GBP", "USD"],
        "USDJPY": ["USD", "JPY"],
        "EURJPY": ["EUR", "JPY"],
        "USDCAD": ["USD", "CAD"],
        "AUDUSD": ["AUD", "USD"],
        "NZDUSD": ["NZD", "USD"],
        "EURGBP": ["EUR", "GBP"],
    }

    # Recurring high-impact times (UTC)
    RECURRING_EVENTS = [
        (8, 30, "USD", "US Economic Data"),
        (13, 30, "USD", "US Economic Data"),
        (10, 0, "EUR", "ECB Events"),
        (12, 0, "EUR", "ECB Events"),
    ]

    def __init__(self, high_impact_only: bool = True,
                 blackout_before_min: int = 15, blackout_after_min: int = 30):
        self.high_impact_only = high_impact_only
        self.blackout_before_min = blackout_before_min
        self.blackout_after_min = blackout_after_min
        self._events_cache: List[dict] = []
        self._cache_time: Optional[datetime] = None

    async def fetch_events(self) -> List[dict]:
        """Fetch upcoming economic events."""
        now = datetime.now(timezone.utc)

        # Use cache if less than 1 hour old
        if self._cache_time and (now - self._cache_time).total_seconds() < 3600:
            return self._events_cache

        events = []

        # Try Forex Factory RSS feed
        try:
            events = await self._fetch_forex_factory()
        except Exception as e:
            logger.warning("Failed to fetch economic calendar: %s", e)

        # Fallback: use recurring events
        if not events:
            events = self._get_recurring_events()

        self._events_cache = events
        self._cache_time = now
        return events

    async def _fetch_forex_factory(self) -> List[dict]:
        """Try to fetch from Forex Factory RSS."""
        try:
            import aiohttp
            url = "https://www.forexfactory.com/rss.php"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10),
                                        headers={"User-Agent": "Mozilla/5.0"}) as r:
                    if r.status != 200:
                        return []
                    text = await r.text()
                    # Parse RSS XML (simplified)
                    events = []
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(text)
                    for item in root.findall(".//item"):
                        title = item.findtext("title", "")
                        pub_date = item.findtext("pubDate", "")
                        events.append({
                            "title": title,
                            "time": pub_date,
                            "currency": "USD",  # default
                            "impact": "medium",
                        })
                    return events
        except Exception:
            return []

    def _get_recurring_events(self) -> List[dict]:
        """Get recurring high-impact event times."""
        now = datetime.now(timezone.utc)
        events = []
        for hour, minute, currency, title in self.RECURRING_EVENTS:
            event_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            events.append({
                "title": title,
                "time": event_time.isoformat(),
                "currency": currency,
                "impact": "high",
            })
        return events

    def is_blackout(self, symbol: str) -> Tuple[bool, str]:
        """Check if current time is within blackout window for the symbol's currencies."""
        now = datetime.now(timezone.utc)
        currencies = self.CURRENCY_MAP.get(symbol.upper(), [])

        if not currencies:
            return False, ""

        events = self._events_cache if self._events_cache else self._get_recurring_events()

        for event in events:
            if event.get("currency") not in currencies:
                continue
            if self.high_impact_only and event.get("impact", "high") != "high":
                continue

            try:
                event_time = datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            before = event_time - timedelta(minutes=self.blackout_before_min)
            after = event_time + timedelta(minutes=self.blackout_after_min)

            if before <= now <= after:
                return True, f"{event.get('title', 'unknown')} ({event.get('currency', '')})"

        return False, ""

    def get_next_event(self, symbol: str) -> Optional[dict]:
        """Get next upcoming event for the symbol's currencies."""
        now = datetime.now(timezone.utc)
        currencies = self.CURRENCY_MAP.get(symbol.upper(), [])
        events = self._events_cache if self._events_cache else self._get_recurring_events()

        next_event = None
        min_diff = float("inf")

        for event in events:
            if event.get("currency") not in currencies:
                continue
            try:
                event_time = datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                diff = (event_time - now).total_seconds()
                if 0 < diff < min_diff:
                    min_diff = diff
                    next_event = event
            except Exception:
                continue

        return next_event

    def format_events(self, symbol: str, count: int = 3) -> str:
        """Format upcoming events for Telegram."""
        now = datetime.now(timezone.utc)
        currencies = self.CURRENCY_MAP.get(symbol.upper(), [])
        events = self._events_cache if self._events_cache else self._get_recurring_events()

        # Filter by currency and future events
        upcoming = []
        for event in events:
            if event.get("currency") not in currencies:
                continue
            try:
                event_time = datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                if event_time > now:
                    upcoming.append(event)
            except Exception:
                continue

        upcoming.sort(key=lambda e: e.get("time", ""))

        if not upcoming:
            return "لا توجد أخبار قادمة"

        lines = []
        for event in upcoming[:count]:
            time_str = event.get("time", "")[:16]
            impact_emoji = "🔴" if event.get("impact") == "high" else "🟡" if event.get("impact") == "medium" else "🟢"
            lines.append(f"• {time_str} {event.get('currency', '')} - {event.get('title', 'N/A')} {impact_emoji}")

        return "\n".join(lines)
