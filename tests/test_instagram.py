from datetime import datetime
from zoneinfo import ZoneInfo

from jarvis.instagram import clean, parse

TZ = ZoneInfo("America/New_York")


def test_clean_drops_trailing_hashtags():
    assert clean("New single out Friday!\n\n#music #newmusic") == "New single out Friday!"
    assert clean("the #1 show of the tour") == "the #1 show of the tour"


def test_parse_newest_first_in_local_time():
    data = {"business_discovery": {"media": {"data": [
        {"caption": "older", "timestamp": "2026-10-13T20:00:00+0000", "permalink": "https://instagram.com/p/a"},
        {"timestamp": "2026-10-14T13:30:00+0000", "permalink": "https://instagram.com/p/b"},
    ]}}}
    posts = parse(data, "aplasticplant", TZ)
    assert [p.text for p in posts] == ["", "older"]
    assert posts[0].at == datetime(2026, 10, 14, 9, 30, tzinfo=TZ)
    assert posts[0].who == "aplasticplant"


def test_expired_token_is_flagged(monkeypatch):
    import pytest
    from jarvis import instagram

    class Resp:
        status_code = 400
        def json(self):
            return {"error": {"code": 190, "message": "Error validating access token"}}

    monkeypatch.setattr(instagram.requests, "get", lambda *a, **k: Resp())
    with pytest.raises(instagram.TokenExpired):
        instagram.fetch_posts("1", "t", "aplasticplant", TZ)
