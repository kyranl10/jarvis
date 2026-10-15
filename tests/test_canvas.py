from datetime import date
from zoneinfo import ZoneInfo

from jarvis.canvas import parse_assignments

TZ = ZoneInfo("America/New_York")

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Instructure//Canvas//EN
BEGIN:VEVENT
UID:event-assignment-101
SUMMARY:Quiz 3 [ENGL 105]
DTSTART:20261015T035900Z
DTEND:20261015T035900Z
END:VEVENT
BEGIN:VEVENT
UID:event-assignment-102
SUMMARY:Problem Set 5 [MATH 101]
DTSTART;VALUE=DATE:20261016
DTEND;VALUE=DATE:20261017
END:VEVENT
BEGIN:VEVENT
UID:event-assignment-103
SUMMARY:Final Project [MATH 101]
DTSTART:20261210T035900Z
DTEND:20261210T035900Z
END:VEVENT
BEGIN:VEVENT
UID:event-calendar-event-7
SUMMARY:Office hours [ENGL 105]
DTSTART:20261014T180000Z
DTEND:20261014T190000Z
END:VEVENT
END:VCALENDAR
"""


def test_due_soon_window_and_wording():
    today = date(2026, 10, 14)
    got = [a.describe(today) for a in parse_assignments(ICS, today, TZ)]
    assert got == [
        "Due today at 11:59 PM: Quiz 3 [ENGL 105]",
        "Due Friday: Problem Set 5 [MATH 101]",
    ]


def test_window_can_be_narrowed():
    today = date(2026, 10, 14)
    assert [a.title for a in parse_assignments(ICS, today, TZ, days=2)] == ["Quiz 3 [ENGL 105]"]
