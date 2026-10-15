from datetime import datetime
from zoneinfo import ZoneInfo

from jarvis import band

TZ = ZoneInfo("America/New_York")


def _vevent(uid, summary, start, end=None, location="", description=""):
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"SUMMARY:{summary}"]
    if len(start) == 8:
        lines.append(f"DTSTART;VALUE=DATE:{start}")
    else:
        lines += [f"DTSTART:{start}", f"DTEND:{end or start}"]
    if location:
        lines.append(f"LOCATION:{location}")
    if description:
        lines.append(f"DESCRIPTION:{description}")
    return lines + ["END:VEVENT"]


# Shaped like the real GroupSpot feed: UTC times, tags in titles, no descriptions
EVENTS = [
    ("MTH Rehearsal", "20261020T223000Z", "20261021T003000Z", "Bill Koman Practice Complex\\, South Road\\, Chapel Hill\\, NC", ""),  # Tue
    ("MTH Rehearsal", "20261019T223000Z", "20261020T003000Z", "Bill Koman Practice Complex", ""),  # Mon
    ("FALL BREAK", "20261016", None, "", ""),
    ("Fockey Band", "20261018T171500Z", "20261018T190000Z", "Karen Shelton Stadium", ""),
    ("PB4 - Volleyball", "20261023T221500Z", "20261024T000000Z", "Carmichael Arena", ""),
    ("VPB - WBB Exhibition", "20261018T161500Z", "20261018T180000Z", "Carmichael Arena", ""),
    ("Volunteer Band @ dOOk", "20261017T173000Z", "20261017T200000Z", "Bill Koman Practice Complex", ""),
    ("GAME DAY v Syracuse", "20261024T181500Z", "20261024T230000Z", "", ""),
    ("All RP - Men's Soccer", "20261030T221500Z", "20261031T000000Z", "Dorrance Field\\, Chapel Hill\\, NC", ""),
    ("MBB v Charlotte", "20261027T224500Z", "20261028T010000Z", "Dean Smith Center", ""),
    ("Sectional", "20261028T223000Z", "20261028T233000Z", "Hill Hall", "Drumline rp3 only"),
    ("PB1 - Volleyball", "20261031T234500Z", "20261101T010000Z", "Carmichael Arena", "pb1 and rp3"),
    ("Pep Band Rehearsal", "20261022T223000Z", "20261022T233000Z", "Hill Hall", ""),  # a Thursday, wrong group
    ("THANKSGIVING BREAK (No Rehearsal)", "20261029", None, "", ""),  # a Thursday
    ("GAME DAY at Duke", "20261107T170000Z", "20261107T230000Z", "", ""),
]
ICS = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//test//EN"]
                  + sum((_vevent(i, *e) for i, e in enumerate(EVENTS)), []) + ["END:VCALENDAR"])
NOW = datetime(2026, 10, 14, 15, 30, tzinfo=TZ)


def kept_titles():
    return [e.title for e in band.parse(ICS, NOW.date(), TZ, 30) if band.decide(e)[0]]


def test_keeps_only_kyrans_events():
    assert kept_titles() == ["MTH Rehearsal", "GAME DAY v Syracuse", "Sectional", "All RP - Men's Soccer",
                             "PB1 - Volleyball"]


def test_rehearsal_day_is_eastern():
    # 22:30 UTC Tuesday is 6:30 PM Tuesday in Chapel Hill
    tue = next(e for e in band.parse(ICS, NOW.date(), TZ, 30) if e.title == "MTH Rehearsal" and e.start.day == 20)
    assert (tue.start.weekday(), tue.start.hour, tue.start.minute) == (1, 18, 30)


def test_reasons():
    reasons = {e.title + str(e.start.day): band.decide(e)[1] for e in band.parse(ICS, NOW.date(), TZ, 30)}
    assert reasons["FALL BREAK16"] == "already on calendar"
    assert reasons["MTH Rehearsal19"] == "rehearsal not on Tue/Thu"
    assert reasons["Fockey Band18"] == "other group"
    assert reasons["MBB v Charlotte27"] == "not tagged for rp3"


def test_build_returns_calendar_events(monkeypatch):
    monkeypatch.setattr(band, "fetch", lambda url: ICS)
    out = band.build("https://example.test/feed", NOW.date(), TZ, days=30)
    first = out[0]
    assert (first.title, first.start.day, first.location) == ("MTH Rehearsal", 20, "Bill Koman Practice Complex")
    assert first.describe() == "6:30 PM-8:30 PM: MTH Rehearsal @ Bill Koman Practice Complex"


def test_build_hides_the_url(monkeypatch, capsys):
    def boom(url):
        raise RuntimeError(f"failed {url}")
    monkeypatch.setattr(band, "fetch", boom)
    assert band.build("https://example.test/calendarSync?token=SECRET", NOW.date(), TZ) == []
    assert "SECRET" not in capsys.readouterr().out
