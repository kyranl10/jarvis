from datetime import date, datetime
from zoneinfo import ZoneInfo

from jarvis import calendar_mail
from jarvis.calendar_source import Event

TZ = ZoneInfo("America/New_York")
ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1
SUMMARY:DATA 495
DTSTART;TZID=America/New_York:20261015T140000
DTEND;TZID=America/New_York:20261015T151500
RRULE:FREQ=WEEKLY;COUNT=10
LOCATION:Phillips 215
END:VEVENT
BEGIN:VEVENT
UID:2
SUMMARY:Far away
DTSTART;TZID=America/New_York:20270301T090000
DTEND;TZID=America/New_York:20270301T100000
END:VEVENT
BEGIN:VEVENT
UID:3
SUMMARY:Fall break
DTSTART;VALUE=DATE:20261016
DTEND;VALUE=DATE:20261017
END:VEVENT
END:VCALENDAR
"""


def test_window_expands_recurring_events_and_stops_at_the_horizon():
    evs = calendar_mail.window(ICS, date(2026, 10, 14), TZ, days=30)
    titles = [e.title for e in evs]
    assert titles.count("DATA 495") == 5  # Oct 15, 22, 29, Nov 5, 12
    assert "Far away" not in titles
    assert any(e.all_day for e in evs if e.title == "Fall break")


def test_snapshot_sorts_dedupes_and_names_the_calendar():
    now = datetime(2026, 10, 14, 17, 0, tzinfo=TZ)
    a = Event("Rehearsal", datetime(2026, 10, 20, 18, 30, tzinfo=TZ), datetime(2026, 10, 20, 21, 0, tzinfo=TZ), False)
    b = Event("DATA 495", datetime(2026, 10, 15, 14, 0, tzinfo=TZ), datetime(2026, 10, 15, 15, 15, tzinfo=TZ), False)
    snap = calendar_mail.snapshot([("UNC", [b]), ("Marching Tar Heels", [a, a])], now)
    assert [e["title"] for e in snap["events"]] == ["DATA 495", "Rehearsal"]
    assert snap["events"][1]["calendar"] == "Marching Tar Heels"
    assert snap["events"][0]["start"] == "2026-10-15T14:00-04:00"
    assert calendar_mail.fingerprint(snap) == calendar_mail.fingerprint(dict(snap, updated="later"))
