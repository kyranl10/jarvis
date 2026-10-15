from datetime import date, datetime
from zoneinfo import ZoneInfo

from jarvis import style
from jarvis.calendar_source import Event
from jarvis.canvas import Assignment

TZ = ZoneInfo("America/New_York")
TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 7, 30, tzinfo=TZ)
WEATHER = {"temp": 58, "sky": "overcast", "high": 86, "low": 55, "rain": 0}


def at(h, m=0, d=14):
    return datetime(2026, 10, d, h, m, tzinfo=TZ)


EVENTS = [Event("MATH 101 – Client Meeting", at(16), at(16, 30), False,
                "https://example.zoom.us/j/123?pwd=secret")]
COMING = [(date(2026, 10, 15), Event("NO CLASS: Fall Break", at(0, d=15), at(0, d=16), True))]
DUE = [Assignment("Homework 7 [HIST210.001.FA26]", at(23, 59, d=18), False),
       Assignment("Assignment 3: Spatial Data and GIS [BIOL202.001.FA26]", at(23, 59, d=19), False)]


def test_notification_layout():
    title, body = style.notification(TODAY, NOW, WEATHER, EVENTS, COMING, DUE, "sir")
    assert title == "Good morning, sir"
    assert body.splitlines() == [
        "Wednesday, October 14th",
        "58° now · overcast · H 86° L 55°",
        "",
        "▸ TODAY",
        "  4 PM — MATH 101 – Client Meeting · online",
        "",
        "▸ AHEAD",
        "  Tomorrow, All day — Fall Break",
        "",
        "▸ DUE",
        "  Sun — Homework 7 · HIST 210",
        "  Mon — Assignment 3: Spatial Data and GIS · BIOL 202",
    ]
    assert "secret" not in body


def test_spoken_reads_like_jarvis():
    text = style.spoken(TODAY, WEATHER, EVENTS, COMING, DUE, "sir")
    assert text == (
        "Today is Wednesday the 14th. It's currently 58 degrees and overcast, "
        "with a high of 86. You have one engagement today: MATH 101 – Client Meeting at 4 PM. "
        "Homework 7 for HIST 210 is due on Sunday, and 1 more this week. "
        "Tomorrow, Fall Break. Shall I leave you to it?"
    )


def test_hud_data_hides_links():
    data = style.hud(TODAY, NOW, WEATHER, EVENTS, COMING, DUE, "sir", "hello")
    assert data["today"][0] == {"time": "4 PM", "end": "4:30 PM",
                                "title": "MATH 101 – Client Meeting", "place": "online",
                                "start_at": "2026-10-14T16:00-04:00", "all_day": False}
    assert data["due"][0]["course"] == "HIST 210" and data["due"][0]["day"] == "Sun"
    assert "secret" not in str(data)


def test_room_kept_when_link_follows():
    assert style.where("Room 120; https://example.zoom.us/j/1") == "Room 120"
    assert style.where("Kenan Stadium") == "Kenan Stadium"


def test_instagram_captions():
    from jarvis.instagram import Post
    posts = [Post(at(6, 5), "aplasticplant", "Out now. Link in bio", "https://instagram.com/p/x")]
    _, body = style.notification(TODAY, NOW, WEATHER, [], [], [], "sir", insta=posts)
    assert body.splitlines()[-2:] == ["▸ INSTAGRAM", "  @aplasticplant · Today 6:05 AM — Out now. Link in bio"]
    assert "aplasticplant posted on Instagram: Out now. Link in bio." in style.spoken(TODAY, WEATHER, [], [], [], "sir", insta=posts)
    data = style.hud(TODAY, NOW, WEATHER, [], [], [], "sir", "hello", insta=posts)
    assert data["insta"] == [{"who": "aplasticplant", "when": "Today 6:05 AM", "text": "Out now. Link in bio",
                              "url": "https://instagram.com/p/x"}]
