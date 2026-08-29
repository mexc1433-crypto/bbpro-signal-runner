"""
صياد الشمعات | Candle Hunter - Economic Calendar
تنبيهات الأخبار الاقتصادية المؤثرة على الذهب
"""
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ForexFactory free JSON API
CALENDAR_API = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# الأحداث المؤثرة على الذهب (USD)
HIGH_IMPACT_KEYWORDS = [
    "nonfarm", "non-farm", "nfp", "employment change",
    "cpi", "consumer price", "inflation",
    "fomc", "fed chair", "interest rate", "rate decision",
    "federal reserve", "speech", "gdp", "unemployment",
    "retail sales", "ism", "pmi", "pce", "core cpi",
]


class EconomicCalendar:
    """يجلب الأحداث الاقتصادية ويرسل تنبيهات"""

    def __init__(self):
        self.cached_events: List[Dict] = []
        self.last_fetch: Optional[datetime] = None
        self.alerted_events: set = set()

    def fetch_events(self) -> List[Dict]:
        """يجلب أحداث الأسبوع من ForexFactory"""
        # Cache لمدة ساعة
        if self.cached_events and self.last_fetch:
            if (datetime.now() - self.last_fetch).total_seconds() < 3600:
                return self.cached_events

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            resp = requests.get(CALENDAR_API, headers=headers, timeout=15)

            if resp.status_code != 200:
                logger.warning(f"Calendar API returned {resp.status_code}")
                return self.cached_events

            all_events = resp.json()

            # فلترة: USD فقط + تأثير عالي/متوسط
            filtered = []
            for event in all_events:
                country = event.get("country", "")
                impact = event.get("impact", "").lower()
                title = event.get("title", "").lower()

                if country != "USD":
                    continue
                if impact not in ["high", "medium"]:
                    continue

                # تأكد إن الحدث مؤثر على الذهب
                is_relevant = any(kw in title for kw in HIGH_IMPACT_KEYWORDS)
                if impact == "high":
                    is_relevant = True  # كل أحداث High impact مهمة

                if is_relevant:
                    filtered.append({
                        "title": event.get("title", ""),
                        "country": country,
                        "date": event.get("date", ""),
                        "impact": impact.capitalize(),
                        "forecast": event.get("forecast", ""),
                        "previous": event.get("previous", ""),
                    })

            self.cached_events = filtered
            self.last_fetch = datetime.now()
            logger.info(f"Fetched {len(filtered)} USD economic events")
            return filtered

        except Exception as e:
            logger.error(f"Error fetching economic calendar: {e}")
            return self.cached_events

    def get_upcoming_events(self, hours_ahead: int = 24) -> List[Dict]:
        """أحداث الساعات القادمة"""
        events = self.fetch_events()
        now = datetime.now()
        cutoff = now + timedelta(hours=hours_ahead)
        upcoming = []

        for event in events:
            try:
                # ForexFactory format: "2026-08-27T12:30:00-04:00"
                event_date = datetime.fromisoformat(event["date"])
                event_date = event_date.replace(tzinfo=None)
                if now <= event_date <= cutoff:
                    event["datetime"] = event_date
                    upcoming.append(event)
            except:
                continue

        upcoming.sort(key=lambda x: x["datetime"])
        return upcoming

    def is_high_impact_soon(self, minutes_before: int = 30) -> bool:
        """هل في حدث عالي التأثير قريب؟ (لإيقاف الإشارات)"""
        events = self.get_upcoming_events(hours_ahead=1)
        now = datetime.now()
        for event in events:
            if event.get("impact") != "High":
                continue
            try:
                event_time = event["datetime"]
                diff = (event_time - now).total_seconds() / 60
                if 0 <= diff <= minutes_before:
                    return True
            except:
                continue
        return False

    def check_and_alert(self) -> Optional[Dict]:
        """يفحص لو في حدث عالي لازم نرسل تنبيه قبله"""
        events = self.get_upcoming_events(hours_ahead=1)
        now = datetime.now()
        now_str = now.strftime('%Y%m%d%H%M')

        for event in events:
            if event.get("impact") != "High":
                continue
            try:
                event_time = event["datetime"]
                event_key = f"{event['title']}_{event_time.strftime('%Y%m%d%H%M')}"
                diff = (event_time - now).total_seconds() / 60

                # تنبيه قبل 30 دقيقة (مرة واحدة)
                if 28 <= diff <= 32 and event_key not in self.alerted_events:
                    self.alerted_events.add(event_key)
                    return event
            except:
                continue
        return None

    def format_events_message(self, events: List[Dict]) -> str:
        """رسالة الأحداث القادمة"""
        if not events:
            return "📅 لا توجد أحداث اقتصادية مهمة في الفترة القادمة"

        msg = "📅 الأحداث الاقتصادية القادمة\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"

        for event in events[:10]:
            impact = event.get("impact", "")
            emoji = "🔴" if impact == "High" else "🟡"
            time_str = event.get("datetime", "").strftime('%Y-%m-%d %H:%M') if hasattr(event.get("datetime", ""), 'strftime') else event.get("date", "")

            msg += f"{emoji} {event['title']}\n"
            msg += f"   ⏰ {time_str}\n"
            if event.get("forecast"):
                msg += f"   📊 متوقع: {event['forecast']}\n"
            if event.get("previous"):
                msg += f"   📈 سابق: {event['previous']}\n"
            msg += "\n"

        msg += "⚠️ تجنب التداول وقت الأخبار عالية التأثير\n"
        msg += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        msg += "🤖 صياد الشمعات | Candle Hunter"

        return msg

    def format_pre_alert(self, event: Dict) -> str:
        """تنبيه قبل حدث مهم بـ 30 دقيقة"""
        msg = "⚠️ تنبيه حدث اقتصادي مهم\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🔴 {event['title']}\n"
        msg += f"⏰ بعد 30 دقيقة\n"
        if event.get("forecast"):
            msg += f"📊 متوقع: {event['forecast']}\n"
        if event.get("previous"):
            msg += f"📈 سابق: {event['previous']}\n"
        msg += "\n🚫 يرجى الحذر - توقف الإشارات مؤقتاً\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += "🤖 صياد الشمعات | Candle Hunter"

        return msg
