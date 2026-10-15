"""Marching Tar Heels events from the GroupSpot calendar feed, filtered to the ones Kyran attends.

The feed (GROUPSPOT_ICAL_URL) carries a private token, so it only ever comes from the environment and is
never printed: errors are reported by class name only. Kept events join Today and Ahead like any other
calendar event, with title, time and place only.

What the feed looks like (checked Oct 2026): no DESCRIPTION, CATEGORIES or RRULE on any event, and every
timed event in UTC. Group tags live in the title instead: "PB1 - Volleyball" (pep band), "VPB - WBB"
and "Volunteer Band @ dOOk" (volunteer band), "Fockey Band", "All RP - Men's Soccer". So the tag rules
below check the title as well as the description.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests

from .calendar_source import Event

# Edit these to tune the filter. All matching is case-insensitive.
INCLUDE_TAGS = ["rp3", "all rp", "all band", "full band"]  # Kyran's group, or everyone
REHEARSAL_WORDS = ["rehearsal", "practice"]  # kept on Tuesdays and Thursdays
REHEARSAL_DAYS = {1, 3}  # Monday is 0
NOT_REHEARSAL = ["no rehearsal", "cancel"]  # "THANKSGIVING BREAK (No Rehearsal)" isn't one
EXCLUDE_TAGS = [r"\bvfb\b", r"\bvpb\b", r"volunteer band", r"\bfockey\b", r"\bfocky\b", r"field hockey",
                r"\bpep ?band\b", r"\bpb ?\d"]  # regexes: groups Kyran isn't in
ALREADY_ON_CALENDAR = ["fall break"]  # title keywords for days off he already has
DAYS_AHEAD = 4  # today plus the HUD's next 3 days

_HOME_GAME = re.compile(r"\bgame ?day\b", re.IGNORECASE)
_AWAY = re.compile(r"\s(@|at)\s", re.IGNORECASE)


@dataclass
class BandEvent:
    title: str
    start: datetime
    end: datetime
    all_day: bool
    location: str
    description: str = ""


def fetch(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def _local(value, tz: ZoneInfo) -> tuple[datetime, bool]:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=tz)).astimezone(tz), False
    return datetime.combine(value, time.min, tzinfo=tz), True


def parse(ics_text: str, today: date, tz: ZoneInfo, days: int = DAYS_AHEAD) -> list[BandEvent]:
    """Every event from today through `days` days ahead, recurrences expanded, in Eastern time."""
    cal = icalendar.Calendar.from_ical(ics_text)
    start = datetime.combine(today, time.min, tzinfo=tz)
    out = []
    for comp in recurring_ical_events.of(cal).between(start, start + timedelta(days=days)):
        if str(comp.get("STATUS", "")).upper() == "CANCELLED":
            continue
        s, all_day = _local(comp.decoded("DTSTART"), tz)
        e = _local(comp.decoded("DTEND"), tz)[0] if comp.get("DTEND") else s
        out.append(BandEvent(str(comp.get("SUMMARY", "")).strip(), s, e, all_day,
                             str(comp.get("LOCATION", "") or "").strip(), str(comp.get("DESCRIPTION", "") or "")))
    return sorted(out, key=lambda ev: (ev.start.date(), not ev.all_day, ev.start))


def decide(ev: BandEvent) -> tuple[bool, str]:
    """(keep, reason) for one event."""
    title, text = ev.title.lower(), f"{ev.title}\n{ev.description}".lower()
    if any(k in title for k in ALREADY_ON_CALENDAR):
        return False, "already on calendar"
    if any(t in text for t in INCLUDE_TAGS):
        return True, "rp3 / all band"
    rehearsal = any(w in text for w in REHEARSAL_WORDS) and not any(w in text for w in NOT_REHEARSAL)
    if rehearsal and not _excluded(text):
        if ev.start.weekday() in REHEARSAL_DAYS:
            return True, "Tue/Thu rehearsal"
        return False, "rehearsal not on Tue/Thu"
    # Football games are titled "GAME DAY v Opponent" with no location. The band's calendar lists only the
    # games it plays at Kenan, so that title is the home-game signal; an "@"/"at" would mark an away game.
    if _HOME_GAME.search(ev.title) and not _AWAY.search(ev.title):
        return True, "home football game"
    if _excluded(text):
        return False, "other group"
    return False, "not tagged for rp3"


def _excluded(text: str) -> bool:
    return any(re.search(p, text) for p in EXCLUDE_TAGS)


def place(location: str) -> str:
    """'Bill Koman Practice Complex, South Road, Chapel Hill, NC' -> 'Bill Koman Practice Complex'."""
    return location.split(",")[0].strip()


def build(url: str, today: date, tz: ZoneInfo, days: int = DAYS_AHEAD, strict: bool = False) -> list[Event]:
    """The events Kyran attends, as calendar events for Today and Ahead. Logs what was kept and why.
    A feed failure gives [] (or re-raises with strict=True, so the HUD's health strip can show it)."""
    try:
        events = parse(fetch(url), today, tz, days)
    except Exception as exc:  # never print the exception text: it can contain the feed URL
        print(f"Marching Tar Heels feed unavailable: {exc.__class__.__name__}")
        if strict:
            raise
        return []
    kept, dropped = [], {}
    for ev in events:
        keep, why = decide(ev)
        if keep:
            kept.append(ev)
        else:
            dropped.setdefault(why, []).append(ev.title)
    print(f"Marching Tar Heels: {len(events)} events in the next {days} days, {len(kept)} kept, "
          f"{len(events) - len(kept)} dropped")
    for why, titles in dropped.items():
        print(f"  dropped ({why}): {', '.join(sorted(set(titles)))}")
    return [Event(ev.title, ev.start, ev.end, ev.all_day, place(ev.location)) for ev in kept]
