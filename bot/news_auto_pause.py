"""
news_auto_pause.py — High-Impact News Auto-Pause
=================================================
Pauses signal generation during major economic events:
  - NFP (Non-Farm Payrolls): First Friday of month, 12:30 UTC
  - FOMC: Configurable dates via FOMC_DATES env var
  - CPI: Configurable dates via CPI_DATES env var
  - ECB, GDP, Retail Sales, PMI: Configurable via env vars
  - Manual pause dates: MANUAL_PAUSE_DATES env var

Pause windows:
  - NEWS_PAUSE_BEFORE_MIN (default 30): minutes before event
  - NEWS_PAUSE_AFTER_MIN (default 60): minutes after event

Env vars:
  - ENABLE_NEWS_AUTO_PAUSE (default true)
  - NEWS_PAUSE_BEFORE_MIN (default 30)
  - NEWS_PAUSE_AFTER_MIN (default 60)
  - FOMC_DATES (comma-separated ISO dates, e.g. "2026-09-17,2026-10-29")
  - CPI_DATES (comma-separated ISO dates)
  - ECB_DATES (comma-separated ISO dates)
  - MANUAL_PAUSE_DATES (comma-separated ISO dates for ad-hoc events)
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Event Definitions ───────────────────────────────────────────────────────

# Events with fixed recurring schedules
RECURRING_EVENTS = {
    "NFP": {
        "description": "Non-Farm Payrolls",
        "time_utc": (12, 30),      # 12:30 UTC
        "recurrence": "first_friday",
    },
    "ECB": {
        "description": "ECB Rate Decision",
        "time_utc": (11, 45),      # 11:45 UTC
        "recurrence": "first_thursday",
    },
    "PMI": {
        "description": "Manufacturing PMI",
        "time_utc": (8, 0),        # 08:00 UTC
        "recurrence": "first_business_day",
    },
}

# Events that need manual date configuration (dates vary)
CONFIGURABLE_EVENTS = {
    "FOMC": {"description": "FOMC Rate Decision", "time_utc": (18, 0)},
    "FOMC_MINUTES": {"description": "FOMC Minutes", "time_utc": (18, 0)},
    "CPI": {"description": "Consumer Price Index", "time_utc": (12, 30)},
    "GDP": {"description": "GDP Report", "time_utc": (12, 30)},
    "RETAIL_SALES": {"description": "Retail Sales", "time_utc": (12, 30)},
}


class NewsAutoPause:
    """Manages auto-pause during high-impact news events."""

    def __init__(self, cfg=None):
        self.enabled = os.environ.get("ENABLE_NEWS_AUTO_PAUSE", "true").strip().lower() != "false"
        self.before_min = int(os.environ.get("NEWS_PAUSE_BEFORE_MIN", "30"))
        self.after_min = int(os.environ.get("NEWS_PAUSE_AFTER_MIN", "60"))

        # Load configurable event dates from env
        self.event_dates: Dict[str, List[datetime]] = {}
        for key in ["FOMC", "FOMC_MINUTES", "CPI", "GDP", "RETAIL_SALES"]:
            dates_str = os.environ.get(f"{key}_DATES", "")
            if dates_str:
                self.event_dates[key] = self._parse_dates(dates_str)

        # Manual pause dates
        self.manual_dates: List[datetime] = []
        manual_str = os.environ.get("MANUAL_PAUSE_DATES", "")
        if manual_str:
            self.manual_dates = self._parse_dates(manual_str)

        logger.info("NewsAutoPause: enabled=%s, before=%dmin, after=%dmin, events=%s",
                     self.enabled, self.before_min, self.after_min,
                     {k: len(v) for k, v in self.event_dates.items()})

    def _parse_dates(self, dates_str: str) -> List[datetime]:
        """Parse comma-separated ISO date strings into datetime objects."""
        dates = []
        for s in dates_str.split(","):
            s = s.strip()
            if not s:
                continue
            try:
                # Parse date and add UTC timezone
                dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
                dates.append(dt)
            except Exception as e:
                logger.warning("Could not parse date '%s': %s", s, e)
        return dates

    def _get_first_friday(self, year: int, month: int) -> datetime:
        """Get the first Friday of a given month."""
        d = datetime(year, month, 1, tzinfo=timezone.utc)
        while d.weekday() != 4:  # Friday = 4
            d += timedelta(days=1)
        return d

    def _get_first_thursday(self, year: int, month: int) -> datetime:
        """Get the first Thursday of a given month."""
        d = datetime(year, month, 1, tzinfo=timezone.utc)
        while d.weekday() != 3:  # Thursday = 3
            d += timedelta(days=1)
        return d

    def _get_first_business_day(self, year: int, month: int) -> datetime:
        """Get the first business day of a month."""
        d = datetime(year, month, 1, tzinfo=timezone.utc)
        while d.weekday() >= 5:  # Skip Saturday (5) and Sunday (6)
            d += timedelta(days=1)
        return d

    def _get_recurring_event_time(self, event_key: str, now: datetime) -> Optional[datetime]:
        """Get the datetime of a recurring event for the current month."""
        event = RECURRING_EVENTS.get(event_key)
        if not event:
            return None

        h, m = event["time_utc"]
        recurrence = event["recurrence"]

        if recurrence == "first_friday":
            d = self._get_first_friday(now.year, now.month)
        elif recurrence == "first_thursday":
            d = self._get_first_thursday(now.year, now.month)
        elif recurrence == "first_business_day":
            d = self._get_first_business_day(now.year, now.month)
        else:
            return None

        return d.replace(hour=h, minute=m, second=0, microsecond=0)

    def is_paused(self, now_utc: datetime = None) -> Tuple[bool, str]:
        """
        Check if signals should be paused due to news events.

        Returns:
            (True, reason) if paused, (False, "") if not.
        """
        if not self.enabled:
            return False, ""

        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        # ── Check recurring events (NFP, ECB, PMI) ──────────────────────
        for key, event in RECURRING_EVENTS.items():
            event_time = self._get_recurring_event_time(key, now_utc)
            if event_time is None:
                continue

            pause_start = event_time - timedelta(minutes=self.before_min)
            pause_end = event_time + timedelta(minutes=self.after_min)

            if pause_start <= now_utc <= pause_end:
                desc = event["description"]
                return True, f"{desc} release window ({pause_start.strftime('%H:%M')}-{pause_end.strftime('%H:%M')} UTC)"

        # ── Check configurable events (FOMC, CPI, GDP, etc.) ─────────────
        for key, dates in self.event_dates.items():
            event_info = CONFIGURABLE_EVENTS.get(key, {})
            h, m = event_info.get("time_utc", (12, 30))
            desc = event_info.get("description", key)

            for date in dates:
                event_time = date.replace(hour=h, minute=m, second=0, microsecond=0)
                pause_start = event_time - timedelta(minutes=self.before_min)
                pause_end = event_time + timedelta(minutes=self.after_min)

                if pause_start <= now_utc <= pause_end:
                    return True, f"{desc} release window ({pause_start.strftime('%H:%M')}-{pause_end.strftime('%H:%M')} UTC)"

        # ── Check manual pause dates ─────────────────────────────────────
        for date in self.manual_dates:
            pause_start = date - timedelta(minutes=self.before_min)
            pause_end = date + timedelta(minutes=self.after_min)

            if pause_start <= now_utc <= pause_end:
                return True, f"Manual pause ({date.strftime('%Y-%m-%d %H:%M')} UTC)"

        return False, ""

    def get_next_event(self, now_utc: datetime = None) -> Optional[Dict]:
        """Get info about the next upcoming event."""
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        upcoming: List[Tuple[datetime, str]] = []

        # Recurring events this month and next
        for key, event in RECURRING_EVENTS.items():
            for month_offset in [0, 1]:
                check_date = now_utc.replace(day=1) + timedelta(days=32 * month_offset)
                event_time = self._get_recurring_event_time(key, check_date)
                if event_time and event_time > now_utc:
                    upcoming.append((event_time, event["description"]))

        # Configurable events
        for key, dates in self.event_dates.items():
            event_info = CONFIGURABLE_EVENTS.get(key, {})
            h, m = event_info.get("time_utc", (12, 30))
            desc = event_info.get("description", key)
            for date in dates:
                event_time = date.replace(hour=h, minute=m, second=0, microsecond=0)
                if event_time > now_utc:
                    upcoming.append((event_time, desc))

        if not upcoming:
            return None

        upcoming.sort(key=lambda x: x[0])
        next_time, next_desc = upcoming[0]
        return {
            "name": next_desc,
            "datetime_utc": next_time.isoformat(),
            "date": next_time.strftime("%Y-%m-%d"),
            "time_utc": next_time.strftime("%H:%M"),
        }

    def get_status(self) -> Dict:
        """Get full status for API/dashboard consumption."""
        now_utc = datetime.now(timezone.utc)
        paused, reason = self.is_paused(now_utc)
        next_event = self.get_next_event(now_utc)

        return {
            "enabled": self.enabled,
            "paused": paused,
            "reason": reason,
            "next_event": next_event,
            "config": {
                "before_minutes": self.before_min,
                "after_minutes": self.after_min,
            },
            "tracked_events": list(RECURRING_EVENTS.keys()) + list(self.event_dates.keys()),
        }
