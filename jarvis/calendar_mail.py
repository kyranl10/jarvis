"""A read-only snapshot of the coming weeks' calendar for the Jarvis chat page.

The chat page can't reach the calendar feeds, but it can read Gmail. So each refresh files the
upcoming events as JSON in a "JarvisCalendar" Gmail label, using the same IMAP app password the
briefing already uses. Only one snapshot is kept; it is replaced when the events change.
Nothing here is published anywhere public. Kyran approved this on Oct 14.
"""
import email.utils
import hashlib
import imaplib
import json
import time as clock
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from .calendar_source import Event, _to_local

LABEL = "JarvisCalendar"
SUBJECT = "Jarvis calendar snapshot"
DAYS = 45


def window(ics_text: str, today: date, tz: ZoneInfo, days: int = DAYS) -> list[Event]:
    """Every event from yesterday through `days` days ahead, recurring ones expanded."""
    cal = icalendar.Calendar.from_ical(ics_text)
    start = datetime.combine(today - timedelta(days=1), time.min, tzinfo=tz)
    found = []
    for comp in recurring_ical_events.of(cal).between(start, start + timedelta(days=days + 1)):
        if str(comp.get("STATUS", "")).upper() == "CANCELLED":
            continue
        s, all_day = _to_local(comp.decoded("DTSTART"), tz)
        e = _to_local(comp.decoded("DTEND"), tz)[0] if comp.get("DTEND") else s
        found.append(Event(str(comp.get("SUMMARY", "(no title)")), s, e, all_day, str(comp.get("LOCATION", "") or "")))
    return found


def snapshot(sources: list[tuple[str, list[Event]]], now: datetime, days: int = DAYS) -> dict:
    """sources: (calendar name, events). Returns the JSON-ready snapshot, sorted by start, duplicates dropped."""
    seen, events = set(), []
    for name, evs in sources:
        for e in evs:
            key = (e.title.strip().lower(), e.start)
            if key in seen:
                continue
            seen.add(key)
            events.append({"title": e.title, "start": e.start.isoformat(timespec="minutes"),
                           "end": e.end.isoformat(timespec="minutes"), "all_day": e.all_day,
                           "location": e.location, "calendar": name})
    events.sort(key=lambda x: (x["start"], not x["all_day"]))
    return {"updated": now.isoformat(timespec="minutes"), "from": (now.date() - timedelta(days=1)).isoformat(),
            "to": (now.date() + timedelta(days=days)).isoformat(), "events": events}


def fingerprint(snap: dict) -> str:
    return hashlib.sha256(json.dumps(snap["events"], sort_keys=True).encode()).hexdigest()[:16]


def deliver(address: str, app_password: str, snap: dict) -> bool:
    """Files the snapshot under the label if the events changed. Returns True when a new one was filed."""
    mark = fingerprint(snap)
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        imap.login(address, app_password)
        imap.create(LABEL)  # fails harmlessly when it already exists
        imap.select(LABEL)
        _, data = imap.search(None, "ALL")
        old = data[0].split()
        if old:
            _, parts = imap.fetch(old[-1], "(BODY.PEEK[HEADER.FIELDS (X-JARVIS-FINGERPRINT)])")
            if mark.encode() in (parts[0][1] or b""):
                return False  # nothing changed since the last snapshot
        msg = EmailMessage()
        msg["From"] = f"Jarvis <{address}>"
        msg["To"] = address
        msg["Subject"] = SUBJECT
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["X-Jarvis-Fingerprint"] = mark
        msg.set_content(json.dumps(snap, ensure_ascii=False))
        imap.append(LABEL, "\\Seen", imaplib.Time2Internaldate(clock.time()), msg.as_bytes())
        for num in old:  # keep only the newest snapshot; older ones go to the trash
            imap.copy(num, "[Gmail]/Trash")
            imap.store(num, "+FLAGS", "\\Deleted")
        imap.expunge()
        return True
    finally:
        try:
            imap.logout()
        except Exception:
            pass
