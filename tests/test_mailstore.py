import json

from cryptography.fernet import Fernet

from jarvis import mailstore


def test_seal_and_read_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_KEY", Fernet.generate_key().decode())
    path = tmp_path / "mail.enc"
    mailstore.seal({"flagged": [{"subject": "Café hours"}]}, path)
    assert b"Caf" not in path.read_bytes()
    assert mailstore.read(path) == {"flagged": [{"subject": "Café hours"}]}


def test_wrong_or_missing_key_reads_as_none(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_KEY", Fernet.generate_key().decode())
    path = tmp_path / "mail.enc"
    mailstore.seal({"flagged": []}, path)
    monkeypatch.setenv("MAIL_KEY", Fernet.generate_key().decode())
    assert mailstore.read(path) is None
    monkeypatch.delenv("MAIL_KEY")
    monkeypatch.setattr(mailstore, "KEY_FILE", tmp_path / "none.key")
    assert mailstore.read(path) is None


def test_key_file_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("MAIL_KEY", raising=False)
    keyfile = tmp_path / "k"
    keyfile.write_text(Fernet.generate_key().decode() + "\n")
    monkeypatch.setattr(mailstore, "KEY_FILE", keyfile)
    path = tmp_path / "mail.enc"
    mailstore.seal({"flagged": []}, path)
    assert mailstore.read(path) == {"flagged": []}


def test_plain_json_still_reads(tmp_path):
    path = tmp_path / "mail.json"
    path.write_text(json.dumps({"flagged": []}))
    assert mailstore.read(path) == {"flagged": []}


from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=ZoneInfo("America/New_York"))
FRESH_ID = format(int(NOW.timestamp() * 1000) << 20, "x")
OLD_ID = format(int((NOW - timedelta(days=5)).timestamp() * 1000) << 20, "x")


def item(id, at=NOW, **kw):
    return {"id": id, "at": at.isoformat(), "subject": f"S {id}", "level": "fyi", **kw}


def test_merge_adds_replaces_and_prunes():
    data = {"seen": [OLD_ID, FRESH_ID], "flagged": [item("a", status="done"), item("old", NOW - timedelta(days=5))]}
    run = {"seen": [FRESH_ID, "1"], "flagged": [item("a", why="updated"), item("b")]}
    out = mailstore.merge(data, run, NOW)
    assert out["seen"] == [FRESH_ID]  # "1" decodes to 1970, so it's past keeping too
    assert [(i["id"], i.get("status"), i.get("why")) for i in out["flagged"]] == [("a", "done", "updated"), ("b", None, None)]


def test_sync_mirrors_statuses_and_dismissals():
    data = {"flagged": [item("a"), item("b", status="denied")],
            "dismissed": [{"id": "x", "subject": "Old", "at": (NOW - timedelta(days=4)).isoformat()},
                          {"id": "y", "subject": "Restored", "at": NOW.isoformat()}]}
    out = mailstore.sync(data, [{"id": "a", "status": "done"}, {"id": "b", "status": "open"},
                                {"id": "y", "status": "open"}, {"id": "z", "status": "denied", "subject": "Spam"}], NOW)
    assert [i.get("status") for i in out["flagged"]] == ["done", None]
    assert [(d["id"], d["subject"]) for d in out["dismissed"]] == [("z", "Spam")]


def test_merge_cli_reports_unchanged(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAIL_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(mailstore, "SEALED", tmp_path / "mail.enc")
    monkeypatch.setattr(mailstore, "PLAIN", tmp_path / "mail.json")
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"seen": [FRESH_ID], "flagged": []}))
    monkeypatch.setattr(mailstore, "thread_time", lambda i: datetime.now(ZoneInfo("UTC")))
    mailstore.main(["merge", str(run)])
    mailstore.main(["merge", str(run)])
    assert capsys.readouterr().out.splitlines()[-1] == "unchanged"
    assert mailstore.read(tmp_path / "mail.enc")["seen"] == [FRESH_ID]


def test_plans_made_on_request_reach_the_hud_and_survive_a_rerun():
    plan = {"summary": "Worth it.", "steps": [{"who": "you", "text": "Apply."}]}
    out = mailstore.sync({"flagged": [item("a")]}, [{"id": "a", "status": "open", "plan": plan}], NOW)
    assert out["flagged"][0]["plan"] == plan
    out = mailstore.merge(out, {"flagged": [dict(item("a"), plan=None)]}, NOW)
    assert out["flagged"][0]["plan"] == plan
