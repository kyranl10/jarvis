from datetime import date
from zoneinfo import ZoneInfo

from jarvis.calendar_source import parse_events

TZ = ZoneInfo("America/New_York")

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:1
SUMMARY:ENGL 105
DTSTART;TZID=America/New_York:20261012T093000
DTEND;TZID=America/New_York:20261012T104500
RRULE:FREQ=WEEKLY;BYDAY=MO,WE
LOCATION:Room 120
END:VEVENT
BEGIN:VEVENT
UID:2
SUMMARY:Drumline rehearsal
DTSTART:20261014T210000Z
DTEND:20261014T233000Z
END:VEVENT
BEGIN:VEVENT
UID:3
SUMMARY:Fall break
DTSTART;VALUE=DATE:20261014
DTEND;VALUE=DATE:20261015
END:VEVENT
BEGIN:VEVENT
UID:4
SUMMARY:Cancelled meeting
STATUS:CANCELLED
DTSTART:20261014T150000Z
DTEND:20261014T160000Z
END:VEVENT
END:VCALENDAR
"""


def test_recurring_utc_and_all_day_events():
    events = parse_events(ICS, date(2026, 10, 14), TZ)
    assert [e.describe() for e in events] == [
        "All day: Fall break",
        "9:30 AM-10:45 AM: ENGL 105 @ Room 120",
        "5:00 PM-7:30 PM: Drumline rehearsal",
    ]


def test_empty_day():
    assert parse_events(ICS, date(2026, 10, 13), TZ) == []


def test_meeting_links_are_hidden():
    from datetime import datetime
    from jarvis.calendar_source import Event

    start = datetime(2026, 10, 13, 16, tzinfo=TZ)
    end = datetime(2026, 10, 13, 16, 30, tzinfo=TZ)
    zoom = "https://zoom.us/j/99115842550?pwd=secret"
    assert Event("Client meeting", start, end, False, zoom).describe() == "4:00 PM-4:30 PM: Client meeting @ online"
    assert Event("Office hours", start, end, False, f"Room 120; {zoom}").describe() == "4:00 PM-4:30 PM: Office hours @ Room 120"


def test_coming_up_next_three_days():
    from jarvis.calendar_source import coming_up

    assert [(d, ev.describe()) for d, ev in coming_up(ICS, date(2026, 10, 13), TZ)] == [
        (date(2026, 10, 14), "All day: Fall break"),
        (date(2026, 10, 14), "9:30 AM-10:45 AM: ENGL 105 @ Room 120"),
        (date(2026, 10, 14), "5:00 PM-7:30 PM: Drumline rehearsal"),
    ]


def test_work_events_are_labelled():
    from jarvis.calendar_source import label
    ev = parse_events(ICS, date(2026, 10, 14), TZ)[1]
    assert label(ev, "VenueHorn").title == "VenueHorn: " + ev.title
    assert label(label(ev, "VenueHorn"), "VenueHorn").title == "VenueHorn: " + ev.title
