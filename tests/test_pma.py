from datetime import date, datetime
from zoneinfo import ZoneInfo

from jarvis.calendar_source import Event
from jarvis.pma import Post, announced, clean, find_event

TZ = ZoneInfo("America/New_York")


def at(d, h, m=0):
    return datetime(2026, 10, d, h, m, tzinfo=TZ)


def test_clean_drops_mentions_and_markdown():
    assert clean("<@&123456> **A reminder:** GMC cleanup <:pma:987> is at noon") == "A reminder: GMC cleanup is at noon"
    assert clean("@Brothers Feel free to pull up to Strat") == "Feel free to pull up to Strat"


def test_reads_the_time_day_and_place():
    ev = find_event(Post(at(13, 11, 58), "A reminder that we will have Chapter tonight at 9:00 in Hill Hall"))
    assert (ev.title, ev.start, ev.location) == ("PMA Chapter", at(13, 21), "Hill Hall")

    ev = find_event(Post(at(11, 0, 6), "A reminder: GMC cleanup is at noon, please show up to Hill Hall if you are available"))
    assert (ev.title, ev.start, ev.location) == ("PMA GMC cleanup", at(11, 12), "Hill Hall")

    ev = find_event(Post(at(14, 10), "Formal is this Saturday at 7pm at the Carolina Inn. Dress nice"))
    assert (ev.title, ev.start, ev.location) == ("PMA Formal", at(17, 19), "Carolina Inn")

    ev = find_event(Post(at(14, 10), "Brotherhood breakfast 10/16 at 9:30 in the morning"))
    assert (ev.title, ev.start) == ("PMA Brotherhood breakfast", at(16, 9, 30))


def test_ignores_posts_without_a_time():
    assert find_event(Post(at(11, 17, 56), "Feel free to pull up to Strat whenever, we just vibing for the rest of the evening")) is None
    assert find_event(Post(at(11, 17), "Dues are $150 for 2k26, see Hill 107")) is None


def test_skips_events_already_on_the_calendar_and_repeat_reminders():
    posts = [Post(at(13, 9), "Chapter tonight at 9 in Hill Hall"),
             Post(at(13, 18), "Reminder: chapter tonight at 9:00pm!"),
             Post(at(13, 12), "Exec meeting tomorrow at 8pm in Hill 107"),
             Post(at(10, 12), "Retreat Saturday at 2pm")]
    known = [Event("Exec Meeting", at(14, 20), at(14, 21), False)]
    found = announced(posts, known, date(2026, 10, 13), date(2026, 10, 16))
    assert [(e.title, e.start) for e in found] == [("PMA Chapter", at(13, 21))]


def test_briefing_shows_pma_posts_and_reads_new_ones():
    from jarvis import style
    from jarvis.inbox import since
    now, today = at(14, 7, 30), date(2026, 10, 14)
    posts = [Post(at(14, 0, 15), "Chapter tonight at 9 in Hill Hall"), Post(at(13, 11, 58), "Dues are due Friday")]
    _, body = style.notification(today, now, None, [], [], [], "sir", None, posts)
    assert body.splitlines()[-3:] == ["▸ PMA", "  Today 12:15 AM — Chapter tonight at 9 in Hill Hall",
                                      "  Yesterday 11:58 AM — Dues are due Friday"]
    voice = style.spoken(today, None, [], [], [], "sir", None, posts[:1])
    assert "From PMA: Chapter tonight at 9 in Hill Hall." in voice
    hud = style.hud(today, now, None, [], [], [], "sir", voice, None, posts, since(now))
    assert [(p["when"], p["new"]) for p in hud["pma"]] == [("Today 12:15 AM", True), ("Yesterday 11:58 AM", False)]


def test_forwarded_messages_keep_their_original_time(monkeypatch):
    from jarvis import pma
    page = [{"content": "", "timestamp": "2026-10-14T05:10:00+00:00",
             "message_snapshots": [{"message": {"content": "<@&1> Chapter tonight at 9:00 in Hill Hall",
                                                 "timestamp": "2026-10-13T15:58:00+00:00"}}]},
            {"content": "", "timestamp": "2026-10-14T05:00:00+00:00"}]

    class Resp:
        def raise_for_status(self): pass
        def json(self): return page
    monkeypatch.setattr(pma.requests, "get", lambda *a, **k: Resp())
    assert pma.fetch_posts("token", "1", TZ) == [Post(at(13, 11, 58), "Chapter tonight at 9:00 in Hill Hall")]
