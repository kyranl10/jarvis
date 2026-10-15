from types import SimpleNamespace

from jarvis import loop


def test_sync_requested_only_when_the_hud_posted(monkeypatch):
    replies = {"https://ntfy.sh/t-sync/json": '{"id":"a","event":"open"}\n{"id":"b","event":"message","message":"sync"}\n'}
    monkeypatch.setattr(loop.requests, "get", lambda url, **kw: SimpleNamespace(text=replies[url]))
    assert loop.sync_requested("t", 0)
    replies["https://ntfy.sh/t-sync/json"] = ""
    assert not loop.sync_requested("t", 0)


def test_remote_head_reads_ls_remote(monkeypatch):
    out = {"stdout": "abc123\tHEAD\n", "returncode": 0}
    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **kw: SimpleNamespace(**out))
    assert loop.remote_head() == "abc123"
    out.update(stdout="", returncode=128)
    assert loop.remote_head() == ""
