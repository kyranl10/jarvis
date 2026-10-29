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


def test_start_unc_board_runs_the_workflow(monkeypatch):
    calls = []
    out = {"returncode": 0}
    monkeypatch.setattr(loop.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or SimpleNamespace(**out))
    assert loop.start_unc_board()
    assert calls == [["gh", "workflow", "run", "unc.yml", "--ref", "master"]]
    out["returncode"] = 1
    assert not loop.start_unc_board()


def test_start_status_sync_fires_the_task(monkeypatch):
    posts = []
    monkeypatch.setattr(loop.requests, "post", lambda url, **kw: posts.append((url, kw)) or SimpleNamespace(ok=True))
    monkeypatch.delenv("STATUS_SYNC_URL", raising=False)
    assert not loop.start_status_sync() and not posts  # not set up yet: nothing is sent
    monkeypatch.setenv("STATUS_SYNC_URL", "https://example.test/fire")
    monkeypatch.setenv("STATUS_SYNC_TOKEN", "tok")
    assert loop.start_status_sync()
    assert posts[0][0] == "https://example.test/fire"
    assert posts[0][1]["headers"]["Authorization"] == "Bearer tok"
