from types import SimpleNamespace

from jarvis import loop


def test_sync_requested_only_when_the_hud_posted(monkeypatch):
    replies = {"https://ntfy.sh/t-sync/json": '{"id":"a","event":"open"}\n{"id":"b","event":"message","message":"sync"}\n'}
    monkeypatch.setattr(loop.requests, "get", lambda url, **kw: SimpleNamespace(text=replies[url]))
    assert loop.sync_requested("t", 0)
    replies["https://ntfy.sh/t-sync/json"] = ""
    assert not loop.sync_requested("t", 0)
