"""Reads today's events from a published Outlook calendar (ICS link)."""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests


@dataclass
class Event:
    title: str
    start: datetime
    end: datetime
    all_day: bool
    location: str = ""

    def describe(self) -> str:
        if self.all_day:
            when = "All day"
        else:
            when = f"{_clock(self.start)}-{_clock(self.end)}"
        place = _hide_links(self.location)
        where = f" @ {place}" if place else ""
        return f"{when}: {self.title}{where}"


_URL = re.compile(r"\S*https?://\S+|\S+\.(?:zoom|teams)\.\S+", re.IGNORECASE)


def _hide_links(location: str) -> str:
    # Meeting links can carry passwords, so they never go into a notification
    if not _URL.search(location):
        return location
    rest = _URL.sub("", location).strip(" ;,|-")
    return rest or "online"


def _clock(dt: datetime) -> str:
    # %-I isn't supported on Windows, so strip the leading zero by hand
    return dt.strftime("%I:%M %p").lstrip("0")


def _to_local(value, tz: ZoneInfo) -> tuple[datetime, bool]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return value.astimezone(tz), False
    return datetime.combine(value, time.min, tzinfo=tz), True


def parse_events(ics_text: str, day: date, tz: ZoneInfo) -> list[Event]:
    cal = icalendar.Calendar.from_ical(ics_text)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    events = []
    for comp in recurring_ical_events.of(cal).between(start, end):
        if str(comp.get("STATUS", "")).upper() == "CANCELLED":
            continue
        s, all_day = _to_local(comp.decoded("DTSTART"), tz)
        e = comp.get("DTEND")
        e = _to_local(comp.decoded("DTEND"), tz)[0] if e else s
        events.append(Event(
            title=str(comp.get("SUMMARY", "(no title)")),
            start=s,
            end=e,
            all_day=all_day,
            location=str(comp.get("LOCATION", "") or ""),
        ))
    return sorted(events, key=lambda ev: (not ev.all_day, ev.start))


def label(ev: Event, name: str) -> Event:
    """'Weekly Data Meeting' -> 'VenueHorn: Weekly Data Meeting'."""
    if ev.title.lower().startswith(name.lower()):
        return ev
    return Event(f"{name}: {ev.title}", ev.start, ev.end, ev.all_day, ev.location)


def fetch_ics(ics_url: str) -> str:
    resp = requests.get(ics_url, timeout=30)
    resp.raise_for_status()
    return resp.text


def todays_events(ics_url: str, day: date, tz: ZoneInfo) -> list[Event]:
    return parse_events(fetch_ics(ics_url), day, tz)


def coming_up(ics_text: str, today: date, tz: ZoneInfo, days: int = 3) -> list[tuple[date, Event]]:
    """(day, event) pairs for each of the `days` days after today."""
    found = []
    for offset in range(1, days + 1):
        day = today + timedelta(days=offset)
        found += [(day, ev) for ev in parse_events(ics_text, day, tz)]
    return found
