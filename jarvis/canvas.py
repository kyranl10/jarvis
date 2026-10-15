"""Upcoming assignment due dates from the Canvas calendar feed (ICS link)."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests


@dataclass
class Assignment:
    title: str
    due: datetime
    all_day: bool

    def describe(self, today: date) -> str:
        days = (self.due.date() - today).days
        day = "today" if days == 0 else "tomorrow" if days == 1 else f"{self.due:%A}"
        if self.all_day:
            return f"Due {day}: {self.title}"
        clock = self.due.strftime("%I:%M %p").lstrip("0")
        return f"Due {day} at {clock}: {self.title}"


def parse_assignments(ics_text: str, today: date, tz: ZoneInfo, days: int = 8) -> list[Assignment]:
    """Assignments due from today through the next `days - 1` days."""
    cal = icalendar.Calendar.from_ical(ics_text)
    start = datetime.combine(today, time.min, tzinfo=tz)
    end = start + timedelta(days=days)
    found = []
    for comp in recurring_ical_events.of(cal).between(start, end):
        # Canvas marks assignments with UIDs like "event-assignment-12345";
        # anything else is a regular calendar event, which Outlook already covers.
        if "assignment" not in str(comp.get("UID", "")).lower():
            continue
        due = comp.decoded("DTSTART")
        all_day = not isinstance(due, datetime)
        if all_day:
            due = datetime.combine(due, time.min, tzinfo=tz)
        elif due.tzinfo is None:
            due = due.replace(tzinfo=tz)
        found.append(Assignment(str(comp.get("SUMMARY", "(untitled)")), due.astimezone(tz), all_day))
    return sorted(found, key=lambda a: a.due)


def due_soon(ics_url: str, today: date, tz: ZoneInfo, days: int = 8) -> list[Assignment]:
    resp = requests.get(ics_url, timeout=30)
    resp.raise_for_status()
    return parse_assignments(resp.text, today, tz, days)
